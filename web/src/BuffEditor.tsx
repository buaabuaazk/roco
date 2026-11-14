import {useEffect, useState} from 'react'

export type BuffDraft = {id: string; side: 'attacker' | 'defender'; kind: string; layers: string; value: string; enabled: boolean}
type Rule = {kind: string; label: string; unit: string; minimum: number; maximum: number}

export const buffPayload = (rows: BuffDraft[]) => rows.filter(row => row.enabled).map(row => ({side: row.side, kind: row.kind, layers: Number(row.layers), value: Number(row.value), enabled: row.enabled}))

export default function BuffEditor({rows, onChange}: {rows: BuffDraft[]; onChange: (rows: BuffDraft[]) => void}) {
  const [rules, setRules] = useState<Rule[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/damage/buffs', {signal: controller.signal}).then(async response => {
      if (!response.ok) throw new Error('Buff类型读取失败，请刷新重试。')
      setRules(await response.json())
    }).catch(e => {if (!controller.signal.aborted) setError(e.message)})
    return () => controller.abort()
  }, [])
  const update = (id: string, patch: Partial<BuffDraft>) => onChange(rows.map(row => row.id === id ? {...row, ...patch} : row))
  return <section className="damage-card buff-editor"><div className="damage-card-heading"><h2>战斗 Buff</h2><span>{rows.filter(row => row.enabled).length} 项启用</span></div>
    <p className="damage-input-note">添加双方当前生效的强化或减益，填写每层幅度与层数，后台按伤害通道计算。</p>
    {rows.map((row, index) => {
      const rule = rules.find(value => value.kind === row.kind)
      return <div className={'buff-row ' + (!row.enabled ? 'buff-disabled' : '')} key={row.id}>
        <div className="buff-row-heading"><label><input type="checkbox" aria-label={`Buff${index+1}启用`} checked={row.enabled} onChange={e => update(row.id, {enabled: e.target.checked})} />Buff {index+1}</label><button type="button" aria-label={`移除Buff${index+1}`} onClick={() => onChange(rows.filter(value => value.id !== row.id))}>移除</button></div>
        <fieldset disabled={!row.enabled}><div className="buff-fields">
          <label className="damage-field"><span>所属精灵</span><select aria-label={`Buff${index+1}所属方`} value={row.side} onChange={e => update(row.id, {side: e.target.value as BuffDraft['side']})}><option value="attacker">攻击方</option><option value="defender">受击方</option></select></label>
          <label className="damage-field"><span>效果</span><select aria-label={`Buff${index+1}效果`} value={row.kind} onChange={e => update(row.id, {kind: e.target.value, value: ''})}>{rules.map(value => <option value={value.kind} key={value.kind}>{value.label}</option>)}</select></label>
          <label className="damage-field"><span>每层幅度</span><div><input aria-label={`Buff${index+1}每层幅度`} type="number" step="any" min={rule?.minimum} max={rule?.maximum} required value={row.value} onChange={e => update(row.id, {value: e.target.value})} /><em>{rule?.unit}</em></div></label>
          <label className="damage-field"><span>当前层数</span><div><input aria-label={`Buff${index+1}层数`} type="number" min={0} max={100} step={1} required value={row.layers} onChange={e => update(row.id, {layers: e.target.value})} /></div></label>
        </div></fieldset>
        <p className="damage-input-note">{rule?.label}：{row.value || '—'}{rule?.unit} × {row.layers || '—'} 层{row.value !== '' && row.layers !== '' ? ` = ${Number((Number(row.value) * Number(row.layers)).toFixed(6))}${rule?.unit}` : ''}</p>
      </div>
    })}
    {error && <div className="data-error" role="alert">{error}</div>}
    <button className="buff-add" type="button" disabled={!rules.length || rows.length >= 32} onClick={() => onChange([...rows, {id: crypto.randomUUID(), side: 'attacker', kind: rules[0].kind, value: '', layers: '1', enabled: true}])}>＋ 添加 Buff</button>
    <p className="damage-input-note">每层幅度按游戏效果填写；同类攻防与普通威力加成相加，独立威力增幅及最终伤害倍率逐项相乘。结果会列出生效和未适用的条目。</p>
  </section>
}
