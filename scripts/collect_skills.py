"""独立采集技能图鉴与详情，复用 data/skills 下的成功响应。"""
import argparse

from collect_pets import Collector, ROOT, now, save


def collect(collector, ids=None, limit=None):
    root = collector.root
    manifest = {'started_at': now(), 'status': 'running', 'requests': [], 'selected_ids': []}
    target = root / 'skills_manifest.json'

    def request(path, key, **params):
        data, record = collector.fetch(path, key, **params)
        manifest['requests'].append(record)
        save(target, manifest)
        mode = 'local' if record.get('reused_local') else 'network'
        print(params['resource'], params.get('skill_id', params.get('page_no')),
              record['status'], mode, flush=True)
        return data

    if ids is None:
        ids = []
        page = 1
        while True:
            data = request(root / 'lists' / f'skills_{page}.json', 'items',
                           resource='skills', page_no=page, page_size=100)
            if data is None:
                manifest.update(status='partial', finished_at=now())
                save(target, manifest)
                return 1
            try:
                page_ids = [item['skill_id'] for item in data['items']]
                if any(type(i) is not int or i < 1 for i in page_ids):
                    raise ValueError('技能 ID 无效')
                if type(data.get('has_more')) is not bool:
                    raise ValueError('分页响应缺少 has_more 标记')
                if data['has_more'] and not set(page_ids).difference(ids):
                    raise ValueError('分页未返回新技能却标记 has_more')
            except (KeyError, TypeError, ValueError) as exc:
                manifest.update(status='partial', error=str(exc), finished_at=now())
                save(target, manifest)
                return 1
            ids = list(dict.fromkeys(ids + page_ids))
            if (limit and len(ids) >= limit) or not data['has_more']:
                break
            page += 1
    ids = list(dict.fromkeys(ids))
    ids = ids[:limit] if limit else ids
    manifest['selected_ids'] = ids
    save(target, manifest)
    for skill_id in ids:
        request(root / 'skills' / f'{skill_id}.json', 'data',
                resource='skill-detail', skill_id=skill_id)
    failures = sum(r['status'] == 'error' for r in manifest['requests'])
    manifest.update(status='partial' if failures else 'complete', finished_at=now())
    save(target, manifest)
    print(f'处理 {len(ids)} 个技能；失败 {failures} 项', flush=True)
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true', help='分页读取技能图鉴')
    group.add_argument('--ids', nargs='+', type=int, help='指定技能 ID')
    parser.add_argument('--limit', type=int, help='本次最多处理多少个技能，包含已保存项')
    parser.add_argument('--refresh', action='store_true', help='重新请求列表和详情')
    parser.add_argument('--interval', type=float, default=1, help='请求间隔秒数，至少 1 秒')
    args = parser.parse_args()
    if (not args.interval >= 1 or (args.limit is not None and args.limit < 1)
            or any(i < 1 for i in args.ids or [])):
        parser.error('间隔至少 1 秒，ID 和数量须为正数')
    raise SystemExit(collect(Collector(root=ROOT, refresh=args.refresh, interval=args.interval),
                             ids=args.ids, limit=args.limit))


if __name__ == '__main__':
    main()
