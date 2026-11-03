import unittest

from crosscheck_bwiki import STAT_KEYS, identity_text, skill_compare


class CrosscheckTest(unittest.TestCase):
    def test_normalizes_representation_but_preserves_numeric_differences(self):
        rows = [{'技能名': '测试', '属性': '机械系', '类型': '变化',
                 '威力': '0', '耗能': '1', '效果描述': '回复 2 能量。'}]
        skills = [{'name': '测试', 'skill_id': 1, 'element': '机械系', 'category': '状态',
                   'energy': 1, 'desc': '回复2能量'}]
        self.assertEqual(skill_compare(rows, skills)['equal'], 1)
        skills[0]['energy'] = 2
        result = skill_compare(rows, skills)
        self.assertEqual(result['different'], 1)
        self.assertEqual(list(result['differences'][0]['fields']), ['energy'])
        self.assertEqual(skill_compare(rows, [])['missing_names'], ['测试'])
        self.assertEqual(skill_compare(rows, skills * 2)['ambiguous_names'], ['测试'])
        self.assertEqual(STAT_KEYS['spd'], 'spe')
        self.assertEqual(STAT_KEYS['sp_def'], 'spd')
        self.assertEqual(identity_text('权杖-Ⅴ'), identity_text('权杖-V'))


if __name__ == '__main__':
    unittest.main()
