"""隔离临时目录中的数据层回归测试，不修改采集文件。"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from roco_data import RocoQueries, import_data


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'data'
        self.db = Path(self.temp.name) / 'roco.db'
        self.stats = dict(hp=65, physical_attack=66, physical_defense=49,
                          magic_attack=66, magic_defense=91, speed=33, sum=370)
        for pet_id, name, speed in ((3001, '喵喵', 33), (3004, '迪莫', 92)):
            stats = {**self.stats, 'speed': speed, 'sum': 370 + speed - 33}
            sections = {
                'base': {'pet_id': pet_id, 'name': name, 'handbook_no': '002', 'types': [{'id': 3, 'name': '草'}]},
                'profile': {'attributes': stats},
                'features': {'items': [{'name': '氧循环', 'desc': '使用草系技能后，回复10%生命。'}]},
                'skills': {'level': [{'skill_id': 7, 'level': 1}, {'skill_id': 8, 'level': 10}],
                           'machine': [{'skill_id': 9}],
                           'blood': [{'skill_id': 8, 'level': 15, 'bloodline_id': 1}]},
                'stories': {'items': [], 'total': 0},
            }
            self.write(f'pets/{pet_id}/combined.json', {'pet_id': pet_id, 'name': name, 'sections': sections})
            self.write(f'pets/{pet_id}/pet-detail.json', {
                'ok': True, 'resource': 'pet-detail', 'updated_at': '2026-11-01T10:22:57+08:00',
                'stale': True, 'warning': '上游暂时不可用，返回最近缓存',
                'sections': {'skills': {'blood': [{'skill_id': 8, 'bloodline': {'id': 1, 'name': '普通系血脉'}}]}},
            })
        self.write('lists/skills_1.json', {'ok': True, 'items': [
            {'skill_id': 7, 'name': '抓挠'}, {'skill_id': 8, 'name': '星星撞击'}, {'skill_id': 9, 'name': '毒沼'}]})
        for skill_id, name in ((7, '抓挠'), (8, '星星撞击')):
            self.write(f'skills/{skill_id}.json', {'ok': True, 'data': {
                'skill_id': skill_id, 'name': name, 'power': '35', 'cost': '0', 'description': '技能效果'}})
        import_data(self.root, self.db)

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding='utf-8')

    def test_identity_stats_sources_and_empty_story(self):
        with RocoQueries(self.db) as q:
            pet = q.get_pet('喵喵')
            self.assertEqual(pet['data']['handbook_no'], '002')
            self.assertEqual(pet['data']['attributes'], self.stats)
            self.assertEqual(q.get_pet(3001), q.get_pet('3001'))
            self.assertTrue(pet['sources'][0]['stale'])
            self.assertEqual(pet['sources'][0]['updated_at'], '2026-11-01T10:22:57+08:00')
            story = q.get_pet('喵喵', 'stories')
            self.assertEqual(story['status'], 'ok')
            self.assertEqual(story['data']['value']['items'], [])
            self.assertEqual(q.get_pet('喵喵', 'egg')['status'], 'data_missing')

    def test_skill_join_keeps_source_level_and_bloodline(self):
        with RocoQueries(self.db) as q:
            upgrade = q.get_pet_skills('喵喵', 'level', max_level=10)
            self.assertEqual(upgrade['status'], 'ok')
            self.assertEqual([i['skill_id'] for i in upgrade['data']['items']], [7, 8])
            self.assertEqual(upgrade['data']['items'][0]['detail']['cost'], '0')
            blood = q.get_pet_skills(3001, 'blood', skill='星星撞击')['data']['items'][0]
            self.assertEqual((blood['level'], blood['bloodline_id'], blood['bloodline_name']),
                             (15, 1, '普通系血脉'))
            self.assertEqual(q.get_pet_skills(3001, 'level', skill=9)['data']['can_learn_in_selected_scope'], False)

    def test_sources_follow_requested_section(self):
        pet_path = self.root / 'pets/3001/combined.json'
        pet = json.loads(pet_path.read_text())
        pet['sections']['ecology'] = {'name': '喵喵'}
        self.write('pets/3001/combined.json', pet)
        self.write('pets/3001/pet-ecology.json', {
            'ok': True, 'resource': 'pet-ecology', 'data': {'name': '喵喵'},
            'updated_at': '2026-11-02T10:00:00+08:00'})
        import_data(self.root, self.db)
        with RocoQueries(self.db) as q:
            ecology = q.get_pet('喵喵', 'ecology')
            self.assertEqual([s['section'] for s in ecology['sources']], ['pet-ecology'])
            self.assertEqual([s['section'] for s in q.get_pet('喵喵', 'features')['sources']], ['pet-detail'])
            self.assertEqual([s['section'] for s in q.get_pet('喵喵')['sources']], ['pet-detail'])

    def test_missing_detail_preserves_learning_membership(self):
        with RocoQueries(self.db) as q:
            answer = q.get_pet_skills(3001, 'machine', skill='毒沼')
            self.assertEqual(answer['status'], 'partial')
            self.assertTrue(answer['data']['can_learn_in_selected_scope'])
            self.assertEqual(answer['data']['items'][0]['detail_status'], 'detail_missing')
            self.assertIsNone(answer['data']['items'][0]['detail'])
            self.assertEqual(q.get_skill('毒沼')['status'], 'detail_missing')
            self.assertEqual(q.search_skills('毒')['data']['items'][0]['has_detail'], False)

    def test_search_parameterization_and_input_validation(self):
        with RocoQueries(self.db) as q:
            self.assertEqual(q.search_pets('喵', '草')['data']['items'][0]['pet_id'], 3001)
            self.assertTrue(q.search_pets(limit=1)['data']['has_more'])
            self.assertFalse(q.search_pets('喵')['data']['has_more'])
            self.assertEqual(q.search_pets("' OR 1=1 --")['data']['items'], [])
            self.assertEqual(q.get_pet("' OR 1=1 --")['status'], 'not_found')
            self.assertEqual(q.get_pet('不存在XYZ')['status'], 'not_found')
            self.assertEqual(q.get_pet('')['status'], 'invalid_argument')
            self.assertEqual(q.get_pet(2 ** 80)['status'], 'invalid_argument')
            self.assertEqual(q.get_pet(str(2 ** 80))['status'], 'invalid_argument')
            self.assertEqual(q.get_pet('喵喵', [])['status'], 'invalid_argument')
            self.assertEqual(q.search_pets(limit=0)['status'], 'invalid_argument')
            self.assertEqual(q.get_pet_skills(3001, source='unknown')['status'], 'invalid_argument')
            self.assertEqual(q.get_pet_skills(3001, 'machine', max_level=1)['status'], 'invalid_argument')

    def test_search_prefers_exact_name_before_keyword_and_limit(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute('INSERT INTO pets (pet_id, name, sections_json, sources_json) VALUES (?, ?, ?, ?)',
                         (3471, '化蝶（喵喵的样子）', '{}', '[]'))
        with RocoQueries(self.db) as q:
            exact = q.search_pets(' 喵喵 ', limit=1)['data']
            self.assertEqual([row['pet_id'] for row in exact['items']], [3001])
            self.assertFalse(exact['has_more'])
            self.assertEqual(len(q.search_pets('喵')['data']['items']), 2)
            self.assertTrue(q.search_pets('喵', limit=1)['data']['has_more'])

    def test_skill_pets_sqlite_groups_and_filters(self):
        with RocoQueries(self.db) as q:
            data = q.get_skill_pets('星星撞击', limit=1)['data']
            self.assertEqual(data['total'], 2)
            self.assertEqual(len(data['items'][0]['learning']), 2)
            self.assertTrue(data['has_more'])
            self.assertEqual(data['next_offset'], 1)
            second = q.get_skill_pets(8, offset=1, source='blood')['data']
            self.assertEqual(len(second['items']), 1)
            self.assertEqual(second['items'][0]['learning'][0]['bloodline_name'], '普通系血脉')
            self.assertFalse(second['has_more'])
            self.assertEqual(q.get_skill_pets(9)['status'], 'ok')
            self.assertEqual(q.get_skill_pets(999)['status'], 'not_found')

    def test_compare_and_read_only(self):
        with RocoQueries(self.db) as q:
            answer = q.compare_pets(['喵喵', 3004])
            self.assertEqual(answer['data']['difference'], 59)
            self.assertEqual(answer['data']['ranking'][0]['name'], '迪莫')
            self.assertEqual(q.compare_pets([3001, 3001])['status'], 'invalid_argument')
            self.assertEqual(q.compare_pets([3001, 3004], 'invalid')['status'], 'invalid_argument')
            self.assertEqual(q.compare_pets([3001, 999])['status'], 'not_found')
            with self.assertRaises(sqlite3.OperationalError):
                q.conn.execute('DELETE FROM pets')

    def test_reimport_completes_missing_detail_without_duplicate_relations(self):
        self.write('skills/9.json', {'ok': True, 'data': {'skill_id': 9, 'name': '毒沼', 'power': '80'}})
        for _ in range(2):
            report = import_data(self.root, self.db)
            self.assertEqual(report['learning_relations'], 8)
            self.assertEqual(report['relations_missing_detail'], 0)
        with RocoQueries(self.db) as q:
            self.assertEqual(q.get_skill(9)['data']['power'], '80')
            self.assertEqual(q.get_pet_skills('喵喵', 'machine')['status'], 'ok')
            self.assertEqual(q.conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_failed_import_rolls_back_previous_snapshot(self):
        with RocoQueries(self.db) as q:
            before = q.statistics()
        self.write('skills/9.json', {'ok': True, 'data': {'skill_id': 900, 'name': '错误 ID'}})
        with self.assertRaises(ValueError):
            import_data(self.root, self.db)
        with RocoQueries(self.db) as q:
            self.assertEqual(q.statistics(), before)
            self.assertEqual(q.get_pet('喵喵')['status'], 'ok')
            self.assertEqual(q.get_skill(9)['status'], 'detail_missing')

    def test_ambiguous_name_requires_id(self):
        path = self.root / 'pets/3004/combined.json'
        pet = json.loads(path.read_text())
        pet['name'] = pet['sections']['base']['name'] = '喵喵'
        self.write('pets/3004/combined.json', pet)
        import_data(self.root, self.db)
        with RocoQueries(self.db) as q:
            self.assertEqual(q.get_pet('喵喵')['status'], 'ambiguous')
            self.assertEqual(q.get_pet(3001)['status'], 'ok')

    def test_missing_database_does_not_create_empty_file(self):
        missing = Path(self.temp.name) / 'missing.db'
        with self.assertRaises(FileNotFoundError):
            RocoQueries(missing)
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
