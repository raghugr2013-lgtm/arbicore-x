import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { VerdictBadge } from "@/components/VerdictBadge";
import { fmtPct, fmtPrice, fmtQty, fmtUsd, pctClass } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Cell = ({ label, value, color, testId, sub }) => (
  <div className="bg-[#0a0e13] border border-[#1f2a36] px-3 py-2">
    <div className="text-[9px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div data-testid={testId} className="font-mono text-base font-bold" style={color ? { color } : {}}>{value}</div>
    {sub && <div className="font-mono text-[9px] text-[#6b7888] mt-0.5">{sub}</div>}
  </div>
);

export const OpportunityWidget = ({ routeId }) => {
  const [d, setD] = useState(null);

  const load = useCallback(() => {
    if (!routeId) return;
    axios.get(`${API}/execution/opportunity/${routeId}`).then((r) => setD(r.data)).catch(() => {});
  }, [routeId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 7000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="panel" data-testid="opportunity-widget">
      <div className="panel-title">
        Portal vs Exchange Opportunity
        <span className="float-right flex items-center gap-2 text-[#3d4a59]">read-only · E2</span>
      </div>
      {!d && <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>}
      {d && d.available === false && (
        <div className="font-mono text-[11px] text-[#6b7888]" data-testid="opportunity-widget-empty">
          No live evaluation yet for this route.
        </div>
      )}
      {d && d.available && (
        <>
          <div className="flex items-center gap-3 mb-3">
            <VerdictBadge verdict={d.verdict} size="lg" />
            <span data-testid="opportunity-verdict-label" className="font-mono text-[10px] text-[#6b7888]">
              {d.verdict === "GO" ? "executable now" : d.verdict === "WAIT" ? "below thresholds" : "blocked / not viable"}
            </span>
            <div className="flex-1" />
            <span className="font-mono text-[9px] text-[#6b7888]">
              best venue: <span className="text-[#38bdf8] font-bold">{(d.best_exchange || "—").toUpperCase()}</span>
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Cell label="Portal price (buy)" value={fmtPrice(d.portal_price)} color="#34d399"
                  testId="opp-portal-price" sub={d.portal_stale ? "STALE" : "live"} />
            <Cell label={`Best exch price`} value={fmtPrice(d.best_exchange_price)} color="#38bdf8"
                  testId="opp-best-exchange-price" sub={(d.best_exchange || "—").toUpperCase()} />
            <Cell label="Gross spread" value={fmtPct(d.gross_spread_pct)} color="#ffb224" testId="opp-gross-spread" />
            <Cell label="Net spread" value={fmtPct(d.net_spread_pct)}
                  color={d.net_spread_pct > 0 ? "#34d399" : "#f87171"} testId="opp-net-spread" />
            <Cell label="Liquidity (≤2%)" value={fmtUsd(d.liquidity_quote_2pct)} testId="opp-liquidity"
                  sub={`exit: ${(d.exit_venue || "—").toUpperCase()}`} />
            <Cell label="Max safe size" value={fmtQty(d.max_safe_size_base)} color="#c9d4e0"
                  testId="opp-max-safe-size" sub={fmtUsd(d.max_safe_size_quote)} />
            <Cell label="Recommended size" value={fmtQty(d.recommended_size_base)} color="#ffb224" testId="opp-recommended-size" />
            <Cell label="Expected profit" value={fmtUsd(d.expected_profit_quote)}
                  color={d.expected_profit_quote > 0 ? "#34d399" : "#6b7888"} testId="opp-expected-profit" />
          </div>
          <div className="font-mono text-[9px] text-[#3d4a59] mt-2">
            Buy price used: {fmtPrice(d.buy_price_used)} · source {String(d.price_source || "—").toUpperCase()} · exit best bid {fmtPrice(d.exit_best_bid)} ({(d.exit_venue || "—").toUpperCase()})
          </div>
        </>
      )}
    </div>
  );
};
