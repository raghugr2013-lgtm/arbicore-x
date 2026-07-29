import { useCallback, useEffect, useState, Fragment } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtUsd, fmtPrice, fmtPct, fmtTime, pctClass } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const download = async (format, setBusy) => {
  setBusy(format);
  try {
    const r = await axios.get(`${API}/execution/ledger/permanent/export`, {
      params: { format }, responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([r.data]));
    const a = document.createElement("a");
    a.href = url;
    a.download = `production_ledger.${format === "xlsx" ? "xlsx" : format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch {
    toast.error("Export failed");
  } finally {
    setBusy(null);
  }
};

export const PermanentLedgerPanel = () => {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);
  const [open, setOpen] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/ledger/permanent`).then((r) => setData(r.data)).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const refreeze = async () => {
    setBusy("backfill");
    try {
      const r = await axios.post(`${API}/execution/ledger/permanent/backfill`);
      toast.success(`Froze ${r.data.newly_frozen} new cycle(s)`);
      load();
    } catch {
      toast.error("Backfill failed");
    } finally {
      setBusy(null);
    }
  };

  if (!data) {
    return (
      <div className="panel" data-testid="permanent-ledger-panel">
        <div className="panel-title">Permanent Institutional Ledger</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center">loading ledger…</div>
      </div>
    );
  }

  const s = data.summary;
  const tiles = [
    ["CYCLES", s.cycles, "#38bdf8"],
    ["TOTAL CAPITAL", fmtUsd(s.total_initial_capital_usd), "#c9d4e0"],
    ["NET PROFIT", fmtUsd(s.total_net_profit_usd), "#34d399"],
    ["OVERALL ROI", fmtPct(s.overall_roi_pct), "#34d399"],
    ["WIN RATE", `${s.win_rate_pct ?? "—"}%`, "#34d399"],
    ["TOTAL FEES", fmtUsd(s.total_fees_usd), "#f87171"],
    ["AVG / CYCLE", fmtUsd(s.avg_net_per_cycle_usd), "#ffb224"],
  ];

  return (
    <div className="panel" data-testid="permanent-ledger-panel">
      <div className="panel-title">
        Permanent Institutional Ledger
        <span className="float-right text-[#3d4a59]">immutable · append-only</span>
      </div>

      <div className="flex flex-wrap gap-2 mb-3" data-testid="permanent-ledger-summary">
        {tiles.map(([k, v, c]) => (
          <div key={k} className="border border-[#1f2a36] bg-[#0a0e13] px-3 py-1.5">
            <div className="font-mono text-[8px] text-[#6b7888] tracking-wider">{k}</div>
            <div className="font-mono text-sm font-bold" style={{ color: c }}>{v}</div>
          </div>
        ))}
        <div className="flex-1" />
        <div className="flex items-end gap-1.5">
          <button data-testid="ledger-export-xlsx" onClick={() => download("xlsx", setBusy)} disabled={busy === "xlsx"}
                  className="px-2 py-1.5 border border-[#34d399] text-[#34d399] font-mono text-[9px] font-bold hover:bg-[#34d399]/10">
            ↓ XLSX
          </button>
          <button data-testid="ledger-export-csv" onClick={() => download("csv", setBusy)} disabled={busy === "csv"}
                  className="px-2 py-1.5 border border-[#38bdf8] text-[#38bdf8] font-mono text-[9px] font-bold hover:bg-[#38bdf8]/10">
            ↓ CSV
          </button>
          <button data-testid="ledger-export-json" onClick={() => download("json", setBusy)} disabled={busy === "json"}
                  className="px-2 py-1.5 border border-[#1f2a36] text-[#8b97a6] font-mono text-[9px] font-bold hover:bg-[#1f2a36]">
            ↓ JSON
          </button>
          <button data-testid="ledger-refreeze" onClick={refreeze} disabled={busy === "backfill"}
                  className="px-2 py-1.5 border border-[#1f2a36] text-[#6b7888] font-mono text-[9px] font-bold hover:bg-[#1f2a36]">
            ⟳ FREEZE NEW
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[9px] font-mono" data-testid="permanent-ledger-table">
          <thead>
            <tr className="panel-th text-[#6b7888]">
              <th className="text-left">Cycle</th>
              <th className="text-left">Completed</th>
              <th className="text-left">Venue</th>
              <th className="text-right">Capital</th>
              <th className="text-right">Buy Px</th>
              <th className="text-right">Sell VWAP</th>
              <th className="text-right">Fills</th>
              <th className="text-right">Fees</th>
              <th className="text-right">Net</th>
              <th className="text-right">ROI</th>
              <th className="text-center"></th>
            </tr>
          </thead>
          <tbody>
            {data.entries.map((e) => {
              const fees = (e.gas_fee_usd || 0) + (e.trading_fee_usd || 0) + (e.withdrawal_fee_usd || 0);
              const isOpen = open === e.cycle_id;
              return (
                <Fragment key={e.cycle_id}>
                  <tr className="border-b border-[#1f2a36]/50 cursor-pointer hover:bg-[#0a0e13]"
                      data-testid={`ledger-row-${e.cycle_id.slice(0, 8)}`} onClick={() => setOpen(isOpen ? null : e.cycle_id)}>
                    <td className="py-1.5 text-[#38bdf8]">{e.cycle_id.slice(0, 8)}</td>
                    <td className="py-1.5 text-[#6b7888]">{fmtTime(e.completed_at)}</td>
                    <td className="py-1.5 text-[#8b97a6]">{(e.sell_venue || "—").toUpperCase()}</td>
                    <td className="py-1.5 text-right">{fmtUsd(e.initial_capital_usd)}</td>
                    <td className="py-1.5 text-right">{fmtPrice(e.portal_buy_price)}</td>
                    <td className="py-1.5 text-right">{fmtPrice(e.weighted_sell_price)}</td>
                    <td className="py-1.5 text-right text-[#6b7888]">{e.fill_levels}</td>
                    <td className="py-1.5 text-right text-[#f87171]">{fmtUsd(fees)}</td>
                    <td className="py-1.5 text-right text-[#34d399] font-bold">{fmtUsd(e.net_profit_usd)}</td>
                    <td className={`py-1.5 text-right font-bold ${pctClass(e.roi_pct)}`}>{fmtPct(e.roi_pct)}</td>
                    <td className="py-1.5 text-center text-[#3d4a59]">{isOpen ? "▾" : "▸"}</td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-[#0a0e13]" data-testid={`ledger-lifecycle-${e.cycle_id.slice(0, 8)}`}>
                      <td colSpan={11} className="px-2 py-2">
                        <div className="text-[8px] text-[#6b7888] tracking-wider mb-1">CYCLE LIFECYCLE — {e.cycle_id} (frozen {fmtTime(e.frozen_at)} · {e.fills_source})</div>
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-1">
                          {(e.lifecycle || []).map((l, i) => (
                            <div key={i} className="border border-[#1f2a36] px-2 py-1">
                              <div className="text-[9px] font-bold text-[#c9d4e0]">{l.stage}</div>
                              <div className="text-[8px] text-[#6b7888]">{fmtTime(l.timestamp)} · {l.state}</div>
                              <div className="text-[8px] text-[#38bdf8] truncate">tx: {l.tx_hash || "—"}</div>
                              <div className="text-[8px] text-[#5a6573]">{l.fund_location}</div>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        Each entry is a permanent, immutable record frozen at cycle completion — never overwritten. Sell fills
        are modeled (shadow). No fund movement.
      </div>
    </div>
  );
};
