import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api.js'
import { Panel, QueryView } from '../components/Panel.jsx'

const TYPE_OPTIONS = ['', 'CROSS_CHAIN_ARBITRAGE', 'CEX_ARBITRAGE', 'FUNDING_ARBITRAGE', 'DEX_ARBITRAGE', 'LAUNCH_ARBITRAGE', 'FLASH_LOAN']
const STATUS_OPTIONS = ['', 'pending', 'verified', 'confirmed', 'rejected']

export default function Opportunities() {
  const [type, setType] = useState('')
  const [status, setStatus] = useState('')
  const [limit, setLimit] = useState(50)

  const q = useQuery({
    queryKey: ['opportunities', type, status, limit],
    queryFn: () => api.opportunities({ type: type || undefined, status: status || undefined, limit }),
    refetchInterval: 30_000,
  })

  return (
    <div className="space-y-6" data-testid="page-opportunities">
      <header>
        <div className="label-mono">opportunities</div>
        <h1 className="text-3xl font-semibold tracking-tight">Verifier output</h1>
        <p className="text-sm text-ink-400 mt-1">Filter and inspect canonical opportunities (read-only).</p>
      </header>

      <Panel title="Filters" subtitle="query" testid="card-filters">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label>
            <span className="label-mono mb-1 block">type</span>
            <select className="input" value={type} onChange={(e) => setType(e.target.value)} data-testid="filter-type">
              {TYPE_OPTIONS.map((v) => <option key={v} value={v}>{v || 'any'}</option>)}
            </select>
          </label>
          <label>
            <span className="label-mono mb-1 block">status</span>
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} data-testid="filter-status">
              {STATUS_OPTIONS.map((v) => <option key={v} value={v}>{v || 'any'}</option>)}
            </select>
          </label>
          <label>
            <span className="label-mono mb-1 block">limit</span>
            <select className="input" value={limit} onChange={(e) => setLimit(Number(e.target.value))} data-testid="filter-limit">
              {[25, 50, 100, 200, 500].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        </div>
      </Panel>

      <Panel title={`Results (${q.data?.count ?? 0})`} subtitle="latest first" testid="card-results">
        <QueryView q={q} testidPrefix="results" empty={(d) => !d?.items?.length}>
          {(d) => (
            <div className="overflow-auto -mx-2">
              <table className="min-w-full text-xs" data-testid="opportunities-table">
                <thead className="text-ink-400">
                  <tr className="border-b border-bg-line">
                    <th className="text-left font-medium px-2 py-2">type</th>
                    <th className="text-left font-medium px-2 py-2">subject</th>
                    <th className="text-left font-medium px-2 py-2">asset</th>
                    <th className="text-left font-medium px-2 py-2">status</th>
                    <th className="text-right font-medium px-2 py-2">confidence</th>
                    <th className="text-right font-medium px-2 py-2">return %</th>
                    <th className="text-left font-medium px-2 py-2">id</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.items || []).map((o) => (
                    <tr key={o.opportunity_id || o.id} className="border-b border-bg-line/60 table-row-hover" data-testid="opportunity-row">
                      <td className="px-2 py-2 font-mono">{o.opportunity_type || ''}</td>
                      <td className="px-2 py-2 font-mono text-ink-200">{o.subject_id || ''}</td>
                      <td className="px-2 py-2">{o.asset || ''}</td>
                      <td className="px-2 py-2">
                        <StatusPill status={o.status || o.decision} />
                      </td>
                      <td className="px-2 py-2 text-right font-mono">{fmtPct(o.confidence_score)}</td>
                      <td className="px-2 py-2 text-right font-mono">{fmtPct(o.expected_return_pct)}</td>
                      <td className="px-2 py-2 font-mono text-ink-400 truncate max-w-[18rem]">{o.opportunity_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryView>
      </Panel>
    </div>
  )
}

function StatusPill({ status }) {
  if (!status) return <span className="pill bg-bg-raised text-ink-400">—</span>
  const map = {
    confirmed: 'pill-green',
    verified: 'pill-violet',
    pending: 'pill-amber',
    rejected: 'pill-red',
  }
  const cls = map[status] || 'pill bg-bg-raised text-ink-200'
  return <span className={cls}>{status}</span>
}

function fmtPct(v) {
  if (v == null || isNaN(Number(v))) return '—'
  return `${(Number(v) * (Number(v) <= 1 ? 100 : 1)).toFixed(2)}`
}
