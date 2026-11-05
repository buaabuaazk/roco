import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from roco_server.data_updates import DataUpdates
from roco_server.service import BusyError, SessionManager
from roco_data import DEFAULT_JSON_DIR


class DataUpdateTests(unittest.TestCase):
    def wait(self, updates):
        deadline = time.monotonic() + 15
        while updates.snapshot()['busy']:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.02)
        return updates.snapshot()

    def test_staged_success_network_failure_and_reload_rollback(self):
        raw = json.loads((DEFAULT_JSON_DIR.parent / 'modules/response.json').read_text())
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            shutil.copytree(DEFAULT_JSON_DIR, root / 'converted')
            shutil.copytree(DEFAULT_JSON_DIR.parent / 'modules', root / 'modules')
            manager = SessionManager(root / 'converted', root / 'logs')
            updates = DataUpdates(manager)
            gate, started = threading.Event(), threading.Event()
            def fetch():
                started.set(); gate.wait(3)
                return raw, {'fetched_at': 'test'}
            with patch('roco_server.data_updates.fetch_modules', side_effect=fetch):
                updates.start('update'); self.assertTrue(started.wait(2))
                with self.assertRaises(BusyError): updates.start('check')
                session = manager.create()
                with self.assertRaises(BusyError): manager.start(session['id'], 'test')
                gate.set()
                status = self.wait(updates)
            self.assertIsNone(status['error'])
            self.assertEqual(json.loads((root / 'converted/manifest.json').read_text())['source'], {'fetched_at': 'test'})
            self.assertFalse(manager.data_updating)
            installed = (root / 'converted/manifest.json').read_bytes()
            with patch('roco_server.data_updates.fetch_modules', side_effect=ValueError('网络失败')):
                updates.start('update'); self.assertIn('网络失败', self.wait(updates)['error'])
            self.assertEqual((root / 'converted/manifest.json').read_bytes(), installed)
            invalid = json.loads(json.dumps(raw))
            next(p for p in invalid['query']['pages'] if p['title'] == '模块:ContentVisibility')['revisions'][0]['revid'] = 99999
            with patch('roco_server.data_updates.fetch_modules', return_value=(invalid, {})):
                updates.start('update'); self.assertIn('展示规则修订已变化', self.wait(updates)['error'])
            self.assertEqual((root / 'converted/manifest.json').read_bytes(), installed)
            with patch('roco_server.data_updates.fetch_modules', return_value=(raw, {})), patch.object(manager, 'reload_data', side_effect=ValueError('加载失败')):
                updates.start('update'); self.assertIn('加载失败', self.wait(updates)['error'])
            self.assertEqual((root / 'converted/manifest.json').read_bytes(), installed)
            self.assertTrue((root / 'modules/response.json').exists())
            self.assertFalse(list(root.glob('.update-*')))
            manager.close()

    def test_check_failure_and_persistence(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manager = SessionManager(log_dir=root / 'logs')
            updates = DataUpdates(manager); updates.root = root
            report = {'status': 'updates_available', 'changed_modules': [{'title': 'test'}]}
            with patch('roco_server.data_updates.check_updates', return_value=report):
                updates.start('check'); self.assertEqual(self.wait(updates)['report'], report)
            self.assertEqual(json.loads((root / 'update_status.json').read_text())['report'], report)
            with patch('roco_server.data_updates.check_updates', side_effect=ValueError('限流')):
                updates.start('check'); self.assertIn('限流', self.wait(updates)['error'])
            manager.close()


if __name__ == '__main__':
    unittest.main()
