import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const usd = (v) => (v == null ? "—" : `$${Number(v).toFixed(2)}`);
const TABS = ["cycles", "daily", "weekly", "monthly"];

const Tile = ({ label, value, color, testId }) => (
  <div className="bg-[#0a0e13] border border-[#1f2a36] px-2 py-1.5 text-center">
    <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">{label}</div>
    <div data-testid={testId} className="font-mono text-sm font-bold" style={color ? { color } : {}}>{value}</div>
  </div>
);

export const LedgerPanel = () => {
  const [d, setD] = useState(null);
  const [tab, setTab] = useState("cycles");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    axios.get(`${API}/execution/ledger`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  const download = async (fmt) => {
    setBusy(true);
    try {
      const r = await axios.get(`${API}/execution/ledger/export`, { params: { format: fmt }, responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url; a.download = `production_ledger.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      toast.success(`Ledger exported (${fmt.toUpperCase()})`);
    } catch (e) { toast.error("Export failed"); } finally { setBusy(false); }
  };

  if (!d) return <div className="panel" data-testid="ledger-panel"><div className="panel-title">Production Ledger</div><div className="font-mono text-[11px] text-[#6b7888]">loading…</div></div>;
  const s = d.summary;
  const agg = { daily: d.daily_pnl, weekly: d.weekly_pnl, monthly: d.monthly_pnl };

  return (
    <div className="panel" data-testid="ledger-panel">
      <div className="panel-title flex items-center gap-2 flex-wrap">
        <span>Production Ledger & Profit Accounting (E4.6)</span>
        <div className="flex-1" />
        <button data-testid="ledger-export-csv" disabled={busy} onClick={() => download("csv")} className="px-2 py-0.5 border border-[#1f2a36] text-[#8b97a6] hover:text-[#c9d4e0] font-mono text-[10px]">↓ CSV</button>
        <button data-testid="ledger-export-json" disabled={busy} onClick={() => download("json")} className="px-2 py-0.5 border border-[#1f2a36] text-[#8b97a6] hover:text-[#c9d4e0] font-mono text-[10px]">↓ JSON</button>
      </div>

      <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-3">
        <Tile label="Cycles" value={s.cycles} color="#c9d4e0" testId="ledger-cycles" />
        <Tile label="Total net" value={usd(s.total_net_profit_usd)} color="#34d399" testId="ledger-net" />
        <Tile label="Invested" value={usd(s.total_investment_usd)} color="#38bdf8" />
        <Tile label="Overall ROI" value={s.overall_roi_pct != null ? `${s.overall_roi_pct}%` : "—"} color="#34d399" />
        <Tile label="Total fees" value={usd(s.total_fees_usd)} color="#ffb224" />
        <Tile label="Avg/cycle" value={usd(s.avg_net_per_cycle_usd)} color="#34d399" />
      </div>

      <div className="flex gap-1 mb-2" data-testid="ledger-tabs">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)} data-testid={`ledger-tab-${t}`}
            className={`px-2 py-1 border font-mono text-[10px] uppercase ${tab === t ? "border-[#38bdf8] text-[#38bdf8]" : "border-[#1f2a36] text-[#6b7888]"}`}>{t}</button>
        ))}
      </div>

      <div className="overflow-x-auto">
        {tab === "cycles" ? (
          <table className="w-full text-[9px] font-mono" data-testid="ledger-cycles-table">
            <thead><tr className="panel-th"><th className="text-left">Cycle</th><th>Venue</th><th className="text-right">Invest</th><th className="text-right">Buy px</th><th className="text-right">Sell VWAP</th><th className="text-right">Fills</th><th className="text-right">Trade fee</th><th className="text-right">Wd fee</th><th className="text-right">Net</th><th className="text-right">ROI</th><th>Fills src</th></tr></thead>
            <tbody>
              {d.entries.map((e) => (
                <tr key={e.cycle_id} className="border-b border-[#1f2a36]/50">
                  <td className="py-0.5">{e.cycle_id.slice(0, 8)}</td>
                  <td className="py-0.5 text-center">{(e.sell_venue || "—").toUpperCase()}</td>
                  <td className="py-0.5 text-right">{usd(e.investment_usd)}</td>
                  <td className="py-0.5 text-right">{e.portal_buy_price != null ? Number(e.portal_buy_price).toPrecision(4) : "—"}</td>
                  <td className="py-0.5 text-right">{e.weighted_sell_price != null ? Number(e.weighted_sell_price).toPrecision(4) : "—"}</td>
                  <td className="py-0.5 text-right">{e.fill_levels}</td>
                  <td className="py-0.5 text-right text-[#ffb224]">{usd(e.trading_fee_usd)}</td>
                  <td className="py-0.5 text-right text-[#ffb224]">{usd(e.withdrawal_fee_usd)}</td>
                  <td className="py-0.5 text-right font-bold" style={{ color: (e.net_profit_usd ?? 0) >= 0 ? "#34d399" : "#f87171" }}>{usd(e.net_profit_usd)}</td>
                  <td className="py-0.5 text-right" style={{ color: (e.roi_pct ?? 0) >= 0 ? "#34d399" : "#f87171" }}>{e.roi_pct}%</td>
                  <td className="py-0.5 text-center text-[8px] text-[#6b7888]">{e.fills_source === "modeled_live_book" ? "live" : "spread"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-[10px] font-mono" data-testid={`ledger-${tab}-table`}>
            <thead><tr className="panel-th"><th className="text-left">Period</th><th className="text-right">Cycles</th><th className="text-right">Invested</th><th className="text-right">Net profit</th><th className="text-right">ROI</th></tr></thead>
            <tbody>
              {(agg[tab] || []).map((r) => (
                <tr key={r.period} className="border-b border-[#1f2a36]/50">
                  <td className="py-0.5">{r.period}</td>
                  <td className="py-0.5 text-right">{r.cycles}</td>
                  <td className="py-0.5 text-right">{usd(r.investment_usd)}</td>
                  <td className="py-0.5 text-right font-bold" style={{ color: r.net_profit_usd >= 0 ? "#34d399" : "#f87171" }}>{usd(r.net_profit_usd)}</td>
                  <td className="py-0.5 text-right" style={{ color: r.roi_pct >= 0 ? "#34d399" : "#f87171" }}>{r.roi_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">{d.note}</div>
    </div>
  );
};
