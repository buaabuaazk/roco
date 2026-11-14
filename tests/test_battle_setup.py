from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from roco_server.battle_setup import PetSetup, MatchupInput, panel, pet_skills, matchup, level_editable, pet_image_url, IMAGE_URLS


class BattleSetupTests(unittest.TestCase):
    def test_image_urls_follow_source_filename_and_fallback(self):
        pet = {'pet_id': 3433, 'profile': {'image': {'head': 'PetAvatar_3431.png', 'illustration': 'portrait.png'}}}
        with patch.dict(IMAGE_URLS, {'PetAvatar_3431.png': 'https://patchwiki.biligame.com/head.png',
                                   'portrait.png': 'https://patchwiki.biligame.com/portrait.png'}, clear=True):
            self.assertEqual(pet_image_url(pet), 'https://patchwiki.biligame.com/head.png')
            del IMAGE_URLS['PetAvatar_3431.png']
            self.assertEqual(pet_image_url(pet), 'https://patchwiki.biligame.com/portrait.png')
        self.assertIsNone(pet_image_url({'profile': {}}))

    def setUp(self):
        base = dict(hp=100, atk=128, spa=170, **{'def': 121}, spd=200, spe=100)
        self.queries = SimpleNamespace(features={}, skills={
            701: dict(skill_id=701, name='翼招式', category='攻击', damage_class='物攻', power=75, element='翼系', desc='造成物伤'),
            702: dict(skill_id=702, name='魔攻招式', category='攻击', damage_class='魔攻', power=100, element='草系', desc='造成魔伤'),
            703: dict(skill_id=703, name='非本宠技能', category='攻击', damage_class='物攻', power=50, element='火系')}, pets={})
        for key in (1, 2):
            self.queries.pets[key] = {'pet_id': key, 'title': f'精灵{key}', 'feature_id': 0,
                'profile': {'stats': deepcopy(base), 'types': ['翼系'] if key == 1 else ['草系']},
                'type_effectiveness': {'weak': [{'type': '翼系', 'multiplier': 2}], 'resist': []},
                'skills': {'level': [{'skill_id': 701, 'level': 1}], 'machine': [{'skill_id': 702}]}}

    def test_panel_formula_natures_and_current_hp(self):
        result = panel(self.queries, PetSetup(pet_id=1, ivs={'atk': 60}, hp_percent=50))
        self.assertEqual(result['stats']['atk'], 234)
        self.assertEqual(result['stats']['hp'], 340)
        self.assertEqual(result['current_hp'], 170)
        raised = panel(self.queries, PetSetup(pet_id=1, ivs={'atk': 60}, nature_plus='atk', nature_minus='spa'))
        self.assertEqual(raised['stats']['atk'], 271)
        self.assertEqual(raised['stats']['spa'], 227)
        self.assertEqual(result['ivs']['spe'], 0)
        self.assertEqual(result['ivs']['atk'], 60)
        partial = panel(self.queries, PetSetup(pet_id=1, ivs={'atk': 31}))
        self.assertEqual(partial['stats']['atk'], 218)

    def test_example_and_auto_physical_channel(self):
        body = MatchupInput(attacker=PetSetup(pet_id=1, ivs={'atk': 60}),
                            defender=PetSetup(pet_id=2, ivs={'def': 60}), skill_id=701,
                            modifiers={'flat_power_bonus': 20, 'power_percent_bonus': .5})
        result = matchup(self.queries, body)
        self.assertEqual(result['estimated_damage'], 332)
        self.assertEqual(result['inputs']['attack'], 234)
        self.assertEqual(result['inputs']['defense'], 226)
        self.assertEqual(result['inputs']['stab_multiplier'], 1.25)
        self.assertEqual(result['inputs']['type_multiplier'], 2)
        self.assertEqual(result['matchup']['channel'], '物攻 → 物防')
        from_buffs = matchup(self.queries, MatchupInput(attacker=body.attacker, defender=body.defender, skill_id=701,
            buffs=[{'kind': 'power_flat', 'side': 'attacker', 'value': 10, 'layers': 2},
                   {'kind': 'power_boost', 'side': 'attacker', 'value': 25, 'layers': 2},
                   {'kind': 'spa_boost', 'side': 'attacker', 'value': 100}]))
        self.assertEqual(from_buffs['estimated_damage'], 332)
        self.assertEqual(from_buffs['resolved_modifiers']['power_percent_bonus'], .5)
        self.assertFalse(from_buffs['buffs'][-1]['applied'])
        with self.assertRaises(ValidationError):
            MatchupInput(attacker=body.attacker, defender=body.defender, skill_id=701,
                         buffs=[{'kind': 'power_boost', 'side': 'attacker', 'value': 1}] * 33)

    def test_card_buffs_and_combo_only_on_combo_skills(self):
        body = MatchupInput(attacker=PetSetup(pet_id=1, buffs={'physical_attack': 30, 'magic_attack': 70, 'combo': 2, 'power': 30}),
                            defender=PetSetup(pet_id=2, buffs={'physical_defense': -20, 'magic_defense': 40, 'physical_attack': 90, 'combo': 4}), skill_id=701)
        plain = matchup(self.queries, body)
        self.assertEqual(plain['resolved_modifiers'], {'attack_boost': .3, 'defense_reduction': .2, 'flat_power_bonus': 30})
        self.assertEqual(plain['inputs']['flat_power_bonus'], 30)
        magical = matchup(self.queries, MatchupInput(attacker=body.attacker, defender=body.defender, skill_id=702))
        self.assertEqual(magical['resolved_modifiers'], {'attack_boost': .7, 'defense_boost': .4, 'flat_power_bonus': 30})
        self.assertEqual(plain['combo']['hits'], 1)
        self.assertFalse(plain['buffs'][-2]['applied'])
        self.assertFalse(plain['buffs'][-1]['applied'])
        self.queries.skills[701]['desc'] = '造成物伤，2连击，应对状态下连击数翻倍。'
        multi = matchup(self.queries, body)
        self.assertEqual(multi['combo']['base_hits'], 2)
        self.assertEqual(multi['combo']['hits'], 4)
        self.assertEqual(multi['estimated_damage'], plain['estimated_damage'] * 4)
        self.assertAlmostEqual(multi['damage_percent'], plain['damage_percent'] * 4)
        self.assertEqual(multi['steps'][-1]['label'], '连击总伤害')
        self.assertEqual(multi['estimated_ko'], multi['estimated_damage'] >= multi['matchup']['defender']['current_hp'])
        negative = matchup(self.queries, MatchupInput(attacker=PetSetup(pet_id=1, buffs={'combo': -10}),
                           defender=PetSetup(pet_id=2), skill_id=701))
        self.assertEqual(negative['combo']['hits'], 1)

    def test_fixed_training_nature_and_float32_rounding(self):
        defaults = panel(self.queries, PetSetup(pet_id=1))
        self.assertEqual((defaults['level'], defaults['stars'], defaults['growth']), (60, 5, 50))
        setup = dict(pet_id=1, ivs={'atk': 60}, nature_plus='atk', nature_minus='spa')
        raised = panel(self.queries, PetSetup(**setup))
        self.assertEqual(raised['stats']['atk'], 271)
        explicit = panel(self.queries, PetSetup(**setup, stars=5, growth=50))
        self.assertEqual(raised['stats'], explicit['stats'])
        # 半点取整结果仍包含固定成长50的加成。
        self.queries.pets[1]['profile']['stats'].update(atk=105, spa=115)
        boundary = panel(self.queries, PetSetup(pet_id=1))
        self.assertEqual(boundary['stats']['atk'], 175)
        self.assertEqual(boundary['stats']['spa'], 187)

    def test_magic_channel_combined_type_chart_and_override(self):
        self.queries.pets[2]['type_effectiveness']['weak'] = [{'type': '草系', 'multiplier': 3}]
        body = MatchupInput(attacker=PetSetup(pet_id=1), defender=PetSetup(pet_id=2),
                            skill_id=702, power_override=120)
        result = matchup(self.queries, body)
        self.assertEqual(result['inputs']['attack'], 247)
        self.assertEqual(result['inputs']['defense'], 280)
        self.assertEqual(result['inputs']['type_multiplier'], 3)
        self.assertEqual(result['inputs']['stab_multiplier'], 1)
        self.assertEqual(result['inputs']['base_power'], 120)
        self.assertTrue(result['matchup']['power_overridden'])
        self.queries.pets[1]['skills']['level'].append({'skill_id': 703, 'level': 61})
        self.assertNotIn(703, [row['skill_id'] for row in pet_skills(self.queries, 1)])
        with self.assertRaises(ValueError):
            matchup(self.queries, body.model_copy(update={'skill_id': 703}))
        with self.assertRaises(ValueError):
            matchup(self.queries, body.model_copy(update={'modifiers': {'attack': 999}}))

    def test_build_constraints_and_missing_data(self):
        for fields in ({'pet_id': True}, {'ivs': {'atk': True}}, {'ivs': {'atk': 61}},
                       {'ivs': {'atk': .5}}, {'ivs': {'bad': 1}},
                       {'ivs': {'hp': 1, 'atk': 1, 'def': 1, 'spa': 1}},
                       {'nature_plus': 'atk', 'nature_minus': 'atk'}, {'nature_plus': 'atk'},
                       {'hp_percent': 0}, {'hp_percent': float('nan')}, {'unknown': 1},
                       {'stars': 0}, {'stars': 4}, {'stars': -1}, {'stars': 11}, {'stars': True}, {'stars': 5.5},
                       {'growth': 0}, {'growth': 51}, {'growth': -1}, {'growth': 101}, {'growth': True}, {'growth': 50.5},
                       {'stars': 6, 'growth': 50}, {'growth': 49},
                       {'level': 0}, {'level': 101}, {'level': True}, {'level': 89.5}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                PetSetup(**({'pet_id': 1} | fields))
        with self.assertRaises(ValueError): panel(self.queries, PetSetup(pet_id=999))
        del self.queries.pets[1]['profile']['stats']['hp']
        with self.assertRaises(ValueError): panel(self.queries, PetSetup(pet_id=1))

    def test_family_levels_and_observed_247_damage(self):
        with self.assertRaises(ValueError):
            panel(self.queries, PetSetup(pet_id=1, level=89))
        for title in ('阿布', '冥古龙'):
            self.assertTrue(level_editable({'title': title}))
            self.assertTrue(level_editable({'title': '进化形态', 'evolution_branches': [{'chain': [{'name': title}]}]}))
        self.assertFalse(level_editable({'title': '喵喵'}))
        self.queries.pets[1]['profile'].update(types=['机械系', '火系'])
        self.queries.pets[1]['profile']['stats']['spa'] = 130
        self.queries.pets[2]['title'] = '冥古龙'
        self.queries.pets[2]['profile']['stats'].update(hp=118, spd=63)
        self.queries.pets[2]['type_effectiveness']['weak'] = [{'type': '幽系', 'multiplier': 2}]
        self.queries.skills[702]['element'] = '幽系'
        body = MatchupInput(attacker=PetSetup(pet_id=1), defender=PetSetup(pet_id=2, level=89, ivs={'hp': 60}), skill_id=702)
        result = matchup(self.queries, body)
        self.assertEqual(result['inputs']['attack'], 203)
        self.assertEqual(result['inputs']['defense'], 148)
        self.assertEqual(result['inputs']['level'], 60)
        self.assertEqual(result['matchup']['defender']['level'], 89)
        self.assertEqual(result['matchup']['defender']['stats']['hp'], 536)
        self.assertEqual(result['estimated_damage'], 247)
        self.queries.pets[1]['title'] = '阿布'
        higher = matchup(self.queries, body.model_copy(update={'attacker': PetSetup(pet_id=1, level=89)}))
        self.assertEqual(higher['inputs']['level'], 89)
        self.assertGreater(higher['estimated_damage'], result['estimated_damage'])


if __name__ == '__main__':
    unittest.main()
