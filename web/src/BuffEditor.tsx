export type CombatBuffDraft = {physical_attack: string; magic_attack: string; physical_defense: string; magic_defense: string; combo: string; power: string}
export const emptyBuffs = (): CombatBuffDraft => ({physical_attack: '0', magic_attack: '0', physical_defense: '0', magic_defense: '0', combo: '0', power: '0'})
export const buffPayload = (value: CombatBuffDraft) => Object.fromEntries(Object.entries(value).map(([key, amount]) => [key, Number(amount)]))

export default function BuffEditor({side, value, onChange}: {side: string; value: CombatBuffDraft; onChange: (value: CombatBuffDraft) => void}) {
  const fields = [
    ['physical_attack', '物攻', '%', -1000, 1000, '10', '每次调整10%，正数提升、负数降低'],
    ['magic_attack', '魔攻', '%', -1000, 1000, '10', '每次调整10%，正数提升、负数降低'],
    ['physical_defense', '物防', '%', -1000, 1000, '10', '每次调整10%，正数提升、负数降低'],
    ['magic_defense', '魔防', '%', -1000, 1000, '10', '每次调整10%，正数提升、负数降低'],
    ['combo', '连击', '次', -100, 100, '1', '连击次数增减，仅对自带连击的技能生效'],
    ['power', '威力', '点', -1000, 1000, '10', '每次调整10点，正数提升、负数降低'],
  ] as const
  return <div className="creature-buffs"><h3>战斗 Buff</h3>{fields.filter(([key]) => side === '攻击方' ? !key.endsWith('_defense') : key.endsWith('_defense')).map(([key, label, unit, min, max, step, hint]) => <label className="damage-field" key={key}><span title={hint}>{label}</span><div><input title={hint} aria-label={`${side}${label}Buff`} type="number" min={min} max={max} step={step} required value={value[key]} onChange={e => onChange({...value, [key]: e.target.value})} /><em>{unit}</em></div></label>)}
  </div>
}
