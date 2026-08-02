import { useState } from "react";
import { Link } from "react-router-dom";
import { ONBOARDING } from "@/lib/exchangeOnboarding";
import { fmtQty, fmtUsd } from "@/lib/fmt";

const Onboarding = ({ ex }) => {
  const ob = ONBOARDING[ex];
  if (!ob) return null;
  return (
    <div className="mt-2 border border-[#1f2a36] bg-[#0a0f14] p-2.5 font-mono text-[10px]" data-testid={`onboarding-${ex}`}>
      <div className="text-[#ffb224] font-bold tracking-wider mb-1">HOW TO CREATE A READ-ONLY {ob.name.toUpperCase()} KEY</div>
      <ol className="list-decimal list-inside space-y-0.5 text-[#6b7888]">
        {ob.steps.map((s, i) => <li key={i}>{s}</li>)}
      </ol>
      <div className="mt-1.5 text-[#3d4a59]">
        Console: <a href={ob.url} target="_blank" rel="noreferrer" className="text-[#38bdf8] underline">{ob.url}</a>
        {" "}· then store it in <Link to="/settings" className="text-[#38bdf8] underline">Settings → Vault</Link>
      </div>
      <div className="mt-1 text-[#f87171]">No trading permission. No withdrawal permission. Read only.</div>
    </div>
  );
};

const ExchangeBlock = ({ ex }) => {
  const [showOb, setShowOb] = useState(false);
  const status = ex.status || "no_key";
  return (
    <div className="border border-[#1f2a36] p-2.5" data-testid={`balances-block-${ex.exchange}`}>
      <div className="flex items-center gap-2 font-mono text-[11px]">
        <span className="font-bold uppercase">{ex.exchange}</span>
        {status === "ok" && <span className="text-[#34d399] text-[9px] font-bold">● LIVE</span>}
        {status === "no_key" && (
          <span className="text-[#6b7888] text-[9px] font-bold border border-[#3d4a59] px-1.5 py-0.5"
                data-testid={`balances-nokey-${ex.exchange}`}>NO API KEY CONFIGURED</span>
        )}
        {status === "error" && <span className="text-[#f87171] text-[9px] font-bold">● ERROR</span>}
        {status === "rate_limited" && <span className="text-[#fbbf24] text-[9px] font-bold">● RATE LIMITED</span>}
        <div className="flex-1" />
        {ex.total_usd != null && <span className="text-[#34d399] font-bold">{fmtUsd(ex.total_usd)}</span>}
        {status === "no_key" && (
          <button onClick={() => setShowOb(!showOb)} data-testid={`balances-onboarding-btn-${ex.exchange}`}
                  className="text-[9px] font-bold px-2 py-0.5 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10">
            {showOb ? "HIDE" : "SETUP GUIDE"}
          </button>
        )}
      </div>
      {status === "error" && <div className="font-mono text-[10px] text-[#f87171] mt-1 truncate" title={ex.error}>{ex.error}</div>}
      {status === "rate_limited" && (
        <div className="font-mono text-[10px] text-[#fbbf24] mt-1">
          backing off{ex.backoff_remaining_s != null ? ` — retrying in ${ex.backoff_remaining_s}s` : ""} (rate-limit aware)
        </div>
      )}
      {showOb && <Onboarding ex={ex.exchange} />}
      {status === "ok" && (ex.balances || []).length === 0 && (
        <div className="font-mono text-[10px] text-[#6b7888] mt-1">no non-zero balances</div>
      )}
      {(ex.balances || []).length > 0 && (
        <table className="w-full text-[10px] font-mono mt-1.5">
          <thead>
            <tr className="panel-th">
              <th className="text-left">Asset</th><th className="text-right">Free</th>
              <th className="text-right">Locked</th><th className="text-right">Total</th>
              <th className="text-right">USD</th>
            </tr>
          </thead>
          <tbody>
            {ex.balances.map((b) => (
              <tr key={b.asset} className="border-b border-[#1f2a36]/40" data-testid={`balance-row-${ex.exchange}-${b.asset}`}>
                <td className="py-1 font-bold">{b.asset}</td>
                <td className="text-right">{fmtQty(b.free)}</td>
                <td className="text-right text-[#6b7888]">{fmtQty(b.locked)}</td>
                <td className="text-right">{fmtQty(b.total)}</td>
                <td className="text-right text-[#34d399]">{b.usd_value != null ? fmtUsd(b.usd_value) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export const BalancesPanel = ({ data }) => {
  const exchanges = Object.values(data?.exchanges || {});
  return (
    <div className="panel" data-testid="balances-panel">
      <div className="panel-title">Exchange Balances (read-only)</div>
      <div className="space-y-2">
        {exchanges.length === 0 && <div className="font-mono text-[11px] text-[#6b7888]">starting balance service…</div>}
        {exchanges.map((ex) => <ExchangeBlock key={ex.exchange} ex={ex} />)}
      </div>
    </div>
  );
};
