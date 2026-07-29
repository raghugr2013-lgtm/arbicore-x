import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtUsd, fmtTime } from "@/lib/fmt";
import { FreshnessBadge } from "@/components/execution/FreshnessBadge";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const GV = {
  GO: { c: "#34d399", bg: "rgba(52,211,153,0.08)" },
  WAIT: { c: "#ffb224", bg: "rgba(255,178,36,0.08)" },
  NO_GO: { c: "#f87171", bg: "rgba(248,113,113,0.08)" },
};

export const OpportunityGatePanel = () => {
  const [gate, setGate] = useState(null);
  const [hist, setHist] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/opportunity/gate`).then((r) => setGate(r.data)).catch(() => {});
    axios.get(`${API}/execution/opportunity/windows`).then((r) => setHist(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [load]);

  if (!gate) {
    return (
      <div className="panel" data-testid="opportunity-gate-panel">
        <div className="panel-title">Live Opportunity Gate</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center">evaluating opportunity…</div>
      </div>
    );
  }

  const g = GV[gate.gate_verdict] || GV.NO_GO;
  const fr = gate.freshness || {};
  const summary = hist?.summary || {};
  const windows = hist?.windows || [];

  return (
    <div className="panel" data-testid="opportunity-gate-panel">
      <div className="panel-title">
        Live Opportunity Gate &amp; GO-Window Tracker
        <span className="float-right inline-flex items-center gap-2 text-[#3d4a59]">
          <FreshnessBadge invalid={!gate.available} stale={fr.all_fresh === false} showAge={false} testid="gate-freshness" />
          read-only · {gate.venue?.toUpperCase()}
        </span>
      </div>

      {/* verdict + headline metrics */}
      <div className="border p-3 mb-3" style={{ borderColor: g.c + "66", background: g.bg }}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase">Gate Verdict</div>
            <div data-testid="gate-verdict" className="font-mono text-3xl font-bold" style={{ color: g.c }}>{gate.gate_verdict}</div>
          </div>
          {gate.available && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 font-mono text-[10px]">
              <div><span className="text-[#6b7888]">Net ROI:</span> <b className="text-[#34d399]">{gate.roi_pct}%</b></div>
              <div><span className="text-[#6b7888]">Safe buy:</span> <b className="text-[#ffb224]">{fmtUsd(gate.max_safe_buy_usd)}</b></div>
              <div><span className="text-[#6b7888]">Prof. depth:</span> <b className="text-[#c9d4e0]">{fmtUsd(gate.profitable_liquidity_quote)}</b></div>
              <div><span className="text-[#6b7888]">Stability:</span> <b className="text-[#c9d4e0]">{gate.buyer_stability}</b></div>
            </div>
          )}
        </div>
      </div>

      {/* GO conditions + freshness */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="gate-conditions">
          <div className="font-mono text-[9px] text-[#6b7888] tracking-wider mb-1">GO CONDITIONS (all required)</div>
          {(gate.conditions || []).map((c) => (
            <div key={c.key} className="flex items-center gap-2 text-[10px] font-mono py-0.5" data-testid={`gate-cond-${c.key}`}>
              <span style={{ color: c.passed ? "#34d399" : "#f87171" }}>{c.passed ? "✓" : "✗"}</span>
              <span className="flex-1 text-[#8b97a6]">{c.label}</span>
              <span className="text-[8px] text-[#5a6573]">{c.detail}</span>
            </div>
          ))}
        </div>
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="gate-freshness">
          <div className="font-mono text-[9px] text-[#6b7888] tracking-wider mb-1">DATA FRESHNESS</div>
          {["buy_price", "order_book", "gate_status", "qualification"].map((k) => {
            const f = fr[k] || {};
            return (
              <div key={k} className="flex items-center gap-2 text-[10px] font-mono py-0.5" data-testid={`gate-fresh-${k}`}>
                <span style={{ color: f.fresh ? "#34d399" : "#f87171" }}>{f.fresh ? "●" : "○"}</span>
                <span className="flex-1 text-[#8b97a6]">{k.replace("_", " ")}</span>
                <span className="text-[8px] text-[#5a6573]">{f.age_s != null ? `${f.age_s}s` : "static"}{f.threshold_s ? ` / ${f.threshold_s}s` : ""}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* GO window history */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="gate-windows">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[9px] text-[#6b7888] tracking-wider">GO-WINDOW HISTORY</span>
          <span className="font-mono text-[9px] text-[#6b7888]">
            {summary.total_windows ?? 0} total · {summary.open ?? 0} open · avg dur {summary.avg_duration_s ?? "—"}s · best peak ROI {summary.best_peak_roi_pct ?? "—"}%
          </span>
        </div>
        {windows.length === 0 ? (
          <div className="font-mono text-[10px] text-[#3d4a59] py-2 text-center">No GO windows recorded yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[9px] font-mono">
              <thead>
                <tr className="panel-th text-[#6b7888]">
                  <th className="text-left">Venue</th><th className="text-left">Status</th>
                  <th className="text-left">Opened</th><th className="text-right">Dur(s)</th>
                  <th className="text-right">ROI open</th><th className="text-right">Peak</th>
                  <th className="text-right">Avg</th><th className="text-right">Safe buy</th>
                  <th className="text-left">Closed reason</th>
                </tr>
              </thead>
              <tbody>
                {windows.slice(0, 12).map((w) => (
                  <tr key={w.id} className="border-b border-[#1f2a36]/50" data-testid={`window-${w.id.slice(0, 8)}`}>
                    <td className="py-1 font-bold text-[#c9d4e0]">{(w.venue || "").toUpperCase()}</td>
                    <td className="py-1"><span style={{ color: w.status === "open" ? "#34d399" : "#6b7888" }}>{w.status.toUpperCase()}</span></td>
                    <td className="py-1 text-[#6b7888]">{fmtTime(w.opened_at)}</td>
                    <td className="py-1 text-right text-[#8b97a6]">{w.duration_s ?? "—"}</td>
                    <td className="py-1 text-right text-[#34d399]">{w.roi_open}%</td>
                    <td className="py-1 text-right text-[#34d399]">{w.roi_peak}%</td>
                    <td className="py-1 text-right text-[#34d399]">{w.roi_avg}%</td>
                    <td className="py-1 text-right text-[#ffb224]">{fmtUsd(w.safe_buy_size_usd)}</td>
                    <td className="py-1 text-[#5a6573] truncate max-w-[160px]">{w.reason_closed || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        GO is allowed only when ROI &gt; floor, depth sufficient, liquidity stable, venue qualified, and all data fresh.
        Telegram alerts (GO opened/closed, gate/qualification changes) are DORMANT until a bot token is configured. No fund movement.
      </div>
    </div>
  );
};
