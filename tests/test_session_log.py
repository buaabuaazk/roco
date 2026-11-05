import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from roco_agent import RocoAgent
from roco_agent.llm import ModelError
from roco_agent.session_log import SessionLog


class LogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.payload = {'status': 'ok', 'data': {'items': [{'pet_id': 3001, 'name': '喵喵'}]},
                        'sources': [{'file': 'pets/3001/combined.json'}]}
        self.queries = SimpleNamespace(**{name: lambda **kwargs: self.payload for name in (
            'search_pets', 'get_pet', 'get_skill', 'get_pet_skills', 'get_skill_pets', 'compare_pets')})

    def model(self, final='可以。'):
        class FakeModel:
            model = 'test-model'
            calls = 0

            def complete(self, *args):
                self.calls += 1
                if self.calls == 1:
                    return {'role': 'assistant', 'tool_calls': [{'id': 'call_1', 'type': 'function',
                            'function': {'name': 'search_pets', 'arguments': '{"query":"喵喵"}'}}]}
                if isinstance(final, BaseException):
                    raise final
                return {'role': 'assistant', 'content': final}

            def close(self):
                pass

        return FakeModel()

    def read(self, logger):
        return [json.loads(line) for line in logger.path.read_text(encoding='utf-8').splitlines()]

    def test_logs_raw_query_and_exact_model_payload_and_final_answer(self):
        logger = SessionLog(self.directory)
        agent = RocoAgent(self.model(), self.queries, logger=logger)
        self.assertEqual(agent.ask('喵喵能学毒沼吗？')['status'], 'ok')
        events = self.read(logger)
        self.assertEqual([e['event'] for e in events], [
            'session_start', 'turn_start', 'model_request', 'tool_call',
            'tool_result', 'model_request', 'turn_end'])
        self.assertEqual(events[1]['question'], '喵喵能学毒沼吗？')
        tool = events[4]
        self.assertEqual(tool['query_result'], self.payload)
        self.assertEqual(tool['model_result'], 3001)
        self.assertEqual(tool['call_id'], events[3]['call_id'])
        self.assertEqual(events[-1]['answer'], '可以。')
        self.assertEqual(events[-1]['status'], 'ok')
        self.assertEqual(len({e['turn_id'] for e in events if 'turn_id' in e}), 1)
        self.assertEqual({e['session_id'] for e in events}, {logger.session_id})
        self.assertTrue(all(e['timestamp'].endswith('+08:00') for e in events))

    def test_failure_and_interrupt_preserve_completed_tool_events(self):
        for final, expected in [(ModelError('连接失败'), 'model_error'), (KeyboardInterrupt(), 'interrupted')]:
            with self.subTest(expected=expected):
                logger = SessionLog(self.directory)
                agent = RocoAgent(self.model(final), self.queries, logger=logger)
                if isinstance(final, KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        agent.ask('查喵喵')
                else:
                    self.assertEqual(agent.ask('查喵喵')['status'], expected)
                events = self.read(logger)
                self.assertTrue(any(e['event'] == 'tool_result' for e in events))
                self.assertEqual(events[-1]['event'], 'turn_end')
                self.assertEqual(events[-1]['status'], expected)
                self.assertEqual(agent.turns, [])

    def test_redacts_key_and_sensitive_fields_without_mutating_input(self):
        with patch.dict(os.environ, {'ZZZ_API_KEY': ' private-test-value '}):
            logger = SessionLog(self.directory)
        original = {'question': '内容 private-test-value', 'nested': {'api_key': 'other-secret'}}
        logger.write('test', **original)
        text = logger.path.read_text(encoding='utf-8')
        self.assertNotIn('private-test-value', text)
        self.assertNotIn('other-secret', text)
        self.assertIn('private-test-value', original['question'])
        self.assertEqual(self.read(logger)[0]['nested']['api_key'], '[REDACTED]')

    def test_cli_logs_by_default_without_trace(self):
        from roco_agent.__main__ import main
        logger = SessionLog(self.directory)
        with patch('sys.argv', ['roco_agent', '查喵喵']), \
                patch('roco_agent.__main__.RocoQueries') as queries, \
                patch('roco_agent.__main__.ChatModel', return_value=self.model()), \
                patch('roco_agent.__main__.SessionLog', return_value=logger), \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            queries.return_value.__enter__.return_value = self.queries
            self.assertEqual(main(), 0)
            self.assertEqual(output.getvalue().strip(), '可以。')
        self.assertEqual(self.read(logger)[-1]['event'], 'turn_end')

    def test_new_turn_ids_reset_and_write_failure(self):
        logger = SessionLog(self.directory)
        agent = RocoAgent(self.model(), self.queries, logger=logger)
        agent.ask('喵喵？')
        agent.reset()
        agent.ask('再问一次')
        events = self.read(logger)
        self.assertEqual(len({e['turn_id'] for e in events if 'turn_id' in e}), 2)
        self.assertTrue(any(e['event'] == 'context_reset' for e in events))
        with patch.object(logger, 'write', side_effect=PermissionError('无法写入')):
            with self.assertRaises(PermissionError):
                agent.ask('测试写入失败')


if __name__ == '__main__':
    unittest.main()
