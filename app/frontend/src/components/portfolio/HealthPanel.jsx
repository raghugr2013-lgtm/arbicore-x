const scoreColor = (v) => (v == null ? "#6b7888" : v >= 80 ? "#34d399" : v >= 50 ? "#fbbf24" : "#f87171");

const Pct = ({ v }) => (
  <span style={{ color: scoreColor(v) }}>{v != null ? `${v}%` : "—"}</span>
);

export const HealthPanel = ({ data }) => {
  const rows = data?.exchanges || [];
  return (
    <div className="panel" data-testid="health-panel">
      <div className="panel-title">Exchange Health Analytics — {data?.hours || 24}h window</div>
      <table className="w-full text-[10px] font-mono">
        <thead>
          <tr className="panel-th">
            <th className="text-left">Venue</th>
            <th className="text-right">API uptime</th>
            <th className="text-right">Latency</th>
            <th className="text-right">Deposit up</th>
            <th className="text-right">Withdraw up</th>
            <th className="text-right">Gate open avg</th>
            <th className="text-right">Flips/day</th>
            <th className="text-right">Reliability</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr key={h.exchange} className="border-b border-[#1f2a36]/40" data-testid={`health-row-${h.exchange}`}>
              <td className="py-1.5 font-bold uppercase">
                {h.exchange}
                {h.ws_mode === "ws" && <span className="ml-1 text-[8px] text-[#34d399]">WS</span>}
              </td>
              <td className="text-right"><Pct v={h.api_uptime_pct} /></td>
              <td className="text-right text-[#6b7888]">{h.avg_latency_ms != null ? `${h.avg_latency_ms}ms` : "—"}</td>
              <td className="text-right"><Pct v={h.deposit_uptime_pct} /></td>
              <td className="text-right"><Pct v={h.withdraw_uptime_pct} /></td>
              <td className="text-right text-[#6b7888]">
                {h.avg_gate_open_min != null ? (h.avg_gate_open_min >= 60 ? `${(h.avg_gate_open_min / 60).toFixed(1)}h` : `${h.avg_gate_open_min}m`) : "—"}
              </td>
              <td className="text-right" style={{ color: h.flips_per_day > 2 ? "#f87171" : "#c9d4e0" }}>{h.flips_per_day}</td>
              <td className="text-right font-bold" data-testid={`health-reliability-${h.exchange}`}>
                <Pct v={h.reliability_score} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="font-mono text-[9px] text-[#3d4a59] mt-2">
        API uptime from live request telemetry (5-min buckets) · gate uptime from fee snapshots · reliability = 35% API + 25% deposit + 20% withdraw + 20% gate stability
      </div>
    </div>
  );
};
