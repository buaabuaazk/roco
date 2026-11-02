import unittest

from collect_bwiki_modules import parse_lua, visible_tables


class LuaDataTest(unittest.TestCase):
    def test_nested_literals_preserve_conditions(self):
        result = parse_lua('''-- comment
        return {pet={game_id=3200,name="机械方方",enabled=true,
        stats={atk=81},chain={{level=28,cond="需在他人世界"}}},
        manual={["喵喵"]={["喵呜"]=""}},text="a\\n\\\"b",rate=0.5}''')
        self.assertEqual(result['pet']['chain'][0], {'level': 28, 'cond': '需在他人世界'})
        self.assertEqual(result['manual']['喵喵']['喵呜'], '')
        self.assertEqual(result['text'], 'a\n"b')
        self.assertIs(result['pet']['enabled'], True)

    def test_rejects_code_and_unsupported_tables(self):
        for source in ('return os.execute("x")', 'return {} do_something()',
                       'return {1,a=2}', 'return {x="a" y=2}', 'return {x=3'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_lua(source)

    def test_visible_patch_replaces_learnset_and_preserves_raw(self):
        raw = {
            'VisibilityConfig': {'hidden_seasons': {'S5': True}, 's5_shiny_pets': {'pet': True},
                                 's5_topic_ids': {'new': True}},
            'Catalog': {'pet': {'stats': {'hp': 1}, 'has_shiny': True,
                                'image': {'shiny': 'new.png'},
                                'ecology': {'eggs': [{'is_shiny': True}, {'name': 'old'}]}}},
            'CatalogPatch': {'pet': {'stats': {'hp': 2}}},
            'Skills': {}, 'SkillsPatch': {},
            'Learnsets': {'learn': {'skill_stones': ['old', 'new']}},
            'LearnsetsPatch': {'learn': {'skill_stones': ['old']}},
            'Handbooks': {'book': {'topics': [{'progress_id': 'new'}, {'progress_id': 'old'}]}},
        }
        result = visible_tables(raw)
        self.assertEqual(result['Learnsets']['learn']['skill_stones'], ['old'])
        self.assertEqual(raw['Learnsets']['learn']['skill_stones'], ['old', 'new'])
        self.assertEqual(result['Catalog']['pet']['stats']['hp'], 2)
        self.assertFalse(result['Catalog']['pet']['has_shiny'])
        self.assertEqual(result['Catalog']['pet']['ecology']['eggs'], [{'name': 'old'}])
        self.assertEqual(result['Handbooks']['book']['topics'], [{'progress_id': 'old'}])
        raw['VisibilityConfig']['hidden_seasons']['S5'] = False
        with self.assertRaises(ValueError):
            visible_tables(raw)


if __name__ == '__main__':
    unittest.main()
