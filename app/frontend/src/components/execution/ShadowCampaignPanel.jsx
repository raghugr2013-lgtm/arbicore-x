import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtPct, fmtUsd, fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VERDICT = {
  READY_FOR_MICROCAPITAL_REVIEW: { c: "#34d399", t: "READY FOR MICRO-CAPITAL REVIEW" },
  PROMISING_NEEDS_MORE_DATA: { c: "#38bdf8", t: "PROMISING — NEEDS MORE DATA" },
  INSUFFICIENT_DATA: { c: "#6b7888", t: "INSUFFICIENT DATA" },
  NOT_READY: { c: "#f87171", t: "NOT READY" },
};

const STATUS_C = {
  running: "#38bdf8",
  completed: "#34d399",
  stopped_breach: "#f87171",
  stopped_manual: "#ffb224",
};

const Stat = ({ label, value, color, testId }) => (
  <div className="bg-[#0a0e13] border border-[#1f2a36] px-2 py-1.5 text-center">
    <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div data-testid={testId} className="font-mono text-sm font-bold" style={color ? { color } : {}}>{value}</div>
  </div>
);

export const ShadowCampaignPanel = ({ onChanged }) => {
  const [d, setD] = useState(null);
  const [target, setTarget] = useState(20);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/execution/campaign/status`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const start = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/execution/campaign/start`, { target_completed: Number(target) });
      toast.success(`Shadow certification campaign started — target ${target} completed cycles (non-executing)`);
      load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Start failed");
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/execution/campaign/stop`, {});
      toast.success("Campaign stopped — shadow mode disabled");
      load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Stop failed");
    } finally {
      setBusy(false);
    }
  };

  if (!d) return (
    <div className="panel" data-testid="campaign-panel">
      <div className="panel-title">Shadow Certification Campaign</div>
      <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
    </div>
  );

  const camp = d.campaign;
  const active = camp && camp.status === "running";
  const terminal = camp && !active;
  const rep = d.live_report;
  const liveVerdict = rep ? (VERDICT[rep.verdict] || { c: "#6b7888", t: rep.verdict }) : null;
  const finalV = camp?.final_verdict ? (VERDICT[camp.final_verdict] || { c: "#6b7888", t: camp.final_verdict }) : null;

  return (
    <div className="panel" data-testid="campaign-panel">
      <div className="panel-title">
        Shadow Certification Campaign (E4.5) — hands-off, non-executing
        <span className="float-right" style={{ color: d.monitor_running ? "#34d399" : "#6b7888" }}>
          {d.monitor_running ? "● monitor up" : "○ monitor down"}
        </span>
      </div>

      <div className="font-mono text-[10px] text-[#8b97a6] mb-3 border border-[#1f2a36] bg-[#0a0e13] px-2 py-1.5">
        Runs Shadow Mode automatically to a target number of <b className="text-[#c9d4e0]">completed</b> shadow
        cycles, then generates an updated certification report. Auto-stops on a breach (recovery failure, stuck-rate,
        or variance over threshold). <span className="text-[#ffb224]">No trading · no wallet · no withdrawals · no fund movement.</span>
      </div>

      {/* ---------- ACTIVE ---------- */}
      {active && (
        <div data-testid="campaign-active">
          <div className="flex items-center justify-between mb-2">
            <div className="font-mono text-[11px]">
              <span className="text-[#6b7888]">campaign </span>
              <span data-testid="campaign-status" className="font-bold" style={{ color: STATUS_C.running }}>RUNNING</span>
              <span className="text-[#3d4a59]"> · {camp.id.slice(0, 8)}</span>
            </div>
            <button
              data-testid="campaign-stop-btn"
              disabled={busy}
              onClick={stop}
              className="px-3 py-1 border border-[#f87171] text-[#f87171] hover:bg-[#f87171]/10 font-mono text-[10px] font-bold tracking-wider disabled:opacity-40"
            >
              ◼ STOP CAMPAIGN
            </button>
          </div>

          <div className="mb-3">
            <div className="flex items-center justify-between font-mono text-[9px] text-[#6b7888] mb-1">
              <span>PROGRESS — {camp.completed_count} / {camp.target_completed} completed</span>
              <span data-testid="campaign-progress-pct">{d.progress_pct ?? 0}%</span>
            </div>
            <div className="h-3 bg-[#1f2a36]" data-testid="campaign-progress">
              <div className="h-full transition-all" style={{ width: `${d.progress_pct ?? 0}%`, background: "#38bdf8" }} />
            </div>
          </div>

          <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-3">
            <Stat label="Completed" value={camp.completed_count ?? 0} color="#34d399" testId="campaign-completed" />
            <Stat label="Total cyc" value={camp.total_count ?? 0} color="#c9d4e0" />
            <Stat label="Stuck rate" value={camp.stuck_rate_pct != null ? fmtPct(camp.stuck_rate_pct, false) : "—"} color="#f87171" testId="campaign-stuck-rate" />
            <Stat label="Recovery" value={camp.recovery_success_rate_pct != null ? fmtPct(camp.recovery_success_rate_pct, false) : "—"} color="#34d399" testId="campaign-recovery-rate" />
            <Stat label="Rec. fails" value={camp.recovery_failures ?? 0} color={(camp.recovery_failures ?? 0) > 0 ? "#f87171" : "#6b7888"} testId="campaign-recovery-failures" />
            <Stat label="Variance" value={camp.variance_pct != null ? fmtPct(camp.variance_pct, false) : "—"} color="#ffb224" testId="campaign-variance" />
          </div>

          {rep && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-2">
              <div className="border border-[#1f2a36] bg-[#0a0e13] px-2 py-1.5">
                <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Live verdict</div>
                <div data-testid="campaign-live-verdict" className="font-mono text-xs font-bold" style={{ color: liveVerdict.c }}>{liveVerdict.t}</div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Stat label="Expected" value={fmtUsd(rep.profit.expected_total_quote)} color="#ffb224" />
                <Stat label="Realized" value={fmtUsd(rep.profit.realized_total_quote)} color="#34d399" />
                <Stat label="Rec. size" value={fmtUsd(rep.recommended_safe_cycle_size.recommended_usd)} color="#38bdf8" />
              </div>
            </div>
          )}

          <div className="font-mono text-[9px] text-[#3d4a59]">
            started {fmtTime(camp.start_at)} · last check {camp.last_checked_at ? fmtTime(camp.last_checked_at) : "—"} · auto-checks every {d.check_interval_s}s
          </div>
        </div>
      )}

      {/* ---------- TERMINAL (last result) ---------- */}
      {terminal && (
        <div data-testid="campaign-result" className="mb-3 border border-[#1f2a36] bg-[#0a0e13] p-2">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
            <div className="font-mono text-[11px]">
              <span className="text-[#6b7888]">last campaign </span>
              <span data-testid="campaign-status" className="font-bold uppercase" style={{ color: STATUS_C[camp.status] || "#6b7888" }}>
                {String(camp.status).replace("_", " ")}
              </span>
              <span className="text-[#3d4a59]"> · {camp.id.slice(0, 8)}</span>
            </div>
            <div className="font-mono text-[10px] text-[#8b97a6]">
              {camp.completed_count} / {camp.target_completed} completed
            </div>
          </div>
          {finalV && (
            <div className="font-mono text-xs font-bold mb-1" data-testid="campaign-final-verdict" style={{ color: finalV.c }}>
              VERDICT: {finalV.t}
            </div>
          )}
          {camp.breach_reason && (
            <div data-testid="campaign-breach" className="font-mono text-[10px] text-[#f87171]">⚠ BREACH: {camp.breach_reason}</div>
          )}
          <div className="font-mono text-[9px] text-[#3d4a59] mt-1">
            ended {fmtTime(camp.ended_at)} — see full Shadow Certification Report below for venue/route performance & sizing.
          </div>
        </div>
      )}

      {/* ---------- START FORM (no active campaign) ---------- */}
      {!active && (
        <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-[#1f2a36]" data-testid="campaign-start-form">
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">Target completed cycles</div>
            <input
              data-testid="campaign-target-input"
              type="number"
              min={1}
              max={200}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="w-24 bg-[#0a0e13] border border-[#1f2a36] px-2 py-1 font-mono text-sm text-[#c9d4e0] focus:border-[#38bdf8] outline-none"
            />
          </div>
          <button
            data-testid="campaign-start-btn"
            disabled={busy}
            onClick={start}
            className="px-4 py-1.5 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 font-mono text-[11px] font-bold tracking-wider disabled:opacity-40"
          >
            ▶ START CAMPAIGN
          </button>
          <div className="font-mono text-[9px] text-[#6b7888] flex-1 min-w-[180px]">
            Enabling a campaign turns Shadow Mode ON and drives the workflow off live data only.
            E5 (micro-capital) stays blocked until the final verdict reads READY.
          </div>
        </div>
      )}
    </div>
  );
};
