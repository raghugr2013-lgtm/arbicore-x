import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const VCOLOR = { GO: "#34d399", WAIT: "#fbbf24", NO_GO: "#f87171" };

export const HistoricalPanel = ({ routeId }) => {
  const [hours, setHours] = useState(6);
  const [data, setData] = useState(null);

  const fetchReplay = useCallback(() => {
    axios.get(`${API}/routes/${routeId}/replay`, { params: { hours } })
      .then((res) => setData(res.data)).catch(() => {});
  }, [routeId, hours]);

  useEffect(() => {
    fetchReplay();
    const t = setInterval(fetchReplay, 30000);
    return () => clearInterval(t);
  }, [fetchReplay]);

  const tl = (data?.timeline || []).map((x) => ({ ...x, t: fmtTime(x.ts) }));
  const vp = data?.verdict_pct || {};
  const blocked = data?.blocked_opportunity;

  return (
    <div className="panel" data-testid="historical-panel">
      <div className="panel-title">
        Historical Performance — Opportunity Replay
        <span className="float-right flex gap-1">
          {[1, 6, 24].map((h) => (
            <button key={h} data-testid={`replay-range-${h}h`} onClick={() => setHours(h)}
                    className={`px-2 py-0.5 text-[9px] border ${hours === h ? "border-[#ffb224] text-[#ffb224]" : "border-[#1f2a36] text-[#6b7888]"}`}>
              {h}H
            </button>
          ))}
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 mb-2 font-mono text-center">
        {[["GO", vp.GO, "#34d399"], ["WAIT", vp.WAIT, "#fbbf24"], ["NO GO", vp.NO_GO, "#f87171"],
          ["EVALS", data?.evaluations_count, "#38bdf8"]].map(([l, v, c]) => (
          <div key={l} className="border border-[#1f2a36] py-1.5">
            <div className="text-lg font-bold" style={{ color: c }}>{v != null ? (l === "EVALS" ? v : `${v}%`) : "—"}</div>
            <div className="text-[8px] tracking-widest text-[#6b7888]">{l}</div>
          </div>
        ))}
      </div>
      {/* verdict ribbon */}
      <div className="flex h-2 mb-2" data-testid="verdict-ribbon">
        {tl.map((x, i) => (
          <div key={i} className="flex-1" style={{ background: VCOLOR[x.verdict] || "#1f2a36" }} title={`${x.t} ${x.verdict}`} />
        ))}
      </div>
      <div className="h-32" data-testid="replay-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={tl} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
            <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#6b7888" }} interval="preserveStartEnd" />
            <YAxis yAxisId="net" tick={{ fontSize: 8, fill: "#6b7888" }} />
            <YAxis yAxisId="score" orientation="right" domain={[0, 100]} tick={{ fontSize: 8, fill: "#6b7888" }} />
            <Tooltip contentStyle={{ background: "#10161e", border: "1px solid #1f2a36", fontSize: 11, fontFamily: "IBM Plex Mono" }} />
            <ReferenceLine yAxisId="net" y={0} stroke="#6b7888" strokeDasharray="3 3" />
            <Line yAxisId="net" dataKey="net_pct" stroke="#38bdf8" dot={false} strokeWidth={1.5} isAnimationActive={false} name="net %" />
            <Line yAxisId="score" dataKey="overall" stroke="#ffb224" dot={false} strokeWidth={1} isAnimationActive={false} name="safety" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-between text-[9px] font-mono text-[#6b7888] mt-1">
        <span><span className="text-[#38bdf8]">━</span> NET SPREAD % <span className="text-[#ffb224] ml-2">━</span> SAFETY</span>
        {blocked && blocked.evaluations > 0 && (
          <span className="text-[#fbbf24]" data-testid="blocked-opportunity">
            ⚠ {blocked.approx_minutes} min of spread blocked ONLY by deposit gate
          </span>
        )}
      </div>
    </div>
  );
};
