import unittest

from pydantic import ValidationError
from roco_server.buffs import BuffInput, resolve_buffs


def buff(kind, value, layers=1, side='attacker', **extra):
    return BuffInput(kind=kind, value=value, layers=layers, side=side, **extra)


class BuffTests(unittest.TestCase):
    def test_stat_channels_sum_and_inactive_rows(self):
        rows = [buff('dual_attack_boost', 20, 3), buff('spa_boost', 10),
                buff('atk_boost', 100), buff('dual_defense_reduction', 20, side='defender'),
                buff('spd_boost', 10, 2, 'defender'), buff('spa_boost', 50, enabled=False),
                buff('spa_boost', 100, 0)]
        totals, details = resolve_buffs(rows, 'spa', 'spd', {'attack_boost': .1})
        self.assertEqual(totals, {'attack_boost': .8, 'defense_reduction': .2, 'defense_boost': .2})
        self.assertEqual([d['applied'] for d in details], [True, True, False, True, True, False, False])
        physical, _ = resolve_buffs(rows, 'atk', 'def', {})
        self.assertEqual(physical['attack_boost'], 1.6)
        self.assertNotIn('defense_boost', physical)

    def test_power_and_final_multipliers(self):
        rows = [buff('power_flat', 10, 4), buff('power_flat', -5),
                buff('power_boost', 20, 3), buff('power_reduction', 10),
                buff('power_independent', 20), buff('power_independent', 50),
                buff('damage_boost', 20), buff('vulnerability', 30, side='defender'),
                buff('damage_reduction', 20, 2, 'defender'), buff('damage_reduction', 50, side='defender'),
                buff('power_boost', 100, side='defender'), buff('vulnerability', 100)]
        totals, details = resolve_buffs(rows, 'atk', 'def', {})
        self.assertEqual(totals['flat_power_bonus'], 35)
        self.assertEqual(totals['power_percent_bonus'], .5)
        self.assertEqual(totals['other_power_multiplier'], 1.8)
        self.assertEqual(totals['final_damage_multiplier'], .468)
        self.assertFalse(details[-1]['applied'])
        self.assertFalse(details[-2]['applied'])
        zero, _ = resolve_buffs([buff('damage_reduction', 100, side='defender')], 'atk', 'def', {})
        self.assertEqual(zero['final_damage_multiplier'], 0)
        self.assertEqual(resolve_buffs([], 'atk', 'def', {})[0], {})

    def test_input_validation(self):
        for change in ({'kind': 'unknown'}, {'value': float('nan')}, {'value': float('inf')},
                       {'value': -1}, {'value': True}, {'layers': -1}, {'layers': .5},
                       {'layers': True}, {'layers': 101}, {'side': 'other'}, {'enabled': 1},
                       {'kind': 'damage_reduction', 'value': 60, 'layers': 2},
                       {'kind': 'power_reduction', 'value': 101}, {'extra': 1}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                BuffInput(**({'kind': 'atk_boost', 'value': 20, 'side': 'attacker'} | change))


if __name__ == '__main__':
    unittest.main()
