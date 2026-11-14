import { useEffect, useState } from 'react'
import {typeIcons} from './typeIcons'
import DamageResult, {type DamageAnswer} from './DamageResult'
import BuffEditor, {buffPayload, emptyBuffs, type CombatBuffDraft} from './BuffEditor'

type Stat = 'hp' | 'atk' | 'def' | 'spa' | 'spd' | 'spe'
const stats: [Stat, string][] = [['hp', '生命'], ['atk', '物攻'], ['def', '物防'], ['spa', '魔攻'], ['spd', '魔防'], ['spe', '速度']]
type Pet = {pet_id: number; name: string; types: string[]; level_editable: boolean; image_url?: string | null}
type Build = {pet_id?: number; name: string; level: string; stars: string; growth: string; nature_plus: Stat | ''; nature_minus: Stat | ''; ivs: Record<Stat, string>; buffs: CombatBuffDraft}
type Panel = Pet & {base_stats: Record<Stat, number>; stats: Record<Stat, number>; current_hp: number; feature: {name?: string; description?: string}; type_effectiveness: Record<string, {type: string; multiplier: number}[]>}
type Learning = {source: string; level?: number; blood?: string; requires?: string}
type Skill = {skill_id: number; name: string; power: number; element: string; damage_class: string; description: string; learning: Learning[]}
const emptyBuild = (): Build => ({name: '', level: '60', stars: '5', growth: '50', nature_plus: '', nature_minus: '', ivs: {hp: '0', atk: '0', def: '0', spa: '0', spd: '0', spe: '0'}, buffs: emptyBuffs()})
async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api/damage/' + path, {method: body === undefined ? 'GET' : 'POST', signal, headers: body === undefined ? {} : {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)})
  const value = await response.json()
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : Array.isArray(value.detail) ? value.detail.map((item: {msg: string}) => item.msg).join('；') : '请求失败，请检查配置。')
  return value
}
function buildError(build: Build) {
  if (Object.values(build.buffs).some(value => value === '' || !Number.isInteger(Number(value)))) return 'Buff变化值与连击增减请填整数。'
  if (build.level === '' || !Number.isInteger(Number(build.level)) || Number(build.level) < 1 || Number(build.level) > 100) return '入场等级请填1～100的整数。'
  if (build.stars === '' || !Number.isInteger(Number(build.stars)) || Number(build.stars) < 0 || Number(build.stars) > 10) return '星级请填0～10的整数。'
  if (build.growth === '' || !Number.isInteger(Number(build.growth)) || Number(build.growth) < 0 || Number(build.growth) > 100) return '成长等级请填0～100的整数。'
  if (Number(build.growth) < Number(build.stars) * 10) return '成长等级需达到星级的10倍。'
  if (!!build.nature_plus !== !!build.nature_minus) return '请选择性格的正面和负面能力，或两项均选无修正。'
  if (build.nature_plus && build.nature_plus === build.nature_minus) return '性格的正面和负面能力需选择不同项。'
  if (Object.values(build.ivs).some(value => value === '' || !Number.isInteger(Number(value)) || Number(value) < 0 || Number(value) > 60)) return '个体值请填0～60的整数。'
  if (Object.values(build.ivs).filter(value => Number(value) > 0).length > 3) return '当前社区规则最多设置3项非零个体。'
  return ''
}
function payload(build: Build) {
  return {pet_id: build.pet_id, level: Number(build.level), stars: Number(build.stars), growth: Number(build.growth), ivs: Object.fromEntries(Object.entries(build.ivs).map(([key, value]) => [key, Number(value)])), nature_plus: build.nature_plus || null, nature_minus: build.nature_minus || null, buffs: buffPayload(build.buffs)}
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
  return <div className="creature-avatar">{pet.image_url && !failed ? <img src={pet.image_url} alt={pet.name} width={64} height={64} referrerPolicy="no-referrer" onError={() => setFailed(true)} /> : <b aria-label="暂无精灵图片">{pet.name.slice(0, 1)}</b>}</div>
}

function TypeIcon({name}: {name: string}) {
  const [failed, setFailed] = useState(false)
  const url = typeIcons[name.replace(/系$/, '')]
  return <span className="creature-type-icon" title={name}>{failed || !url ? name : <img src={url} alt={name} width={28} height={28} referrerPolicy="no-referrer" onError={() => setFailed(true)} />}</span>
}

function CreatureCard({side, pets, build, onChange, preview}: {side: string; pets: Pet[]; build: Build; onChange: (value: Build) => void; preview: ReturnType<typeof usePanel>}) {
  const count = Object.values(build.ivs).filter(value => Number(value) > 0).length
  const pet = pets.find(row => row.pet_id === build.pet_id)
  return <section className="damage-card creature-card"><div className="damage-card-heading"><h2>{side}</h2><span>{build.level || '—'}级 · {build.stars || '—'}星 · 成长{build.growth || '—'}</span></div>
    <label className="damage-skill-label" htmlFor={`${side}-pet`}>选择{side}精灵</label><input id={`${side}-pet`} className="pet-search-input" aria-label={`${side}精灵`} list={`${side}-pets`} placeholder="输入精灵名称并从列表选择" value={build.name} onChange={e => {const next = pets.find(row => row.name === e.target.value); onChange({...build, name: e.target.value, pet_id: next?.pet_id, level: next?.level_editable ? build.level : '60'})}} autoComplete="off" /><datalist id={`${side}-pets`}>{pets.map(row => <option value={row.name} key={row.pet_id}>{row.types.join(' / ')}</option>)}</datalist>
    {pet && <div className="creature-identity"><div className="creature-name"><PetAvatar key={pet.pet_id} pet={pet} /><strong>{pet.name}</strong></div><div className="creature-types" aria-label="精灵系别">{pet.types.map(name => <TypeIcon key={name} name={name} />)}</div></div>}
    {!pet && <p className="damage-input-note">选择具体精灵后，读取种族值并换算面板。</p>}
    {pet?.level_editable && <label className="damage-field cultivation-fields"><span>实际入场等级</span><div><input aria-label={`${side}入场等级`} type="number" min={1} max={100} step={1} required value={build.level} onChange={e => onChange({...build, level: e.target.value})} /><em>级</em></div><small>按特性生效后的实际等级填写，用于换算面板。</small></label>}
    <div className="damage-field-grid cultivation-fields"><label className="damage-field"><span>星级</span><div><input aria-label={`${side}星级`} type="number" min={0} max={10} step={1} required value={build.stars} onChange={e => onChange({...build, stars: e.target.value})} /><em>星</em></div></label><label className="damage-field"><span>成长等级</span><div><input aria-label={`${side}成长等级`} type="number" min={0} max={100} step={1} required value={build.growth} onChange={e => onChange({...build, growth: e.target.value})} /></div></label></div>
    <div className="damage-field-grid cultivation-fields">{(['nature_plus', 'nature_minus'] as const).map(key => <label className="damage-field" key={key}><span>性格{key === 'nature_plus' ? '正面提升' : '负面降低'}</span><select aria-label={`${side}性格${key === 'nature_plus' ? '正面' : '负面'}`} value={build[key]} onChange={e => onChange({...build, [key]: e.target.value as Stat | ''})}><option value="">无修正</option>{stats.map(([stat, title]) => <option key={stat} value={stat} disabled={stat === build[key === 'nature_plus' ? 'nature_minus' : 'nature_plus']}>{title}{key === 'nature_plus' ? `↑${10 + 2 * Number(build.stars)}%` : '↓10%'}</option>)}</select></label>)}</div>
    <div className="iv-table"><div className="iv-row iv-head"><span>能力</span><span>种族</span><span>个体</span><span>估算面板</span></div>{stats.map(([key, title]) => <div className="iv-row" key={key}><span>{title}</span><span>{preview.panel?.base_stats[key] ?? '—'}</span><div className="iv-control"><input aria-label={`${side}${title}个体`} type="number" min={0} max={60} step={1} required value={build.ivs[key]} onChange={e => onChange({...build, ivs: {...build.ivs, [key]: e.target.value}})} /><button type="button" className="iv-max" aria-label={`${side}${title}个体拉满`} title="填满60" disabled={count >= 3 && Number(build.ivs[key]) === 0} onClick={() => onChange({...build, ivs: {...build.ivs, [key]: '60'}})}>拉满</button></div><strong>{preview.loading ? '…' : preview.panel?.stats[key] ?? '—'}</strong></div>)}</div>
    <p className="damage-input-note">个体0～60整数 · 拉满填60 · 已设置 {count}/3 项 · 性格按所选增减项换算</p>
    <BuffEditor side={side} value={build.buffs} onChange={buffs => onChange({...build, buffs})} />
    {preview.panel?.feature.name && <details className="creature-feature"><summary>特性：{preview.panel.feature.name}</summary><p>{preview.panel.feature.description}</p><small>本次生效效果通过下方战斗Buff填写。</small></details>}
    {preview.error && <div className="data-error" role="alert">{preview.error}</div>}
  </section>
}
export default function PetBattleForm() {
  const [pets, setPets] = useState<Pet[]>([])
  const [attacker, setAttacker] = useState(emptyBuild)
  const [defender, setDefender] = useState(emptyBuild)
  const attackPanel = usePanel(attacker), defensePanel = usePanel(defender)
  const [skills, setSkills] = useState<Skill[]>([])
  const [skillsLoading, setSkillsLoading] = useState(false)
  const [skillId, setSkillId] = useState('')
  const [customPower, setCustomPower] = useState('')
  const [overridePower, setOverridePower] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState<DamageAnswer>()
  const skill = skills.find(row => String(row.skill_id) === skillId)
  useEffect(() => {
    const controller = new AbortController()
    request<Pet[]>('pets', undefined, controller.signal).then(setPets).catch(e => {if (!controller.signal.aborted) setError(e.message)})
    return () => controller.abort()
  }, [])
  useEffect(() => {
    setSkills([]); setSkillId(''); setSkillsLoading(false)
    if (!attacker.pet_id) return
    const controller = new AbortController()
    setSkillsLoading(true)
    request<Skill[]>(`pets/${attacker.pet_id}/skills`, undefined, controller.signal).then(setSkills).catch(e => {if (!controller.signal.aborted) setError(e.message)}).finally(() => {if (!controller.signal.aborted) setSkillsLoading(false)})
    return () => controller.abort()
  }, [attacker.pet_id])
  useEffect(() => {setOverridePower(false); setCustomPower(skill ? String(skill.power) : '')}, [skill])
  useEffect(() => {setAnswer(undefined)}, [attacker, defender, skillId, customPower, overridePower])
  const ready = !!(skill && attackPanel.panel && defensePanel.panel && !attackPanel.loading && !defensePanel.loading && !attackPanel.error && !defensePanel.error)
  const attackKey = skill?.damage_class === '物攻' ? 'atk' : 'spa', defenseKey = skill?.damage_class === '物攻' ? 'def' : 'spd'
  const stab = skill && attackPanel.panel?.types.includes(skill.element) ? 1.25 : 1
  const type = skill && defensePanel.panel ? Object.values(defensePanel.panel.type_effectiveness).flat().find(row => row.type === skill.element)?.multiplier ?? 1 : 1
  async function calculate(event: React.FormEvent) {
    event.preventDefault()
    if (!ready) return
    setBusy(true); setError(''); setAnswer(undefined)
    try {
      const result = await request<DamageAnswer>('matchup', {attacker: payload(attacker), defender: payload(defender), skill_id: Number(skillId), power_override: overridePower ? Number(customPower) : null})
      setAnswer(result)
    } catch(e) {setError((e as Error).message)} finally {setBusy(false)}
  }
  function learning(row: Learning) {return [({level: '升级', machine: '技能石', blood: '血脉', legendary: '传说'} as Record<string,string>)[row.source] || row.source, row.level != null ? `Lv.${row.level}` : '', row.blood || '', row.requires || ''].filter(Boolean).join(' · ')}
  return <div className="damage-layout pet-battle-layout"><form onSubmit={calculate}><fieldset disabled={busy}>
    <div className="creature-grid"><CreatureCard side="攻击方" pets={pets} build={attacker} onChange={setAttacker} preview={attackPanel} /><CreatureCard side="受击方" pets={pets} build={defender} onChange={setDefender} preview={defensePanel} /></div>
    <section className="damage-card"><div className="damage-card-heading"><h2>攻击技能</h2><span>{skillsLoading ? '读取技能池…' : `${skills.length} 个可选攻击技能`}</span></div><label className="damage-skill-label" htmlFor="battle-skill">从攻击方技能池选择</label><select id="battle-skill" value={skillId} disabled={!attacker.pet_id || skillsLoading} required onChange={e => setSkillId(e.target.value)}><option value="">{attacker.pet_id ? '选择本次攻击技能' : '先选择攻击方精灵'}</option>{skills.map(row => <option key={row.skill_id} value={row.skill_id}>{row.name} · {row.element} · {row.damage_class} · 威力{row.power}</option>)}</select>
      {skill && <><div className="damage-skill-note"><strong>{skill.name} · {skill.element} · {skill.damage_class}</strong><p>{skill.description}</p><small>{[...new Set(skill.learning.map(learning))].join(' / ')}</small></div><div className="matchup-auto"><div><span>{skill.damage_class === '物攻' ? '物攻 → 物防' : '魔攻 → 魔防'}</span><strong>{attackPanel.panel?.stats[attackKey] ?? '—'} → {defensePanel.panel?.stats[defenseKey] ?? '—'}</strong></div><div><span>本系倍率</span><strong>×{stab}</strong></div><div><span>克制倍率</span><strong>×{type}</strong></div></div><label className="power-override"><input type="checkbox" checked={overridePower} onChange={e => setOverridePower(e.target.checked)} />按本次触发条件手动调整基础威力</label>{overridePower && <label className="damage-field"><span>本次基础威力</span><div><input aria-label="本次技能基础威力" type="number" min={0} max={100000} step="any" required value={customPower} onChange={e => setCustomPower(e.target.value)} /></div></label>}<p className="damage-input-note">本系与克制读取双方属性及本地克制表。血脉、传说学习条件和条件变威力请按本次对战确认。</p></>}
    </section>
    {error && <div className="data-error" role="alert">{error}</div>}
    <button type="submit" className="damage-submit" disabled={busy || !ready}>{busy ? '正在计算…' : '计算预计伤害'}<span>↗</span></button>
    {!ready && <p className="damage-input-note">请完成双方精灵、个体与性格配置，并选择一个攻击技能。</p>}
  </fieldset></form><DamageResult answer={answer} /></div>
}
