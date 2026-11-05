import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from roco_server.service import BusyError, SessionManager


class ServerTests(unittest.TestCase):
    def wait(self, session):
        deadline = time.monotonic() + 5
        while session.snapshot(False)['busy']:
            if time.monotonic() > deadline:
                self.fail('后台请求未按时完成')
            time.sleep(0.01)
        return session.snapshot()

    def test_live_events_are_redacted_and_sessions_are_independent(self):
        gate, started = threading.Event(), threading.Event()

        class Model:
            def __init__(self, model):
                self.model, self.calls, self.closed = model, 0, False

            def complete(self, messages, tools, timeout):
                self.calls += 1
                started.set()
                gate.wait(3)
                if self.calls == 1:
                    return {'role': 'assistant', 'tool_calls': [{'id': 'reverse', 'type': 'function',
                            'function': {'name': 'get_skill_pets', 'arguments': '{"identifier":"丰饶"}'}}]}
                return {'role': 'assistant', 'content': '喵喵可以学习。 test-secret'}

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'ZZZ_API_KEY': 'test-secret'}):
            manager = SessionManager(log_dir=directory, model_factory=Model)
            self.addCleanup(manager.close)
            first, second = manager.create('test-model'), manager.create('other-model')
            session = manager.get(first['id'])
            run_id = manager.start(first['id'], '哪些精灵能学丰饶？')
            self.assertTrue(started.wait(2))
            with self.assertRaises(BusyError):
                manager.start(first['id'], '重复点击')
            with self.assertRaises(BusyError):
                manager.reload_data()
            events, done = session.events(run_id)
            self.assertFalse(done)
            self.assertIn('model_request', [event['event'] for event in events])
            self.assertEqual(manager.get(second['id']).snapshot()['runs'], [])
            gate.set()
            final = self.wait(session)
            run = final['runs'][0]
            self.assertEqual(run['status'], 'ok')
            self.assertEqual(run['answer'], '喵喵可以学习。 [REDACTED]')
            result = next(event for event in run['events'] if event['event'] == 'tool_result')
            self.assertEqual(result['query_result']['data']['name'], '丰饶')
            self.assertEqual(result['model_result']['data']['技能'], '丰饶')
            last = run['events'][-1]
            self.assertEqual(last['event'], 'run_finished')
            self.assertEqual(session.events(run_id, last['sequence']), ([], True))
            logs = list(Path(directory).glob('*.jsonl'))
            self.assertNotIn('test-secret', ''.join(path.read_text() for path in logs))
            self.assertEqual(len(session.agent.turns), 1)
            manager.reload_data()
            self.assertEqual(session.snapshot()['runs'], [])
            self.assertEqual(session.agent.turns, [])

    def test_model_start_failure_is_visible_and_can_be_retried(self):
        def missing_key(model):
            raise ValueError('请配置模型密钥')

        with tempfile.TemporaryDirectory() as directory:
            manager = SessionManager(log_dir=directory, model_factory=missing_key)
            value = manager.create()
            session = manager.get(value['id'])
            manager.start(value['id'], '测试')
            run = self.wait(session)['runs'][0]
            self.assertTrue(run['done'])
            self.assertEqual(run['status'], 'error')
            self.assertIn('模型密钥', run['answer'])
            manager.start(value['id'], '再次尝试')
            self.assertEqual(len(self.wait(session)['runs']), 2)
            manager.close()

    def test_log_failure_does_not_leave_session_busy(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SessionManager(log_dir=directory)
            value = manager.create()
            session = manager.get(value['id'])
            with patch.object(session.logger, 'write', side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):
                    manager.start(value['id'], '测试')
            self.assertFalse(session.snapshot()['busy'])
            self.assertEqual(session.snapshot()['runs'], [])
            manager.close()


if __name__ == '__main__':
    unittest.main()
