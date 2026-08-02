import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const REC = {
  READY_FOR_MICROCAPITAL_REVIEW: { c: "#34d399", t: "READY FOR MICRO-CAPITAL REVIEW" },
  NEEDS_MORE_DATA: { c: "#38bdf8", t: "NEEDS MORE DATA" },
  NOT_READY: { c: "#f87171", t: "NOT READY" },
};
const STATUS_C = { PASS: "#34d399", FAIL: "#f87171", "N/A": "#6b7888" };
const SEV_C = { high: "#f87171", medium: "#ffb224", low: "#6b7888" };

const Stat = ({ label, value, color, testId }) => (
  <div className="bg-[#0a0e13] border border-[#1f2a36] px-2 py-1.5 text-center">
    <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div data-testid={testId} className="font-mono text-sm font-bold" style={color ? { color } : {}}>{value}</div>
  </div>
);

const Evidence = ({ items }) =>
  !items?.length ? null : (
    <div className="space-y-0.5 mt-1.5 mb-1">
      {items.map((e, i) => (
        <div key={i} className="font-mono text-[10px] flex items-start gap-1.5">
          <span style={{ color: STATUS_C[e.status] || "#6b7888" }} className="font-bold w-9 shrink-0">{e.status}</span>
          <span className="text-[#8b97a6]">{e.metric} = </span>
          <span className="text-[#c9d4e0] font-bold">{String(e.value)}</span>
          <span className="text-[#3d4a59]">(threshold {e.threshold})</span>
        </div>
      ))}
    </div>
  );

const Section = ({ sec, idx }) => (
  <div className="border border-[#1f2a36] bg-[#0a0e13] p-2.5" data-testid={`review-section-${idx}`}>
    <div className="font-mono text-[11px] font-bold text-[#c9d4e0] mb-1">{sec.title}</div>
    {sec.headline && <div className="font-mono text-[10px] text-[#8b97a6] mb-1">{sec.headline}</div>}
    {sec.breach_reason && <div className="font-mono text-[10px] text-[#f87171] mb-1">⚠ breach: {sec.breach_reason}</div>}
    {sec.narrative && <div className="font-mono text-[10px] text-[#8b97a6]">{sec.narrative}</div>}
    <Evidence items={sec.evidence} />

    {/* Section 3 — stuck-cycle analysis */}
    {sec.by_state?.length > 0 && (
      <table className="w-full text-[9px] font-mono mt-1">
        <thead><tr className="panel-th"><th className="text-left">Stuck leg</th><th className="text-right">Cnt</th><th className="text-right">Recov</th><th className="text-right">Abort</th><th className="text-right">Stuck</th><th className="text-right">Avg s</th></tr></thead>
        <tbody>
          {sec.by_state.map((g) => (
            <tr key={g.state} className="border-b border-[#1f2a36]/50">
              <td className="py-0.5">{g.label}</td>
              <td className="py-0.5 text-right">{g.count}</td>
              <td className="py-0.5 text-right text-[#34d399]">{g.recovered}</td>
              <td className="py-0.5 text-right text-[#f87171]">{g.aborted}</td>
              <td className="py-0.5 text-right text-[#ffb224]">{g.still_stuck}</td>
              <td className="py-0.5 text-right">{g.avg_seconds_stuck ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}

    {/* Section 5 — venue comparison */}
    {sec.coinstore && (
      <table className="w-full text-[9px] font-mono mt-1" data-testid="review-venue-table">
        <thead><tr className="panel-th"><th className="text-left">Venue</th><th>Role</th><th className="text-right">Cyc</th><th className="text-right">Comp</th><th className="text-right">Rate</th><th className="text-right">Avg real</th></tr></thead>
        <tbody>
          {[sec.coinstore, sec.bitmart, ...(sec.other_venues || [])].map((v) => (
            <tr key={v.key} className="border-b border-[#1f2a36]/50">
              <td className="py-0.5 font-bold">{String(v.label || v.key).toUpperCase()}</td>
              <td className="py-0.5 text-center text-[#3d4a59]">{v.role || "—"}</td>
              <td className="py-0.5 text-right">{v.cycles ?? 0}</td>
              <td className="py-0.5 text-right text-[#34d399]">{v.completed ?? 0}</td>
              <td className="py-0.5 text-right">{v.completion_rate_pct != null ? `${v.completion_rate_pct}%` : "—"}</td>
              <td className="py-0.5 text-right text-[#34d399]">{v.avg_realized != null ? `$${v.avg_realized}` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}

    {/* Section 6 — route comparison */}
    {sec.routes?.length > 0 && (
      <table className="w-full text-[9px] font-mono mt-1">
        <thead><tr className="panel-th"><th className="text-left">Route</th><th className="text-right">Cyc</th><th className="text-right">Comp</th><th className="text-right">Avg real</th></tr></thead>
        <tbody>
          {sec.routes.map((r) => (
            <tr key={r.key} className="border-b border-[#1f2a36]/50">
              <td className="py-0.5">{r.label}</td>
              <td className="py-0.5 text-right">{r.cycles}</td>
              <td className="py-0.5 text-right text-[#34d399]">{r.completed}</td>
              <td className="py-0.5 text-right text-[#34d399]">{r.avg_realized != null ? `$${r.avg_realized}` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}

    {/* Section 8 — failure modes */}
    {sec.modes && (
      sec.modes.length === 0
        ? <div className="font-mono text-[10px] text-[#34d399] mt-1">✓ No failure modes triggered.</div>
        : (
          <div className="space-y-1 mt-1">
            {sec.modes.map((m, i) => (
              <div key={i} className="font-mono text-[9px] border-l-2 pl-2" style={{ borderColor: SEV_C[m.severity] }}>
                <span style={{ color: SEV_C[m.severity] }} className="font-bold uppercase">{m.severity}</span>{" "}
                <span className="text-[#c9d4e0]">{m.mode}</span>{" "}
                <span className="text-[#6b7888]">×{m.occurrences} (rec {m.recovered} / abort {m.aborted})</span>
                <div className="text-[#3d4a59]">{m.mitigation}</div>
              </div>
            ))}
          </div>
        )
    )}

    {/* Section 9 — readiness criteria */}
    {sec.criteria?.length > 0 && (
      <table className="w-full text-[9px] font-mono mt-1" data-testid="review-criteria-table">
        <thead><tr className="panel-th"><th className="text-left">Criterion</th><th className="text-right">Actual</th><th className="text-right">Threshold</th><th>Sev</th><th className="text-right">Status</th></tr></thead>
        <tbody>
          {sec.criteria.map((cr, i) => (
            <tr key={i} className="border-b border-[#1f2a36]/50">
              <td className="py-0.5">{cr.criterion}</td>
              <td className="py-0.5 text-right text-[#c9d4e0]">{cr.actual}</td>
              <td className="py-0.5 text-right text-[#6b7888]">{cr.threshold}</td>
              <td className="py-0.5 text-center text-[#3d4a59]">{cr.severity}</td>
              <td className="py-0.5 text-right font-bold" style={{ color: STATUS_C[cr.status] }}>{cr.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}

    {/* Section 10 — final recommendation */}
    {sec.next_steps && (
      <div className="mt-1 font-mono text-[9px]">
        {sec.blocking_criteria?.length > 0 && (
          <div className="text-[#f87171] mb-1">Blocking: {sec.blocking_criteria.join("; ")}</div>
        )}
        {sec.gaps_to_close?.length > 0 && (
          <div className="text-[#ffb224] mb-1">Gaps: {sec.gaps_to_close.join("; ")}</div>
        )}
        <div className="text-[#8b97a6]">Next steps:</div>
        <ul className="list-disc ml-4 text-[#8b97a6]">{sec.next_steps.map((n, i) => <li key={i}>{n}</li>)}</ul>
        <div className="text-[#3d4a59] mt-1">{sec.guard_rails}</div>
      </div>
    )}
  </div>
);

export const CertificationReviewPanel = () => {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback((regenerate = false) => {
    axios.get(`${API}/execution/certification/review`, { params: regenerate ? { regenerate: true } : {} })
      .then((r) => setD(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(() => load(), 15000);
    return () => clearInterval(t);
  }, [load]);

  const download = async (fmt) => {
    setBusy(true);
    try {
      const r = await axios.get(`${API}/execution/certification/review/download`, {
        params: { format: fmt }, responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `certification_review.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`Downloaded certification review (${fmt.toUpperCase()})`);
    } catch (e) {
      toast.error("Download failed");
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async () => {
    setBusy(true);
    try {
      const r = await axios.get(`${API}/execution/certification/review`, { params: { regenerate: true } });
      setD(r.data);
      toast.success("Certification review regenerated");
    } catch (e) {
      toast.error("Regenerate failed");
    } finally {
      setBusy(false);
    }
  };

  if (!d) return (
    <div className="panel" data-testid="certification-review-panel">
      <div className="panel-title">Certification Review Package</div>
      <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
    </div>
  );

  if (!d.available) {
    return (
      <div className="panel" data-testid="certification-review-panel">
        <div className="panel-title">Certification Review Package (E4.5)</div>
        <div data-testid="review-unavailable" className="font-mono text-[11px] text-[#6b7888] border border-[#1f2a36] bg-[#0a0e13] px-3 py-3">
          {d.message}
        </div>
      </div>
    );
  }

  const rec = REC[d.recommendation] || { c: "#6b7888", t: d.recommendation };
  const s = d.summary;

  return (
    <div className="panel" data-testid="certification-review-panel">
      <div className="panel-title">
        Certification Review Package (E4.5)
        <span className="float-right text-[#3d4a59]">10-section evidence package</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 mb-3 border border-[#1f2a36] bg-[#0a0e13] p-2">
        <div>
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Recommendation</div>
          <div data-testid="review-recommendation" className="font-mono text-sm font-bold" style={{ color: rec.c }}>{rec.t}</div>
          <div className="font-mono text-[9px] text-[#3d4a59] mt-0.5">
            campaign {d.campaign.id.slice(0, 8)} · {d.campaign.status} · {s.completed}/{d.campaign.target_completed} completed
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button data-testid="review-download-md" disabled={busy} onClick={() => download("md")}
            className="px-2 py-1 border border-[#1f2a36] text-[#8b97a6] hover:text-[#c9d4e0] font-mono text-[10px] disabled:opacity-40">↓ MD</button>
          <button data-testid="review-download-json" disabled={busy} onClick={() => download("json")}
            className="px-2 py-1 border border-[#1f2a36] text-[#8b97a6] hover:text-[#c9d4e0] font-mono text-[10px] disabled:opacity-40">↓ JSON</button>
          <button data-testid="review-regenerate" disabled={busy} onClick={regenerate}
            className="px-2 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 font-mono text-[10px] disabled:opacity-40">⟳ REGEN</button>
        </div>
      </div>

      <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-3">
        <Stat label="Completed" value={s.completed} color="#34d399" testId="review-completed" />
        <Stat label="Completion" value={s.completion_rate_pct != null ? `${s.completion_rate_pct}%` : "—"} color="#38bdf8" />
        <Stat label="Recovery" value={s.recovery_success_rate_pct != null ? `${s.recovery_success_rate_pct}%` : "—"} color="#34d399" />
        <Stat label="Stuck rate" value={`${s.stuck_rate_pct}%`} color="#f87171" />
        <Stat label="Variance" value={s.variance_pct != null ? `${s.variance_pct}%` : "—"} color="#ffb224" />
        <Stat label="Rec. size" value={s.recommended_safe_cycle_usd != null ? `$${s.recommended_safe_cycle_usd}` : "—"} color="#38bdf8" />
      </div>

      <div className="space-y-2">
        {d.sections.map((sec, i) => <Section key={i} sec={sec} idx={i + 1} />)}
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-3 pt-2 border-t border-[#1f2a36]">{d.note}</div>
    </div>
  );
};
