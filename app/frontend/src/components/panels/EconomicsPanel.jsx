import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtPct, fmtQty, fmtTime, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Stat = ({ label, value, color = "#c9d4e0" }) => (
  <div className="flex justify-between py-0.5">
    <span className="text-[10px] uppercase tracking-wider text-[#6b7888]">{label}</span>
    <span className="font-bold" style={{ color }}>{value}</span>
  </div>
);

export const EconomicsPanel = ({ routeId }) => {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    if (!routeId) return;
    axios.get(`${API}/routes/${routeId}/economics`, { params: { hours } })
      .then((r) => setData(r.data)).catch(() => {});
  }, [routeId, hours]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const raw = data?.raw;
  const ex = data?.executable;
  const gates = Object.entries(data?.gate_blockage || {}).sort((a, b) => b[1] - a[1]);
  const maxGate = gates.length ? gates[0][1] : 0;
  const episodes = data?.recent_episodes || [];

  return (
    <div className="panel" data-testid="economics-panel">
      <div className="panel-title">
        Opportunity Economics — raw spread vs executable
        <span className="float-right flex gap-1">
          {[6, 24, 72].map((h) => (
            <button key={h} data-testid={`economics-range-${h}`} onClick={() => setHours(h)}
                    className={`px-1.5 ${hours === h ? "text-[#ffb224]" : "text-[#6b7888] hover:text-[#c9d4e0]"}`}>
              {h}h
            </button>
          ))}
        </span>
      </div>

      {!data && <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>}
      {data && (
        <div className="font-mono text-xs">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="border border-[#1f2a36] p-2.5" data-testid="economics-raw-col">
              <div className="text-[9px] tracking-widest text-[#38bdf8] mb-1.5">RAW SPREAD OPPORTUNITIES</div>
              <Stat label="Episodes" value={raw.episodes} color="#38bdf8" />
              <Stat label="Total window" value={`${raw.total_minutes}m`} />
              <Stat label="Avg duration" value={`${raw.avg_duration_min}m`} />
              <Stat label="Avg net spread" value={fmtPct(raw.avg_net_pct)} color="#38bdf8" />
              <Stat label="Best net spread" value={fmtPct(raw.best_net_pct)} />
              <Stat label="Avg capacity" value={fmtQty(raw.avg_recommended)} />
              <Stat label="Est. profit (if executable)" value={fmtUsd(raw.est_profit_quote)} color="#38bdf8" />
            </div>
            <div className="border border-[#1f2a36] p-2.5" data-testid="economics-exec-col">
              <div className="text-[9px] tracking-widest text-[#34d399] mb-1.5">EXECUTABLE (ALL GATES PASS)</div>
              <Stat label="Episodes" value={ex.episodes} color="#34d399" />
              <Stat label="Total window" value={`${ex.total_minutes}m`} />
              <Stat label="Avg duration" value={`${ex.avg_duration_min}m`} />
              <Stat label="Avg net spread" value={fmtPct(ex.avg_net_pct)} color="#34d399" />
              <Stat label="Best net spread" value={fmtPct(ex.best_net_pct)} />
              <Stat label="Avg capacity" value={fmtQty(ex.avg_recommended)} />
              <Stat label="Est. capturable profit" value={fmtUsd(ex.est_profit_quote)} color="#34d399" />
            </div>
            <div className="border border-[#1f2a36] p-2.5" data-testid="economics-capture-col">
              <div className="text-[9px] tracking-widest text-[#6b7888] mb-1.5">CAPTURE RATIO</div>
              <div className="text-3xl font-bold mb-1" data-testid="economics-capture-ratio"
                   style={{ color: data.capture_ratio_pct == null ? "#6b7888" : data.capture_ratio_pct >= 50 ? "#34d399" : data.capture_ratio_pct > 0 ? "#fbbf24" : "#f87171" }}>
                {data.capture_ratio_pct != null ? `${data.capture_ratio_pct}%` : "—"}
              </div>
              <div className="text-[10px] text-[#6b7888] mb-2">of raw opportunity minutes were executable</div>
              <div className="text-[9px] tracking-widest text-[#6b7888] mb-1">GATE BLOCKAGE (minutes)</div>
              {gates.length === 0 && <div className="text-[10px] text-[#3d4a59]">no gate blockage in window</div>}
              {gates.map(([g, m]) => (
                <div key={g} className="flex items-center gap-2 py-0.5" data-testid={`economics-gate-${g}`}>
                  <span className="w-24 text-[9px] text-[#f87171]">{g}</span>
                  <div className="flex-1 h-1.5 bg-[#1f2a36]">
                    <div className="h-1.5 bg-[#f87171]" style={{ width: `${maxGate ? (m / maxGate) * 100 : 0}%` }} />
                  </div>
                  <span className="w-12 text-right text-[10px]">{m}m</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-3">
            <div className="text-[9px] tracking-widest text-[#6b7888] mb-1">RECENT RAW EPISODES</div>
            {episodes.length === 0 && <div className="text-[10px] text-[#3d4a59]">no spread episodes above {data.min_net_spread_pct}% in window</div>}
            {episodes.length > 0 && (
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="panel-th">
                    <th className="text-left">Start</th><th className="text-right">Duration</th>
                    <th className="text-right">Avg net</th><th className="text-right">Peak net</th>
                    <th className="text-right">Capacity</th><th className="text-right">Est. profit</th>
                    <th className="text-right">Executable</th>
                  </tr>
                </thead>
                <tbody>
                  {episodes.map((e, i) => (
                    <tr key={i} className="border-b border-[#1f2a36]/40">
                      <td className="py-1">{fmtTime(e.start)}</td>
                      <td className="text-right">{e.duration_min}m</td>
                      <td className="text-right text-[#38bdf8]">{fmtPct(e.avg_net_pct)}</td>
                      <td className="text-right">{fmtPct(e.peak_net_pct)}</td>
                      <td className="text-right text-[#ffb224]">{fmtQty(e.avg_recommended)}</td>
                      <td className="text-right">{fmtUsd(e.est_profit_quote)}</td>
                      <td className="text-right">
                        {e.had_go
                          ? <span className="text-[#34d399] font-bold">YES</span>
                          : <span className="text-[#f87171]">blocked</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
