import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/context/AuthContext";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const RULES = [
  ["verdict_flip", "Verdict flips (GO/WAIT/NO_GO transitions)"],
  ["capability_flip", "Capability flips (deposit/withdraw gates)"],
  ["go_opportunity", "GO opportunities above spread threshold"],
];

export const TelegramSection = () => {
  const [settings, setSettings] = useState(null);
  const [token, setToken] = useState("");
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/alerts/settings`).then((r) => setSettings(r.data)).catch(() => {});
    axios.get(`${API}/alerts/log?limit=20`).then((r) => setLog(r.data)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  if (!settings) return <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>;

  const save = async () => {
    setBusy(true);
    try {
      const { data } = await axios.put(`${API}/alerts/settings`, {
        enabled: settings.enabled,
        chat_id: settings.chat_id,
        rules: settings.rules,
        bot_token: token || undefined,
      });
      setSettings(data);
      setToken("");
      toast.success("Alert settings saved");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    }
    setBusy(false);
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const { data } = await axios.post(`${API}/alerts/test`);
      data.ok ? toast.success(data.message) : toast.error(data.message);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    }
    setTesting(false);
  };

  const setRule = (k, v) => setSettings({ ...settings, rules: { ...settings.rules, [k]: v } });

  return (
    <div className="space-y-4" data-testid="telegram-section">
      {!settings.enabled && (
        <div className="border border-[#38bdf8]/40 bg-[#38bdf8]/5 px-3 py-2 font-mono text-[11px] text-[#38bdf8]" data-testid="telegram-dormant-banner">
          DORMANT — alerting is fully wired but inactive until you enable it and provide a Bot Token (@BotFather) + Chat ID.
        </div>
      )}

      <div className="panel">
        <div className="panel-title">Telegram channel</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">
              Bot token {settings.token_set && <span className="text-[#34d399]">(set: {settings.token_mask})</span>}
            </label>
            <input data-testid="telegram-token-input" type="password" value={token} onChange={(e) => setToken(e.target.value)}
                   placeholder={settings.token_set ? "leave blank to keep current token" : "123456:ABC-DEF…"}
                   autoComplete="off"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Chat ID</label>
            <input data-testid="telegram-chatid-input" value={settings.chat_id}
                   onChange={(e) => setSettings({ ...settings, chat_id: e.target.value })}
                   placeholder="-100123456789 or @channel"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
        </div>

        <div className="mt-4">
          <div className="font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-2">Alert rules</div>
          {RULES.map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 font-mono text-[11px] text-[#c9d4e0] py-1 cursor-pointer">
              <input data-testid={`telegram-rule-${k}`} type="checkbox" checked={settings.rules[k] !== false}
                     onChange={(e) => setRule(k, e.target.checked)} className="accent-[#ffb224]" />
              {label}
            </label>
          ))}
          <div className="flex flex-wrap gap-4 mt-2">
            <label className="font-mono text-[11px] text-[#6b7888]">
              Min net spread for GO alerts (%){" "}
              <input data-testid="telegram-minspread-input" type="number" step="0.1" value={settings.rules.min_net_spread_pct}
                     onChange={(e) => setRule("min_net_spread_pct", parseFloat(e.target.value) || 0)}
                     className="w-20 ml-1 bg-[#0a0f14] border border-[#1f2a36] px-2 py-1 text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
            </label>
            <label className="font-mono text-[11px] text-[#6b7888]">
              Cooldown per alert type (s){" "}
              <input data-testid="telegram-cooldown-input" type="number" step="10" value={settings.rules.cooldown_s}
                     onChange={(e) => setRule("cooldown_s", parseInt(e.target.value, 10) || 0)}
                     className="w-20 ml-1 bg-[#0a0f14] border border-[#1f2a36] px-2 py-1 text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
            </label>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 mt-4">
          <button data-testid="telegram-enabled-toggle" onClick={() => setSettings({ ...settings, enabled: !settings.enabled })}
                  className={`font-mono text-[10px] font-bold tracking-widest px-3 py-1.5 border ${
                    settings.enabled ? "border-[#34d399] text-[#34d399] bg-[#34d399]/10"
                                     : "border-[#6b7888] text-[#6b7888]"}`}>
            {settings.enabled ? "◉ ENABLED" : "○ DISABLED (dormant)"}
          </button>
          <button data-testid="telegram-save-btn" onClick={save} disabled={busy}
                  className="font-mono text-[10px] font-bold tracking-widest px-3 py-1.5 border border-[#ffb224] text-[#ffb224] bg-[#ffb224]/10 hover:bg-[#ffb224]/20 disabled:opacity-50">
            {busy ? "SAVING…" : "SAVE SETTINGS"}
          </button>
          <button data-testid="telegram-test-btn" onClick={sendTest} disabled={testing}
                  className="font-mono text-[10px] font-bold tracking-widest px-3 py-1.5 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 disabled:opacity-50">
            {testing ? "SENDING…" : "SEND TEST MESSAGE"}
          </button>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Alert log (last 20)</div>
        {log.length === 0 && <div className="font-mono text-[11px] text-[#6b7888] py-1">no alerts sent yet</div>}
        {log.map((a) => (
          <div key={a.id} className="font-mono text-[10px] py-1 border-b border-[#1f2a36]/40">
            <span className="text-[#6b7888]">{fmtTime(a.ts)}</span>{" "}
            <span className={a.status === "sent" ? "text-[#34d399]" : "text-[#f87171]"}>[{a.kind}:{a.status}]</span>{" "}
            <span className="text-[#c9d4e0]">{a.message}</span>
            {a.error && <span className="text-[#f87171]"> — {a.error}</span>}
          </div>
        ))}
      </div>
    </div>
  );
};
