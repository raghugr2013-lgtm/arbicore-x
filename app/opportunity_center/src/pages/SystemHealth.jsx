import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api.js'
import { Panel, QueryView } from '../components/Panel.jsx'

export default function SystemHealth() {
  const colsQ = useQuery({ queryKey: ['system-collections'], queryFn: api.systemCollections, refetchInterval: 60_000 })
  const auditQ = useQuery({ queryKey: ['audit-log'], queryFn: () => api.auditLog({ limit: 50 }), refetchInterval: 30_000 })
  const healthQ = useQuery({ queryKey: ['health-detail'], queryFn: api.health, refetchInterval: 30_000 })

  return (
    <div className="space-y-6" data-testid="page-system-health">
      <header>
        <div className="label-mono">system health</div>
        <h1 className="text-3xl font-semibold tracking-tight">Backbone telemetry</h1>
        <p className="text-sm text-ink-400 mt-1">Collections census, audit-log tail, and health snapshot.</p>
      </header>

      <Panel title="Backend health" subtitle="/api/arbicore/health" testid="card-backend-health">
        <QueryView q={healthQ} testidPrefix="health">
          {(d) => (
            <pre
              data-testid="health-json"
              className="text-xs font-mono text-ink-200 max-h-72 overflow-auto whitespace-pre-wrap"
            >
              {JSON.stringify(d, null, 2)}
            </pre>
          )}
        </QueryView>
      </Panel>

      <Panel title="Mongo collections" subtitle="arbicore_* census" testid="card-collections">
        <QueryView q={colsQ} testidPrefix="collections" empty={(d) => !d?.items?.length}>
          {(d) => (
            <div className="overflow-auto">
              <table className="min-w-full text-xs" data-testid="collections-table">
                <thead className="text-ink-400">
                  <tr className="border-b border-bg-line">
                    <th className="text-left font-medium px-2 py-2">collection</th>
                    <th className="text-right font-medium px-2 py-2">count</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.items || []).map((c) => (
                    <tr key={c.name} className="border-b border-bg-line/60 table-row-hover">
                      <td className="px-2 py-2 font-mono">{c.name}</td>
                      <td className="px-2 py-2 text-right font-mono">{c.count.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryView>
      </Panel>

      <Panel title="Audit log · last 50" subtitle="arbicore_audit_log" testid="card-audit">
        <QueryView q={auditQ} testidPrefix="audit" empty={(d) => !d?.items?.length}>
          {(d) => (
            <div className="overflow-auto">
              <table className="min-w-full text-xs" data-testid="audit-table">
                <thead className="text-ink-400">
                  <tr className="border-b border-bg-line">
                    <th className="text-left font-medium px-2 py-2">timestamp</th>
                    <th className="text-left font-medium px-2 py-2">event</th>
                    <th className="text-left font-medium px-2 py-2">scanner / subject</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.items || []).map((e, i) => (
                    <tr key={i} className="border-b border-bg-line/60 table-row-hover">
                      <td className="px-2 py-2 font-mono text-ink-400">
                        {fmtTs(e.timestamp)}
                      </td>
                      <td className="px-2 py-2 font-mono text-ink-200">{e.event_type || e.event || '—'}</td>
                      <td className="px-2 py-2 font-mono text-ink-200 truncate max-w-[24rem]">
                        {e.scanner_id || e.subject_id || e.subject || '—'}
                      </td>
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

function fmtTs(t) {
  if (!t) return '—'
  const ts = typeof t === 'number' ? t * 1000 : Date.parse(t)
  if (!Number.isFinite(ts)) return String(t)
  return new Date(ts).toISOString().replace('T', ' ').slice(0, 19)
}
