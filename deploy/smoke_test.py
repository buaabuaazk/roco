"""验证公网计算功能与后台接口隔离：python deploy/smoke_test.py http://SERVER_IP。"""
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def check(base):
    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        with urlopen(Request(base.rstrip('/') + path, data=data,
                             headers={'Content-Type': 'application/json'}), timeout=20) as response:
            return json.load(response)

    pets = request('/api/damage/pets')
    assert any(pet['pet_id'] == 3359 for pet in pets), '缺少爵士鹿数据'
    skills = request('/api/damage/pets/3359/skills')
    assert any(skill['skill_id'] == 7170220 for skill in skills), '缺少灵媒技能'
    result = request('/api/damage/matchup', {
        'attacker': {'pet_id': 3359, 'feature_entries': 2},
        'defender': {'pet_id': 3798}, 'skill_id': 7170220,
    })
    assert result['estimated_damage'] > 0, '伤害计算无结果'
    assert result['resolved_modifiers']['attack_boost'] == .6, '特性未生效'
    for path, body in (('/api/config', None), ('/api/sessions', None),
                       ('/api/sessions', {}), ('/api/data/update', {})):
        try:
            request(path, body)
        except HTTPError as error:
            assert error.code == 403, f'{path}预期403，实际{error.code}'
        else:
            raise AssertionError(f'{path}不应公开访问')
    print(f'PASS: {len(pets)} pets, damage={result["estimated_damage"]}, private APIs=403')


if __name__ == '__main__':
    check(sys.argv[1])
