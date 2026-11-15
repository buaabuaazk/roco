import { useEffect, useState } from 'react'
import VisitStats from './VisitStats'

type Change = {title: string; local_revision: number; remote_revision: number; remote_timestamp: string; conversion_rule: boolean}
type Status = {busy: boolean; operation: string | null; message: string; error: string | null; updated_at: string | null;
  local?: {converted_at: string; pets: number; skills: number; features: number};
  report: null | {status: string; checked_at: string; checked_modules: number; unchanged_modules: number; changed_modules: Change[]; unavailable_modules: string[]}}
const time = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN', {hour12: false}) : '—'
async function request(path: string, method = 'GET'): Promise<Status> {
  const response = await fetch('/api/data/' + path, {method})
  const result = await response.json()
  if (!response.ok) throw new Error(result.detail || '请求失败')
  return result
}
export default function DataPage({onUpdated}: {onUpdated: () => void}) {
  const [status, setStatus] = useState<Status>()
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  useEffect(() => {
    let cancelled = false, timer: ReturnType<typeof setTimeout>
    let updateStamp: string | null = null
    async function poll() {
      try {
        const value = await request('status')
        if (cancelled) return
        setStatus(value); setError('')
        if (!value.busy && value.operation === 'update' && value.updated_at !== updateStamp) onUpdated()
        updateStamp = value.updated_at
        timer = setTimeout(poll, value.busy ? 700 : 3000)
      } catch (e) { if (!cancelled) {setError((e as Error).message); timer = setTimeout(poll, 3000)} }
    }
    poll()
    return () => {cancelled = true; clearTimeout(timer)}
  }, [onUpdated])
  async function run(operation: string) {
    setSubmitting(true); setError('')
    try {const value = await request(operation, 'POST'); setStatus(previous => ({...value, local: previous?.local}))} catch(e) {setError((e as Error).message)}
    finally {setSubmitting(false)}
  }
  const report = status?.report
  const changed = report?.changed_modules || []
  const busy = submitting || status?.busy
  return <main className="data-page">
    <div className="data-page-heading"><div><span className="section-kicker">DATA CENTER</span><h1>数据检测</h1><p>对比 BWIKI 模块版本，将最新资料同步到本地 JSON。</p></div><span className="source-tag">BWIKI · 模块采集</span></div>
    <VisitStats />
    <div className="data-stat-grid">{[['精灵', status?.local?.pets], ['技能', status?.local?.skills], ['特性', status?.local?.features]].map(([label, count]) => <div className="data-stat" key={label}><span>{label}</span><strong>{count?.toLocaleString() ?? '—'}</strong><small>本地正式数据</small></div>)}</div>
    <section className="data-check-card">
      <div className="data-check-header"><div><h2>{status?.busy ? '任务执行中' : report?.status === 'up_to_date' ? '已是最新版本' : changed.length ? `发现 ${changed.length} 个模块有更新` : '检查资料更新'}</h2><p>检测只读取模块版本；一键更新会下载、转换并校验完整数据。</p></div><span className={'data-state ' + (busy ? 'working' : '')}>{busy ? '处理中' : report?.status === 'up_to_date' ? '已同步' : changed.length ? '有更新' : '待检测'}</span></div>
      <div className="data-job-message" role="status">{status?.busy && <span className="spinner" />}{status?.message || '正在读取本地信息…'}</div>
      {(error || status?.error) && <div className="data-error" role="alert">{error || status?.error}</div>}
      <div className="data-actions"><button className="data-check-button" disabled={busy} onClick={() => run('check')}>检测更新</button><button className="data-update-button" disabled={busy || !changed.length || !!report?.unavailable_modules.length} onClick={() => run('update')}>一键更新</button><span>更新成功后自动加载，会话上下文将清空。</span></div>
      <div className="data-times"><span>本地转换时间：{time(status?.local?.converted_at)}</span><span>最近检测：{time(report?.checked_at)}</span></div>
    </section>
    {report && <section className="data-module-card"><div className="data-module-heading"><h2>模块版本差异</h2><span>已检查 {report.checked_modules} 个 · {report.unchanged_modules} 个一致</span></div>
      {report.unavailable_modules.length > 0 && <div className="data-error">以下模块检测失败，请重新检测：{report.unavailable_modules.join('、')}</div>}
      {changed.length ? <div className="data-table-wrap"><table><thead><tr><th>模块</th><th>本地版本</th><th>最新版本</th><th>上游更新时间</th></tr></thead><tbody>{changed.map(row => <tr key={row.title}><td>{row.title}{row.conversion_rule && <small>转换规则</small>}</td><td><code>{row.local_revision}</code></td><td><code>{row.remote_revision}</code></td><td>{time(row.remote_timestamp)}</td></tr>)}</tbody></table></div> : <div className="data-no-changes">{report.status === 'up_to_date' ? '当前采集范围内的模块版本全部一致。' : '请完成模块检测。'}</div>}
    </section>}
    <p className="data-scope">检测范围：采集器使用的精灵、技能、特性和关联规则模块。页面正文、图片与模块之外的攻略内容另行采集。网络或转换失败时保留原有正式数据。</p>
  </main>
}
