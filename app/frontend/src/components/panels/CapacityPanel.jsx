import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtQty } from "@/lib/fmt";

const Stat = ({ label, value, accent, testId }) => (
  <div className="border border-[#1f2a36] p-2">
    <div className="text-[9px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div data-testid={testId} className={`font-mono text-base font-bold ${accent || "text-[#c9d4e0]"}`}>
      {value}
    </div>
  </div>
);

export const CapacityPanel = ({ evaluation }) => {
  const cap = evaluation?.capacity || {};
  const curve = (evaluation?.slippage_curve || []).map((p) => ({
    q: p.q_base, qLabel: fmtQty(p.q_base), slip: p.slippage_pct,
  }));
  return (
    <div className="panel" data-testid="capacity-panel">
      <div className="panel-title">Capacity Engine — buy sizing (base units)</div>
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Min buy" value={fmtQty(cap.min_buy)} testId="capacity-min" />
        <Stat label="Recommended" value={fmtQty(cap.recommended)} accent="text-[#ffb224]" testId="capacity-recommended" />
        <Stat label="Max safe" value={fmtQty(cap.max_safe)} testId="capacity-max-safe" />
        <Stat label="Optimal" value={fmtQty(cap.optimal)} accent="text-[#38bdf8]" testId="capacity-optimal" />
      </div>
      <div className="mt-2 text-[10px] font-mono text-[#6b7888] flex justify-between">
        <span>book cap {fmtQty(cap.q_book)}</span>
        <span>vol cap {fmtQty(cap.q_volume)}</span>
        <span>×{(cap.safety_multiplier ?? 1).toFixed(2)} safety</span>
      </div>
      <div className="h-28 mt-2" data-testid="slippage-curve-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={curve} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
            <XAxis dataKey="qLabel" tick={{ fontSize: 8, fill: "#6b7888" }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 8, fill: "#6b7888" }} unit="%" />
            <Tooltip
              contentStyle={{ background: "#10161e", border: "1px solid #1f2a36", fontSize: 11, fontFamily: "IBM Plex Mono" }}
              formatter={(v) => v.toFixed(3) + "% slippage"}
              labelFormatter={(l) => "size " + l}
            />
            <Line type="stepAfter" dataKey="slip" stroke="#f87171" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="text-[9px] font-mono text-[#6b7888] mt-1">SLIPPAGE vs SELL SIZE (current bid ladder)</div>
    </div>
  );
};
