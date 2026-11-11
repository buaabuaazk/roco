"""按已记录的社区规则估算单次伤害；使用玩家提供的实际能力值。"""
from decimal import Decimal, ROUND_HALF_UP, localcontext
import math
from pathlib import Path

FORMULA_FILE = Path(__file__).resolve().parents[1] / 'data/mechanics/damage_formula.json'


def field(description, default=None, minimum=0, maximum=100):
    value = {'type': 'number', 'minimum': minimum, 'maximum': maximum, 'description': description}
    if default is not None:
        value['default'] = default
    return value


DAMAGE_PARAMETERS = {
    'attack': field('强化前实际物攻或魔攻，由玩家提供，不能用种族值代替。', minimum=1, maximum=1000000),
    'defense': field('强化前实际物防或魔防，与技能伤害通道对应，由玩家提供。', minimum=1, maximum=1000000),
    'base_power': field('本次技能的基础威力；变威力、固定伤害及特殊结算需人工核对。', maximum=100000),
    'level': {**field('攻击方等级，默认60。', 60, 1, 100), 'type': 'integer'},
    'flat_power_bonus': field('固定威力加成，可负数。', 0, -100000, 100000),
    'power_percent_bonus': field('本次技能威力百分比合计，小数表示，如50%填0.5。', 0, -1, 10),
    'stab_multiplier': field('本系倍率，默认1；社区规则本系加成为1.25，确认本系后填写。', 1, 0, 10),
    'type_multiplier': field('属性克制合计倍率，默认1；免疫填0。', 1, 0, 16),
    'attack_boost': field('攻击提升比例，如100%填1。', 0, 0, 10),
    'attack_reduction': field('攻击降低比例，如40%填0.4。', 0, 0, 10),
    'defense_boost': field('防御提升比例。', 0, 0, 10),
    'defense_reduction': field('防御降低比例。', 0, 0, 10),
    'other_power_multiplier': field('其他威力乘区的合计倍率。', 1, 0, 100),
    'final_damage_multiplier': field('减伤及条件最终乘区的合计倍率；减伤70%填0.3。', 1, 0, 100),
    'defender_hp': field('可选：防御方当前生命，用于估算伤害占比。', minimum=1, maximum=1000000000),
}
DAMAGE_REQUIRED = ('attack', 'defense', 'base_power')


def calculate_damage(**parameters):
    unknown = set(parameters) - DAMAGE_PARAMETERS.keys()
    if unknown or set(DAMAGE_REQUIRED) - parameters.keys():
        raise ValueError('请提供实际攻击、实际防御、基础威力，并使用已定义的参数。')
    values = {}
    for key, spec in DAMAGE_PARAMETERS.items():
        value = parameters.get(key, spec.get('default'))
        if value is None and key == 'defender_hp':
            continue
        if (type(value) not in (int, float) or spec['type'] == 'integer' and type(value) is not int
                or not spec['minimum'] <= value <= spec['maximum']
                or isinstance(value, float) and not math.isfinite(value)):
            raise ValueError(f'{key} 应为 {spec["minimum"]}～{spec["maximum"]} 的有限数值')
        values[key] = Decimal(str(value))
    steps = []

    def record(label, expression, value):
        steps.append({'label': label, 'expression': expression, 'value': float(value)})
        return value

    def half_up(value):
        return value.quantize(Decimal(1), rounding=ROUND_HALF_UP)

    with localcontext() as context:
        context.prec = 40
        p = values
        effective = record('有效威力', '(基础威力 + 固定加成) × (1 + 威力百分比合计)，最低为0',
                           max(Decimal(0), (p['base_power'] + p['flat_power_bonus']) * (1 + p['power_percent_bonus'])))
        stage = record('攻防强化倍率', '(1 + 攻击提升 + 防御降低) ÷ (1 + 攻击降低 + 防御提升)',
                       (1 + p['attack_boost'] + p['defense_reduction']) /
                       (1 + p['attack_reduction'] + p['defense_boost']))
        display = record('显示威力', '四舍五入(有效威力 × 本系 × 克制 × 攻防强化倍率 × 其他威力倍率)',
                         half_up(effective * p['stab_multiplier'] * p['type_multiplier'] * stage * p['other_power_multiplier']))
        level = record('等级系数', '(攻击方等级 × 0.45 + 10) ÷ 41', (p['level'] * Decimal('.45') + 10) / 41)
        numerator = record('攻击与威力结算', '四舍五入(实际攻击 × 显示威力 × 等级系数)',
                           half_up(p['attack'] * display * level))
        base = record('基础伤害', '向下取整(攻击与威力结算 ÷ 实际防御)', numerator // p['defense'])
        damage = record('最终估算伤害', '基础伤害 × 最终伤害倍率', base * p['final_damage_multiplier'])
        answer = {'formula_id': 'community_showdown_v1', 'verification_status': 'pending_in_game_validation',
                  'estimated_damage': float(damage), 'inputs': {key: float(value) for key, value in p.items()},
                  'steps': steps,
                  'assumptions': ['社区公式估算，待游戏内实测验证。',
                                  '使用强化前的实际能力值，物理和魔法通道须对应。',
                                  '中间四舍五入采用半数进位；最终乘区后保留小数，最终取整规则待实测。',
                                  '本次计算按一次伤害结算；特殊技能、特性、天气、连击和随机效果需核对并折算为输入。']}
        if 'defender_hp' in p:
            answer['damage_percent'] = float(damage / p['defender_hp'] * 100)
            answer['estimated_ko'] = damage >= p['defender_hp']
        return answer


def damage_tool(**parameters):
    from .queries import result
    return result('ok', calculate_damage(**parameters), [{'file': str(FORMULA_FILE)}])
