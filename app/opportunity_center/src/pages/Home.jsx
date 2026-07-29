import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api.js'
import { Panel, Stat, QueryView } from '../components/Panel.jsx'
import { Activity, CheckCircle2, AlertCircle } from 'lucide-react'

export default function Home() {
  const healthQ = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000 })
  const opportunitiesQ = useQuery({
    queryKey: ['opportunities-recent'],
    queryFn: () => api.opportunities({ limit: 5 }),
    refetchInterval: 60_000,
  })
  const discoveryQ = useQuery({
    queryKey: ['discovery-stats-1h'],
    queryFn: () => api.discoveryStats('1h'),
    refetchInterval: 30_000,
  })
  const funnelQ = useQuery({
    queryKey: ['funnel-24h'],
    queryFn: () => api.analyticsFunnel('24h'),
    refetchInterval: 60_000,
  })

  return (
    <div className="space-y-6" data-testid="page-home">
      <header>
        <div className="label-mono">overview</div>
        <h1 className="text-3xl font-semibold tracking-tight">System pulse</h1>
        <p className="text-sm text-ink-400 mt-1">
          Read-only operator console. Confidence in the numbers, not in the prose.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Panel title="System status" subtitle="liveness" testid="card-status">
          <QueryView q={healthQ} testidPrefix="status">
            {(d) => (
              <div className="flex items-center gap-2">
                <CheckCircle2 className="text-accent-green" size={20} />
                <div>
                  <div className="text-sm text-ink-50">{d?.status || 'OK'}</div>
                  <div className="text-xs text-ink-400">{d?.phase || 'arbicore-x'}</div>
                </div>
              </div>
            )}
          </QueryView>
        </Panel>

        <Panel title="Candidates · 1h" subtitle="discovery velocity" testid="card-candidates">
          <QueryView q={discoveryQ} testidPrefix="candidates">
            {(d) => (
              <Stat
                label="total"
                value={d?.total?.toLocaleString() || '0'}
                hint={`${d?.by_source?.length || 0} sources active`}
                testid="stat-candidates-total"
              />
            )}
          </QueryView>
        </Panel>

        <Panel title="Confirmed · 24h" subtitle="verifier output" testid="card-confirmed">
          <QueryView q={funnelQ} testidPrefix="confirmed">
            {(d) => {
              const conf = d?.stages?.find((s) => s.stage === 'confirmed')?.count ?? 0
              return <Stat label="confirmed" value={conf.toLocaleString()} tone="green" testid="stat-confirmed" />
            }}
          </QueryView>
        </Panel>

        <Panel title="Recent verifications" subtitle="latest 5" testid="card-recent">
          <QueryView q={opportunitiesQ} testidPrefix="recent" empty={(d) => !d?.items?.length}>
            {(d) => (
              <ul className="space-y-2 text-xs text-ink-200" data-testid="recent-list">
                {(d.items || []).slice(0, 5).map((o) => (
                  <li key={o.opportunity_id || o.id} className="flex items-center justify-between gap-2 truncate">
                    <span className="truncate">{o.opportunity_type || o.type || 'opp'}</span>
                    <span className="font-mono text-ink-400 truncate">{(o.subject_id || '').slice(0, 22)}</span>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Panel>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Panel title="Top discovery sources · 1h" subtitle="hint emissions" testid="card-top-sources">
          <QueryView q={discoveryQ} testidPrefix="top-sources" empty={(d) => !d?.by_source?.length}>
            {(d) => (
              <ul className="space-y-2" data-testid="top-sources-list">
                {(d.by_source || []).slice(0, 6).map((s) => (
                  <li key={s.source} className="flex items-center justify-between text-sm">
                    <span className="text-ink-200 truncate font-mono">{s.source}</span>
                    <span className="text-ink-50 font-mono">{s.count.toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Panel>

        <Panel title="Verification funnel · 24h" subtitle="candidate → confirmed" testid="card-funnel">
          <QueryView q={funnelQ} testidPrefix="funnel">
            {(d) => (
              <ul className="space-y-2" data-testid="funnel-list">
                {(d.stages || []).map((s) => (
                  <li key={s.stage} className="flex items-center justify-between text-sm">
                    <span className="text-ink-200">{s.stage}</span>
                    <span className="text-ink-50 font-mono">{s.count.toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Panel>

        <Panel title="Alerts" subtitle="any P0 / P1" testid="card-alerts">
          <div className="flex items-center gap-2 text-ink-200">
            <AlertCircle size={18} className="text-accent-amber" />
            <div className="text-sm">
              No active alerts.
              <div className="text-xs text-ink-400 mt-0.5">Phase 2 will hydrate this from /audit_log filtering.</div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  )
}
