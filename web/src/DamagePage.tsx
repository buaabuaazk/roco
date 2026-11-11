import { useEffect, useState } from 'react'
import DamageResult, {type DamageAnswer} from './DamageResult'
import PetBattleForm from './PetBattleForm'

type Skill = {skill_id: number; name: string; element: string; damage_class: string; power: number; description: string}
type Input = {key: string; label: string; hint?: string; min: number; max: number; unit?: string; optional?: boolean}
const basic: Input[] = [
  {key: 'attack', label: '实际攻击', hint: '强化前物攻或魔攻', min: 1, max: 1000000},
  {key: 'defense', label: '实际防御', hint: '对应的强化前物防或魔防', min: 1, max: 1000000},
  {key: 'base_power', label: '本次基础威力', hint: '特殊技能按本次触发条件确认', min: 0, max: 100000},
  {key: 'level', label: '攻击方等级', min: 1, max: 100},
  {key: 'defender_hp', label: '防御方当前生命', hint: '可选，用于计算伤害占比', min: 1, max: 1000000000, optional: true},
]
const advanced: Input[] = [
  {key: 'flat_power_bonus', label: '固定威力加成', min: -100000, max: 100000},
  {key: 'power_percent_bonus', label: '本次威力加成合计', min: -100, max: 1000, unit: '%'},
  {key: 'stab_multiplier', label: '本系倍率', hint: '非本系1；本系参考1.25', min: 0, max: 10, unit: '×'},
  {key: 'type_multiplier', label: '属性克制倍率', hint: '普通1；克制2；免疫0', min: 0, max: 16, unit: '×'},
  {key: 'attack_boost', label: '攻击提升', min: 0, max: 1000, unit: '%'},
  {key: 'attack_reduction', label: '攻击降低', min: 0, max: 1000, unit: '%'},
  {key: 'defense_boost', label: '防御提升', min: 0, max: 1000, unit: '%'},
  {key: 'defense_reduction', label: '防御降低', min: 0, max: 1000, unit: '%'},
  {key: 'other_power_multiplier', label: '其他威力倍率', min: 0, max: 100, unit: '×'},
  {key: 'final_damage_multiplier', label: '最终伤害倍率', hint: '如减伤70%，填0.3', min: 0, max: 100, unit: '×'},
]
const defaults: Record<string, string> = {attack: '', defense: '', base_power: '35', level: '60', defender_hp: '', flat_power_bonus: '0', power_percent_bonus: '0', stab_multiplier: '1', type_multiplier: '1', attack_boost: '0', attack_reduction: '0', defense_boost: '0', defense_reduction: '0', other_power_multiplier: '1', final_damage_multiplier: '1'}
const percentKeys = new Set(advanced.filter(field => field.unit === '%').map(field => field.key))

function DirectDamageForm() {
  const [values, setValues] = useState(defaults)
  const [skills, setSkills] = useState<Skill[]>([])
  const [skillId, setSkillId] = useState('')
  const [answer, setAnswer] = useState<DamageAnswer>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const skill = skills.find(row => String(row.skill_id) === skillId)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/damage/skills', {signal: controller.signal}).then(async response => {
      if (!response.ok) throw new Error('技能列表加载失败，可手动填写基础威力。')
      setSkills(await response.json())
    }).catch(e => {if (!controller.signal.aborted) setError(e.message)})
    return () => controller.abort()
  }, [])
  function change(key: string, value: string) {setValues(previous => ({...previous, [key]: value})); setAnswer(undefined)}
  async function calculate(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setAnswer(undefined)
    const body = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value) / (percentKeys.has(key) ? 100 : 1)]))
    try {
      const response = await fetch('/api/damage/calculate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '请检查输入数值。')
      setAnswer(result)
    } catch(e) {setError((e as Error).message)} finally {setBusy(false)}
  }
  function field(item: Input) {
    return <label className="damage-field" key={item.key}><span>{item.label}</span><div><input type="number" aria-label={item.label} min={item.min} max={item.max} step={item.key === 'level' ? 1 : 'any'} required={!item.optional} value={values[item.key]} onChange={e => change(item.key, e.target.value)} placeholder={item.optional ? '选填' : '填写数值'} />{item.unit && <em>{item.unit}</em>}</div>{item.hint && <small>{item.hint}</small>}</label>
  }
  return <div className="damage-layout"><form onSubmit={calculate}>
      <fieldset disabled={busy}>
        <section className="damage-card"><div className="damage-card-heading"><h2>基础数值</h2><button type="button" className="text-button" onClick={() => {setValues({...defaults, attack: '234', defense: '226', base_power: '75', flat_power_bonus: '20', power_percent_bonus: '50', stab_multiplier: '1.25', type_multiplier: '2', defender_hp: '411'}); setSkillId(''); setAnswer(undefined); setError('')}}>载入公式示例</button></div>
          <label className="damage-skill-label" htmlFor="damage-skill">参考技能</label><select id="damage-skill" value={skillId} onChange={e => {setSkillId(e.target.value); const row = skills.find(item => String(item.skill_id) === e.target.value); if (row) change('base_power', String(row.power)); else setAnswer(undefined)}}><option value="">手动填写本次威力</option>{skills.map(row => <option key={row.skill_id} value={row.skill_id}>{row.name} · {row.element} · {row.damage_class || '攻击'}</option>)}</select>
          {skill && <div className="damage-skill-note"><strong>{skill.name} · {skill.damage_class}</strong><p>{skill.description}</p><small>已填入资料中的基础威力。请核对本次触发条件，以及实际攻防通道。</small></div>}
          <div className="damage-field-grid">{basic.map(field)}</div><p className="damage-input-note">能力值采用游戏面板中的实际数值。强化效果在下方填写。</p>
        </section>
        <details className="damage-card damage-advanced"><summary>加成与修正<span>{advanced.some(item => values[item.key] !== defaults[item.key]) ? '已设置修正 · 展开查看' : '默认无额外修正 · 展开设置'}</span></summary><div className="damage-field-grid">{advanced.map(field)}</div></details>
        {error && <div className="data-error" role="alert">{error}</div>}
        <button type="submit" className="damage-submit">{busy ? '正在计算…' : '计算预计伤害'}<span>↗</span></button>
      </fieldset>
    </form>
    <DamageResult answer={answer} /></div>
}

export default function DamagePage() {
  const [mode, setMode] = useState('pets')
  return <main className="data-page damage-page">
    <div className="data-page-heading"><div><span className="section-kicker">DAMAGE CALCULATOR</span><h1>伤害计算器</h1><p>手动选择双方精灵与配置，按社区规则估算单次伤害。</p></div><span className="source-tag">社区公式 · 估算版</span></div>
    <nav className="damage-mode-tabs" aria-label="计算方式"><button className={mode === 'pets' ? 'active' : ''} onClick={() => setMode('pets')}>精灵配置 · 60级PVP</button><button className={mode === 'direct' ? 'active' : ''} onClick={() => setMode('direct')}>直接输入数值</button></nav>
    <div hidden={mode !== 'pets'}><PetBattleForm /></div>
    <div hidden={mode !== 'direct'}><DirectDamageForm /></div>
  </main>
}
