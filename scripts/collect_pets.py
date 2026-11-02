"""批量采集精灵资料与技能关联 ID；技能详情由 collect_skills.py 采集。"""
import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

API = 'https://091p.com/lkwg/wiki-api.php'

ROOT = Path(__file__).resolve().parents[1] / 'data'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
    temporary.replace(path)


def now():
    return datetime.now().astimezone().isoformat()


def skill_references(skills):
    groups = {}
    for group in ('level', 'machine', 'blood'):
        groups[group] = []
        for skill in skills.get(group, []):
            reference = {'skill_id': skill['skill_id']}
            if 'level' in skill:
                reference['level'] = skill['level']
            if 'bloodline' in skill:
                reference['bloodline_id'] = skill['bloodline']['id']
            groups[group].append(reference)
    return groups


def validate(data, key, params):
    if not isinstance(data, dict) or data.get('ok') is not True or key not in data:
        raise ValueError('接口失败或响应缺少 ' + key)
    if key in ('data', 'sections', 'pet') and not isinstance(data[key], dict):
        raise ValueError('资料字段类型异常')
    if key in ('resources', 'items') and not isinstance(data[key], list):
        raise ValueError('列表字段类型异常')
    if 'skill_id' in params and data['data'].get('skill_id') != params['skill_id']:
        raise ValueError('技能 ID 不匹配')
    if params.get('resource') == 'pet-detail':
        if data['sections'].get('base', {}).get('pet_id') != params['pet_id']:
            raise ValueError('精灵 ID 不匹配')


class Collector:
    def __init__(self, root=ROOT, refresh=False, interval=1):
        self.root, self.refresh, self.interval = root, refresh, interval
        self.fetched = set()

    def fetch(self, path, key, **params):
        url = API + '?' + urlencode(params)
        record = {'file': str(path.relative_to(self.root)), 'request_url': url}
        try:
            if path.exists() and (not self.refresh or path in self.fetched):
                data = json.loads(path.read_text(encoding='utf-8'))
                validate(data, key, params)
                record['reused_local'] = True
            else:
                for attempt in range(3):
                    time.sleep(self.interval * (attempt + 1))
                    try:
                        response = subprocess.run(
                            ['curl', '-sS', '-L', '--fail', '--max-time', '45', url],
                            capture_output=True, check=True,
                        )
                        data = json.loads(response.stdout)
                        validate(data, key, params)
                        break
                    except (subprocess.SubprocessError, ValueError):
                        if attempt == 2:
                            raise
                save(path, data)
                self.fetched.add(path)
                record['fetched_at'] = now()
            record.update(status='ok', source=data.get('source'),
                          updated_at=data.get('updated_at'), stale=data.get('stale', False),
                          warning=data.get('warning'))
            return data, record
        except (subprocess.SubprocessError, ValueError, OSError) as exc:
            record.update(status='error', error=str(exc))
            return None, record

    def collect(self, pet_id, catalog):
        out = self.root / 'pets' / str(pet_id)
        manifest = {'pet_id': pet_id, 'started_at': now(), 'status': 'running', 'requests': []}

        def fetch(resource, key='data', **params):
            path = out / f'{resource}.json'
            data, record = self.fetch(path, key, resource=resource, **params)
            manifest['requests'].append(record)
            save(out / 'manifest.json', manifest)
            print(pet_id, resource, params.get('skill_id', ''), record['status'], flush=True)
            return data

        detail = fetch('pet-detail', 'sections', pet_id=pet_id)
        sections = dict(detail['sections']) if detail else {}
        expected = {r['section']: r['resource'] for r in catalog['resources']
                    if r.get('id_param') == 'pet_id' and r.get('section')}
        for section, resource in expected.items():
            if sections.get(section) is None:
                data = fetch(resource, pet_id=pet_id)
                if data is not None:
                    sections[section] = data['data']
        appearance = fetch('pet-appearance', 'pet', pet_id=pet_id)
        if appearance:
            sections['appearance'] = appearance['pet']
            sections.setdefault('base', appearance['pet'])
        skills = sections.get('skills', {})
        ids = sorted({s['skill_id'] for group in ('level', 'machine', 'blood')
                      for s in skills.get(group, [])})
        if 'skills' in sections:
            sections['skills'] = skill_references(skills)
        missing = [s for s in expected if sections.get(s) is None]
        errors = [r for r in manifest['requests'] if r['status'] == 'error']
        combined = {'pet_id': pet_id, 'name': sections.get('base', {}).get('name'),
                    'sections': sections, 'skill_ids': ids,
                    'skill_detail_directory': '../../skills', 'provenance': 'manifest.json'}
        save(out / 'combined.json', combined)
        manifest.update(finished_at=now(), status='partial' if missing or errors else 'complete',
                        name=combined['name'], missing_sections=missing, skill_count=len(ids),
                        scope='公开精灵分区及技能 ID 与学习条件；技能详情独立采集，图片保留 URL。')
        save(out / 'manifest.json', manifest)
        return {k: manifest[k] for k in ('pet_id', 'name', 'status', 'missing_sections', 'skill_count')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--ids', nargs='+', type=int, help='指定精灵 ID，例如 3002 3003')
    group.add_argument('--all', action='store_true', help='分页读取图鉴并采集全部精灵')
    parser.add_argument('--limit', type=int, help='限制本次采集精灵数量')
    parser.add_argument('--refresh', action='store_true', help='重新请求所选资料（上游仍可能返回缓存）')
    parser.add_argument('--interval', type=float, default=1, help='请求间隔秒数，至少 1 秒')
    args = parser.parse_args()
    if args.interval < 1 or (args.limit is not None and args.limit < 1) or any(i < 1 for i in args.ids or []):
        parser.error('间隔至少 1 秒，ID 和数量须为正数')
    collector = Collector(refresh=args.refresh, interval=args.interval)
    catalog, record = collector.fetch(ROOT / 'api_catalog.json', 'resources', api='help')
    if catalog is None:
        parser.exit(1, '接口目录读取失败：' + record['error'] + '\n')
    ids = list(dict.fromkeys(args.ids or []))
    if args.all:
        page = 1
        while True:
            data, record = collector.fetch(ROOT / 'lists' / f'pets_{page}.json', 'items',
                                           resource='pets', page_no=page, page_size=100)
            if data is None:
                save(ROOT / 'discovery_error.json', record)
                parser.exit(1, '图鉴分页失败，已保存失败记录\n')
            ids = list(dict.fromkeys(ids + [p['pet_id'] for p in data['items']]))
            if (args.limit and len(ids) >= args.limit) or not data.get('has_more'):
                break
            if not data['items']:
                parser.exit(1, '图鉴分页为空但仍标记 has_more，停止采集\n')
            page += 1
    ids = ids[:args.limit] if args.limit else ids
    summary = {'started_at': now(), 'selected_ids': ids, 'pets': []}
    for pet_id in ids:
        summary['pets'].append(collector.collect(pet_id, catalog))
        save(ROOT / 'batch_manifest.json', summary)
    summary['finished_at'] = now()
    save(ROOT / 'batch_manifest.json', summary)
    failures = sum(p['status'] != 'complete' for p in summary['pets'])
    print(f'完成 {len(ids)} 只；待补采 {failures} 只', flush=True)
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
