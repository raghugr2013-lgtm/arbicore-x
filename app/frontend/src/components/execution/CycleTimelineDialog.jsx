import { useEffect, useState } from "react";
import axios from "axios";
import { fmtPct, fmtTime, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const KIND = {
  normal: { bar: "#38bdf8", dot: "#38bdf8", label: "step" },
  waiting: { bar: "#fbbf24", dot: "#fbbf24", label: "waiting" },
  stuck: { bar: "#f87171", dot: "#f87171", label: "STUCK" },
  review: { bar: "#f87171", dot: "#f87171", label: "review" },
  terminal: { bar: "#34d399", dot: "#34d399", label: "done" },
};

const dur = (s) => {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${(s / 60).toFixed(1)}m`;
  return `${(s / 3600).toFixed(1)}h`;
};

export const CycleTimelineDialog = ({ cycleId, onClose }) => {
  const [t, setT] = useState(null);

  useEffect(() => {
    if (!cycleId) return;
    axios.get(`${API}/execution/cycles/${cycleId}/timeline`).then((r) => setT(r.data)).catch(() => {});
  }, [cycleId]);

  if (!cycleId) return null;
  const variance = t ? (t.realized_shadow_pnl_quote ?? 0) - (t.expected_profit_quote ?? 0) : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" data-testid="cycle-timeline-dialog"
         onClick={onClose}>
      <div className="bg-[#0a0e13] border border-[#1f2a36] w-full max-w-2xl max-h-[88vh] overflow-y-auto"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[#1f2a36] px-4 py-2 sticky top-0 bg-[#0a0e13]">
          <span className="font-mono text-sm font-bold tracking-wider">CYCLE TIMELINE — REPLAY</span>
          <button data-testid="timeline-close-btn" onClick={onClose} className="font-mono text-xs text-[#6b7888] hover:text-[#f87171]">✕ CLOSE</button>
        </div>

        {!t && <div className="p-4 font-mono text-[11px] text-[#6b7888]">loading…</div>}
        {t && (
          <div className="p-4">
            <div className="flex flex-wrap items-center gap-2 mb-3 font-mono text-[10px]">
              <span className="px-1.5 py-0.5 border font-bold" style={{
                borderColor: t.mode === "shadow" ? "#38bdf8" : "#6b7888",
                color: t.mode === "shadow" ? "#38bdf8" : "#6b7888" }}>{(t.mode || "scaffold").toUpperCase()}</span>
              <span className="text-[#6b7888]">{t.cycle_id.slice(0, 8)} · {t.route_name} · venue {(t.sell_venue || "—").toUpperCase()}</span>
              <span className="text-[#6b7888]">· total {dur(t.total_duration_s)}</span>
            </div>

            {/* profit comparison */}
            <div className="grid grid-cols-3 gap-2 mb-4">
              <div className="bg-[#10161e] border border-[#1f2a36] px-2 py-1.5 text-center">
                <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Expected profit</div>
                <div data-testid="timeline-expected" className="font-mono text-sm font-bold text-[#ffb224]">{fmtUsd(t.expected_profit_quote)}</div>
                <div className="font-mono text-[8px] text-[#6b7888]">{fmtPct(t.expected_net_pct)}</div>
              </div>
              <div className="bg-[#10161e] border border-[#1f2a36] px-2 py-1.5 text-center">
                <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Realized (shadow)</div>
                <div data-testid="timeline-realized" className="font-mono text-sm font-bold text-[#34d399]">{fmtUsd(t.realized_shadow_pnl_quote)}</div>
                <div className="font-mono text-[8px] text-[#6b7888]">{fmtPct(t.realized_net_pct)}</div>
              </div>
              <div className="bg-[#10161e] border border-[#1f2a36] px-2 py-1.5 text-center">
                <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Variance</div>
                <div className="font-mono text-sm font-bold" style={{ color: variance >= 0 ? "#34d399" : "#f87171" }}>{fmtUsd(variance)}</div>
              </div>
            </div>

            {t.stuck && t.recommended_action && (
              <div className="border border-[#f87171]/40 bg-[#f87171]/5 px-2 py-1.5 mb-3 font-mono text-[9px] text-[#f87171]">
                ⚠ Currently held — recommended: {t.recommended_action}
              </div>
            )}

            {/* timeline */}
            <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-2">State progression</div>
            <div className="relative pl-4" data-testid="timeline-segments">
              <div className="absolute left-[5px] top-1 bottom-1 w-px bg-[#1f2a36]" />
              {t.segments.map((s, i) => {
                const k = KIND[s.kind] || KIND.normal;
                return (
                  <div key={i} className="relative mb-2.5" data-testid={`timeline-seg-${s.state}`}>
                    <span className="absolute -left-4 top-1 w-2.5 h-2.5 rounded-full border-2 border-[#0a0e13]"
                          style={{ background: k.dot, boxShadow: s.current ? `0 0 6px ${k.dot}` : "none" }} />
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[11px] font-bold" style={{ color: k.bar }}>
                        {s.state} {s.current && <span className="text-[#ffb224]">◂ now</span>}
                      </span>
                      <span className="font-mono text-[9px] text-[#6b7888]">{dur(s.duration_s)} · {fmtTime(s.start)}</span>
                    </div>
                    <div className="font-mono text-[9px] text-[#8b97a6]">📍 {s.fund_location}</div>
                    {s.decision && (
                      <div className="font-mono text-[9px] mt-0.5" style={{
                        color: (s.decision.action || "").startsWith("recovery") ? "#38bdf8"
                          : s.kind === "stuck" ? "#f87171" : "#6b7888" }}>
                        ▸ {s.decision.action}{s.decision.detail ? ` — ${s.decision.detail}` : ""}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* events */}
            {t.events.length > 0 && (
              <>
                <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mt-3 mb-1">Recovery & stuck events</div>
                <div className="space-y-1" data-testid="timeline-events">
                  {t.events.map((e, i) => (
                    <div key={i} className="font-mono text-[9px] border-l-2 pl-2"
                         style={{ borderColor: e.type === "recovery" ? "#38bdf8" : "#f87171" }}>
                      <span style={{ color: e.type === "recovery" ? "#38bdf8" : "#f87171" }}>{e.type.toUpperCase()}</span>{" "}
                      <span className="text-[#6b7888]">{fmtTime(e.ts)}</span> — <span className="text-[#8b97a6]">{e.note}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div className="font-mono text-[8px] text-[#3d4a59] mt-3 pt-2 border-t border-[#1f2a36]">{t.note}</div>
          </div>
        )}
      </div>
    </div>
  );
};
