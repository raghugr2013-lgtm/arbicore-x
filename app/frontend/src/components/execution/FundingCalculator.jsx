import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtPrice, fmtQty } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const FundingCalculator = () => {
  const [size, setSize] = useState(25);
  const [data, setData] = useState(null);

  const load = useCallback((s) => {
    const v = parseFloat(s);
    if (!v || v <= 0) return;
    axios.get(`${API}/execution/funding`, { params: { size_usd: v } }).then((r) => setData(r.data)).catch(() => {});
  }, []);

  useEffect(() => { load(25); }, [load]);

  return (
    <div className="panel" data-testid="funding-calculator">
      <div className="panel-title">
        Funding Asset Flexibility
        <span className="float-right text-[#3d4a59]">USDT · BNB · ETH</span>
      </div>
      <div className="flex items-end gap-2 mb-3">
        <label className="block flex-1">
          <span className="text-[9px] uppercase tracking-widest text-[#6b7888]">Cycle size (USD)</span>
          <input data-testid="funding-size-input" value={size} onChange={(e) => setSize(e.target.value)}
                 className="term-input w-full" />
        </label>
        <button data-testid="funding-calc-btn" onClick={() => load(size)} className="term-btn-secondary">CALCULATE</button>
      </div>
      {data && (
        <>
          <div className="flex items-center justify-between mb-2 font-mono text-[11px]">
            <span className="text-[#6b7888]">BDAG obtainable (gross)</span>
            <span data-testid="funding-bdag-qty" className="text-[#34d399] font-bold">
              {fmtQty(data.bdag_qty_gross)} BDAG @ {fmtPrice(data.bdag_price)}
            </span>
          </div>
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="panel-th">
                <th className="text-left">Asset</th>
                <th className="text-right">USD price</th>
                <th className="text-right">Amount required</th>
              </tr>
            </thead>
            <tbody>
              {data.funding_assets.map((a) => (
                <tr key={a.asset} className="border-b border-[#1f2a36]/50" data-testid={`funding-asset-${a.asset}`}>
                  <td className="py-1.5 font-bold">{a.asset}</td>
                  <td className="py-1.5 text-right">{a.usd_price != null ? `$${a.usd_price.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : "—"}</td>
                  <td className="py-1.5 text-right text-[#ffb224] font-bold">
                    {a.amount_required != null ? `${a.amount_required} ${a.asset}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="font-mono text-[9px] text-[#3d4a59] mt-2">
            {data.portal_stale ? "Portal price STALE — values unavailable." : "Gross conversion at live portal price; excludes fees. Read-only — no swaps."}
          </div>
        </>
      )}
    </div>
  );
};
