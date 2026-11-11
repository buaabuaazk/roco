import { useEffect, useRef, useState } from 'react'

type Skill = {skill_id: number; name: string; element: string; damage_class: string; power: number; description: string}
type Answer = {estimated_damage: number; damage_percent?: number; estimated_ko?: boolean; steps: {label: string; expression: string; value: number}[]; assumptions: string[]}
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
const number = (value: number) => value.toLocaleString('zh-CN', {maximumFractionDigits: 6})

export default function DamagePage() {
  const resultPanel = useRef<HTMLElement>(null)
  const [values, setValues] = useState(defaults)
  const [skills, setSkills] = useState<Skill[]>([])
  const [skillId, setSkillId] = useState('')
  const [answer, setAnswer] = useState<Answer>()
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
  useEffect(() => {if (answer && window.innerWidth <= 1100) resultPanel.current?.scrollIntoView({behavior: 'smooth', block: 'start'})}, [answer])
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
  return <main className="data-page damage-page">
    <div className="data-page-heading"><div><span className="section-kicker">DAMAGE CALCULATOR</span><h1>伤害计算器</h1><p>基于社区公式估算单次伤害，输入实际能力值查看计算过程。</p></div><span className="source-tag">社区公式 · 估算版</span></div>
    <div className="damage-layout"><form onSubmit={calculate}>
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
    <section ref={resultPanel} className="damage-result" aria-live="polite"><div className="damage-result-heading"><span className="section-kicker">ESTIMATE</span><h2>计算结果</h2><span>单次伤害 · 待游戏内实测验证</span></div>
      {answer ? <><div className="damage-total"><small>最终估算伤害</small><strong>{number(answer.estimated_damage)}</strong>{answer.damage_percent !== undefined && <p>约占当前生命 <b>{number(answer.damage_percent)}%</b><span className="damage-ko">{answer.estimated_ko ? '估算可击倒' : '估算未击倒'}</span></p>}</div><ol className="damage-steps">{answer.steps.map((step, index) => <li key={step.label}><i>{index + 1}</i><div><div className="damage-step-heading"><strong>{step.label}</strong><b>{number(step.value)}</b></div><p>{step.expression}</p></div></li>)}</ol><div className="damage-rounding">中间四舍五入采用半数进位，最终乘区后保留小数；游戏最终取整规则待实测。</div><details className="damage-assumptions"><summary>本次估算的适用条件</summary><ul>{answer.assumptions.map(text => <li key={text}>{text}</li>)}</ul></details></> : <div className="damage-result-empty"><span>ƒ</span><h3>每一步，都算清楚</h3><p>填写左侧数据后计算，查看威力、等级系数与最终伤害的完整过程。</p><small>也可载入公式示例，验证 332 点估算伤害。</small></div>}
      <div className="damage-source">公式依据：<a href="https://roco-showdown.com/battle-use-guide" target="_blank" rel="noreferrer">Roco Showdown 社区指南 ↗</a></div>
    </section></div>
  </main>
}
