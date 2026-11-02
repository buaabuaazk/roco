"""供命令行、网页后端及 Agent 工具复用的只读查询。"""
import json
import sqlite3
from pathlib import Path

from .database import DEFAULT_DB, STATS

GROUPS = ('level', 'machine', 'blood')


def result(status, data=None, sources=None, message=None):
    answer = {'status': status, 'data': data, 'sources': sources or []}
    if message:
        answer['message'] = message
    return answer


class RocoQueries:
    def __init__(self, db_path=DEFAULT_DB):
        path = Path(db_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f'查询库不存在：{path}；请先运行 python -m roco_data import')
        self.conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=30)
        self.conn.row_factory = sqlite3.Row
        if self.conn.execute('PRAGMA user_version').fetchone()[0] != 1:
            self.conn.close()
            raise ValueError('数据库版本不匹配，请使用当前程序重新导入 JSON')

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _resolve(self, table, identifier):
        key = 'pet_id' if table == 'pets' else 'skill_id'
        if type(identifier) is int and 1 <= identifier <= 9223372036854775807:
            rows = self.conn.execute(f'SELECT * FROM {table} WHERE {key}=?', (identifier,)).fetchall()
        elif isinstance(identifier, str) and identifier.strip():
            text = identifier.strip()
            if text.isdecimal():
                # 避免过长 ID 超出 SQLite 整数范围。
                if len(text) > 19 or int(text) > 9223372036854775807:
                    return None, result('invalid_argument', message='ID 过长')
                rows = self.conn.execute(f'SELECT * FROM {table} WHERE {key}=?', (int(text),)).fetchall()
            else:
                rows = self.conn.execute(f'SELECT * FROM {table} WHERE name=? ORDER BY {key}', (text,)).fetchall()
        else:
            return None, result('invalid_argument', message='请提供精灵或技能的名称、正整数 ID')
        if not rows:
            return None, result('not_found', message='当前查询库未检索到该名称或 ID')
        if len(rows) > 1:
            return None, result('ambiguous', [{key: r[key], 'name': r['name']} for r in rows],
                                message='名称对应多条记录，请用 ID 确定对象')
        return rows[0], None

    def search_pets(self, query='', type_name=None, limit=20):
        if (not isinstance(query, str) or type(limit) is not int or not 1 <= limit <= 100
                or (type_name is not None and not isinstance(type_name, str))):
            return result('invalid_argument', message='query 应为字符串，limit 范围为 1～100')
        sql = '''SELECT p.pet_id, p.name, p.handbook_no FROM pets p
                 WHERE instr(lower(p.name), lower(?)) > 0'''
        params = [query.strip()]
        if type_name is not None:
            sql += ' AND EXISTS (SELECT 1 FROM pet_types t WHERE t.pet_id=p.pet_id AND t.name=?)'
            params.append(type_name)
        rows = self.conn.execute(sql + ' ORDER BY p.pet_id LIMIT ?', (*params, limit)).fetchall()
        return result('ok', {'items': [dict(r) for r in rows], 'limit': limit})

    def search_skills(self, query='', limit=20):
        if not isinstance(query, str) or type(limit) is not int or not 1 <= limit <= 100:
            return result('invalid_argument', message='query 应为字符串，limit 范围为 1～100')
        rows = self.conn.execute('''SELECT skill_id, name, detail_json IS NOT NULL AS has_detail
            FROM skills WHERE instr(lower(name), lower(?)) > 0 ORDER BY skill_id LIMIT ?''',
                                 (query.strip(), limit)).fetchall()
        return result('ok', {'items': [{**dict(r), 'has_detail': bool(r['has_detail'])} for r in rows], 'limit': limit})

    def get_pet(self, identifier, section=None):
        if section is not None and not isinstance(section, str):
            return result('invalid_argument', message='section 应为分区名称字符串')
        row, error = self._resolve('pets', identifier)
        if error:
            return error
        sections, sources = json.loads(row['sections_json']), json.loads(row['sources_json'])
        identity = {'pet_id': row['pet_id'], 'name': row['name']}
        if section is not None:
            if section not in sections or sections[section] is None:
                return result('data_missing', identity, sources, '该精灵的指定资料分区待补齐')
            return result('ok', {**identity, 'section': section, 'value': sections[section]}, sources)
        types = self.conn.execute('SELECT type_id, name FROM pet_types WHERE pet_id=? ORDER BY type_id',
                                  (row['pet_id'],)).fetchall()
        data = {**identity, 'handbook_no': row['handbook_no'], 'types': [dict(t) for t in types],
                'attributes': sections.get('profile', {}).get('attributes'),
                'features': sections.get('features'), 'available_sections': sorted(sections)}
        return result('ok', data, sources)

    def get_skill(self, identifier):
        row, error = self._resolve('skills', identifier)
        if error:
            return error
        sources = json.loads(row['sources_json'])
        if row['detail_json'] is None:
            return result('detail_missing', {'skill_id': row['skill_id'], 'name': row['name']},
                          sources, '已知技能 ID，详细效果待独立技能采集补齐')
        return result('ok', json.loads(row['detail_json']), sources)

    def get_pet_skills(self, identifier, source=None, max_level=None, skill=None):
        """按学习来源与等级过滤；skill 可指定技能名称或 ID，核对学习资格。"""
        if source is not None and source not in GROUPS:
            return result('invalid_argument', message='source 应为 level、machine 或 blood')
        if max_level is not None:
            if type(max_level) is not int or max_level < 1 or source == 'machine':
                return result('invalid_argument', message='等级须为正整数，等级筛选适用于升级或血脉技能')
            source = source or 'level'
        pet, error = self._resolve('pets', identifier)
        if error:
            return error
        sections, sources = json.loads(pet['sections_json']), json.loads(pet['sources_json'])
        groups = sections.get('skills', {})
        selected = (source,) if source else GROUPS
        if any(g not in groups for g in selected):
            return result('data_missing', {'pet_id': pet['pet_id'], 'name': pet['name']},
                          sources, '所选技能学习关系待采集补齐')
        sql = '''SELECT p.*, s.name, s.detail_json, s.sources_json AS skill_sources
                 FROM pet_skills p JOIN skills s ON s.skill_id=p.skill_id WHERE p.pet_id=?'''
        params = [pet['pet_id']]
        if source:
            sql += ' AND p.source=?'
            params.append(source)
        if max_level is not None:
            sql += ' AND p.level <= ?'
            params.append(max_level)
        if skill is not None:
            skill_row, error = self._resolve('skills', skill)
            if error:
                return error
            sql += ' AND p.skill_id=?'
            params.append(skill_row['skill_id'])
        rows = self.conn.execute(sql + ' ORDER BY p.source, p.level, p.position', params).fetchall()
        items = []
        for row in rows:
            items.append({'skill_id': row['skill_id'], 'name': row['name'],
                          'source': row['source'], 'level': row['level'],
                          'bloodline_id': row['bloodline_id'], 'bloodline_name': row['bloodline_name'],
                          'detail_status': 'ok' if row['detail_json'] else 'detail_missing',
                          'detail': json.loads(row['detail_json']) if row['detail_json'] else None,
                          'sources': json.loads(row['skill_sources'])})
        data = {'pet_id': pet['pet_id'], 'name': pet['name'], 'items': items, 'count': len(items)}
        if skill is not None:
            data['can_learn_in_selected_scope'] = bool(items)
        missing = any(item['detail_status'] == 'detail_missing' for item in items)
        return result('partial' if missing else 'ok', data, sources,
                      '学习关系已获取，部分技能详情待补齐' if missing else None)

    def compare_pets(self, identifiers, stat='speed'):
        if stat not in STATS or not isinstance(identifiers, (list, tuple)) or not 2 <= len(identifiers) <= 10:
            return result('invalid_argument', message='请提供 2～10 只精灵，stat 使用种族值字段名')
        column = 'stat_total' if stat == 'sum' else stat
        rows, sources = [], []
        for identifier in identifiers:
            row, error = self._resolve('pets', identifier)
            if error:
                return error
            rows.append({'pet_id': row['pet_id'], 'name': row['name'], 'value': row[column]})
            sources.extend(json.loads(row['sources_json']))
        if len({r['pet_id'] for r in rows}) != len(rows):
            return result('invalid_argument', message='比较对象应为不同精灵')
        if any(r['value'] is None for r in rows):
            return result('data_missing', {'stat': stat, 'items': rows}, sources, '部分精灵的该项种族值待补齐')
        ranking = sorted(rows, key=lambda r: (-r['value'], r['pet_id']))
        data = {'stat': stat, 'ranking': ranking}
        if len(ranking) == 2:
            data['difference'] = ranking[0]['value'] - ranking[1]['value']
        return result('ok', data, sources)

    def statistics(self):
        row = self.conn.execute("SELECT value FROM metadata WHERE key='import'").fetchone()
        return result('ok', json.loads(row[0]) if row else {})
