export type CombatBuffDraft = {attack: string; defense: string; combo: string; power: string}
export const emptyBuffs = (): CombatBuffDraft => ({attack: '0', defense: '0', combo: '0', power: '0'})
export const buffPayload = (value: CombatBuffDraft) => Object.fromEntries(Object.entries(value).map(([key, amount]) => [key, Number(amount)]))

export default function BuffEditor({side, value, onChange}: {side: string; value: CombatBuffDraft; onChange: (value: CombatBuffDraft) => void}) {
  const fields = [
    ['attack', '攻', '层', -100, 100, '1', '每层10%，正数提升、负数降低'],
    ['defense', '防', '层', -100, 100, '1', '每层10%，正数提升、负数降低'],
    ['combo', '连击', '次', -100, 100, '1', '连击次数增减，仅对自带连击的技能生效'],
    ['power', '威力', '层', -100, 100, '1', '每层10点，正数提升、负数降低'],
  ] as const
  return <div className="creature-buffs"><h3>战斗 Buff</h3>{fields.map(([key, label, unit, min, max, step, hint]) => <label className="damage-field" key={key}><span>{label}</span><div><input aria-label={`${side}${label}Buff`} type="number" min={min} max={max} step={step} required value={value[key]} onChange={e => onChange({...value, [key]: e.target.value})} /><em>{unit}</em></div><small>{hint}{key !== 'combo' ? ` · 当前${Number(value[key]) * 10}${key === 'power' ? '点' : '%'}` : ''}</small></label>)}
  </div>
}
