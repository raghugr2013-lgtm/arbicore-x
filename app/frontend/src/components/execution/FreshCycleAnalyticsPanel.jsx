import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtUsd, fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VERDICT_C = {
  FREQUENT: "#34d399",
  OCCASIONAL: "#ffb224",
  RARE: "#f87171",
  INSUFFICIENT_OBSERVATION_WINDOW: "#38bdf8",
};

const RANGES = [
  { days: 1, label: "TODAY" },
  { days: 7, label: "7D" },
  { days: 30, label: "30D" },
  { days: 90, label: "LIFETIME" },
];

const fmtPct = (v) => (v == null ? "—" : `${v}%`);
const fmtNum = (v) => (v == null ? "—" : String(v));
const fmtDur = (v) => {
  if (v == null) return "—";
  if (v < 60) return `${v.toFixed(1)}s`;
  if (v < 3600) return `${(v / 60).toFixed(1)}m`;
  return `${(v / 3600).toFixed(2)}h`;
};

const download = async (path, filename) => {
  try {
    const r = await axios.get(`${API}${path}`, { responseType: "blob" });
    const url = window.URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click();
    a.remove(); window.URL.revokeObjectURL(url);
    toast.success(`Downloaded ${filename}`);
  } catch (e) {
    toast.error(`Download failed: ${e.message || e}`);
  }
};

export const FreshCycleAnalyticsPanel = () => {
  const [days, setDays] = useState(30);
  const [pkg, setPkg] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    axios
      .get(`${API}/execution/fresh-cycle/analytics?days=${days}`)
      .then((r) => setPkg(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]);

  const s = pkg?.statistics || {};
  const sv = pkg?.survivability || {};
  const ev = pkg?.evidence || {};
  const a = ev?.answer || {};
  const ow = pkg?.observation_window || ev?.observation_window || {};
  const tg = ow?.target || {};
  const pg = ow?.progress || {};
  const trig = ow?.triggers || {};
  const formal = ev?.formal_recommendation || {};
  const verdict = ev.frequency_verdict;
  const vc = VERDICT_C[verdict] || "#6b7888";
  const windows = sv.windows || [];

  const fmtDays = (d) => (d == null ? "—" : `${(+d).toFixed(2)}d`);
  const fmtInt = (v) => (v == null ? "—" : Number(v).toLocaleString());
  const FORMAL_C = {
    "Not Recommended": "#f87171",
    "Occasional Manual Opportunity": "#ffb224",
    "Worth Monitoring": "#38bdf8",
    "Suitable For Automation": "#34d399",
  };

  return (
    <div className="panel" data-testid="fresh-cycle-analytics-panel">
      <div className="panel-title">
        Fresh-Cycle Opportunity Analytics &amp; Survivability
        <span className="float-right inline-flex items-center gap-2 text-[#3d4a59]">
          <span data-testid="fresh-cycle-obs-count">{s.observations || 0} obs · span {s.observation_span_hours || 0}h</span>
          {loading && <span className="text-[#38bdf8]">loading…</span>}
        </span>
      </div>

      {/* OBSERVATION WINDOW — data-collection mode banner */}
      <div className="border border-[#ffb224]/40 bg-[#0e0a05] p-3 mb-3" data-testid="observation-window">
        <div className="flex items-baseline justify-between flex-wrap gap-2 mb-2">
          <div className="font-mono text-[9px] text-[#ffb224] tracking-widest uppercase">
            OBSERVATION WINDOW · DATA-COLLECTION MODE
          </div>
          <div className="font-mono text-[9px] tracking-widest uppercase"
               style={{ color: ow.ready_for_first_formal_review ? "#34d399" : "#6b7888" }}>
            <span data-testid="ow-ready">{ow.ready_for_first_formal_review ? "READY FOR FORMAL REVIEW" : "ACCUMULATING"}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 font-mono text-[10px]">
          <div>
            <div className="text-[8px] text-[#6b7888] tracking-widest uppercase">Observation Start</div>
            <div data-testid="ow-start" className="text-[#c9d4e0] font-bold">{ow.observation_start_time ? fmtTime(ow.observation_start_time) : "—"}</div>
          </div>
          <div>
            <div className="text-[8px] text-[#6b7888] tracking-widest uppercase">Observation Duration</div>
            <div data-testid="ow-duration" className="text-[#c9d4e0] font-bold">{fmtDays(ow.observation_duration_days)}</div>
          </div>
          <div>
            <div className="text-[8px] text-[#6b7888] tracking-widest uppercase">Observation Count</div>
            <div data-testid="ow-count" className="text-[#c9d4e0] font-bold">{fmtInt(ow.observation_count)}</div>
          </div>
          <div>
            <div className="text-[8px] text-[#6b7888] tracking-widest uppercase">Target Window</div>
            <div data-testid="ow-target" className="text-[#ffb224] font-bold">
              {tg.days}d · {fmtInt(tg.observations)} obs · ≥{tg.significant_go_windows} GO windows
            </div>
          </div>
        </div>

        {/* progress bars for the 3 review-readiness triggers */}
        <div className="space-y-1 font-mono text-[9px]" data-testid="ow-progress">
          {[
            ["7-DAY OBSERVATION", pg.days_pct, trig.days,
              `${fmtDays(ow.observation_duration_days)} / ${tg.days}d`],
            ["10,000 OBSERVATIONS", pg.observations_pct, trig.observations,
              `${fmtInt(ow.observation_count)} / ${fmtInt(tg.observations)}`],
            ["STATISTICALLY SIGNIFICANT GO EVIDENCE", pg.go_windows_pct, trig.statistically_significant,
              `${pg.go_windows_total ?? 0} GO windows · ${pg.pct_time_roi_above_floor ?? 0}% time above floor`],
          ].map(([label, pct, fired, sub]) => (
            <div key={label}>
              <div className="flex justify-between text-[#6b7888]">
                <span><span style={{ color: fired ? "#34d399" : "#6b7888" }}>{fired ? "● " : "○ "}</span>{label}</span>
                <span className="text-[#8b97a6]">{sub}</span>
              </div>
              <div className="h-1.5 bg-[#1f2a36] mt-0.5 overflow-hidden">
                <div className="h-full" style={{
                  width: `${Math.min(100, pct || 0)}%`,
                  background: fired ? "#34d399" : "#ffb224",
                  transition: "width 600ms ease",
                }} />
              </div>
            </div>
          ))}
        </div>

        {ow.review_trigger_satisfied && (
          <div className="mt-2 font-mono text-[10px] text-[#34d399]" data-testid="ow-trigger-satisfied">
            ✓ Review trigger satisfied: {ow.review_trigger_satisfied}
          </div>
        )}
        <div className="mt-2 font-mono text-[8px] text-[#3d4a59]">{ow.note}</div>
      </div>

      {/* range tabs */}
      <div className="flex items-center gap-1 mb-3" data-testid="fresh-cycle-ranges">
        {RANGES.map((r) => (
          <button
            key={r.days}
            data-testid={`fresh-cycle-range-${r.days}`}
            onClick={() => setDays(r.days)}
            className={`font-mono text-[10px] font-bold tracking-wider px-2.5 py-1 border transition-colors ${
              days === r.days
                ? "border-[#ffb224] text-[#ffb224] bg-[#ffb224]/10"
                : "border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0]"
            }`}>
            {r.label}
          </button>
        ))}
        <span className="text-[9px] font-mono text-[#3d4a59] ml-2">window = {days} days</span>
      </div>

      {/* evidence verdict */}
      <div className="border p-3 mb-3" style={{ borderColor: vc + "66", background: vc + "15" }} data-testid="fresh-cycle-evidence">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase">Frequency verdict — fresh executable opportunity</div>
            <div data-testid="fresh-cycle-verdict" className="font-mono text-2xl font-bold mt-0.5" style={{ color: vc }}>
              {verdict || "—"}
            </div>
          </div>
          <div className="text-[10px] font-mono text-[#c9d4e0] max-w-[640px] flex-1">
            {ev.automation_recommendation || ""}
          </div>
        </div>
        {/* Formal 4-level recommendation (per operator brief) */}
        <div className="mt-3 pt-3 border-t border-[#1f2a36] grid grid-cols-1 md:grid-cols-[260px_1fr] gap-3" data-testid="formal-recommendation">
          <div>
            <div className="font-mono text-[8px] text-[#6b7888] tracking-widest uppercase">Formal Recommendation</div>
            <div data-testid="formal-level" className="font-mono text-lg font-bold mt-0.5"
                 style={{ color: FORMAL_C[formal.level] || "#6b7888" }}>
              {formal.level || "—"}
            </div>
          </div>
          <div className="font-mono text-[10px] text-[#8b97a6] self-center">
            {formal.rationale || ""}{!formal.ready_for_formal_review &&
              <span className="text-[#3d4a59]"> · awaiting observation-window trigger before this becomes binding</span>}
          </div>
        </div>
      </div>

      {/* headline statistics */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-px bg-[#1f2a36] border border-[#1f2a36] mb-3 font-mono" data-testid="fresh-cycle-headline">
        {[
          ["% TIME ROI > 0", fmtPct(s.pct_time_roi_positive), s.pct_time_roi_positive > 0 ? "#34d399" : "#f87171"],
          [`% TIME ROI ≥ ${s.floor_pct ?? "—"}%`, fmtPct(s.pct_time_roi_above_floor), s.pct_time_roi_above_floor >= 10 ? "#34d399" : s.pct_time_roi_above_floor >= 1 ? "#ffb224" : "#f87171"],
          ["% TIME GO", fmtPct(s.pct_time_go), s.pct_time_go > 0 ? "#34d399" : "#f87171"],
          ["AVG POS. ROI", fmtPct(s.avg_positive_roi_pct), "#34d399"],
          ["MAX ROI", fmtPct(s.max_roi_pct), s.max_roi_pct > 0 ? "#34d399" : "#f87171"],
          ["FLOOR", fmtPct(s.floor_pct), "#ffb224"],
        ].map(([l, v, c]) => (
          <div key={l} className="bg-[#10161e] px-3 py-2">
            <div className="text-[8px] tracking-widest text-[#6b7888]">{l}</div>
            <div className="text-lg font-bold" style={{ color: c }}>{v}</div>
          </div>
        ))}
      </div>

      {/* GO window statistics */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-px bg-[#1f2a36] border border-[#1f2a36] mb-3 font-mono" data-testid="fresh-cycle-go-stats">
        {[
          ["GO WINDOWS", fmtNum(s.go_windows_total), "#c9d4e0"],
          ["WINDOWS / DAY", fmtNum(s.go_windows_per_day), "#ffb224"],
          ["WINDOWS / WEEK", fmtNum(s.go_windows_per_week), "#ffb224"],
          ["AVG WINDOW DUR", fmtDur(s.avg_go_window_s), "#38bdf8"],
          ["LONGEST WINDOW", fmtDur(s.longest_go_window_s), "#38bdf8"],
          ["AVG MAX SAFE BUY $ IN GO", fmtUsd(s.avg_max_safe_buy_usd_in_go_windows), "#a78bfa"],
        ].map(([l, v, c]) => (
          <div key={l} className="bg-[#10161e] px-3 py-2">
            <div className="text-[8px] tracking-widest text-[#6b7888]">{l}</div>
            <div className="text-lg font-bold" style={{ color: c }}>{v}</div>
          </div>
        ))}
      </div>

      {/* survivability table */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="fresh-cycle-survivability">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[9px] text-[#6b7888] tracking-wider">GO WINDOW SURVIVABILITY ({windows.length})</span>
          <span className="font-mono text-[8px] text-[#3d4a59]">{sv.note || ""}</span>
        </div>
        {windows.length === 0 ? (
          <div className="font-mono text-[10px] text-[#3d4a59] py-3 text-center">No GO windows recorded yet — keep observing.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[9px] font-mono">
              <thead>
                <tr className="panel-th text-[#6b7888]">
                  <th className="text-left">Start</th>
                  <th className="text-left">End</th>
                  <th className="text-right">Dur</th>
                  <th className="text-right">Peak ROI</th>
                  <th className="text-right">Avg ROI</th>
                  <th className="text-right">Max Safe Buy</th>
                  <th className="text-left">Venue</th>
                  <th className="text-right">Samples</th>
                  <th className="text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {windows.slice(0, 50).map((w, i) => (
                  <tr key={i} className="border-b border-[#1f2a36]/50" data-testid={`fresh-cycle-window-${i}`}>
                    <td className="py-1 text-[#6b7888]">{fmtTime(w.start_time)}</td>
                    <td className="py-1 text-[#6b7888]">{w.end_time ? fmtTime(w.end_time) : "—"}</td>
                    <td className="py-1 text-right text-[#8b97a6]">{fmtDur(w.duration_s)}</td>
                    <td className="py-1 text-right text-[#34d399]">{fmtPct(w.peak_roi_pct)}</td>
                    <td className="py-1 text-right text-[#34d399]">{fmtPct(w.avg_roi_pct)}</td>
                    <td className="py-1 text-right text-[#ffb224]">{fmtUsd(w.max_safe_buy_usd)}</td>
                    <td className="py-1 text-[#c9d4e0]">{(w.venue || "—").toUpperCase()}</td>
                    <td className="py-1 text-right text-[#8b97a6]">{w.samples}</td>
                    <td className="py-1"><span style={{ color: w.status === "open" ? "#34d399" : "#6b7888" }}>{(w.status || "—").toUpperCase()}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* headline answer */}
      <div className="border border-[#38bdf8]/30 bg-[#38bdf8]/5 p-3 mb-3 font-mono text-[10px]" data-testid="fresh-cycle-answer">
        <div className="text-[9px] tracking-widest uppercase text-[#38bdf8] mb-1">Core Evidence — {ev.question}</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1 text-[#c9d4e0]">
          <div><span className="text-[#6b7888]">Observations:</span> <b>{a.observations}</b></div>
          <div><span className="text-[#6b7888]">Span (h):</span> <b>{a.observation_span_hours}</b></div>
          <div><span className="text-[#6b7888]">% ROI &gt; 0:</span> <b>{fmtPct(a.pct_time_fresh_roi_positive)}</b></div>
          <div><span className="text-[#6b7888]">% ROI ≥ floor:</span> <b>{fmtPct(a.pct_time_fresh_roi_above_floor)}</b></div>
          <div><span className="text-[#6b7888]">Max ROI:</span> <b>{fmtPct(a.max_roi_pct)}</b></div>
          <div><span className="text-[#6b7888]">Avg pos. ROI:</span> <b>{fmtPct(a.avg_positive_roi_pct)}</b></div>
          <div><span className="text-[#6b7888]">GO/day:</span> <b>{fmtNum(a.go_windows_per_day)}</b></div>
          <div><span className="text-[#6b7888]">GO/week:</span> <b>{fmtNum(a.go_windows_per_week)}</b></div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2" data-testid="fresh-cycle-downloads">
        <button data-testid="fresh-cycle-download-md"
                onClick={() => download(`/execution/fresh-cycle/download?format=md&days=${days}`, `fresh_cycle_${days}d.md`)}
                className="px-3 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 font-mono text-[10px] font-bold tracking-wider">
          ↓ DOWNLOAD MARKDOWN
        </button>
        <button data-testid="fresh-cycle-download-json"
                onClick={() => download(`/execution/fresh-cycle/download?format=json&days=${days}`, `fresh_cycle_${days}d.json`)}
                className="px-3 py-1 border border-[#a78bfa] text-[#a78bfa] hover:bg-[#a78bfa]/10 font-mono text-[10px] font-bold tracking-wider">
          ↓ DOWNLOAD JSON
        </button>
        <span className="text-[8px] font-mono text-[#3d4a59] ml-auto self-center">
          Per-tick observations recorded by the gate monitor (~20s cadence). Read-only. E5 BLOCKED.
        </span>
      </div>
    </div>
  );
};
