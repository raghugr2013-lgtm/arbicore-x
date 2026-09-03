/**
 * ArbiCore X — UI v2 · Home page (Slice 1)
 * Layout: Pulse band → Priorities band → Vitals band.
 * Wired to /api/arbicore/dashboard/pulse + /deck + /opportunities/summary.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { v2Api } from "@/v2/lib/api";
import { ConfidencePill, MetricStat, fmtUsd } from "@/v2/components/Primitives";

function Card({ title, testid, children, actions }) {
  return (
    <div className="v2-panel" data-testid={testid}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div className="v2-panel__title">{title}</div>
        {actions}
      </div>
      {children}
    </div>
  );
}

function useAsync(fn, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    fn()
      .then((d) => alive && setState({ loading: false, data: d, error: null }))
      .catch((e) => alive && setState({ loading: false, data: null, error: e }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

/** v2.11.9 — polling variant used by the live Shadow Certification card so
 * the operator dashboard reflects cycle progress without a manual refresh. */
function usePolled(fn, intervalMs = 5000, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let alive = true;
    const tick = () => {
      fn()
        .then((d) => alive && setState({ loading: false, data: d, error: null }))
        .catch((e) => alive && setState({ loading: false, data: null, error: e }));
    };
    tick();
    const h = setInterval(tick, intervalMs);
    return () => { alive = false; clearInterval(h); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

function ShadowCertificationCard({ pulse, current }) {
  const p = pulse.data?.shadow_certification || null;
  const c = current.data?.current || null;
  const active = Boolean(p?.active);
  const runId = p?.run_id || c?.run_id || null;
  const status = p?.status || c?.status || "IDLE";
  const done = p?.cycles_completed ?? c?.cycles_completed ?? 0;
  const target = p?.target_cycles ?? c?.target_cycles ?? 20;
  const rate = (c?.cumulative?.executable_rate ?? p?.executable_rate ?? 0) * 100;
  const outcomes = c?.cumulative?.outcome_counts || {};
  const cycles = c?.cycles || [];
  const recent = cycles.slice(-3).reverse();

  const statusColor = {
    RUNNING:  "var(--v2-text-strong)",
    PASS:     "var(--v2-verdict-go, #4ade80)",
    WARNING:  "#facc15",
    FAIL:     "var(--v2-verdict-no, #f87171)",
    ABORTED:  "var(--v2-text-muted)",
    IDLE:     "var(--v2-text-muted)",
  }[status] || "var(--v2-text-strong)";

  const pctDone = target > 0 ? Math.round((done / target) * 100) : 0;

  return (
    <Card title="Shadow Certification" testid="v2-home-shadow-cert">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div className="v2-num" style={{ fontSize: 20, color: statusColor }} data-testid="v2-home-shadow-cert-status">
          {status}
        </div>
        <div className="v2-num" style={{ fontSize: 13, color: "var(--v2-text-strong)" }} data-testid="v2-home-shadow-cert-progress">
          {done}/{target}
        </div>
      </div>
      {active || done > 0 ? (
        <>
          <div style={{ height: 6, background: "rgba(255,255,255,0.08)", borderRadius: 3, marginTop: 8, overflow: "hidden" }}>
            <div style={{ width: `${pctDone}%`, height: "100%", background: statusColor, transition: "width 300ms ease" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 11, fontFamily: "var(--v2-font-mono)", color: "var(--v2-text-secondary)" }}>
            <span data-testid="v2-home-shadow-cert-rate">exec-rate {rate.toFixed(2)}%</span>
            <span data-testid="v2-home-shadow-cert-outcomes">{Object.entries(outcomes).map(([k, v]) => `${k}:${v}`).join(" · ") || "—"}</span>
          </div>
          {recent.length > 0 ? (
            <div style={{ marginTop: 8, borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: 6 }} data-testid="v2-home-shadow-cert-recent">
              {recent.map((cyc) => {
                const p95 = cyc.stage_p95_ms || {};
                const p95max = Object.values(p95).length ? Math.max(...Object.values(p95)) : 0;
                const cs = cyc.cycle_status || "?";
                const csColor = cs === "PASS" ? "var(--v2-verdict-go, #4ade80)"
                              : cs === "WARNING" ? "#facc15"
                              : cs === "FAIL" ? "var(--v2-verdict-no, #f87171)"
                              : "var(--v2-text-muted)";
                return (
                  <div key={cyc.cycle_id} style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontFamily: "var(--v2-font-mono)", padding: "1px 0" }}>
                    <span style={{ color: "var(--v2-text-muted)" }}>#{cyc.cycle_index}</span>
                    <span style={{ color: csColor }}>{cs}</span>
                    <span style={{ color: "var(--v2-text-secondary)" }}>
                      p{cyc.opportunities_processed}·e{cyc.executable_count}·{p95max.toFixed(0)}ms
                    </span>
                  </div>
                );
              })}
            </div>
          ) : null}
        </>
      ) : (
        <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)", marginTop: 4 }}>
          No run active · start via /api/arbicore/certification/shadow/start
        </div>
      )}
      {runId ? (
        <div style={{ marginTop: 6, fontSize: 10, fontFamily: "var(--v2-font-mono)", color: "var(--v2-text-muted)" }} data-testid="v2-home-shadow-cert-runid">
          {runId.slice(0, 24)}…
        </div>
      ) : null}
    </Card>
  );
}

function PulseBand({ pulse, shadowCert }) {
  const d = pulse.data;
  const regime = d?.regime;
  const vitals = d?.opportunity_vitals;
  return (
    <section data-testid="v2-home-pulse" style={{ marginBottom: 20 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
        <Card title="Market regime" testid="v2-home-pulse-regime">
          <div className="v2-num" style={{ fontSize: 20, color: "var(--v2-text-strong)" }}>{regime?.regime || "—"}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)" }}>
            {regime ? `confidence ${Math.round((regime.confidence || 0) * 100)}%` : "no snapshot"}
          </div>
          {regime?.tags?.length ? (
            <div style={{ color: "var(--v2-text-secondary)", fontSize: 11, fontFamily: "var(--v2-font-mono)", marginTop: 4 }}>
              {regime.tags.join(" · ")}
            </div>
          ) : null}
        </Card>
        <Card title="Live pipeline" testid="v2-home-pulse-pipeline">
          <div style={{ display: "flex", gap: 20 }}>
            <MetricStat value={vitals?.total ?? 0} label="opps" testid="v2-home-pulse-total" accent />
            <MetricStat value={Object.keys(vitals?.by_family || {}).length} label="families" testid="v2-home-pulse-families" />
          </div>
        </Card>
        <Card title="Route learning" testid="v2-home-pulse-learning">
          <MetricStat value={d?.route_learning?.tracked_routes ?? 0} label="routes tracked" testid="v2-home-pulse-routes" />
        </Card>
        <ShadowCertificationCard pulse={pulse} current={shadowCert} />
        <Card title="Interlock" testid="v2-home-pulse-interlock">
          <div className="v2-num" style={{ fontSize: 20, color: "var(--v2-verdict-go)" }}>ARMED</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)" }}>Safety armed · Slice 3 wires live</div>
        </Card>
        <Card title="Venue readiness" testid="v2-home-pulse-venues">
          <div className="v2-num" style={{ fontSize: 20, color: "var(--v2-text-strong)" }}>—</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)" }}>Live in Slice 3</div>
        </Card>
        <Card title="Deployable capital" testid="v2-home-pulse-capital">
          <div className="v2-num" style={{ fontSize: 20, color: "var(--v2-text-strong)" }}>—</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)" }}>Live in Slice 4</div>
        </Card>
      </div>
    </section>
  );
}

function PrioritiesBand({ deck }) {
  const navigate = useNavigate();
  const d = deck.data;
  const opps = d?.fresh_opportunities || [];
  return (
    <section data-testid="v2-home-priorities" style={{ marginBottom: 20 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
        <Card
          title={`Fresh opportunities · ${d?.fresh_opportunities_total ?? 0}`}
          testid="v2-home-priorities-fresh"
          actions={
            <button
              onClick={() => navigate("/v2/opportunities")}
              data-testid="v2-home-priorities-fresh-cta"
              style={{ background: "transparent", border: "1px solid var(--v2-border-subtle)", color: "var(--v2-accent-base)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, padding: "2px 8px", borderRadius: 2, cursor: "pointer" }}
            >
              VIEW ALL →
            </button>
          }
        >
          {opps.length === 0 ? (
            <div className="v2-empty">{"> No fresh opportunities.\n> Scanners may be paused or gates are pruning routes."}</div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {opps.slice(0, 5).map((o, i) => (
                <li
                  key={`${o.id}-${i}`}
                  data-testid={`v2-home-priorities-item-${o.id}`}
                  onClick={() => navigate(`/v2/opportunities?id=${o.id}`)}
                  style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--v2-border-subtle)", cursor: "pointer" }}
                >
                  <span style={{ fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>
                    {o.subject_id || o.opportunity_type} · {o.chain || "—"}
                  </span>
                  <ConfidencePill value={o.confidence} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Pending approvals · 0" testid="v2-home-priorities-approvals">
          <div className="v2-empty">{"> No approvals pending.\n> Approval workflow wires live in Slice 3."}</div>
        </Card>
        <Card title="Requires attention · 0" testid="v2-home-priorities-attention">
          <div className="v2-empty">{"> All venues nominal.\n> Alerts + interlock detail wires live in Slice 3."}</div>
        </Card>
      </div>
    </section>
  );
}

function VitalsBand({ summary }) {
  const s = summary.data;
  const by_family = s?.by_family || {};
  const by_chain = s?.by_chain || {};
  const by_status = s?.by_status || {};
  return (
    <section data-testid="v2-home-vitals">
      <Card title="Vitals · 24h" testid="v2-home-vitals-card">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 24 }}>
          <div>
            <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginBottom: 4 }}>By family</div>
            {Object.entries(by_family).map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                <span style={{ fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{k}</span>
                <span className="v2-num" style={{ fontSize: 12, color: "var(--v2-text-strong)" }}>{v}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginBottom: 4 }}>By chain</div>
            {Object.entries(by_chain).map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                <span style={{ fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{k}</span>
                <span className="v2-num" style={{ fontSize: 12, color: "var(--v2-text-strong)" }}>{v}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginBottom: 4 }}>By status</div>
            {Object.entries(by_status).map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "2px 0" }}>
                <span style={{ fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{k}</span>
                <span className="v2-num" style={{ fontSize: 12, color: "var(--v2-text-strong)" }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </section>
  );
}

export default function HomePage() {
  const pulse = usePolled(() => v2Api.pulse(), 5000);
  const deck = useAsync(() => v2Api.deck(5));
  const summary = useAsync(() => v2Api.opportunitiesSummary(24));
  const shadowCert = usePolled(
    () => v2Api.shadowCertCurrent().catch(() => ({ current: null })),
    5000,
  );

  return (
    <section data-testid="v2-home">
      <h1 className="v2-page__title">Home</h1>
      <p className="v2-page__lede">
        Operator briefing. Pulse now · Priorities to work · Vitals over the last 24h.
      </p>
      <PulseBand pulse={pulse} shadowCert={shadowCert} />
      <PrioritiesBand deck={deck} />
      <VitalsBand summary={summary} />
    </section>
  );
}
