// 只在公开版页面首次挂载时记录一次，不统计计算接口调用。
export function recordVisit() {
  let visitorId: string | null = null
  try {
    visitorId = localStorage.getItem('roco.visitor-id')
    if (!visitorId || !/^[a-f0-9]{32}$/.test(visitorId)) {
      visitorId = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
      localStorage.setItem('roco.visitor-id', visitorId)
    }
  } catch { visitorId = null }
  void fetch('/api/visits', {method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({visitor_id: visitorId})}).catch(() => {})
}
