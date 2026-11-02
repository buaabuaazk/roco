"""离线核验喵喵采集结果：python3 roco/scripts/check_miaomiao.py。"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'data' / 'pets' / '3001'
load = lambda path: json.loads(path.read_text(encoding='utf-8'))
combined = load(root / 'combined.json')
manifest = load(root / 'manifest.json')
catalog = load(root / 'api_catalog.json')
sections = combined['sections']
expected = {r['section'] for r in catalog['resources']
            if r.get('id_param') == 'pet_id' and r.get('section')}
assert expected <= sections.keys(), expected - sections.keys()
assert not manifest['missing_sections']
assert all(r['status'] == 'ok' for r in manifest['requests'])
assert sections['base']['pet_id'] == combined['pet_id'] == 3001
stats = sections['profile']['attributes']
assert sum(v for k, v in stats.items() if k != 'sum') == stats['sum']
ids = {s['skill_id'] for group in ['level', 'machine', 'blood']
       for s in sections['skills'][group]}
assert ids == set(combined.get('skill_ids', combined.get('skill_detail_ids', [])))
for path in root.rglob('*.json'):
    data = load(path)
    assert path.read_text(encoding='utf-8') == json.dumps(data, ensure_ascii=False, indent=4) + '\n', path
print(f'核验通过：{len(expected)} 个资料分区，{len(ids)} 个技能关联，JSON 格式统一。')
