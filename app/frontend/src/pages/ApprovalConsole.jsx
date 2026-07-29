import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const REGIME_C = { Stable: "#34d399", Volatile: "#ffb224", "Extremely Volatile": "#f87171" };
const RISK_C = { LOW: "#34d399", MEDIUM: "#ffb224", HIGH: "#fb8b3a", VERY_HIGH: "#f87171" };

const num = (v, d = 2) => (v == null || isNaN(v) ? "—" : Number(v).toFixed(d));
const pct = (v) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`);
const minOf = (...xs) => Math.min(...xs.filter((x) => typeof x === "number" && !isNaN(x) && x > 0));

const ApprovalConsole = () => {
  const [proposed, setProposed] = useState(null);
  const [auto, setAuto] = useState(null);
  const [customSize, setCustomSize] = useState("");
  const [posting, setPosting] = useState(false);
  const [showSecondary, setShowSecondary] = useState(false);
  const [autoToggling, setAutoToggling] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([
        axios.get(`${API}/execution/proposed`).then((r) => r.data),
        axios.get(`${API}/execution/auto-mode/status`).then((r) => r.data),
      ]);
      setProposed(p);
      setAuto(a);
    } catch (e) { /* soft fail */ }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000); // 5s refresh — fast enough for the 30s reverify window
    return () => clearInterval(t);
  }, [load]);

  const approve = async (proposalId, sizeUsd, mode) => {
    if (!proposalId || !(sizeUsd > 0)) return;
    setPosting(true);
    try {
      const r = await axios.post(`${API}/execution/proposed/${proposalId}/approve`,
                                 { size_usd: sizeUsd, approve_mode: mode });
      toast.success(`Cycle opened (${mode}) — id=${r.data?.cycle?.id?.slice(0, 8) || "—"}`);
      load();
    } catch (e) {
      toast.error(`Approve failed: ${e.response?.data?.detail || e.message}`);
    } finally { setPosting(false); }
  };

  const reject = async (proposalId, reason) => {
    if (!proposalId) return;
    setPosting(true);
    try {
      await axios.post(`${API}/execution/proposed/${proposalId}/reject`, { reason });
      toast.success("Rejected — logged for evidence");
      load();
    } catch (e) {
      toast.error(`Reject failed: ${e.response?.data?.detail || e.message}`);
    } finally { setPosting(false); }
  };

  const toggleAuto = async () => {
    if (!auto) return;
    setAutoToggling(true);
    try {
      const r = await axios.put(`${API}/execution/auto-mode/status`,
                                { enabled: !auto.auto_mode_enabled_flag });
      setAuto(r.data);
      toast.success(`Auto-mode flag: ${r.data.auto_mode_enabled_flag ? "ON" : "OFF"} ` +
                    `(effective: ${r.data.auto_mode_effective ? "yes" : "no — interlock blocks"})`);
    } catch (e) {
      toast.error(`Toggle failed: ${e.response?.data?.detail || e.message}`);
    } finally { setAutoToggling(false); }
  };

  if (!proposed) {
    return (
      <div className="p-4 font-mono text-[#6b7888] text-[12px]" data-testid="approval-loading">loading…</div>
    );
  }

  const primary = proposed.primary;
  const secondary = proposed.secondary || [];
  const targets = proposed.targets || {};
  const blockers = proposed.blockers || [];
  const reverifyIn = primary?.quote_age_s != null
    ? Math.max(0, Math.round(proposed.staleness_threshold_s - primary.quote_age_s))
    : null;

  return (
    <div className="min-h-[calc(100vh-60px)] bg-[#0a0e13] px-4 py-3" data-testid="approval-console">
      {/* Top strip — Auto Mode */}
      <div className="flex items-center justify-between mb-3 pb-2 border-b border-[#1f2a36]">
        <div>
          <div className="text-[10px] tracking-widest text-[#6b7888] font-mono">ARBICORE · APPROVAL REQUIRED MODE</div>
          <div className="text-[10px] text-[#5a6573] font-mono">
            min ROI {num(proposed.min_roi_threshold_pct, 1)}% · reverify {proposed.staleness_threshold_s}s · refresh 5s
          </div>
        </div>
        <button onClick={toggleAuto} disabled={autoToggling}
                data-testid="auto-mode-toggle"
                className={"font-mono text-[10px] px-3 py-1 border tracking-wider " + (
                  auto?.auto_mode_effective
                    ? "border-[#f87171] text-[#f87171] bg-[#f87171]/10"
                    : auto?.auto_mode_enabled_flag
                      ? "border-[#ffb224] text-[#ffb224] bg-[#ffb224]/10"
                      : "border-[#1f2a36] text-[#8b97a6] hover:text-[#c9d4e0]")}>
          AUTO MODE: {auto?.auto_mode_effective ? "ON (LIVE)"
                    : auto?.auto_mode_enabled_flag ? "FLAG ON · GATED"
                    : "OFF"}
        </button>
      </div>

      {/* Blockers banner */}
      {blockers.length > 0 && !primary && (
        <div className="border border-[#ffb224]/40 bg-[#ffb224]/05 p-3 mb-3 font-mono text-[11px] text-[#ffb224]"
             data-testid="approval-blockers">
          <div className="font-bold mb-1">No actionable proposal — blockers:</div>
          <ul className="space-y-0.5">{blockers.map((b, i) => <li key={i}>• {b}</li>)}</ul>
        </div>
      )}

      {/* PRIMARY OPPORTUNITY */}
      {primary ? (
        <div className="border-2 border-[#34d399]/60 bg-gradient-to-br from-[#0a120e] to-[#0a0e13] p-4 mb-4"
             data-testid="primary-proposal">
          <div className="flex items-baseline justify-between mb-3">
            <div className="font-mono text-[10px] tracking-widest uppercase text-[#34d399]">
              ⬢ PRIMARY OPPORTUNITY
            </div>
            <div className="flex items-center gap-3 font-mono text-[10px]">
              <span className="text-[#8b97a6]">quality <b className="text-[#c9d4e0]">{num(primary.quality_score, 1)}</b></span>
              <span className="text-[#8b97a6]">verified <b className={reverifyIn < 5 ? "text-[#f87171]" : "text-[#c9d4e0]"}>{num(primary.quote_age_s, 0)}s ago</b></span>
              {reverifyIn != null && <span className={"px-2 py-0.5 border " + (
                reverifyIn < 5 ? "border-[#f87171] text-[#f87171]" : "border-[#34d399] text-[#34d399]")}
                data-testid="primary-reverify-countdown">reverify in {reverifyIn}s</span>}
            </div>
          </div>

          {/* Prices row */}
          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="bg-[#0e141c] border border-[#1f2a36] p-2">
              <div className="text-[8px] tracking-widest text-[#6b7888]">BUY (BlockDAG)</div>
              <div className="font-mono text-base font-bold text-[#38bdf8]" data-testid="primary-buy-price">
                {Number(primary.buy_price).toExponential(4)}
              </div>
              <div className="text-[8px] text-[#5a6573]">{primary.buy_price_source} · verified</div>
            </div>
            <div className="bg-[#0e141c] border border-[#1f2a36] p-2">
              <div className="text-[8px] tracking-widest text-[#6b7888]">SELL (Coinstore)</div>
              <div className="font-mono text-base font-bold text-[#a78bfa]" data-testid="primary-sell-price">
                {Number(primary.sell_price).toExponential(4)}
              </div>
              <div className="text-[8px] text-[#5a6573]">live order book</div>
            </div>
            <div className="bg-[#0e141c] border border-[#1f2a36] p-2">
              <div className="text-[8px] tracking-widest text-[#6b7888]">NET ROI</div>
              <div className="font-mono text-base font-bold text-[#34d399]" data-testid="primary-net-roi">
                {pct(primary.net_roi_pct)}
              </div>
              <div className="text-[8px] text-[#5a6573]">gross {pct(primary.gross_spread_pct)} − fees {num(primary.fee_drag_pct, 2)}%</div>
            </div>
          </div>

          {/* Sizing row */}
          <div className="grid grid-cols-5 gap-2 mb-3 font-mono">
            <div className="text-center">
              <div className="text-[8px] tracking-widest text-[#6b7888]">AVAILABLE</div>
              <div className="text-sm font-bold text-[#c9d4e0]" data-testid="size-available">
                {fmtUsd(targets.available_balance_usd)}
              </div>
              <div className="text-[7px] text-[#5a6573]">{targets.available_source || "—"}</div>
            </div>
            <div className="text-center">
              <div className="text-[8px] tracking-widest text-[#6b7888]">RECOMMENDED</div>
              <div className="text-sm font-bold text-[#34d399]" data-testid="size-recommended">
                {fmtUsd(targets.recommended_buy_usd)}
              </div>
              <div className="text-[7px] text-[#5a6573]">HDA optimal</div>
            </div>
            <div className="text-center">
              <div className="text-[8px] tracking-widest text-[#6b7888]">MAX SAFE</div>
              <div className="text-sm font-bold text-[#ffb224]" data-testid="size-max-safe">
                {fmtUsd(targets.max_safe_buy_usd)}
              </div>
              <div className="text-[7px] text-[#5a6573]">depth @ 8%</div>
            </div>
            <div className="text-center">
              <div className="text-[8px] tracking-widest text-[#6b7888]">MIN</div>
              <div className="text-sm font-bold text-[#8b97a6]" data-testid="size-min">{fmtUsd(targets.min_buy_usd)}</div>
              <div className="text-[7px] text-[#5a6573]">BDAG floor</div>
            </div>
            <div className="text-center">
              <div className="text-[8px] tracking-widest text-[#6b7888]">DAILY REMAINING</div>
              <div className="text-sm font-bold text-[#a78bfa]" data-testid="size-daily-remaining">
                {fmtUsd(targets.daily_remaining_usd)}
              </div>
              <div className="text-[7px] text-[#5a6573]">used ${num(targets.daily_used_usd, 0)}/${num(targets.daily_limit_usd, 0)}</div>
            </div>
          </div>

          {/* Risk + regime + duration row */}
          <div className="grid grid-cols-4 gap-2 mb-3 font-mono">
            <div className="text-center bg-[#0e141c] border border-[#1f2a36] p-2">
              <div className="text-[8px] tracking-widest text-[#6b7888]">RISK</div>
              <div className="text-sm font-bold" style={{ color: RISK_C[primary.risk_label] || "#8b97a6" }}
                   data-testid="primary-risk-label">
                {primary.risk_label || "—"} ({num(primary.risk_score, 0)}/100)
              </div>
            </div>
            <div className="text-center bg-[#0e141c] border border-[#1f2a36] p-2">
              <div className="text-[8px] tracking-widest text-[#6b7888]">REGIME</div>
              <div className="text-sm font-bold" style={{ color: REGIME_C[primary.regime] || "#8b97a6" }}
                   data-testid="primary-regime">
                {primary.regime || "—"}
              </div>
            </div>
            <div className="text-center bg-[#0e141c] border border-[#1f2a36] p-2">
              <div className="text-[8px] tracking-widest text-[#6b7888]">CYCLE DURATION</div>
              <div className="text-sm font-bold text-[#c9d4e0]" data-testid="primary-cycle-duration">
                ~{Math.round(primary.expected_cycle_s / 60)}m
              </div>
              <div className="text-[7px] text-[#5a6573]">survival {primary.combined_survival_prob != null ? `${(primary.combined_survival_prob*100).toFixed(0)}%` : "—"}</div>
            </div>
            <div className="text-center bg-[#0e141c] border border-[#1f2a36] p-2">
              <div className="text-[8px] tracking-widest text-[#6b7888]">EXPECTED PROFIT</div>
              <div className="text-sm font-bold text-[#34d399]" data-testid="primary-expected-profit">
                {fmtUsd(primary.expected_profit_usd)}
              </div>
              <div className="text-[7px] text-[#5a6573]">size ${num(primary.size_usd, 0)} · ~{num(primary.bdag_expected, 0)} BDAG</div>
            </div>
          </div>

          {/* Action row */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mt-2 pt-3 border-t border-[#1f2a36]">
            <button data-testid="approve-available" disabled={posting || !(targets.available_balance_usd >= targets.min_buy_usd)}
                    onClick={() => approve(primary.proposal_id,
                      Math.min(targets.available_balance_usd, targets.max_safe_buy_usd || targets.available_balance_usd),
                      "available")}
                    className="px-3 py-2 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-30 disabled:cursor-not-allowed font-mono text-[10px] font-bold tracking-wider text-left">
              ✓ APPROVE w/ AVAILABLE
              <div className="text-[9px] text-[#8b97a6] font-normal mt-0.5">{fmtUsd(Math.min(targets.available_balance_usd || 0, targets.max_safe_buy_usd || targets.available_balance_usd || 0))} · clipped to max safe</div>
            </button>
            <button data-testid="approve-recommended" disabled={posting || !(targets.recommended_buy_usd >= targets.min_buy_usd)}
                    onClick={() => approve(primary.proposal_id, targets.recommended_buy_usd, "recommended")}
                    className="px-3 py-2 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-30 disabled:cursor-not-allowed font-mono text-[10px] font-bold tracking-wider text-left">
              ✓ APPROVE w/ RECOMMENDED
              <div className="text-[9px] text-[#8b97a6] font-normal mt-0.5">{fmtUsd(targets.recommended_buy_usd)} · HDA optimal</div>
            </button>
            <div data-testid="approve-custom" className="flex flex-col gap-1">
              <input type="number" step="any" placeholder="custom $"
                     value={customSize} onChange={(e) => setCustomSize(e.target.value)}
                     data-testid="custom-size-input"
                     className="bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0] w-full" />
              <button disabled={posting || !(parseFloat(customSize) >= targets.min_buy_usd)}
                      onClick={() => approve(primary.proposal_id, parseFloat(customSize), "custom")}
                      data-testid="custom-size-submit"
                      className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-30 disabled:cursor-not-allowed font-mono text-[10px] font-bold tracking-wider">
                ✓ CUSTOM
              </button>
            </div>
            <button data-testid="reject-primary" disabled={posting}
                    onClick={() => reject(primary.proposal_id, "operator")}
                    className="px-3 py-2 border border-[#f87171] text-[#f87171] hover:bg-[#f87171]/10 disabled:opacity-30 font-mono text-[10px] font-bold tracking-wider">
              ✗ REJECT
            </button>
          </div>
        </div>
      ) : (
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-6 mb-3 text-center font-mono text-[12px] text-[#6b7888]"
             data-testid="no-primary-proposal">
          {blockers.length === 0 ? "No actionable opportunity at the moment — waiting for next verified batch."
                                 : "Resolve blockers above to surface proposals."}
        </div>
      )}

      {/* SECONDARY proposals */}
      {secondary.length > 0 && (
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="secondary-proposals">
          <button onClick={() => setShowSecondary((s) => !s)}
                  className="font-mono text-[10px] text-[#8b97a6] hover:text-[#c9d4e0] tracking-wider"
                  data-testid="secondary-toggle">
            ▾ SECONDARY ({secondary.length}) {showSecondary ? "▲" : "▼"}
          </button>
          {showSecondary && (
            <table className="w-full font-mono text-[10px] mt-2">
              <thead className="text-[#5a6573]">
                <tr className="border-b border-[#1f2a36]">
                  <th className="text-left py-1">Size</th>
                  <th className="text-right">Net ROI</th>
                  <th className="text-right">Quality</th>
                  <th className="text-right">Risk</th>
                  <th className="text-right">Regime</th>
                  <th className="text-right">Age</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {secondary.map((s) => (
                  <tr key={s.proposal_id} className="border-b border-[#0f1620]" data-testid={`secondary-${s.proposal_id}`}>
                    <td className="py-1 text-[#c9d4e0]">{fmtUsd(s.size_usd)}</td>
                    <td className="text-right text-[#34d399]">{pct(s.net_roi_pct)}</td>
                    <td className="text-right text-[#c9d4e0]">{num(s.quality_score, 1)}</td>
                    <td className="text-right" style={{ color: RISK_C[s.risk_label] || "#8b97a6" }}>{s.risk_label}</td>
                    <td className="text-right" style={{ color: REGIME_C[s.regime] || "#8b97a6" }}>{s.regime}</td>
                    <td className="text-right text-[#8b97a6]">{num(s.quote_age_s, 0)}s</td>
                    <td className="text-right">
                      <button onClick={() => approve(s.proposal_id, s.size_usd, "recommended")}
                              disabled={posting}
                              className="px-1.5 py-0.5 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 text-[9px] mr-1">approve</button>
                      <button onClick={() => reject(s.proposal_id, "operator")}
                              disabled={posting}
                              className="px-1.5 py-0.5 border border-[#f87171] text-[#f87171] hover:bg-[#f87171]/10 text-[9px]">reject</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="mt-3 font-mono text-[9px] text-[#3d4a59] text-center">
        Approval Required Mode · {proposed.actionable_count} actionable / {proposed.ranked_count} ranked · refreshed {fmtTime(proposed.now)}
      </div>
    </div>
  );
};

export default ApprovalConsole;
