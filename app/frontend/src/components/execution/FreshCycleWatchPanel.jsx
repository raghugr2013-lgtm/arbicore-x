import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATE_C = {
  ARMED: "#34d399",
  PARTIAL: "#ffb224",
  DORMANT: "#f87171",
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

export const FreshCycleWatchPanel = () => {
  const [w, setW] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/fresh-cycle/watch`).then((r) => setW(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  if (!w) {
    return (
      <div className="panel" data-testid="fresh-cycle-watch-panel">
        <div className="panel-title">Fresh-Cycle Watch (Telegram framework, DORMANT)</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
      </div>
    );
  }

  const state = w.credential_state || "DORMANT";
  const sc = STATE_C[state] || "#6b7888";
  const evidenceDays = 30;

  return (
    <div className="panel" data-testid="fresh-cycle-watch-panel">
      <div className="panel-title">
        Fresh-Cycle Watch — Telegram alert framework
        <span className="float-right text-[#3d4a59]">read-only · outbound-only</span>
      </div>

      {/* state banner */}
      <div className="border p-3 mb-3" style={{ borderColor: sc + "66", background: sc + "12" }} data-testid="fresh-cycle-watch-state">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase">Watcher state</div>
            <div data-testid="watch-state" className="font-mono text-2xl font-bold" style={{ color: sc }}>{state}</div>
          </div>
          <div className="font-mono text-[10px] text-[#c9d4e0] max-w-[640px] flex-1">
            {w.credential_state_label}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-[10px] font-mono">
          <div data-testid="watch-token-set">
            <div className="text-[8px] text-[#6b7888] tracking-widest uppercase">Bot Token</div>
            <div className="font-bold" style={{ color: w.token_set ? "#34d399" : "#f87171" }}>
              {w.token_set ? `SET · ${w.token_mask || ""}` : "NOT SET"}
            </div>
          </div>
          <div data-testid="watch-chat-set">
            <div className="text-[8px] text-[#6b7888] tracking-widest uppercase">Chat ID</div>
            <div className="font-bold" style={{ color: w.chat_id_set ? "#34d399" : "#f87171" }}>
              {w.chat_id_set ? "SET" : "NOT SET"}
            </div>
          </div>
          <div>
            <div className="text-[8px] text-[#6b7888] tracking-widest uppercase">Alerts Enabled</div>
            <div className="font-bold" style={{ color: w.alerts_enabled ? "#34d399" : "#6b7888" }}>
              {w.alerts_enabled ? "YES" : "NO"}
            </div>
          </div>
          <div>
            <div className="text-[8px] text-[#6b7888] tracking-widest uppercase">Cooldown / Min ROI floor</div>
            <div className="font-bold text-[#c9d4e0]">
              {w.rules?.cooldown_s ?? "—"}s · {w.rules?.min_net_spread_pct ?? "—"}%
            </div>
          </div>
        </div>
      </div>

      {/* alert kinds */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="watch-alert-kinds">
        <div className="font-mono text-[9px] text-[#6b7888] tracking-wider mb-1">ALERT KINDS — fire only when ARMED</div>
        <div className="overflow-x-auto">
          <table className="w-full text-[10px] font-mono">
            <thead>
              <tr className="panel-th text-[#6b7888]">
                <th className="text-left">Kind</th>
                <th className="text-left">Label</th>
                <th className="text-left">Trigger</th>
                <th className="text-center">Enabled</th>
              </tr>
            </thead>
            <tbody>
              {(w.alert_kinds || []).map((k) => (
                <tr key={k.key} className="border-b border-[#1f2a36]/50" data-testid={`watch-kind-${k.key}`}>
                  <td className="py-1 pr-2 text-[#c9d4e0] font-bold">{k.key}</td>
                  <td className="py-1 pr-2 text-[#8b97a6]">{k.label}</td>
                  <td className="py-1 pr-2 text-[#6b7888]">{k.trigger}</td>
                  <td className="py-1 text-center" style={{ color: k.enabled ? "#34d399" : "#f87171" }}>{k.enabled ? "✓" : "✗"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* recent alerts log */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="watch-recent-alerts">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[9px] text-[#6b7888] tracking-wider">RECENT ALERT EVENTS ({w.recent_count || 0})</span>
        </div>
        {(w.recent_alerts || []).length === 0 ? (
          <div className="font-mono text-[10px] text-[#3d4a59] py-3 text-center">
            No alert events recorded yet — watcher is dormant.
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[260px] overflow-y-auto">
            <table className="w-full text-[9px] font-mono">
              <thead>
                <tr className="panel-th text-[#6b7888]">
                  <th className="text-left">Time</th>
                  <th className="text-left">Kind</th>
                  <th className="text-left">Status</th>
                  <th className="text-left">Message</th>
                </tr>
              </thead>
              <tbody>
                {(w.recent_alerts || []).map((a, i) => (
                  <tr key={i} className="border-b border-[#1f2a36]/50">
                    <td className="py-1 text-[#6b7888]">{fmtTime(a.ts)}</td>
                    <td className="py-1 text-[#c9d4e0]">{a.kind}</td>
                    <td className="py-1" style={{ color: a.status === "sent" ? "#34d399" : "#f87171" }}>{a.status}</td>
                    <td className="py-1 text-[#6b7888] truncate max-w-[420px]">{a.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2" data-testid="watch-evidence-downloads">
        <span className="font-mono text-[9px] text-[#6b7888] tracking-wider self-center mr-2">FINAL EVIDENCE REPORT (bundle):</span>
        <button data-testid="evidence-report-download-md"
                onClick={() => download(`/execution/evidence-report/download?format=md&days=${evidenceDays}`, `evidence_report_${evidenceDays}d.md`)}
                className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 font-mono text-[10px] font-bold tracking-wider">
          ↓ EVIDENCE REPORT (MD)
        </button>
        <button data-testid="evidence-report-download-json"
                onClick={() => download(`/execution/evidence-report/download?format=json&days=${evidenceDays}`, `evidence_report_${evidenceDays}d.json`)}
                className="px-3 py-1 border border-[#a78bfa] text-[#a78bfa] hover:bg-[#a78bfa]/10 font-mono text-[10px] font-bold tracking-wider">
          ↓ EVIDENCE REPORT (JSON)
        </button>
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        {w.note}
      </div>
    </div>
  );
};
