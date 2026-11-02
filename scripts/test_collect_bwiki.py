import unittest

from collect_bwiki import extract


class BwikiExtractionTest(unittest.TestCase):
    def test_preserves_special_condition_and_branch_boundaries(self):
        html = '''<style>fake condition</style><div class="roco-panel" data-panel="pEvo">
        <div class="roco-evo-timeline" data-branch="1">
        <div class="roco-evo-name-main"><a>机械方方</a></div>
        <div class="roco-evo-conn-pill"><span></span><span>LV28 需在他人世界</span></div>
        <div class="roco-evo-name-main"><img src="a"><a>多彩方方</a></div></div>
        <div class="roco-evo-timeline" data-branch="2">
        <div class="roco-evo-name-main">另一分支</div></div></div>'''
        result = extract({'parse': {'title': '机械方方', 'pageid': 1, 'revid': 2, 'text': html}})
        self.assertEqual(result['evolution_branches'], [
            {'branch': '1', 'steps': [
                {'kind': 'pet', 'text': '机械方方'},
                {'kind': 'condition', 'text': 'LV28 需在他人世界'},
                {'kind': 'pet', 'text': '多彩方方'}]},
            {'branch': '2', 'steps': [{'kind': 'pet', 'text': '另一分支'}]}])
        self.assertNotIn('fake condition', result['page_text'])
        self.assertIn('LV28 需在他人世界', result['sections_text']['pEvo'])

    def test_rejects_error_or_changed_layout(self):
        with self.assertRaises(ValueError):
            extract({'error': {'code': 'missingtitle'}})
        with self.assertRaises(ValueError):
            extract({'parse': {'text': '<div>empty</div>'}})


if __name__ == '__main__':
    unittest.main()
