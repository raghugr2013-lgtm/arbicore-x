import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtQty, fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const Gate = ({ enabled }) => (
  enabled === true ? <span className="text-[#34d399] font-bold">OPEN</span>
  : enabled === false ? <span className="text-[#f87171] font-bold">CLOSED</span>
  : <span className="text-[#6b7888]">unknown</span>
);

export const CapabilityPanel = ({ asset = "BDAG" }) => {
  const [caps, setCaps] = useState([]);
  const [history, setHistory] = useState([]);

  const load = useCallback(() => {
    axios.get(`${API}/capabilities`, { params: { currency: asset } }).then((r) => setCaps(r.data)).catch(() => {});
    axios.get(`${API}/capabilities/history`, { params: { limit: 12 } }).then((r) => setHistory(r.data)).catch(() => {});
  }, [asset]);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="panel" data-testid="capability-panel">
      <div className="panel-title">Capability Registry — {asset} transfer gates (persisted)</div>
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="panel-th">
            <th className="text-left">Venue</th><th className="text-center">Deposit</th>
            <th className="text-center">Withdraw</th><th className="text-right">W/D fee</th>
            <th className="text-right">W/D min</th><th className="text-right">Since change</th>
          </tr>
        </thead>
        <tbody>
          {caps.length === 0 && (
            <tr><td colSpan={6} className="py-2 text-[#6b7888]">collecting capability snapshots…</td></tr>
          )}
          {caps.map((c) => (
            <tr key={c.id} className="border-b border-[#1f2a36]/50" data-testid={`capability-row-${c.exchange}`}>
              <td className="py-1.5 uppercase font-bold">{c.exchange}</td>
              <td className="text-center"><Gate enabled={c.deposit_enabled} /></td>
              <td className="text-center"><Gate enabled={c.withdraw_enabled} /></td>
              <td className="text-right text-[#6b7888]">{c.withdraw_fee != null ? fmtQty(Number(c.withdraw_fee)) : "—"}</td>
              <td className="text-right text-[#6b7888]">{c.withdraw_min != null ? fmtQty(Number(c.withdraw_min)) : "—"}</td>
              <td className="text-right text-[10px] text-[#6b7888]">{c.last_changed ? fmtTime(c.last_changed) : "stable"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3">
        <div className="text-[9px] font-mono uppercase tracking-widest text-[#6b7888] mb-1">Flip history</div>
        <div className="max-h-28 overflow-y-auto" data-testid="capability-history">
          {history.length === 0 && <div className="font-mono text-[10px] text-[#3d4a59]">no gate flips recorded yet — history persists from now on</div>}
          {history.map((h) => (
            <div key={h.id} className="font-mono text-[10px] py-0.5 border-b border-[#1f2a36]/40">
              <span className="text-[#6b7888]">{fmtTime(h.ts)}</span>{" "}
              <span className="text-[#ffb224] uppercase font-bold">{h.exchange}</span>{" "}
              <span className="text-[#c9d4e0]">{h.currency} {h.field.replace("_enabled", "")}</span>{" "}
              <span className={h.to ? "text-[#34d399]" : "text-[#f87171]"}>
                {String(h.from)} → {String(h.to)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
