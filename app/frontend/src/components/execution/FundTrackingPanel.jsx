import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { CycleTimelineDialog } from "@/components/execution/CycleTimelineDialog";
import { fmtPct, fmtQty, fmtTime, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const stateColor = (s) => {
  if (!s) return "#6b7888";
  if (s === "COMPLETE") return "#34d399";
  if (s === "ABORTED") return "#6b7888";
  if (s.startsWith("STUCK_") || s === "MANUAL_REVIEW") return "#f87171";
  if (s.startsWith("WAITING")) return "#fbbf24";
  return "#38bdf8";
};

const LEDGER_LABELS = {
  purchase_order: "Purchase order", payment_tx: "Payment tx", bdag_receipt: "BDAG receipt",
  transfer_tx: "Transfer tx", exchange_deposit: "Exchange deposit", exchange_balance: "Exchange balance",
  sell_order: "Sell order", usdt_balance: "USDT balance", withdrawal: "Withdrawal", wallet_receipt: "Wallet receipt",
};

export const FundTrackingPanel = ({ status, onChanged }) => {
  const [routes, setRoutes] = useState([]);
  const [fundingAssets, setFundingAssets] = useState(["USDT", "BNB", "ETH"]);
  const [stateFlow, setStateFlow] = useState([]);
  const [cycles, setCycles] = useState([]);
  const [form, setForm] = useState({ route_id: "", size_usd: 25, funding_asset: "USDT" });
  const [selected, setSelected] = useState(null);
  const [audit, setAudit] = useState([]);
  const [timelineId, setTimelineId] = useState(null);

  const loadCycles = useCallback(() => {
    axios.get(`${API}/execution/cycles`).then((r) => setCycles(r.data.cycles || [])).catch(() => {});
  }, []);

  const loadDetail = useCallback((id) => {
    axios.get(`${API}/execution/cycles/${id}`).then((r) => setSelected(r.data)).catch(() => {});
    axios.get(`${API}/execution/cycles/${id}/audit`).then((r) => setAudit(r.data.trail || [])).catch(() => {});
  }, []);

  useEffect(() => {
    axios.get(`${API}/routes`).then((r) => {
      setRoutes(r.data || []);
      if (r.data?.length) setForm((f) => ({ ...f, route_id: r.data[0].id }));
    }).catch(() => {});
    axios.get(`${API}/execution/config`).then((r) => setFundingAssets(r.data.funding_assets || ["USDT", "BNB", "ETH"])).catch(() => {});
    loadCycles();
    const t = setInterval(() => {
      loadCycles();
      setSelected((cur) => {
        if (cur && !["COMPLETE", "ABORTED"].includes(cur.state)) loadDetail(cur.id);
        return cur;
      });
    }, 8000);
    return () => clearInterval(t);
  }, [loadCycles, loadDetail]);

  useEffect(() => {
    if (status?.fund_tracker?.state_flow) setStateFlow(status.fund_tracker.state_flow);
  }, [status]);

  const create = async () => {
    try {
      const { data } = await axios.post(`${API}/execution/cycles`, {
        route_id: form.route_id, size_usd: parseFloat(form.size_usd), funding_asset: form.funding_asset,
      });
      toast.success(`SIMULATED cycle created (${data.id.slice(0, 8)})`);
      loadCycles(); loadDetail(data.id); onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Create failed");
    }
  };

  const action = async (id, verb, label) => {
    try {
      await axios.post(`${API}/execution/cycles/${id}/${verb}`);
      toast.success(label);
      loadCycles(); loadDetail(id); onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Action failed");
    }
  };

  const ctr = status?.fund_tracker?.counters || {};

  return (
    <div className="panel" data-testid="fund-tracking-panel">
      <div className="panel-title">
        Fund Tracking & Recovery — "Where are the funds right now?"
        <span className="float-right text-[#3d4a59]">SIMULATED · {status?.fund_tracker?.running ? "● tracking" : "○ off"}</span>
      </div>

      {/* counters */}
      <div className="grid grid-cols-5 gap-px bg-[#1f2a36] border border-[#1f2a36] mb-3 font-mono" data-testid="fund-tracking-counters">
        {[["TOTAL", ctr.cycles_total, "#c9d4e0"], ["OPEN", ctr.cycles_open, "#38bdf8"],
          ["STUCK", ctr.cycles_stuck, "#f87171"], ["COMPLETE", ctr.cycles_complete, "#34d399"],
          ["ABORTED", ctr.cycles_aborted, "#6b7888"]].map(([l, v, c]) => (
          <div key={l} className="bg-[#10161e] px-2 py-1.5 text-center">
            <div className="text-[8px] tracking-widest text-[#6b7888]">{l}</div>
            <div className="text-base font-bold" style={{ color: c }}>{v ?? 0}</div>
          </div>
        ))}
      </div>

      {/* create form */}
      <div className="flex flex-wrap items-end gap-2 mb-3 border border-[#1f2a36] bg-[#0a0e13] p-2">
        <label className="block">
          <span className="text-[9px] uppercase tracking-widest text-[#6b7888]">Route</span>
          <select data-testid="cycle-route-select" value={form.route_id}
                  onChange={(e) => setForm({ ...form, route_id: e.target.value })} className="term-input w-44">
            {routes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-[9px] uppercase tracking-widest text-[#6b7888]">Size $</span>
          <input data-testid="cycle-size-input" value={form.size_usd}
                 onChange={(e) => setForm({ ...form, size_usd: e.target.value })} className="term-input w-20" />
        </label>
        <label className="block">
          <span className="text-[9px] uppercase tracking-widest text-[#6b7888]">Funding</span>
          <select data-testid="cycle-funding-select" value={form.funding_asset}
                  onChange={(e) => setForm({ ...form, funding_asset: e.target.value })} className="term-input w-24">
            {fundingAssets.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
        <button data-testid="cycle-create-btn" onClick={create} className="term-btn-primary">+ SIMULATED CYCLE</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* cycle list */}
        <div>
          <div className="text-[10px] uppercase tracking-widest text-[#6b7888] mb-1">Cycles</div>
          {cycles.length === 0 && <div className="font-mono text-[11px] text-[#6b7888]" data-testid="cycles-empty">No cycles yet.</div>}
          <div className="space-y-1 max-h-72 overflow-y-auto">
            {cycles.map((c) => (
              <button key={c.id} data-testid={`cycle-item-${c.id}`} onClick={() => loadDetail(c.id)}
                      className={`w-full text-left border px-2 py-1.5 font-mono transition-colors ${
                        selected?.id === c.id ? "border-[#ffb224] bg-[#ffb224]/5" : "border-[#1f2a36] hover:bg-[#141b24]"}`}>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-[#6b7888]">
                    {c.mode === "shadow" && <span className="text-[#38bdf8] font-bold mr-1">◆</span>}
                    {c.id.slice(0, 8)} · {c.route_name}
                  </span>
                  <span className="text-[10px] font-bold" style={{ color: stateColor(c.state) }}>{c.state}</span>
                </div>
                <div className="text-[9px] text-[#8b97a6] mt-0.5">{c.fund_location?.current}</div>
              </button>
            ))}
          </div>
        </div>

        {/* detail */}
        <div data-testid="cycle-detail">
          {!selected && <div className="font-mono text-[11px] text-[#6b7888]">Select a cycle to inspect its state, fund location, ledger & audit trail.</div>}
          {selected && (
            <>
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-xs font-bold flex items-center gap-1.5">
                  <span className="px-1 py-0.5 text-[8px] font-bold border" style={{
                    borderColor: selected.mode === "shadow" ? "#38bdf8" : "#6b7888",
                    color: selected.mode === "shadow" ? "#38bdf8" : "#6b7888" }}
                    data-testid="cycle-detail-mode">{(selected.mode || "scaffold").toUpperCase()}</span>
                  {selected.id.slice(0, 8)}
                </span>
                <span data-testid="cycle-detail-state" className="font-mono text-xs font-bold" style={{ color: stateColor(selected.state) }}>{selected.state}</span>
              </div>
              <div className="font-mono text-[10px] text-[#34d399] mb-1" data-testid="cycle-detail-location">📍 {selected.fund_location?.current}</div>
              {selected.mode === "shadow" && (
                <div className="flex items-center gap-3 mb-1 font-mono text-[10px]" data-testid="cycle-detail-pnl">
                  <span className="text-[#6b7888]">expected <span className="text-[#ffb224] font-bold">{fmtUsd(selected.expected_profit_quote)}</span> ({fmtPct(selected.expected_net_pct)})</span>
                  <span className="text-[#6b7888]">realized <span className="text-[#34d399] font-bold">{fmtUsd(selected.realized_shadow_pnl_quote)}</span></span>
                </div>
              )}
              {selected.stuck && (
                <div className="border border-[#f87171]/40 bg-[#f87171]/5 px-2 py-1.5 mb-2 font-mono text-[9px] text-[#f87171]" data-testid="cycle-recommendation">
                  ⚠ {selected.stuck_reason}<br />→ {selected.recommended_action}
                </div>
              )}
              <div className="font-mono text-[9px] text-[#6b7888] mb-2">
                {selected.funding_asset} {selected.funding_amount ?? "—"} → ~{fmtQty(selected.bdag_qty_expected)} BDAG · ${selected.size_usd} · venue {(selected.sell_venue || "—").toUpperCase()} · {selected.simulated ? "SIMULATED" : "LIVE"}
              </div>

              {/* stepper */}
              <div className="flex flex-wrap gap-0.5 mb-2" data-testid="cycle-stepper">
                {stateFlow.map((s) => {
                  const reached = (selected.history || []).some((h) => h.state === s) || selected.state === s;
                  const current = selected.state === s;
                  return (
                    <span key={s} title={s}
                          className={`h-1.5 flex-1 min-w-[8px] ${current ? "" : ""}`}
                          style={{ background: current ? "#ffb224" : reached ? "#34d399" : "#1f2a36" }} />
                  );
                })}
              </div>

              {/* action buttons */}
              <div className="flex flex-wrap gap-1 mb-2">
                <button data-testid="cycle-advance-btn" onClick={() => action(selected.id, "advance", "Cycle advanced")}
                        disabled={["COMPLETE", "ABORTED"].includes(selected.state) || selected.mode === "shadow"}
                        title={selected.mode === "shadow" ? "auto-driven by the shadow runner" : ""}
                        className="term-btn-secondary disabled:opacity-40">ADVANCE ▸</button>
                <button data-testid="cycle-manual-review-btn" onClick={() => action(selected.id, "manual-review", "Moved to manual review")}
                        disabled={["COMPLETE", "ABORTED"].includes(selected.state) || selected.mode === "shadow"}
                        className="term-btn-secondary disabled:opacity-40">MANUAL REVIEW</button>
                <button data-testid="cycle-timeline-btn" onClick={() => setTimelineId(selected.id)}
                        className="font-mono text-[10px] font-bold px-2.5 py-1 border border-[#38bdf8]/50 text-[#38bdf8] hover:bg-[#38bdf8]/10">⏱ TIMELINE</button>
                <button data-testid="cycle-abort-btn" onClick={() => action(selected.id, "abort", "Cycle aborted")}
                        disabled={["COMPLETE", "ABORTED"].includes(selected.state)}
                        className="font-mono text-[10px] font-bold px-2.5 py-1 border border-[#f87171]/50 text-[#f87171] hover:bg-[#f87171]/10 disabled:opacity-40">ABORT</button>
              </div>
              {selected.mode === "shadow" && !["COMPLETE", "ABORTED"].includes(selected.state) && (
                <div className="font-mono text-[9px] text-[#38bdf8] mb-2">◆ auto-driven by the shadow runner off live data (non-executing)</div>
              )}

              {/* ledger */}
              <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Fund-location ledger</div>
              <div className="grid grid-cols-2 gap-px bg-[#1f2a36] border border-[#1f2a36] mb-2" data-testid="cycle-ledger">
                {Object.entries(selected.ledger || {}).map(([k, v]) => (
                  <div key={k} className="bg-[#10161e] px-2 py-1 flex items-center justify-between">
                    <span className="font-mono text-[9px] text-[#6b7888]">{LEDGER_LABELS[k] || k}</span>
                    <span className={`font-mono text-[9px] font-bold ${v.status === "confirmed" ? "text-[#34d399]" : "text-[#6b7888]"}`}>
                      {v.status === "confirmed" ? "✓" : "·"}
                    </span>
                  </div>
                ))}
              </div>

              {/* audit */}
              <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Audit trail ({audit.length})</div>
              <div className="max-h-32 overflow-y-auto border border-[#1f2a36] bg-[#0a0e13] p-1.5" data-testid="cycle-audit">
                {audit.map((a, i) => (
                  <div key={i} className="font-mono text-[9px] text-[#8b97a6] border-b border-[#1f2a36]/40 py-0.5">
                    <span className="text-[#6b7888]">{fmtTime(a.ts)}</span>{" "}
                    <span className={a.phase === "intent" ? "text-[#fbbf24]" : a.phase === "recovery" ? "text-[#38bdf8]" : "text-[#34d399]"}>{a.phase}</span>{" "}
                    {a.step} {a.external_ref && <span className="text-[#3d4a59]">{a.external_ref}</span>}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
      <CycleTimelineDialog cycleId={timelineId} onClose={() => setTimelineId(null)} />
    </div>
  );
};
