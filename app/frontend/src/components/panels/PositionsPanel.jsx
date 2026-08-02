import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtPrice, fmtQty } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const FLOW = ["BOUGHT", "IN_WALLET", "TRANSFERRING", "ON_EXCHANGE", "SOLD", "SETTLED"];

export const PositionsPanel = ({ routeId, positions, onChanged }) => {
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("");
  const [sellPrice, setSellPrice] = useState({});

  const addPosition = async () => {
    if (!price || !qty) return toast.error("Enter buy price and quantity");
    try {
      await axios.post(`${API}/positions`, { route_id: routeId, buy_price: parseFloat(price), qty: parseFloat(qty) });
      toast.success("Manual buy recorded — engines now evaluate this position");
      setPrice(""); setQty("");
      onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to record buy");
    }
  };

  const advance = async (pos) => {
    const next = FLOW[FLOW.indexOf(pos.status) + 1];
    if (!next) return;
    const body = { status: next };
    if (next === "SOLD") {
      const sp = parseFloat(sellPrice[pos.id]);
      if (!sp) return toast.error("Enter sell price before marking SOLD");
      body.sell = { price: sp, qty: pos.qty, proceeds_quote: sp * pos.qty, sold_at: new Date().toISOString() };
    }
    try {
      await axios.patch(`${API}/positions/${pos.id}`, body);
      if (next === "ON_EXCHANGE") {
        await axios.post(`${API}/transfers`, {
          route_id: routeId, position_id: pos.id, qty: pos.qty,
          sent_at: pos.updated_at, credited_at: new Date().toISOString(), status: "complete",
          notes: "auto-logged from position lifecycle",
        });
        toast.success("Deposit credited — transfer duration logged to history");
      } else {
        toast.success(`Position → ${next}`);
      }
      onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Update failed");
    }
  };

  return (
    <div className="panel" data-testid="positions-panel">
      <div className="panel-title">Manual Buy Input · Position Lifecycle</div>
      <div className="flex gap-2 mb-3">
        <input data-testid="manual-buy-price-input" value={price} onChange={(e) => setPrice(e.target.value)}
               placeholder="buy price (USDT)" className="term-input flex-1" />
        <input data-testid="manual-buy-qty-input" value={qty} onChange={(e) => setQty(e.target.value)}
               placeholder="quantity (BDAG)" className="term-input flex-1" />
        <button data-testid="manual-buy-submit" onClick={addPosition} className="term-btn-primary">
          RECORD BUY
        </button>
      </div>
      {(positions || []).length === 0 ? (
        <div className="text-xs font-mono text-[#6b7888] py-3">
          No positions yet. Record your manual BDAG purchase to drive position-based evaluation
          (otherwise the route's hypothetical buy price is used).
        </div>
      ) : (
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="panel-th">
              <th className="text-left">Status</th>
              <th className="text-right">Buy</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Sell</th>
              <th className="text-right">PnL</th>
              <th className="text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.id} data-testid={`position-row-${p.id}`} className="border-b border-[#1f2a36]/60">
                <td className="py-1.5">
                  <span className={`px-1.5 py-0.5 text-[9px] font-bold border ${
                    p.status === "SETTLED" ? "border-[#34d399] text-[#34d399]" : "border-[#ffb224] text-[#ffb224]"
                  }`}>{p.status}</span>
                </td>
                <td className="text-right">{fmtPrice(p.buy_price)}</td>
                <td className="text-right">{fmtQty(p.qty)}</td>
                <td className="text-right">
                  {p.status === "ON_EXCHANGE" ? (
                    <input data-testid={`sell-price-input-${p.id}`} value={sellPrice[p.id] || ""}
                           onChange={(e) => setSellPrice({ ...sellPrice, [p.id]: e.target.value })}
                           placeholder="sell px" className="term-input w-20 text-right" />
                  ) : p.sell?.price ? fmtPrice(p.sell.price) : "—"}
                </td>
                <td className={`text-right ${p.realized_pnl_quote > 0 ? "text-[#34d399]" : p.realized_pnl_quote < 0 ? "text-[#f87171]" : "text-[#6b7888]"}`}>
                  {p.realized_pnl_quote != null ? `$${p.realized_pnl_quote.toFixed(2)}` : "—"}
                </td>
                <td className="text-right">
                  {p.status !== "SETTLED" && (
                    <button data-testid={`advance-position-${p.id}`} onClick={() => advance(p)} className="term-btn-secondary">
                      → {FLOW[FLOW.indexOf(p.status) + 1]}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};
