"""直接读取 BWIKI 正式 JSON，提供与 Agent 查询工具一致的接口。"""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import quote

from .database import STATS
from .queries import result, skill_pets_result

DEFAULT_JSON_DIR = Path(__file__).resolve().parents[1] / 'data/bwiki/converted'
GROUPS = ('level', 'machine', 'blood', 'legendary')
STAT_FIELDS = {'hp': 'hp', 'physical_attack': 'atk', 'physical_defense': 'def',
               'magic_attack': 'spa', 'magic_defense': 'spd', 'speed': 'spe'}


class JsonQueries:
    def __init__(self, data_dir=DEFAULT_JSON_DIR):
        self.root = Path(data_dir).resolve()
        self.pets = self._load('pets', 'pet_id')
        self.skills = self._load('skills', 'skill_id')
        self.features = self._load('features', 'skill_id')
        if not self.pets or not self.skills:
            raise ValueError(f'精灵或技能 JSON 目录为空：{self.root}')

    def _load(self, directory, key):
        rows = {}
        for path in sorted((self.root / directory).glob('*.json')):
            record = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(record, dict) or type(record.get(key)) is not int
                    or str(record[key]) != path.stem or record[key] < 1):
                raise ValueError(f'JSON 的 ID 与文件名不匹配：{path}')
            if record[key] in rows:
                raise ValueError(f'重复 ID：{path}')
            rows[record[key]] = record
        return rows

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _resolve(self, rows, identifier, key):
        if isinstance(identifier, str):
            identifier = identifier.strip()
        if type(identifier) is int or isinstance(identifier, str) and identifier.isdecimal():
            if len(str(identifier)) > 19 or not 1 <= int(identifier) <= 9223372036854775807:
                return None, result('invalid_argument', message='ID 须为有效正整数')
            found = [rows[int(identifier)]] if int(identifier) in rows else []
        elif isinstance(identifier, str) and identifier:
            found = [row for row in rows.values() if row.get('title') == identifier]
            found = found or [row for row in rows.values() if row['name'] == identifier]
        else:
            return None, result('invalid_argument', message='请提供准确名称或正整数 ID')
        if not found:
            return None, result('not_found', message='当前 JSON 资料未检索到该名称或 ID')
        if len(found) > 1:
            return None, result('ambiguous', [{key: row[key], 'name': row.get('title', row['name'])}
                                             for row in found], message='请确认具体形态或 ID')
        return found[0], None

    def _sources(self, pet):
        return [{'file': str(self.root / 'pets' / f"{pet['pet_id']}.json"),
                 'source': 'https://wiki.biligame.com/nrc/' + quote(pet['title'])}]

    def _stats(self, pet):
        stats = pet['profile'].get('stats', {})
        values = {key: stats.get(field) for key, field in STAT_FIELDS.items()}
        values['sum'] = sum(values.values()) if all(v is not None for v in values.values()) else None
        return values

    def search_pets(self, query='', type_name=None, limit=20):
        if (not isinstance(query, str) or type(limit) is not int or not 1 <= limit <= 100
                or type_name is not None and not isinstance(type_name, str)):
            return result('invalid_argument', message='query 应为字符串，limit 范围为 1～100')
        rows = [pet for pet in self.pets.values()
                if query.strip().lower() in pet['title'].lower()
                and (type_name is None or type_name.removesuffix('系') in
                     [value.removesuffix('系') for value in pet['profile']['types']])]
        term = query.strip().lower()
        if term:
            rows = ([pet for pet in rows if pet['title'].lower() == term]
                    or [pet for pet in rows if pet['name'].lower() == term] or rows)
        rows.sort(key=lambda pet: pet['pet_id'])
        return result('ok', {'items': [{'pet_id': pet['pet_id'], 'name': pet['title'],
            'handbook_no': pet['profile']['number']} for pet in rows[:limit]],
            'limit': limit, 'has_more': len(rows) > limit})

    def search_skills(self, query='', limit=20):
        if not isinstance(query, str) or type(limit) is not int or not 1 <= limit <= 100:
            return result('invalid_argument', message='query 应为字符串，limit 范围为 1～100')
        rows = sorted((row for row in self.skills.values() if query.strip() in row['name']),
                      key=lambda row: row['skill_id'])
        return result('ok', {'items': [{'skill_id': row['skill_id'], 'name': row['name'],
                                       'has_detail': True} for row in rows[:limit]], 'limit': limit})

    @staticmethod
    def _skill(row):
        return {key: value for key, value in {
            'skill_id': row['skill_id'], 'name': row['name'],
            'element_type': {'name': row['element'].removesuffix('系')},
            'skill_type': {'name': row.get('damage_class') or row['category']},
            'power': row.get('power'), 'cost': row['energy'], 'description': row['desc'],
            'terms': {term['note']: term['desc'] for term in (row.get('terms') or {}).values()} or None,
            'stone_topics': [{'pet': topic['pet_name'], 'topic': topic['topic']}
                             for topic in row.get('stone_topics', [])] or None,
        }.items() if value is not None}

    def get_skill(self, identifier):
        row, error = self._resolve(self.skills, identifier, 'skill_id')
        if error:
            return error
        return result('ok', self._skill(row), [{'file': str(self.root / 'skills' / f"{row['skill_id']}.json")}])

    def _family(self, pet):
        branches = []
        for branch in pet['evolution_branches']:
            edges = []
            for edge in branch['transitions']:
                start, end = self.pets.get(edge['from_pet_id']), self.pets.get(edge['to_pet_id'])
                edges.append({'from': start['title'] if start else edge['from_pet_id'],
                              'to': end['title'] if end else edge['to_pet_id'],
                              'conditions': deepcopy(edge['conditions'])})
            branches.append({'name': branch['name'], 'transitions': edges})
        return {'branches': branches}

    def get_pet(self, identifier, section=None):
        pet, error = self._resolve(self.pets, identifier, 'pet_id')
        if error:
            return error
        if section is not None and not isinstance(section, str):
            return result('invalid_argument', message='section 应为分区名称字符串')
        profile = pet['profile']
        feature = self.features.get(pet['feature_id'])
        features = {'items': [{'name': feature['name'], 'desc': feature['desc']}]} if feature else None
        ecology = profile.get('ecology') or {}
        sections = {
            'base': {'description': profile.get('description'), 'types': profile.get('types')},
            'profile': {'attributes': self._stats(pet), 'height': profile.get('height'),
                        'weight': profile.get('weight'), 'types': profile.get('types'),
                        'egg_groups': profile.get('egg_group'), 'type_effectiveness': pet['type_effectiveness']},
            'features': features, 'family': self._family(pet), 'acquisition': ecology,
            'ecology': ecology, 'egg': {'gender_ratio': profile.get('gender_ratio'),
                                      'egg_size': profile.get('egg_size'), 'eggs': ecology.get('eggs', [])},
            'fruit': ecology.get('fruits'), 'handbook': pet.get('handbook'),
            'ride': {'can_ride': profile.get('can_ride'), 'can_double_ride': profile.get('can_double_ride')},
            'skills': pet['skills'], 'history': pet.get('history'),
            'training_reference': pet.get('training_reference'),
        }
        identity = {'pet_id': pet['pet_id'], 'name': pet['title']}
        if section is None:
            data = dict(identity, handbook_no=profile['number'], types=profile['types'],
                        attributes=self._stats(pet), features=features,
                        available_sections=[key for key, value in sections.items() if value is not None])
        elif section not in sections or sections[section] is None:
            return result('data_missing', identity, self._sources(pet), '当前 JSON 中该资料分区待补齐')
        else:
            data = dict(identity, section=section, value=deepcopy(sections[section]))
        return result('ok', data, self._sources(pet))

    def get_pet_skills(self, identifier, source=None, max_level=None, skill=None):
        if source is not None and source not in GROUPS:
            return result('invalid_argument', message='学习来源应为 level、machine、blood 或 legendary')
        if max_level is not None:
            if type(max_level) is not int or max_level < 1 or source in ('machine', 'legendary'):
                return result('invalid_argument', message='等级筛选适用于升级或血脉技能')
            source = source or 'level'
        pet, error = self._resolve(self.pets, identifier, 'pet_id')
        if error:
            return error
        target = None
        if skill is not None:
            target, error = self._resolve(self.skills, skill, 'skill_id')
            if error:
                return error
        items = []
        for group in ((source,) if source else GROUPS):
            for relation in pet['skills'].get(group, []):
                if target is not None and relation['skill_id'] != target['skill_id']:
                    continue
                level = relation.get('level')
                if max_level is not None and (level is None or level > max_level):
                    continue
                detail = self.skills.get(relation['skill_id'])
                item = {'skill_id': relation['skill_id'], 'source': group, 'level': level,
                        'bloodline_name': relation.get('blood'),
                        'name': detail['name'] if detail else None,
                        'detail': self._skill(detail) if detail else None,
                        'detail_status': 'ok' if detail else 'detail_missing'}
                for key in ('requires', 'stage'):
                    if key in relation:
                        item[key] = relation[key]
                items.append(item)
        data = {'pet_id': pet['pet_id'], 'name': pet['title'], 'items': items, 'count': len(items)}
        if target is not None:
            data['can_learn_in_selected_scope'] = bool(items)
        return result('partial' if any(row['detail_status'] != 'ok' for row in items) else 'ok',
                      data, self._sources(pet))

    def get_skill_pets(self, identifier, source=None, limit=100, offset=0):
        if (source is not None and source not in GROUPS
                or type(limit) is not int or not 1 <= limit <= 100
                or type(offset) is not int or offset < 0):
            return result('invalid_argument', message='请使用有效学习来源、1～100 的 limit 和非负 offset')
        skill, error = self._resolve(self.skills, identifier, 'skill_id')
        if error:
            return error
        pets = []
        for pet in sorted(self.pets.values(), key=lambda row: row['pet_id']):
            learning = []
            for group in ((source,) if source else GROUPS):
                for relation in pet['skills'].get(group, []):
                    if relation['skill_id'] != skill['skill_id']:
                        continue
                    condition = {'source': group}
                    condition.update({key: relation[key] for key in ('level', 'requires', 'stage') if key in relation})
                    if 'blood' in relation:
                        condition['bloodline_name'] = relation['blood']
                    learning.append(condition)
            if learning:
                pets.append({'pet_id': pet['pet_id'], 'name': pet['title'], 'learning': learning})
        return skill_pets_result(skill, pets, limit, offset,
                                 [{'file': str(self.root / 'skills' / f"{skill['skill_id']}.json")}])

    def compare_pets(self, identifiers, stat='speed'):
        if stat not in STATS or not isinstance(identifiers, (tuple, list)) or not 2 <= len(identifiers) <= 10:
            return result('invalid_argument', message='请指定 2～10 只精灵和有效种族值字段')
        rows = []
        for identifier in identifiers:
            pet, error = self._resolve(self.pets, identifier, 'pet_id')
            if error:
                return error
            rows.append({'pet_id': pet['pet_id'], 'name': pet['title'], 'value': self._stats(pet)[stat]})
        if len({row['pet_id'] for row in rows}) != len(rows):
            return result('invalid_argument', message='比较对象应为不同精灵')
        if any(row['value'] is None for row in rows):
            return result('data_missing', {'stat': stat, 'items': rows})
        rows.sort(key=lambda row: (-row['value'], row['pet_id']))
        data = {'stat': stat, 'ranking': rows}
        if len(rows) == 2:
            data['difference'] = rows[0]['value'] - rows[1]['value']
        return result('ok', data)

    def statistics(self):
        return result('ok', {'storage': 'json', 'pets': len(self.pets),
                             'skills_with_details': len(self.skills), 'features': len(self.features)})
