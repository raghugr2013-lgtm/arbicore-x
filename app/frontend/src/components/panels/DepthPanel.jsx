import { fmtPrice, fmtQty } from "@/lib/fmt";

export const DepthPanel = ({ orderbook }) => {
  const bids = orderbook?.bids || [];
  const asks = orderbook?.asks || [];
  const maxCum = (rows) => {
    let c = 0;
    return rows.map(([p, q]) => (c += p * q));
  };
  const bidCum = maxCum(bids);
  const askCum = maxCum(asks);
  const maxTotal = Math.max(bidCum[bidCum.length - 1] || 0, askCum[askCum.length - 1] || 0, 1);

  const Side = ({ rows, cum, color, align, label, prefix }) => (
    <div className="flex-1">
      <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">{label}</div>
      {rows.slice(0, 12).map(([p, q], i) => (
        <div key={i} data-testid={`${prefix}-row-${i}`} className="relative flex justify-between text-[11px] font-mono py-px px-1">
          <div
            className="absolute inset-y-0"
            style={{
              [align]: 0,
              width: `${Math.min((cum[i] / maxTotal) * 100, 100)}%`,
              background: color, opacity: 0.13,
            }}
          />
          <span style={{ color }}>{fmtPrice(p)}</span>
          <span className="text-[#c9d4e0]">{fmtQty(q)}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="panel" data-testid="depth-panel">
      <div className="panel-title">
        Market Depth — {orderbook?.exchange?.toUpperCase() || "—"}
        {orderbook?.source === "sim" && <span className="ml-2 text-[9px] text-[#38bdf8]">SIM</span>}
        <span className="float-right text-[9px] text-[#6b7888]">
          {orderbook?.age_s != null ? `${Math.round(orderbook.age_s)}s ago` : ""}
        </span>
      </div>
      {bids.length === 0 ? (
        <div className="text-xs font-mono text-[#6b7888] py-6 text-center">no order book data</div>
      ) : (
        <div className="flex gap-3">
          <Side rows={bids} cum={bidCum} color="#34d399" align="right" label="Bids" prefix="bid" />
          <Side rows={asks} cum={askCum} color="#f87171" align="left" label="Asks" prefix="ask" />
        </div>
      )}
    </div>
  );
};
