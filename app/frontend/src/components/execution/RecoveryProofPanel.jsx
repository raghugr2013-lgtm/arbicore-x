import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Check = ({ ok, label }) => (
  <span className="font-mono text-[9px]" style={{ color: ok ? "#34d399" : "#f87171" }}>
    {ok ? "✓" : "✗"} {label}
  </span>
);

export const RecoveryProofPanel = () => {
  const [latest, setLatest] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/execution/recovery-proof/status`).then((r) => setLatest(r.data.latest)).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const run = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/execution/recovery-proof/run`, {});
      setLatest(r.data);
      toast.success(`Recovery proof complete — ${r.data.passed_count}/${r.data.total} scenarios passed`);
    } catch (e) { toast.error("Recovery proof failed"); } finally { setBusy(false); }
  };

  return (
    <div className="panel" data-testid="recovery-proof-panel">
      <div className="panel-title flex items-center gap-2 flex-wrap">
        <span>Recovery Proof Campaign (E4.6 — isolated, non-executing)</span>
        <div className="flex-1" />
        <button data-testid="recovery-proof-run-btn" disabled={busy} onClick={run}
          className="px-3 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 font-mono text-[10px] font-bold disabled:opacity-40">
          {busy ? "RUNNING…" : "▶ RUN PROOF BATTERY"}
        </button>
      </div>

      <div className="font-mono text-[10px] text-[#8b97a6] mb-3 border border-[#1f2a36] bg-[#0a0e13] px-2 py-1.5">
        Injects deposit delays, gate closures, routing failures & stuck states into isolated
        <b className="text-[#c9d4e0]"> recovery_proof</b> cycles (excluded from certification) and verifies
        stuck-detection → Telegram → recovery recommendation → recovery → persistence.
        <span className="text-[#ffb224]"> No real fund movement.</span>
      </div>

      {!latest ? (
        <div data-testid="recovery-proof-empty" className="font-mono text-[11px] text-[#6b7888]">No proof run yet — click RUN.</div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3 mb-3 border border-[#1f2a36] bg-[#0a0e13] p-2">
            <div>
              <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Result</div>
              <div data-testid="recovery-proof-result" className="font-mono text-sm font-bold" style={{ color: latest.overall_pass ? "#34d399" : "#f87171" }}>
                {latest.passed_count}/{latest.total} {latest.overall_pass ? "PASS" : "REVIEW"}
              </div>
            </div>
            <div>
              <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Telegram</div>
              <div className="font-mono text-[11px]" style={{ color: latest.telegram_state === "active" ? "#34d399" : "#ffb224" }}>{latest.telegram_state}</div>
            </div>
            <div className="font-mono text-[9px] text-[#3d4a59]">{fmtTime(latest.ts)}</div>
          </div>

          <table className="w-full text-[9px] font-mono" data-testid="recovery-proof-table">
            <thead><tr className="panel-th"><th className="text-left">Scenario</th><th className="text-left">Stuck state</th><th className="text-left">Checks</th><th className="text-right">Result</th></tr></thead>
            <tbody>
              {(latest.scenarios || []).map((s) => (
                <tr key={s.scenario} className="border-b border-[#1f2a36]/50">
                  <td className="py-1 text-[#c9d4e0]">{s.scenario}</td>
                  <td className="py-1 text-[#8b97a6]">{s.target_stuck_state}</td>
                  <td className="py-1">
                    <div className="flex flex-wrap gap-x-2">
                      <Check ok={s.stuck_detected} label="detect" />
                      <Check ok={s.recommendation_present} label="reco" />
                      <Check ok={s.persisted} label="persist" />
                      <Check ok={s.recovered} label="recover" />
                      {s.reroute_applied != null && <Check ok={s.reroute_applied} label="reroute" />}
                    </div>
                  </td>
                  <td className="py-1 text-right font-bold" style={{ color: s.passed ? "#34d399" : "#f87171" }}>{s.passed ? "PASS" : "FAIL"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="font-mono text-[8px] text-[#3d4a59] mt-2">{latest.note}</div>
        </>
      )}
    </div>
  );
};
