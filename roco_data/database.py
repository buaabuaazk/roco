"""从采集 JSON 生成 SQLite 快照；一次事务提交，保留完整来源。"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
DEFAULT_DB = DATA_DIR / 'roco.db'
STATS = ('hp', 'physical_attack', 'physical_defense', 'magic_attack', 'magic_defense', 'speed', 'sum')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS pets (
    pet_id INTEGER PRIMARY KEY, name TEXT NOT NULL, handbook_no TEXT,
    hp INTEGER, physical_attack INTEGER, physical_defense INTEGER,
    magic_attack INTEGER, magic_defense INTEGER, speed INTEGER, stat_total INTEGER,
    sections_json TEXT NOT NULL, sources_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS pets_name ON pets(name);
CREATE TABLE IF NOT EXISTS pet_types (
    pet_id INTEGER NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
    type_id INTEGER NOT NULL, name TEXT NOT NULL,
    PRIMARY KEY (pet_id, type_id)
);
CREATE TABLE IF NOT EXISTS skills (
    skill_id INTEGER PRIMARY KEY, name TEXT,
    catalog_json TEXT, detail_json TEXT, sources_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS skills_name ON skills(name);
CREATE TABLE IF NOT EXISTS pet_skills (
    pet_id INTEGER NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK(source IN ('level', 'machine', 'blood')),
    position INTEGER NOT NULL,
    skill_id INTEGER NOT NULL REFERENCES skills(skill_id),
    level INTEGER, bloodline_id INTEGER, bloodline_name TEXT,
    PRIMARY KEY (pet_id, source, position)
);
CREATE INDEX IF NOT EXISTS pet_skills_skill ON pet_skills(skill_id);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
'''


def encode(data):
    return json.dumps(data, ensure_ascii=False)


def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'读取 JSON 失败：{path}: {exc}') from exc


def positive_id(value):
    if type(value) is not int or not 1 <= value <= 9223372036854775807:
        raise ValueError(f'ID 应为 64 位正整数：{value!r}')
    return value


def source_info(path, response, root):
    return {'file': path.relative_to(root).as_posix(),
            **{k: response[k] for k in ('source', 'updated_at', 'stale', 'warning') if k in response}}


def import_data(data_dir=DATA_DIR, db_path=DEFAULT_DB):
    """用当前 JSON 重建逻辑快照。失败时回滚，JSON 原文件保持原样。"""
    root, target = Path(data_dir).resolve(), Path(db_path).resolve()
    pet_files = sorted((root / 'pets').glob('*/combined.json'))
    detail_files = sorted((root / 'skills').glob('*.json'))
    list_files = sorted((root / 'lists').glob('skills_*.json'))
    if not (pet_files or detail_files or list_files):
        raise ValueError(f'{root} 下没有可导入的精灵或技能资料')
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=30)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA journal_mode=WAL')
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            raise ValueError(f'数据库版本 {version} 与当前程序不兼容')
        conn.executescript(SCHEMA)
        with conn:
            conn.execute('DELETE FROM pet_skills')
            conn.execute('DELETE FROM pet_types')
            conn.execute('DELETE FROM pets')
            conn.execute('DELETE FROM skills')
            for path in list_files:
                response = load(path)
                if response.get('ok') is not True or not isinstance(response.get('items'), list):
                    raise ValueError(f'技能列表格式异常：{path}')
                for item in response['items']:
                    skill_id = positive_id(item['skill_id'])
                    if not isinstance(item.get('name'), str) or not item['name'].strip():
                        raise ValueError(f'技能名称异常：{path} / {skill_id}')
                    conn.execute('''INSERT INTO skills VALUES (?, ?, ?, NULL, ?)
                        ON CONFLICT(skill_id) DO UPDATE SET name=excluded.name,
                        catalog_json=excluded.catalog_json, sources_json=excluded.sources_json''',
                                 (skill_id, item['name'], encode(item), encode([source_info(path, response, root)])))
            for path in detail_files:
                response = load(path)
                detail = response.get('data')
                if response.get('ok') is not True or not isinstance(detail, dict):
                    raise ValueError(f'技能详情格式异常：{path}')
                skill_id = positive_id(detail['skill_id'])
                if str(skill_id) != path.stem or not isinstance(detail.get('name'), str) or not detail['name'].strip():
                    raise ValueError(f'技能 ID 或名称异常：{path}')
                old = conn.execute('SELECT sources_json FROM skills WHERE skill_id=?', (skill_id,)).fetchone()
                sources = json.loads(old[0]) if old else []
                sources.append(source_info(path, response, root))
                conn.execute('''INSERT INTO skills VALUES (?, ?, NULL, ?, ?)
                    ON CONFLICT(skill_id) DO UPDATE SET name=excluded.name,
                    detail_json=excluded.detail_json, sources_json=excluded.sources_json''',
                             (skill_id, detail['name'], encode(detail), encode(sources)))
            for path in pet_files:
                pet = load(path)
                pet_id = positive_id(pet['pet_id'])
                if str(pet_id) != path.parent.name:
                    raise ValueError(f'精灵 ID 与目录不一致：{path}')
                sections = pet['sections']
                if not isinstance(sections, dict):
                    raise ValueError(f'精灵分区格式异常：{path}')
                base = sections.get('base', {})
                if base.get('pet_id') != pet_id or not isinstance(pet.get('name'), str) or not pet['name'].strip():
                    raise ValueError(f'精灵基础资料异常：{path}')
                stats = sections.get('profile', {}).get('attributes', {})
                if any(type(v) is not int or v < 0 for v in stats.values()):
                    raise ValueError(f'种族值格式异常：{path}')
                if all(k in stats for k in STATS) and sum(stats[k] for k in STATS[:-1]) != stats['sum']:
                    raise ValueError(f'种族值总和不一致：{path}')
                sources, bloodline_names = [], {}
                for raw_path in sorted(path.parent.glob('pet-*.json')):
                    response = load(raw_path)
                    if response.get('ok') is not True:
                        raise ValueError(f'精灵原始响应异常：{raw_path}')
                    info = source_info(raw_path, response, root)
                    info['section'] = response.get('resource', raw_path.stem)
                    sources.append(info)
                    raw_skills = (response.get('sections', {}).get('skills', {})
                                  if raw_path.stem == 'pet-detail' else
                                  response.get('data', {}) if raw_path.stem == 'pet-skills' else {})
                    for item in raw_skills.get('blood', []):
                        blood = item.get('bloodline', {})
                        if blood.get('id') and blood.get('name'):
                            bloodline_names[blood['id']] = blood['name']
                conn.execute('INSERT INTO pets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (pet_id, pet['name'], base.get('handbook_no'),
                              *(stats.get(k) for k in STATS), encode(sections), encode(sources)))
                for element in base.get('types', sections.get('profile', {}).get('types', [])):
                    conn.execute('INSERT INTO pet_types VALUES (?, ?, ?)',
                                 (pet_id, positive_id(element['id']), element['name']))
                for group in ('level', 'machine', 'blood'):
                    for position, item in enumerate(sections.get('skills', {}).get(group, [])):
                        skill_id = positive_id(item['skill_id'])
                        level = item.get('level')
                        bloodline_id = item.get('bloodline_id', item.get('bloodline', {}).get('id'))
                        if level is not None and (type(level) is not int or level < 1):
                            raise ValueError(f'学习等级异常：{path} / {skill_id}')
                        if bloodline_id is not None:
                            positive_id(bloodline_id)
                        conn.execute('INSERT OR IGNORE INTO skills VALUES (?, NULL, NULL, NULL, ?)',
                                     (skill_id, encode([])))
                        conn.execute('INSERT INTO pet_skills VALUES (?, ?, ?, ?, ?, ?, ?)',
                                     (pet_id, group, position, skill_id, level, bloodline_id,
                                      bloodline_names.get(bloodline_id)))
            report = {'imported_at': datetime.now(timezone.utc).isoformat(),
                      'schema_version': 1,
                      'pets': conn.execute('SELECT count(*) FROM pets').fetchone()[0],
                      'skills_with_details': conn.execute('SELECT count(*) FROM skills WHERE detail_json IS NOT NULL').fetchone()[0],
                      'skills_known': conn.execute('SELECT count(*) FROM skills').fetchone()[0],
                      'learning_relations': conn.execute('SELECT count(*) FROM pet_skills').fetchone()[0],
                      'relations_missing_detail': conn.execute('''SELECT count(*) FROM pet_skills p
                          JOIN skills s ON s.skill_id=p.skill_id WHERE s.detail_json IS NULL''').fetchone()[0]}
            conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?)', ('import', encode(report)))
            conn.execute('PRAGMA user_version=1')
        return report
    except (KeyError, TypeError) as exc:
        raise ValueError(f'JSON 字段格式异常：{exc}') from exc
    finally:
        conn.close()
