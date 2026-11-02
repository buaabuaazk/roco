"""离线验证技能分页、去重、续采及数量限制。"""
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from collect_pets import Collector
from collect_skills import collect


def main():
    with tempfile.TemporaryDirectory() as directory:
        calls = []
        failed = {9}

        def request(command, **kwargs):
            p = parse_qs(urlparse(command[-1]).query)
            calls.append(p)
            if p['resource'] == ['skills']:
                first = p['page_no'] == ['1']
                data = {'ok': True, 'items': [{'skill_id': i} for i in ([7, 8] if first else [8, 9])],
                        'has_more': first}
            else:
                skill_id = int(p['skill_id'][0])
                if skill_id in failed:
                    raise subprocess.CalledProcessError(28, command)
                data = {'ok': True, 'data': {'skill_id': skill_id}}
            return subprocess.CompletedProcess(command, 0, json.dumps(data).encode())

        root = Path(directory)
        with patch('collect_pets.subprocess.run', request), patch('collect_pets.time.sleep'):
            assert collect(Collector(root=root)) == 1
            m = json.loads((root / 'skills_manifest.json').read_text())
            assert m['selected_ids'] == [7, 8, 9]
            assert m['status'] == 'partial'
            failed.clear()
            calls.clear()
            assert collect(Collector(root=root)) == 0
            assert len(calls) == 1 and calls[0]['skill_id'] == ['9']
            calls.clear()
            assert collect(Collector(root=root), limit=1) == 0
            m = json.loads((root / 'skills_manifest.json').read_text())
            assert m['selected_ids'] == [7] and not calls
            assert collect(Collector(root=root, refresh=True), ids=[9, 9]) == 0
            assert len(calls) == 1
            assert not (root / 'pets').exists()
    print('通过：独立技能分页、去重、失败后续采、limit 与 refresh。')


if __name__ == '__main__':
    main()
