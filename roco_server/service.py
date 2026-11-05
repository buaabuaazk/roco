"""独立会话、后台执行及脱敏事件回放。"""
from copy import deepcopy
from datetime import datetime, timezone
import os
import threading
import time
from uuid import uuid4

from roco_agent import RocoAgent
from roco_agent.llm import ChatModel, DEFAULT_MODEL
from roco_agent.session_log import LOG_DIR, SessionLog
from roco_data import DEFAULT_JSON_DIR, JsonQueries, RocoTools


class BusyError(ValueError):
    pass


class Session:
    def __init__(self, queries, model, log_dir, model_factory):
        self.lock = threading.RLock()
        self.queries, self.model_name, self.model_factory = queries, model, model_factory
        self.agent = self.client = None
        self.runs = []
        self.active = None
        self.sequence = 0
        self.title = '新的调试会话'
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.logger = SessionLog(log_dir, on_event=self.on_event)
        self.id = self.logger.session_id

    def on_event(self, record):
        # SessionLog 先落盘并脱敏；前端收到的内容与本地记录一致。
        with self.lock:
            self.sequence += 1
            if self.active is not None:
                event = {**record, 'sequence': self.sequence, 'run_id': self.active['id']}
                self.active['events'].append(event)
                if record['event'] == 'turn_end':
                    self.active.update(status=record['status'], answer=record.get('answer', ''))

    def snapshot(self, include_runs=True):
        with self.lock:
            value = {'id': self.id, 'title': self.title, 'model': self.model_name,
                     'created_at': self.created_at, 'busy': self.active is not None,
                     'log_file': self.logger.path.name}
            if include_runs:
                value['runs'] = deepcopy(self.runs)
            return value

    def start(self, question):
        with self.lock:
            if self.active is not None:
                raise BusyError('这个会话正在处理问题，请等待本轮结束')
            run = {'id': uuid4().hex, 'question': question, 'answer': '', 'status': 'running',
                   'done': False, 'elapsed_seconds': 0, 'events': []}
            self.runs.append(run)
            self.active = run
            if len(self.runs) == 1:
                self.title = question[:24]
            try:
                self.logger.write('run_start', question=question)
            except OSError:
                self.runs.pop()
                self.active = None
                if not self.runs:
                    self.title = '新的调试会话'
                raise
            threading.Thread(target=self.execute, args=(run,), daemon=True).start()
            return run['id']

    def execute(self, run):
        started = time.monotonic()
        try:
            if self.agent is None:
                self.client = self.model_factory(self.model_name)
                self.agent = RocoAgent(self.client, self.queries, logger=self.logger)
            self.agent.ask(run['question'])
        except (ValueError, OSError) as exc:
            self.logger.write('turn_end', status='error', answer=str(exc), error_type=type(exc).__name__)
        except Exception as exc:
            self.logger.write('turn_end', status='error', answer='本轮执行失败，请检查本地服务。',
                              error_type=type(exc).__name__)
        finally:
            with self.lock:
                run['elapsed_seconds'] = round(time.monotonic() - started, 3)
                if run['status'] == 'running':
                    run.update(status='error', answer='本轮执行中断，请检查本地日志是否可写。')
                run['done'] = True
                try:
                    self.logger.write('run_finished', status=run['status'],
                                      elapsed_seconds=run['elapsed_seconds'])
                finally:
                    self.active = None

    def reset(self):
        with self.lock:
            if self.active is not None:
                raise BusyError('请在本轮结束后清空会话')
            if self.agent is not None:
                self.agent.reset()
            self.runs.clear()
            self.title = '新的调试会话'

    def events(self, run_id, after=0):
        with self.lock:
            run = next((run for run in self.runs if run['id'] == run_id), None)
            if run is None:
                raise KeyError(run_id)
            return deepcopy([e for e in run['events'] if e['sequence'] > after]), run['done']


class SessionManager:
    def __init__(self, data_dir=DEFAULT_JSON_DIR, log_dir=LOG_DIR, model_factory=ChatModel):
        self.lock = threading.RLock()
        self.data_dir, self.log_dir, self.model_factory = data_dir, log_dir, model_factory
        self.queries = JsonQueries(data_dir)
        self.sessions = {}

    def config(self):
        return {'default_model': os.environ.get('LLM_MODEL_ID', '').strip() or DEFAULT_MODEL,
                'key_configured': bool(os.environ.get('ZZZ_API_KEY', '').strip()),
                'data': self.queries.statistics()['data'],
                'tools': [tool['function']['name'] for tool in RocoTools(self.queries).definitions]}

    def create(self, model=None):
        with self.lock:
            session = Session(self.queries, (model or '').strip() or self.config()['default_model'],
                              self.log_dir, self.model_factory)
            self.sessions[session.id] = session
            return session.snapshot()

    def get(self, session_id):
        with self.lock:
            return self.sessions[session_id]

    def list(self):
        with self.lock:
            return [session.snapshot(False) for session in reversed(list(self.sessions.values()))]

    def start(self, session_id, question):
        with self.lock:
            return self.get(session_id).start(question)

    def reload_data(self):
        with self.lock:
            if any(session.snapshot(False)['busy'] for session in self.sessions.values()):
                raise BusyError('有会话正在运行，请等待完成后重新加载数据')
            queries = JsonQueries(self.data_dir)
            for session in self.sessions.values():
                session.reset()
                session.queries = queries
                if session.agent is not None:
                    session.agent.tools = RocoTools(queries)
            self.queries = queries
            return self.config()

    def close(self):
        with self.lock:
            for session in self.sessions.values():
                if session.client is not None:
                    session.client.close()
