import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtPct, fmtQty, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CLASS_STYLE = {
  A: { color: "#34d399", label: "FULLY AUTOMATED" },
  B: { color: "#fbbf24", label: "SEMI-AUTOMATED" },
  C: { color: "#f87171", label: "MANUAL OPPORTUNITY" },
};
const ROLE_STYLE = {
  primary: "#34d399", backup: "#38bdf8", watch: "#ffb224", disabled: "#6b7888",
};

const CoverageBar = ({ pct }) => (
  <div className="h-1.5 w-full bg-[#1f2a36] mt-1">
    <div className="h-full" style={{ width: `${pct}%`, background: pct >= 100 ? "#34d399" : pct >= 80 ? "#fbbf24" : "#f87171" }} />
  </div>
);

export const RouteClassificationPanel = ({ routeId }) => {
  const [cls, setCls] = useState(null);
  const [manual, setManual] = useState(null);

  const load = useCallback(() => {
    if (!routeId) return;
    axios.get(`${API}/execution/classification/${routeId}`).then((r) => setCls(r.data)).catch(() => {});
    axios.get(`${API}/execution/manual-opportunities/${routeId}`).then((r) => setManual(r.data)).catch(() => {});
  }, [routeId]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="panel" data-testid="route-classification-panel">
      <div className="panel-title">
        Route Classification & Automation Coverage
        <span className="float-right text-[#3d4a59]">A·B·C · read-only</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="panel-th">
              <th className="text-left">Venue</th>
              <th className="text-left">Role</th>
              <th className="text-left">Class</th>
              <th className="text-left w-40">Automation coverage</th>
              <th className="text-right">Manual steps</th>
              <th className="text-right">Deposit gate</th>
            </tr>
          </thead>
          <tbody>
            {(cls?.venues || []).map((v) => {
              const cs = CLASS_STYLE[v.classification] || CLASS_STYLE.C;
              return (
                <tr key={v.exchange} className="border-b border-[#1f2a36]/50" data-testid={`classification-row-${v.exchange}`}>
                  <td className="py-2 font-bold">{v.exchange.toUpperCase()}</td>
                  <td className="py-2" style={{ color: ROLE_STYLE[v.role] || "#6b7888" }}>{(v.role || "").toUpperCase()}</td>
                  <td className="py-2">
                    <span data-testid={`classification-class-${v.exchange}`} className="font-bold" style={{ color: cs.color }}>
                      {v.classification} · {cs.label}
                    </span>
                  </td>
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      <span data-testid={`classification-coverage-${v.exchange}`} className="font-bold w-9" style={{ color: cs.color }}>
                        {v.automation_coverage_pct}%
                      </span>
                      <div className="flex-1"><CoverageBar pct={v.automation_coverage_pct} /></div>
                    </div>
                  </td>
                  <td className="py-2 text-right">{v.manual_steps}</td>
                  <td className="py-2 text-right">
                    {v.deposit_gate_open === true ? <span className="text-[#34d399]">open</span>
                      : v.deposit_gate_open === false ? <span className="text-[#f87171]">CLOSED</span>
                      : <span className="text-[#6b7888]">unknown</span>}
                  </td>
                </tr>
              );
            })}
            {cls && cls.venues?.length === 0 && (
              <tr><td colSpan={6} className="py-2 text-[#6b7888]">no venues</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4">
        <div className="text-[10px] uppercase tracking-widest text-[#6b7888] mb-2 flex items-center justify-between">
          <span>Manual Opportunity Engine</span>
          <span className="text-[#3d4a59]">net ≥ {manual?.min_net_spread_pct ?? "—"}% · {manual?.count ?? 0} live</span>
        </div>
        {manual && manual.opportunities.length === 0 && (
          <div className="font-mono text-[11px] text-[#6b7888]" data-testid="manual-opportunities-empty">
            No profitable manual opportunities right now.
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {(manual?.opportunities || []).map((o, i) => {
            const cs = CLASS_STYLE[o.classification] || CLASS_STYLE.C;
            return (
              <div key={i} className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid={`manual-opp-${o.sell_venue.toLowerCase()}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs font-bold">
                    {o.buy_venue} → <span className="text-[#38bdf8]">{o.sell_venue}</span>
                  </span>
                  <span className="font-mono text-[9px] font-bold" style={{ color: cs.color }}>
                    {o.classification} · {o.automation_coverage_pct}%
                  </span>
                </div>
                <div className="grid grid-cols-4 gap-1 font-mono text-[10px] mb-2">
                  <div><span className="text-[#6b7888]">Qty </span><span className="text-[#c9d4e0]">{fmtQty(o.qty_base)}</span></div>
                  <div><span className="text-[#6b7888]">Net </span><span className={pctCls(o.net_spread_pct)}>{fmtPct(o.net_spread_pct)}</span></div>
                  <div><span className="text-[#6b7888]">Profit </span><span className="text-[#34d399]">{fmtUsd(o.est_profit_quote)}</span></div>
                  <div><span className="text-[#6b7888]">Liq </span><span className="text-[#c9d4e0]">{fmtUsd(o.liquidity_quote)}</span></div>
                </div>
                <div className="font-mono text-[9px] text-[#6b7888] mb-1">
                  Window: {o.time_window} · gate {o.deposit_gate_open === true ? "open" : o.deposit_gate_open === false ? "CLOSED" : "unknown"}
                </div>
                <ol className="list-decimal list-inside font-mono text-[9px] text-[#8b97a6] space-y-0.5">
                  {o.manual_actions.map((m, j) => <li key={j}>{m.action}</li>)}
                </ol>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

const pctCls = (v) => (v == null ? "text-[#6b7888]" : v > 0 ? "text-[#34d399]" : "text-[#f87171]");
