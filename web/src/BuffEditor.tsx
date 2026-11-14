export type CombatBuffDraft = {attack: string; defense: string; combo: string; power_percent: string; power_flat: string}
export const emptyBuffs = (): CombatBuffDraft => ({attack: '0', defense: '0', combo: '0', power_percent: '0', power_flat: '0'})
export const buffPayload = (value: CombatBuffDraft) => Object.fromEntries(Object.entries(value).map(([key, amount]) => [key, Number(amount)]))

export default function BuffEditor({side, value, onChange}: {side: string; value: CombatBuffDraft; onChange: (value: CombatBuffDraft) => void}) {
  const fields = [
    ['attack', '攻', '层', -100, 100, '1', '每层10%，正数提升、负数降低'],
    ['defense', '防', '层', -100, 100, '1', '每层10%，正数提升、负数降低'],
    ['combo', '连击', '次', -100, 100, '1', '连击次数增减，仅对自带连击的技能生效'],
  ] as const
  return <div className="creature-buffs"><h3>战斗 Buff</h3>{fields.map(([key, label, unit, min, max, step, hint]) => <label className="damage-field" key={key}><span>{label}</span><div><input aria-label={`${side}${label}Buff`} type="number" min={min} max={max} step={step} required value={value[key]} onChange={e => onChange({...value, [key]: e.target.value})} /><em>{unit}</em></div><small>{hint}{key === 'attack' || key === 'defense' ? ` · 当前${Number(value[key]) * 10}%` : ''}</small></label>)}
    <div className="damage-field buff-power"><span>威力</span><div className="buff-power-fields"><label><input aria-label={`${side}威力百分比Buff`} type="number" min={-100} max={1000} step="any" required value={value.power_percent} onChange={e => onChange({...value, power_percent: e.target.value})} /><em>%</em></label><label><input aria-label={`${side}固定威力Buff`} type="number" min={-100000} max={100000} step="any" required value={value.power_flat} onChange={e => onChange({...value, power_flat: e.target.value})} /><em>点</em></label></div><small>百分比加成／固定威力加成，可填负数</small></div>
  </div>
}
