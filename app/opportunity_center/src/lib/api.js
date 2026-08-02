// Thin API client for ArbiCore Opportunity Center.
// All requests are credentialed (cookie-based JWT). All endpoints are read-only.

const BASE = import.meta.env.VITE_BACKEND_URL || ''

async function request(path, { method = 'GET', body, signal } = {}) {
  const url = `${BASE}${path}`
  const opts = {
    method,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    signal,
  }
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(url, opts)
  if (res.status === 401) {
    const err = new Error('unauthorized')
    err.status = 401
    throw err
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try { const j = await res.json(); msg = j.detail || msg } catch { /* noop */ }
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  return res.json()
}

export const api = {
  // auth
  login: (username, password) =>
    request('/api/auth/login', { method: 'POST', body: { username, password } }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),

  // arbicore — existing
  health: () => request('/api/arbicore/health'),
  opportunities: ({ type, status, limit = 50 } = {}) => {
    const qs = new URLSearchParams()
    if (type) qs.set('type', type)
    if (status) qs.set('status', status)
    qs.set('limit', String(limit))
    return request(`/api/arbicore/opportunities?${qs}`)
  },
  opportunity: (id) => request(`/api/arbicore/opportunities/${encodeURIComponent(id)}`),

  // arbicore — opportunity-center additions (Phase 1)
  wallets: ({ label, label_source, chain, limit = 100, offset = 0 } = {}) => {
    const qs = new URLSearchParams()
    if (label) qs.set('label', label)
    if (label_source) qs.set('label_source', label_source)
    if (chain) qs.set('chain', chain)
    qs.set('limit', String(limit))
    qs.set('offset', String(offset))
    return request(`/api/arbicore/wallets?${qs}`)
  },
  walletsGetMany: (addresses) =>
    request('/api/arbicore/wallets/get_many', { method: 'POST', body: { addresses } }),
  auditLog: ({ limit = 50, since } = {}) => {
    const qs = new URLSearchParams()
    qs.set('limit', String(limit))
    if (since) qs.set('since', String(since))
    return request(`/api/arbicore/audit_log?${qs}`)
  },
  systemCollections: () => request('/api/arbicore/system/collections'),
  discoveryStats: (window = '1h') =>
    request(`/api/arbicore/discovery_candidates/stats?window=${encodeURIComponent(window)}`),
  analyticsTimeseries: ({ metric, window = '24h', bucket = '1h' }) =>
    request(`/api/arbicore/analytics/timeseries?metric=${metric}&window=${window}&bucket=${bucket}`),
  analyticsFunnel: (window = '24h') =>
    request(`/api/arbicore/analytics/funnel?window=${encodeURIComponent(window)}`),
}
