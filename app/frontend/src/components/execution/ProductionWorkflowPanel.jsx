import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const READY_STYLE = {
  READY: "#34d399", WAIT: "#ffb224", COOLDOWN: "#38bdf8",
  BLOCKED: "#f87171", NO_HISTORY: "#6b7888",
};

const AutoBadge = ({ r }) => {
  const ok = r?.status === "AUTOMATABLE";
  return (
    <span className="px-1.5 py-0.5 border text-[8px] font-bold whitespace-nowrap"
          style={{ borderColor: ok ? "#34d399" : "#ffb224", color: ok ? "#34d399" : "#ffb224" }}
          title={r?.blocking_reason || ""}>
      {ok ? "AUTOMATABLE" : "MANUAL"}
    </span>
  );
};

const Field = ({ label, children }) => (
  <div>
    <div className="text-[8px] text-[#6b7888] tracking-wider uppercase">{label}</div>
    <div className="text-[9px] text-[#8b97a6]">{children}</div>
  </div>
);

export const ProductionWorkflowPanel = () => {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/workflow/blueprint`).then((r) => setData(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  if (!data) {
    return (
      <div className="panel" data-testid="workflow-panel">
        <div className="panel-title">Production Workflow Blueprint</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center">loading blueprint…</div>
      </div>
    );
  }

  const rd = data.next_cycle_readiness || {};
  const rdColor = READY_STYLE[rd.verdict] || "#6b7888";

  return (
    <div className="panel" data-testid="workflow-panel">
      <div className="panel-title">
        Production Workflow Blueprint
        <span className="float-right text-[#3d4a59]">non-executing · target {data.target_venue?.toUpperCase()}</span>
      </div>

      {/* automation coverage + readiness */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="workflow-coverage">
          <div className="flex items-center justify-between mb-1">
            <span className="font-mono text-[10px] text-[#6b7888] tracking-wider">AUTOMATION READINESS (E5 PRECONDITION)</span>
            <span className="font-mono text-sm font-bold text-[#38bdf8]">{data.automation_coverage_pct}%</span>
          </div>
          <div className="h-2 bg-[#1f2a36] rounded overflow-hidden">
            <div className="h-full bg-[#38bdf8] transition-all" style={{ width: `${data.automation_coverage_pct}%` }} />
          </div>
          <div className="font-mono text-[9px] text-[#6b7888] mt-1">
            {data.automatable_now}/{data.total_stages} stages automatable now · wallet_enabled={String(data.execution_gates?.wallet_enabled)} · whitelist={String(data.execution_gates?.withdrawal_whitelist_configured)}
          </div>
        </div>

        <div className="border p-3" data-testid="workflow-readiness"
             style={{ borderColor: rdColor + "66", background: rdColor + "0d" }}>
          <div className="flex items-center justify-between mb-1">
            <span className="font-mono text-[10px] text-[#6b7888] tracking-wider">NEXT-CYCLE READINESS</span>
            <span data-testid="workflow-readiness-verdict" className="font-mono text-sm font-bold" style={{ color: rdColor }}>{rd.verdict}</span>
          </div>
          {rd.verdict === "NO_HISTORY" ? (
            <div className="font-mono text-[9px] text-[#6b7888]">{rd.note}</div>
          ) : (
            <>
              <div className="font-mono text-[9px] text-[#6b7888] mb-1">
                cooldown {rd.cooldown_elapsed ? "elapsed" : `${rd.cooldown_remaining_s}s left`} (min {rd.min_cooldown_s}s) · {rd.checks_passed}/5 checks
              </div>
              <div className="space-y-0.5">
                {(rd.checks || []).map((c) => (
                  <div key={c.key} className="flex items-center gap-1.5 text-[9px] font-mono" data-testid={`workflow-check-${c.key}`}>
                    <span style={{ color: c.passed ? "#34d399" : "#f87171" }}>{c.passed ? "✓" : "✗"}</span>
                    <span className="text-[#8b97a6]">{c.label}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* stages */}
      <div className="space-y-1.5" data-testid="workflow-stages">
        {data.stages.map((s) => {
          const isOpen = open === s.key;
          return (
            <div key={s.key} className="border border-[#1f2a36] bg-[#0a0e13]" data-testid={`workflow-stage-${s.key}`}>
              <button onClick={() => setOpen(isOpen ? null : s.key)}
                      className="w-full flex items-center gap-2 px-2 py-1.5 text-left">
                <span className="w-5 h-5 flex items-center justify-center rounded-full bg-[#1f2a36] text-[9px] font-mono font-bold text-[#38bdf8] shrink-0">{s.stage}</span>
                <span className="flex-1 font-mono text-[11px] font-bold text-[#c9d4e0]">{s.name}</span>
                <AutoBadge r={s.automation_readiness} />
                <span className="text-[#3d4a59] text-[10px]">{isOpen ? "▾" : "▸"}</span>
              </button>
              {isOpen && (
                <div className="px-2 pb-2 pt-1 border-t border-[#1f2a36]/50 grid grid-cols-2 md:grid-cols-3 gap-2 font-mono">
                  <Field label="Fund Location">{s.fund_location}</Field>
                  <Field label="Maps to states">{(s.states || []).join(" → ")}</Field>
                  <Field label="Est. Duration">{s.est_duration}</Field>
                  <Field label="Preconditions"><ul className="list-disc ml-3">{(s.preconditions || []).map((p, i) => <li key={i}>{p}</li>)}</ul></Field>
                  <Field label="Verification">{s.verification_method}</Field>
                  <Field label="Recovery Path">{s.recovery_path}</Field>
                  <Field label="Failure Modes"><ul className="list-disc ml-3">{(s.failure_modes || []).map((p, i) => <li key={i}>{p}</li>)}</ul></Field>
                  {s.automation_readiness?.blocking_reason && (
                    <Field label="Blocking Reason"><span className="text-[#ffb224]">{s.automation_readiness.blocking_reason}</span></Field>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-3 border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="workflow-future-path">
        <div className="font-mono text-[8px] text-[#6b7888] tracking-wider mb-0.5">FUTURE EXECUTION PATH (E5 — maps 1:1, no redesign)</div>
        <div className="font-mono text-[10px] text-[#38bdf8]">{data.future_execution_path}</div>
      </div>
      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        Read-only blueprint. No execution, no API keys, no wallet actions, no fund movement. E5 stays blocked.
      </div>
    </div>
  );
};
