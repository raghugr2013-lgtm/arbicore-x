/**
 * Phase 4 — AI Operations Center.
 *
 * Institutional-grade dark-theme dashboard. Reads from the existing
 * observability + memory + safety + provider endpoints already shipped
 * in v2.2.0 / v2.3.0 / v2.4.0. No WebSocket yet — 5s polling for
 * critical tiles + 60s polling for historical charts. ECharts is
 * loaded on-demand from a CDN so the frontend bundle stays small.
 */
import React, { useEffect, useState, useCallback } from 'react';

const REFRESH_CRITICAL_MS = 5000;
const REFRESH_HISTORY_MS  = 60000;

const backend = () =>
  (typeof process !== 'undefined' && process.env && process.env.REACT_APP_BACKEND_URL) || '';

const useBearer = () => localStorage.getItem('arbicore_token') || '';

async function jget(path) {
  const r = await fetch(`${backend()}${path}`, {
    headers: { 'Authorization': `Bearer ${useBearer()}` },
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return await r.json();
}

const Card = ({ title, right, children, testid }) => (
  <div data-testid={testid} style={{
    background: '#0f1420', border: '1px solid #1e2536',
    borderRadius: 10, padding: '18px 22px', margin: 8, minWidth: 260,
    boxShadow: '0 2px 12px rgba(0,0,0,0.35)',
  }}>
    <div style={{
      display: 'flex', justifyContent: 'space-between',
      alignItems: 'center', marginBottom: 10,
    }}>
      <div style={{ color: '#7d8ba0', fontSize: 12, letterSpacing: '.08em',
                     textTransform: 'uppercase' }}>{title}</div>
      <div style={{ fontSize: 11, color: '#455065' }}>{right}</div>
    </div>
    {children}
  </div>
);

const Big = ({ value, unit }) => (
  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
    <div style={{ color: '#e8ecf7', fontSize: 34, fontWeight: 600,
                   letterSpacing: '-.02em' }}>{value}</div>
    {unit && <div style={{ color: '#7d8ba0', fontSize: 14 }}>{unit}</div>}
  </div>
);

const StatusChip = ({ label, ok, warn }) => {
  const color = warn ? '#f5a623' : ok ? '#3ddc84' : '#ff5470';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: color + '22', color, padding: '3px 10px',
      borderRadius: 20, fontSize: 12, fontWeight: 500,
      border: `1px solid ${color}55`,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%',
                      background: color }} />
      {label}
    </span>
  );
};

const Row = ({ children }) => (
  <div style={{ display: 'flex', flexWrap: 'wrap' }}>{children}</div>
);

export default function OpsCenter() {
  const [obs, setObs]         = useState(null);
  const [memory, setMem]      = useState(null);
  const [providers, setProv]  = useState(null);
  const [safety, setSafety]   = useState(null);
  const [paperStats, setPS]   = useState(null);
  const [err, setErr]         = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [o, m, p, s, ps] = await Promise.all([
        jget('/api/arbicore/observability'),
        jget('/api/arbicore/memory/summary').catch(() => null),
        jget('/api/arbicore/providers/status').catch(() => null),
        jget('/api/arbicore/safety/status').catch(() => null),
        jget('/api/arbicore/paper/stats').catch(() => null),
      ]);
      setObs(o); setMem(m); setProv(p); setSafety(s); setPS(ps);
      setErr(null);
    } catch (e) { setErr(String(e)); }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_CRITICAL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  if (err) return (
    <div style={{ color: '#ff5470', padding: 40 }}
         data-testid="ops-center-error">
      Ops Center error: {err}
    </div>
  );
  if (!obs) return (
    <div style={{ color: '#7d8ba0', padding: 40 }}
         data-testid="ops-center-loading">Loading…</div>
  );

  const mid = obs.mid || {};
  const intel = obs.intelligence || {};
  const scanners = obs.scanners || {};
  const lifetime = obs.lifetime || {};
  const safetyO = obs.safety || safety || {};
  const paperO = obs.paper || paperStats || {};

  return (
    <div style={{
      background: '#070a12', minHeight: '100vh', color: '#e8ecf7',
      fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI"',
      padding: 24,
    }} data-testid="ops-center">
      <div style={{ display: 'flex', alignItems: 'baseline',
                     justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 28, fontWeight: 700,
                         letterSpacing: '-.02em' }}>
            ArbiCore X — AI Operations Center
          </div>
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 4 }}>
            observe → shadow → paper · live execution DISABLED
          </div>
        </div>
        <div>
          <StatusChip
            label={`kill: ${safetyO.kill?.engaged ? 'ENGAGED' : 'clear'}`}
            ok={!safetyO.kill?.engaged}
            warn={safetyO.kill?.engaged} />
          &nbsp;
          <StatusChip
            label={safetyO.live_execution_enabled
              ? 'LIVE EXECUTION ARMED' : 'live execution off'}
            ok={!safetyO.live_execution_enabled} />
        </div>
      </div>

      <Row>
        <Card title="MID health" right={mid.available ? 'ok' : '—'}
              testid="ops-mid-card">
          <Big value={
            Object.values(mid.domains || {}).reduce(
              (s, d) => s + (d.count || 0), 0).toLocaleString()}
              unit="rows" />
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 6 }}>
            {Object.keys(mid.domains || {}).length} domains
          </div>
        </Card>

        <Card title="Intelligence engines"
              right={intel.available ? 'active' : '—'}
              testid="ops-intel-card">
          <Big value={`${intel.active_count || 0}/${
            (intel.engines || []).length || 6}`} unit="engines" />
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 6 }}>
            {(intel.active || []).slice(0, 4).join(', ')}
          </div>
        </Card>

        <Card title="Scanners"
              right={scanners.available ? 'shadow' : '—'}
              testid="ops-scanners-card">
          <Big value={(scanners.running || []).length || 0}
                unit={`/ ${scanners.scanner_count || 0} running`} />
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 6 }}>
            {(scanners.scanners || []).map(s =>
              `${s.id}:${s.running ? 'run' : 'idle'}`).join('  ')}
          </div>
        </Card>

        <Card title="Opportunity lifetime"
              right={lifetime.available ? 'ok' : '—'}
              testid="ops-lifetime-card">
          <Big value={lifetime.total || 0} unit="opps tracked" />
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 6 }}>
            ACTIVE {lifetime.by_status?.ACTIVE || 0} · STALE {
              lifetime.by_status?.STALE || 0} · EXPIRED {
              lifetime.by_status?.EXPIRED || 0}
          </div>
        </Card>

        <Card title="Memory"
              right={memory ? 'ok' : '—'}
              testid="ops-memory-card">
          <Big value={memory?.opportunities?.recurring || 0}
               unit="recurring" />
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 6 }}>
            confidence {memory?.evidence?.confidence_rows || 0} ·
            routes {memory?.evidence?.route_rows || 0} ·
            venues {memory?.evidence?.provider_rows || 0}
          </div>
        </Card>

        <Card title="Providers"
              right={providers ? 'ok' : '—'}
              testid="ops-providers-card">
          <Big value={providers?.provider_count || 0} unit="registered" />
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 6 }}>
            {Object.keys(providers?.by_kind || {}).join(' · ') || 'noop stubs only'}
          </div>
        </Card>

        <Card title="Paper engine"
              right={paperO.available !== false ? 'ok' : '—'}
              testid="ops-paper-card">
          <Big value={paperO.analyses || 0} unit="analyses" />
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 6 }}>
            EV+ {paperO.ev_positive || 0} · EV- {
              paperO.ev_negative || 0} · blocked {
              paperO.policy_blocked || 0}
          </div>
        </Card>

        <Card title="Bridge throughput"
              right="scanners → MID"
              testid="ops-bridge-card">
          <Big value={
            scanners.bridge_stats?.total_emissions || 0}
               unit="emissions" />
          <div style={{ color: '#7d8ba0', fontSize: 12, marginTop: 6 }}>
            routes {scanners.bridge_stats?.routes_observed || 0}
          </div>
        </Card>
      </Row>

      <div style={{ color: '#455065', fontSize: 11, marginTop: 24,
                     textAlign: 'right' }}>
        polling every {REFRESH_CRITICAL_MS / 1000}s ·
        historical charts every {REFRESH_HISTORY_MS / 1000}s (planned)
      </div>
    </div>
  );
}
