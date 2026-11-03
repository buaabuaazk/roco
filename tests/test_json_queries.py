import contextlib
import io
import unittest
from unittest.mock import patch

from roco_data import JsonQueries, RocoTools
from roco_agent.presentation import model_result


class JsonQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('sqlite3.connect', side_effect=AssertionError('JSON 查询不应连接 SQLite')):
            cls.queries = JsonQueries()
        cls.tools = RocoTools(cls.queries)

    def test_all_five_tools_and_current_skill_data(self):
        answer = self.tools.execute('search_pets', {'query': '喵喵'})
        self.assertIn({'pet_id': 3001, 'name': '喵喵'}, model_result('search_pets', answer))
        skill = self.tools.execute('get_skill', {'identifier': '轴承支撑'})
        self.assertEqual(skill['data']['cost'], 6)
        learned = self.tools.execute('get_pet_skills', {'identifier': 3001, 'skill': '毒沼'})
        self.assertTrue(learned['data']['can_learn_in_selected_scope'])
        self.assertEqual(learned['data']['items'][0]['source'], 'machine')
        rank = self.tools.execute('compare_pets', {'identifiers': [3001, 3200], 'stat': 'speed'})
        self.assertEqual([row['value'] for row in rank['data']['ranking']], [51, 33])
        self.assertEqual(rank['data']['difference'], 18)

    def test_evolution_conditions_reach_model_without_legacy_costs(self):
        answer = self.tools.execute('get_pet', {'identifier': 3200, 'section': 'family'})
        data = model_result('get_pet', answer)['data']['value']
        self.assertEqual(data['branches'][0]['transitions'][0]['conditions'],
                         {'level': 28, 'special': '需在他人世界'})
        cat = self.queries.get_pet(3001, 'family')['data']['value']
        self.assertEqual(cat['branches'][0]['transitions'][0]['conditions'], {'level': 16})
        self.assertEqual(cat['branches'][0]['transitions'][-1]['conditions']['item'], '阳光罐头')

    def test_level_filter_feature_and_missing_sections(self):
        learned = self.queries.get_pet_skills('古卷匣魔像', skill='血气')['data']['items']
        self.assertEqual(learned[0]['level'], 39)
        self.assertFalse(self.queries.get_pet_skills('古卷匣魔像', max_level=38, skill='血气')
                         ['data']['can_learn_in_selected_scope'])
        feature = self.queries.get_pet(3001, 'features')['data']['value']['items'][0]
        self.assertEqual(feature['name'], '氧循环')
        self.assertEqual(self.queries.get_pet(3001, 'natures')['status'], 'data_missing')
        self.assertEqual(self.queries.get_skill('不存在的技能')['status'], 'not_found')
        self.assertEqual(self.queries.compare_pets([3001, 3001])['status'], 'invalid_argument')

    def test_legendary_requirement_and_search_truncation(self):
        pet = next(pet for pet in self.queries.pets.values() if pet['skills']['legendary'])
        answer = self.tools.execute('get_pet_skills', {'identifier': pet['pet_id'], 'source': 'legendary'})
        self.assertEqual(answer['status'], 'ok')
        self.assertEqual(answer['data']['items'][0]['requires'], pet['skills']['legendary'][0]['requires'])
        view = model_result('get_pet_skills', answer)['data']['技能'][0]
        self.assertEqual(view['学习条件'], pet['skills']['legendary'][0]['requires'])
        search = self.queries.search_pets('', limit=1)
        self.assertTrue(search['data']['has_more'])
        self.assertIsInstance(model_result('search_pets', search), dict)

    def test_agent_cli_defaults_to_json(self):
        from roco_agent.__main__ import main
        with patch('sys.argv', ['roco_agent', '测试']), \
                patch('roco_agent.__main__.RocoQueries', side_effect=AssertionError('不应使用数据库')), \
                patch('roco_agent.__main__.ChatModel'), \
                patch('roco_agent.__main__.SessionLog'), \
                patch('roco_agent.__main__.RocoAgent') as agent, contextlib.redirect_stdout(io.StringIO()):
            agent.return_value.ask.return_value = {'status': 'ok', 'answer': '测试通过'}
            self.assertEqual(main(), 0)
            self.assertIsInstance(agent.call_args.args[1], JsonQueries)


if __name__ == '__main__':
    unittest.main()
