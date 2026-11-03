"""运行方式：python -m roco_data --help。"""
import argparse
import json
import sqlite3

from .database import DATA_DIR, DEFAULT_DB, STATS, import_data
from .queries import RocoQueries, result
from .json_queries import GROUPS, JsonQueries, DEFAULT_JSON_DIR


def main():
    parser = argparse.ArgumentParser(description='Roco JSON 只读查询与可选 SQLite 建库')
    parser.add_argument('--db', help='显式指定时使用 SQLite 查询库')
    parser.add_argument('--json-dir', default=str(DEFAULT_JSON_DIR), help='BWIKI 正式 JSON 目录')
    commands = parser.add_subparsers(dest='command', required=True)
    importer = commands.add_parser('import', help='从现有 JSON 导入或更新查询快照')
    importer.add_argument('--data-dir', default=str(DATA_DIR), help='采集数据目录')
    commands.add_parser('stats', help='查看入库数量和详情缺失数量')
    for command in ('pets', 'skills'):
        search = commands.add_parser(command, help='按名称关键词检索')
        search.add_argument('query', nargs='?', default='')
        search.add_argument('--limit', type=int, default=20)
        if command == 'pets':
            search.add_argument('--type', dest='type_name', help='按属性名称筛选')
    pet = commands.add_parser('pet', help='按名称或 ID 查询精灵')
    pet.add_argument('identifier')
    pet.add_argument('--section', help='分区，例如 profile、family、features、acquisition、egg、stories')
    skill = commands.add_parser('skill', help='按名称或 ID 查询技能详情')
    skill.add_argument('identifier')
    relations = commands.add_parser('pet-skills', help='关联查询学习条件与技能详情')
    relations.add_argument('identifier')
    relations.add_argument('--source', choices=GROUPS)
    relations.add_argument('--max-level', type=int)
    relations.add_argument('--skill', help='指定技能名称或 ID，检查学习关系')
    compare = commands.add_parser('compare', help='按指定种族值比较精灵')
    compare.add_argument('identifiers', nargs='+')
    compare.add_argument('--stat', choices=STATS, default='speed')
    args = parser.parse_args()
    try:
        if args.command == 'import':
            answer = result('ok', import_data(args.data_dir, args.db or DEFAULT_DB))
        else:
            with (RocoQueries(args.db) if args.db else JsonQueries(args.json_dir)) as queries:
                if args.command == 'stats':
                    answer = queries.statistics()
                elif args.command == 'pets':
                    answer = queries.search_pets(args.query, args.type_name, args.limit)
                elif args.command == 'skills':
                    answer = queries.search_skills(args.query, args.limit)
                elif args.command == 'pet':
                    answer = queries.get_pet(args.identifier, args.section)
                elif args.command == 'skill':
                    answer = queries.get_skill(args.identifier)
                elif args.command == 'pet-skills':
                    answer = queries.get_pet_skills(args.identifier, args.source, args.max_level, args.skill)
                else:
                    answer = queries.compare_pets(args.identifiers, args.stat)
    except (OSError, ValueError, sqlite3.Error) as exc:
        answer = result('error', message=str(exc))
    print(json.dumps(answer, ensure_ascii=False, indent=4))
    return 0 if answer['status'] == 'ok' else 2


if __name__ == '__main__':
    raise SystemExit(main())
