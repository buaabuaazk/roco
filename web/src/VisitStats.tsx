import {useEffect, useState} from 'react'

type Stats = {total_pv: number; today_pv: number; today_uv: number; days: {day: string; pv: number; uv: number}[]}
export default function VisitStats() {
  const [stats, setStats] = useState<Stats>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function refresh(signal?: AbortSignal) {
    setBusy(true)
    try {
      const response = await fetch('/api/visits/stats', {signal})
      if (!response.ok) throw new Error('访问统计读取失败')
      const value: Stats = await response.json()
      if (!signal?.aborted) {setStats(value); setError('')}
    } catch (e) {if (!signal?.aborted) setError((e as Error).message)}
    finally {if (!signal?.aborted) setBusy(false)}
  }
  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal)
    return () => controller.abort()
  }, [])
  return <section className="data-check-card visit-stats"><div className="data-module-heading"><h2>网站访问统计</h2><button className="data-check-button" disabled={busy} onClick={() => void refresh()}>{busy ? '读取中…' : '刷新统计'}</button></div>
    <div className="data-stat-grid">{[['今日访问次数', stats?.today_pv], ['今日独立访客', stats?.today_uv], ['累计访问次数', stats?.total_pv]].map(([label, value]) => <div className="data-stat" key={label}><span>{label}</span><strong>{value?.toLocaleString() ?? '—'}</strong></div>)}</div>
    {error && <div className="data-error" role="alert">{error}</div>}
    <details className="visit-history"><summary>最近7天</summary><div className="data-table-wrap"><table><thead><tr><th>日期</th><th>访问次数</th><th>独立访客</th></tr></thead><tbody>{stats?.days.map(day => <tr key={day.day}><td>{day.day}</td><td>{day.pv}</td><td>{day.uv}</td></tr>)}</tbody></table></div></details>
    <p className="data-scope">按北京时间统计。打开或刷新公开页面记一次访问；独立访客按浏览器去重。清理浏览器存储或更换设备会重新计数。</p>
  </section>
}
