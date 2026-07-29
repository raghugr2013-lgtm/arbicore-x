import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtUsd, fmtTime } from "@/lib/fmt";
import { FreshnessBadge } from "@/components/execution/FreshnessBadge";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// precise price (BDAG trades at ~4e-05 — show 8 decimals so it reconciles by hand)
const fmtP = (v) => (v == null ? "—" : Number(v).toFixed(8));
const age = (s) => (s == null ? "—" : `${s}s`);

const GV = { GO: "#34d399", WAIT: "#ffb224", NO_GO: "#f87171" };
const IV = { READY: "#34d399", WAIT: "#ffb224", BLOCKED: "#f87171" };

const Card = ({ title, children, testid, right }) => (
  <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid={testid}>
    <div className="flex items-center justify-between mb-2">
      <div className="font-mono text-[10px] font-bold tracking-wider text-[#38bdf8]">{title}</div>
      {right}
    </div>
    <div className="font-mono text-[10px] text-[#8b97a6] space-y-1">{children}</div>
  </div>
);

const Row = ({ k, v, c, mono }) => (
  <div className="flex justify-between gap-3">
    <span className="text-[#6b7888]">{k}</span>
    <span className={`font-bold text-right ${mono ? "tabular-nums" : ""}`} style={{ color: c || "#c9d4e0" }}>{v}</span>
  </div>
);

export const PriceVerificationPanel = () => {
  const [d, setD] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/price-verification`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [load]);

  if (!d) {
    return (
      <div className="panel" data-testid="price-verification-panel">
        <div className="panel-title">Price Verification &amp; Calculation Transparency</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center">loading transparency data…</div>
      </div>
    );
  }
  if (!d.available) {
    return (
      <div className="panel" data-testid="price-verification-panel">
        <div className="panel-title">Price Verification &amp; Calculation Transparency</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center" data-testid="pv-empty">
          {d.note || "No live opportunity surface to verify."}
        </div>
      </div>
    );
  }

  const ls = d.blockdag_live_swap || {};
  const md = d.market_data || {};
  const calc = d.calculation_transparency || {};
  const tr = d.profitability_trace || {};
  const sc = d.source_comparison || {};
  const dt = d.decision_trace || {};
  const es = d.executable_sizing || {};
  const dr = d.dual_roi || {};
  const fc = dr.fresh_cycle || {};
  const ep = dr.existing_position || {};
  const fcColor = GV[fc.verdict] || "#6b7888";
  const fr = d.freshness || {};
  const gc = GV[dt.gate_verdict] || "#6b7888";
  const ic = IV[dt.interlock_verdict] || "#6b7888";

  return (
    <div className="panel" data-testid="price-verification-panel">
      <div className="panel-title">
        Price Verification &amp; Calculation Transparency
        <span className="float-right inline-flex items-center gap-2 text-[#3d4a59]">
          <FreshnessBadge invalid={fr.all_fresh == null} stale={fr.all_fresh === false} showAge={false} testid="pv-freshness" />
          read-only · {(d.sell_venue || "").toUpperCase()}
        </span>
      </div>

      {/* Dual ROI — Part 3: Existing Position (info) vs Fresh Cycle (execution authority) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-1" data-testid="pv-dual-roi">
        <div className="border p-3" data-testid="pv-existing-roi"
             style={{ borderColor: "#1f2a36", background: "#0a0e13" }}>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold text-[#8b97a6]">Existing Position ROI</span>
            <span className="font-mono text-[8px] px-1.5 py-0.5 border border-[#3d4a59] text-[#6b7888]">INFORMATIONAL</span>
          </div>
          <div className="font-mono text-2xl font-bold mt-1" data-testid="pv-existing-roi-pct"
               style={{ color: ep.roi_pct > 0 ? "#34d399" : ep.roi_pct != null ? "#f87171" : "#5a6573" }}>
            {ep.roi_pct != null ? `${ep.roi_pct > 0 ? "+" : ""}${ep.roi_pct}%` : "—"}
          </div>
          <div className="font-mono text-[9px] text-[#5a6573]">buy {fmtP(ep.buy_price)} · {ep.buy_source}</div>
          <div className="font-mono text-[8px] text-[#5a6573] mt-1">{ep.purpose}</div>
        </div>
        <div className="border p-3" data-testid="pv-fresh-roi"
             style={{ borderColor: fcColor + "66", background: fcColor + "0d" }}>
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold text-[#c9d4e0]">Fresh Cycle ROI</span>
            <span className="font-mono text-[8px] font-bold px-1.5 py-0.5 border" data-testid="pv-fresh-verdict"
                  style={{ borderColor: fcColor, color: fcColor }}>▶ DRIVES VERDICT · {fc.verdict}</span>
          </div>
          <div className="font-mono text-2xl font-bold mt-1" data-testid="pv-fresh-roi-pct"
               style={{ color: fc.roi_pct > 0 ? "#34d399" : fc.roi_pct != null ? "#f87171" : "#5a6573" }}>
            {fc.roi_pct != null ? `${fc.roi_pct > 0 ? "+" : ""}${fc.roi_pct}%` : "—"}
          </div>
          <div className="font-mono text-[9px] text-[#5a6573]">buy {fmtP(fc.buy_price)} · {fc.buy_source}</div>
          <div className="font-mono text-[8px] text-[#5a6573] mt-1">{fc.purpose}</div>
        </div>
      </div>
      <div className="font-mono text-[8px] text-[#3d4a59] mb-3" data-testid="pv-dual-roi-note">{dr.note}</div>

      {/* Executable sizing banner — Part 1 */}
      <div className="border p-3 mb-3" data-testid="pv-executable-sizing"
           style={{ borderColor: (es.actionable ? "#34d399" : "#f87171") + "66",
                    background: (es.actionable ? "#34d399" : "#f87171") + "0d" }}>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="font-mono text-[8px] text-[#6b7888] tracking-widest uppercase">Certification Size</div>
            <div data-testid="pv-cert-size" className="font-mono text-lg font-bold text-[#34d399]">{fmtUsd(es.certification_size_usd)}</div>
          </div>
          <div>
            <div className="font-mono text-[8px] text-[#6b7888] tracking-widest uppercase">Min Executable Size</div>
            <div data-testid="pv-min-exec" className="font-mono text-lg font-bold text-[#ffb224]">{fmtUsd(es.min_executable_size_usd)}</div>
          </div>
          <div>
            <div className="font-mono text-[8px] text-[#6b7888] tracking-widest uppercase">Actual Executable Rec.</div>
            <div data-testid="pv-actual-exec" className="font-mono text-lg font-bold" style={{ color: es.actionable ? "#34d399" : "#f87171" }}>
              {fmtUsd(es.actual_executable_recommendation_usd)}
            </div>
          </div>
        </div>
        <div className="text-center mt-1">
          <span data-testid="pv-actionable" className="font-mono text-[9px] font-bold px-2 py-0.5 border"
                style={{ borderColor: es.actionable ? "#34d399" : "#f87171", color: es.actionable ? "#34d399" : "#f87171" }}>
            {es.actionable ? "ACTIONABLE" : "NOT ACTIONABLE"}
          </span>
        </div>
        {(es.notes || []).map((n, i) => (
          <div key={i} className="font-mono text-[9px] text-[#f87171] mt-1" data-testid={`pv-exec-note-${i}`}>▸ {n}</div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-2">
        {/* 1. BlockDAG Live Swap */}
        <Card title="BlockDAG Live Swap" testid="pv-live-swap"
              right={<FreshnessBadge ageS={ls.data_age_s} stale={ls.stale} testid="pv-live-swap-freshness" />}>
          <Row k="Live Swap Price" v={fmtP(ls.current_live_swap_price)} c="#38bdf8" mono />
          <Row k="Source" v={ls.source_identifier} />
          <Row k="Timestamp" v={fmtTime(ls.timestamp)} />
          <Row k="Data Age" v={age(ls.data_age_s)} c={ls.stale ? "#f87171" : "#8b97a6"} />
          <a href={ls.source_url} target="_blank" rel="noreferrer" data-testid="pv-live-swap-url"
             className="block text-[9px] text-[#38bdf8] hover:underline truncate pt-1">↗ {ls.source_url}</a>
        </Card>

        {/* 2. Sell-venue market data */}
        <Card title={`${md.venue_label} Market Data`} testid="pv-market-data"
              right={<FreshnessBadge item={fr.order_book} ageS={md.data_age_s} thresholdS={60} testid="pv-orderbook-freshness" />}>
          <Row k="Best Bid" v={fmtP(md.best_bid)} c="#34d399" mono />
          <Row k="Best Ask" v={fmtP(md.best_ask)} c="#f87171" mono />
          <Row k="Bid/Ask Spread" v={md.bid_ask_spread_pct != null ? `${md.bid_ask_spread_pct}%` : "—"} />
          <Row k="Profitable Bid Depth" v={fmtUsd(md.total_profitable_bid_depth_usd)} c="#34d399" />
          <Row k="Total Bid / Ask Depth" v={`${fmtUsd(md.total_bid_depth_usd)} / ${fmtUsd(md.total_ask_depth_usd)}`} />
          <Row k="Weighted Avg Sell" v={fmtP(md.weighted_average_sell_price_used)} c="#38bdf8" mono />
          <Row k="Order Book Time" v={fmtTime(md.order_book_timestamp)} />
          {md.reference_url && (
            <a href={md.reference_url} target="_blank" rel="noreferrer" data-testid="pv-market-url"
               className="block text-[9px] text-[#38bdf8] hover:underline truncate pt-1">↗ {md.reference_url}</a>
          )}
        </Card>

        {/* 3. Calculation transparency */}
        <Card title="Calculation Transparency" testid="pv-calc">
          <Row k="Buy Price Used" v={fmtP(calc.buy_price_used)} c="#ffb224" mono />
          <Row k="Buy Source" v={calc.buy_source_used} c="#ffb224" />
          <Row k="Sell Price Used" v={fmtP(calc.sell_price_used)} c="#34d399" mono />
          <Row k="Sell Source" v={calc.sell_source_used} c="#34d399" />
          <Row k="Weighted Sell Price" v={fmtP(calc.weighted_average_sell_price_used)} c="#38bdf8" mono />
          <div className="text-[9px] text-[#5a6573] pt-1">{calc.weighted_sell_note}</div>
        </Card>

        {/* 4. Full profitability trace */}
        <Card title="Full Profitability Trace" testid="pv-trace"
              right={<span className="font-mono text-[8px] text-[#5a6573]">{tr.size_basis}</span>}>
          {tr.available === false ? (
            <div className="text-[#5a6573]">{tr.note}</div>
          ) : (
            <>
              <Row k="Capital Input" v={fmtUsd(tr.capital_input_usd)} c="#ffb224" />
              <Row k="BDAG Acquired" v={tr.bdag_acquired_base != null ? Number(tr.bdag_acquired_base).toLocaleString() : "—"} />
              <Row k="Trading Fees" v={fmtUsd(tr.trading_fees_usd)} c="#f87171" />
              <Row k="Transfer Fees (BDAG)" v={tr.transfer_fees_bdag ?? "—"} c="#f87171" />
              <Row k="Gas Fee" v={fmtUsd(tr.gas_fee_usd)} c="#f87171" />
              <Row k="Withdrawal Fees" v={fmtUsd(tr.withdrawal_fees_usd)} c="#f87171" />
              <Row k="Gross Proceeds" v={fmtUsd(tr.gross_proceeds_usd)} />
              <Row k="Net Proceeds" v={fmtUsd(tr.net_proceeds_usd)} />
              <Row k="Net Profit" v={fmtUsd(tr.net_profit_usd)} c={tr.net_profit_usd > 0 ? "#34d399" : "#f87171"} />
              <Row k="ROI %" v={tr.roi_pct != null ? `${tr.roi_pct}%` : "—"} c={tr.roi_pct > 0 ? "#34d399" : "#f87171"} />
            </>
          )}
        </Card>
      </div>

      {/* 5. Source comparison */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-2" data-testid="pv-source-comparison">
        <div className="font-mono text-[9px] text-[#6b7888] tracking-wider mb-1">
          BUY-PRICE SOURCE COMPARISON · WINNER = source actually used
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[9px] font-mono">
            <thead>
              <tr className="panel-th text-[#6b7888]">
                <th className="text-left">Candidate</th><th className="text-right">Price</th>
                <th className="text-center">Available</th><th className="text-right">Age</th>
                <th className="text-left">Why</th>
              </tr>
            </thead>
            <tbody>
              {(sc.candidates || []).map((c) => (
                <tr key={c.source} data-testid={`pv-source-${c.source}`}
                    className="border-b border-[#1f2a36]/50"
                    style={{ background: c.winner ? "rgba(52,211,153,0.07)" : "transparent" }}>
                  <td className="py-1 font-bold" style={{ color: c.winner ? "#34d399" : "#c9d4e0" }}>
                    {c.winner ? "★ " : ""}{c.label}{c.winner ? " (WINNER)" : ""}
                  </td>
                  <td className="py-1 text-right tabular-nums text-[#8b97a6]">{c.value != null ? fmtP(c.value) : "—"}</td>
                  <td className="py-1 text-center" style={{ color: c.available ? "#34d399" : "#5a6573" }}>{c.available ? "✓" : "✗"}</td>
                  <td className="py-1 text-right text-[#5a6573]">{age(c.age_s)}</td>
                  <td className="py-1 text-[#5a6573] truncate max-w-[260px]">{c.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="text-[8px] text-[#3d4a59] mt-1">{sc.note}</div>
      </div>

      {/* 6. Opportunity decision trace */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="pv-decision-trace">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono text-[9px] text-[#6b7888] tracking-wider">OPPORTUNITY DECISION TRACE</span>
          <span className="font-mono text-[9px] font-bold px-1.5 border" style={{ borderColor: gc, color: gc }} data-testid="pv-gate-verdict">{dt.gate_verdict}</span>
          <span className="font-mono text-[8px] text-[#5a6573]">interlock</span>
          <span className="font-mono text-[9px] font-bold px-1.5 border" style={{ borderColor: ic, color: ic }} data-testid="pv-interlock-verdict">{dt.interlock_verdict}</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4">
          {(dt.conditions || []).map((c) => (
            <div key={c.key} className="flex items-center gap-2 text-[10px] font-mono py-0.5" data-testid={`pv-cond-${c.key}`}>
              <span style={{ color: c.passed ? "#34d399" : "#f87171" }}>{c.passed ? "✓" : "✗"}</span>
              <span className="flex-1 text-[#8b97a6]">{c.label}</span>
              <span className="text-[8px] text-[#5a6573] truncate max-w-[140px]">{c.detail}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 space-y-0.5">
          {(dt.explanation || []).map((l, i) => (
            <div key={i} className="font-mono text-[9px] text-[#c9d4e0]" data-testid={`pv-explain-${i}`}>· {l}</div>
          ))}
        </div>
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        {d.note}
      </div>
    </div>
  );
};
