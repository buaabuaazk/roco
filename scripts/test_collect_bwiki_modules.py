import unittest

from collect_bwiki_modules import (parse_lua, visible_tables, evolution_edges, convert_pet,
                                  select_pets, validate_rules, RULE_REVISIONS)


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

    def test_manual_condition_priority_and_empty_override(self):
        start = {'id': 'a', 'title': '甲'}
        end = {'id': 'b', 'title': '乙', 'level': 28, 'cond': '旧条件'}
        tables = {'Catalog': {'a': {'game_id': 1}, 'b': {'game_id': 2}},
                  'EvolutionConditions': {'1': {'2': ''}, 'a': {'b': '低优先级'}}}
        branches = [{'name': '分支', 'chain': [start, end], 'lord_branches': [
            {'id': 'c', 'title': '丙', 'cond': '首领化', 'item': '信物'}]}]
        edges = evolution_edges(tables, branches)[0]['transitions']
        self.assertEqual(edges[0]['conditions'], {'level': 28, 'special': ''})
        self.assertEqual(edges[0]['special_condition_source'], 'manual')
        self.assertEqual(edges[1]['from_wiki_id'], 'b')
        self.assertEqual(edges[1]['conditions']['item'], '信物')
        self.assertIsNone(edges[1]['to_pet_id'])
        tables['EvolutionConditions'] = {}
        self.assertEqual(evolution_edges(tables, branches)[0]['transitions'][0]['conditions']['special'], '旧条件')

    def test_separate_skill_references_preserve_legendary_requirement(self):
        pet = {'id': 'pet', 'game_id': 3200, 'name': '甲', 'title': '甲',
               'learnset_id': 'learn', 'feature_skill_id': 'feature',
               'evolution_id': 'family', 'handbook_id': 'book'}
        tables = {'Catalog': {'pet': pet}, 'Skills': {'feature': {'game_id': 10},
                   'attack': {'game_id': 20}}, 'Learnsets': {'learn': {
                       'feature_skill': 'feature', 'native_skills': [{'level': 5, 'skill': 'attack'}],
                       'skill_stones': ['missing'], 'blood_skills': [],
                       'legendary': {'skill': 'attack', 'requires': '指定形态'}}},
                  'Evolutions': {'family': []}, 'EvolutionConditions': {}, 'Handbooks': {'book': {}},
                  'Types': {}, 'TrainingReference': {'pets': {}}, 'History': {'pets': {}}}
        result = convert_pet(tables, pet)
        self.assertEqual(result['skills']['level'][0]['skill_id'], 20)
        self.assertEqual(result['skills']['level'][0]['level'], 5)
        self.assertNotIn('skill_detail', result['skills']['level'][0])
        self.assertEqual(result['skills']['legendary'][0]['requires'], '指定形态')
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['missing_skill_references'], ['missing'])

    def test_batch_selection_uses_game_ids_and_full_titles(self):
        catalog = {'a': {'game_id': 2, 'name': '甲', 'title': '甲（特殊形态）'},
                   'b': {'game_id': 1, 'name': '甲', 'title': '甲'}}
        self.assertEqual([p['game_id'] for p in select_pets(catalog, ['甲'], [2])], [1, 2])
        self.assertEqual(select_pets(catalog, [], [], True, 1)[0]['game_id'], 1)
        with self.assertRaises(ValueError):
            select_pets(catalog, [], [99])

    def test_rule_revision_change_requires_review(self):
        rows = [{'title': title, 'revision_id': revision} for title, revision in RULE_REVISIONS.items()]
        validate_rules(rows)
        rows[0]['revision_id'] += 1
        with self.assertRaises(ValueError):
            validate_rules(rows)
        with self.assertRaises(ValueError):
            validate_rules([])



class SeasonShardTest(unittest.TestCase):
    def test_decode_and_restored_merge_without_legacy_patch(self):
        from collect_bwiki_modules import decode_shard, season_tables
        season = {'codec': 'dragon-tuples-1', 'namespace': 'test'}
        def pack(value):
            fields = []
            def encode(row):
                if isinstance(row, dict):
                    pairs = []
                    for key, item in row.items():
                        if key not in fields: fields.append(key)
                        pairs.append([fields.index(key) + 1, encode(item)])
                    return [1, pairs]
                if isinstance(row, list): return [2, [encode(item) for item in row]]
                return row
            payload = encode(value)
            return ['dragon-tuples-1', fields, payload]
        sample = {'a': {'nested': [1, '值', False]}}
        self.assertEqual(decode_shard(pack(sample), season), sample)
        with self.assertRaises(ValueError): decode_shard(['other', [], []], season)
        tables = {'SeasonConfig': {'view_namespace': '精灵图鉴/S5'},
                  'SeasonManifest': {'seasons': [season]},
                  'VisibilityConfig': {'withheld_titles': {'撤下': True}},
                  'Catalog': {'old': {'title': '原有', 'siblings': []}},
                  'Skills': {}, 'Evolutions': {'new': [1]}, 'SkillStoneTopics': {'x': [1]},
                  'History': {'versions': {'old': 1}, 'pets': {}}}
        shards = {'Roster': {'new': {'title': '新增', 'siblings': ['old', 'hidden']}, 'hidden': {'title': '撤下'}},
                  'Arts': {'a': 1}, 'Gifts': {'b': 2},
                  'Aux': {'History': {'versions': {'new': 2}}, 'LegacyEvolutionAliases': {'old': 'new'},
                          'LegacyStoneTopics': {'x': [2]}}, 'Links': {}}
        for name, value in shards.items(): tables['SeasonShard:模块:test/' + name] = pack(value)
        result = season_tables(tables)
        self.assertEqual(set(result['Catalog']), {'old', 'new'})
        self.assertEqual(result['Catalog']['new']['siblings'], ['old'])
        self.assertEqual(result['History']['versions'], {'old': 1, 'new': 2})
        self.assertEqual(result['SkillStoneTopics']['x'], [1, 2])
        self.assertEqual(result['Evolutions']['old'], [1])
        self.assertNotIn('new', tables['Catalog'])


if __name__ == '__main__':
    unittest.main()
