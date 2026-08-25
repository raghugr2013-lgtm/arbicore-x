import { API_BASE } from "@/lib/apiBase";
/**
 * ArbiCore X — Live Ops Control Center
 *
 * Surfaces the backend Opportunity Engine: continuous scanner status, the
 * market-coverage funnel, top ranked opportunities, rejection reasons, profit
 * alerts, the backend-authoritative RED/YELLOW/GREEN readiness matrix, the
 * exact LIMITED_LIVE blockers and the operator onboarding checklist.
 *
 * All values are backend-authoritative. Nothing is computed client-side.
 */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API = API_BASE;
const MONO = "var(--v2-font-mono, ui-monospace, SFMono-Regular, monospace)";

const TONE = {
  GREEN:  { bg: "#022c22", fg: "#4ade80", border: "#065f46" },
  YELLOW: { bg: "#3d2500", fg: "#fbbf24", border: "#78350f" },
  RED:    { bg: "#3a0a0a", fg: "#f87171", border: "#7f1d1d" },
  INFO:   { bg: "#0f172a", fg: "#93c5fd", border: "#1e3a8a" },
};

const Pill = ({ status }) => {
  const t = TONE[status] || TONE.INFO;
  return (
    <span data-testid={`lo-pill-${status}`} style={{
      background: t.bg, color: t.fg, border: `1px solid ${t.border}`,
      fontFamily: MONO, fontSize: 10, padding: "2px 8px", borderRadius: 2,
      textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600,
    }}>{status}</span>
  );
};

const Card = ({ title, right, children, testid }) => (
  <div data-testid={testid} style={{
    background: "var(--v2-bg-surface, #0b0f16)", border: "1px solid var(--v2-border-subtle, #1e293b)",
    borderRadius: 4, padding: 16, marginBottom: 16,
  }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
      <div style={{ color: "#e2e8f0", fontFamily: MONO, fontSize: 12, textTransform: "uppercase", letterSpacing: 0.8 }}>{title}</div>
      {right}
    </div>
    {children}
  </div>
);

const Stat = ({ label, value, tone }) => (
  <div style={{ minWidth: 120 }}>
    <div style={{ color: "#64748b", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6 }}>{label}</div>
    <div style={{ color: tone || "#e2e8f0", fontFamily: MONO, fontSize: 20, fontWeight: 700 }}>{value}</div>
  </div>
);

const FunnelStep = ({ label, value, dim }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 0" }}>
    <div style={{ width: 190, color: dim ? "#64748b" : "#94a3b8", fontSize: 11, fontFamily: MONO }}>{label}</div>
    <div style={{ color: "#e2e8f0", fontFamily: MONO, fontSize: 14, fontWeight: 700, width: 60, textAlign: "right" }}>{value ?? "—"}</div>
  </div>
);

export default function LiveOpsPage() {
  const [scanner, setScanner] = useState(null);
  const [checkpoint, setCheckpoint] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [onboarding, setOnboarding] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [s, c, a, o] = await Promise.all([
        axios.get(`${API}/arbicore/engine/scanner/status`, { timeout: 20000 }),
        axios.get(`${API}/arbicore/engine/checkpoint`, { timeout: 60000 }),
        axios.get(`${API}/arbicore/engine/alerts?limit=20`, { timeout: 20000 }),
        axios.get(`${API}/arbicore/engine/onboarding`, { timeout: 20000 }),
      ]);
      setScanner(s.data); setCheckpoint(c.data); setAlerts(a.data); setOnboarding(o.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message || "load failed");
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const act = useCallback(async (fn) => {
    setBusy(true); setErr(null);
    try { await fn(); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || e.message || "action failed"); }
    finally { setBusy(false); }
  }, [load]);

  const scanNow = () => act(() => axios.post(`${API}/arbicore/engine/scan-once`, { limit: 12 }, { timeout: 90000 }));
  const startScanner = () => act(() => axios.post(`${API}/arbicore/engine/scanner/start`, {}, { timeout: 20000 }));
  const stopScanner = () => act(() => axios.post(`${API}/arbicore/engine/scanner/stop`, {}, { timeout: 20000 }));

  const fn = scanner?.funnel_cumulative || {};
  const mx = checkpoint?.readiness_matrix || {};
  const caps = mx.capabilities || [];
  const modes = mx.modes || {};
  const btn = (label, onClick, tone) => (
    <button data-testid={`lo-btn-${label.toLowerCase().replace(/\s+/g, "-")}`} onClick={onClick} disabled={busy}
      style={{ background: tone?.bg || "#0f172a", color: tone?.fg || "#93c5fd", border: `1px solid ${tone?.border || "#1e3a8a"}`,
        fontFamily: MONO, fontSize: 11, padding: "6px 12px", borderRadius: 2, cursor: busy ? "not-allowed" : "pointer",
        textTransform: "uppercase", letterSpacing: 0.6 }}>{label}</button>
  );

  return (
    <div data-testid="live-ops-page" style={{ padding: 20, maxWidth: 1200 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <div style={{ color: "#e2e8f0", fontFamily: MONO, fontSize: 18, fontWeight: 700 }}>LIVE OPS · OPPORTUNITY ENGINE</div>
          <div style={{ color: "#64748b", fontSize: 12 }}>Autonomous Base flash-loan discovery — SHADOW-safe (read-only, no signing/broadcast)</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {btn("Scan Now", scanNow, TONE.INFO)}
          {scanner?.running
            ? btn("Stop Scanner", stopScanner, TONE.RED)
            : btn("Start Scanner", startScanner, TONE.GREEN)}
          {btn("Refresh", load, TONE.INFO)}
        </div>
      </div>

      {err && <div data-testid="lo-error" style={{ color: "#f87171", fontFamily: MONO, fontSize: 12, marginBottom: 12 }}>⚠ {err}</div>}

      <Card title="Scanner Status" testid="lo-scanner-card"
        right={<Pill status={scanner?.running ? "GREEN" : "YELLOW"} />}>
        <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
          <Stat label="Running" value={scanner ? String(scanner.running) : "—"} tone={scanner?.running ? "#4ade80" : "#fbbf24"} />
          <Stat label="Interval" value={scanner ? `${scanner.interval_s}s` : "—"} />
          <Stat label="Candidate Universe" value={scanner?.candidate_universe ?? "—"} />
          <Stat label="Scans Done" value={scanner?.cumulative?.scans ?? "—"} />
          <Stat label="ETH Price" value={scanner?.last_scan_summary?.eth_price_usd ? `$${Number(scanner.last_scan_summary.eth_price_usd).toFixed(2)}` : "—"} />
          <Stat label="Last Scan" value={scanner?.cumulative?.last_scan_at ? new Date(scanner.cumulative.last_scan_at).toLocaleTimeString() : "—"} />
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card title="Market-Coverage Funnel (cumulative)" testid="lo-funnel-card">
          <FunnelStep label="Candidate universe" value={fn.candidate_universe} />
          <FunnelStep label="Routes quoted" value={fn.routes_quoted} />
          <FunnelStep label="↳ real quotes" value={fn.real_quotes} dim />
          <FunnelStep label="↳ quote failures" value={fn.quote_failures} dim />
          <FunnelStep label="↳ liquidity measured (live)" value={fn.liquidity_measured} dim />
          <FunnelStep label="negative economics" value={fn.negative_economics} />
          <FunnelStep label="positive net profit" value={fn.positive_net} />
          <FunnelStep label="positive EV" value={fn.positive_ev} />
          <FunnelStep label="simulation candidates" value={fn.simulation_candidates} />
          <FunnelStep label="simulation passes" value={fn.simulation_passes} />
          <FunnelStep label="executable candidates" value={fn.executable} />
        </Card>

        <Card title="Profit Alerts" testid="lo-alerts-card"
          right={<Pill status={(alerts?.total > 0) ? "GREEN" : "INFO"} />}>
          <div style={{ color: "#64748b", fontSize: 10, marginBottom: 8 }}>
            Fires only after the COMPLETE chain: real quote → net profit → confidence → EV → optimal size → simulation.
          </div>
          <Stat label="Qualified Alerts" value={alerts?.total ?? "—"} tone={(alerts?.total > 0) ? "#4ade80" : "#94a3b8"} />
          {(alerts?.alerts || []).length === 0
            ? <div style={{ color: "#64748b", fontFamily: MONO, fontSize: 11, marginTop: 10 }}>No qualified opportunities yet — engine will alert the moment one clears every gate.</div>
            : (alerts.alerts).map((a, i) => (
              <div key={i} style={{ borderTop: "1px solid #1e293b", padding: "6px 0", fontFamily: MONO, fontSize: 11, color: "#e2e8f0" }}>
                {a.opportunity_type} · {(a.token_path || []).join("→")} · net ${Number(a.net_profit_usd).toFixed(2)} · EV ${Number(a.expected_value_usd).toFixed(2)}
              </div>
            ))}
        </Card>
      </div>

      <Card title="Top Ranked Opportunities" testid="lo-top-card">
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: MONO, fontSize: 11 }}>
          <thead>
            <tr style={{ color: "#64748b", textAlign: "left" }}>
              <th style={{ padding: "4px 6px" }}>TYPE</th><th>ROUTE</th><th>QUOTE</th>
              <th>SPREAD bps</th><th>NET $</th><th>EV $</th><th>CONF</th><th>SIZE $</th><th>EXEC</th>
            </tr>
          </thead>
          <tbody>
            {(checkpoint?.top_opportunities || []).map((o, i) => (
              <tr key={i} style={{ color: "#cbd5e1", borderTop: "1px solid #1e293b" }}>
                <td style={{ padding: "4px 6px" }}>{o.opportunity_type}</td>
                <td>{(o.token_path || []).join("→")}</td>
                <td>{o.quote_status}</td>
                <td>{o.gross_spread_bps != null ? Number(o.gross_spread_bps).toFixed(2) : "—"}</td>
                <td>{o.net_profit_usd != null ? Number(o.net_profit_usd).toFixed(2) : "—"}</td>
                <td>{o.expected_value_usd != null ? Number(o.expected_value_usd).toFixed(2) : "—"}</td>
                <td>{o.confidence ?? "—"}</td>
                <td>{o.optimal_notional_usd ?? "—"}</td>
                <td>{String(o.would_execute)}</td>
              </tr>
            ))}
            {(!checkpoint?.top_opportunities || checkpoint.top_opportunities.length === 0) &&
              <tr><td colSpan={9} style={{ color: "#64748b", padding: 8 }}>No evidence yet — run a scan.</td></tr>}
          </tbody>
        </table>
        <div style={{ marginTop: 10, color: "#64748b", fontSize: 10 }}>
          Rejection reasons: {JSON.stringify(checkpoint?.rejection_reasons || {})}
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card title="Readiness Matrix" testid="lo-matrix-card"
          right={<Pill status={mx.overall_status || "INFO"} />}>
          {caps.map((c, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "3px 0", borderTop: i ? "1px solid #131c2b" : "none" }}>
              <span style={{ color: "#cbd5e1", fontFamily: MONO, fontSize: 11 }}>{c.capability}</span>
              <Pill status={c.status} />
            </div>
          ))}
          <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {Object.entries(modes).map(([m, v]) => (
              <span key={m} style={{ fontFamily: MONO, fontSize: 10, color: v.can_activate ? "#4ade80" : "#f87171", border: "1px solid #1e293b", padding: "2px 6px", borderRadius: 2 }}>
                {m}{v.can_activate ? " ✓" : " ✗"}
              </span>
            ))}
          </div>
        </Card>

        <Card title="LIMITED_LIVE Blockers + Onboarding" testid="lo-blockers-card">
          {(checkpoint?.limited_live_blockers || []).map((b, i) => (
            <div key={i} style={{ padding: "5px 0", borderTop: i ? "1px solid #131c2b" : "none" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#e2e8f0", fontFamily: MONO, fontSize: 11 }}>{b.capability}</span>
                <span style={{ color: b.owner === "USER" ? "#fbbf24" : "#93c5fd", fontSize: 10, fontFamily: MONO }}>{b.owner}</span>
              </div>
              <div style={{ color: "#64748b", fontSize: 10 }}>{b.action}</div>
            </div>
          ))}
          <div style={{ marginTop: 12, color: "#94a3b8", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6 }}>Onboarding checklist</div>
          {(onboarding?.checklist || []).map((c, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontFamily: MONO, fontSize: 11 }}>
              <span style={{ color: c.status === "DONE" ? "#4ade80" : "#94a3b8" }}>{c.status === "DONE" ? "✓" : "○"} {c.title}</span>
              {c.handles_secret && <span style={{ color: "#f59e0b", fontSize: 9 }}>secret — never stored here</span>}
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}
