"""BWIKI Lua 基础表试采：只解析数据字面量，按精灵名称关联为 JSON。"""
import argparse
from copy import deepcopy
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from collect_bwiki import ROOT, API, save

TABLES = ('Catalog', 'Skills', 'Learnsets', 'Evolutions', 'Handbooks')
TITLES = ['Module:Pets/data/' + name for name in TABLES] + [
    'Module:Pets/EvolutionConditions', 'Module:Pets/SeasonData',
    'Module:ContentVisibility/Config'] + [
    'Module:ContentVisibility/S5Legacy/' + name for name in ('Catalog', 'Skills', 'Learnsets')]
TOKEN = re.compile(r'\s+|--[^\n]*|"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z_0-9]*|'
                   r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[{}\[\]=,;]')


def parse_lua(source):
    """接受 return + Lua 数据表子集；遇到函数、表达式或未知语法即失败。"""
    tokens = []
    pos = 0
    while pos < len(source):
        match = TOKEN.match(source, pos)
        if not match:
            raise ValueError(f'不支持的 Lua 数据语法，位置 {pos}')
        token = match.group()
        pos = match.end()
        if not token.isspace() and not token.startswith('--'):
            tokens.append(token)
    pos = 0

    def take(expected=None):
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError('Lua 数据提前结束')
        token = tokens[pos]
        if expected is not None and token != expected:
            raise ValueError(f'期待 {expected}，得到 {token}')
        pos += 1
        return token

    def value():
        token = take()
        if token == '{':
            fields, sequence = {}, []
            while pos < len(tokens) and tokens[pos] != '}':
                if tokens[pos] == '[':
                    take('[')
                    key = value()
                    if not isinstance(key, (str, int)) or isinstance(key, bool):
                        raise ValueError('不支持的 Lua 表键')
                    take(']'); take('=')
                    fields[str(key)] = value()
                elif pos + 1 < len(tokens) and tokens[pos + 1] == '=':
                    key = take(); take('=')
                    fields[key] = value()
                else:
                    sequence.append(value())
                if pos < len(tokens) and tokens[pos] in (',', ';'):
                    take()
                elif pos < len(tokens) and tokens[pos] != '}':
                    raise ValueError('Lua 表字段缺少分隔符')
            take('}')
            if fields and sequence:
                raise ValueError('试采暂不支持混合键值与数组的 Lua 表')
            return fields if fields else sequence
        if token.startswith('"'):
            return json.loads(token)
        if token in ('true', 'false', 'nil'):
            return {'true': True, 'false': False, 'nil': None}[token]
        if re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', token):
            return json.loads(token)
        raise ValueError('不支持的 Lua 数据值：' + token)

    take('return')
    result = value()
    if pos != len(tokens):
        raise ValueError('Lua 表后存在额外代码')
    return result


def unpack(response):
    if 'error' in response:
        raise ValueError(str(response['error']))
    tables, provenance = {}, []
    for page in response['query']['pages']:
        if page.get('missing') or not page.get('revisions'):
            raise ValueError('模块不存在：' + page['title'])
        revision = page['revisions'][0]
        name = page['title'].split('/')[-1]
        if '/S5Legacy/' in page['title']:
            name += 'Patch'
        elif page['title'] == '模块:ContentVisibility/Config':
            name = 'VisibilityConfig'
        provenance.append({'title': page['title'], 'revision_id': revision['revid'],
                           'revision_timestamp': revision['timestamp']})
        if name != 'SeasonData':
            tables[name] = parse_lua(revision['slots']['main']['content'])
    return tables, provenance


def visible_tables(tables):
    """复现已核对的当前展示投影；规则切换时显式停止并重新核验。"""
    config = tables['VisibilityConfig']
    if not config.get('hidden_seasons', {}).get('S5'):
        raise ValueError('BWIKI 已切换赛季展示规则，须重新核验 SeasonData 适配器')
    result = deepcopy(tables)
    for name in ('Catalog', 'Skills', 'Learnsets'):
        for key, fields in tables[name + 'Patch'].items():
            if key in result[name]:
                result[name][key].update(fields)
    for key in config.get('s5_shiny_pets', {}):
        if key in result['Catalog']:
            row = result['Catalog'][key]
            row['has_shiny'] = False
            for field in ('shiny', 'shiny_head'):
                row.get('image', {}).pop(field, None)
            ecology = row.get('ecology', {})
            if ecology:
                ecology['eggs'] = [egg for egg in ecology.get('eggs', []) if not egg.get('is_shiny')]
    for row in result['Catalog'].values():
        row['siblings'] = [key for key in row.get('siblings', []) if key in result['Catalog']]
    for row in result['Handbooks'].values():
        row['topics'] = [topic for topic in row.get('topics', [])
                         if topic.get('progress_id') not in config.get('s5_topic_ids', {})]
    return result


def pet_view(tables, name):
    matches = [p for p in tables['Catalog'].values() if p.get('title') == name]
    if len(matches) != 1:
        raise ValueError(f'{name} 在基础表中匹配到 {len(matches)} 条，须使用完整页面标题')
    pet = matches[0]
    skills = tables['Skills']
    learnset = tables['Learnsets'][pet['learnset_id']]
    # 保留来源中的关联键和条件，不把配置字段推断为要求。
    learned = {}
    for group, rows in learnset.items():
        if not isinstance(rows, list):
            learned[group] = rows
            continue
        learned[group] = []
        for row in rows:
            reference = {'skill': row} if isinstance(row, str) else row
            detail = skills.get(reference['skill'])
            linked = dict(reference, skill_detail=detail)
            if detail is None:
                linked['status'] = 'detail_missing'
            learned[group].append(linked)
    evolutions = tables['Evolutions'][pet['evolution_id']]
    member_keys = set()
    for branch in evolutions:
        for member in branch.get('chain', []) + branch.get('lord_branches', []):
            member_keys.update(str(member[k]) for k in ('id', 'title') if k in member)
            entry = tables['Catalog'].get(member['id'], {})
            if 'game_id' in entry:
                member_keys.add(str(entry['game_id']))
    conditions = tables['EvolutionConditions']
    manual = {key: {target: condition for target, condition in targets.items()
                    if target in member_keys}
              for key, targets in conditions.items() if key in member_keys}
    return {'pet': pet, 'feature': skills[pet['feature_skill_id']],
            'learnset': learned, 'evolutions': evolutions,
            'manual_evolution_conditions': manual,
            'handbook': tables['Handbooks'][pet['handbook_id']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('titles', nargs='+')
    parser.add_argument('--from-response', type=Path, help='复用已保存的模块响应，离线转换')
    args = parser.parse_args()
    for title in args.titles:
        if title in ('.', '..') or '/' in title or '\\' in title:
            parser.error('标题须为精灵名称')
    if args.from_response:
        raw = json.loads(args.from_response.read_text(encoding='utf-8'))
    else:
        url = API + '?' + urlencode(dict(action='query', titles='|'.join(TITLES),
            prop='revisions', rvprop='ids|timestamp|content', rvslots='main',
            format='json', formatversion=2))
        time.sleep(1)
        result = subprocess.run(['curl', '-fsSL', '--max-time', '60', url],
                                capture_output=True, check=True)
        raw = json.loads(result.stdout)
    tables, provenance = unpack(raw)
    tables = visible_tables(tables)
    collected = datetime.now().astimezone().isoformat()
    outputs = [(title, pet_view(tables, title)) for title in args.titles]
    save(ROOT / 'modules' / 'response.json', raw)
    for title, data in outputs:
        data.update(source='BWIKI nrc Lua modules', fetched_or_converted_at=collected,
                    scope='当前 S5 隐藏展示规则下的数据投影试采；保留条件原始字段，尚未接入 Agent',
                    modules=provenance)
        save(ROOT / title / 'structured.json', data)
        print(title, data['pet']['game_id'], 'ok',
              {key: len(rows) for key, rows in data['learnset'].items()
               if isinstance(rows, list)}, flush=True)


if __name__ == '__main__':
    main()
