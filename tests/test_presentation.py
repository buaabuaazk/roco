import unittest
from copy import deepcopy

from roco_agent.presentation import model_result


class PresentationTests(unittest.TestCase):
    def test_skill_has_one_attribute_type_and_preserves_zero_and_variable_power(self):
        raw = {'status': 'ok', 'data': {
            'skill_id': 7, 'name': '样本', 'element_type': {'id': 3, 'name': '草'},
            'type': {'id': 3, 'name': '草'}, 'families': '草',
            'skill_type': {'id': 1, 'name': '物攻'}, 'damage_type': {'id': 2, 'name': '物攻'},
            'power': '80', 'cost': '0', 'description': '技能效果', 'icon': 'url'},
            'sources': [{'file': 'private-path', 'stale': True}]}
        original = deepcopy(raw)
        self.assertEqual(model_result('get_skill', raw), {'status': 'ok', 'data': {
            '名称': '样本', '属性': '草', '类型': '物攻', '威力': 80, '能耗': 0, '效果': '技能效果'}})
        self.assertEqual(raw, original)
        raw['data']['power'] = '随速度差变化'
        raw['data']['special_rule'] = {'condition': '额外条件'}
        view = model_result('get_skill', raw)['data']
        self.assertEqual(view['威力'], '随速度差变化')
        self.assertEqual(view['补充信息']['special_rule'], {'condition': '额外条件'})
        raw['data']['damage_type']['name'] = '魔攻'
        self.assertEqual(model_result('get_skill', raw)['data']['伤害类型'], '魔攻')

    def test_learning_preserves_bloodline_missing_detail_and_negative_membership(self):
        raw = {'status': 'partial', 'data': {'pet_id': 3001, 'name': '喵喵', 'count': 1,
            'items': [{'skill_id': 7, 'name': '星星撞击', 'source': 'blood', 'level': 15,
                       'bloodline_id': 1, 'bloodline_name': '普通系血脉',
                       'detail_status': 'detail_missing', 'detail': None}]}}
        view = model_result('get_pet_skills', raw)
        self.assertEqual(view['status'], 'partial')
        self.assertEqual(view['data'], {'精灵': '喵喵', '技能': [{
            '名称': '星星撞击', '学习方式': '血脉', '学习等级': 15,
            '血脉': '普通系血脉', '详情状态': 'detail_missing'}]})
        raw['data']['items'] = []
        raw['data']['can_learn_in_selected_scope'] = False
        self.assertIs(model_result('get_pet_skills', raw)['data']['当前筛选条件下可学习'], False)

    def test_family_deduplicates_conditions_and_keeps_branches_materials_and_extra_rules(self):
        feature = {'name': '氧循环', 'desc': '回复10%生命', 'skill_id': 200076}
        raw = {'status': 'ok', 'data': {'pet_id': 3001, 'name': '喵喵', 'section': 'family', 'value': {
            'family_id': 4, 'name': '喵喵进化链', 'members': [
                {'pet_id': 3001, 'name': '喵喵', 'feature': feature, 'display_order': 1},
                {'pet_id': 3025, 'name': '喵呜', 'previous_pet_id': 3001,
                 'level': 16, 'condition_level': 16, 'condition_summary': '等级达到 16',
                 'condition_texts': ['等级达到 16'], 'money': 0,
                 'evolution_description': '喵喵升级到16级后进化为喵呜。',
                 'items': [{'item_id': 100201, 'name': '魔法粉尘', 'count': 5}], 'feature': feature},
                {'pet_id': 5003, 'name': '分支形态', 'previous_pet_id': 3025,
                 'condition_texts': ['完成课题', '白天'], 'special_condition': '特殊前提',
                 'evolution_description': '在某地完成进化'}]}}}
        view = model_result('get_pet', raw)['data']['value']
        self.assertEqual(view['members'][1]['conditions'], {
            'level': 16, 'items': [{'name': '魔法粉尘', 'count': 5}], 'cost': 0})
        self.assertEqual(view['features'], {'氧循环': '回复10%生命'})
        self.assertEqual(view['members'][2]['previous_pet_id'], 3025)
        self.assertEqual(view['members'][2]['conditions'], {
            'other': ['完成课题', '白天'], 'description': '在某地完成进化'})
        self.assertEqual(view['members'][2]['extra'], {'special_condition': '特殊前提'})

    def test_pet_labels_replace_internal_type_and_feature_ids(self):
        raw = {'status': 'ok', 'data': {'pet_id': 3001, 'name': '喵喵',
            'types': [{'type_id': 3, 'name': '草'}], 'type_ids': [3], 'type_names': ['草'],
            'features': {'items': [{'name': '氧循环', 'skill_id': 200076, 'desc': '回复生命'}]},
            'available_sections': ['profile']}}
        view = model_result('get_pet', raw)['data']
        self.assertEqual(view['types'], ['草'])
        self.assertNotIn('type_ids', view)
        self.assertNotIn('type_names', view)
        self.assertNotIn('available_sections', view)
        self.assertNotIn('skill_id', view['features']['items'][0])


if __name__ == '__main__':
    unittest.main()
