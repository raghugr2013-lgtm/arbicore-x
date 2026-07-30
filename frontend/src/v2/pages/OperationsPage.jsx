/**
 * ArbiCore X — UI v2 · Operations page (Slice 3)
 * Sub-rail: Scanners · Cycles · Venues · Interlock · Integrations · Queues · Alerts
 * All sub-sections read composed operations endpoints. Reuses Primitives.
 */
import { useEffect, useState } from "react";
import { Route, Routes, NavLink, Navigate } from "react-router-dom";
import { toast } from "sonner";
import { v2Api } from "@/v2/lib/api";
import { MetricStat, fmtUsd, fmtBps } from "@/v2/components/Primitives";

const SUB = [
  { key: "scanners", label: "Scanners" },
  { key: "cycles", label: "Cycles" },
  { key: "venues", label: "Venues" },
  { key: "interlock", label: "Interlock" },
  { key: "integrations", label: "Integrations" },
  { key: "queues", label: "Queues" },
  { key: "alerts", label: "Alerts" },
];

function SubNav() {
  return (
    <nav data-testid="v2-ops-subnav" style={{ display: "flex", flexWrap: "wrap", gap: 4, borderBottom: "1px solid var(--v2-border-subtle)", marginBottom: 16, paddingBottom: 8 }}>
      {SUB.map((s) => (
        <NavLink
          key={s.key}
          to={`/v2/operations/${s.key}`}
          data-testid={`v2-ops-tab-${s.key}`}
          style={({ isActive }) => ({
            padding: "5px 10px",
            fontFamily: "var(--v2-font-mono)",
            fontSize: 11,
            letterSpacing: 1,
            textTransform: "uppercase",
            color: isActive ? "var(--v2-accent-base)" : "var(--v2-text-secondary)",
            borderBottom: isActive ? "1px solid var(--v2-accent-base)" : "1px solid transparent",
            textDecoration: "none",
          })}
        >
          {s.label}
        </NavLink>
      ))}
    </nav>
  );
}

function StateTag({ value, map }) {
  const color = map?.[value] || "var(--v2-text-muted)";
  return (
    <span style={{ padding: "1px 6px", fontFamily: "var(--v2-font-mono)", fontSize: 9, letterSpacing: 1, border: `1px solid ${color}`, color, borderRadius: 2 }}>
      {value || "—"}
    </span>
  );
}

function useAsync(fn, deps = []) {
  const [s, setS] = useState({ loading: true, data: null, error: null, reload: 0 });
  useEffect(() => {
    let alive = true;
    setS((p) => ({ ...p, loading: true }));
    fn().then((d) => alive && setS((p) => ({ ...p, loading: false, data: d, error: null }))).catch((e) => alive && setS((p) => ({ ...p, loading: false, error: e })));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return [s, () => setS((p) => ({ ...p, reload: p.reload + 1 }))];
}

const SCANNER_STATE = { RUNNING: "var(--v2-verdict-go)", PAUSED: "var(--v2-verdict-no-soft)", IDLE: "var(--v2-text-muted)" };
const VENUE_STATE = { READY: "var(--v2-verdict-go)", DEGRADED: "var(--v2-verdict-no-soft)", OFFLINE: "var(--v2-verdict-no-hard)" };
const CYCLE_STATE = { SETTLED: "var(--v2-verdict-go)", RUNNING: "var(--v2-regime-active)", REVERTED: "var(--v2-verdict-no-hard)", FAILED: "var(--v2-verdict-no-hard)" };
const INT_STATE = { CONNECTED: "var(--v2-verdict-go)", DEGRADED: "var(--v2-verdict-no-soft)", DISCONNECTED: "var(--v2-verdict-no-hard)" };
const ALERT_SEV = { info: "var(--v2-regime-active)", warn: "var(--v2-verdict-no-soft)", error: "var(--v2-verdict-no-hard)" };

function Scanners() {
  const [reloadKey, setReloadKey] = useState(0);
  const [{ loading, data }] = useAsync(() => v2Api.scanners(), [reloadKey]);
  const [busy, setBusy] = useState(null);

  const doAction = async (family, action) => {
    setBusy(family);
    try {
      await v2Api.scannerAction(family, action);
      toast.success(`${action.toUpperCase()} · ${family}`);
      setReloadKey((k) => k + 1);
    } catch (e) { toast.error("Action failed"); }
    finally { setBusy(null); }
  };

  return (
    <section data-testid="v2-ops-scanners">
      <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="v2-ops-scanners-table">
          <thead>
            <tr style={{ background: "var(--v2-bg-panel)" }}>
              {["Family", "State", "Cadence", "Opps 1h", "Gates dropped 1h", "Errors 1h", "Actions"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (<tr><td colSpan={7} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).map((s) => (
              <tr key={s.family} data-testid={`v2-ops-scanner-${s.family}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-strong)" }}>{s.family}</td>
                <td style={{ padding: "6px 10px" }}><StateTag value={s.state} map={SCANNER_STATE} /></td>
                <td style={{ padding: "6px 10px" }}>{s.cadence_s}s</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }}>{s.opps_1h}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{s.gates_dropped_1h}</td>
                <td style={{ padding: "6px 10px", color: s.errors_1h > 0 ? "var(--v2-verdict-no-hard)" : "var(--v2-text-secondary)" }}>{s.errors_1h}</td>
                <td style={{ padding: "6px 10px", display: "flex", gap: 4 }}>
                  <button disabled={busy === s.family || s.state === "RUNNING"} onClick={() => doAction(s.family, "start")} data-testid={`v2-ops-scanner-start-${s.family}`}
                          style={{ padding: "2px 8px", background: "transparent", border: "1px solid var(--v2-verdict-go)", color: "var(--v2-verdict-go)", fontFamily: "var(--v2-font-mono)", fontSize: 10, borderRadius: 2, cursor: "pointer", opacity: (busy === s.family || s.state === "RUNNING") ? 0.4 : 1 }}>START</button>
                  <button disabled={busy === s.family || s.state === "PAUSED"} onClick={() => doAction(s.family, "pause")} data-testid={`v2-ops-scanner-pause-${s.family}`}
                          style={{ padding: "2px 8px", background: "transparent", border: "1px solid var(--v2-verdict-no-soft)", color: "var(--v2-verdict-no-soft)", fontFamily: "var(--v2-font-mono)", fontSize: 10, borderRadius: 2, cursor: "pointer", opacity: (busy === s.family || s.state === "PAUSED") ? 0.4 : 1 }}>PAUSE</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Cycles() {
  const [status, setStatus] = useState("ALL");
  const [{ loading, data }] = useAsync(() => v2Api.cycles({ status, limit: 100 }), [status]);
  const OPTS = ["ALL", "RUNNING", "SETTLED", "REVERTED", "FAILED"];
  return (
    <section data-testid="v2-ops-cycles">
      <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center" }}>
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Status</span>
        {OPTS.map((s) => (
          <button key={s} onClick={() => setStatus(s)} data-testid={`v2-ops-cycles-filter-${s}`}
                  style={{ padding: "3px 10px", border: `1px solid ${status === s ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`, background: status === s ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)", color: status === s ? "var(--v2-accent-base)" : "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer" }}>{s}</button>
        ))}
      </div>
      <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="v2-ops-cycles-table">
          <thead>
            <tr style={{ background: "var(--v2-bg-panel)" }}>
              {["Cycle", "Family", "Route", "Status", "Realized", "Size", "Ended"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (<tr><td colSpan={7} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).length === 0 && (
              <tr><td colSpan={7} style={{ padding: 0 }}><div className="v2-empty" style={{ margin: 12 }}>{"> 0 cycles match the current filter."}</div></td></tr>
            )}
            {!loading && (data?.items || []).map((c) => (
              <tr key={c.id} data-testid={`v2-ops-cycle-${c.id}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-strong)" }}>{c.id}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{c.family.replace("_ARBITRAGE", "")}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }}>{c.route}</td>
                <td style={{ padding: "6px 10px" }}><StateTag value={c.status} map={CYCLE_STATE} /></td>
                <td style={{ padding: "6px 10px", color: c.realized_bps == null ? "var(--v2-text-muted)" : (c.realized_bps >= 0 ? "var(--v2-verdict-go)" : "var(--v2-verdict-no-hard)") }}>{c.realized_bps == null ? "—" : fmtBps(c.realized_bps)}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }}>{fmtUsd(c.size_usd)}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-muted)" }}>{c.ended_at ? c.ended_at.slice(11, 19) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Venues() {
  const [{ loading, data }] = useAsync(() => v2Api.venues());
  return (
    <section data-testid="v2-ops-venues">
      <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="v2-ops-venues-table">
          <thead>
            <tr style={{ background: "var(--v2-bg-panel)" }}>
              {["Venue", "Kind", "State", "Role", "Latency", "Last seen"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (<tr><td colSpan={6} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).map((v) => (
              <tr key={v.venue} data-testid={`v2-ops-venue-${v.venue}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-strong)" }}>{v.venue}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{v.kind}</td>
                <td style={{ padding: "6px 10px" }}><StateTag value={v.state} map={VENUE_STATE} /></td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{v.role}</td>
                <td style={{ padding: "6px 10px", color: v.latency_ms > 300 ? "var(--v2-verdict-no-soft)" : "var(--v2-text-primary)" }}>{v.latency_ms == null ? "—" : `${v.latency_ms}ms`}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-muted)" }}>{v.last_seen?.slice(11, 19)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Interlock() {
  const [reloadKey, setReloadKey] = useState(0);
  const [{ loading, data }] = useAsync(() => v2Api.interlock(), [reloadKey]);
  const [busy, setBusy] = useState(false);
  const doAction = async (a) => {
    setBusy(true);
    try { await v2Api.interlockAction(a); toast.success(`Interlock ${a.toUpperCase()}`); setReloadKey((k) => k + 1); }
    catch (e) { toast.error("Action failed"); }
    finally { setBusy(false); }
  };
  if (loading) return <div className="v2-empty">Loading interlock…</div>;
  const armed = !!data?.armed;
  return (
    <section data-testid="v2-ops-interlock">
      <div className="v2-panel" style={{ marginBottom: 12 }} data-testid="v2-ops-interlock-summary">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div className="v2-panel__title">Safety interlock</div>
            <div className="v2-num" style={{ fontSize: 24, color: armed ? "var(--v2-verdict-go)" : "var(--v2-verdict-no-hard)" }}>{data?.state}</div>
            <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)" }}>
              Last transition {data?.last_transition_at?.slice(11, 19)}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button disabled={busy || armed} onClick={() => doAction("arm")} data-testid="v2-ops-interlock-arm"
                    style={{ padding: "6px 12px", background: "var(--v2-verdict-go)", color: "var(--v2-accent-onSolid)", border: "1px solid var(--v2-verdict-go)", fontFamily: "var(--v2-font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: 1.5, borderRadius: 2, cursor: "pointer", opacity: (busy || armed) ? 0.5 : 1 }}>ARM</button>
            <button disabled={busy || !armed} onClick={() => doAction("disarm")} data-testid="v2-ops-interlock-disarm"
                    style={{ padding: "6px 12px", background: "transparent", color: "var(--v2-verdict-no-hard)", border: "1px solid var(--v2-verdict-no-hard)", fontFamily: "var(--v2-font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: 1.5, borderRadius: 2, cursor: "pointer", opacity: (busy || !armed) ? 0.5 : 1 }}>DISARM</button>
          </div>
        </div>
      </div>
      <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="v2-ops-interlock-gates">
          <thead>
            <tr style={{ background: "var(--v2-bg-panel)" }}>
              {["Gate", "State", "Value", "Threshold"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data?.gates || []).map((g) => (
              <tr key={g.gate} data-testid={`v2-ops-interlock-gate-${g.gate}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-strong)" }}>{g.gate}</td>
                <td style={{ padding: "6px 10px" }}><StateTag value={g.state} map={{ PASS: "var(--v2-verdict-go)", FAIL: "var(--v2-verdict-no-hard)" }} /></td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }}>{String(g.value)}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-muted)" }}>{String(g.threshold)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Integrations() {
  const [{ loading, data }] = useAsync(() => v2Api.integrations());
  return (
    <section data-testid="v2-ops-integrations">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
        {loading && <div className="v2-empty">Loading…</div>}
        {!loading && (data?.items || []).map((it) => (
          <div key={it.key} className="v2-panel" data-testid={`v2-ops-integration-${it.key}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="v2-panel__title">{it.label}</div>
              <StateTag value={it.state} map={INT_STATE} />
            </div>
            <div style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{it.detail}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Queues() {
  const [{ loading, data }] = useAsync(() => v2Api.queues());
  return (
    <section data-testid="v2-ops-queues">
      <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="v2-ops-queues-table">
          <thead>
            <tr style={{ background: "var(--v2-bg-panel)" }}>
              {["Queue", "Pending", "In flight", "Failed 1h", "Rate/min"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (<tr><td colSpan={5} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).map((q) => (
              <tr key={q.queue} data-testid={`v2-ops-queue-${q.queue}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-strong)" }}>{q.queue}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }}>{q.pending}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }}>{q.in_flight}</td>
                <td style={{ padding: "6px 10px", color: q.failed_1h > 0 ? "var(--v2-verdict-no-hard)" : "var(--v2-text-secondary)" }}>{q.failed_1h}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{q.rate_per_min}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Alerts() {
  const [sev, setSev] = useState("ALL");
  const [reloadKey, setReloadKey] = useState(0);
  const [{ loading, data }] = useAsync(() => v2Api.alerts({ severity: sev, limit: 100 }), [sev, reloadKey]);
  const [busy, setBusy] = useState(null);
  const doAck = async (id) => {
    setBusy(id);
    try { await v2Api.alertAck(id); toast.success(`ACK · ${id}`); setReloadKey((k) => k + 1); }
    catch (e) { toast.error("Ack failed"); }
    finally { setBusy(null); }
  };
  const OPTS = ["ALL", "info", "warn", "error"];
  return (
    <section data-testid="v2-ops-alerts">
      <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center" }}>
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Severity</span>
        {OPTS.map((s) => (
          <button key={s} onClick={() => setSev(s)} data-testid={`v2-ops-alerts-filter-${s}`}
                  style={{ padding: "3px 10px", border: `1px solid ${sev === s ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`, background: sev === s ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)", color: sev === s ? "var(--v2-accent-base)" : "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer" }}>{s.toUpperCase()}</button>
        ))}
      </div>
      <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 }}>
        {loading && (<div style={{ padding: 16, color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>Loading…</div>)}
        {!loading && (data?.items || []).length === 0 && (
          <div className="v2-empty" style={{ margin: 12 }}>{"> 0 alerts.\n> System nominal."}</div>
        )}
        {!loading && (data?.items || []).map((a) => (
          <div key={a.id} data-testid={`v2-ops-alert-${a.id}`} style={{ padding: "10px 12px", borderBottom: "1px solid var(--v2-border-subtle)", display: "flex", justifyContent: "space-between", alignItems: "center", opacity: a.acked ? 0.55 : 1 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StateTag value={a.severity} map={ALERT_SEV} />
                <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1 }}>{a.source}</span>
                <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>{a.at?.slice(11, 19)}</span>
              </div>
              <div style={{ marginTop: 4, color: "var(--v2-text-primary)", fontSize: 13 }}>{a.message}</div>
            </div>
            {!a.acked && (
              <button disabled={busy === a.id} onClick={() => doAck(a.id)} data-testid={`v2-ops-alert-ack-${a.id}`}
                      style={{ padding: "4px 10px", background: "transparent", border: "1px solid var(--v2-accent-base)", color: "var(--v2-accent-base)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer", opacity: busy === a.id ? 0.5 : 1 }}>ACK</button>
            )}
            {a.acked && (
              <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1 }}>ACKED</span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

export default function OperationsPage() {
  return (
    <section data-testid="v2-operations">
      <h1 className="v2-page__title">Operations</h1>
      <p className="v2-page__lede">Scanners · Cycles · Venues · Interlock · Integrations · Queues · Alerts.</p>
      <SubNav />
      <Routes>
        <Route index element={<Navigate to="scanners" replace />} />
        <Route path="scanners" element={<Scanners />} />
        <Route path="cycles" element={<Cycles />} />
        <Route path="venues" element={<Venues />} />
        <Route path="interlock" element={<Interlock />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="queues" element={<Queues />} />
        <Route path="alerts" element={<Alerts />} />
      </Routes>
    </section>
  );
}
