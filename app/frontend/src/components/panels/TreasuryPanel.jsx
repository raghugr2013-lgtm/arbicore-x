import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtPrice, fmtQty, fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Stat = ({ label, value, cls }) => (
  <div className="border border-[#1f2a36] p-2">
    <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div className={`font-mono text-sm font-bold ${cls || "text-[#c9d4e0]"}`}>{value}</div>
  </div>
);

export const TreasuryPanel = ({ routeId }) => {
  const [data, setData] = useState(null);

  const fetchTreasury = useCallback(() => {
    axios.get(`${API}/treasury/${routeId}`).then((res) => setData(res.data)).catch(() => {});
  }, [routeId]);

  useEffect(() => {
    fetchTreasury();
    const t = setInterval(fetchTreasury, 30000);
    return () => clearInterval(t);
  }, [fetchTreasury]);

  const s = data?.summary || {};
  const c = data?.conversion || {};
  const pnlCls = (v) => (v > 0 ? "text-[#34d399]" : v < 0 ? "text-[#f87171]" : "text-[#6b7888]");

  return (
    <div className="panel" data-testid="treasury-panel">
      <div className="panel-title">
        Treasury — capital lifecycle
        <span className="float-right text-[9px] text-[#6b7888]">
          {data ? `${data.funding?.coin}@${data.funding?.network} → asset → ${data.settlement?.coin}@${data.settlement?.network}` : ""}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 mb-2">
        <Stat label="Cost basis" value={`$${fmtQty(s.cost_quote)}`} />
        <Stat label="Proceeds" value={`$${fmtQty(s.proceeds_quote)}`} />
        <Stat label="Realized PnL" value={s.realized_pnl_quote != null ? `$${s.realized_pnl_quote}` : "—"} cls={pnlCls(s.realized_pnl_quote)} />
        <Stat label="Open qty" value={fmtQty(s.open_qty)} />
        <Stat label="Open value" value={s.open_value_quote != null ? `$${fmtQty(s.open_value_quote)}` : "—"} />
        <Stat label="Unrealized" value={s.unrealized_pnl_quote != null ? `$${s.unrealized_pnl_quote}` : "—"} cls={pnlCls(s.unrealized_pnl_quote)} />
      </div>
      <div className="border border-[#38bdf8]/25 bg-[#38bdf8]/5 px-2 py-1.5 mb-2 font-mono text-[10px]" data-testid="conversion-box">
        <span className="text-[#38bdf8] font-bold">REPLENISHMENT ROUTE</span>{" "}
        <span className="text-[#6b7888]">
          USDT→{data?.settlement?.coin} @ {c.rate ? fmtPrice(c.rate) : "—"} · fee {c.taker_fee_pct}% + ${c.est_fixed_fee_quote}
        </span>
        {c.est_settlement_amount != null && (
          <span className="text-[#c9d4e0]"> → est {c.est_settlement_amount} {data?.settlement?.coin} from ${fmtQty(c.unsettled_proceeds_quote)} unsettled</span>
        )}
      </div>
      <div className="max-h-32 overflow-y-auto" data-testid="treasury-ledger">
        {(data?.ledger || []).length === 0 ? (
          <div className="text-[10px] font-mono text-[#6b7888] py-2">Ledger empty — entries auto-record on buy / sell / settle.</div>
        ) : (
          data.ledger.slice(0, 8).map((l) => (
            <div key={l.id} className="flex justify-between text-[10px] font-mono py-1 border-b border-[#1f2a36]/40">
              <span className="text-[#6b7888]">{fmtTime(l.ts)}</span>
              <span className={`uppercase font-bold ${l.leg === "sell" ? "text-[#34d399]" : l.leg === "purchase" ? "text-[#ffb224]" : "text-[#38bdf8]"}`}>{l.leg}</span>
              <span>{fmtQty(l.qty)}</span>
              <span className="text-[#c9d4e0]">{l.quote_value != null ? `$${fmtQty(l.quote_value)}` : "—"}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
