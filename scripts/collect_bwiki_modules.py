"""批量采集 BWIKI 数据模块，独立导出精灵、技能和特性 JSON。"""
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

TABLES = ('Catalog', 'Skills', 'Learnsets', 'Evolutions', 'Handbooks',
          'Types', 'Terms', 'History', 'TrainingReference', 'SkillStoneTopics')
TITLES = ['Module:Pets/data/' + name for name in TABLES] + [
    'Module:Pets/EvolutionConditions', 'Module:Pets/SeasonData', 'Module:ContentVisibility',
    'Module:ContentVisibility/Config'] + [
    'Module:ContentVisibility/S5Legacy/' + name for name in ('Catalog', 'Skills', 'Learnsets')]
RULE_REVISIONS = {'模块:Pets/SeasonData': 20687, '模块:ContentVisibility': 20611}
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
        if name != 'SeasonData' and not page['title'].endswith(':ContentVisibility'):
            try:
                tables[name] = parse_lua(revision['slots']['main']['content'])
            except ValueError as exc:
                raise ValueError(f"{page['title']}: {exc}") from exc
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
    if 'History' in result:
        history = result['History']
        history['versions'] = {key: row for key, row in history['versions'].items()
                               if not key.startswith('s5-')}
        history['pets'] = {key: [event for event in events
                                if not event['version'].startswith('s5-')]
                           for key, events in history['pets'].items()}
    return result


def validate_rules(provenance):
    revisions = {row['title']: row['revision_id'] for row in provenance}
    for title, expected in RULE_REVISIONS.items():
        if revisions.get(title) != expected:
            raise ValueError(f'{title} 展示规则修订已变化或缺失，须重新核验转换逻辑')


def skill_record(tables, wiki_id):
    row = tables['Skills'][wiki_id]
    return dict(row, skill_id=row['game_id'], wiki_id=wiki_id,
                terms={str(key): tables['Terms'][str(key)]
                       for key in row.get('desc_notes', []) if str(key) in tables['Terms']},
                stone_topics=tables['SkillStoneTopics'].get(wiki_id, []))


def evolution_edges(tables, branches):
    """按页面规则合并等级、特殊条件和首领信物，保留分支与原始成员字段。"""
    catalog = tables['Catalog']
    overrides = tables['EvolutionConditions']

    def keys(member):
        entry = catalog.get(member['id'], {})
        return [str(key) for key in (entry.get('game_id'), member['id'], member.get('title'))
                if key is not None]

    def edge(source, target, lord=False):
        special, origin = target.get('cond'), 'member'
        for start in keys(source):
            destinations = overrides.get(start, {})
            found = next((key for key in keys(target) if key in destinations), None)
            if found is not None:
                special, origin = destinations[found], 'manual'
                break
        conditions = {}
        if 'level' in target and not lord:
            conditions['level'] = target['level']
        if special is not None:
            conditions['special'] = special
        if lord:
            conditions['method'] = '首领化'
            if target.get('item'):
                conditions['item'] = target['item']
        return {'from_wiki_id': source['id'], 'to_wiki_id': target['id'],
                'from_pet_id': catalog.get(source['id'], {}).get('game_id'),
                'to_pet_id': catalog.get(target['id'], {}).get('game_id'),
                'conditions': conditions, 'special_condition_source': origin}

    results = []
    for branch in branches:
        chain = branch['chain']
        edges = [edge(source, target) for source, target in zip(chain, chain[1:])]
        if chain:
            edges.extend(edge(chain[-1], target, True) for target in branch.get('lord_branches', []))
        results.append(dict(branch, transitions=edges))
    return results


def convert_pet(tables, pet):
    groups = {'native_skills': 'level', 'skill_stones': 'machine',
              'blood_skills': 'blood', 'legendary': 'legendary'}
    learned = {key: [] for key in groups.values()}
    missing = []
    learnset = tables['Learnsets'][pet['learnset_id']]
    for group, rows in learnset.items():
        if group == 'feature_skill':
            continue
        if group not in groups:
            raise ValueError('未知技能来源：' + group)
        rows = [rows] if isinstance(rows, dict) else rows
        for row in rows:
            reference = dict(skill=row) if isinstance(row, str) else dict(row)
            wiki_id = reference.pop('skill')
            detail = tables['Skills'].get(wiki_id)
            reference.update(wiki_skill_id=wiki_id, skill_id=detail['game_id'] if detail else None)
            if detail is None:
                missing.append(wiki_id)
                reference['status'] = 'detail_missing'
            learned[groups[group]].append(reference)
    feature = tables['Skills'][pet['feature_skill_id']]
    return {
        'pet_id': pet['game_id'], 'wiki_id': pet['id'], 'name': pet['name'], 'title': pet['title'],
        'profile': pet, 'feature_id': feature['game_id'], 'skills': learned,
        'evolution_branches': evolution_edges(tables, tables['Evolutions'][pet['evolution_id']]),
        'handbook': tables['Handbooks'][pet['handbook_id']],
        'type_effectiveness': tables['Types'].get(pet.get('relation_key'), {}),
        'training_reference': tables['TrainingReference']['pets'].get(str(pet['game_id']), {}),
        'history': tables['History']['pets'].get(pet['id'], []),
        'status': 'partial' if missing else 'ok', 'missing_skill_references': missing,
    }


def select_pets(catalog, titles, ids, all_pets=False, limit=None):
    selected = {}
    for title in titles:
        matches = [pet for pet in catalog.values() if pet['title'] == title]
        if len(matches) != 1:
            raise ValueError(f'{title} 匹配到 {len(matches)} 条，请使用完整页面标题')
        selected[matches[0]['game_id']] = matches[0]
    for game_id in ids:
        matches = [pet for pet in catalog.values() if pet['game_id'] == game_id]
        if len(matches) != 1:
            raise ValueError(f'精灵游戏 ID {game_id} 匹配到 {len(matches)} 条')
        selected[game_id] = matches[0]
    if all_pets:
        for pet in catalog.values():
            selected[pet['game_id']] = pet
    return sorted(selected.values(), key=lambda pet: pet['game_id'])[:limit]


def fetch_modules():
    url = API + '?' + urlencode(dict(action='query', titles='|'.join(TITLES),
        prop='revisions', rvprop='ids|timestamp|content', rvslots='main',
        format='json', formatversion=2, maxlag=5))
    for attempt in range(3):
        time.sleep(attempt + 1)
        try:
            result = subprocess.run(['curl', '-fsSL', '--max-time', '45', url],
                                    capture_output=True, check=True)
            raw = json.loads(result.stdout)
            if raw.get('error', {}).get('code') in ('maxlag', 'ratelimited', 'readonly'):
                raise ValueError(str(raw['error']))
            return raw, {'request_url': url, 'fetched_at': datetime.now().astimezone().isoformat()}
        except (subprocess.SubprocessError, ValueError):
            if attempt == 2:
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('titles', nargs='*', help='完整精灵页面标题')
    parser.add_argument('--ids', nargs='+', type=int, default=[], help='游戏精灵 ID')
    parser.add_argument('--all', action='store_true', help='转换全部精灵及技能目录')
    parser.add_argument('--limit', type=int, help='限制精灵数量')
    parser.add_argument('--refresh', action='store_true', help='重新请求模块，否则复用缓存')
    parser.add_argument('--output', type=Path, default=ROOT / 'converted')
    parser.add_argument('--from-response', type=Path, help='复用已保存的模块响应，离线转换')
    args = parser.parse_args()
    if not (args.titles or args.ids or args.all):
        parser.error('请指定名称、--ids 或 --all')
    if args.limit is not None and args.limit < 1 or any(key < 1 for key in args.ids):
        parser.error('ID 和数量须为正数')
    if args.from_response and args.refresh:
        parser.error('--from-response 与 --refresh 不能同时使用')
    try:
        cache = ROOT / 'modules' / 'response.json'
        metadata = ROOT / 'modules' / 'fetch.json'
        network = not args.from_response and (args.refresh or not cache.exists())
        if network:
            raw, source = fetch_modules()
        else:
            raw = json.loads((args.from_response or cache).read_text(encoding='utf-8'))
            source = (json.loads(metadata.read_text(encoding='utf-8'))
                      if not args.from_response and metadata.exists() else {})
        tables, provenance = unpack(raw)
        validate_rules(provenance)
        required = set(TABLES) | {'VisibilityConfig', 'EvolutionConditions',
                                 'CatalogPatch', 'SkillsPatch', 'LearnsetsPatch'}
        if required - tables.keys():
            raise ValueError('模块缓存缺少 ' + ', '.join(sorted(required - tables.keys())) + '；请使用 --refresh')
        tables = visible_tables(tables)
        selected = select_pets(tables['Catalog'], args.titles, args.ids, args.all, args.limit)
        pets = [convert_pet(tables, pet) for pet in selected]
        skill_keys = set(tables['Skills']) if args.all and not args.limit else {
            row['wiki_skill_id'] for pet in pets for rows in pet['skills'].values() for row in rows}
        skill_keys.update(pet['feature_skill_id'] for pet in selected)
        skills = [skill_record(tables, key) for key in sorted(skill_keys) if key in tables['Skills']]
        if network:
            save(cache, raw)
            save(metadata, source)
        # 完成所有转换后再写出，manifest 最后写入，列明本批次有效文件。
        files = []
        for pet in pets:
            file = f"pets/{pet['pet_id']}.json"
            save(args.output / file, pet)
            files.append(file)
        for skill in skills:
            directory = 'features' if skill['category'] == '特性' else 'skills'
            file = f"{directory}/{skill['skill_id']}.json"
            save(args.output / file, skill)
            files.append(file)
        save(args.output / 'reference.json', {
            'terms': tables['Terms'], 'history_versions': tables['History']['versions'],
            'training_labels': tables['TrainingReference']['labels'],
            'training_season': tables['TrainingReference']['season'],
        })
        missing = sorted({key for pet in pets for key in pet['missing_skill_references']})
        manifest = dict(schema_version=1, converted_at=datetime.now().astimezone().isoformat(),
            source=source, reused_local=not network, modules=provenance,
            visibility_policy='S5 hidden: legacy patches applied',
            pets=len(pets), skills=sum(s['category'] != '特性' for s in skills),
            features=sum(s['category'] == '特性' for s in skills),
            learning_relations=sum(len(rows) for pet in pets for rows in pet['skills'].values()),
            status='partial' if missing else 'complete', missing_skill_references=missing,
            files=files + ['reference.json'])
        save(args.output / 'manifest.json', manifest)
        print(json.dumps({key: manifest[key] for key in (
            'pets', 'skills', 'features', 'learning_relations', 'status', 'missing_skill_references')},
            ensure_ascii=False, indent=4))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'采集或转换失败：{exc}\n')


if __name__ == '__main__':
    main()
