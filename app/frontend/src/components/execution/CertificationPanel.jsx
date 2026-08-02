import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const LIMIT_FIELDS = [
  ["max_cycle_usd", "Max cycle size ($)"],
  ["max_purchase_usd", "Max purchase ($)"],
  ["max_daily_volume_usd", "Daily volume cap ($)"],
  ["max_daily_loss_usd", "Max daily loss ($)"],
  ["max_concurrent_cycles", "Max concurrent cycles"],
  ["min_net_spread_pct", "Min net spread (%)"],
];

const KillSwitch = ({ label, value, danger, onToggle, testId }) => (
  <button
    data-testid={testId}
    onClick={() => onToggle(!value)}
    className={`flex items-center justify-between w-full px-3 py-2 border font-mono text-[11px] font-bold tracking-wider transition-colors ${
      value
        ? danger ? "border-[#f87171] text-[#f87171] bg-[#f87171]/10" : "border-[#34d399] text-[#34d399] bg-[#34d399]/10"
        : "border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0]"
    }`}
  >
    <span>{label}</span>
    <span>{value ? "◉ ON" : "○ OFF"}</span>
  </button>
);

export const CertificationPanel = ({ onChanged }) => {
  const [cfg, setCfg] = useState(null);
  const [limits, setLimits] = useState({});

  const load = useCallback(() => {
    axios.get(`${API}/execution/config`).then((r) => {
      setCfg(r.data);
      setLimits(r.data.limits || {});
    }).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const patch = async (body, msg) => {
    try {
      const { data } = await axios.patch(`${API}/execution/config`, body);
      setCfg(data);
      setLimits(data.limits || {});
      toast.success(msg);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    }
  };

  const saveLimits = () => {
    const parsed = {};
    LIMIT_FIELDS.forEach(([k]) => { parsed[k] = parseFloat(limits[k]); });
    patch({ limits: parsed }, "Certification limits saved");
  };

  if (!cfg) return <div className="panel" data-testid="certification-panel"><div className="panel-title">Certification Limits</div><div className="font-mono text-[11px] text-[#6b7888]">loading…</div></div>;

  return (
    <div className="panel" data-testid="certification-panel">
      <div className="panel-title">Certification Limits & Kill Switches</div>

      <div className="space-y-2 mb-3" data-testid="kill-switches">
        <KillSwitch label="Execution enabled (global)" value={cfg.execution_enabled} danger
                    onToggle={(v) => patch({ execution_enabled: v }, `Execution ${v ? "ENABLED (still simulated in E2)" : "disabled"}`)}
                    testId="toggle-execution-enabled" />
        <KillSwitch label="Wallet signing enabled" value={cfg.wallet_enabled} danger
                    onToggle={(v) => patch({ wallet_enabled: v }, `Wallet signing ${v ? "ENABLED (still simulated in E2)" : "disabled"}`)}
                    testId="toggle-wallet-enabled" />
        <KillSwitch label="Hard freeze (→ manual review)" value={cfg.hard_freeze} danger
                    onToggle={(v) => patch({ hard_freeze: v }, `Hard freeze ${v ? "ON" : "OFF"}`)}
                    testId="toggle-hard-freeze" />
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2">
        {LIMIT_FIELDS.map(([k, label]) => (
          <label key={k} className="block">
            <span className="text-[9px] uppercase tracking-widest text-[#6b7888]">{label}</span>
            <input
              data-testid={`limit-${k}`}
              value={limits[k] ?? ""}
              onChange={(e) => setLimits({ ...limits, [k]: e.target.value })}
              className="term-input w-full"
            />
          </label>
        ))}
      </div>
      <button data-testid="save-limits-btn" onClick={saveLimits} className="term-btn-primary w-full">SAVE LIMITS</button>
      <div className="font-mono text-[9px] text-[#3d4a59] mt-2">
        Flags persist as config only — no code acts on them in E2 (everything stays SIMULATED). Live use begins at E3+.
      </div>
    </div>
  );
};
