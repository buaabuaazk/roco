"""只请求模块修订元数据，检查 BWIKI 相比本地模块快照是否有更新。"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode

from collect_bwiki_modules import API, ROOT, RULE_REVISIONS, save


def compare_revisions(local, remote):
    if remote.get('error'):
        raise ValueError(str(remote['error']))
    latest = {page['pageid']: page for page in remote['query']['pages']}
    changed, unavailable = [], []
    unchanged = 0
    for page in local['query']['pages']:
        old = page['revisions'][0]
        current = latest.get(page['pageid'])
        if not current or current.get('missing') or not current.get('revisions'):
            unavailable.append(page['title'])
            continue
        revision = current['revisions'][0]
        if revision['revid'] == old['revid']:
            unchanged += 1
        else:
            changed.append({'title': current['title'], 'page_id': page['pageid'],
                            'local_revision': old['revid'], 'remote_revision': revision['revid'],
                            'local_timestamp': old['timestamp'], 'remote_timestamp': revision['timestamp'],
                            'conversion_rule': page['title'] in RULE_REVISIONS})
    return {'status': 'partial' if unavailable else 'updates_available' if changed else 'up_to_date',
            'checked_modules': len(local['query']['pages']), 'unchanged_modules': unchanged,
            'changed_modules': changed, 'unavailable_modules': unavailable}


def check_updates(snapshot):
    local = json.loads(snapshot.read_text(encoding='utf-8'))
    ids = [str(page['pageid']) for page in local['query']['pages']]
    if not ids or len(ids) > 50:
        raise ValueError('本检查支持包含 1～50 个模块的本地快照')
    url = API + '?' + urlencode(dict(action='query', pageids='|'.join(ids), prop='revisions',
        rvprop='ids|timestamp', format='json', formatversion=2, maxlag=5))
    response = subprocess.run(['curl', '-fsSL', '--max-time', '45', '--retry', '2',
                               '--retry-delay', '2', url], capture_output=True, check=True)
    remote = json.loads(response.stdout)
    report = compare_revisions(local, remote)
    report.update(checked_at=datetime.now().astimezone().isoformat(),
                  local_snapshot=str(snapshot.resolve()), request_url=url,
                  response_bytes=len(response.stdout),
                  scope='本地快照中的模块修订检查；正文及未纳入快照的页面未请求')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'modules/response.json')
    parser.add_argument('--output', type=Path, help='可选：另存检查报告，采集数据保持原样')
    args = parser.parse_args()
    try:
        report = check_updates(args.snapshot)
        if args.output:
            save(args.output, report)
        print(json.dumps(report, ensure_ascii=False, indent=4))
        return 2 if report['unavailable_modules'] else 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'更新检查失败：{exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
