import { useCallback, useEffect, useRef, useState } from 'react'
import DataPage from './DataPage'
import DamagePage from './DamagePage'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const pageFromHash = () => window.location.hash === '#data' ? 'data' : window.location.hash === '#damage' ? 'damage' : 'chat'

type Trace = {
  sequence: number; event: string; timestamp: string; run_id: string; round?: number;
  name?: string; arguments?: string; call_id?: string; status?: string; answer?: string;
  query_result?: unknown; model_result?: unknown; elapsed_seconds?: number;
  [key: string]: unknown;
}
type Run = { id: string; question: string; answer: string; status: string; done: boolean; elapsed_seconds: number; events: Trace[] }
type Session = { id: string; title: string; model: string; created_at: string; busy: boolean; log_file: string; runs?: Run[] }
type Config = { default_model: string; key_configured: boolean; data: { pets: number; skills_with_details: number; features: number }; tools: string[] }

const questions = ['哪些精灵可以学习丰饶？', '机械方方怎么进化？', '喵喵能学毒沼吗？']
const labels: Record<string, string> = { search_pets: '搜索精灵', get_pet: '精灵资料', get_skill: '技能详情', get_pet_skills: '精灵可学技能', get_skill_pets: '技能反查精灵', compare_pets: '种族值比较', calculate_damage: '伤害计算' }

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    calculator: <><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M8 6h8M8 11h1m6 0h1m-8 5h1m6 0h1" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    chat: <path d="M20 11a8 8 0 0 1-8 8H5l-3 3V11a9 9 0 0 1 18 0Z" />,
    send: <><path d="m4 11 16-7-7 16-2-7-7-2Z" /><path d="m11 13 9-9" /></>,
    arrow: <path d="m9 5 7 7-7 7" />,
    refresh: <><path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5" /></>,
    trash: <><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5m4-5v5" /></>,
    code: <><path d="m8 7-5 5 5 5m8-10 5 5-5 5m-5-12-2 20" /></>,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M15 8V4H4v11h4" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    bolt: <path d="m13 2-8 12h6l-1 8 9-12h-6l1-8Z" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M14 4v16" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v.1" /></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.code}</svg>
}

async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, { method, headers: body === undefined ? {} : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!response.ok) {
    const value = await response.json().catch(() => ({}))
    throw new Error(typeof value.detail === 'string' ? value.detail : `请求失败（${response.status}）`)
  }
  return response.json()
}

function JsonView({ value }: { value: unknown }) {
  const [copied, setCopied] = useState(false)
  const [full, setFull] = useState(false)
  const content = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  return <div className="json-view">
    <div className="json-toolbar"><span>JSON</span><button className="text-button" onClick={async () => { try { await navigator.clipboard.writeText(content ?? ''); setCopied(true); setTimeout(() => setCopied(false), 1600) } catch { setCopied(false) } }}><Icon name={copied ? 'check' : 'copy'} size={13} />{copied ? '已复制' : '复制'}</button></div>
    <pre>{!full && (content?.length || 0) > 40000 ? content?.slice(0, 40000) : content ?? '尚无返回内容'}</pre>
    {!full && (content?.length || 0) > 40000 && <button className="expand-button" onClick={() => setFull(true)}>显示完整内容（{content.length.toLocaleString()} 字符）</button>}
  </div>
}

function Inspector({ run }: { run?: Run }) {
  const [selected, setSelected] = useState('')
  const [tab, setTab] = useState('model')
  const events = run?.events || []
  const calls = events.filter(event => event.event === 'tool_call')
  const results = events.filter(event => event.event === 'tool_result')
  const chosen = calls.find(event => event.call_id === selected) || calls.at(-1)
  const result = results.find(event => event.call_id === chosen?.call_id)
  const rounds = events.filter(event => event.event === 'model_request')
  const config = events.find(event => event.event === 'session_start')
  const parsedArgs = (() => { try { return JSON.parse(chosen?.arguments || '{}') } catch { return chosen?.arguments } })()
  const value = tab === 'raw' ? result?.query_result : tab === 'args' ? parsedArgs : result?.model_result
  return <aside className="inspector">
    <div className="inspector-title"><div><Icon name="bolt" /><h2>执行轨迹</h2></div><span className="muted small">LIVE TRACE</span></div>
    <div className="trace-metrics"><div><strong>{rounds.length.toString().padStart(2, '0')}</strong><span>模型请求</span></div><div><strong>{calls.length.toString().padStart(2, '0')}</strong><span>工具调用</span></div><div><strong>{run?.done ? `${run.elapsed_seconds.toFixed(1)}s` : run ? '…' : '—'}</strong><span>总耗时</span></div></div>
    <div className="timeline">
      {!rounds.length && !calls.length && <div className="trace-empty"><span className="empty-node"><Icon name="code" size={22} /></span><strong>每一步，都有迹可循</strong><p>发送问题后，这里会实时展示模型请求与工具调用。</p></div>}
      {events.filter(event => event.event === 'model_request' || event.event === 'tool_call').map(event => event.event === 'model_request' ?
        <div className="model-step" key={event.sequence}><span className="timeline-dot" /><Icon name="bolt" size={13} /><span>模型请求 <b>#{event.round}</b></span><span className="step-time">{new Date(event.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}</span></div> :
        <button className={'tool-step ' + (event.call_id === chosen?.call_id ? 'selected' : '')} key={event.sequence} onClick={() => setSelected(event.call_id!)}>
          <div className="tool-step-head"><span className="tool-symbol"><Icon name="code" size={15} /></span><span>{labels[event.name!] || event.name}<code>{event.name}</code></span><span className={'status-dot ' + (results.find(r => r.call_id === event.call_id)?.status === 'ok' ? 'success' : results.some(r => r.call_id === event.call_id) ? 'warning' : 'pending')} /></div>
          <div className="arguments-preview">{event.arguments}</div>
        </button>)}
    </div>
    {chosen && <div className="result-inspector"><div className="result-header"><strong>调用详情</strong><span className="small muted">{result?.status || '执行中'}</span></div><div className="tabs">{[['model', '模型视图'], ['raw', '完整结果'], ['args', '参数']].map(([key, title]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{title}</button>)}</div><p className="view-hint">{tab === 'model' ? '实际传给大模型的工具结果' : tab === 'raw' ? '查询层返回的完整资料与来源' : '模型生成的工具调用参数'}</p><JsonView key={`${chosen.call_id}-${tab}`} value={value} /></div>}
    {run && <details className="event-details"><summary>全部事件 <span>{events.length}</span></summary><JsonView value={events} /></details>}
    {config && <details className="event-details"><summary>会话配置</summary><JsonView value={config} /></details>}
    <div className="inspector-note"><Icon name="info" size={14} /><span>展示接口实际返回的事件，模型内部思考保持私密。</span></div>
  </aside>
}

export default function App() {
  const [page, setPage] = useState(pageFromHash)
  const [config, setConfig] = useState<Config>()
  const [sessions, setSessions] = useState<Session[]>([])
  const [selected, setSelected] = useState('')
  const [detail, setDetail] = useState<Session>()
  const [question, setQuestion] = useState('')
  const [model, setModel] = useState('deepseek-v4.1-flash')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [runId, setRunId] = useState('')
  const [showInspector, setShowInspector] = useState(() => window.innerWidth >= 1050)
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const stream = useRef<EventSource | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const runs = detail?.runs || []
  const latestRun = runs.at(-1)
  const activeRun = runs.find(run => run.id === runId) || latestRun
  const busy = detail?.busy || sending

  const dataUpdated = useCallback(() => {
    api<Config>('/config').then(setConfig).catch(e => setError(e.message))
    api<Session[]>('/sessions').then(setSessions).catch(() => {})
    if (selectedRef.current) api<Session>(`/sessions/${selectedRef.current}`).then(setDetail).catch(() => {})
    setRunId('')
  }, [])
  useEffect(() => {
    const change = () => setPage(pageFromHash())
    window.addEventListener('hashchange', change)
    return () => window.removeEventListener('hashchange', change)
  }, [])

  async function refreshList() { setSessions(await api<Session[]>('/sessions')) }

  function attachStream(sessionId: string, id: string) {
    stream.current?.close()
    const events = new EventSource(`/api/sessions/${sessionId}/runs/${id}/events`)
    stream.current = events
    events.onmessage = message => {
      if (selectedRef.current !== sessionId) return
      const event: Trace = JSON.parse(message.data)
      setDetail(previous => previous?.id !== sessionId ? previous : { ...previous, runs: previous.runs?.map(run => {
        if (run.id !== id || run.events.some(item => item.sequence === event.sequence)) return run
        return { ...run, events: [...run.events, event],
          ...(event.event === 'turn_end' ? { answer: event.answer || '', status: event.status || 'error' } : {}),
          ...(event.event === 'run_finished' ? { done: true, elapsed_seconds: event.elapsed_seconds || 0 } : {}) }
      }), busy: event.event === 'run_finished' ? false : previous.busy })
      if (event.event === 'run_finished') {
        events.close()
        setSending(false)
        api<Session>(`/sessions/${sessionId}`).then(value => { if (selectedRef.current === sessionId) setDetail(value) }).catch(e => setError(e.message))
        refreshList().catch(() => {})
      }
    }
    events.onerror = () => {
      api<Session>(`/sessions/${sessionId}`).then(value => {
        if (selectedRef.current !== sessionId) return
        setDetail(value)
        if (!value.busy) { events.close(); setSending(false) }
      }).catch(() => { events.close(); setSending(false); setError('与本地服务的连接中断，请确认服务正在运行。') })
    }
  }

  useEffect(() => {
    Promise.all([api<Config>('/config'), api<Session[]>('/sessions')]).then(([settings, list]) => {
      setConfig(settings); setModel(settings.default_model); setSessions(list)
      if (list.length) setSelected(list[0].id)
    }).catch(e => setError('无法连接本地服务：' + e.message))
    return () => stream.current?.close()
  }, [])

  useEffect(() => {
    stream.current?.close(); setSending(false); setRunId(''); setDetail(undefined)
    if (!selected) return
    let cancelled = false
    api<Session>(`/sessions/${selected}`).then(value => {
      if (cancelled) return
      setDetail(value)
      const running = value.runs?.find(run => !run.done)
      if (running) attachStream(selected, running.id)
    }).catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true; stream.current?.close() }
  }, [selected])

  useEffect(() => { if (runs.length) bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [runs.length, latestRun?.answer, detail?.busy])

  async function newSession() {
    setError(''); setNotice('')
    try {
      const value = await api<Session>('/sessions', 'POST', { model })
      setSelected(value.id); await refreshList(); input.current?.focus()
    } catch (e) { setError((e as Error).message) }
  }

  async function send() {
    if (!question.trim() || busy || loading) return
    setSending(true); setError(''); setNotice('')
    const text = question.trim()
    try {
      let id = selected
      if (!id) {
        const created = await api<Session>('/sessions', 'POST', { model })
        id = created.id
        // 创建与首次提问分两步；会话选择 effect 在服务端读取新状态。
        setSelected(id); selectedRef.current = id
      }
      const value = await api<{ run_id: string }>(`/sessions/${id}/runs`, 'POST', { question: text })
      setQuestion(''); setRunId(value.run_id)
      const snapshot = await api<Session>(`/sessions/${id}`)
      if (selectedRef.current === id) { setDetail(snapshot); attachStream(id, value.run_id) }
      await refreshList()
    } catch (e) { setError((e as Error).message); setSending(false) }
  }

  async function reset() {
    if (!selected || busy) return
    try { setDetail(await api<Session>(`/sessions/${selected}/reset`, 'POST')); setRunId(''); setNotice('会话上下文已清空，原始日志已保留。'); await refreshList() }
    catch (e) { setError((e as Error).message) }
  }

  async function reloadData() {
    setLoading(true); setError('')
    try {
      setConfig(await api<Config>('/data/reload', 'POST'))
      if (selected) setDetail(await api<Session>(`/sessions/${selected}`))
      setRunId(''); setNotice('JSON 已重新加载，会话上下文已清空，原始日志已保留。'); await refreshList()
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }

  return <div className="workbench">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Roco 调试台首页"><span className="brand-mark">R</span><div><strong>Roco<span> / </span></strong><small>AGENT WORKBENCH</small></div></a>
      <nav className="page-nav" aria-label="功能导航"><a href="#chat" aria-label="对话调试" className={page === 'chat' ? 'active' : ''}><Icon name="chat" /><span>对话调试</span></a><a href="#data" aria-label="数据检测" className={page === 'data' ? 'active' : ''}><Icon name="refresh" /><span>数据检测</span></a><a href="#damage" aria-label="伤害计算" className={page === 'damage' ? 'active' : ''}><Icon name="calculator" /><span>伤害计算</span></a></nav>
      <button className="new-session" onClick={() => {window.location.hash = 'chat'; newSession()}}><Icon name="plus" size={17} />新建会话<span>＋</span></button>
      <div className="sidebar-section-label">调试会话 <span>{sessions.length}</span></div>
      <nav className="sessions" aria-label="会话列表">{!sessions.length && <p className="sidebar-empty">你的调试记录会出现在这里</p>}{sessions.map(session => <button key={session.id} className={'session-link ' + (session.id === selected ? 'active' : '')} onClick={() => { window.location.hash = 'chat'; setSelected(session.id); setError(''); setNotice('') }}><Icon name="chat" size={15} /><span>{session.title}</span>{session.busy && <i className="status-dot pending" />}</button>)}</nav>
      {page === 'chat' && <div className="model-card"><label htmlFor="model">新会话模型 <span>MODEL</span></label><input id="model" value={model} onChange={e => setModel(e.target.value)} list="models" autoComplete="off" /><datalist id="models"><option value="deepseek-v4.1-flash" /><option value="deepseek-v4.1-flash-1017" /></datalist><p><span className={'status-dot ' + (config?.key_configured ? 'success' : 'warning')} />{config?.key_configured ? '服务端密钥已配置' : '请在服务端设置 ZZZ_API_KEY'}</p></div>}
      <div className="sidebar-footer"><span className="local-symbol">⌘</span><div>本地开发环境<small>JSON 数据 · 127.0.0.1</small></div><span className="version">v0.1</span></div>
    </aside>
    <section className="workspace">
      <header className="topbar"><div className="breadcrumb">工作台 <span>/</span> <strong>{page === 'data' ? '数据检测' : page === 'damage' ? '伤害计算' : '对话调试'}</strong><span className="local-badge">LOCAL</span></div><div className="header-actions">{page === 'chat' && <><button className={'icon-button ' + (loading ? 'spinning' : '')} disabled={loading || busy} onClick={reloadData} title="重新加载 JSON 并清空会话上下文" aria-label="重新加载数据"><Icon name="refresh" /></button><span className="header-divider" /><button className={'icon-button ' + (showInspector ? 'is-on' : '')} onClick={() => setShowInspector(!showInspector)} title="显示或隐藏执行轨迹" aria-label="切换执行轨迹"><Icon name="panel" /></button></>}</div></header>
      {page === 'data' ? <DataPage onUpdated={dataUpdated} /> : page === 'damage' ? <DamagePage /> : <div className={'main-grid ' + (!showInspector ? 'inspector-hidden' : '')}>
        <main className="chat-panel">
          <div className="chat-heading"><div><span className="section-kicker">PLAYGROUND</span><h1>对话调试</h1></div><button className="text-button" disabled={!runs.length || busy} onClick={reset}><Icon name="trash" size={14} />清空上下文</button></div>
          {(error || notice) && <div role={error ? 'alert' : 'status'} className={'banner ' + (error ? 'error' : '')}><Icon name="info" size={15} /><span>{error || notice}</span><button onClick={() => { setError(''); setNotice('') }} aria-label="关闭提示">×</button></div>}
          <div className="conversation">
            {!runs.length && <div className="welcome"><div className="welcome-icon"><Icon name="chat" size={29} /><span>✦</span></div><span className="welcome-kicker">从一个好问题开始</span><h2>今天要验证哪个问题？</h2><p>和 Roco 助手聊聊，在右侧观察每一次工具调用。</p><div className="suggestions">{questions.map((value, index) => <button key={value} onClick={() => { setQuestion(value); input.current?.focus() }}><span className="suggestion-icon">{['↗', '⌘', '◇'][index]}</span><span>{value}</span><Icon name="arrow" size={13} /></button>)}</div><div className="welcome-foot"><Icon name="code" size={13} />{config?.tools.length || 7} 个工具<span>·</span>多轮上下文<span>·</span>实时轨迹</div></div>}
            {runs.map((run, index) => <article className={'turn ' + (activeRun?.id === run.id ? 'active-turn' : '')} key={run.id} onClick={() => setRunId(run.id)}><div className="user-message"><span className="speaker-label">你</span><div>{run.question}</div></div><div className="assistant-message"><span className="assistant-avatar">R</span><div className="assistant-content"><div className="assistant-label"><strong>Roco</strong><span>{detail?.model}</span>{run.done && <button className="turn-trace" onClick={() => { setRunId(run.id); setShowInspector(true) }}><Icon name="bolt" size={11} />轨迹 #{index + 1}</button>}</div>{run.answer ? <div className={'markdown ' + (run.status !== 'ok' ? 'answer-error' : '')}><Markdown remarkPlugins={[remarkGfm]}>{run.answer}</Markdown></div> : <div className="thinking"><span /><span /><span /><small>{run.events.filter(event => event.event === 'tool_call').at(-1)?.name ? `正在查询 · ${labels[run.events.filter(event => event.event === 'tool_call').at(-1)!.name!] || '工具执行中'}` : '模型正在处理问题'}</small></div>}{run.done && <div className="answer-footer"><span className={'status-dot ' + (run.status === 'ok' ? 'success' : 'warning')} />{run.status === 'ok' ? '执行完成' : run.status}<span>·</span><Icon name="clock" size={11} />{run.elapsed_seconds.toFixed(1)}s<span>·</span>{run.events.filter(event => event.event === 'tool_call').length} 次工具调用</div>}</div></div></article>)}
            <div ref={bottom} />
          </div>
          <div className="composer-area"><div className={'composer ' + (busy ? 'is-busy' : '')}><textarea ref={input} aria-label="输入调试问题" placeholder="输入问题，看看 Agent 会如何调用工具…" value={question} maxLength={4000} disabled={busy} rows={2} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} /><div className="composer-bottom"><span><span className="status-dot success" />{detail?.model || model}</span><button className="send-button" onClick={send} disabled={!question.trim() || busy || loading} aria-label="发送问题" title="发送问题">{busy ? <span className="spinner" /> : <Icon name="send" size={17} />}</button></div></div><div className="composer-hint"><span>Enter 发送 · Shift + Enter 换行</span><span>记录保存在本地 · 密钥由后端管理</span></div></div>
        </main>
        {showInspector && <Inspector run={activeRun} />}
      </div>}
    </section>
  </div>
}
