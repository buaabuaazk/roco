import { useEffect, useState } from 'react'
import {typeIcons} from './typeIcons'
import DamageResult, {type DamageAnswer} from './DamageResult'
import BuffEditor, {buffPayload, emptyBuffs, type CombatBuffDraft} from './BuffEditor'

type Stat = 'hp' | 'atk' | 'def' | 'spa' | 'spd' | 'spe'
const stats: [Stat, string][] = [['hp', '生命'], ['atk', '物攻'], ['def', '物防'], ['spa', '魔攻'], ['spd', '魔防'], ['spe', '速度']]
type Pet = {pet_id: number; name: string; types: string[]; level_editable: boolean; entry_attack_bonus?: number | null; image_url?: string | null; default_training?: {nature_plus?: Stat; nature_minus?: Stat; ivs?: Record<Stat, number>}}
type Build = {pet_id?: number; name: string; level: string; feature_entries: string; nature_plus: Stat | ''; nature_minus: Stat | ''; ivs: Record<Stat, string>; buffs: CombatBuffDraft}
type Panel = Pet & {base_stats: Record<Stat, number>; stats: Record<Stat, number>; current_hp: number; feature: {name?: string; description?: string}; type_effectiveness: Record<string, {type: string; multiplier: number}[]>}
type Learning = {source: string; level?: number; blood?: string; requires?: string}
type Skill = {skill_id: number; name: string; power: number; energy?: number | null; image_url?: string | null; element: string; damage_class: string; description: string; learning: Learning[]}
const emptyBuild = (): Build => ({name: '', level: '60', feature_entries: '1', nature_plus: '', nature_minus: '', ivs: {hp: '0', atk: '0', def: '0', spa: '0', spd: '0', spe: '0'}, buffs: emptyBuffs()})
async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api/damage/' + path, {method: body === undefined ? 'GET' : 'POST', signal, headers: body === undefined ? {} : {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)})
  const value = await response.json()
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : Array.isArray(value.detail) ? value.detail.map((item: {msg: string}) => item.msg).join('；') : '请求失败，请检查配置。')
  return value
}
function buildError(build: Build) {
  if (build.feature_entries === '' || !Number.isInteger(Number(build.feature_entries)) || Number(build.feature_entries) < 0 || Number(build.feature_entries) > 100) return '累计入场次数请填0～100的整数。'
  if (Object.values(build.buffs).some(value => value === '' || !Number.isInteger(Number(value)))) return 'Buff变化值与连击增减请填整数。'
  if (Object.entries(build.buffs).some(([key, value]) => Math.abs(Number(value)) > (key === 'combo' ? 100 : 1000) || (key !== 'combo' && Number(value) % 10 !== 0))) return '物攻、魔攻、物防、魔防和威力请填-1000～1000内10的整数倍，连击增减请填-100～100。'
  if (build.level === '' || !Number.isInteger(Number(build.level)) || Number(build.level) < 1 || Number(build.level) > 100) return '入场等级请填1～100的整数。'
  if (!!build.nature_plus !== !!build.nature_minus) return '请选择性格的正面和负面能力，或两项均选无修正。'
  if (build.nature_plus && build.nature_plus === build.nature_minus) return '性格的正面和负面能力需选择不同项。'
  if (Object.values(build.ivs).some(value => value === '' || !Number.isInteger(Number(value)) || Number(value) < 0 || Number(value) > 60)) return '个体值请填0～60的整数。'
  if (Object.values(build.ivs).filter(value => Number(value) > 0).length > 3) return '当前社区规则最多设置3项非零个体。'
  return ''
}
function payload(build: Build) {
  return {pet_id: build.pet_id, level: Number(build.level), feature_entries: Number(build.feature_entries), ivs: Object.fromEntries(Object.entries(build.ivs).map(([key, value]) => [key, Number(value)])), nature_plus: build.nature_plus || null, nature_minus: build.nature_minus || null, buffs: buffPayload(build.buffs)}
}
function usePanel(build: Build) {
  const [state, setState] = useState<{panel?: Panel; error: string; loading: boolean}>({error: '', loading: false})
  useEffect(() => {
    const error = buildError(build)
    if (!build.pet_id || error) {setState({error: build.pet_id ? error : '', loading: false}); return}
    const controller = new AbortController()
    setState({error: '', loading: true})
    const timer = setTimeout(() => request<Panel>('panel', payload(build), controller.signal).then(panel => setState({panel, error: '', loading: false})).catch(e => {if (!controller.signal.aborted) setState({error: e.message, loading: false})}), 150)
    return () => {clearTimeout(timer); controller.abort()}
  }, [build])
  return state
}
function PetAvatar({pet}: {pet: Pet}) {
  const [failed, setFailed] = useState(false)
  return <div className="creature-avatar">{pet.image_url && !failed ? <img src={pet.image_url} alt={pet.name} width={112} height={112} referrerPolicy="no-referrer" onError={() => setFailed(true)} /> : <b aria-label="暂无精灵图片">{pet.name.slice(0, 1)}</b>}</div>
}

function TypeIcon({name}: {name: string}) {
  const [failed, setFailed] = useState(false)
  const url = typeIcons[name.replace(/系$/, '')]
  return <span className="creature-type-icon" title={name}>{failed || !url ? name : <img src={url} alt={name} width={28} height={28} referrerPolicy="no-referrer" onError={() => setFailed(true)} />}</span>
}

function CreatureCard({side, pets, build, onChange, preview}: {side: string; pets: Pet[]; build: Build; onChange: (value: Build) => void; preview: ReturnType<typeof usePanel>}) {
  const count = Object.values(build.ivs).filter(value => Number(value) > 0).length
  const pet = pets.find(row => row.pet_id === build.pet_id)
  return <section className="damage-card creature-card" data-side={side === '攻击方' ? 'attack' : 'defense'}><div className="damage-card-heading"><h2>{side}</h2><span>{build.level || '—'}级 · 5星 · 成长50</span></div>
    <label className="damage-skill-label" htmlFor={`${side}-pet`}>选择{side}精灵</label><input id={`${side}-pet`} className="pet-search-input" aria-label={`${side}精灵`} list={`${side}-pets`} placeholder="输入精灵名称并从列表选择" value={build.name} onChange={e => {const next = pets.find(row => row.name === e.target.value); const training = next && next.pet_id !== build.pet_id ? next.default_training : undefined; onChange({...build, name: e.target.value, pet_id: next?.pet_id, feature_entries: next?.pet_id === build.pet_id ? build.feature_entries : '1', level: next?.level_editable ? build.level : '60', nature_plus: training?.nature_plus ?? build.nature_plus, nature_minus: training?.nature_minus ?? build.nature_minus, ivs: training?.ivs ? Object.fromEntries(stats.map(([key]) => [key, String(training.ivs![key])])) as Record<Stat, string> : build.ivs})}} autoComplete="off" /><datalist id={`${side}-pets`}>{pets.map(row => <option value={row.name} key={row.pet_id} />)}</datalist>
    {pet && <div className="creature-identity"><div className="creature-name"><PetAvatar key={pet.pet_id} pet={pet} /><strong>{pet.name}</strong></div><div className="creature-types" aria-label="精灵系别">{pet.types.map(name => <TypeIcon key={name} name={name} />)}</div></div>}
    {pet?.level_editable && <label className="damage-field cultivation-fields"><span>实际入场等级</span><div><input aria-label={`${side}入场等级`} type="number" min={1} max={100} step={1} required value={build.level} onChange={e => onChange({...build, level: e.target.value})} /><em>级</em></div><small>按特性生效后的实际等级填写，用于换算面板。</small></label>}
    <div className="damage-field-grid cultivation-fields">{(['nature_plus', 'nature_minus'] as const).map(key => <label className="damage-field" key={key}><span>性格{key === 'nature_plus' ? '正面提升' : '负面降低'}</span><select aria-label={`${side}性格${key === 'nature_plus' ? '正面' : '负面'}`} value={build[key]} onChange={e => onChange({...build, [key]: e.target.value as Stat | ''})}><option value="">无修正</option>{stats.map(([stat, title]) => <option key={stat} value={stat} disabled={stat === build[key === 'nature_plus' ? 'nature_minus' : 'nature_plus']}>{title}{key === 'nature_plus' ? `↑20%` : '↓10%'}</option>)}</select></label>)}</div>
    <div className="iv-table"><div className="iv-row iv-head"><span>能力</span><span>种族</span><span>个体</span><span>估算面板</span></div>{stats.map(([key, title]) => <div className="iv-row" key={key}><span>{title}</span><span>{preview.panel?.base_stats[key] ?? '—'}</span><div className="iv-control"><input aria-label={`${side}${title}个体`} type="number" min={0} max={60} step={1} required value={build.ivs[key]} onChange={e => onChange({...build, ivs: {...build.ivs, [key]: e.target.value}})} /><button type="button" className="iv-max" aria-label={`${side}${title}个体拉满`} title="填满60" disabled={count >= 3 && Number(build.ivs[key]) === 0} onClick={() => onChange({...build, ivs: {...build.ivs, [key]: '60'}})}>拉满</button></div><strong>{preview.loading ? '…' : preview.panel?.stats[key] ?? '—'}</strong></div>)}</div>
    <BuffEditor side={side} value={build.buffs} onChange={buffs => onChange({...build, buffs})} />
    {side === '攻击方' && pet?.entry_attack_bonus && <label className="damage-field cultivation-fields feature-entry"><span>特性 · 累计入场次数</span><div><input aria-label={`${side}特性累计入场次数`} type="number" min={0} max={100} step={1} required value={build.feature_entries} onChange={e => onChange({...build, feature_entries: e.target.value})} /><em>次</em></div><small>双攻 +{Number(build.feature_entries) * pet.entry_attack_bonus}% · 已自动计入</small></label>}
    {preview.panel?.feature.name && <details className="creature-feature"><summary>特性：{preview.panel.feature.name}</summary><p>{preview.panel.feature.description}</p><small>{pet?.entry_attack_bonus ? side === '攻击方' ? '按上方累计入场次数自动计算双攻加成。' : '双攻加成在该精灵作为攻击方时参与计算。' : '本次生效效果通过战斗Buff填写。'}</small></details>}
    {preview.error && <div className="data-error" role="alert">{preview.error}</div>}
  </section>
}
function SkillIcon({skill}: {skill: Skill}) {
  const [failed, setFailed] = useState(false)
  return <div className="skill-icon">{skill.image_url && !failed ? <img src={skill.image_url} alt={`${skill.name}图标`} width={64} height={64} referrerPolicy="no-referrer" onError={() => setFailed(true)} /> : <span>{skill.name.slice(0, 1)}</span>}</div>
}
function SkillSlot({index, skills, ids, onChange, loading, hasAttacker, ready, attacker, defender}: {
  index: number; skills: Skill[]; ids: string[]; onChange: (value: string) => void; loading: boolean;
  hasAttacker: boolean; ready: boolean; attacker: Build; defender: Build
}) {
  const skill = skills.find(row => String(row.skill_id) === ids[index])
  const [customPower, setCustomPower] = useState('')
  const [overridePower, setOverridePower] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState<DamageAnswer>()
  useEffect(() => {setOverridePower(false); setCustomPower(skill ? String(skill.power) : '')}, [skill?.skill_id, skill?.power])
  const validPower = !overridePower || (customPower !== '' && Number.isFinite(Number(customPower)) && Number(customPower) >= 0 && Number(customPower) <= 100000)
  const calculationKey = ready && skill && validPower ? JSON.stringify({attacker: payload(attacker), defender: payload(defender), skill_id: skill.skill_id, power_override: overridePower ? Number(customPower) : null}) : null
  useEffect(() => {
    setAnswer(undefined); setError(''); setBusy(calculationKey !== null)
    if (calculationKey === null) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      request<DamageAnswer>('matchup', JSON.parse(calculationKey), controller.signal)
        .then(result => {if (!controller.signal.aborted) setAnswer(result)})
        .catch(e => {if (!controller.signal.aborted) setError(e.message)})
        .finally(() => {if (!controller.signal.aborted) setBusy(false)})
    }, 200)
    return () => {clearTimeout(timer); controller.abort()}
  }, [calculationKey])
  const label = `技能${index + 1}`
  function learning(row: Learning) {return [({level: '升级', machine: '技能石', blood: '血脉', legendary: '传说'} as Record<string,string>)[row.source] || row.source, row.level != null ? `Lv.${row.level}` : '', row.blood || '', row.requires || ''].filter(Boolean).join(' · ')}
  return <section className="skill-slot" aria-label={`${label}配置与伤害`}>
    <label className="damage-skill-label" htmlFor={`battle-skill-${index}`}>{label}</label>
    <select id={`battle-skill-${index}`} aria-label={label} value={ids[index]} disabled={!hasAttacker || loading} onChange={e => onChange(e.target.value)}><option value="">{hasAttacker ? '选择技能（可留空）' : '先选择攻击方精灵'}</option>{skills.map(row => <option key={row.skill_id} value={row.skill_id} disabled={ids.some((id, slot) => slot !== index && id === String(row.skill_id))}>{row.name} · {row.element} · {row.damage_class} · 威力{row.power}</option>)}</select>
    {skill ? <div className="skill-summary">
      <SkillIcon key={skill.skill_id} skill={skill} />
      <div className="skill-summary-body"><div className="skill-summary-heading"><h3>{skill.name}</h3><span className="skill-element">{skill.element}</span></div><div className="skill-meta">{skill.energy != null && <span>能量: {skill.energy}</span>}<span>{skill.damage_class}</span><span>威力: {overridePower && validPower ? customPower : skill.power}</span></div><p className="skill-description">✦ {skill.description || '效果资料待补齐'}</p></div>
      <div className="skill-damage" aria-live="polite" aria-busy={busy} aria-label={`${label}预计伤害`}>{answer ? <><strong>{answer.estimated_damage.toLocaleString('zh-CN', {maximumFractionDigits: 6})}</strong><span>{answer.damage_percent?.toFixed(1)}%</span></> : <span>{busy ? '计算中…' : '待配置'}</span>}</div>
      {answer?.combo && answer.combo.hits > 1 && <small className="skill-combo-note">连击总伤害 · 单次{answer.combo.single_damage} × {answer.combo.hits}次</small>}
    </div> : <p className="skill-empty">选择技能后自动显示伤害</p>}
    {!validPower && <div className="data-error" role="alert">{label}基础威力请填0～100000的有效数值。</div>}
    {error && <div className="data-error" role="alert">{label}：{error}</div>}
    {skill && <details className="skill-calculation-details"><summary>调整威力与计算详情</summary><label className="power-override"><input aria-label={`${label}调整基础威力`} type="checkbox" checked={overridePower} onChange={e => setOverridePower(e.target.checked)} />按本次触发条件调整基础威力</label>{overridePower && <label className="damage-field"><span>本次基础威力</span><div><input aria-label={`${label}本次基础威力`} type="number" min={0} max={100000} step="any" required value={customPower} onChange={e => setCustomPower(e.target.value)} /></div></label>}<small>{[...new Set(skill.learning.map(learning))].join(' / ')}</small>{answer && <DamageResult answer={answer} autoScroll={false} />}</details>}
  </section>
}

export default function PetBattleForm() {
  const [pets, setPets] = useState<Pet[]>([])
  const [attacker, setAttacker] = useState(emptyBuild)
  const [defender, setDefender] = useState(emptyBuild)
  const attackPanel = usePanel(attacker), defensePanel = usePanel(defender)
  const [skills, setSkills] = useState<Skill[]>([])
  const [skillsLoading, setSkillsLoading] = useState(false)
  const [skillIds, setSkillIds] = useState<string[]>(['', '', '', ''])
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    request<Pet[]>('pets', undefined, controller.signal).then(setPets).catch(e => {if (!controller.signal.aborted) setError(e.message)})
    return () => controller.abort()
  }, [])
  useEffect(() => {
    setSkills([]); setSkillsLoading(false)
    if (!attacker.pet_id) return
    const controller = new AbortController()
    setSkillsLoading(true)
    request<Skill[]>(`pets/${attacker.pet_id}/skills`, undefined, controller.signal).then(rows => {
      if (controller.signal.aborted) return
      setSkills(rows)
      setSkillIds(previous => previous.map(id => rows.some(row => String(row.skill_id) === id) ? id : ''))
    }).catch(e => {if (!controller.signal.aborted) setError(e.message)}).finally(() => {if (!controller.signal.aborted) setSkillsLoading(false)})
    return () => controller.abort()
  }, [attacker.pet_id])
  const ready = !!(attacker.pet_id && defender.pet_id && !skillsLoading && attackPanel.panel?.pet_id === attacker.pet_id && defensePanel.panel?.pet_id === defender.pet_id && !attackPanel.loading && !defensePanel.loading && !attackPanel.error && !defensePanel.error && !buildError(attacker) && !buildError(defender))
  return <div className="damage-layout pet-battle-layout multi-skill-layout"><form onSubmit={event => event.preventDefault()}><fieldset>
    <div className="creature-grid"><CreatureCard side="攻击方" pets={pets} build={attacker} onChange={setAttacker} preview={attackPanel} /><CreatureCard side="受击方" pets={pets} build={defender} onChange={setDefender} preview={defensePanel} /></div>
    <section className="damage-card"><div className="damage-card-heading"><h2>攻击技能对比</h2><span>{skillsLoading ? '读取技能池…' : `${skills.length} 个可选攻击技能 · 最多4个`}</span></div>
      <div className="skill-comparison-grid">{skillIds.map((_, index) => <SkillSlot key={index} index={index} skills={skills} ids={skillIds} onChange={id => setSkillIds(previous => previous.map((value, slot) => slot === index ? id : value))} loading={skillsLoading} hasAttacker={!!attacker.pet_id} ready={ready} attacker={attacker} defender={defender} />)}</div>
      <p className="damage-input-note">各技能按同一组双方配置独立计算。血脉、传说学习条件和变威力按本次对战确认。</p>
    </section>
    {error && <div className="data-error" role="alert">{error}</div>}
    {!ready && <p className="damage-input-note">请完成双方精灵、个体与性格配置，选中的技能会自动显示伤害。</p>}
  </fieldset></form></div>
}
