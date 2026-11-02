"""BWIKI 试采：保留原始页面响应，提取正文分区与进化条件原文。"""
import argparse
import json
import subprocess
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, quote

API = 'https://wiki.biligame.com/nrc/api.php'
ROOT = Path(__file__).resolve().parents[1] / 'data' / 'bwiki'


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.divs = []
        self.hidden = 0
        self.text = []
        self.sections = {}
        self.branches = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'div':
            attrs = dict(attrs)
            classes = attrs.get('class', '').split()
            frame = {'attrs': attrs, 'classes': classes, 'text': []}
            if 'roco-evo-timeline' in classes:
                branch = {'branch': attrs.get('data-branch'), 'steps': []}
                self.branches.append(branch)
                frame['branch'] = branch
            self.divs.append(frame)

    def handle_data(self, data):
        if self.hidden or not data.strip():
            return
        value = ' '.join(data.split())
        self.text.append(value)
        for frame in self.divs:
            frame['text'].append(value)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if tag != 'div' or not self.divs:
            return
        frame = self.divs.pop()
        classes = frame['classes']
        text = ' '.join(frame['text'])
        if 'roco-panel' in classes and frame['attrs'].get('data-panel'):
            self.sections[frame['attrs']['data-panel']] = text
        kind = ('pet' if 'roco-evo-name-main' in classes else
                'condition' if 'roco-evo-conn-pill' in classes else None)
        if kind:
            for parent in reversed(self.divs):
                if 'branch' in parent:
                    parent['branch']['steps'].append({'kind': kind, 'text': text})
                    break


def extract(response):
    if 'error' in response:
        raise ValueError(str(response['error']))
    page = response['parse']
    parser = PageText()
    parser.feed(page['text'])
    if not parser.branches or not any(
            step['kind'] == 'pet' for b in parser.branches for step in b['steps']):
        raise ValueError('页面未提取到进化链，请检查标题或页面结构')
    return {
        'title': page['title'], 'page_id': page['pageid'], 'revision_id': page['revid'],
        'page_url': 'https://wiki.biligame.com/nrc/' + quote(page['title']),
        'evolution_branches': parser.branches,
        'sections_text': parser.sections, 'page_text': '\n'.join(parser.text),
    }


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('titles', nargs='+', help='精灵名称，例如 喵喵 机械方方')
    args = parser.parse_args()
    for title in args.titles:
        if title in ('.', '..') or '/' in title or '\\' in title:
            parser.error('标题须为精灵名称')
    for title in args.titles:
        url = API + '?' + urlencode(dict(action='parse', page=title, prop='wikitext|text|revid',
                                         format='json', formatversion=2, redirects=1))
        time.sleep(1)
        result = subprocess.run(['curl', '-fsSL', '--max-time', '45', url],
                                capture_output=True, check=True)
        raw = json.loads(result.stdout)
        extracted = extract(raw)
        extracted.update(request_url=url, fetched_at=datetime.now().astimezone().isoformat())
        save(ROOT / title / 'page.json', raw)
        save(ROOT / title / 'extracted.json', extracted)
        print(title, 'ok', json.dumps(extracted['evolution_branches'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
