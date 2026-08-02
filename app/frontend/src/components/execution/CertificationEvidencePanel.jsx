import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VC = {
  READY_FOR_MICROCAPITAL_REVIEW: "#34d399",
  PROMISING_NEEDS_MORE_DATA: "#ffb224",
  NEEDS_MORE_DATA: "#ffb224",
  NOT_READY: "#f87171",
};

const Card = ({ n, title, children, testid }) => (
  <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid={testid}>
    <div className="font-mono text-[10px] font-bold tracking-wider text-[#38bdf8] mb-2">
      <span className="text-[#3d4a59]">{n}.</span> {title}
    </div>
    <div className="font-mono text-[10px] text-[#8b97a6] space-y-1">{children}</div>
  </div>
);

const Row = ({ k, v, c }) => (
  <div className="flex justify-between gap-3">
    <span className="text-[#6b7888]">{k}</span>
    <span className="font-bold text-right" style={{ color: c || "#c9d4e0" }}>{v}</span>
  </div>
);

const download = async (format, setBusy) => {
  setBusy(format);
  try {
    const r = await axios.get(`${API}/execution/certification/evidence/download`, {
      params: { format }, responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([r.data]));
    const a = document.createElement("a");
    a.href = url;
    a.download = `certification_evidence.${format === "json" ? "json" : "md"}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch {
    toast.error("Download failed");
  } finally {
    setBusy(null);
  }
};

export const CertificationEvidencePanel = () => {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/certification/evidence`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!d) {
    return (
      <div className="panel" data-testid="evidence-panel">
        <div className="panel-title">Certification Evidence Package</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center">loading evidence…</div>
      </div>
    );
  }
  if (!d.available) {
    return (
      <div className="panel" data-testid="evidence-panel">
        <div className="panel-title">Certification Evidence Package</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center" data-testid="evidence-empty">
          No certification campaign available. Run a Shadow Certification Campaign to generate evidence.
        </div>
      </div>
    );
  }

  const s = d.sections;
  const vc = VC[d.verdict] || "#6b7888";
  const fv = s["1_final_verdict"];
  const ta = s["2_threshold_audit"];
  const og = s["3_opportunity_gate_statistics"];
  const gh = s["4_go_window_history_summary"].summary || {};
  const il = s["5_safety_interlock_summary"];
  const vs = s["6_venue_qualification_snapshot"];
  const cap = s["7_recommended_capital_size"];
  const gaps = s["8_remaining_evidence_gaps"];
  const sc = il.campaign_start_context || {};
  const fc = il.campaign_finalize_context || {};
  const pv = vs.primary_execution_venue || {};

  return (
    <div className="panel" data-testid="evidence-panel">
      <div className="panel-title">
        Certification Evidence Package
        <span className="float-right text-[#3d4a59]">E4.7 opportunity-gated · read-only</span>
      </div>

      {/* verdict banner */}
      <div className="border p-3 mb-3 flex items-center justify-between flex-wrap gap-3"
           style={{ borderColor: vc + "66", background: vc + "0d" }}>
        <div>
          <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase">Certification Verdict</div>
          <div data-testid="evidence-verdict" className="font-mono text-xl font-bold" style={{ color: vc }}>{d.verdict}</div>
          <div className="font-mono text-[9px] text-[#6b7888]">campaign {(d.campaign_id || "").slice(0, 8)} · {fv.completed}/{fv.target} cycles</div>
        </div>
        <div className="flex items-end gap-1.5">
          <button data-testid="evidence-download-md" onClick={() => download("md", setBusy)} disabled={busy === "md"}
                  className="px-2 py-1.5 border border-[#34d399] text-[#34d399] font-mono text-[9px] font-bold hover:bg-[#34d399]/10">↓ MARKDOWN</button>
          <button data-testid="evidence-download-json" onClick={() => download("json", setBusy)} disabled={busy === "json"}
                  className="px-2 py-1.5 border border-[#38bdf8] text-[#38bdf8] font-mono text-[9px] font-bold hover:bg-[#38bdf8]/10">↓ JSON</button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <Card n="1" title="Final Verdict" testid="evidence-s1">
          <Row k="Verdict" v={fv.verdict} c={vc} />
          <Row k="Completion" v={`${fv.completion_rate_pct}%`} c="#34d399" />
          <Row k="PnL variance" v={`${fv.variance_pct}%`} />
          <Row k="Profitable rate" v={`${fv.profitable_rate_pct}%`} c="#34d399" />
          <Row k="Stuck rate" v={`${fv.stuck_rate_pct}%`} />
        </Card>

        <Card n="2" title="Threshold Audit" testid="evidence-s2">
          <Row k="Passed / Failed / N-A" v={`${ta.passed} / ${ta.failed} / ${ta.na}`} c={ta.all_thresholds_met ? "#34d399" : "#ffb224"} />
          {(ta.criteria || []).map((c, i) => (
            <div key={i} className="flex justify-between gap-2" data-testid={`evidence-criterion-${i}`}>
              <span style={{ color: c.status === "PASS" ? "#34d399" : c.status === "N/A" ? "#6b7888" : "#f87171" }}>
                {c.status === "PASS" ? "✓" : c.status === "N/A" ? "—" : "✗"} {c.criterion}
              </span>
              <span className="text-[#8b97a6] text-right whitespace-nowrap">{c.actual}</span>
            </div>
          ))}
        </Card>

        <Card n="3" title="Opportunity Gate Statistics" testid="evidence-s3">
          <Row k="Current gate" v={`${og.current_gate_verdict} · ${(og.current_venue || "").toUpperCase()}`}
               c={og.current_gate_verdict === "GO" ? "#34d399" : "#ffb224"} />
          <Row k="Current ROI" v={`${og.current_roi_pct}%`} c="#34d399" />
          <Row k="GO windows" v={`${og.go_windows_total} (${og.go_windows_open} open)`} />
          <Row k="Avg window dur" v={`${og.avg_window_duration_s ?? "—"}s`} />
          <Row k="Best peak ROI" v={`${og.best_peak_roi_pct ?? "—"}%`} c="#34d399" />
        </Card>

        <Card n="4" title="GO Window History Summary" testid="evidence-s4">
          <Row k="Total windows" v={gh.total_windows ?? 0} />
          <Row k="Closed" v={gh.closed ?? 0} />
          <Row k="Avg duration" v={`${gh.avg_duration_s ?? "—"}s`} />
          <Row k="Max duration" v={`${gh.max_duration_s ?? "—"}s`} />
          <Row k="Best peak ROI" v={`${gh.best_peak_roi_pct ?? "—"}%`} c="#34d399" />
        </Card>

        <Card n="5" title="Safety Interlock Summary" testid="evidence-s5">
          <Row k="Current verdict" v={il.current_verdict}
               c={il.current_verdict === "READY" ? "#34d399" : il.current_verdict === "WAIT" ? "#ffb224" : "#f87171"} />
          <Row k="Launch" v={`${sc.interlock_verdict} / ${sc.gate_verdict} · ${(sc.venue || "").toUpperCase()}`} />
          <Row k="Finalize" v={`${fc.interlock_verdict} / ${fc.gate_verdict} · ${(fc.venue || "").toUpperCase()}`} />
          {(il.wait_reasons || []).map((r, i) => <div key={i} style={{ color: "#ffb224" }}>▲ {r}</div>)}
          {(il.blocked_reasons || []).map((r, i) => <div key={i} style={{ color: "#f87171" }}>■ {r}</div>)}
        </Card>

        <Card n="6" title="Venue Qualification Snapshot" testid="evidence-s6">
          <Row k="Execution-approved" v={vs.counts?.execution_approved} c="#34d399" />
          <Row k="Monitor / Disabled" v={`${vs.counts?.monitor_only} / ${vs.counts?.disabled}`} />
          <Row k={`Primary: ${pv.name}`} v={`${pv.qualification_pct}%`} c="#34d399" />
          {(vs.promotion_candidates || []).map((c) => (
            <Row key={c.name} k={`Candidate: ${c.name}`} v={`${c.qualification_pct}%`} c="#ffb224" />
          ))}
        </Card>

        <Card n="7" title="Recommended Capital Size" testid="evidence-s7">
          <Row k="Certification size" v={fmtUsd(cap.certification_size_usd)} c="#34d399" />
          <Row k="Min executable size" v={fmtUsd(cap.min_executable_size_usd)} c="#ffb224" />
          <Row k="Actual executable rec" v={fmtUsd(cap.actual_executable_recommendation_usd)}
               c={cap.executable_actionable ? "#34d399" : "#f87171"} />
          <Row k="Actionable" v={cap.executable_actionable ? "YES" : "NO"}
               c={cap.executable_actionable ? "#34d399" : "#f87171"} />
          <Row k="Live max safe buy" v={fmtUsd(cap.live_max_safe_buy_usd)} c="#ffb224" />
          {cap.min_exceeds_certification_cap && (
            <div className="text-[9px] text-[#f87171] pt-1" data-testid="evidence-min-exec-warn">
              ⚠ Min executable ({fmtUsd(cap.min_executable_size_usd)}) exceeds certification cap ({fmtUsd(cap.certification_size_usd)}).
            </div>
          )}
          <div className="text-[9px] text-[#5a6573] pt-1">{cap.guidance}</div>
        </Card>

        <Card n="8" title="Remaining Evidence Gaps" testid="evidence-s8">
          {(gaps.outstanding || []).map((g, i) => (
            <div key={i} className="flex gap-1.5" data-testid={`evidence-gap-${i}`}>
              <span className="text-[#f87171]">▸</span><span>{g}</span>
            </div>
          ))}
        </Card>
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        READY_FOR_MICROCAPITAL_REVIEW authorizes a human REVIEW, not execution. E5 remains blocked — no execution,
        no API keys, no wallet actions, no fund movement.
      </div>
    </div>
  );
};
