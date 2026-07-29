import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_C = {
  AUTO_ADVANCED: "#34d399",
  MANUAL_CONFIRMED: "#38bdf8",
  PROPOSED: "#ffb224",
  UNMATCHED: "#6b7888",
};

const fmtNum = (v, d = 4) =>
  v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d });

const fmtAddr = (a) => (a ? `${a.slice(0, 8)}…${a.slice(-6)}` : "—");

const Field = ({ label, name, value, onChange, placeholder, type = "text", testid }) => (
  <label className="block">
    <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">{label}</div>
    <input
      data-testid={testid}
      name={name}
      type={type}
      value={value ?? ""}
      onChange={onChange}
      placeholder={placeholder}
      className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]"
    />
  </label>
);

export const WalletObserverPanel = () => {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({});
  const [savingCfg, setSavingCfg] = useState(false);
  const [polling, setPolling] = useState(false);
  const [runningDiag, setRunningDiag] = useState(false);
  const [diag, setDiag] = useState(null);
  const [forcingDown, setForcingDown] = useState(false);
  const [sell, setSell] = useState({ cycle_id: "", order_id: "", bdag_sold: "", usdt_received: "", fee_usdt: "", best_bid_at_sell: "" });
  const [sellSaving, setSellSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/execution/observer/status`);
      setData(r.data);
      return r.data;
    } catch (e) {
      // silent — likely auth
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const d = await load();
      if (!cancelled && d) setForm({ ...(d.config || {}) });
    })();
    const t = setInterval(load, 12000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [load]);

  const onChange = (e) => {
    const v = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [e.target.name]: v }));
  };

  const saveConfig = async () => {
    setSavingCfg(true);
    try {
      const patch = {};
      ["enabled", "poll_interval_s", "operator_bdag_address", "operator_bsc_address",
        "coinstore_bdag_deposit_address", "coinstore_usdt_hot_wallet_address",
        "blockdag_rpc_primary", "blockdag_rpc_secondary",
        "bscscan_api_base", "bscscan_api_key",
        "max_blocks_per_tick", "force_primary_down"].forEach((k) => {
        if (form[k] !== undefined) patch[k] = form[k] === "" ? null : form[k];
      });
      if (patch.poll_interval_s !== undefined && patch.poll_interval_s !== null) {
        patch.poll_interval_s = parseInt(patch.poll_interval_s, 10) || 60;
      }
      if (patch.max_blocks_per_tick !== undefined && patch.max_blocks_per_tick !== null) {
        patch.max_blocks_per_tick = parseInt(patch.max_blocks_per_tick, 10) || 200;
      }
      const r = await axios.put(`${API}/execution/observer/config`, patch);
      setForm({ ...r.data });
      toast.success("Observer config saved");
      await load();
    } catch (e) {
      toast.error(`Save failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setSavingCfg(false);
    }
  };

  const pollNow = async () => {
    setPolling(true);
    try {
      const r = await axios.post(`${API}/execution/observer/poll`);
      if (r.data?.skipped) {
        toast.warning(`Poll skipped: ${r.data.reason || r.data.error || "dormant"}`);
      } else {
        toast.success(`Polled · BDAG tx ${r.data.bdag_tx_seen}, BSC tx ${r.data.bsc_tx_seen}, new ${r.data.new_events}`);
      }
      await load();
    } catch (e) {
      toast.error(`Poll failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setPolling(false);
    }
  };

  const runDiagnostic = async () => {
    setRunningDiag(true);
    try {
      const r = await axios.post(`${API}/execution/observer/diagnostic`, {});
      setDiag(r.data);
      toast.success(`Diagnostic: ${r.data.recommendation?.verdict} · score ${r.data.recommendation?.reliability_score}/100`);
      await load();
    } catch (e) {
      toast.error(`Diagnostic failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setRunningDiag(false);
    }
  };

  const loadLastDiagnostic = async () => {
    try {
      const r = await axios.get(`${API}/execution/observer/diagnostic/last`);
      if (r.data?.available === false) {
        toast.warning("No diagnostic has been run yet — click RUN DIAGNOSTIC.");
        return;
      }
      setDiag(r.data);
    } catch (e) {
      toast.error(`Load failed: ${e.response?.data?.detail || e.message}`);
    }
  };

  const toggleForceDown = async (next) => {
    setForcingDown(true);
    try {
      await axios.put(`${API}/execution/observer/config`, { force_primary_down: next });
      // trigger a poll so the failover health updates
      await axios.post(`${API}/execution/observer/poll`);
      await load();
      toast[next ? "warning" : "success"](
        next ? "Primary forced DOWN — failover active" : "Primary restored",
      );
    } catch (e) {
      toast.error(`Failover toggle failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setForcingDown(false);
    }
  };

  const submitSell = async () => {
    if (!sell.cycle_id || !sell.order_id || !sell.bdag_sold || !sell.usdt_received) {
      toast.error("cycle_id, order_id, bdag_sold and usdt_received are required");
      return;
    }
    setSellSaving(true);
    try {
      const body = {
        cycle_id: sell.cycle_id.trim(),
        order_id: sell.order_id.trim(),
        bdag_sold: parseFloat(sell.bdag_sold),
        usdt_received: parseFloat(sell.usdt_received),
        fee_usdt: sell.fee_usdt === "" ? null : parseFloat(sell.fee_usdt),
        best_bid_at_sell: sell.best_bid_at_sell === "" ? null : parseFloat(sell.best_bid_at_sell),
      };
      const r = await axios.post(`${API}/execution/observer/coinstore-sell`, body);
      toast.success(`Cycle ${r.data?.cycle?.id?.slice(0, 8)}… stamped SOLD · realized ROI ${r.data?.cycle?.actuals?.realized_roi_pct ?? "—"}%`);
      setSell({ cycle_id: "", order_id: "", bdag_sold: "", usdt_received: "", fee_usdt: "", best_bid_at_sell: "" });
      await load();
    } catch (e) {
      toast.error(`Stamp failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setSellSaving(false);
    }
  };

  const linkEvent = async (eventId) => {
    const cycleId = window.prompt("Cycle ID to link this event to:");
    if (!cycleId) return;
    try {
      await axios.post(`${API}/execution/observer/events/${eventId}/link`, { cycle_id: cycleId.trim() });
      toast.success("Event linked + cycle advanced");
      await load();
    } catch (e) {
      toast.error(`Link failed: ${e.response?.data?.detail || e.message}`);
    }
  };

  if (!data) {
    return (
      <div className="panel" data-testid="wallet-observer-panel">
        <div className="panel-title">WALLET + COINSTORE OBSERVER</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
      </div>
    );
  }

  const cfg = data.config || {};
  const dormancy = data.dormancy_reasons || [];
  const counters = data.counters || {};
  const events = data.recent_events || [];
  const sells = data.recent_sells || [];
  const lastPoll = data.last_poll_result || {};

  return (
    <div className="panel" data-testid="wallet-observer-panel">
      <div className="panel-title flex items-center justify-between flex-wrap gap-2">
        <span>WALLET + COINSTORE OBSERVER</span>
        <div className="flex items-center gap-2">
          <span
            className="text-[9px] font-bold tracking-widest px-2 py-0.5 border"
            style={{
              borderColor: data.ready ? "#34d399" : "#ffb224",
              color: data.ready ? "#34d399" : "#ffb224",
            }}
            data-testid="wo-readiness-badge"
          >
            {data.ready ? "READY" : "DORMANT"}
          </span>
          <span
            className="text-[9px] font-bold tracking-widest px-2 py-0.5 border border-[#f87171] text-[#f87171]"
            data-testid="wo-guardrail-badge"
          >
            READ-ONLY · NO SIGNING
          </span>
        </div>
      </div>

      {/* Dormancy banner */}
      {dormancy.length > 0 && (
        <div
          className="mb-3 border border-[#ffb224]/40 bg-[#ffb224]/10 px-3 py-2 font-mono text-[10px] text-[#ffb224]"
          data-testid="wo-dormancy-banner"
        >
          <div className="font-bold tracking-wider mb-1">DORMANT</div>
          {dormancy.map((r, i) => (
            <div key={i}>• {r}</div>
          ))}
        </div>
      )}

      {/* Counters strip */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-[#1f2a36] border border-[#1f2a36] font-mono mb-3" data-testid="wo-counters">
        {[
          ["Auto-advanced", counters.auto_advanced, "#34d399"],
          ["Manual-confirmed", counters.manual_confirmed, "#38bdf8"],
          ["Proposed", counters.proposed, "#ffb224"],
          ["Unmatched", counters.unmatched, "#6b7888"],
          ["Sell stamps", counters.sells, "#a78bfa"],
        ].map(([lbl, val, c]) => (
          <div key={lbl} className="bg-[#10161e] px-3 py-2">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase">{lbl}</div>
            <div className="text-base font-bold font-mono" style={{ color: c }}>
              {val ?? 0}
            </div>
          </div>
        ))}
      </div>

      {/* Diagnostic + RPC health */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-3 mb-3" data-testid="wo-diag-section">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <div className="text-[10px] tracking-widest text-[#38bdf8] uppercase">
            BlockDAG Connectivity · RPC Health · Failover
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              data-testid="wo-diag-run"
              onClick={runDiagnostic}
              disabled={runningDiag}
              className="px-3 py-1 border border-[#a78bfa] text-[#a78bfa] hover:bg-[#a78bfa]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider"
            >
              {runningDiag ? "DIAGNOSING…" : "→ RUN DIAGNOSTIC"}
            </button>
            <button
              data-testid="wo-diag-load-last"
              onClick={loadLastDiagnostic}
              className="px-3 py-1 border border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0] font-mono text-[10px] font-bold tracking-wider"
            >
              ↻ LAST REPORT
            </button>
            <button
              data-testid="wo-force-down-toggle"
              onClick={() => toggleForceDown(!cfg.force_primary_down)}
              disabled={forcingDown}
              className={`px-3 py-1 border font-mono text-[10px] font-bold tracking-wider disabled:opacity-50 ${
                cfg.force_primary_down
                  ? "border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10"
                  : "border-[#f87171] text-[#f87171] hover:bg-[#f87171]/10"
              }`}
            >
              {cfg.force_primary_down ? "▷ RESTORE PRIMARY" : "✕ FORCE PRIMARY DOWN"}
            </button>
          </div>
        </div>

        {/* RPC health table */}
        <RPCHealth health={data.rpc_health} forceDown={!!cfg.force_primary_down} />

        {/* Diagnostic verdict + report */}
        {(diag || data.last_diagnostic) && (
          <DiagnosticReport report={diag || data.last_diagnostic} />
        )}

        {!diag && !data.last_diagnostic && (
          <div className="font-mono text-[10px] text-[#6b7888]">
            No diagnostic run yet. Click <b>RUN DIAGNOSTIC</b> to probe rpc.bdagscan.com,
            rpc.blockdag.engineering, bdagscan.com, and explorer.blockdag.engineering with the
            operator&apos;s test wallet + tx and store a connectivity report.
          </div>
        )}
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Config form */}
        <div className="col-span-12 xl:col-span-6">
          <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="wo-config-form">
            <div className="text-[10px] tracking-widest text-[#a78bfa] uppercase mb-2">Configuration</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="flex items-center gap-2 col-span-full">
                <input
                  type="checkbox"
                  data-testid="wo-cfg-enabled"
                  name="enabled"
                  checked={!!form.enabled}
                  onChange={onChange}
                />
                <span className="font-mono text-[11px] text-[#c9d4e0]">Enable observer polling</span>
              </label>
              <Field
                label="Poll interval (s · min 15)"
                name="poll_interval_s"
                type="number"
                value={form.poll_interval_s ?? 60}
                onChange={onChange}
                testid="wo-cfg-poll-interval"
              />
              <Field
                label="BlockDAG RPC primary"
                name="blockdag_rpc_primary"
                value={form.blockdag_rpc_primary ?? ""}
                onChange={onChange}
                placeholder="https://rpc.bdagscan.com"
                testid="wo-cfg-rpc-primary"
              />
              <Field
                label="BlockDAG RPC secondary (failover)"
                name="blockdag_rpc_secondary"
                value={form.blockdag_rpc_secondary ?? ""}
                onChange={onChange}
                placeholder="https://rpc.blockdag.engineering"
                testid="wo-cfg-rpc-secondary"
              />
              <Field
                label="Max blocks per tick (10–1000)"
                name="max_blocks_per_tick"
                type="number"
                value={form.max_blocks_per_tick ?? 200}
                onChange={onChange}
                testid="wo-cfg-max-blocks"
              />
              <Field
                label="Operator BDAG address"
                name="operator_bdag_address"
                value={form.operator_bdag_address ?? ""}
                onChange={onChange}
                placeholder="0x…"
                testid="wo-cfg-op-bdag"
              />
              <Field
                label="Operator BSC address (USDT receive)"
                name="operator_bsc_address"
                value={form.operator_bsc_address ?? ""}
                onChange={onChange}
                placeholder="0x…"
                testid="wo-cfg-op-bsc"
              />
              <Field
                label="Coinstore BDAG deposit address"
                name="coinstore_bdag_deposit_address"
                value={form.coinstore_bdag_deposit_address ?? ""}
                onChange={onChange}
                placeholder="0x…"
                testid="wo-cfg-cs-deposit"
              />
              <Field
                label="Coinstore USDT hot wallet (BSC)"
                name="coinstore_usdt_hot_wallet_address"
                value={form.coinstore_usdt_hot_wallet_address ?? ""}
                onChange={onChange}
                placeholder="0x…"
                testid="wo-cfg-cs-hot"
              />
              <Field
                label="BSCScan API base"
                name="bscscan_api_base"
                value={form.bscscan_api_base ?? ""}
                onChange={onChange}
                placeholder="https://api.bscscan.com/api"
                testid="wo-cfg-bscscan-base"
              />
              <Field
                label="BSCScan API key"
                name="bscscan_api_key"
                value={form.bscscan_api_key ?? ""}
                onChange={onChange}
                placeholder="optional"
                testid="wo-cfg-bscscan-key"
              />
            </div>
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <button
                data-testid="wo-cfg-save"
                onClick={saveConfig}
                disabled={savingCfg}
                className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider"
              >
                {savingCfg ? "SAVING…" : "→ SAVE CONFIG"}
              </button>
              <button
                data-testid="wo-poll-now"
                onClick={pollNow}
                disabled={polling}
                className="px-3 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider"
              >
                {polling ? "POLLING…" : "↻ POLL NOW"}
              </button>
              <span className="text-[10px] text-[#6b7888] font-mono ml-auto">
                Last poll:{" "}
                <b className="text-[#c9d4e0]" data-testid="wo-last-poll">
                  {lastPoll.ran_at ? fmtTime(lastPoll.ran_at) : "—"}
                </b>
                {lastPoll.skipped && <span className="text-[#ffb224]"> · skipped</span>}
              </span>
            </div>
          </div>
        </div>

        {/* Coinstore manual sell stamp */}
        <div className="col-span-12 xl:col-span-6">
          <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="wo-sell-form">
            <div className="text-[10px] tracking-widest text-[#a78bfa] uppercase mb-2">
              Coinstore Sell Stamp (operator → marks cycle SOLD)
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field
                label="Cycle ID"
                name="cycle_id"
                value={sell.cycle_id}
                onChange={(e) => setSell((s) => ({ ...s, cycle_id: e.target.value }))}
                placeholder="cycle id"
                testid="wo-sell-cycle"
              />
              <Field
                label="Coinstore order ID"
                name="order_id"
                value={sell.order_id}
                onChange={(e) => setSell((s) => ({ ...s, order_id: e.target.value }))}
                placeholder="from Coinstore UI"
                testid="wo-sell-order"
              />
              <Field
                label="BDAG sold"
                name="bdag_sold"
                type="number"
                value={sell.bdag_sold}
                onChange={(e) => setSell((s) => ({ ...s, bdag_sold: e.target.value }))}
                placeholder="e.g. 1234567"
                testid="wo-sell-bdag"
              />
              <Field
                label="USDT received"
                name="usdt_received"
                type="number"
                value={sell.usdt_received}
                onChange={(e) => setSell((s) => ({ ...s, usdt_received: e.target.value }))}
                placeholder="net of trading fee"
                testid="wo-sell-usdt"
              />
              <Field
                label="Trading fee (USDT, optional)"
                name="fee_usdt"
                type="number"
                value={sell.fee_usdt}
                onChange={(e) => setSell((s) => ({ ...s, fee_usdt: e.target.value }))}
                placeholder="optional"
                testid="wo-sell-fee"
              />
              <Field
                label="Best bid at sell (optional)"
                name="best_bid_at_sell"
                type="number"
                value={sell.best_bid_at_sell}
                onChange={(e) => setSell((s) => ({ ...s, best_bid_at_sell: e.target.value }))}
                placeholder="enables drift %"
                testid="wo-sell-bid"
              />
            </div>
            <button
              data-testid="wo-sell-submit"
              onClick={submitSell}
              disabled={sellSaving}
              className="mt-3 px-3 py-1 border border-[#a78bfa] text-[#a78bfa] hover:bg-[#a78bfa]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider"
            >
              {sellSaving ? "STAMPING…" : "→ STAMP SOLD"}
            </button>
            <div className="font-mono text-[9px] text-[#6b7888] mt-2">
              Operator stamps the sell after executing it in the Coinstore UI. This advances the cycle to SOLD and
              records actuals (realized ROI, drift %). Chain confirmation of the USDT withdrawal will be auto-detected
              by the observer once the BSC hot wallet sends to your address.
            </div>
          </div>
        </div>

        {/* Recent events */}
        <div className="col-span-12">
          <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="wo-events">
            <div className="text-[10px] tracking-widest text-[#a78bfa] uppercase mb-2">
              Recent Detected Events
            </div>
            {events.length === 0 ? (
              <div className="font-mono text-[10px] text-[#6b7888]">
                No chain events recorded yet. Configure addresses + explorer above, enable observer, and the poller will
                start matching transactions to open cycles.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-[10px]" data-testid="wo-events-table">
                  <thead className="text-[#6b7888] uppercase tracking-widest">
                    <tr className="border-b border-[#1f2a36]">
                      <th className="text-left py-1 pr-2">Detected</th>
                      <th className="text-left pr-2">Chain</th>
                      <th className="text-left pr-2">Milestone</th>
                      <th className="text-left pr-2">Tx</th>
                      <th className="text-left pr-2">From → To</th>
                      <th className="text-right pr-2">Amount</th>
                      <th className="text-left pr-2">Status</th>
                      <th className="text-left">Cycle</th>
                    </tr>
                  </thead>
                  <tbody className="text-[#c9d4e0]">
                    {events.map((e) => (
                      <tr key={e.id} className="border-b border-[#1f2a36]/60">
                        <td className="py-1 pr-2 text-[#6b7888]">{fmtTime(e.detected_at)}</td>
                        <td className="pr-2">{e.chain}</td>
                        <td className="pr-2">{e.milestone}</td>
                        <td className="pr-2 text-[#38bdf8]">{(e.tx_hash || "").slice(0, 10)}…</td>
                        <td className="pr-2 text-[#6b7888]">
                          {fmtAddr(e.from_addr)} → {fmtAddr(e.to_addr)}
                        </td>
                        <td className="pr-2 text-right">{fmtNum(e.amount, 6)} {e.asset}</td>
                        <td className="pr-2" style={{ color: STATUS_C[e.status] || "#c9d4e0" }}>
                          {e.status}
                        </td>
                        <td className="">
                          {e.matched_cycle_id ? (
                            <span className="text-[#34d399]">{e.matched_cycle_id.slice(0, 8)}…</span>
                          ) : (
                            <button
                              data-testid={`wo-event-link-${e.id}`}
                              onClick={() => linkEvent(e.id)}
                              className="text-[#ffb224] underline hover:text-[#ffd97a]"
                            >
                              link
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Recent sells */}
        <div className="col-span-12">
          <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="wo-sells">
            <div className="text-[10px] tracking-widest text-[#a78bfa] uppercase mb-2">Recent Sell Stamps</div>
            {sells.length === 0 ? (
              <div className="font-mono text-[10px] text-[#6b7888]">No sell stamps yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-[10px]">
                  <thead className="text-[#6b7888] uppercase tracking-widest">
                    <tr className="border-b border-[#1f2a36]">
                      <th className="text-left py-1 pr-2">Stamped</th>
                      <th className="text-left pr-2">Cycle</th>
                      <th className="text-left pr-2">Order</th>
                      <th className="text-right pr-2">BDAG Sold</th>
                      <th className="text-right pr-2">USDT Recv</th>
                      <th className="text-right pr-2">Avg Sell</th>
                      <th className="text-right">Fee</th>
                    </tr>
                  </thead>
                  <tbody className="text-[#c9d4e0]">
                    {sells.map((s) => (
                      <tr key={s.id} className="border-b border-[#1f2a36]/60">
                        <td className="py-1 pr-2 text-[#6b7888]">{fmtTime(s.stamped_at)}</td>
                        <td className="pr-2 text-[#34d399]">{s.cycle_id.slice(0, 8)}…</td>
                        <td className="pr-2">{s.order_id}</td>
                        <td className="pr-2 text-right">{fmtNum(s.bdag_sold, 0)}</td>
                        <td className="pr-2 text-right">${fmtNum(s.usdt_received, 2)}</td>
                        <td className="pr-2 text-right text-[#a78bfa]">${fmtNum(s.sell_price_avg, 8)}</td>
                        <td className="text-right">{s.fee_usdt == null ? "—" : `$${fmtNum(s.fee_usdt, 4)}`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="font-mono text-[10px] text-[#6b7888] mt-3">
        ◆ Observer reads public chain explorers only. It NEVER signs, submits, or moves funds. Auto-advance triggers only
        when a single open cycle in the prior state matches the on-chain amount within ±2 %. Ambiguous matches are
        proposed and require operator confirmation.
      </div>
    </div>
  );
};


// ---------------- RPC Health table ----------------------------------------
const RPCHealth = ({ health, forceDown }) => {
  if (!health) {
    return (
      <div className="font-mono text-[10px] text-[#6b7888]">
        RPC client not yet initialised — run a poll or diagnostic to populate health.
      </div>
    );
  }
  const rows = [
    { label: "PRIMARY", h: health.primary, forced: forceDown },
    ...(health.secondary ? [{ label: "SECONDARY", h: health.secondary, forced: false }] : []),
  ];
  return (
    <div className="overflow-x-auto mb-3" data-testid="wo-rpc-health">
      <table className="w-full font-mono text-[10px]">
        <thead className="text-[#6b7888] uppercase tracking-widest">
          <tr className="border-b border-[#1f2a36]">
            <th className="text-left py-1 pr-2">Role</th>
            <th className="text-left pr-2">URL</th>
            <th className="text-left pr-2">Health</th>
            <th className="text-right pr-2">Latency</th>
            <th className="text-right pr-2">Calls</th>
            <th className="text-right pr-2">Failures</th>
            <th className="text-right pr-2">Streak</th>
            <th className="text-left">Last Error</th>
          </tr>
        </thead>
        <tbody className="text-[#c9d4e0]">
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-[#1f2a36]/60" data-testid={`wo-rpc-row-${r.label.toLowerCase()}`}>
              <td className="py-1 pr-2 font-bold tracking-wider" style={{ color: r.label === "PRIMARY" ? "#a78bfa" : "#38bdf8" }}>
                {r.label}
                {r.forced && (
                  <span className="ml-1 text-[8px] text-[#f87171] border border-[#f87171] px-1">FORCED DOWN</span>
                )}
              </td>
              <td className="pr-2 text-[#38bdf8]">{r.h.url}</td>
              <td className="pr-2" style={{ color: r.h.healthy ? "#34d399" : "#f87171" }}>
                {r.h.healthy ? "HEALTHY" : "DEGRADED"}
              </td>
              <td className="pr-2 text-right">{r.h.last_latency_ms == null ? "—" : `${r.h.last_latency_ms}ms`}</td>
              <td className="pr-2 text-right">{r.h.total_calls ?? 0}</td>
              <td className="pr-2 text-right text-[#ffb224]">{r.h.total_failures ?? 0}</td>
              <td className="pr-2 text-right">
                {r.h.consecutive_failures > 0 ? (
                  <span className="text-[#f87171]">{r.h.consecutive_failures}✗</span>
                ) : (
                  <span className="text-[#34d399]">{r.h.consecutive_successes ?? 0}✓</span>
                )}
              </td>
              <td className="text-[#6b7888] max-w-[300px] truncate">{r.h.last_error || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-[9px] text-[#6b7888] mt-1">
        expected chain_id: <b className="text-[#c9d4e0]">{health.expected_chain_id}</b>
      </div>
    </div>
  );
};

// ---------------- Diagnostic Report -----------------------------------------
const DiagnosticReport = ({ report }) => {
  if (!report) return null;
  const rec = report.recommendation || {};
  const verdictColor = rec.verdict === "PASS" ? "#34d399" : "#f87171";
  return (
    <div className="border border-[#1f2a36] bg-[#10161e] p-3 mt-2" data-testid="wo-diagnostic-report">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <div className="font-mono text-[10px] tracking-widest uppercase" style={{ color: verdictColor }}>
          Diagnostic verdict: <span data-testid="wo-diag-verdict">{rec.verdict || "—"}</span>
          {" · "}reliability <span data-testid="wo-diag-score">{rec.reliability_score ?? "—"}/100</span>
        </div>
        <div className="font-mono text-[9px] text-[#6b7888]">
          ran: {report.ran_at_iso || "—"}
        </div>
      </div>
      <div className="font-mono text-[10px] text-[#c9d4e0] mb-2">
        <div>Recommended PRIMARY: <b className="text-[#34d399]" data-testid="wo-diag-rec-primary">{rec.primary || "NONE"}</b></div>
        <div>Recommended BACKUP : <b className="text-[#ffb224]" data-testid="wo-diag-rec-backup">{rec.backup || "NONE"}</b></div>
        {(rec.notes || []).map((n, i) => (
          <div key={i} className="text-[#6b7888]">• {n}</div>
        ))}
      </div>
      <DiagSourceTable label="RPC" rows={[report.rpc_primary, report.rpc_secondary]} mode="rpc" />
      <DiagSourceTable label="EXPLORER" rows={[report.explorer_primary, report.explorer_secondary]} mode="expl" />
      {report.cross_chain_check?.bsc_mainnet && (
        <div className="font-mono text-[10px] text-[#c9d4e0] mt-2" data-testid="wo-diag-cross-chain">
          <b className="text-[#a78bfa]">Cross-chain check</b>:{" "}
          {report.cross_chain_check.bsc_mainnet.found ? (
            <span className="text-[#34d399]">
              test_tx found on BSC block {report.cross_chain_check.bsc_mainnet.block_decimal}
            </span>
          ) : (
            <span className="text-[#6b7888]">test_tx not found on BSC either</span>
          )}
          {report.cross_chain_check.bsc_mainnet.note && (
            <div className="text-[#6b7888]">→ {report.cross_chain_check.bsc_mainnet.note}</div>
          )}
        </div>
      )}
      {report.address_activity_demo && (
        <div className="font-mono text-[10px] text-[#c9d4e0] mt-2" data-testid="wo-diag-activity">
          <b className="text-[#a78bfa]">Live address activity probe</b> (last{" "}
          {report.address_activity_demo.lookback_blocks} blocks @ head{" "}
          {report.address_activity_demo.head_block}):{" "}
          <span style={{ color: report.address_activity_demo.found_activity ? "#34d399" : "#6b7888" }}>
            {report.address_activity_demo.verdict}
          </span>
          {(report.address_activity_demo.matched || []).map((m, i) => (
            <div key={i} className="text-[#6b7888]">
              block {m.block} {m.direction} {m.value_bdag} BDAG tx={(m.tx_hash || "").slice(0, 14)}…
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const DiagSourceTable = ({ label, rows, mode }) => (
  <div className="overflow-x-auto mb-2">
    <table className="w-full font-mono text-[10px]" data-testid={`wo-diag-${mode}-table`}>
      <thead className="text-[#6b7888] uppercase tracking-widest">
        <tr className="border-b border-[#1f2a36]">
          <th className="text-left py-1 pr-2">{label}</th>
          <th className="text-left pr-2">Host</th>
          <th className="text-right pr-2">Score</th>
          <th className="text-right pr-2">Stab%</th>
          <th className="text-right pr-2">Lat avg</th>
          <th className="text-left">Key Capabilities</th>
        </tr>
      </thead>
      <tbody className="text-[#c9d4e0]">
        {(rows || []).filter(Boolean).map((s, i) => (
          <tr key={i} className="border-b border-[#1f2a36]/60">
            <td className="py-1 pr-2 font-bold" style={{ color: i === 0 ? "#a78bfa" : "#38bdf8" }}>
              {i === 0 ? "PRIMARY" : "SECONDARY"}
            </td>
            <td className="pr-2">{s.name}</td>
            <td className="pr-2 text-right" style={{ color: (s.score || 0) >= 50 ? "#34d399" : "#f87171" }}>
              {s.score ?? "—"}
            </td>
            <td className="pr-2 text-right">{s.reachability?.stability_pct ?? "—"}%</td>
            <td className="pr-2 text-right">{s.reachability?.latency_ms_avg ?? "—"}ms</td>
            <td className="text-[#6b7888]">
              {mode === "rpc" ? (
                <>
                  chainId={s.evm?.eth_chainId?.verdict}{" "}
                  block#={s.evm?.eth_blockNumber?.verdict}{" "}
                  bal={s.evm?.eth_getBalance?.verdict}{" "}
                  tx={s.evm?.eth_getTransactionByHash?.verdict}{" "}
                  recpt={s.evm?.eth_getTransactionReceipt?.verdict}{" "}
                  logs={s.evm?.eth_getLogs?.verdict}
                </>
              ) : (
                <>
                  etherscan={String(s.explorer?.etherscan_works)}{" "}
                  blockscout_history={String(s.explorer?.blockscout_works_address_history)}{" "}
                  blockscout_tx={String(s.explorer?.blockscout_works_tx_lookup)}
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
