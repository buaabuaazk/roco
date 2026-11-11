"""网页手动精灵配置：60级PVP社区面板与伤害估算。"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from roco_data.damage import calculate_damage

STAT_LABELS = {'hp': '生命', 'atk': '物攻', 'def': '物防', 'spa': '魔攻', 'spd': '魔防', 'spe': '速度'}
Stat = Literal['hp', 'atk', 'def', 'spa', 'spd', 'spe']
IV = Annotated[int, Field(strict=True, ge=0, le=10)]
MODIFIERS = {'flat_power_bonus', 'power_percent_bonus', 'attack_boost', 'attack_reduction',
             'defense_boost', 'defense_reduction', 'other_power_multiplier', 'final_damage_multiplier'}


class PetSetup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pet_id: int = Field(strict=True, gt=0)
    ivs: dict[str, IV] = Field(default_factory=dict)
    nature_plus: Stat | None = None
    nature_minus: Stat | None = None
    hp_percent: float = Field(default=100, strict=True, ge=1, le=100, allow_inf_nan=False)

    @model_validator(mode='after')
    def check_build(self):
        if set(self.ivs) - STAT_LABELS.keys():
            raise ValueError('个体配置包含未知能力项')
        if sum(value > 0 for value in self.ivs.values()) > 3:
            raise ValueError('当前社区配置规则最多设置3项非零个体')
        if ((self.nature_plus is None) != (self.nature_minus is None)
                or self.nature_plus is not None and self.nature_plus == self.nature_minus):
            raise ValueError('性格需选择不同的提升项与降低项，或选择无修正')
        return self


class MatchupInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attacker: PetSetup
    defender: PetSetup
    skill_id: int = Field(strict=True, gt=0)
    power_override: float | None = Field(default=None, strict=True, ge=0, le=100000, allow_inf_nan=False)
    modifiers: dict[str, Annotated[float, Field(strict=True, allow_inf_nan=False)]] = Field(default_factory=dict)


def get_pet(queries, pet_id):
    pet = queries.pets.get(pet_id)
    if pet is None:
        raise ValueError('当前资料中未找到该精灵，请重新选择')
    return pet


def half_up(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def panel(queries, setup: PetSetup):
    pet = get_pet(queries, setup.pet_id)
    base = pet['profile'].get('stats', {})
    if any(type(base.get(key)) not in (int, float) or base[key] < 1 for key in STAT_LABELS):
        raise ValueError('该精灵的种族值资料待补齐')
    stats, ivs = {}, {key: setup.ivs.get(key, 0) for key in STAT_LABELS}
    for key in STAT_LABELS:
        coefficient, constant, offset = ('1.7', 70, 100) if key == 'hp' else ('1.1', 10, 50)
        nature = Decimal('1.2') if setup.nature_plus == key else Decimal('.9') if setup.nature_minus == key else Decimal(1)
        core = half_up(Decimal(coefficient) * (Decimal(str(base[key])) + 3 * ivs[key])) + constant
        stats[key] = half_up(Decimal(core) * nature) + offset
    current_hp = max(1, half_up(Decimal(stats['hp']) * Decimal(str(setup.hp_percent)) / 100))
    feature = queries.features.get(pet['feature_id'], {})
    return {'pet_id': pet['pet_id'], 'name': pet['title'], 'types': pet['profile']['types'],
            'base_stats': base, 'stats': stats, 'ivs': ivs, 'level': 60,
            'nature_plus': setup.nature_plus, 'nature_minus': setup.nature_minus,
            'hp_percent': setup.hp_percent, 'current_hp': current_hp,
            'feature': {'name': feature.get('name'), 'description': feature.get('desc')},
            'type_effectiveness': pet['type_effectiveness'],
            'verification_status': 'pending_in_game_validation'}


def pet_skills(queries, pet_id):
    pet = get_pet(queries, pet_id)
    learning = {}
    for source, rows in pet['skills'].items():
        for row in rows:
            if source == 'level' and row.get('level') is not None and row['level'] > 60:
                continue
            learning.setdefault(row['skill_id'], []).append(
                {'source': source, **{key: row[key] for key in ('level', 'blood', 'requires', 'stage') if key in row}})
    return [{'skill_id': row['skill_id'], 'name': row['name'], 'power': row['power'],
             'element': row.get('element'), 'damage_class': row.get('damage_class'),
             'description': row.get('desc', ''), 'learning': learning[row['skill_id']]}
            for row in sorted(queries.skills.values(), key=lambda value: (value['name'], value['skill_id']))
            if row['skill_id'] in learning and row.get('category') == '攻击'
            and row.get('damage_class') in ('物攻', '魔攻') and type(row.get('power')) in (int, float)]


def type_multiplier(pet_panel, element):
    for group in pet_panel['type_effectiveness'].values():
        for row in group:
            if row['type'].removesuffix('系') == element.removesuffix('系'):
                return row['multiplier']
    return 1


def matchup(queries, body: MatchupInput):
    if set(body.modifiers) - MODIFIERS:
        raise ValueError('修正参数包含自动计算项或未知项，请使用页面提供的修正字段')
    attacker, defender = panel(queries, body.attacker), panel(queries, body.defender)
    skill = next((row for row in pet_skills(queries, body.attacker.pet_id) if row['skill_id'] == body.skill_id), None)
    if skill is None:
        raise ValueError('该技能不在攻击方当前可选的攻击技能池中')
    if not skill.get('element'):
        raise ValueError('技能属性资料待补齐')
    physical = skill['damage_class'] == '物攻'
    attack_key, defense_key = ('atk', 'def') if physical else ('spa', 'spd')
    stab = 1.25 if skill['element'].removesuffix('系') in [value.removesuffix('系') for value in attacker['types']] else 1
    result = calculate_damage(attack=attacker['stats'][attack_key], defense=defender['stats'][defense_key],
        base_power=skill['power'] if body.power_override is None else body.power_override, level=60,
        stab_multiplier=stab, type_multiplier=type_multiplier(defender, skill['element']),
        defender_hp=defender['current_hp'], **body.modifiers)
    result['matchup'] = {'attacker': attacker, 'defender': defender, 'skill': skill,
                         'channel': f'{STAT_LABELS[attack_key]} → {STAT_LABELS[defense_key]}',
                         'power_overridden': body.power_override is not None}
    result['assumptions'].insert(1, '面板采用60级PVP社区换算；个体为0～10刻度，最多3项非零；性格提升1.2、降低0.9。')
    result['assumptions'].append('血脉或传说学习条件与技能触发条件由使用者确认；特性效果通过已确认的额外修正填写。')
    return result
