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
  { key: "analytics", label: "Analytics", slice: 4 },
  { key: "certification", label: "Certification & Evidence", slice: 4 },
  { key: "market", label: "Market Intelligence", slice: 5 },
  { key: "learning", label: "Learning", slice: 5 },
  { key: "knowledge", label: "Knowledge", slice: 5 },
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
        <Route path="analytics" element={<ScheduledSub label="Analytics" slice={4} testid="v2-intel-scheduled-analytics" />} />
        <Route path="certification" element={<ScheduledSub label="Certification & Evidence" slice={4} testid="v2-intel-scheduled-certification" />} />
        <Route path="market" element={<ScheduledSub label="Market Intelligence" slice={5} testid="v2-intel-scheduled-market" />} />
        <Route path="learning" element={<ScheduledSub label="Learning" slice={5} testid="v2-intel-scheduled-learning" />} />
        <Route path="knowledge" element={<ScheduledSub label="Knowledge" slice={5} testid="v2-intel-scheduled-knowledge" />} />
      </Routes>
    </section>
  );
}
