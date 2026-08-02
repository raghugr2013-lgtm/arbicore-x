/**
 * ArbiCore X — UI v2 · Intelligence page (Slice 2)
 * Sub-rail with 7 sections; Recommendations + Confidence activated in this slice.
 * The rest render inline "arrives in Slice N" hints so the section stays discoverable.
 */
import { useEffect, useState } from "react";
import { Route, Routes, NavLink, Navigate } from "react-router-dom";
import { v2Api } from "@/v2/lib/api";
import { ConfidencePill, VerdictBadge, fmtPct } from "@/v2/components/Primitives";

const SUB_SECTIONS = [
  { key: "recommendations", label: "Recommendations", slice: 2 },
  { key: "confidence", label: "Confidence", slice: 2 },
  { key: "calibration", label: "Calibration", slice: "W1" },
  { key: "models", label: "Models", slice: "W1" },
  { key: "analytics", label: "Analytics", slice: 4 },
  { key: "certification", label: "Certification & Evidence", slice: "W2" },
  { key: "market", label: "Market Intelligence", slice: 5 },
  { key: "learning", label: "Learning", slice: 5 },
  { key: "knowledge", label: "Knowledge", slice: "W2" },
];

function SubNav() {
  return (
    <nav data-testid="v2-intel-subnav" style={{ display: "flex", flexWrap: "wrap", gap: 4, borderBottom: "1px solid var(--v2-border-subtle)", marginBottom: 16, paddingBottom: 8 }}>
      {SUB_SECTIONS.map((s) => (
        <NavLink
          key={s.key}
          to={`/v2/intelligence/${s.key}`}
          data-testid={`v2-intel-tab-${s.key}`}
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

function Panel({ title, testid, children }) {
  return (
    <div className="v2-panel" data-testid={testid}>
      <div className="v2-panel__title">{title}</div>
      {children}
    </div>
  );
}

function useAsync(fn, deps = []) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let alive = true;
    setState({ loading: true, data: null, error: null });
    fn()
      .then((d) => alive && setState({ loading: false, data: d, error: null }))
      .catch((e) => alive && setState({ loading: false, data: null, error: e }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

function Recommendations() {
  const { loading, data, error } = useAsync(() => v2Api.recommendations());
  if (loading) return <div className="v2-empty">Loading recommendations…</div>;
  if (error) return <div className="v2-empty">{"> Unable to reach backend."}</div>;
  return (
    <section data-testid="v2-intel-recommendations" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12 }}>
      <Panel title="Top routes · by win rate" testid="v2-intel-top-routes">
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
          <thead>
            <tr>
              {["Route", "Win", "Trials", "Mean ROI"].map((h) => (
                <th key={h} style={{ textAlign: "left", color: "var(--v2-text-muted)", padding: "6px 4px", fontWeight: 500, letterSpacing: 1, textTransform: "uppercase", fontSize: 10, borderBottom: "1px solid var(--v2-border-subtle)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data?.top_routes || []).map((r, i) => (
              <tr key={i} data-testid={`v2-intel-route-${i}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ padding: "6px 4px", color: "var(--v2-text-primary)" }}>{r.route}</td>
                <td style={{ padding: "6px 4px", color: r.win_rate >= 0.6 ? "var(--v2-verdict-go)" : "var(--v2-text-primary)" }}>{Math.round(r.win_rate * 100)}%</td>
                <td style={{ padding: "6px 4px", color: "var(--v2-text-secondary)" }}>{r.trials}</td>
                <td style={{ padding: "6px 4px", color: "var(--v2-text-primary)" }}>{fmtPct(r.mean_roi)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title="Top chains · by activity" testid="v2-intel-top-chains">
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {(data?.top_chains || []).map((c, i) => (
            <li key={i} data-testid={`v2-intel-chain-${c.chain}`} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--v2-border-subtle)" }}>
              <span style={{ fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>{c.chain}</span>
              <span style={{ display: "flex", gap: 10 }}>
                <span className="v2-num" style={{ fontSize: 12, color: "var(--v2-text-strong)" }}>{c.opps_24h}</span>
                <ConfidencePill value={c.avg_confidence} label="CONF" />
              </span>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Top entities · by score" testid="v2-intel-top-entities">
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {(data?.top_entities || []).map((e, i) => (
            <li key={i} data-testid={`v2-intel-entity-${e.entity}`} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--v2-border-subtle)" }}>
              <span style={{ fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>
                {e.entity}
                <span style={{ marginLeft: 6, color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>{e.kind}</span>
              </span>
              <ConfidencePill value={e.score} />
            </li>
          ))}
        </ul>
      </Panel>
    </section>
  );
}

function Confidence() {
  const [verdict, setVerdict] = useState("ALL");
  const [family, setFamily] = useState("ALL");
  const [minConf, setMinConf] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    v2Api.decisions({ verdict, family, min_confidence: minConf, limit: 200 })
      .then((r) => alive && setItems(r.items || []))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [verdict, family, minConf]);

  const FAM = ["ALL", "CEX_ARBITRAGE", "DEX_ARBITRAGE", "FUNDING_ARBITRAGE", "FLASH_LOAN_ARBITRAGE"];
  const VER = ["ALL", "GO", "SOFT_NO", "HARD_NO"];

  const chip = (active, label, onClick, testid) => (
    <button
      key={testid}
      type="button"
      onClick={onClick}
      data-testid={testid}
      style={{
        padding: "3px 10px",
        border: `1px solid ${active ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`,
        background: active ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)",
        color: active ? "var(--v2-accent-base)" : "var(--v2-text-secondary)",
        fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer",
      }}
    >{label}</button>
  );

  return (
    <section data-testid="v2-intel-confidence">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12, alignItems: "center" }} data-testid="v2-intel-confidence-filters">
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Verdict</span>
        {VER.map((v) => chip(verdict === v, v, () => setVerdict(v), `v2-intel-conf-filter-verdict-${v}`))}
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginLeft: 12, marginRight: 4 }}>Family</span>
        {FAM.map((f) => chip(family === f, f.replace("_ARBITRAGE", ""), () => setFamily(f), `v2-intel-conf-filter-family-${f}`))}
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginLeft: 12, marginRight: 4 }}>Min conf</span>
        <select value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} data-testid="v2-intel-conf-filter-minconf"
                style={{ background: "var(--v2-bg-panel)", color: "var(--v2-text-primary)", border: "1px solid var(--v2-border-subtle)", fontFamily: "var(--v2-font-mono)", fontSize: 10, padding: "3px 6px", borderRadius: 2 }}>
          {[0, 0.4, 0.6, 0.7, 0.8].map((v) => (<option key={v} value={v}>{v === 0 ? "any" : `${v * 100}%+`}</option>))}
        </select>
      </div>

      <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="v2-intel-decision-table">
          <thead>
            <tr style={{ background: "var(--v2-bg-panel)" }}>
              {["Decision", "Asset", "Family", "Verdict", "Confidence", "Regime", "Top factors"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (<tr><td colSpan={7} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && items.length === 0 && (
              <tr><td colSpan={7} style={{ padding: 0 }}>
                <div className="v2-empty" style={{ margin: 12 }}>{"> 0 decisions match the current filters.\n> Widen Verdict/Family or lower Min conf."}</div>
              </td></tr>
            )}
            {!loading && items.map((d) => (
              <tr key={d.id} data-testid={`v2-intel-decision-${d.id}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{d.id}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-strong)" }}>{d.asset}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{d.family.replace("_ARBITRAGE", "")}</td>
                <td style={{ padding: "6px 10px" }}><VerdictBadge verdict={d.verdict} /></td>
                <td style={{ padding: "6px 10px" }}><ConfidencePill value={d.confidence} /></td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{d.regime}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)", fontSize: 11 }}>{(d.top_factors || []).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ScheduledSub({ label, slice, testid }) {
  return (
    <div className="v2-empty" data-testid={testid}>
      {`> ${label} · scheduled for Slice ${slice}.\n> Roadmap: docs/ui_v2/05_IMPLEMENTATION_ROADMAP.md`}
    </div>
  );
}

/* --------------------------------------------------------------------------
 * Wave-2 exposures — read-only reference panels backed by file-verified
 * canonical engines (certification_review, entity graph). Zero business
 * logic; UI mirrors the canonical response shape 1:1.
 * -------------------------------------------------------------------------- */

function Certification() {
  const [state, setState] = useState({ loading: true, data: null });
  useEffect(() => {
    let alive = true;
    v2Api.certification().then((d) => alive && setState({ loading: false, data: d })).catch(() => alive && setState({ loading: false, data: null }));
    return () => { alive = false; };
  }, []);
  if (state.loading) return <div className="v2-empty">Loading certification review…</div>;
  const d = state.data;
  if (!d) return <div className="v2-empty">{"> Certification review unreachable."}</div>;

  const REC_MAP = {
    "READY_FOR_MICROCAPITAL_REVIEW": "var(--v2-verdict-go)",
    "NEEDS_MORE_DATA": "var(--v2-verdict-no-soft)",
    "NOT_READY": "var(--v2-verdict-no-hard)",
  };
  const VERDICT_MAP = { PASS: "var(--v2-verdict-go)", FAIL: "var(--v2-verdict-no-hard)", INFO: "var(--v2-accent-base)" };
  const s = d.summary || {};

  return (
    <section data-testid="v2-intel-certification">
      <div className="v2-panel" style={{ marginBottom: 12 }} data-testid="v2-intel-certification-headline">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div className="v2-panel__title">Shadow certification review</div>
            <div className="v2-num" style={{ fontSize: 18, color: "var(--v2-text-strong)" }}>{d.headline || d.recommendation || "—"}</div>
            <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, marginTop: 4 }}>
              {d.phase} · campaign {d.campaign?.id || "—"}
            </div>
          </div>
          <StateTag value={d.recommendation || "—"} map={REC_MAP} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div className="v2-panel"><div className="v2-num" style={{ fontSize: 22 }}>{s.total_cycles ?? "—"}</div><div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Total cycles</div></div>
        <div className="v2-panel"><div className="v2-num" style={{ fontSize: 22, color: "var(--v2-verdict-go)" }}>{s.completion_rate_pct != null ? s.completion_rate_pct.toFixed(1) + "%" : "—"}</div><div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Completion</div></div>
        <div className="v2-panel"><div className="v2-num" style={{ fontSize: 22, color: s.stuck_rate_pct > 10 ? "var(--v2-verdict-no-soft)" : "var(--v2-text-strong)" }}>{s.stuck_rate_pct != null ? s.stuck_rate_pct.toFixed(1) + "%" : "—"}</div><div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Stuck rate</div></div>
        <div className="v2-panel"><div className="v2-num" style={{ fontSize: 22, color: "var(--v2-accent-base)" }}>{s.recovery_success_rate_pct != null ? s.recovery_success_rate_pct.toFixed(0) + "%" : "—"}</div><div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Recovery</div></div>
        <div className="v2-panel"><div className="v2-num" style={{ fontSize: 22 }}>${s.avg_realized_per_cycle != null ? s.avg_realized_per_cycle.toFixed(0) : "—"}</div><div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Avg realised</div></div>
        <div className="v2-panel"><div className="v2-num" style={{ fontSize: 22, color: "var(--v2-accent-base)" }}>${s.recommended_safe_cycle_usd != null ? s.recommended_safe_cycle_usd.toFixed(0) : "—"}</div><div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Safe cycle size</div></div>
      </div>

      <div style={{ ...CARD, marginBottom: 12 }}>
        <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>
          Readiness sections · {s.criteria_passed ?? 0} passed · {s.criteria_failed ?? 0} failed · {s.criteria_na ?? 0} n/a
        </div>
        <table style={TABLE} data-testid="v2-intel-certification-sections">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Section", "Verdict", "Evidence"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(d.sections || []).map((sec, i) => (
              <tr key={i} data-testid={`v2-intel-certification-section-${i}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)", width: 240 }}>{sec.title}</td>
                <td style={{ ...TD, width: 90 }}><StateTag value={sec.verdict} map={VERDICT_MAP} /></td>
                <td style={TD}>
                  {(sec.evidence || []).map((e, j) => (
                    <div key={j} style={{ fontFamily: "var(--v2-font-mono)", fontSize: 11, color: "var(--v2-text-secondary)", lineHeight: 1.6 }}>
                      <span style={{ color: "var(--v2-text-muted)" }}>{e.metric}</span>
                      {" · "}<span style={{ color: "var(--v2-text-primary)" }}>{typeof e.value === "number" ? e.value : (e.value ?? "—")}</span>
                      {e.threshold != null && <> {" vs "} <span style={{ color: "var(--v2-text-muted)" }}>{e.threshold}</span></>}
                      {" · "}<span style={{ color: VERDICT_MAP[e.status] || "var(--v2-text-muted)" }}>{e.status}</span>
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(d.next_steps || []).length > 0 && (
        <div className="v2-panel" data-testid="v2-intel-certification-next">
          <div className="v2-panel__title">Next steps</div>
          <ul style={{ margin: 0, paddingLeft: 20, color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11, lineHeight: 1.7 }}>
            {(d.next_steps || []).map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}

      <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, marginTop: 12 }}>
        &gt; {d.note}
      </div>
    </section>
  );
}

function Entities() {
  const [entityType, setEntityType] = useState("ALL");
  const [state, setState] = useState({ loading: true, data: null });
  useEffect(() => {
    let alive = true;
    setState((p) => ({ ...p, loading: true }));
    v2Api.entities({ entity_type: entityType, limit: 50 })
      .then((d) => alive && setState({ loading: false, data: d }))
      .catch(() => alive && setState({ loading: false, data: null }));
    return () => { alive = false; };
  }, [entityType]);
  const d = state.data;
  const TYPE_COLOR = {
    SMART_MONEY: "var(--v2-verdict-go)",
    MARKET_MAKER: "var(--v2-accent-base)",
    EXCHANGE_WALLET: "var(--v2-regime-active)",
    LIQUIDITY_PROVIDER: "var(--v2-accent-base)",
    LAUNCH_PARTICIPANT: "var(--v2-verdict-no-soft)",
    CEX_ACCOUNT: "var(--v2-text-secondary)",
    DEX_POOL: "var(--v2-accent-base)",
    WALLET: "var(--v2-text-secondary)",
    UNKNOWN: "var(--v2-text-muted)",
  };
  const VOCAB = ["ALL", ...(d?.vocabulary || [])];

  return (
    <section data-testid="v2-intel-entities">
      {d && (
        <div className="v2-panel" style={{ marginBottom: 12 }} data-testid="v2-intel-entities-summary">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div className="v2-panel__title">Entity graph</div>
              <div className="v2-num" style={{ fontSize: 22, color: "var(--v2-accent-base)" }}>{d.total_entities}</div>
              <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1 }}>
                {d.count} shown · {Object.keys(d.counts_by_type || {}).length} types
              </div>
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "flex-end", maxWidth: "60%" }}>
              {Object.entries(d.counts_by_type || {}).map(([t, n]) => (
                <div key={t} data-testid={`v2-intel-entities-count-${t}`} style={{ textAlign: "right" }}>
                  <div style={{ color: TYPE_COLOR[t] || "var(--v2-text-primary)", fontFamily: "var(--v2-font-mono)", fontSize: 14 }}>{n}</div>
                  <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 9, letterSpacing: 1 }}>{t}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Type</span>
        {VOCAB.map((t) => (
          <button key={t} onClick={() => setEntityType(t)} data-testid={`v2-intel-entities-filter-${t}`}
                  style={{ padding: "3px 10px", border: `1px solid ${entityType === t ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`, background: entityType === t ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)", color: entityType === t ? "var(--v2-accent-base)" : "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer" }}>{t}</button>
        ))}
      </div>

      <div style={CARD}>
        <table style={TABLE} data-testid="v2-intel-entities-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Entity", "Type", "Score", "Samples", "Notable"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {state.loading && (<tr><td colSpan={5} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!state.loading && (d?.items || []).length === 0 && (
              <tr><td colSpan={5} style={{ padding: 0 }}><div className="v2-empty" style={{ margin: 12 }}>{"> 0 entities match the current filter."}</div></td></tr>
            )}
            {!state.loading && (d?.items || []).map((e) => (
              <tr key={e.entity_id} data-testid={`v2-intel-entities-row-${e.entity_id}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{e.label}</td>
                <td style={TD}><StateTag value={e.entity_type} map={TYPE_COLOR} /></td>
                <td style={{ ...TD, color: e.score >= 0.8 ? "var(--v2-verdict-go)" : "var(--v2-text-primary)", width: 80 }}>{(e.score * 100).toFixed(0)}%</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)", width: 100 }}>{e.samples?.toLocaleString?.()}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{e.extras?.notable || (e.extras?.chains ? `chains: ${e.extras.chains.join(", ")}` : (e.extras?.chain || e.extras?.venue || "—"))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, marginTop: 8 }}>
        &gt; Read-only reference. Vocabulary is frozen. Scores from EntityScorer.top() (canonical).
      </div>
    </section>
  );
}

/* --------------------------------------------------------------------------
 * Wave-1 read-only reference panels — expose activated learning surfaces.
 * No writes, no business logic, purely observability for operator + auditor.
 * Reuses v2 tokens + Primitives + fmtPct. Contract additions only.
 * -------------------------------------------------------------------------- */

const CARD = { border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 };
const TABLE = { width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 };
const TH = { textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" };
const TD = { padding: "6px 10px" };

function StateTag({ value, map }) {
  const color = map?.[value] || "var(--v2-text-muted)";
  return (
    <span style={{ padding: "1px 6px", fontFamily: "var(--v2-font-mono)", fontSize: 9, letterSpacing: 1, border: `1px solid ${color}`, color, borderRadius: 2 }}>
      {value || "—"}
    </span>
  );
}

function Calibration() {
  const [state, setState] = useState({ loading: true, data: null });
  useEffect(() => {
    let alive = true;
    v2Api.calibration().then((d) => alive && setState({ loading: false, data: d })).catch(() => alive && setState({ loading: false, data: null }));
    return () => { alive = false; };
  }, []);
  if (state.loading) return <div className="v2-empty">Loading calibration…</div>;
  const d = state.data;
  if (!d) return <div className="v2-empty">{"> Calibration surface unreachable."}</div>;
  const maxN = Math.max(1, ...(d.buckets || []).map((b) => b.n));
  return (
    <section data-testid="v2-intel-calibration">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div className="v2-panel" data-testid="v2-intel-calibration-brier">
          <div className="v2-num" style={{ fontSize: 22, color: "var(--v2-accent-base)" }}>{d.brier_score}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Brier score</div>
        </div>
        <div className="v2-panel" data-testid="v2-intel-calibration-ece">
          <div className="v2-num" style={{ fontSize: 22, color: d.drift_alert ? "var(--v2-verdict-no-soft)" : "var(--v2-text-strong)" }}>{d.ece}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Expected calibration error</div>
        </div>
        <div className="v2-panel">
          <div className="v2-num" style={{ fontSize: 22, color: "var(--v2-text-strong)" }}>{d.n_samples?.toLocaleString?.()}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Samples · {d.window_days}d</div>
        </div>
        <div className="v2-panel">
          <StateTag value={d.drift_alert ? "DRIFT" : "OK"} map={{ OK: "var(--v2-verdict-go)", DRIFT: "var(--v2-verdict-no-soft)" }} />
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)", marginTop: 6 }}>Drift status</div>
        </div>
      </div>
      <div style={{ ...CARD, marginBottom: 12 }}>
        <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>
          Reliability diagram · model {d.model}
        </div>
        <table style={TABLE} data-testid="v2-intel-calibration-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Bucket", "Predicted", "Realised", "Gap", "N", "Reliability"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(d.buckets || []).map((b) => {
              const gap = b.realised - b.predicted;
              const gapColor = Math.abs(gap) > 0.05 ? "var(--v2-verdict-no-soft)" : "var(--v2-text-secondary)";
              return (
                <tr key={b.bucket} data-testid={`v2-intel-calibration-bucket-${b.bucket}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                  <td style={{ ...TD, color: "var(--v2-text-strong)", width: 90 }}>{b.bucket}</td>
                  <td style={{ ...TD, color: "var(--v2-text-secondary)", width: 90 }}>{fmtPct(b.predicted)}</td>
                  <td style={{ ...TD, color: "var(--v2-text-primary)", width: 90 }}>{fmtPct(b.realised)}</td>
                  <td style={{ ...TD, color: gapColor, width: 80 }}>{(gap >= 0 ? "+" : "") + (gap * 100).toFixed(1) + "pp"}</td>
                  <td style={{ ...TD, color: "var(--v2-text-secondary)", width: 60 }}>{b.n}</td>
                  <td style={TD}>
                    <div style={{ display: "flex", gap: 4, alignItems: "center", height: 8 }}>
                      <div style={{ width: `${(b.n / maxN) * 60}%`, height: 6, background: "var(--v2-accent-base)", borderRadius: 1 }} />
                      <div style={{ width: `${Math.min(Math.abs(gap) * 400, 40)}%`, height: 6, background: gapColor, borderRadius: 1, opacity: 0.7 }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1 }}>
        &gt; Read-only reference. Well-calibrated ≈ every bucket&apos;s realised matches predicted. Gap {'>'}5pp = drift risk.
      </div>
    </section>
  );
}

function Models() {
  const [state, setState] = useState({ loading: true, data: null });
  useEffect(() => {
    let alive = true;
    v2Api.models().then((d) => alive && setState({ loading: false, data: d })).catch(() => alive && setState({ loading: false, data: null }));
    return () => { alive = false; };
  }, []);
  if (state.loading) return <div className="v2-empty">Loading models…</div>;
  const d = state.data;
  if (!d) return <div className="v2-empty">{"> Model registry unreachable."}</div>;
  const STATE_MAP = { ACTIVE: "var(--v2-verdict-go)", SHADOW: "var(--v2-accent-base)", RETIRED: "var(--v2-text-muted)" };
  return (
    <section data-testid="v2-intel-models">
      <div style={{ ...CARD, marginBottom: 12 }}>
        <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>
          Active + shadow models
        </div>
        <table style={TABLE} data-testid="v2-intel-models-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Model", "Kind", "State", "Promoted", "Trained on", "Eval Brier", "Eval ECE"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(d.items || []).map((m) => (
              <tr key={m.id} data-testid={`v2-intel-model-${m.id}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{m.id}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{m.kind}</td>
                <td style={TD}><StateTag value={m.state} map={STATE_MAP} /></td>
                <td style={{ ...TD, color: "var(--v2-text-muted)" }}>{m.promoted_at ? m.promoted_at.slice(0, 10) : "—"}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{m.trained_on_samples?.toLocaleString?.()}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{m.eval_brier}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{m.eval_ece}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={CARD}>
        <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>
          Promotion history
        </div>
        <table style={TABLE} data-testid="v2-intel-models-promotions">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["When", "From", "To", "Reason"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(d.promotions || []).map((p, i) => (
              <tr key={i} data-testid={`v2-intel-models-promotion-${i}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-muted)", width: 120 }}>{p.at?.slice(0, 10)}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{p.from}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{p.to}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{p.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, marginTop: 8 }}>
        &gt; Read-only reference. Shadow models run in parallel; only ACTIVE models drive live verdicts.
      </div>
    </section>
  );
}

export default function IntelligencePage() {
  return (
    <section data-testid="v2-intelligence">
      <h1 className="v2-page__title">Intelligence</h1>
      <p className="v2-page__lede">Recommendations · Confidence · Analytics · Certification · Market · Learning · Knowledge.</p>
      <SubNav />
      <Routes>
        <Route index element={<Navigate to="recommendations" replace />} />
        <Route path="recommendations" element={<Recommendations />} />
        <Route path="confidence" element={<Confidence />} />
        <Route path="calibration" element={<Calibration />} />
        <Route path="models" element={<Models />} />
        <Route path="analytics" element={<ScheduledSub label="Analytics" slice={4} testid="v2-intel-scheduled-analytics" />} />
        <Route path="certification" element={<Certification />} />
        <Route path="market" element={<ScheduledSub label="Market Intelligence" slice={5} testid="v2-intel-scheduled-market" />} />
        <Route path="learning" element={<ScheduledSub label="Learning" slice={5} testid="v2-intel-scheduled-learning" />} />
        <Route path="knowledge" element={<Entities />} />
      </Routes>
    </section>
  );
}
