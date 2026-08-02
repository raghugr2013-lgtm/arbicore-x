import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtUsd, fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtPrice = (v) => (v == null ? "—" : `$${Number(v).toExponential(4)}`);
const fmtPct = (v) => (v == null ? "—" : `${v}%`);
const fmtBdag = (v) =>
  v == null ? "—" : Number(v) < 0.001 ? Number(v).toExponential(3) : Number(v).toFixed(6);
const fmtAge = (s) => (s == null ? "—" : s < 60 ? `${s.toFixed(1)}s` : `${(s / 60).toFixed(1)}m`);

const Verdict = ({ v }) => {
  const C = { GO: "#34d399", WAIT: "#ffb224", NO_GO: "#f87171" };
  return (
    <span className="font-mono font-bold" style={{ color: C[v] || "#6b7888" }} data-testid="cycle-verdict">
      {v || "—"}
    </span>
  );
};

export const RealCyclePanel = () => {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get(`${API}/execution/cycle-model`)
      .then((r) => setD(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  if (!d) {
    return (
      <div className="panel" data-testid="real-cycle-panel">
        <div className="panel-title">Real Arbitrage Cycle Model</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading cycle model…</div>
      </div>
    );
  }

  const ls = d.blockdag_live_swap || {};
  const cm = d.coinstore_market_intel || {};
  const calc = d.executable_opportunity_calculation || {};
  const fu = calc.fees_used || {};
  const steps = d.cycle_steps || [];

  return (
    <div className="panel" data-testid="real-cycle-panel">
      <div className="panel-title">
        Real Arbitrage Cycle — USDT/BNB → Swap → BDAG → Transfer → Coinstore → USDT → Wallet
        <span className="float-right inline-flex items-center gap-2 text-[#3d4a59]">
          <Verdict v={d.verdict} />
          {loading && <span className="text-[#38bdf8]">↻</span>}
        </span>
      </div>

      {/* === Live Swap card ============================================== */}
      <div className="border border-[#34d399]/30 bg-[#0a120e] p-3 mb-3" data-testid="live-swap-card">
        <div className="flex items-baseline justify-between flex-wrap gap-3">
          <div>
            <div className="text-[9px] tracking-widest uppercase text-[#34d399]">BlockDAG Live Swap · Current Executable Buy Price</div>
            <div className="font-mono text-2xl font-bold text-[#34d399] mt-0.5" data-testid="live-swap-price">
              {fmtPrice(ls.current_live_swap_price)} <span className="text-[10px] text-[#6b7888]">/ BDAG</span>
            </div>
          </div>
          <div className="font-mono text-[10px] text-[#8b97a6] text-right">
            <div>source: <a href={ls.source_url} target="_blank" rel="noreferrer"
                            className="text-[#38bdf8] underline" data-testid="live-swap-source">
              {ls.source_url}
            </a></div>
            <div>id: <code className="text-[#c9d4e0]">{ls.source_identifier || "—"}</code></div>
            <div>fetched: <span data-testid="live-swap-ts" className="text-[#c9d4e0]">{fmtTime(ls.timestamp)}</span></div>
            <div>age: <span className="text-[#c9d4e0]" data-testid="live-swap-age">{fmtAge(ls.data_age_s)}</span> · stale: <span style={{ color: ls.stale ? "#f87171" : "#34d399" }}>{ls.stale ? "YES" : "NO"}</span></div>
          </div>
        </div>
      </div>

      {/* === Coinstore Market Intel card ================================ */}
      <div className="border border-[#ffb224]/30 bg-[#11100a] p-3 mb-3" data-testid="coinstore-intel-card">
        <div className="text-[9px] tracking-widest uppercase text-[#ffb224] mb-2">
          {(cm.venue_label || "COINSTORE")} BDAG/USDT · Live Market Intelligence
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-[11px] mb-2">
          <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Best Bid</div>
            <div data-testid="coinstore-bid" className="text-[#34d399] font-bold">{fmtPrice(cm.best_bid)}</div></div>
          <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Best Ask</div>
            <div data-testid="coinstore-ask" className="text-[#f87171] font-bold">{fmtPrice(cm.best_ask)}</div></div>
          <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Spread</div>
            <div data-testid="coinstore-spread" className="text-[#ffb224] font-bold">{fmtPct(cm.bid_ask_spread_pct)}</div></div>
          <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Weighted Sell (VWAP)</div>
            <div data-testid="coinstore-weighted" className="text-[#a78bfa] font-bold">{fmtPrice(cm.weighted_sell_price)}</div></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-[11px]">
          <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Profitable Bid Depth (USD)</div>
            <div data-testid="coinstore-prof-depth" className="text-[#c9d4e0] font-bold">{fmtUsd(cm.total_profitable_bid_depth_usd)}</div></div>
          <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Profitable Bid Depth (BDAG)</div>
            <div className="text-[#c9d4e0] font-bold">{fmtBdag(cm.total_profitable_bid_depth_base)}</div></div>
          <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Total Executable Liquidity</div>
            <div data-testid="coinstore-total-liq" className="text-[#c9d4e0] font-bold">{fmtUsd(cm.total_executable_liquidity_usd)}</div></div>
          <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Order Book TS · Age</div>
            <div data-testid="coinstore-ts" className="text-[#c9d4e0] font-bold">{fmtTime(cm.order_book_timestamp)} · {fmtAge(cm.data_age_s)}</div></div>
        </div>
        <div className="mt-2 text-[9px] font-mono text-[#3d4a59]">
          Reference: <a href={cm.reference_url} target="_blank" rel="noreferrer" className="text-[#38bdf8] underline">{cm.reference_url || "—"}</a>
        </div>
      </div>

      {/* === Executable Opportunity Calculation ========================= */}
      <div className="border border-[#a78bfa]/30 bg-[#0c0a14] p-3 mb-3" data-testid="executable-calc-card">
        <div className="text-[9px] tracking-widest uppercase text-[#a78bfa] mb-2">
          Executable Opportunity Calculation {calc.size_basis ? `· ${calc.size_basis}` : ""}
        </div>
        {!calc.available ? (
          <div className="font-mono text-[10px] text-[#6b7888] py-3 text-center">
            No profitable size at the current book / buy price — buy_price={fmtPrice(calc.buy_price_used)},
            sell_price={fmtPrice(calc.sell_price_used)}. Fresh ROI is negative; verdict is correctly NO_GO.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-[11px] mb-3">
              <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Investment</div>
                <div className="text-[#c9d4e0] font-bold">{fmtUsd(calc.investment_usd)}</div></div>
              <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Gross Profit</div>
                <div className="text-[#34d399] font-bold">{fmtUsd(calc.gross_profit_usd)}</div></div>
              <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Total Fees</div>
                <div className="text-[#f87171] font-bold">{fmtUsd(calc.total_fees_usd)}</div></div>
              <div><div className="text-[8px] text-[#6b7888] uppercase tracking-widest">Net Profit · ROI</div>
                <div className="text-[#a78bfa] font-bold" data-testid="executable-roi">
                  {fmtUsd(calc.net_profit_usd)} · {fmtPct(calc.roi_pct)}
                </div></div>
            </div>
          </>
        )}
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-2">
          <div className="text-[8px] text-[#6b7888] uppercase tracking-widest mb-1">Prices used</div>
          <div className="grid grid-cols-3 gap-2 font-mono text-[10px]">
            <div>Buy <b className="text-[#c9d4e0]" data-testid="calc-buy-price">{fmtPrice(calc.buy_price_used)}</b><br /><span className="text-[#3d4a59]">{calc.buy_source || "—"}</span></div>
            <div>Sell <b className="text-[#c9d4e0]" data-testid="calc-sell-price">{fmtPrice(calc.sell_price_used)}</b><br /><span className="text-[#3d4a59]">{calc.sell_source || "—"}</span></div>
            <div>Weighted Sell <b className="text-[#c9d4e0]" data-testid="calc-weighted">{fmtPrice(calc.weighted_sell_price)}</b><br /><span className="text-[#3d4a59]">{calc.weighted_sell_source || "—"}</span></div>
          </div>
        </div>
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="fees-used">
          <div className="text-[8px] text-[#6b7888] uppercase tracking-widest mb-1">Fees used (per cycle, at recommended size)</div>
          <table className="w-full text-[10px] font-mono">
            <tbody>
              <tr><td className="text-[#8b97a6]">Swap fee</td><td className="text-right text-[#c9d4e0]">{fmtUsd(fu.swap_fee_usd)}</td></tr>
              <tr><td className="text-[#8b97a6]">BSC purchase gas</td><td className="text-right text-[#c9d4e0]">{fmtUsd(fu.purchase_gas_usd)}</td></tr>
              <tr><td className="text-[#8b97a6]">BDAG network transfer fee
                <span className="text-[8px] ml-2 text-[#34d399]">[{fu.bdag_transfer_fee_evidence || "—"}]</span>
              </td><td className="text-right text-[#c9d4e0]">{fmtBdag(fu.bdag_transfer_fee_bdag)} BDAG · {fmtUsd(fu.bdag_transfer_fee_usd)}</td></tr>
              <tr><td className="text-[#8b97a6]">Coinstore trading fee ({fmtPct(fu.trading_fee_pct)})</td><td className="text-right text-[#c9d4e0]">{fmtUsd(fu.trading_fee_usd)}</td></tr>
              <tr><td className="text-[#8b97a6]">USDT BEP20 withdrawal fee</td><td className="text-right text-[#c9d4e0]">{fmtUsd(fu.usdt_withdrawal_fee_usd)}</td></tr>
              <tr><td className="text-[#8b97a6]">Other fees</td><td className="text-right text-[#c9d4e0]">{fmtUsd(fu.other_fees_usd)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* === Cycle Steps ladder ========================================= */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="cycle-steps">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-2">Real Arbitrage Cycle — step-by-step</div>
        <ol className="space-y-1.5">
          {steps.map((s, idx) => {
            const fees = Object.entries(s.fees || {})
              .filter(([k]) => !["evidence", "evidence_count", "network", "trading_fee_pct", "weighted_sell_price", "best_bid_used"].includes(k))
              .filter(([, v]) => v !== null && v !== undefined && v !== 0)
              .map(([k, v]) => `${k}=${typeof v === "number" ? v : v}`).join("  ·  ");
            return (
              <li key={idx} className="border-l-2 border-[#38bdf8]/40 pl-2 font-mono text-[10px]" data-testid={`cycle-step-${s.step}`}>
                <div><span className="text-[#38bdf8] font-bold">{s.step}.</span> <span className="text-[#c9d4e0] font-bold">{s.leg}</span>
                  <span className="text-[#3d4a59] ml-2">{s.source}</span></div>
                <div className="text-[#6b7888] ml-3">
                  IN: <span className="text-[#8b97a6]">{JSON.stringify(s.in)}</span>
                </div>
                <div className="text-[#6b7888] ml-3">
                  OUT: <span className="text-[#8b97a6]">{JSON.stringify(s.out)}</span>
                </div>
                {fees && <div className="text-[#3d4a59] ml-3">Fees: <span className="text-[#a78bfa]">{fees}</span></div>}
                {s.constraints && (
                  <div className="text-[#3d4a59] ml-3">Constraints: <span style={{ color: s.constraints.meets_minimum === false ? "#f87171" : "#34d399" }}>
                    coinstore_min_deposit_bdag={s.constraints.coinstore_min_deposit_bdag} ({s.constraints.meets_minimum === false ? "below minimum" : "ok"})
                  </span></div>
                )}
              </li>
            );
          })}
        </ol>
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        Read-only end-to-end cycle. Fresh ROI authority, Opportunity Gate, and Safety Interlock unchanged.
        Fee evidence: BDAG transfer = {d.fee_evidence?.bdag_transfer_source || "—"}
        ({d.fee_evidence?.bdag_transfer_evidence_count ?? 0} measurements); Coinstore taker/withdrawal/deposit = exchange-sourced.
      </div>
    </div>
  );
};
