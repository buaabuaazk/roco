import unittest

from check_bwiki_updates import compare_revisions


class RevisionCheckTest(unittest.TestCase):
    def test_changed_unchanged_and_unavailable_are_distinguished(self):
        def page(page_id, revision):
            return {'pageid': page_id, 'title': f'模块:{page_id}',
                    'revisions': [{'revid': revision, 'timestamp': '2026-11-03T00:00:00Z'}]}
        local = {'query': {'pages': [page(1, 10), page(2, 20)]}}
        current = {'query': {'pages': [page(2, 20), page(1, 11)]}}
        report = compare_revisions(local, current)
        self.assertEqual(report['status'], 'updates_available')
        self.assertEqual(report['unchanged_modules'], 1)
        self.assertEqual(report['changed_modules'][0]['local_revision'], 10)
        self.assertEqual(report['changed_modules'][0]['remote_revision'], 11)
        self.assertEqual(compare_revisions(local, local)['status'], 'up_to_date')
        partial = compare_revisions(local, {'query': {'pages': [page(1, 10)]}})
        self.assertEqual(partial['status'], 'partial')
        self.assertEqual(partial['unavailable_modules'], ['模块:2'])
        with self.assertRaises(ValueError):
            compare_revisions(local, {'error': {'code': 'maxlag'}})


if __name__ == '__main__':
    unittest.main()
