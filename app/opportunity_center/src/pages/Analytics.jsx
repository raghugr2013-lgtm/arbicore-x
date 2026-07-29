import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api.js'
import { Panel, QueryView } from '../components/Panel.jsx'

const WINDOWS = ['1h', '6h', '24h', '7d']
const BUCKETS = ['5m', '15m', '1h', '6h', '24h']

// Phase 1 renders only TOTALS + tables. Phase 3 will replace these with Recharts viz.
export default function Analytics() {
  const [window, setWindow] = useState('24h')
  const [bucket, setBucket] = useState('1h')
  const [metric, setMetric] = useState('candidates')

  const tsQ = useQuery({
    queryKey: ['ts', metric, window, bucket],
    queryFn: () => api.analyticsTimeseries({ metric, window, bucket }),
  })
  const funnelQ = useQuery({
    queryKey: ['funnel', window],
    queryFn: () => api.analyticsFunnel(window),
  })
  const sourcesQ = useQuery({
    queryKey: ['sources', window],
    queryFn: () => api.discoveryStats(window),
  })

  return (
    <div className="space-y-6" data-testid="page-analytics">
      <header>
        <div className="label-mono">analytics</div>
        <h1 className="text-3xl font-semibold tracking-tight">Aggregated counts</h1>
        <p className="text-sm text-ink-400 mt-1">
          Phase 1 renders totals only. Phase 3 will add Recharts visualisations on top of these same endpoints.
        </p>
      </header>

      <Panel title="Window controls" subtitle="time range" testid="card-controls">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label>
            <span className="label-mono mb-1 block">metric</span>
            <select className="input" value={metric} onChange={(e) => setMetric(e.target.value)} data-testid="filter-metric">
              {['candidates', 'opportunities', 'outcomes'].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <label>
            <span className="label-mono mb-1 block">window</span>
            <select className="input" value={window} onChange={(e) => setWindow(e.target.value)} data-testid="filter-window">
              {WINDOWS.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
          <label>
            <span className="label-mono mb-1 block">bucket</span>
            <select className="input" value={bucket} onChange={(e) => setBucket(e.target.value)} data-testid="filter-bucket">
              {BUCKETS.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </label>
        </div>
      </Panel>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Panel title="Verification funnel" subtitle={`window ${window}`} testid="card-funnel">
          <QueryView q={funnelQ} testidPrefix="funnel">
            {(d) => (
              <ul className="space-y-2" data-testid="funnel-table">
                {(d.stages || []).map((s) => (
                  <li key={s.stage} className="flex items-center justify-between text-sm">
                    <span className="text-ink-200">{s.stage}</span>
                    <span className="font-mono text-ink-50">{s.count.toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Panel>

        <Panel title="Discovery sources" subtitle={`window ${window}`} testid="card-sources">
          <QueryView q={sourcesQ} testidPrefix="sources" empty={(d) => !d?.by_source?.length}>
            {(d) => (
              <ul className="space-y-2" data-testid="sources-table">
                {(d.by_source || []).slice(0, 10).map((s) => (
                  <li key={s.source} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-ink-200 truncate">{s.source}</span>
                    <span className="font-mono text-ink-50">{s.count.toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Panel>
      </div>

      <Panel title={`Timeseries · ${metric}`} subtitle={`window ${window} / bucket ${bucket}`} testid="card-ts">
        <QueryView q={tsQ} testidPrefix="ts" empty={(d) => !d?.points?.length}>
          {(d) => (
            <div className="overflow-auto">
              <table className="min-w-full text-xs" data-testid="ts-table">
                <thead className="text-ink-400">
                  <tr className="border-b border-bg-line">
                    <th className="text-left font-medium px-2 py-2">bucket start (UTC)</th>
                    <th className="text-right font-medium px-2 py-2">count</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.points || []).map((p) => (
                    <tr key={p.ts} className="border-b border-bg-line/60 table-row-hover">
                      <td className="px-2 py-2 font-mono">
                        {new Date(p.ts * 1000).toISOString().replace('T', ' ').slice(0, 19)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono">{p.count.toLocaleString()}</td>
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
