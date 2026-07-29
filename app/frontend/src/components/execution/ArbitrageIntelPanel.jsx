import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const UTILS = [25, 50, 75, 100];
const VERDICT = { GO: "#34d399", WAIT: "#ffb224", NO_GO: "#f87171" };
const STAB = { STABLE: "#34d399", MODERATE: "#ffb224", VOLATILE: "#f87171", insufficient_history: "#6b7888" };

const px = (v) => (v == null ? "—" : Number(v).toPrecision(4));
const usd = (v) => (v == null ? "—" : `$${Number(v).toFixed(2)}`);
const ageLabel = (s) =>
  s == null ? "—" : s < 90 ? `${Math.round(s)}s` : s < 5400 ? `${Math.round(s / 60)}m` : s < 172800 ? `${Math.round(s / 3600)}h` : `${Math.round(s / 86400)}d`;

const Tile = ({ label, value, color, testId }) => (
  <div className="bg-[#0a0e13] border border-[#1f2a36] px-2 py-1.5">
    <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div data-testid={testId} className="font-mono text-xs font-bold" style={color ? { color } : {}}>{value}</div>
  </div>
);

export const ArbitrageIntelPanel = () => {
  const [routes, setRoutes] = useState([]);
  const [routeId, setRouteId] = useState("");
  const [util, setUtil] = useState(75);
  const [d, setD] = useState(null);

  useEffect(() => {
    axios.get(`${API}/routes`).then((r) => {
      const list = Array.isArray(r.data) ? r.data : r.data.routes || [];
      setRoutes(list);
      if (list[0]) setRouteId(list[0].id);
    }).catch(() => {});
  }, []);

  const load = useCallback(() => {
    if (!routeId) return;
    axios.get(`${API}/execution/intel/${routeId}`, { params: { utilization_pct: util } })
      .then((r) => setD(r.data)).catch(() => {});
  }, [routeId, util]);

  useEffect(() => {
    load();
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [load]);

  const v = d?.verdict;
  const rec = d?.recommended;
  const stab = d?.buyer_stability;

  return (
    <div className="panel" data-testid="arbitrage-intel-panel">
      <div className="panel-title flex items-center gap-2 flex-wrap">
        <span>BDAG Arbitrage Intelligence Engine (E4.6)</span>
        <div className="flex-1" />
        <select data-testid="intel-route-select" value={routeId} onChange={(e) => setRouteId(e.target.value)}
          className="bg-[#0a0e13] border border-[#1f2a36] text-[#c9d4e0] font-mono text-[10px] px-1 py-0.5 max-w-[180px]">
          {routes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
      </div>

      {!d ? <div className="font-mono text-[11px] text-[#6b7888]">loading…</div> : !d.available ? (
        <div data-testid="intel-unavailable" className="font-mono text-[11px] text-[#f87171] border border-[#1f2a36] bg-[#0a0e13] px-3 py-3">
          {d.note} {d.verdict ? `(${d.verdict})` : ""}
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2 mb-3 border border-[#1f2a36] bg-[#0a0e13] p-2">
            <div>
              <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">GO / WAIT / NO-GO</div>
              <div data-testid="intel-verdict" className="font-mono text-lg font-bold" style={{ color: VERDICT[v] }}>{v}</div>
              <div className="font-mono text-[9px] text-[#8b97a6]">{(d.verdict_reasons || []).join(" · ")}</div>
            </div>
            <div className="flex gap-1" data-testid="intel-util-toggle">
              {UTILS.map((u) => (
                <button key={u} onClick={() => setUtil(u)} data-testid={`intel-util-${u}`}
                  className={`px-2 py-1 border font-mono text-[10px] ${util === u ? "border-[#38bdf8] text-[#38bdf8]" : "border-[#1f2a36] text-[#6b7888]"}`}>
                  {u}%
                </button>
              ))}
            </div>
          </div>

          {/* Buy-price source transparency (E4.6.1) */}
          {d.buy_price_resolution && (
            <div className="mb-3 border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="intel-buyprice-resolution">
              <div className="flex flex-wrap items-end gap-4 mb-2">
                <div>
                  <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Buy Price</div>
                  <div data-testid="intel-buyprice-value" className="font-mono text-lg font-bold text-[#ffb224]">{px(d.buy_price_resolution.price)}</div>
                </div>
                <div>
                  <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Source</div>
                  <div data-testid="intel-buyprice-source" className="font-mono text-xs font-bold text-[#38bdf8]">{d.buy_price_resolution.source_label}</div>
                </div>
                <div>
                  <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Timestamp</div>
                  <div className="font-mono text-[10px] text-[#c9d4e0]">{d.buy_price_resolution.timestamp ? fmtTime(d.buy_price_resolution.timestamp) : "—"}</div>
                </div>
                <div>
                  <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Age</div>
                  <div className="font-mono text-[10px] text-[#c9d4e0]">{ageLabel(d.buy_price_resolution.age_s)}</div>
                </div>
              </div>
              <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">
                Resolved source chain — precedence: position → manual override → portal → fallback
              </div>
              <table className="w-full text-[9px] font-mono" data-testid="intel-source-chain">
                <thead><tr className="panel-th"><th className="text-left">Source</th><th className="text-right">Value</th><th className="text-right">Age</th><th>Avail</th><th>Won</th><th className="text-left">Why</th></tr></thead>
                <tbody>
                  {d.buy_price_resolution.chain.map((c) => (
                    <tr key={c.source} className={`border-b border-[#1f2a36]/50 ${c.won ? "bg-[#34d399]/10" : ""}`}>
                      <td className="py-0.5 text-[#c9d4e0]">{c.label}</td>
                      <td className="py-0.5 text-right">{c.value != null ? px(c.value) : "—"}</td>
                      <td className="py-0.5 text-right text-[#6b7888]">{ageLabel(c.age_s)}</td>
                      <td className="py-0.5 text-center" style={{ color: c.available ? "#34d399" : "#6b7888" }}>{c.available ? "✓" : "✗"}</td>
                      <td className="py-0.5 text-center font-bold" style={{ color: c.won ? "#34d399" : "#3d4a59" }}>{c.won ? "★" : ""}</td>
                      <td className="py-0.5 text-[#6b7888]">{c.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-3">
            <Tile label="Buy (winner)" value={px(d.buy_price)} color="#ffb224" testId="intel-buy-price" />
            <Tile label="Sell venue" value={`${(d.sell_venue || "—").toUpperCase()}`} color="#38bdf8" testId="intel-sell-venue" />
            <Tile label="Best bid" value={px(d.best_bid)} color="#34d399" />
            <Tile label="Break-even" value={px(d.break_even?.marginal_sell_price)} testId="intel-breakeven" />
            <Tile label="BE cushion" value={d.break_even?.cushion_vs_best_bid_pct != null ? `${d.break_even.cushion_vs_best_bid_pct}%` : "—"}
              color={(d.break_even?.cushion_vs_best_bid_pct ?? 0) >= 0 ? "#34d399" : "#f87171"} />
            <Tile label="Taker fee" value={`${d.taker_fee_pct}%`} />
          </div>

          <div className="mb-2 font-mono text-[10px] text-[#8b97a6]" data-testid="intel-profitable-liquidity">
            Profitable buyer depth: <b className="text-[#34d399]">{usd(d.profitable_liquidity?.profitable_quote)}</b>{" "}
            across <b className="text-[#c9d4e0]">{d.profitable_liquidity?.profitable_levels}</b>/{d.profitable_liquidity?.total_levels} levels
            (bids ≥ break-even). Gate {d.gate_open ? "OPEN" : "CLOSED"}.
          </div>

          {/* Order-book consumption simulator */}
          <table className="w-full text-[9px] font-mono mb-3" data-testid="intel-sims-table">
            <thead><tr className="panel-th"><th className="text-left">Liquidity util</th><th className="text-right">Sell qty</th><th className="text-right">VWAP</th><th className="text-right">Invest</th><th className="text-right">Net profit</th><th className="text-right">ROI</th><th>Flags</th></tr></thead>
            <tbody>
              {(d.utilization_sims || []).map((s) => (
                <tr key={s.utilization_pct} className={`border-b border-[#1f2a36]/50 ${s.utilization_pct === util ? "bg-[#38bdf8]/5" : ""}`}>
                  <td className="py-0.5">{s.utilization_pct}%</td>
                  {s.feasible ? (
                    <>
                      <td className="py-0.5 text-right">{Number(s.sell_qty_base).toLocaleString()}</td>
                      <td className="py-0.5 text-right">{px(s.weighted_sell_price)}</td>
                      <td className="py-0.5 text-right">{usd(s.investment_usd)}</td>
                      <td className="py-0.5 text-right font-bold" style={{ color: s.net_profit_usd >= 0 ? "#34d399" : "#f87171" }}>{usd(s.net_profit_usd)}</td>
                      <td className="py-0.5 text-right" style={{ color: s.roi_pct >= 0 ? "#34d399" : "#f87171" }}>{s.roi_pct}%</td>
                      <td className="py-0.5 text-center text-[8px] text-[#ffb224]">{[s.book_exhausted && "thin", s.exceeds_cert_cap && ">cap"].filter(Boolean).join(" ")}</td>
                    </>
                  ) : (
                    <td className="py-0.5 text-[#6b7888]" colSpan={6}>{s.note}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>

          {/* Maximum Safe Buy Size + ROI curve over profitable depth */}
          {d.max_safe_buy && (
            <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-2" data-testid="intel-max-safe-buy">
              <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">
                Maximum Safe Buy Size — before profitability degrades below {d.max_safe_buy.floor_pct}% floor
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-1 font-mono text-[10px] mb-2">
                <div>Max profitable liquidity: <b className="text-[#38bdf8]" data-testid="msb-liquidity">{usd(d.max_safe_buy.max_profitable_liquidity_quote)}</b></div>
                <div>Max safe buy: <b className="text-[#ffb224]" data-testid="msb-max-buy">{usd(d.max_safe_buy.max_safe_buy_usd)}</b></div>
                <div>VWAP @ max: <b className="text-[#34d399]">{px(d.max_safe_buy.weighted_sell_price_at_max)}</b></div>
                <div>ROI @ max: <b className="text-[#34d399]">{d.max_safe_buy.roi_at_max_safe_pct ?? "—"}%</b></div>
              </div>
              <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">Expected ROI at % of profitable depth</div>
              <div className="grid grid-cols-4 gap-1" data-testid="intel-roi-curve">
                {(d.max_safe_buy.roi_curve || []).map((c) => (
                  <div key={c.depth_pct} className="border border-[#1f2a36] px-2 py-1 text-center" data-testid={`roi-curve-${c.depth_pct}`}>
                    <div className="font-mono text-[9px] text-[#6b7888]">{c.depth_pct}%</div>
                    <div className="font-mono text-sm font-bold" style={{ color: c.roi_pct >= d.max_safe_buy.floor_pct ? "#34d399" : "#f87171" }}>{c.roi_pct}%</div>
                    <div className="font-mono text-[8px] text-[#5a6573]">{usd(c.investment_usd)}{c.exceeds_cert_cap ? " ⚑" : ""}</div>
                  </div>
                ))}
              </div>
              <div className="font-mono text-[8px] text-[#3d4a59] mt-1">{d.max_safe_buy.degrades_note}</div>
            </div>
          )}

          {/* Smart Exit / recommended */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-2">
            <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="intel-recommended">
              <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">Smart Exit — recommended @ {d.chosen_utilization_pct}%</div>
              {rec ? (
                <div className="grid grid-cols-2 gap-1 font-mono text-[10px]">
                  <div>Buy BDAG: <b className="text-[#c9d4e0]">{Number(rec.buy_qty_base).toLocaleString()}</b></div>
                  <div>Weighted sell: <b className="text-[#34d399]">{px(rec.weighted_sell_price)}</b></div>
                  <div>Safe capital: <b className="text-[#38bdf8]">{usd(rec.investment_usd)}</b></div>
                  <div>Net profit: <b style={{ color: rec.net_profit_usd >= 0 ? "#34d399" : "#f87171" }}>{usd(rec.net_profit_usd)}</b></div>
                  <div>ROI: <b style={{ color: rec.roi_pct >= 0 ? "#34d399" : "#f87171" }}>{rec.roi_pct}%</b></div>
                  {rec.capped_to_cert_max && <div className="text-[#ffb224]">capped to cert max</div>}
                </div>
              ) : <div className="font-mono text-[10px] text-[#f87171]">No profitable opportunity at current prices.</div>}
            </div>
            <div className="border border-[#1f2a36] bg-[#0a0e13] p-2">
              <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">Buyer Stability</div>
              <div data-testid="intel-stability" className="font-mono text-sm font-bold" style={{ color: STAB[stab?.label] || "#6b7888" }}>{stab?.label}</div>
              <div className="font-mono text-[9px] text-[#8b97a6]">best-bid CV {stab?.best_bid_cv_pct ?? "—"}% · depth CV {stab?.depth_cv_pct ?? "—"}% · {stab?.samples} samples</div>
            </div>
          </div>
          <div className="font-mono text-[8px] text-[#3d4a59]">{d.note}</div>
        </>
      )}
    </div>
  );
};
