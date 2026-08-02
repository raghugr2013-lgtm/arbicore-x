import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Counter = ({ label, value, color = "#c9d4e0" }) => (
  <div className="border border-[#1f2a36] px-3 py-2">
    <div className="font-mono text-[8px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div className="font-mono text-lg font-bold" style={{ color }}>{value ?? "—"}</div>
  </div>
);

export const ObservationPanel = () => {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/observation/status`).then((r) => setData(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const snapshotNow = async () => {
    setBusy(true);
    try {
      const { data: res } = await axios.post(`${API}/observation/snapshot`);
      toast.success(res.message);
      load();
    } catch (e) {
      toast.error("Snapshot failed");
    }
    setBusy(false);
  };

  const c = data?.counters || {};
  const open = data?.open_episodes || [];

  return (
    <div className="panel" data-testid="observation-panel">
      <div className="panel-title">
        Observation Recorder — evidence accumulation
        <span className="float-right flex items-center gap-2">
          <span className="text-[#3d4a59]">pure data capture · no execution</span>
          <button data-testid="observation-snapshot-btn" onClick={snapshotNow} disabled={busy}
                  className="font-mono text-[9px] font-bold tracking-widest px-2 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 disabled:opacity-50">
            {busy ? "…" : "SNAPSHOT NOW"}
          </button>
        </span>
      </div>
      {!data && <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>}
      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-2" data-testid="observation-counters">
            <Counter label="Readiness snapshots" value={c.readiness_snapshots} color="#38bdf8" />
            <Counter label="Raw episodes" value={c.episodes_raw} color="#38bdf8" />
            <Counter label="Exec episodes" value={c.episodes_exec} color="#34d399" />
            <Counter label="Gate-cost entries" value={c.gate_cost_entries} color="#f87171" />
            <Counter label="Blocked minutes" value={c.blocked_minutes_total} color="#f87171" />
            <Counter label="Missed profit (est)" value={c.missed_profit_total_quote != null ? fmtUsd(c.missed_profit_total_quote) : null} color="#f87171" />
            <Counter label="Calibration pend/res" value={`${c.calibration_pending ?? 0}/${c.calibration_resolved ?? 0}`} color="#ffb224" />
            <Counter label="Survival rate" value={c.calibration_survival_rate_pct != null ? `${c.calibration_survival_rate_pct}%` : null} color="#34d399" />
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-2 font-mono text-[10px]">
            <span className={data.running ? "text-[#34d399]" : "text-[#f87171]"}>
              {data.running ? "● RECORDING" : "○ STOPPED"}
            </span>
            <span className="text-[#6b7888]">
              hourly snapshots · last {data.last_snapshot_at ? fmtTime(data.last_snapshot_at) : "pending (first ~5 min after start)"}
            </span>
            <div className="flex-1" />
            {open.map((e, i) => (
              <span key={i} data-testid={`observation-open-${e.exchange}-${e.kind}`}
                    className={`px-2 py-0.5 border text-[9px] font-bold ${
                      e.kind === "exec" ? "border-[#34d399]/50 text-[#34d399]" : "border-[#38bdf8]/50 text-[#38bdf8]"}`}>
                LIVE {e.kind.toUpperCase()} · {e.exchange.toUpperCase()} · peak {e.peak_net_pct}%
              </span>
            ))}
            {open.length === 0 && <span className="text-[#3d4a59]">no open episodes right now</span>}
          </div>
        </>
      )}
    </div>
  );
};
