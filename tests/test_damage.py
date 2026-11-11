import json
import unittest

from roco_data import JsonQueries, RocoTools
from roco_data.damage import calculate_damage
from roco_agent import RocoAgent


class DamageTests(unittest.TestCase):
    def test_documented_example_and_final_multiplier(self):
        answer = calculate_damage(attack=234, defense=226, base_power=75, flat_power_bonus=20,
                                  power_percent_bonus=.5, stab_multiplier=1.25, type_multiplier=2,
                                  defender_hp=411)
        self.assertEqual(answer['estimated_damage'], 332)
        self.assertEqual(answer['steps'][0]['value'], 142.5)
        self.assertEqual(answer['steps'][2]['value'], 356)
        self.assertFalse(answer['estimated_ko'])
        self.assertAlmostEqual(answer['damage_percent'], 332 / 411 * 100)
        self.assertEqual(answer['verification_status'], 'pending_in_game_validation')
        reduced = calculate_damage(attack=234, defense=226, base_power=75, flat_power_bonus=20,
                                   power_percent_bonus=.5, stab_multiplier=1.25, type_multiplier=2,
                                   final_damage_multiplier=.3)
        self.assertEqual(reduced['estimated_damage'], 99.6)

    def test_half_up_immunity_zero_power_and_stage_composition(self):
        args = dict(attack=100, defense=100, base_power=2.5)
        self.assertEqual(calculate_damage(**args)['steps'][2]['value'], 3)
        self.assertEqual(calculate_damage(**args, type_multiplier=0)['estimated_damage'], 0)
        self.assertEqual(calculate_damage(**args, flat_power_bonus=-50)['estimated_damage'], 0)
        self.assertEqual(calculate_damage(**args, power_percent_bonus=-1)['estimated_damage'], 0)
        staged = calculate_damage(**args, attack_boost=1, defense_reduction=.4,
                                   attack_reduction=.2, defense_boost=.7)
        self.assertAlmostEqual(staged['steps'][1]['value'], 2.4 / 1.9)

    def test_invalid_and_nonfinite_inputs_are_rejected(self):
        tools = RocoTools(JsonQueries())
        for extra in ({'defense': 0}, {'attack': True}, {'attack': float('nan')},
                      {'base_power': float('inf')}, {'power_percent_bonus': -2}, {'defender_hp': 0},
                      {'attack': 1000001}, {'level': 0}, {'level': 1.5}, {'unknown': 1}):
            args = dict(attack=100, defense=100, base_power=100) | extra
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError): calculate_damage(**args)
                self.assertEqual(tools.execute('calculate_damage', args)['status'], 'invalid_argument')
        self.assertEqual(tools.execute('calculate_damage', {})['status'], 'invalid_argument')
        result = tools.execute('calculate_damage', {'attack': 100, 'defense': 100, 'base_power': 100})
        self.assertEqual(result['data']['estimated_damage'], 90)

    def test_agent_receives_steps_and_validation_state(self):
        received = []
        class Model:
            model = 'test'
            def complete(self, messages, tools, timeout):
                if messages[-1]['role'] != 'tool':
                    return {'role': 'assistant', 'tool_calls': [{'id': 'calc', 'type': 'function',
                        'function': {'name': 'calculate_damage', 'arguments': json.dumps(
                            {'attack': 100, 'defense': 100, 'base_power': 100, 'defender_hp': 80})}}]}
                received.append(json.loads(messages[-1]['content']))
                return {'role': 'assistant', 'content': '社区公式估算伤害90，约为当前生命的112.5%。'}
        answer = RocoAgent(Model(), JsonQueries()).ask('实际攻击100、防御100、威力100、60级，打80生命能打多少？')
        self.assertEqual(answer['status'], 'ok')
        self.assertEqual(answer['tool_calls'][0]['name'], 'calculate_damage')
        self.assertTrue(received[0]['data']['estimated_ko'])
        self.assertEqual(len(received[0]['data']['steps']), 7)
        self.assertNotIn('sources', received[0])
        self.assertIn('assumptions', received[0]['data'])


if __name__ == '__main__':
    unittest.main()
