import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtPct, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VERDICT = {
  READY_FOR_MICROCAPITAL_REVIEW: { c: "#34d399", t: "READY FOR MICRO-CAPITAL REVIEW" },
  PROMISING_NEEDS_MORE_DATA: { c: "#38bdf8", t: "PROMISING — NEEDS MORE DATA" },
  INSUFFICIENT_DATA: { c: "#6b7888", t: "INSUFFICIENT DATA" },
  NOT_READY: { c: "#f87171", t: "NOT READY" },
};
const BUCKETS = ["loss (<$0)", "$0–2", "$2–5", "$5–10", "$10+"];
const BUCKET_C = { "loss (<$0)": "#f87171", "$0–2": "#6b7888", "$2–5": "#ffb224", "$5–10": "#34d399", "$10+": "#34d399" };

const Stat = ({ label, value, color, testId }) => (
  <div className="bg-[#0a0e13] border border-[#1f2a36] px-2 py-1.5 text-center">
    <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div data-testid={testId} className="font-mono text-sm font-bold" style={color ? { color } : {}}>{value}</div>
  </div>
);

export const CertificationReportPanel = () => {
  const [d, setD] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/certification/report`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [load]);

  if (!d) return <div className="panel" data-testid="certification-report-panel"><div className="panel-title">Shadow Certification Report</div><div className="font-mono text-[11px] text-[#6b7888]">loading…</div></div>;

  const vd = VERDICT[d.verdict] || { c: "#6b7888", t: d.verdict };
  const tp = d.throughput, rc = d.recovery, pf = d.profit, rec = d.recommended_safe_cycle_size;
  const dist = pf.after_fees_distribution.distribution || {};
  const maxBucket = Math.max(1, ...BUCKETS.map((b) => dist[b] || 0));

  return (
    <div className="panel" data-testid="certification-report-panel">
      <div className="panel-title">
        Shadow Certification Report (E4)
        <span className="float-right text-[#3d4a59]">evidence-based readiness</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 mb-3 border border-[#1f2a36] bg-[#0a0e13] p-2">
        <div>
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Verdict</div>
          <div data-testid="certification-verdict" className="font-mono text-sm font-bold" style={{ color: vd.c }}>{vd.t}</div>
        </div>
        <div className="text-right">
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Recommended safe cycle size</div>
          <div data-testid="recommended-size" className="font-mono text-lg font-bold text-[#ffb224]">{fmtUsd(rec.recommended_usd)}
            <span className="text-[9px] text-[#6b7888] ml-1">({rec.confidence})</span></div>
        </div>
      </div>
      <div className="font-mono text-[9px] text-[#8b97a6] mb-3" data-testid="recommended-rationale">▸ {rec.rationale}</div>

      <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-3">
        <Stat label="Total" value={tp.total_shadow_cycles} color="#c9d4e0" testId="cert-total" />
        <Stat label="Completed" value={tp.completed} color="#34d399" testId="cert-completed" />
        <Stat label="Aborted" value={tp.aborted} color="#6b7888" />
        <Stat label="Stuck (ever)" value={tp.ever_stuck} color="#f87171" testId="cert-stuck" />
        <Stat label="Completion" value={fmtPct(tp.completion_rate_pct)} color="#38bdf8" />
        <Stat label="Recovery" value={rc.recovery_success_rate_pct != null ? fmtPct(rc.recovery_success_rate_pct) : "—"}
              color="#34d399" testId="cert-recovery-rate" />
      </div>

      {/* profit */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Expected vs realized (after fees)</div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Expected" value={fmtUsd(pf.expected_total_quote)} color="#ffb224" testId="cert-expected" />
            <Stat label="Realized" value={fmtUsd(pf.realized_total_quote)} color="#34d399" testId="cert-realized" />
            <Stat label="Avg variance" value={fmtUsd(pf.average_variance_quote)}
                  color={(pf.average_variance_quote ?? 0) >= 0 ? "#34d399" : "#f87171"} />
          </div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Profit-after-fees distribution</div>
          <div className="space-y-1" data-testid="cert-distribution">
            {BUCKETS.map((b) => (
              <div key={b} className="flex items-center gap-2 font-mono text-[9px]">
                <span className="w-16 text-[#8b97a6]">{b}</span>
                <div className="flex-1 h-3 bg-[#1f2a36]">
                  <div className="h-full" style={{ width: `${((dist[b] || 0) / maxBucket) * 100}%`, background: BUCKET_C[b] }} />
                </div>
                <span className="w-5 text-right text-[#c9d4e0]">{dist[b] || 0}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* venue + route perf */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Venue performance</div>
          <table className="w-full text-[10px] font-mono" data-testid="cert-venue-perf">
            <thead><tr className="panel-th"><th className="text-left">Venue</th><th className="text-right">Cyc</th><th className="text-right">Comp</th><th className="text-right">Rate</th><th className="text-right">Avg real</th></tr></thead>
            <tbody>
              {d.venue_performance.map((v) => (
                <tr key={v.key} className="border-b border-[#1f2a36]/50">
                  <td className="py-1 font-bold">{String(v.label).toUpperCase()}<span className="text-[#3d4a59]"> {v.role}</span></td>
                  <td className="py-1 text-right">{v.cycles}</td>
                  <td className="py-1 text-right text-[#34d399]">{v.completed}</td>
                  <td className="py-1 text-right">{fmtPct(v.completion_rate_pct)}</td>
                  <td className="py-1 text-right text-[#34d399]">{fmtUsd(v.avg_realized)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Route performance</div>
          <table className="w-full text-[10px] font-mono" data-testid="cert-route-perf">
            <thead><tr className="panel-th"><th className="text-left">Route</th><th className="text-right">Cyc</th><th className="text-right">Comp</th><th className="text-right">Avg real</th></tr></thead>
            <tbody>
              {d.route_performance.map((r) => (
                <tr key={r.key} className="border-b border-[#1f2a36]/50">
                  <td className="py-1">{r.label}</td>
                  <td className="py-1 text-right">{r.cycles}</td>
                  <td className="py-1 text-right text-[#34d399]">{r.completed}</td>
                  <td className="py-1 text-right text-[#34d399]">{fmtUsd(r.avg_realized)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="font-mono text-[8px] text-[#3d4a59] mt-3 pt-2 border-t border-[#1f2a36]">{d.note}</div>
    </div>
  );
};
