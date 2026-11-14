"""解析本地精灵图片文件名为BWIKI图片直链，仅请求地址元数据。"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'bwiki'
API = 'https://wiki.biligame.com/nrc/api.php'


def resolve(files, urls):
    files = sorted(set(files))
    for start in range(0, len(files), 50):
        batch = files[start:start + 50]
        url = API + '?' + urlencode({'action': 'query', 'titles': '|'.join('File:' + name for name in batch),
                                     'prop': 'imageinfo', 'iiprop': 'url', 'format': 'json', 'formatversion': 2})
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers={'User-Agent': 'RocoData/1.0'}), timeout=20) as response:
                    payload = json.load(response)
                query = payload['query']
                break
            except (OSError, ValueError, KeyError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        normalized = {row['from']: row['to'] for row in query.get('normalized', [])}
        pages = {row['title']: row for row in query['pages']}
        for name in batch:
            title = 'File:' + name
            page = pages.get(normalized.get(title, title), {})
            info = page.get('imageinfo', [])
            if info and info[0]['url'].startswith('https://patchwiki.biligame.com/'):
                urls[name] = info[0]['url']
        print(f'images {min(start + 50, len(files))}/{len(files)}', flush=True)
        time.sleep(.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'converted')
    parser.add_argument('--output', type=Path, default=ROOT / 'image_urls.json')
    args = parser.parse_args()
    images = [(json.loads(path.read_text(encoding='utf-8'))['profile'].get('image') or {})
              for path in (args.data_dir / 'pets').glob('*.json')]
    if not images:
        raise ValueError('精灵资料目录为空')
    primary = {row.get('head') or row.get('illustration') for row in images} - {None}
    urls = {}
    resolve(primary, urls)
    fallback = {row['illustration'] for row in images
                if row.get('head') not in urls and row.get('illustration') not in urls and row.get('illustration')}
    resolve(fallback, urls)
    result = {'source': API, 'updated_at': datetime.now(timezone.utc).isoformat(),
              'urls': dict(sorted(urls.items())), 'missing': sorted((primary | fallback) - urls.keys())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
    temporary.replace(args.output)
    print(f'resolved {len(urls)}, missing {len(result["missing"])}', flush=True)


if __name__ == '__main__':
    main()
