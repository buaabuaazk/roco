import json
import sqlite3
import unittest
from types import SimpleNamespace

from roco_data.tools import RocoTools


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def handler(name):
            def execute(**kwargs):
                self.calls.append((name, kwargs))
                return {'status': 'ok', 'data': kwargs, 'sources': []}
            return execute

        self.names = ['search_pets', 'get_pet', 'get_skill', 'get_pet_skills', 'compare_pets']
        self.tools = RocoTools(SimpleNamespace(**{name: handler(name) for name in self.names}))

    def test_exactly_five_definitions_and_fixed_dispatch(self):
        self.assertEqual([t['function']['name'] for t in self.tools.definitions], self.names)
        calls = [('search_pets', {'query': '喵'}), ('get_pet', {'identifier': 3001, 'section': 'family'}),
                 ('get_skill', {'identifier': '抓挠'}),
                 ('get_pet_skills', {'identifier': '喵喵', 'source': 'blood', 'skill': 7020910}),
                 ('compare_pets', {'identifiers': [3001, '迪莫'], 'stat': 'speed'})]
        for name, arguments in calls:
            self.assertEqual(self.tools.execute(name, json.dumps(arguments))['status'], 'ok')
        self.assertEqual(self.calls, calls)
        self.assertEqual(self.tools.execute('import_data', {})['status'], 'unknown_tool')

    def test_invalid_arguments_are_rejected_before_execution(self):
        invalid = [('get_pet', {}), ('get_pet', {'identifier': True}),
                   ('get_pet', {'identifier': ' '}), ('get_pet', {'identifier': -1}),
                   ('get_pet', {'identifier': 2**80}),
                   ('get_pet', {'identifier': 3001, 'sql': 'DROP TABLE pets'}),
                   ('get_pet', {'identifier': 3001, 'section': 'unknown'}),
                   *[('get_pet', {'identifier': 3001, 'section': section})
                     for section in ('appearance', 'talents', 'natures', 'stories')],
                   ('search_pets', {'limit': 101}),
                   ('get_pet_skills', {'identifier': 3001, 'source': 'unknown'}),
                   ('compare_pets', {'identifiers': [3001]}),
                   ('compare_pets', {'identifiers': [3001, '迪莫'], 'stat': 'invalid'}),
                   ('get_pet', 'bad JSON'), ('get_pet', '[]'), ('get_pet', None)]
        for name, arguments in invalid:
            with self.subTest(name=name, arguments=arguments):
                self.assertEqual(self.tools.execute(name, arguments)['status'], 'invalid_argument')
        self.assertEqual(self.calls, [])

    def test_definitions_are_isolated_and_query_failure_is_structured(self):
        definitions = self.tools.definitions
        definitions[0]['function']['name'] = 'changed'
        self.assertEqual(self.tools.definitions[0]['function']['name'], 'search_pets')

        def broken(**kwargs):
            raise sqlite3.OperationalError('internal detail')

        self.tools._handlers['get_pet'] = broken
        answer = self.tools.execute('get_pet', {'identifier': 3001})
        self.assertEqual(answer['status'], 'tool_error')
        self.assertNotIn('internal detail', answer['message'])


if __name__ == '__main__':
    unittest.main()
