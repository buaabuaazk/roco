import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from pack_bwiki_results import pack


class ResultPackageTest(unittest.TestCase):
    def test_only_current_complete_batch_is_packaged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / 'bwiki'
            (data / 'converted/pets').mkdir(parents=True)
            (data / 'modules').mkdir()
            (data / 'modules/response.json').write_text('{}')
            (data / 'converted/pets/1.json').write_text('{}')
            (data / 'converted/pets/2.json').write_text('{}')  # 旧批次遗留
            manifest = {'status': 'complete', 'pets': 1, 'skills': 0, 'features': 0,
                        'files': ['pets/1.json']}
            manifest_path = data / 'converted/manifest.json'
            manifest_path.write_text(json.dumps(manifest))
            output = root / 'return.zip'
            pack(data, output)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {'data/bwiki/converted/manifest.json',
                    'data/bwiki/converted/pets/1.json', 'data/bwiki/modules/response.json'})
                self.assertIsNone(archive.testzip())
            previous = output.read_bytes()
            for status, files in [('partial', ['pets/1.json']), ('complete', ['pets/missing.json']),
                                  ('complete', ['../outside.json'])]:
                manifest.update(status=status, files=files)
                manifest_path.write_text(json.dumps(manifest))
                with self.assertRaises((ValueError, FileNotFoundError)):
                    pack(data, output)
                self.assertEqual(output.read_bytes(), previous)


if __name__ == '__main__':
    unittest.main()
