"""离线检查精灵与技能分离、本地续采、刷新与失败恢复。"""
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from collect_pets import Collector


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        calls = []
        fail = False

        def request(command, **kwargs):
            params = parse_qs(urlparse(command[-1]).query)
            resource = params['resource'][0]
            pet_id = int(params['pet_id'][0])
            calls.append(resource)
            assert resource != 'skill-detail'
            if resource == 'pet-detail':
                data = {'ok': True, 'sections': {'base': {'pet_id': pet_id, 'name': '样本'},
                        'skills': {'level': [{'skill_id': 7, 'level': 5, 'power': '80'}],
                                   'machine': [{'skill_id': 7, 'desc': '效果'}],
                                   'blood': [{'skill_id': 8, 'level': 15, 'bloodline': {'id': 2}}]}}}
            elif resource == 'pet-appearance':
                data = {'ok': True, 'pet': {'pet_id': pet_id}}
            else:
                if fail:
                    raise subprocess.CalledProcessError(28, command)
                data = {'ok': True, 'data': {'items': []}}
            return subprocess.CompletedProcess(command, 0, json.dumps(data).encode())

        catalog = {'resources': [{'id_param': 'pet_id', 'section': 'skills', 'resource': 'pet-skills'},
                                 {'id_param': 'pet_id', 'section': 'stories', 'resource': 'pet-stories'}]}
        with patch('collect_pets.subprocess.run', request), patch('collect_pets.time.sleep'):
            collector = Collector(root=root)
            assert collector.collect(1, catalog)['status'] == 'complete'
            combined = json.loads((root / 'pets/1/combined.json').read_text())
            assert combined['skill_ids'] == [7, 8]
            skills = combined['sections']['skills']
            assert skills['level'] == [{'skill_id': 7, 'level': 5}]
            assert skills['machine'] == [{'skill_id': 7}]
            assert skills['blood'] == [{'skill_id': 8, 'level': 15, 'bloodline_id': 2}]
            assert not (root / 'skills').exists()
            raw = json.loads((root / 'pets/1/pet-detail.json').read_text())
            assert raw['sections']['skills']['level'][0]['power'] == '80'
            count = len(calls)
            assert collector.collect(1, catalog)['status'] == 'complete'
            assert len(calls) == count
            assert collector.collect(2, catalog)['status'] == 'complete'
            fail = True
            refreshed = Collector(root=root, refresh=True)
            assert refreshed.collect(1, catalog)['status'] == 'partial'
            fail = False
            assert refreshed.collect(1, catalog)['status'] == 'complete'
    print('通过：技能 ID 与学习条件、零技能详情请求、本地复用、刷新失败后补采。')


if __name__ == '__main__':
    main()
