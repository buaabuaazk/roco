from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from roco_server.app import VisitInput
from roco_server.visits import Visits


class VisitTests(unittest.TestCase):
    def test_daily_dedup_totals_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'visits.db'
            visits = Visits(path)
            with patch.object(Visits, 'today', return_value=date(2026, 11, 15)):
                for visitor in ('a' * 32, 'a' * 32, 'b' * 32, None):
                    visits.record(visitor)
                stats = Visits(path).snapshot()
                self.assertEqual((stats['total_pv'], stats['today_pv'], stats['today_uv']), (4, 4, 2))
                self.assertEqual(len(stats['days']), 7)
                self.assertEqual(stats['days'][-1], {'day': '2026-11-15', 'pv': 4, 'uv': 2})
            with patch.object(Visits, 'today', return_value=date(2026, 11, 16)):
                visits.record('a' * 32)
                stats = visits.snapshot()
                self.assertEqual((stats['total_pv'], stats['today_pv'], stats['today_uv']), (5, 1, 1))
            with sqlite3.connect(path) as connection:
                hashes = [row[0] for row in connection.execute('SELECT browser FROM visitors')]
            self.assertEqual(len(set(hashes)), 3)
            self.assertNotIn('a' * 32, hashes)

    def test_concurrent_requests_keep_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            visits = Visits(Path(directory) / 'visits.db')
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(visits.record, ['a' * 32] * 32))
            stats = visits.snapshot()
            self.assertEqual((stats['today_pv'], stats['today_uv']), (32, 1))

    def test_browser_identifier_validation(self):
        self.assertIsNone(VisitInput().visitor_id)
        self.assertEqual(VisitInput(visitor_id='a' * 32).visitor_id, 'a' * 32)
        for value in ('', 'a' * 33, 'x' * 32, 123, {'ip': '127.0.0.1'}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                VisitInput(visitor_id=value)


if __name__ == '__main__':
    unittest.main()
