"""BWIKI 检测与暂存更新；校验通过后切换目录，失败回滚。"""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

from roco_data import JsonQueries
from .service import BusyError

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
# 复用独立采集脚本及其校验，命令行与网页保持相同的转换规则。
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from check_bwiki_updates import check_updates
from collect_bwiki_modules import fetch_modules, save


class DataUpdates:
    def __init__(self, manager):
        self.manager = manager
        self.root = Path(manager.data_dir).resolve().parent
        self.lock = threading.RLock()
        self.state = {'busy': False, 'operation': None, 'message': '点击检测，比较 BWIKI 与本地模块版本。',
                      'report': None, 'error': None, 'updated_at': None}
        path = self.root / 'update_status.json'
        if path.exists():
            try:
                self.state.update(json.loads(path.read_text(encoding='utf-8')))
                if self.state['busy']:
                    self.state.update(busy=False, error='上次任务随服务退出而中断，请重新检测。')
            except (OSError, ValueError):
                pass

    def snapshot(self):
        with self.lock:
            state = deepcopy(self.state)
        manifest = self.root / 'converted/manifest.json'
        if manifest.exists():
            record = json.loads(manifest.read_text(encoding='utf-8'))
            state['local'] = {key: record.get(key) for key in
                              ('converted_at', 'pets', 'skills', 'features', 'status')}
        with self.manager.lock:
            counts = self.manager.queries.statistics()['data']
        state.setdefault('local', {}).update(pets=counts['pets'], skills=counts['skills_with_details'],
                                             features=counts['features'])
        return state

    def start(self, operation):
        with self.manager.lock, self.lock:
            if self.state['busy']:
                raise BusyError('数据任务正在执行，请等待完成')
            if operation == 'update':
                if any(s.snapshot(False)['busy'] for s in self.manager.sessions.values()):
                    raise BusyError('请等待对话结束后更新数据')
                self.manager.data_updating = True
            self.state.update(busy=True, operation=operation, error=None,
                              message='正在检测模块版本…' if operation == 'check' else '正在下载 BWIKI 模块…')
            threading.Thread(target=self.execute, args=(operation,), daemon=True).start()
            return deepcopy(self.state)

    def message(self, value):
        with self.lock:
            self.state['message'] = value

    def execute(self, operation):
        try:
            if operation == 'check':
                report = check_updates(self.root / 'modules/response.json')
                with self.lock:
                    self.state['report'] = report
                self.message('检测完成。')
            else:
                self.update()
        except Exception as exc:
            # curl 的原始诊断只包含公开 BWIKI 地址，保留转换器的具体阻断原因。
            detail = (exc.stderr or b'').decode('utf-8', errors='replace') if isinstance(exc, subprocess.CalledProcessError) else str(exc)
            with self.lock:
                self.state.update(error=detail.strip()[-2000:] or '网络请求失败，请重试。',
                                  message='任务失败，正式数据保持原样。')
        finally:
            with self.manager.lock, self.lock:
                self.manager.data_updating = False
                self.state.update(busy=False, updated_at=datetime.now().astimezone().isoformat())
                try:
                    save(self.root / 'update_status.json', self.state)
                except OSError:
                    self.state['error'] = (self.state['error'] or '') + ' 检测记录保存失败。'

    def update(self):
        with tempfile.TemporaryDirectory(prefix='.update-', dir=self.root) as name:
            staging = Path(name)
            raw, metadata = fetch_modules()
            save(staging / 'modules/response.json', raw)
            save(staging / 'modules/fetch.json', metadata)
            self.message('下载完成，正在转换精灵、技能和特性…')
            subprocess.run([sys.executable, str(SCRIPTS / 'collect_bwiki_modules.py'), '--all',
                            '--from-response', str(staging / 'modules/response.json'),
                            '--output', str(staging / 'converted')],
                           capture_output=True, check=True, timeout=180)
            manifest_path = staging / 'converted/manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest['status'] != 'complete':
                raise ValueError('转换存在缺失的技能引用，请核查后再更新。')
            manifest.update(source=metadata, reused_local=False)
            save(manifest_path, manifest)
            JsonQueries(staging / 'converted')
            self.message('校验通过，正在切换数据并重新加载…')
            with self.manager.lock:
                # 同一文件系统重命名；两个目录全部切换后才发布新查询快照。
                moved, installed = [], []
                try:
                    for folder in ('converted', 'modules'):
                        target = self.root / folder
                        if target.exists():
                            target.rename(staging / (folder + '.previous'))
                            moved.append(folder)
                        (staging / folder).rename(target)
                        installed.append(folder)
                    self.manager.reload_data()
                except Exception:
                    for folder in reversed(installed):
                        shutil.rmtree(self.root / folder)
                    for folder in reversed(moved):
                        (staging / (folder + '.previous')).rename(self.root / folder)
                    raise
            with self.lock:
                self.state['report'] = None
            self.message('更新完成，Agent 已加载最新 JSON，会话上下文已清空。请再次检测确认版本。')
