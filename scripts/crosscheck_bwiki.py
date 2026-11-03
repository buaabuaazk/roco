"""只读比较本项目 BWIKI 转换结果与 rocom-data 的已提交快照。"""
import argparse
from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import unicodedata

from collect_bwiki_modules import save

ROOT = Path(__file__).resolve().parents[1]
STAT_KEYS = {'hp': 'hp', 'atk': 'atk', 'sp_atk': 'spa', 'def': 'def',
             'sp_def': 'spd', 'spd': 'spe'}
STAT_LABELS = {'hp': '生命', 'atk': '物攻', 'sp_atk': '魔攻', 'def': '物防',
               'sp_def': '魔防', 'spd': '速度'}


def text(value):
    return re.sub(r'[\s，。,:：;；、]', '', str(value if value is not None else ''))


def identity_text(value):
    return unicodedata.normalize('NFKC', str(value or ''))


def load_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def git_value(reference, *args):
    return subprocess.check_output(['git', '-C', str(reference), *args], text=True).strip()


def history_evidence(pet, group, field, old, new):
    return [event['version'] for event in pet.get('history', [])
            for change in event.get('changes', [])
            if change.get('group') == group and change.get('field') == field
            and text(change.get('before')) == text(old)
            and text(change.get('after')) == text(new)]


def skill_compare(rows, skills):
    index = defaultdict(list)
    for skill in skills:
        index[skill['name']].append(skill)
    matches, missing, ambiguous, differences = 0, [], [], []
    for row in rows:
        name = row['技能名']
        candidates = index[name]
        if not candidates:
            missing.append(name)
            continue
        if len(candidates) != 1:
            ambiguous.append(name)
            continue
        matches += 1
        skill = candidates[0]
        old_type = {'变化': '状态'}.get(row['类型'], row['类型'])
        new_type = skill.get('damage_class') or skill['category']
        old = {'element': row['属性'].removesuffix('系'), 'type': old_type,
               'power': row['威力'], 'energy': row['耗能'], 'desc': row['效果描述']}
        new = {'element': skill['element'].removesuffix('系'), 'type': new_type,
               'power': skill.get('power'), 'energy': skill['energy'], 'desc': skill['desc']}
        diffs = {}
        for key in old:
            left, right = old[key], new[key]
            if key in ('power', 'energy'):
                try:
                    left = float(left) if left not in ('', None, '--') else None
                    right = float(right) if right not in ('', None, '--') else None
                except ValueError:
                    pass
                if key == 'power' and old_type in ('状态', '防御'):
                    left = None if left == 0 else left
                    right = None if right == 0 else right
            else:
                left, right = text(left), text(right)
            if left != right:
                diffs[key] = {'reference': old[key], 'ours': new[key]}
        if diffs:
            differences.append({'name': name, 'skill_id': skill['skill_id'], 'fields': diffs})
    return {'rows': len(rows), 'matched': matches, 'equal': matches - len(differences),
            'different': len(differences), 'missing_names': missing, 'ambiguous_names': ambiguous,
            'differences': differences}


def compare(reference, converted):
    ours = [json.loads(path.read_text()) for path in sorted((converted / 'pets').glob('*.json'))]
    skills = [json.loads(path.read_text()) for path in sorted((converted / 'skills').glob('*.json'))]
    skill_by_id = {skill['skill_id']: skill for skill in skills}
    features = {int(path.stem): json.loads(path.read_text())
                for path in (converted / 'features').glob('*.json')}
    other = json.loads((reference / 'data' / 'sprites.json').read_text())
    index = defaultdict(list)
    for pet in ours:
        index[(int(pet['profile']['number']), identity_text(pet['name']))].append(pet)
    stats, abilities, types, learnsets, evolutions, unmatched, ambiguous = [], [], [], [], [], [], []
    defense_matchups, learning_levels = [], []
    matched = 0
    for old in other:
        candidates = index[(old['no'], identity_text(old['name']))]
        if len(candidates) > 1:
            title = old['name'] + (f"（{old['form']}）" if old.get('form') else '')
            exact = [pet for pet in candidates if identity_text(pet['title']) == identity_text(title)]
            candidates = exact or [pet for pet in candidates if
                          identity_text(pet['profile'].get('form')) == identity_text(old.get('form'))]
        identity = {key: old.get(key) for key in ('no', 'name', 'form')}
        if len(candidates) != 1:
            (ambiguous if candidates else unmatched).append(identity)
            continue
        matched += 1
        pet = candidates[0]
        identity['pet_id'] = pet['pet_id']
        fields = {}
        for key, current_key in STAT_KEYS.items():
            left, right = (old.get('stats') or {}).get(key), pet['profile']['stats'].get(current_key)
            if left != right:
                fields[key] = {'reference': left, 'ours': right,
                    'history_versions': history_evidence(pet, 'stats', STAT_LABELS[key], left, right)}
        if fields:
            stats.append(dict(identity, fields=fields))
        ability = old.get('ability') or {}
        feature = features[pet['feature_id']]
        if text(ability.get('name')) != text(feature['name']) or text(ability.get('description')) != text(feature['desc']):
            abilities.append(dict(identity, reference=ability,
                                  ours={'name': feature['name'], 'description': feature['desc']}))
        old_types = sorted(old.get('attributes') or [])
        new_types = sorted(value.removesuffix('系') for value in pet['profile']['types'])
        if old_types != new_types:
            types.append(dict(identity, reference=old_types, ours=new_types))
        for old_key, new_key in (('weak_to', 'weak'), ('resists', 'resist')):
            left = sorted((old.get('type_matchup') or {}).get(old_key, []))
            right = sorted(row['type'].removesuffix('系')
                           for row in pet['type_effectiveness'].get(new_key, []))
            if left != right:
                defense_matchups.append(dict(identity, field=old_key, reference=left, ours=right))
        old_names = {row['name'] for row in old.get('skills', [])}
        new_names = {skill_by_id[row['skill_id']]['name']
                     for rows in pet['skills'].values() for row in rows}
        if old_names != new_names:
            learnsets.append(dict(identity, reference_only=sorted(old_names - new_names),
                                  ours_only=sorted(new_names - old_names)))
        levels = defaultdict(list)
        for relation in pet['skills']['level']:
            levels[skill_by_id[relation['skill_id']]['name']].append(relation.get('level'))
        for row in old.get('skills', []):
            if row.get('level', 0) > 0 and row['name'] in levels and row['level'] not in levels[row['name']]:
                learning_levels.append(dict(identity, skill=row['name'], reference=row['level'],
                                            ours=levels[row['name']]))
        # 对方未保留技能来源，level=0 不推断为某种学习方式。
        for stage in old.get('evolution_chain') or []:
            if not stage.get('evolves_from'):
                continue
            pairs = {(member['name'], member['id']) for branch in pet['evolution_branches']
                     for member in branch['chain'] + branch.get('lord_branches', [])}
            starts = {wiki_id for name, wiki_id in pairs if name == stage['evolves_from']}
            ends = {wiki_id for name, wiki_id in pairs if name == stage['name']}
            edges = [edge for branch in pet['evolution_branches'] for edge in branch['transitions']
                     if edge['from_wiki_id'] in starts and edge['to_wiki_id'] in ends]
            conditions = {json.dumps(edge['conditions'], ensure_ascii=False, sort_keys=True)
                          for edge in edges}
            if len(conditions) != 1:
                continue
            condition = json.loads(conditions.pop())
            reasons = []
            if str(stage.get('level') or '') != str(condition.get('level') or ''):
                reasons.append('level')
            if text(stage.get('condition')) != text(condition.get('special')):
                reasons.append('special')
            if reasons:
                evolutions.append(dict(identity, from_name=stage['evolves_from'], to_name=stage['name'],
                    reference={'level': stage.get('level'), 'special': stage.get('condition')},
                    ours=condition, differing_fields=reasons))
    result = {
        'compared_at': datetime.now().astimezone().isoformat(),
        'reference_commit': git_value(reference, 'rev-parse', 'HEAD'),
        'reference_data_last_commit': git_value(reference, 'log', '-1', '--format=%H %cI', '--',
                                               'data/sprites.json', 'data/skills.csv'),
        'scope': '对本地两份快照做只读比较；未重新运行对方爬虫，差异不自动判定正确性',
        'matching': '图鉴编号+名称（Unicode NFKC 规范化）；多候选优先完整页面标题，再比较形态。未匹配和歧义分别报告。',
        'normalization': '描述忽略空白及常见标点；状态/防御的零威力与缺省等价；速度与魔防字段显式映射。',
        'ours_source_snapshot': json.loads((converted.parent / 'modules' / 'fetch.json').read_text())
            if (converted.parent / 'modules' / 'fetch.json').exists() else None,
        'pets': {'reference': len(other), 'ours': len(ours), 'matched': matched,
            'unmatched': unmatched, 'ambiguous': ambiguous, 'stat_differences': stats,
            'ability_differences': abilities, 'type_differences': types,
            'defense_matchup_differences': defense_matchups, 'learning_level_differences': learning_levels,
            'skill_name_set_differences': learnsets, 'evolution_differences': evolutions},
        'scraped_skills': skill_compare(load_csv(reference / 'data' / 'skills.csv'), skills),
        'supplemental_skills': skill_compare(load_csv(reference / 'data' / 'skills_all.csv'), skills),
    }
    summary = {'matched_pets': matched, 'unmatched_pets': len(unmatched),
        'stats_equal': matched - len(stats), 'stats_different': len(stats),
        'stat_differences_fully_explained_by_history': sum(
            all(field['history_versions'] for field in row['fields'].values()) for row in stats),
        'ability_different': len(abilities), 'types_different': len(types),
        'defense_matchup_field_differences': len(defense_matchups),
        'learning_level_differences': len(learning_levels),
        'skill_name_sets_different': len(learnsets), 'evolution_edges_different': len(evolutions)}
    for key in ('scraped_skills', 'supplemental_skills'):
        summary[key] = {field: result[key][field] for field in ('rows', 'matched', 'equal', 'different')}
    result['summary'] = summary
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=ROOT.parent / 'rocom-data')
    parser.add_argument('--converted', type=Path, default=ROOT / 'data/bwiki/converted')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/bwiki_crosscheck.json')
    args = parser.parse_args()
    report = compare(args.reference, args.converted)
    save(args.output, report)
    print(json.dumps(report['summary'], ensure_ascii=False, indent=4))


if __name__ == '__main__':
    main()
