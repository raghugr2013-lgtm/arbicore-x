import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { FreshnessBadge } from "@/components/execution/FreshnessBadge";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const V = {
  READY: { c: "#34d399", bg: "rgba(52,211,153,0.08)" },
  WAIT: { c: "#ffb224", bg: "rgba(255,178,36,0.08)" },
  BLOCKED: { c: "#f87171", bg: "rgba(248,113,113,0.08)" },
};
const ST = { READY: "#34d399", WAIT: "#ffb224", BLOCKED: "#f87171" };

export const SafetyInterlockPanel = () => {
  const [d, setD] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/interlock`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [load]);

  if (!d) {
    return (
      <div className="panel" data-testid="interlock-panel">
        <div className="panel-title">Safety Interlock</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center">evaluating interlock…</div>
      </div>
    );
  }

  const v = V[d.verdict] || V.BLOCKED;
  const il = d.interlocks || {};

  return (
    <div className="panel" data-testid="interlock-panel">
      <div className="panel-title">
        Safety Interlock
        <span className="float-right inline-flex items-center gap-2 text-[#3d4a59]">
          <FreshnessBadge stale={d.data_fresh === false} invalid={d.data_fresh == null} showAge={false} testid="interlock-freshness" />
          final authority · E5 entry guard
        </span>
      </div>

      <div className="border p-3 mb-3" style={{ borderColor: v.c + "66", background: v.bg }}>
        <div className="flex items-center justify-between">
          <div>
            <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase">Composite Readiness</div>
            <div data-testid="interlock-verdict" className="font-mono text-3xl font-bold" style={{ color: v.c }}>{d.verdict}</div>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[10px]">
            {[
              ["Opportunity Gate", il.opportunity_gate],
              ["Next-Cycle Ready", il.next_cycle_readiness],
              ["Venue Qualified", il.venue_qualification],
              ["Deposit / Withdraw", `${il.deposit_gate} / ${il.withdrawal_gate}`],
            ].map(([k, val]) => (
              <div key={k} className="flex items-center gap-1.5">
                <span className="text-[#6b7888]">{k}:</span>
                <span className="text-[#c9d4e0] font-bold uppercase">{val ?? "—"}</span>
              </div>
            ))}
          </div>
        </div>
        {(d.blocked_reasons?.length > 0 || d.wait_reasons?.length > 0) && (
          <div className="mt-2 pt-2 border-t border-[#1f2a36]/50 font-mono text-[10px]" data-testid="interlock-reasons">
            {d.blocked_reasons?.map((r, i) => <div key={`b${i}`} style={{ color: "#f87171" }}>■ BLOCKED: {r}</div>)}
            {d.wait_reasons?.map((r, i) => <div key={`w${i}`} style={{ color: "#ffb224" }}>▲ WAIT: {r}</div>)}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1" data-testid="interlock-checks">
        {(d.checks || []).map((c) => (
          <div key={c.key} className="flex items-center gap-2 text-[10px] font-mono py-0.5" data-testid={`interlock-check-${c.key}`}>
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: ST[c.status] }} />
            <span className="flex-1 text-[#8b97a6]">{c.label}</span>
            <span className="text-[8px] text-[#5a6573]">{c.detail}</span>
            <span className="text-[8px] font-bold w-14 text-right" style={{ color: ST[c.status] }}>{c.status}</span>
          </div>
        ))}
      </div>

      <div className="mt-2 font-mono text-[8px] text-[#3d4a59]">
        Auto-downgrades on: {(d.downgrade_triggers || []).join(" · ")}. READY authorizes nothing today — E5 stays blocked.
      </div>
    </div>
  );
};
