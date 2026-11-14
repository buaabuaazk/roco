"""将当前生效的Buff层数换算成一次攻击使用的修正。"""
from decimal import Decimal
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BUFF_CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'data/mechanics/buffs.json').read_text())
BUFF_RULES = {row['kind']: row for row in BUFF_CATALOG}


class CombatBuffs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attack: int = Field(default=0, strict=True, ge=-100, le=100)
    defense: int = Field(default=0, strict=True, ge=-100, le=100)
    combo: int = Field(default=0, strict=True, ge=-100, le=100)
    power_percent: float = Field(default=0, strict=True, ge=-100, le=1000, allow_inf_nan=False)
    power_flat: float = Field(default=0, strict=True, ge=-100000, le=100000, allow_inf_nan=False)

    def effects(self, side):
        rows = []
        for field, kind in (('attack', 'dual_attack'), ('defense', 'dual_defense')):
            layers = getattr(self, field)
            if layers:
                rows.append(BuffInput(side=side, kind=kind + ('_boost' if layers > 0 else '_reduction'),
                                      value=10, layers=abs(layers)))
        if self.power_percent:
            rows.append(BuffInput(side=side, kind='power_boost' if self.power_percent > 0 else 'power_reduction',
                                  value=abs(self.power_percent)))
        if self.power_flat:
            rows.append(BuffInput(side=side, kind='power_flat', value=self.power_flat))
        return rows


class BuffInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    side: Literal['attacker', 'defender']
    kind: str
    layers: int = Field(default=1, strict=True, ge=0, le=100)
    value: float = Field(strict=True, allow_inf_nan=False)
    enabled: bool = Field(default=True, strict=True)

    @model_validator(mode='after')
    def check_effect(self):
        rule = BUFF_RULES.get(self.kind)
        if rule is None:
            raise ValueError('未知Buff类型')
        if not rule['minimum'] <= self.value <= rule['maximum']:
            raise ValueError(f"{rule['label']}每层幅度应为{rule['minimum']}～{rule['maximum']}{rule['unit']}")
        if self.kind in ('power_reduction', 'damage_reduction') and self.value * self.layers > 100:
            raise ValueError('同一条Buff的降低或减免合计最多为100%')
        return self


def resolve_buffs(buffs: list[BuffInput], attack_key: str, defense_key: str, modifiers: dict):
    totals = {key: Decimal(str(value)) for key, value in modifiers.items()}
    details = []
    for buff in buffs:
        rule = BUFF_RULES[buff.kind]
        total = Decimal(str(buff.value)) * buff.layers
        key, reason = None, ''
        effect = rule['effect']
        if not buff.enabled or buff.layers == 0:
            reason = '未启用' if not buff.enabled else '层数为0'
        elif effect == 'stat':
            stat = attack_key if buff.side == 'attacker' else defense_key
            if stat in rule['stats']:
                key = ('attack_' if buff.side == 'attacker' else 'defense_') + rule['direction']
            else:
                reason = '本次伤害通道未使用该能力'
        elif effect in ('flat_power_bonus', 'power_percent_bonus', 'power_percent_reduction', 'other_power_multiplier', 'damage_boost'):
            if buff.side == 'attacker':
                key = {'power_percent_reduction': 'power_percent_bonus', 'damage_boost': 'final_damage_multiplier'}.get(effect, effect)
            else:
                reason = '攻击方Buff影响本次技能'
        elif buff.side == 'defender':
            key = 'final_damage_multiplier'
        else:
            reason = '受击方Buff影响本次承伤'
        if key is not None:
            amount = total if effect == 'flat_power_bonus' else total / 100
            if key in ('other_power_multiplier', 'final_damage_multiplier'):
                factor = 1 - amount if effect == 'damage_reduction' else 1 + amount
                totals[key] = totals.get(key, Decimal(1)) * factor
            else:
                totals[key] = totals.get(key, Decimal(0)) + (-amount if effect == 'power_percent_reduction' else amount)
        details.append({**buff.model_dump(), 'label': rule['label'], 'unit': rule['unit'],
                        'total': float(total), 'applied': key is not None,
                        'reason': reason or '已计入本次计算', 'modifier': key})
    return {key: float(value) for key, value in totals.items()}, details
