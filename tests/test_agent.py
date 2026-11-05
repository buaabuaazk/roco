import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from roco_agent import RocoAgent
from roco_agent.llm import ModelError


def call(name='get_pet', arguments='{"identifier":"喵喵"}', call_id='call_1'):
    return {'id': call_id, 'type': 'function', 'function': {'name': name, 'arguments': arguments}}


def message(calls=None, text=None):
    return {'role': 'assistant', 'tool_calls': calls or [], 'content': text}


class FakeModel:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def complete(self, messages, tools, timeout):
        self.requests.append(deepcopy(messages))
        assert len(tools) == 6 and timeout > 0
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.payload = {'status': 'ok', 'data': {'pet_id': 3001, 'name': '喵喵', 'icon': 'image-url'},
                        'sources': [{'file': 'pets/3001/combined.json'}]}

        def query(**kwargs):
            self.calls.append(kwargs)
            return deepcopy(self.payload)

        self.queries = SimpleNamespace(**{name: query for name in (
            'search_pets', 'get_pet', 'get_skill', 'get_pet_skills', 'get_skill_pets', 'compare_pets')})

    def test_tool_result_round_trip_and_follow_up(self):
        model = FakeModel([message([call()]), message(text='喵喵是草属性。'),
                           message([call(arguments='{"identifier":"喵喵","section":"features"}')]),
                           message(text='特性是氧循环。')])
        agent = RocoAgent(model, self.queries)
        answer = agent.ask('喵喵是什么属性？')
        self.assertEqual(answer['status'], 'ok')
        tool_message = model.requests[1][-1]
        self.assertEqual(tool_message['role'], 'tool')
        self.assertEqual(tool_message['tool_call_id'], 'call_1')
        self.assertEqual(json.loads(tool_message['content'])['data']['name'], '喵喵')
        self.assertNotIn('icon', json.loads(tool_message['content'])['data'])
        self.assertEqual(answer['sources'], self.payload['sources'])
        self.assertEqual(agent.ask('它的特性呢？')['status'], 'ok')
        self.assertTrue(any(m.get('content') == '喵喵是什么属性？' for m in model.requests[2]))
        self.assertEqual(len(agent.turns), 2)
        agent.reset()
        self.assertEqual(agent.turns, [])

    def test_multiple_calls_return_each_call_id(self):
        model = FakeModel([message([call(call_id='a'), call('get_skill', '{"identifier":"抓挠"}', 'b')]),
                           message(text='结果已查询。')])
        answer = RocoAgent(model, self.queries).ask('查询喵喵和抓挠')
        self.assertEqual(answer['status'], 'ok')
        self.assertEqual([m['tool_call_id'] for m in model.requests[1] if m['role'] == 'tool'], ['a', 'b'])

    def test_reverse_skill_question_uses_one_tool_call(self):
        from roco_data import JsonQueries
        queries = JsonQueries()
        model = FakeModel([message([call('get_skill_pets', '{"identifier":"丰饶"}')]),
                           message(text='喵喵等精灵可以学习丰饶。')])
        answer = RocoAgent(model, queries).ask('哪些精灵可以学习丰饶？')
        self.assertEqual(answer['status'], 'ok')
        self.assertEqual(len(answer['tool_calls']), 1)
        data = json.loads(model.requests[1][-1]['content'])['data']
        self.assertEqual(data['技能'], '丰饶')
        self.assertIn('喵喵', [pet['名称'] for pet in data['精灵']])
        self.assertFalse(data['has_more'])

    def test_search_model_payload_preserves_ambiguity_and_backend_metadata(self):
        candidates = [{'pet_id': 3001, 'name': '喵喵', 'handbook_no': '002'},
                      {'pet_id': 3025, 'name': '喵呜', 'handbook_no': '003'}]
        short = [{'pet_id': p['pet_id'], 'name': p['name']} for p in candidates]
        for items, has_more, expected in [
                (candidates[:1], False, 3001),
                (candidates, False, short),
                ([], False, '未找到'),
                (candidates[:1], True, {'candidates': short[:1], 'has_more': True})]:
            with self.subTest(items=items, has_more=has_more):
                self.payload['data'] = {'items': items, 'has_more': has_more, 'limit': 20}
                model = FakeModel([message([call('search_pets', '{"query":"喵"}')]), message(text='查询完成')])
                answer = RocoAgent(model, self.queries).ask('查找喵')
                self.assertEqual(json.loads(model.requests[1][-1]['content']), expected)
                self.assertEqual(answer['tool_calls'][0]['status'], 'ok')
                self.assertEqual(answer['sources'], self.payload['sources'])

    def test_model_results_exclude_nested_metadata_but_keep_learning_source(self):
        self.payload['data'] = {'items': [{
            'skill_id': 7120200, 'name': '毒沼', 'source': 'machine', 'level': None,
            'detail': {'power': '80', 'cost': '2', 'updated_at': 'old-time', 'stale': True},
            'sources': [{'file': 'skills/7120200.json', 'warning': 'upstream unavailable'}],
        }], 'updated_at': 'old-time'}
        self.payload.update(stale=True, warning='upstream unavailable')
        model = FakeModel([message([call('get_pet_skills', '{"identifier":3001,"skill":"毒沼"}')]),
                           message(text='可以通过技能石学习。')])
        answer = RocoAgent(model, self.queries).ask('喵喵能学毒沼吗？')
        payload = json.loads(model.requests[1][-1]['content'])
        self.assertEqual(payload, {'status': 'ok', 'data': {'技能': [{
            '名称': '毒沼', '威力': 80, '能耗': 2, '学习方式': '技能石',
        }]}})
        self.assertEqual(len(answer['sources']), 2)
        self.assertTrue(self.payload['stale'])

    def test_invalid_arguments_and_unknown_tool_are_feedback(self):
        model = FakeModel([message([call(arguments='{'), call('delete_data', '{}', 'b')]),
                           message(text='请确认查询对象。')])
        answer = RocoAgent(model, self.queries).ask('查询')
        self.assertEqual([r['status'] for r in answer['tool_calls']], ['invalid_argument', 'unknown_tool'])
        self.assertEqual(self.calls, [])

    def test_round_and_tool_budgets_preserve_history(self):
        agent = RocoAgent(FakeModel([message([call()])]), self.queries, max_rounds=1)
        self.assertEqual(agent.ask('查喵喵')['status'], 'round_limit')
        self.assertEqual(agent.turns, [])
        self.calls.clear()
        agent = RocoAgent(FakeModel([message([call(call_id='a'), call(call_id='b')])]),
                          self.queries, max_tool_calls=1)
        self.assertEqual(agent.ask('查喵喵')['status'], 'tool_limit')
        self.assertEqual(self.calls, [])

    def test_deadline_stops_before_executing_tools(self):
        clock = [0]

        class SlowModel:
            def complete(self, *args):
                clock[0] = 121
                return message([call()])

        with patch('roco_agent.agent.time.monotonic', side_effect=lambda: clock[0]):
            agent = RocoAgent(SlowModel(), self.queries)
            self.assertEqual(agent.ask('查喵喵')['status'], 'timeout')
        self.assertEqual(self.calls, [])

    def test_failed_turn_does_not_commit_incomplete_protocol(self):
        agent = RocoAgent(FakeModel([message(text='你想查询哪只精灵？'), ModelError('请求超时')]), self.queries)
        agent.ask('它怎么进化？')
        history = deepcopy(agent.turns)
        self.assertEqual(agent.ask('喵喵')['status'], 'model_error')
        self.assertEqual(agent.turns, history)

    def test_large_results_request_narrower_query(self):
        self.payload['data']['text'] = '长' * 51000
        model = FakeModel([message([call()]), message(text='请指定资料分区。')])
        answer = RocoAgent(model, self.queries).ask('给我所有资料')
        self.assertEqual(answer['tool_calls'][0]['status'], 'result_too_large')
        self.assertEqual(json.loads(model.requests[1][-1]['content'])['data'], None)

    def test_protocol_errors_and_empty_question(self):
        for reply in (message(text=''), message([call(call_id='same'), call(call_id='same')]),
                      {'role': 'user', 'content': 'bad'}):
            with self.subTest(reply=reply):
                agent = RocoAgent(FakeModel([reply]), self.queries)
                self.assertIn(agent.ask('查询')['status'], ('empty_response', 'protocol_error'))
                self.assertEqual(agent.turns, [])
        agent = RocoAgent(FakeModel([]), self.queries)
        self.assertEqual(agent.ask(' ')['status'], 'invalid_argument')


if __name__ == '__main__':
    unittest.main()
