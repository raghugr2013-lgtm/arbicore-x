import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Stat = ({ label, value, color, testId }) => (
  <div className="bg-[#0a0e13] border border-[#1f2a36] px-2 py-1.5 text-center">
    <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div data-testid={testId} className="font-mono text-sm font-bold" style={color ? { color } : {}}>{value}</div>
  </div>
);

export const ShadowModePanel = ({ onChanged }) => {
  const [s, setS] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/shadow/status`).then((r) => setS(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const toggle = async (v) => {
    try {
      await axios.patch(`${API}/execution/config`, { shadow_enabled: v });
      toast.success(`Shadow mode ${v ? "ENABLED — running off live data (non-executing)" : "disabled"}`);
      load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Toggle failed");
    }
  };

  if (!s) return <div className="panel" data-testid="shadow-mode-panel"><div className="panel-title">Shadow Mode (E3)</div><div className="font-mono text-[11px] text-[#6b7888]">loading…</div></div>;

  const cyc = s.shadow_cycles || {};
  const pnl = s.shadow_pnl || {};
  const variance = (pnl.realized_total_quote ?? 0) - (pnl.expected_total_quote ?? 0);

  return (
    <div className="panel" data-testid="shadow-mode-panel">
      <div className="panel-title">
        Shadow Mode (E3) — live data, non-executing
        <span className="float-right" style={{ color: s.running ? "#34d399" : "#6b7888" }}>
          {s.running ? "● runner up" : "○ runner down"}
        </span>
      </div>

      <button
        data-testid="toggle-shadow-enabled"
        onClick={() => toggle(!s.enabled)}
        className={`flex items-center justify-between w-full px-3 py-2 border font-mono text-[11px] font-bold tracking-wider transition-colors mb-3 ${
          s.enabled ? "border-[#38bdf8] text-[#38bdf8] bg-[#38bdf8]/10" : "border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0]"
        }`}
      >
        <span>SHADOW RUNNER {s.enabled ? "ENABLED" : "DISABLED"}</span>
        <span>{s.enabled ? "◉ ON" : "○ OFF"}</span>
      </button>

      <div className="grid grid-cols-4 gap-2 mb-2">
        <Stat label="Total" value={cyc.total ?? 0} color="#c9d4e0" testId="shadow-total" />
        <Stat label="Open" value={cyc.open ?? 0} color="#38bdf8" testId="shadow-open" />
        <Stat label="Stuck" value={cyc.stuck ?? 0} color="#f87171" testId="shadow-stuck" />
        <Stat label="Complete" value={cyc.complete ?? 0} color="#34d399" testId="shadow-complete" />
      </div>
      <div className="grid grid-cols-3 gap-2 mb-2">
        <Stat label="Expected PnL" value={fmtUsd(pnl.expected_total_quote)} color="#ffb224" testId="shadow-expected-pnl" />
        <Stat label="Realized (shadow)" value={fmtUsd(pnl.realized_total_quote)} color="#34d399" testId="shadow-realized-pnl" />
        <Stat label="Variance" value={fmtUsd(variance)} color={variance >= 0 ? "#34d399" : "#f87171"} testId="shadow-variance" />
      </div>
      <div className="font-mono text-[9px] text-[#3d4a59]">
        ticks {s.ticks} · every {s.tick_interval_s}s · last {s.last_tick ? fmtTime(s.last_tick) : "—"}<br />
        {s.note}
      </div>
    </div>
  );
};
