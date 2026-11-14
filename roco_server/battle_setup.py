"""网页手动精灵配置：PVP社区面板与伤害估算。"""
from decimal import Decimal, ROUND_HALF_UP
from math import floor
from struct import pack, unpack
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from roco_data.damage import calculate_damage

STAT_LABELS = {'hp': '生命', 'atk': '物攻', 'def': '物防', 'spa': '魔攻', 'spd': '魔防', 'spe': '速度'}
Stat = Literal['hp', 'atk', 'def', 'spa', 'spd', 'spe']
IV = Annotated[int, Field(strict=True, ge=0, le=60)]
MODIFIERS = {'flat_power_bonus', 'power_percent_bonus', 'attack_boost', 'attack_reduction',
             'defense_boost', 'defense_reduction', 'other_power_multiplier', 'final_damage_multiplier'}


class PetSetup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pet_id: int = Field(strict=True, gt=0)
    level: int = Field(default=60, strict=True, ge=1, le=100)
    stars: int = Field(default=5, strict=True, ge=0, le=10)
    growth: int = Field(default=50, strict=True, ge=0, le=100)
    ivs: dict[str, IV] = Field(default_factory=dict)
    nature_plus: Stat | None = None
    nature_minus: Stat | None = None
    hp_percent: float = Field(default=100, strict=True, ge=1, le=100, allow_inf_nan=False)

    @model_validator(mode='after')
    def check_build(self):
        if self.growth < self.stars * 10:
            raise ValueError('成长等级需达到星级的10倍，才能突破到该星级')
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


def level_editable(pet):
    names = {'阿布', '冥古龙'}
    return pet['title'] in names or any(
        member.get('name') in names
        for branch in pet.get('evolution_branches', [])
        for member in branch.get('chain', []))


def f32(value):
    return unpack('f', pack('f', value))[0]


def panel(queries, setup: PetSetup):
    pet = get_pet(queries, setup.pet_id)
    if setup.level != 60 and not level_editable(pet):
        raise ValueError('仅阿布、冥古龙及其进化链可填写实际入场等级，其他精灵按60级计算')
    base = pet['profile'].get('stats', {})
    if any(type(base.get(key)) not in (int, float) or base[key] < 1 for key in STAT_LABELS):
        raise ValueError('该精灵的种族值资料待补齐')
    stats, ivs = {}, {key: setup.ivs.get(key, 0) for key in STAT_LABELS}
    for key in STAT_LABELS:
        # 社区面板规则：每步落为float32，先除后乘，再取整、乘性格、取整、加成长。
        hp = key == 'hp'
        core = f32(2 * base[key] + ivs[key])
        raw = f32(f32(core / (100 if hp else 200)) * (setup.level + (25 if hp else 50)))
        raw = f32(f32(raw + setup.level) + 10) if hp else f32(raw + 10)
        nature = f32(1.1 + .02 * setup.stars if setup.nature_plus == key else .9 if setup.nature_minus == key else 1)
        stats[key] = floor(f32(floor(raw + .5) * nature) + .5) + setup.growth * (2 if hp else 1)
    current_hp = max(1, half_up(Decimal(stats['hp']) * Decimal(str(setup.hp_percent)) / 100))
    feature = queries.features.get(pet['feature_id'], {})
    return {'pet_id': pet['pet_id'], 'name': pet['title'], 'types': pet['profile']['types'],
            'base_stats': base, 'stats': stats, 'ivs': ivs, 'level': setup.level,
            'stars': setup.stars, 'growth': setup.growth,
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
        base_power=skill['power'] if body.power_override is None else body.power_override, level=attacker['level'],
        stab_multiplier=stab, type_multiplier=type_multiplier(defender, skill['element']),
        defender_hp=defender['current_hp'], **body.modifiers)
    result['matchup'] = {'attacker': attacker, 'defender': defender, 'skill': skill,
                         'channel': f'{STAT_LABELS[attack_key]} → {STAT_LABELS[defense_key]}',
                         'power_overridden': body.power_override is not None}
    result['assumptions'].insert(1, f"面板采用PVP社区换算：攻击方{body.attacker.level}级/{body.attacker.stars}星/成长{body.attacker.growth}，受击方{body.defender.level}级/{body.defender.stars}星/成长{body.defender.growth}；个体为0～60整数，最多3项非零。")
    result['assumptions'].append('血脉或传说学习条件与技能触发条件由使用者确认；特性效果通过已确认的额外修正填写。')
    return result
