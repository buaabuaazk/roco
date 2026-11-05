"""只读工具：规格、参数校验及固定注册表执行。"""
import json
import sqlite3
from copy import deepcopy

from .database import STATS
from .queries import result
from .json_queries import GROUPS

IDENTIFIER = {'type': ['string', 'integer'], 'minLength': 1,
              'minimum': 1, 'maximum': 9223372036854775807,
              'description': '对象的准确名称或数据源 ID；使用精灵 pet_id 或技能 skill_id。'}
SECTION_DESCRIPTIONS = {
    'base': '基础描述和属性',
    'profile': '种族值、身高体重、蛋组和属性克制',
    'features': '特性名称与效果',
    'family': '进化链、等级、特殊条件及首领信物',
    'acquisition': '获取途径、果实来源和活动记录',
    'ecology': '生态与获取资料，当前内容与 acquisition 相同',
    'egg': '性别比例、蛋重范围和特殊精灵蛋',
    'fruit': '精灵果实及其获取来源',
    'handbook': '所属图鉴、图鉴课题及奖励',
    'ride': '骑乘和同乘能力',
    'skills': '技能 ID 与学习条件；查询具体效果或学习资格用 get_pet_skills',
    'history': '历次版本中的资料变化',
    'training_reference': '玩家在大世界和 PVP 中的技能、性格、血脉及天分使用统计',
}
SECTIONS = tuple(SECTION_DESCRIPTIONS)


def specification(name, description, properties, required=()):
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties,
                       'required': list(required), 'additionalProperties': False}}}


TOOL_DEFINITIONS = [
    specification('search_pets',
                  '按名称或属性寻找精灵，优先精确匹配，未命中时再按名称关键词搜索。唯一匹配返回精灵ID；多匹配返回名称与ID列表；无匹配返回“未找到”。'
                  'has_more为true时结果受数量限制，可增加limit或缩小关键词。再按ID查询资料。',
                  {'query': {'type': 'string', 'description': '名称关键词；省略时列出精灵。'},
                   'type_name': {'type': 'string', 'minLength': 1, 'description': '属性名称，例如草、水、火。'},
                   'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100,
                             'description': '最多返回数量，默认20。'}}),
    specification('get_pet',
                  '查询精灵概览或指定资料分区，依据 section 的用途说明选择。',
                  {'identifier': IDENTIFIER,
                   'section': {'type': 'string', 'enum': list(SECTIONS),
                               'description': '省略时返回名称、属性、种族值和特性概览。分区用途：'
                                   + '；'.join(f'{key}：{value}' for key, value in SECTION_DESCRIPTIONS.items())
                                   + '。'}}, ('identifier',)),
    specification('get_skill',
                  '按技能准确名称或skill_id查询属性、威力、能耗及效果。详情缺失时返回detail_missing。',
                  {'identifier': IDENTIFIER}, ('identifier',)),
    specification('get_pet_skills',
                  '查询精灵可学习技能并关联详情，或核对能否学会某技能。level为升级，machine为技能石，blood为血脉，legendary为传说技能。'
                  '保留学习等级及血脉条件；null表示该项条件缺少记录。详情缺失仍保留已知学习关系。',
                  {'identifier': IDENTIFIER,
                   'source': {'type': 'string', 'enum': list(GROUPS), 'description': '省略时查询全部学习来源。'},
                   'max_level': {'type': 'integer', 'minimum': 1, 'maximum': 9223372036854775807,
                                 'description': '学习等级上限（含该等级），单独使用时筛选升级技能。'},
                   'skill': {**IDENTIFIER, 'description': '指定技能名称或ID核对学习资格；省略时列出技能。'}},
                  ('identifier',)),
    specification('get_skill_pets',
                  '按技能名称或skill_id反查哪些精灵能学会该技能，一次返回精灵列表及各自的学习来源、等级和条件。'
                  '用于“哪些精灵能学丰饶”等问题。has_more为true时用next_offset继续查询。',
                  {'identifier': {**IDENTIFIER, 'description': '技能准确名称或游戏技能 ID，例如丰饶。'},
                   'source': {'type': 'string', 'enum': list(GROUPS),
                              'description': '可选学习来源：level升级、machine技能石、blood血脉、legendary传说；省略查询全部。'},
                   'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100,
                             'description': '每页精灵数量，默认100；同一精灵的多种学习方式合并返回。'},
                   'offset': {'type': 'integer', 'minimum': 0,
                              'description': '分页起点，默认0；下一页使用返回的next_offset。'}}, ('identifier',)),
    specification('compare_pets',
                  '比较2至10只精灵的一项种族值并降序排序；两只时同时返回差值。结果描述种族值层面的差异。',
                  {'identifiers': {'type': 'array', 'items': IDENTIFIER, 'minItems': 2, 'maxItems': 10},
                   'stat': {'type': 'string', 'enum': list(STATS),
                            'description': 'hp生命、physical_attack物攻、physical_defense物防、magic_attack魔攻、'
                                           'magic_defense魔防、speed速度（默认）、sum总和。'}}, ('identifiers',)),
]


def validate_argument(value, schema, path='arguments'):
    """只校验本模块工具规格使用的 JSON Schema 子集。"""
    types = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
    actual = {str: 'string', int: 'integer', dict: 'object', list: 'array'}.get(type(value))
    if actual not in types:
        raise ValueError(f'{path} 类型应为 {"/".join(types)}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path} 可选值为 {schema["enum"]}')
    if actual == 'object':
        properties = schema['properties']
        if set(value) - set(properties):
            raise ValueError(f'{path} 含未定义参数')
        if set(schema.get('required', [])) - set(value):
            raise ValueError(f'{path} 缺少必填参数')
        for key, item in value.items():
            validate_argument(item, properties[key], f'{path}.{key}')
    elif actual == 'integer':
        if not schema.get('minimum', -9223372036854775808) <= value <= schema.get('maximum', 9223372036854775807):
            raise ValueError(f'{path} 数值超出范围')
    elif actual == 'string':
        if len(value.strip()) < schema.get('minLength', 0):
            raise ValueError(f'{path} 应提供有效文本')
    elif actual == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
            raise ValueError(f'{path} 元素数量超出范围')
        for index, item in enumerate(value):
            validate_argument(item, schema['items'], f'{path}[{index}]')


class RocoTools:
    def __init__(self, queries):
        self._handlers = {
            'search_pets': queries.search_pets,
            'get_pet': queries.get_pet,
            'get_skill': queries.get_skill,
            'get_pet_skills': queries.get_pet_skills,
            'get_skill_pets': queries.get_skill_pets,
            'compare_pets': queries.compare_pets,
        }
        self._schemas = {t['function']['name']: t['function']['parameters'] for t in TOOL_DEFINITIONS}

    @property
    def definitions(self):
        """可作为 Chat Completions 风格请求的 tools 参数。"""
        return deepcopy(TOOL_DEFINITIONS)

    def execute(self, name, arguments):
        """接收模型的工具名称及 JSON 参数字符串/字典，返回结构化查询结果。"""
        if not isinstance(name, str) or name not in self._handlers:
            return result('unknown_tool', message='请使用已注册的查询工具')
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            validate_argument(arguments, self._schemas[name])
        except (ValueError, TypeError, RecursionError) as exc:
            return result('invalid_argument', message=str(exc))
        try:
            return self._handlers[name](**arguments)
        except (sqlite3.Error, OSError, ValueError):
            return result('tool_error', message='查询执行失败，请检查本地资料文件')
