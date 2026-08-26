import { BACKEND_ORIGIN } from "@/lib/apiBase";
/**
 * ArbiCore X — Live Operations Center (Stage 3 · v2.6.0)
 *
 * One live-only dashboard that replaces every placeholder page.
 * Polls the v2.5+ endpoints every 6 seconds and renders:
 *   · Live prices (cross-venue)
 *   · Live opportunity stream
 *   · Provider health / latency / breaker state
 *   · Scanner health + hit rates
 *   · MID activity (memory summary)
 *   · Kill switch / approval gate posture
 *   · Gas per chain
 *   · Validation summary (recurrence, calibration, ranking)
 *
 * Uses only the existing v2 design tokens — no new components.
 */
import { useEffect, useState, useCallback } from "react";
import axios from "axios";

const API = BACKEND_ORIGIN;
const POLL_MS = 6000;

const fmtUsd = (n) =>
  n === null || n === undefined ? "—" :
    (n < 0 ? "-$" : "$") + Math.abs(Number(n)).toLocaleString(undefined, {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
const fmtNum = (n, d = 2) =>
  n === null || n === undefined ? "—" :
    Number(n).toLocaleString(undefined, {
      minimumFractionDigits: d, maximumFractionDigits: d,
    });
const fmtBps = (n) => (n === null || n === undefined) ? "—" : Number(n).toFixed(2) + " bps";

function KPI({ label, value, unit, delta, deltaKind = "neutral", testId }) {
  const deltaColor = {
    success: "var(--v2-verdict-go)",
    warning: "var(--v2-verdict-no-soft)",
    error: "var(--v2-verdict-no-hard)",
    neutral: "var(--v2-text-muted)",
  }[deltaKind];
  return (
    <div className="w-surface" data-testid={testId} style={{
      background: "var(--v2-bg-surface)",
      border: "1px solid var(--v2-border-subtle)",
      borderRadius: 6, padding: "18px 22px", minWidth: 180,
    }}>
      <div style={{
        color: "var(--v2-text-muted)", fontSize: 11,
        letterSpacing: "0.08em", textTransform: "uppercase",
        fontFamily: "var(--v2-font-mono)", marginBottom: 8,
      }}>{label}</div>
      <div style={{
        color: "var(--v2-text-strong)", fontSize: 30, fontWeight: 600,
        fontFamily: "var(--v2-font-mono)", fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.01em", display: "flex", alignItems: "baseline",
        gap: 6,
      }}>{value}<span style={{
        color: "var(--v2-text-muted)", fontSize: 13,
      }}>{unit}</span></div>
      {delta && <div style={{ fontSize: 12, marginTop: 4, color: deltaColor, fontFamily: "var(--v2-font-mono)" }}>{delta}</div>}
    </div>
  );
}

function Section({ title, right, children, testId }) {
  return (
    <section data-testid={testId} style={{ marginBottom: 32 }}>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "baseline",
        marginBottom: 12, paddingBottom: 8,
        borderBottom: "1px solid var(--v2-border-subtle)",
      }}>
        <div style={{
          color: "var(--v2-accent-base)", fontFamily: "var(--v2-font-mono)",
          fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase",
          fontWeight: 600,
        }}>{title}</div>
        <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)" }}>{right}</div>
      </div>
      {children}
    </section>
  );
}

function Chip({ label, kind = "neutral" }) {
  const map = {
    success: ["#3ddc84", "#3ddc8422", "#3ddc8455"],
    warning: ["#f5a623", "#f5a62322", "#f5a62355"],
    error: ["#ff5470", "#ff547022", "#ff547055"],
    neutral: ["#7d8ba0", "#7d8ba022", "#7d8ba055"],
    accent: ["var(--v2-accent-base)", "var(--v2-accent-subtle)", "rgba(255,178,36,0.4)"],
  };
  const [c, bg, bd] = map[kind] || map.neutral;
  return <span style={{
    display: "inline-flex", alignItems: "center", gap: 6,
    padding: "3px 10px", borderRadius: 20, fontSize: 11,
    fontFamily: "var(--v2-font-mono)", color: c,
    background: bg, border: `1px solid ${bd}`,
  }}>
    <span style={{ width: 6, height: 6, borderRadius: "50%", background: c }} />
    {label}
  </span>;
}

async function safeGet(path) {
  try {
    const r = await axios.get(`${API}${path}`, { timeout: 8000 });
    return r.data;
  } catch { return null; }
}

export default function OpsCenter() {
  const [state, setState] = useState({});
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    const [live, prices, opps, providers, cross, memory, safety, validation, mid, shadowCert, shadowReadiness, shadowRuns, decSummary, decRejections, decBottlenecks, decByScanner] =
      await Promise.all([
        safeGet("/api/arbicore/live/status"),
        safeGet("/api/arbicore/live/prices"),
        safeGet("/api/arbicore/live/opportunities?limit=8"),
        safeGet("/api/arbicore/providers/status"),
        safeGet("/api/arbicore/scanners/cross/status"),
        safeGet("/api/arbicore/memory/summary"),
        safeGet("/api/arbicore/safety/status"),
        safeGet("/api/arbicore/validation/summary"),
        safeGet("/api/arbicore/observability"),
        safeGet("/api/arbicore/certification/shadow/current"),
        safeGet("/api/arbicore/certification/shadow/readiness"),
        safeGet("/api/arbicore/certification/shadow/runs?limit=5"),
        safeGet("/api/arbicore/analytics/decisions/summary?limit=500"),
        safeGet("/api/arbicore/analytics/decisions/rejections?limit=500"),
        safeGet("/api/arbicore/analytics/decisions/bottlenecks?limit=500"),
        safeGet("/api/arbicore/analytics/decisions/by_scanner?limit=500"),
      ]);
    setState({ live, prices, opps, providers, cross, memory, safety, validation, mid, shadowCert, shadowReadiness, shadowRuns, decSummary, decRejections, decBottlenecks, decByScanner });
    setTick(t => t + 1);
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const { live, prices, opps, providers, cross, memory, safety, validation, shadowCert, shadowReadiness, shadowRuns, decSummary, decRejections, decBottlenecks, decByScanner } = state;
  const totalProviders = providers?.provider_count ?? 0;
  const scanners = validation?.scanner_ranking?.scanners || [];
  const totalOpsEmitted = scanners.reduce((s, x) => s + (x.opportunities_emitted || 0), 0);
  const providersByKind = providers?.by_kind || {};

  return (
    <div style={{ padding: "24px 32px", maxWidth: 1600, margin: "0 auto" }} data-testid="ops-center">
      {/* HERO / KPI ROW */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 32 }}>
        <KPI testId="kpi-providers" label="Providers" value={fmtNum(totalProviders, 0)}
             unit="registered"
             delta={providers ? `${providers?.provider_count} HEALTHY` : "loading…"}
             deltaKind="success" />
        <KPI testId="kpi-scanners-running" label="Scanners"
             value={fmtNum(scanners.filter(s => s.running).length, 0)}
             unit={`/ ${scanners.length}`}
             delta={`${totalOpsEmitted} opps emitted`}
             deltaKind={totalOpsEmitted > 0 ? "success" : "neutral"} />
        <KPI testId="kpi-live-quotes" label="Live Quotes"
             value={fmtNum(live?.stats?.quotes_collected, 0)}
             unit="collected"
             delta={live?.running ? `tick ${live?.stats?.iterations || 0}` : "idle"} />
        <KPI testId="kpi-safety" label="Safety" value={safety?.kill?.engaged ? "ENGAGED" : "OPEN"}
             unit={safety?.live_execution_enabled ? "LIVE" : "PAPER"}
             delta={safety?.kill?.reason || "—"}
             deltaKind={safety?.kill?.engaged ? "success" : "warning"} />
        <KPI testId="kpi-mid-opps" label="MID Opps"
             value={fmtNum(memory?.opportunities?.total, 0)}
             unit="total"
             delta={`${memory?.opportunities?.by_status?.ACTIVE || 0} active`}
             deltaKind="neutral" />
        {(() => {
          const cur = shadowCert?.current;
          const status = cur?.status || "IDLE";
          const cyc = cur?.cycles_completed || 0;
          const tgt = cur?.target_cycles || 0;
          const rate = cur?.cumulative?.executable_rate;
          const dKind = { PASS: "success", WARNING: "warning", FAIL: "error", ABORTED: "warning", RUNNING: "neutral", IDLE: "neutral" }[status] || "neutral";
          return (
            <KPI testId="kpi-shadow-cert" label="Shadow Certification"
                 value={status}
                 unit={tgt > 0 ? `${cyc}/${tgt}` : ""}
                 delta={rate !== undefined ? `exec-rate ${(rate * 100).toFixed(2)}%` : "no active run"}
                 deltaKind={dKind} />
          );
        })()}
      </div>

      {/* SHADOW CERTIFICATION — live progress + cycle stream */}
      <Section
        title="Shadow Certification — live"
        testId="section-shadow-cert"
        right={(() => {
          const r = shadowReadiness;
          if (!r) return "";
          return r.is_live_ready ? "readiness: LIVE-READY" : `readiness: ${r.issues?.join(",") || "not ready"}`;
        })()}
      >
        {(() => {
          const cur = shadowCert?.current;
          const runs = shadowRuns?.items || [];
          if (!cur && runs.length === 0) {
            return (
              <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="shadow-cert-empty">
                No certification runs yet. POST /api/arbicore/certification/shadow/start
              </div>
            );
          }
          const active = cur;
          const done = active?.cycles_completed || 0;
          const target = active?.target_cycles || 0;
          const pct = target > 0 ? Math.round((done / target) * 100) : 0;
          const statusColor = {
            RUNNING: "var(--v2-text-strong)",
            PASS:    "var(--v2-verdict-go)",
            WARNING: "var(--v2-verdict-no-soft)",
            FAIL:    "var(--v2-verdict-no-hard)",
            ABORTED: "var(--v2-text-muted)",
          }[active?.status] || "var(--v2-text-strong)";
          const outcomeStr = Object.entries(active?.cumulative?.outcome_counts || {})
            .map(([k, v]) => `${k}:${v}`).join(" · ") || "—";
          const cycles = (active?.cycles || []).slice().reverse();
          return (
            <div>
              {active ? (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
                  <div>
                    <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase" }}>Status</div>
                    <div style={{ color: statusColor, fontSize: 20, fontFamily: "var(--v2-font-mono)", fontWeight: 600 }} data-testid="shadow-cert-status">{active.status}</div>
                  </div>
                  <div>
                    <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase" }}>Progress</div>
                    <div style={{ color: "var(--v2-text-strong)", fontSize: 20, fontFamily: "var(--v2-font-mono)" }} data-testid="shadow-cert-progress">{done}/{target}</div>
                    <div style={{ height: 4, background: "rgba(255,255,255,0.06)", borderRadius: 2, marginTop: 4, overflow: "hidden" }}>
                      <div style={{ width: `${pct}%`, height: "100%", background: statusColor, transition: "width 300ms ease" }} />
                    </div>
                  </div>
                  <div>
                    <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase" }}>Executable rate</div>
                    <div style={{ color: "var(--v2-text-strong)", fontSize: 20, fontFamily: "var(--v2-font-mono)" }} data-testid="shadow-cert-rate">
                      {((active?.cumulative?.executable_rate || 0) * 100).toFixed(2)}%
                    </div>
                    <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)" }} data-testid="shadow-cert-outcomes">{outcomeStr}</div>
                  </div>
                  <div>
                    <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase" }}>Run ID</div>
                    <div style={{ color: "var(--v2-text-strong)", fontSize: 11, fontFamily: "var(--v2-font-mono)", wordBreak: "break-all" }} data-testid="shadow-cert-runid">
                      {(active.run_id || "").slice(0, 36)}…
                    </div>
                  </div>
                </div>
              ) : null}
              {cycles.length > 0 && (
                <div data-testid="shadow-cert-cycles">
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    Recent cycles (newest first)
                  </div>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
                    <thead>
                      <tr style={{ color: "var(--v2-text-muted)", textAlign: "left", borderBottom: "1px solid var(--v2-border-subtle)" }}>
                        <th style={{ padding: "4px 8px" }}>#</th>
                        <th style={{ padding: "4px 8px" }}>Status</th>
                        <th style={{ padding: "4px 8px" }}>Processed</th>
                        <th style={{ padding: "4px 8px" }}>Executable</th>
                        <th style={{ padding: "4px 8px" }}>Vids</th>
                        <th style={{ padding: "4px 8px" }}>Stage p95</th>
                        <th style={{ padding: "4px 8px" }}>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cycles.slice(0, 8).map((c) => {
                        const p95 = c.stage_p95_ms || {};
                        const p95max = Object.values(p95).length ? Math.max(...Object.values(p95)) : 0;
                        const cs = c.cycle_status || "?";
                        const csColor = { PASS: "var(--v2-verdict-go)", WARNING: "var(--v2-verdict-no-soft)", FAIL: "var(--v2-verdict-no-hard)" }[cs] || "var(--v2-text-muted)";
                        const reason = (c.cycle_reasons && c.cycle_reasons[0]) || (c.flags || []).join(",") || "—";
                        return (
                          <tr key={c.cycle_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-muted)" }}>{c.cycle_index}</td>
                            <td style={{ padding: "4px 8px", color: csColor, fontWeight: 600 }}>{cs}</td>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{c.opportunities_processed}</td>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{c.executable_count}</td>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{(c.validation_ids || []).length}</td>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{p95max.toFixed(1)} ms</td>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-secondary)" }}>{reason.slice(0, 60)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {runs.length > 0 && (
                <div style={{ marginTop: 12 }} data-testid="shadow-cert-history">
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase", marginBottom: 4 }}>
                    History (latest {runs.length})
                  </div>
                  {runs.map((r) => {
                    const c = { PASS: "var(--v2-verdict-go)", WARNING: "var(--v2-verdict-no-soft)", FAIL: "var(--v2-verdict-no-hard)", ABORTED: "var(--v2-text-muted)", RUNNING: "var(--v2-text-strong)" }[r.status] || "var(--v2-text-muted)";
                    return (
                      <div key={r.run_id} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontFamily: "var(--v2-font-mono)", fontSize: 11, borderBottom: "1px solid rgba(255,255,255,0.03)" }} data-testid={`shadow-cert-history-${r.run_id.slice(0, 12)}`}>
                        <span style={{ color: "var(--v2-text-secondary)" }}>{r.run_id.slice(0, 30)}…</span>
                        <span style={{ color: c, fontWeight: 600 }}>{r.status}</span>
                        <span style={{ color: "var(--v2-text-muted)" }}>{r.cycles_completed}/{r.target_cycles}</span>
                        <span style={{ color: "var(--v2-text-muted)" }}>{(r.cumulative?.executable_rate * 100 || 0).toFixed(1)}%</span>
                        <span style={{ color: "var(--v2-text-muted)" }}>{r.started_at?.slice(11, 19)}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })()}
      </Section>

      {/* DECISION ANALYTICS — v2.11.10 */}
      <Section
        title="Opportunity Decision Analytics"
        testId="section-decision-analytics"
        right={(() => {
          const s = decSummary;
          if (!s) return "";
          const total = s.window?.sampled || 0;
          return `sample ${total} · executable ${(s.effective_executable_rate * 100).toFixed(2)}% (effective)`;
        })()}
      >
        {(() => {
          const s = decSummary;
          const rej = decRejections;
          const bn = decBottlenecks;
          const bs = decByScanner;
          if (!s) {
            return <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="decision-analytics-empty">Loading analytics…</div>;
          }
          const cats = rej?.categories || [];
          const stages = bn?.stages || [];
          const fams = bs?.families || [];
          const totalExec = s.executable_count || 0;
          const totalReal = s.real_rejection_count || 0;
          const totalObs = s.observed_only_count || 0;
          return (
            <div>
              {/* KPI row */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }} data-testid="decision-analytics-kpi">
                <div>
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase" }}>Sampled</div>
                  <div style={{ color: "var(--v2-text-strong)", fontSize: 20, fontFamily: "var(--v2-font-mono)" }} data-testid="decision-kpi-sampled">{s.window?.sampled || 0}</div>
                </div>
                <div>
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase" }}>Executable</div>
                  <div style={{ color: totalExec > 0 ? "var(--v2-verdict-go)" : "var(--v2-text-muted)", fontSize: 20, fontFamily: "var(--v2-font-mono)" }} data-testid="decision-kpi-exec">
                    {totalExec}
                  </div>
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)" }}>
                    {(s.effective_executable_rate * 100).toFixed(2)}% effective
                  </div>
                </div>
                <div>
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase" }}>Real rejections</div>
                  <div style={{ color: totalReal > 0 ? "var(--v2-verdict-no-hard)" : "var(--v2-text-muted)", fontSize: 20, fontFamily: "var(--v2-font-mono)" }} data-testid="decision-kpi-rej">{totalReal}</div>
                </div>
                <div>
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase" }}>Observe-only (meta)</div>
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 20, fontFamily: "var(--v2-font-mono)" }} data-testid="decision-kpi-obs">{totalObs}</div>
                </div>
              </div>

              {/* Two-column layout: rejections + bottlenecks */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
                <div data-testid="decision-analytics-rejections">
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase", marginBottom: 6 }}>
                    Rejection reasons (by category)
                  </div>
                  {cats.length === 0 ? (
                    <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>no rejections yet</div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
                      <thead>
                        <tr style={{ color: "var(--v2-text-muted)", textAlign: "left", borderBottom: "1px solid var(--v2-border-subtle)" }}>
                          <th style={{ padding: "4px 8px" }}>Category</th>
                          <th style={{ padding: "4px 8px" }}>Count</th>
                          <th style={{ padding: "4px 8px" }}>Share</th>
                          <th style={{ padding: "4px 8px" }}>Top sub-code</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cats.map((c) => {
                          const topSub = Object.entries(c.sub_codes || {})[0] || ["—", 0];
                          const catColor = { EXECUTABLE: "var(--v2-verdict-go)", OBSERVE_ONLY: "var(--v2-text-muted)" }[c.category] || "var(--v2-verdict-no-hard)";
                          return (
                            <tr key={c.category} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }} data-testid={`decision-rejection-cat-${c.category}`}>
                              <td style={{ padding: "4px 8px", color: catColor, fontWeight: 600 }}>{c.category}</td>
                              <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{c.count}</td>
                              <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{(c.share * 100).toFixed(1)}%</td>
                              <td style={{ padding: "4px 8px", color: "var(--v2-text-secondary)" }}>{topSub[0]} ({topSub[1]})</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>

                <div data-testid="decision-analytics-bottlenecks">
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase", marginBottom: 6 }}>
                    Stage bottlenecks (rejections + p95 latency)
                  </div>
                  {stages.length === 0 ? (
                    <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>no stage data yet</div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
                      <thead>
                        <tr style={{ color: "var(--v2-text-muted)", textAlign: "left", borderBottom: "1px solid var(--v2-border-subtle)" }}>
                          <th style={{ padding: "4px 8px" }}>Stage</th>
                          <th style={{ padding: "4px 8px" }}>Rejects</th>
                          <th style={{ padding: "4px 8px" }}>Share</th>
                          <th style={{ padding: "4px 8px" }}>p50 ms</th>
                          <th style={{ padding: "4px 8px" }}>p95 ms</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stages.slice(0, 8).map((st) => (
                          <tr key={st.stage} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }} data-testid={`decision-bottleneck-${st.stage}`}>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{st.stage}</td>
                            <td style={{ padding: "4px 8px", color: st.rejections > 0 ? "var(--v2-verdict-no-hard)" : "var(--v2-text-muted)" }}>{st.rejections}</td>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{(st.rejection_share * 100).toFixed(1)}%</td>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{st.duration_p50_ms.toFixed(3)}</td>
                            <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{st.duration_p95_ms.toFixed(3)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* Per-scanner performance */}
              {fams.length > 0 && (
                <div style={{ marginTop: 16 }} data-testid="decision-analytics-by-scanner">
                  <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", textTransform: "uppercase", marginBottom: 6 }}>
                    Per-scanner performance
                  </div>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
                    <thead>
                      <tr style={{ color: "var(--v2-text-muted)", textAlign: "left", borderBottom: "1px solid var(--v2-border-subtle)" }}>
                        <th style={{ padding: "4px 8px" }}>Family</th>
                        <th style={{ padding: "4px 8px" }}>Sampled</th>
                        <th style={{ padding: "4px 8px" }}>Executable</th>
                        <th style={{ padding: "4px 8px" }}>Rejected</th>
                        <th style={{ padding: "4px 8px" }}>Observe-only</th>
                        <th style={{ padding: "4px 8px" }}>Rate</th>
                        <th style={{ padding: "4px 8px" }}>Top category</th>
                        <th style={{ padding: "4px 8px" }}>Avg e2e ms</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fams.map((f) => (
                        <tr key={f.family} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }} data-testid={`decision-by-scanner-${f.family}`}>
                          <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{f.family}</td>
                          <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{f.sampled}</td>
                          <td style={{ padding: "4px 8px", color: f.executable > 0 ? "var(--v2-verdict-go)" : "var(--v2-text-muted)" }}>{f.executable}</td>
                          <td style={{ padding: "4px 8px", color: f.rejected > 0 ? "var(--v2-verdict-no-hard)" : "var(--v2-text-muted)" }}>{f.rejected}</td>
                          <td style={{ padding: "4px 8px", color: "var(--v2-text-muted)" }}>{f.observe_only}</td>
                          <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{(f.executable_rate * 100).toFixed(2)}%</td>
                          <td style={{ padding: "4px 8px", color: "var(--v2-text-secondary)" }}>{f.top_category || "—"}</td>
                          <td style={{ padding: "4px 8px", color: "var(--v2-text-strong)" }}>{f.avg_e2e_ms.toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })()}
      </Section>

      {/* LIVE PRICES */}
      <Section title="Live Prices — cross-venue snapshot" testId="section-prices"
               right={prices?.generated_at ? new Date(prices.generated_at).toLocaleTimeString() : ""}>
        {Object.entries(prices?.prices || {}).map(([sym, snap]) => {
          const bb = snap.best_bid, ba = snap.best_ask;
          const cross = bb && ba ? (bb.bid - ba.ask) / ba.ask * 10000 : null;
          return (
            <div key={sym} data-testid={`price-row-${sym}`}
                 style={{
                   background: "var(--v2-bg-surface)",
                   border: "1px solid var(--v2-border-subtle)",
                   padding: "14px 20px", marginBottom: 12,
                 }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                             alignItems: "center", marginBottom: 8 }}>
                <div style={{ fontFamily: "var(--v2-font-mono)",
                                color: "var(--v2-text-strong)",
                                fontSize: 15, fontWeight: 600 }}>{sym}</div>
                {cross && <Chip label={`cross ${cross.toFixed(2)} bps`}
                                 kind={cross > 5 ? "success" : "neutral"} />}
              </div>
              <table style={{ width: "100%", fontFamily: "var(--v2-font-mono)",
                                 fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                <thead><tr style={{ color: "var(--v2-text-muted)", textAlign: "left" }}>
                  <th>Venue</th><th style={{ textAlign: "right" }}>Bid</th>
                  <th style={{ textAlign: "right" }}>Ask</th>
                  <th style={{ textAlign: "right" }}>Spread (bps)</th>
                </tr></thead>
                <tbody>
                  {snap.venues.map((v) => (
                    <tr key={v.venue} data-testid={`venue-${sym}-${v.venue}`}
                        style={{ color: "var(--v2-text-primary)" }}>
                      <td>{v.venue}</td>
                      <td style={{ textAlign: "right" }}>{fmtNum(v.bid, 2)}</td>
                      <td style={{ textAlign: "right" }}>{fmtNum(v.ask, 2)}</td>
                      <td style={{ textAlign: "right" }}>{fmtNum(v.spread_bps)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}
      </Section>

      {/* LIVE OPPORTUNITY STREAM */}
      <Section title="Live Opportunity Stream" testId="section-opps"
               right={`${opps?.count || 0} recent`}>
        <table style={{ width: "100%", fontFamily: "var(--v2-font-mono)",
                          fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
          <thead><tr style={{ color: "var(--v2-text-muted)",
                                  background: "var(--v2-bg-panel)", textAlign: "left" }}>
            <th style={{ padding: "8px 12px" }}>Opp ID</th>
            <th>Type</th><th>Symbol</th>
            <th>Buy → Sell</th>
            <th style={{ textAlign: "right" }}>Spread</th>
            <th style={{ textAlign: "right" }}>Gross</th>
            <th style={{ textAlign: "right" }}>Net</th>
            <th>Verdict</th>
          </tr></thead>
          <tbody>
            {(opps?.opportunities || []).slice(0, 8).map((o, i) => {
              const p = o.payload || {};
              const profitable = (p.net_profit_usd || 0) > 0;
              return (
                <tr key={`${o.opp_id}-${i}`} data-testid={`opp-row-${o.opp_id}`}
                    style={{
                      borderBottom: "1px solid var(--v2-border-subtle)",
                      color: "var(--v2-text-primary)",
                    }}>
                  <td style={{ padding: "8px 12px", color: "var(--v2-text-muted)" }}>
                    {String(o.opp_id || "").slice(0, 32)}…
                  </td>
                  <td>{p.opportunity_type || "?"}</td>
                  <td>{p.symbol || "?"}</td>
                  <td>{p.venue_buy} → {p.venue_sell}</td>
                  <td style={{ textAlign: "right" }}>{fmtBps(p.spread_bps)}</td>
                  <td style={{ textAlign: "right" }}>{fmtUsd(p.gross_profit_usd)}</td>
                  <td style={{ textAlign: "right",
                                 color: profitable ? "var(--v2-verdict-go)"
                                                     : "var(--v2-verdict-no-hard)" }}>
                    {fmtUsd(p.net_profit_usd ?? p.expected_profit_usd)}
                  </td>
                  <td>
                    <Chip label={profitable ? "PROFITABLE" : "UNECONOMIC"}
                          kind={profitable ? "success" : "warning"} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {(!opps?.opportunities || !opps.opportunities.length) && (
          <div style={{
            padding: 20, textAlign: "center",
            color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)",
            border: "1px dashed var(--v2-border-subtle)",
          }}>Waiting for first live emission…</div>
        )}
      </Section>

      {/* SCANNERS + PROVIDER HEALTH */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <Section title="Scanner Ranking" testId="section-scanners">
          <table style={{ width: "100%", fontFamily: "var(--v2-font-mono)",
                            fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
            <thead><tr style={{ color: "var(--v2-text-muted)", textAlign: "left" }}>
              <th>Scanner</th><th>State</th>
              <th style={{ textAlign: "right" }}>Iter</th>
              <th style={{ textAlign: "right" }}>Opps</th>
              <th style={{ textAlign: "right" }}>Hit</th>
            </tr></thead>
            <tbody>
              {scanners.map((s) => (
                <tr key={s.scanner_id}
                    style={{ borderBottom: "1px solid var(--v2-border-subtle)",
                              color: "var(--v2-text-primary)" }}
                    data-testid={`scanner-row-${s.scanner_id}`}>
                  <td>{s.scanner_id}</td>
                  <td>
                    <Chip label={s.running ? "RUNNING" : "STOPPED"}
                          kind={s.running ? "success" : "neutral"} />
                  </td>
                  <td style={{ textAlign: "right" }}>{s.iterations}</td>
                  <td style={{ textAlign: "right" }}>{s.opportunities_emitted}</td>
                  <td style={{ textAlign: "right" }}>{fmtNum(s.hit_rate, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Provider Health" testId="section-providers"
                 right={`${totalProviders} total`}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {Object.entries(providersByKind).map(([kind, list]) => {
              const healthy = list.filter(p => p.status === "HEALTHY").length;
              const tripped = list.length - healthy;
              return (
                <div key={kind} data-testid={`provider-kind-${kind}`}
                     style={{
                       background: "var(--v2-bg-surface)",
                       border: "1px solid var(--v2-border-subtle)",
                       padding: "10px 14px",
                     }}>
                  <div style={{ color: "var(--v2-text-muted)",
                                  fontFamily: "var(--v2-font-mono)",
                                  fontSize: 10, letterSpacing: "0.08em",
                                  textTransform: "uppercase",
                                  marginBottom: 4 }}>{kind}</div>
                  <div style={{ display: "flex", alignItems: "baseline",
                                 gap: 8 }}>
                    <span style={{ color: "var(--v2-text-strong)",
                                     fontFamily: "var(--v2-font-mono)",
                                     fontSize: 20, fontWeight: 600 }}>{healthy}</span>
                    <span style={{ color: "var(--v2-text-muted)",
                                     fontSize: 11,
                                     fontFamily: "var(--v2-font-mono)" }}>/ {list.length}</span>
                    {tripped > 0 && <Chip label={`${tripped} trip`} kind="error" />}
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      </div>

      {/* VALIDATION + SAFETY */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 24 }}>
        <Section title="Venue Ranking (live)" testId="section-venues"
                 right={`sampled ${validation?.venue_ranking?.sampled_opps || 0}`}>
          <table style={{ width: "100%", fontFamily: "var(--v2-font-mono)",
                            fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
            <thead><tr style={{ color: "var(--v2-text-muted)", textAlign: "left" }}>
              <th>Venue</th>
              <th style={{ textAlign: "right" }}>Buy</th>
              <th style={{ textAlign: "right" }}>Sell</th>
              <th style={{ textAlign: "right" }}>Avg net $</th>
            </tr></thead>
            <tbody>
              {(validation?.venue_ranking?.venues || []).slice(0, 8).map((v) => (
                <tr key={v.venue} data-testid={`venue-rank-${v.venue}`}
                    style={{ borderBottom: "1px solid var(--v2-border-subtle)",
                              color: "var(--v2-text-primary)" }}>
                  <td>{v.venue}</td>
                  <td style={{ textAlign: "right" }}>{v.buy_count}</td>
                  <td style={{ textAlign: "right" }}>{v.sell_count}</td>
                  <td style={{ textAlign: "right",
                                 color: (v.avg_net_profit_usd || 0) > 0
                                          ? "var(--v2-verdict-go)"
                                          : "var(--v2-verdict-no-hard)" }}>
                    {v.avg_net_profit_usd === null || v.avg_net_profit_usd === undefined
                      ? "—" : fmtUsd(v.avg_net_profit_usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Safety Posture" testId="section-safety">
          <div style={{
            background: "var(--v2-bg-surface)",
            border: "1px solid var(--v2-border-subtle)",
            padding: 20,
          }}>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
              <Chip label={`kill ${safety?.kill?.engaged ? "ENGAGED" : "OPEN"}`}
                    kind={safety?.kill?.engaged ? "success" : "warning"} />
              <Chip label={safety?.live_execution_enabled ? "LIVE-EXEC" : "PAPER-ONLY"}
                    kind={safety?.live_execution_enabled ? "error" : "success"} />
              <Chip label={safety?.require_approval_gate ? "APPROVAL REQ" : "no approval"}
                    kind="accent" />
              <Chip label={safety?.require_paper_validation ? "PAPER REQ" : "paper opt"}
                    kind="accent" />
            </div>
            <div style={{ fontFamily: "var(--v2-font-mono)", fontSize: 12,
                            color: "var(--v2-text-secondary)", lineHeight: 1.7 }}>
              <div>Max per trade: <b style={{ color: "var(--v2-text-primary)" }}>
                {fmtUsd(safety?.capital_policy?.max_per_trade_usd)}</b></div>
              <div>Max per chain: <b style={{ color: "var(--v2-text-primary)" }}>
                {fmtUsd(safety?.capital_policy?.max_per_chain_usd)}</b></div>
              <div>Daily notional cap: <b style={{ color: "var(--v2-text-primary)" }}>
                {fmtUsd(safety?.capital_policy?.max_daily_notional_usd)}</b></div>
              <div style={{ marginTop: 12, color: "var(--v2-text-muted)" }}>
                Reason: <b>{safety?.kill?.reason || "—"}</b>
              </div>
            </div>
          </div>
        </Section>
      </div>

      {/* CROSS SCANNERS DETAIL */}
      <div style={{ marginTop: 24 }}>
        <Section title="Cross-venue scanner detail" testId="section-cross">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {["cex_dex", "dex_dex"].map((k) => {
              const s = cross?.[k];
              const st = s?.stats || {};
              return (
                <div key={k} data-testid={`cross-${k}`}
                     style={{
                       background: "var(--v2-bg-surface)",
                       border: "1px solid var(--v2-border-subtle)",
                       padding: 16, fontFamily: "var(--v2-font-mono)",
                     }}>
                  <div style={{ display: "flex", justifyContent: "space-between",
                                 marginBottom: 8 }}>
                    <div style={{ color: "var(--v2-text-strong)", fontSize: 13 }}>
                      {k}
                    </div>
                    <Chip label={s?.running ? "RUNNING" : "STOPPED"}
                          kind={s?.running ? "success" : "neutral"} />
                  </div>
                  <div style={{ fontSize: 11, color: "var(--v2-text-muted)",
                                 lineHeight: 1.7 }}>
                    <div>iterations: <b style={{ color: "var(--v2-text-primary)" }}>
                      {st.iterations || 0}</b></div>
                    <div>quotes: <b style={{ color: "var(--v2-text-primary)" }}>
                      {st.quotes_collected || 0}</b></div>
                    <div>emitted: <b style={{ color: "var(--v2-text-primary)" }}>
                      {st.opportunities_emitted || 0}</b></div>
                    {st.last_error && <div style={{ color: "var(--v2-verdict-no-hard)",
                                                      marginTop: 8,
                                                      wordBreak: "break-word" }}>
                      last error: {st.last_error.slice(0, 120)}
                    </div>}
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      </div>

      <div style={{ color: "var(--v2-text-muted)",
                     fontFamily: "var(--v2-font-mono)", fontSize: 10,
                     textAlign: "center", marginTop: 32,
                     paddingTop: 16, borderTop: "1px solid var(--v2-border-subtle)" }}>
        ArbiCore X v2.6.0 · OBSERVE + PAPER · poll {POLL_MS}ms · tick #{tick}
      </div>
    </div>
  );
}
