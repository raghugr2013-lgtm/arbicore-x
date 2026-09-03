/**
 * ArbiCore X — UI v2 · Opportunities page (Slice 1)
 * Universal feed across all 8 arbitrage families. Filter chips + dense table.
 * Row click / Enter → OpportunityDrawer. A/R shortcuts approve/reject
 * whatever row is currently focused.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { v2Api } from "@/v2/lib/api";
import {
  VerdictBadge,
  ConfidencePill,
  SafetyPill,
  FreshnessBadge,
  ProvenanceChip,
  AnomalyChips,
  fmtBps,
  fmtUsd,
  fmtPct,
} from "@/v2/components/Primitives";
import { OpportunityDrawer } from "@/v2/components/OpportunityDrawer";
import { toast } from "sonner";

const FAMILY_OPTS = ["ALL", "CEX_ARBITRAGE", "DEX_ARBITRAGE", "FUNDING_ARBITRAGE", "CROSS_CHAIN_ARBITRAGE", "FLASH_LOAN_ARBITRAGE", "LAUNCH_ARBITRAGE"];
const VERDICT_OPTS = ["ALL", "GO", "SOFT_NO", "HARD_NO", "UNVERIFIED"];

function Chip({ active, children, onClick, testid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      style={{
        padding: "3px 10px",
        border: `1px solid ${active ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`,
        background: active ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)",
        color: active ? "var(--v2-accent-base)" : "var(--v2-text-secondary)",
        fontFamily: "var(--v2-font-mono)",
        fontSize: 10,
        letterSpacing: 1,
        borderRadius: 2,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

export default function OpportunitiesPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [family, setFamily] = useState("ALL");
  const [verdict, setVerdict] = useState("ALL");
  const [minConf, setMinConf] = useState(0);
  const [chain, setChain] = useState("ALL");
  const [drawerId, setDrawerId] = useState(null);
  const [focusedIdx, setFocusedIdx] = useState(0);
  const [params, setParams] = useSearchParams();
  const rowRefs = useRef([]);
  const navigate = useNavigate();

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await v2Api.opportunitiesList({
        family, chain, verdict, min_confidence: minConf, limit: 100,
      });
      setItems(r.items || []);
      setTotal(r.total || 0);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetch(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [family, chain, verdict, minConf]);

  // Deep-link ?id=<opp-id> → open drawer
  useEffect(() => {
    const id = params.get("id");
    if (id) setDrawerId(id);
  }, [params]);

  const chainOpts = useMemo(() => {
    const s = new Set(items.map((o) => o.chain).filter(Boolean));
    return ["ALL", ...Array.from(s)];
  }, [items]);

  const openRow = (idx) => {
    const o = items[idx];
    if (!o) return;
    setFocusedIdx(idx);
    setDrawerId(o.id);
    setParams({ id: o.id }, { replace: true });
  };

  const closeDrawer = () => {
    setDrawerId(null);
    setParams({}, { replace: true });
  };

  const onKey = (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.isContentEditable) return;
    if (drawerId) return; // drawer keys are separate
    // Ignore modifier combos so ⌘K etc. still reach the shell handler
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocusedIdx((i) => Math.min(items.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocusedIdx((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      openRow(focusedIdx);
    } else if (e.key === "a" || e.key === "A") {
      const o = items[focusedIdx];
      if (o) v2Api.approveOpportunity(o.id).then(() => { toast.success(`Approved ${o.subject_id}`); fetch(); });
    } else if (e.key === "r" || e.key === "R") {
      const o = items[focusedIdx];
      if (o) v2Api.rejectOpportunity(o.id).then(() => { toast.success(`Rejected ${o.subject_id}`); fetch(); });
    }
  };

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, focusedIdx, drawerId]);

  useEffect(() => {
    rowRefs.current[focusedIdx]?.scrollIntoView({ block: "nearest" });
  }, [focusedIdx]);

  return (
    <section data-testid="v2-opportunities">
      <h1 className="v2-page__title">Opportunities</h1>
      <p className="v2-page__lede">
        Universal feed · {total} match{total === 1 ? "" : "es"} · use <span className="v2-kbd">↑↓</span> to move,{" "}
        <span className="v2-kbd">Enter</span> to open, <span className="v2-kbd">A</span>/<span className="v2-kbd">R</span> to approve / reject.
      </p>

      <div data-testid="v2-opp-verdict-legend" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, padding: "8px 12px", marginBottom: 14, border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2, fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 0.5 }}>
        <span style={{ color: "var(--v2-text-muted)", textTransform: "uppercase", letterSpacing: 1 }}>Economic state ladder</span>
        {[
          { k: "DISCOVERED", c: "var(--v2-text-muted)", d: "Raw candidate — nothing priced" },
          { k: "LIVE_QUOTED", c: "var(--v2-conf-mid)", d: "Live spread / venue price exists" },
          { k: "VERIFIED", c: "var(--v2-accent-base)", d: "REAL provenance + economics" },
          { k: "ECONOMICALLY_VALID", c: "var(--v2-verdict-go)", d: "REAL + positive profit + spread → GO-eligible" },
          { k: "M3_GREEN", c: "var(--v2-verdict-go)", d: "M3 execution authority (not enabled)" },
        ].map((s, i, arr) => (
          <span key={s.k} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <span title={s.d} style={{ color: s.c, border: `1px solid ${s.c}`, padding: "1px 6px", borderRadius: 2 }}>{s.k}</span>
            {i < arr.length - 1 && <span style={{ color: "var(--v2-text-muted)" }}>→</span>}
          </span>
        ))}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14, alignItems: "center" }} data-testid="v2-opp-filters">
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Family</span>
        {FAMILY_OPTS.map((f) => (
          <Chip key={f} active={family === f} onClick={() => setFamily(f)} testid={`v2-opp-filter-family-${f}`}>{f.replace("_ARBITRAGE", "")}</Chip>
        ))}
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginLeft: 12, marginRight: 4 }}>Verdict</span>
        {VERDICT_OPTS.map((v) => (
          <Chip key={v} active={verdict === v} onClick={() => setVerdict(v)} testid={`v2-opp-filter-verdict-${v}`}>{v}</Chip>
        ))}
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginLeft: 12, marginRight: 4 }}>Chain</span>
        {chainOpts.map((c) => (
          <Chip key={c} active={chain === c} onClick={() => setChain(c)} testid={`v2-opp-filter-chain-${c}`}>{c}</Chip>
        ))}
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginLeft: 12, marginRight: 4 }}>Min conf</span>
        <select
          value={minConf}
          onChange={(e) => setMinConf(Number(e.target.value))}
          data-testid="v2-opp-filter-minconf"
          style={{ background: "var(--v2-bg-panel)", color: "var(--v2-text-primary)", border: "1px solid var(--v2-border-subtle)", fontFamily: "var(--v2-font-mono)", fontSize: 10, padding: "3px 6px", borderRadius: 2 }}
        >
          {[0, 0.4, 0.6, 0.7, 0.8].map((v) => (<option key={v} value={v}>{v === 0 ? "any" : `${v * 100}%+`}</option>))}
        </select>
      </div>

      <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 }} data-testid="v2-opp-table-wrap">
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 }} data-testid="v2-opp-table">
          <thead>
            <tr style={{ background: "var(--v2-bg-panel)" }}>
              {["Asset", "Family", "Chain", "Verdict", "Confidence", "Safety", "Spread", "Capital req.", "Est. profit", "Provenance", "Age"].map((h) => (
                <th key={h} style={{ textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={11} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={11} style={{ padding: 0 }}>
                <div className="v2-empty" style={{ margin: 12 }}>
                  {`> 0 opportunities match the current filters.\n> Try widening Family, Chain, or lowering Min Confidence.\n> Full gate reasoning arrives in Slice 3 (Operations · Scanners).`}
                </div>
              </td></tr>
            )}
            {!loading && items.map((o, i) => (
              <tr
                key={`${o.id}-${i}`}
                ref={(el) => (rowRefs.current[i] = el)}
                data-testid={`v2-opp-row-${o.id}`}
                onClick={() => openRow(i)}
                onFocus={() => setFocusedIdx(i)}
                style={{
                  cursor: "pointer",
                  background: focusedIdx === i ? "var(--v2-bg-selected)" : "transparent",
                  borderBottom: "1px solid var(--v2-border-subtle)",
                }}
              >
                <td style={{ padding: "6px 10px", color: "var(--v2-text-strong)" }}>{o.subject_id}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{(o.opportunity_type || "").replace("_ARBITRAGE", "")}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-secondary)" }}>{o.chain}</td>
                <td style={{ padding: "6px 10px" }}><VerdictBadge verdict={o.verdict} /></td>
                <td style={{ padding: "6px 10px" }}><ConfidencePill value={o.confidence} /></td>
                <td style={{ padding: "6px 10px" }}><SafetyPill value={o.safety} /></td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }}>{fmtBps(o.spread_bps)}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }}>{fmtUsd(o.capital_required_usd)}</td>
                <td style={{ padding: "6px 10px", color: "var(--v2-text-primary)" }} data-testid={`v2-opp-profit-${o.id}`}>
                  {fmtUsd(o.expected_profit_usd)}
                  {o.return_pct != null && (
                    <span style={{ color: "var(--v2-text-muted)", marginLeft: 6 }}>({fmtPct(o.return_pct)})</span>
                  )}
                  {Array.isArray(o.data_quality_flags) && o.data_quality_flags.length > 0 && (
                    <div style={{ marginTop: 3 }}>
                      <AnomalyChips flags={o.data_quality_flags} testid={`v2-opp-dq-${o.id}`} />
                    </div>
                  )}
                </td>
                <td style={{ padding: "6px 10px" }}><ProvenanceChip value={o.source_data_quality} testid={`v2-opp-prov-${o.id}`} /></td>
                <td style={{ padding: "6px 10px" }}><FreshnessBadge ageSeconds={o.age_s} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <OpportunityDrawer
        id={drawerId}
        open={!!drawerId}
        onOpenChange={(v) => { if (!v) closeDrawer(); }}
        onActioned={() => fetch()}
      />
    </section>
  );
}
