import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtUsd, fmtTime } from "@/lib/fmt";
import { FreshnessBadge } from "@/components/execution/FreshnessBadge";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const REGIME_COLOR = {
  Stable: { c: "#34d399", bg: "rgba(52,211,153,0.10)" },
  Volatile: { c: "#ffb224", bg: "rgba(255,178,36,0.10)" },
  "Extremely Volatile": { c: "#f87171", bg: "rgba(248,113,113,0.10)" },
};
const RISK_COLOR = {
  LOW: "#34d399",
  MEDIUM: "#ffb224",
  HIGH: "#fb8b3a",
  VERY_HIGH: "#f87171",
};

const PRIMARY_HORIZONS_S = [30, 60, 120, 300, 600, 900];
const SECONDARY_HORIZONS_S = [1800, 3600, 7200];
const SPREADS_PCT = [2, 5, 8, 10, 12, 15];
const DEPTH_BANDS = [1, 2, 5, 10];
const CYCLE_DURATIONS_S = [60, 120, 300, 600, 900, 1800, 3600];

const horizonLabel = (s) => {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${s / 60}m`;
  return `${s / 3600}h`;
};

const pct = (v) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`);
const pctRaw = (v) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const num = (v, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

// Color a survival probability cell: green → red gradient
const survColor = (p) => {
  if (p == null) return "#1f2a36";
  if (p >= 0.9) return "rgba(52,211,153,0.32)";
  if (p >= 0.75) return "rgba(52,211,153,0.18)";
  if (p >= 0.5) return "rgba(255,178,36,0.20)";
  if (p >= 0.25) return "rgba(251,139,58,0.22)";
  return "rgba(248,113,113,0.28)";
};

export const HistoricalDriftPanel = () => {
  const [snap, setSnap] = useState(null);
  const [hist, setHist] = useState([]);
  const [loading, setLoading] = useState(false);
  const [runError, setRunError] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/drift-analysis`).then((r) => setSnap(r.data)).catch(() => {});
    axios.get(`${API}/execution/drift-analysis/history?limit=20`).then((r) => setHist(r.data.snapshots || [])).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  const recompute = useCallback(async () => {
    setLoading(true);
    setRunError(null);
    try {
      await axios.post(`${API}/execution/drift-analysis/run`, {});
      await load();
    } catch (e) {
      setRunError(e?.response?.data?.detail || String(e));
    } finally {
      setLoading(false);
    }
  }, [load]);

  if (!snap) {
    return (
      <div className="panel" data-testid="drift-panel">
        <div className="panel-title">Historical Drift Analyzer</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center">loading…</div>
      </div>
    );
  }

  // Pre-snapshot state (no data yet)
  if (snap.available === false) {
    return (
      <div className="panel" data-testid="drift-panel">
        <div className="panel-title">
          Historical Drift Analyzer
          <span className="float-right text-[#3d4a59]">parallel intelligence · read-only</span>
        </div>
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-4 font-mono text-[11px] text-[#8b97a6]">
          <div data-testid="drift-empty-state">{snap.note}</div>
          <button
            data-testid="drift-recompute-btn"
            disabled={loading}
            onClick={recompute}
            className="mt-3 px-3 py-1.5 border border-[#34d39966] text-[#34d399] hover:bg-[#34d39911] text-[10px] tracking-wider uppercase"
          >
            {loading ? "computing…" : "compute now"}
          </button>
          {runError && <div className="text-[#f87171] mt-2" data-testid="drift-recompute-error">{runError}</div>}
        </div>
      </div>
    );
  }

  const regime = snap.regime || {};
  const rs = snap.risk_score || {};
  const cap = snap.opportunity_capacity || {};
  const drift = snap.drift || {};
  const surv = snap.survivability || {};
  const liq = snap.liquidity_survivability || {};
  const dur = snap.cycle_duration_map || {};
  const samples = snap.sample_count_summary || {};
  const regColor = REGIME_COLOR[regime.label] || REGIME_COLOR.Volatile;

  return (
    <div className="panel" data-testid="drift-panel">
      <div className="panel-title">
        Historical Drift Analyzer · {snap.symbol} @ {snap.venue}
        <span className="float-right inline-flex items-center gap-2 text-[#3d4a59]">
          <FreshnessBadge invalid={false} stale={false} showAge={false} testid="drift-freshness" />
          parallel intelligence · read-only
        </span>
      </div>

      {/* Headline strip — regime + risk + capacity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-3">
        {/* Regime */}
        <div
          className="border p-3"
          style={{ borderColor: regColor.c + "55", background: regColor.bg }}
          data-testid="drift-regime-card"
        >
          <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase">Market Regime</div>
          <div data-testid="drift-regime-label" className="font-mono text-2xl font-bold" style={{ color: regColor.c }}>
            {regime.label || "—"}
          </div>
          <div className="font-mono text-[10px] text-[#8b97a6] mt-1">
            realized vol 1h:&nbsp;<b className="text-[#c9d4e0]">{pct(regime.realized_vol_1h_pct)}</b>
            <br />
            drift p95 @ 5m:&nbsp;<b className="text-[#c9d4e0]">{pct(regime.drift_p95_at_5min_pct)}</b>
            <br />
            liq stability:&nbsp;<b className="text-[#c9d4e0]">{pctRaw(regime.liquidity_stability_score)}</b>
          </div>
        </div>

        {/* Risk-adjusted score */}
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="drift-risk-card">
          <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase">Risk-Adjusted Opportunity</div>
          <div className="flex items-baseline gap-3">
            <div
              data-testid="drift-risk-label"
              className="font-mono text-2xl font-bold"
              style={{ color: RISK_COLOR[rs.label] || "#8b97a6" }}
            >
              {rs.label || "—"}
            </div>
            <div className="font-mono text-sm text-[#c9d4e0]" data-testid="drift-risk-score">
              {num(rs.score_0_100, 1)}/100
            </div>
          </div>
          <div className="font-mono text-[10px] text-[#8b97a6] mt-1 leading-5">
            current spread:&nbsp;<b className="text-[#c9d4e0]">{pct(rs.components?.current_spread_pct)}</b>
            <br />
            expected drift:&nbsp;<b className="text-[#c9d4e0]">{pct(rs.components?.expected_drift_pct)}</b>
            <span className="text-[#5a6573]">&nbsp;· p95:&nbsp;</span>
            <b className="text-[#c9d4e0]">{pct(rs.components?.p95_drift_pct)}</b>
            <br />
            risk-adj profit:&nbsp;<b className="text-[#34d399]">{pct(rs.risk_adjusted_profit_pct)}</b>
            <span className="text-[#5a6573]">&nbsp;@&nbsp;</span>
            <b className="text-[#c9d4e0]">{fmtUsd(rs.risk_adjusted_profit_usd_at_recommended)}</b>
          </div>
        </div>

        {/* Opportunity capacity */}
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="drift-capacity-card">
          <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase">Opportunity Capacity</div>
          <div className="font-mono text-2xl font-bold text-[#c9d4e0]" data-testid="drift-capacity-score">
            {num(cap.opportunity_capacity_score_0_100, 0)}<span className="text-sm text-[#5a6573]">/100</span>
          </div>
          <div className="font-mono text-[10px] text-[#8b97a6] mt-1 leading-5">
            min buy (BDAG floor):&nbsp;<b className="text-[#c9d4e0]">{fmtUsd(cap.min_buy_usd)}</b>
            <br />
            max buy (depth @ {num(cap.profitable_target_pct, 0)}%):&nbsp;
            <b className="text-[#c9d4e0]">{fmtUsd(cap.max_buy_usd)}</b>
            <br />
            recommended:&nbsp;
            <b style={{ color: cap.feasible ? "#34d399" : "#f87171" }} data-testid="drift-recommended-usd">
              {fmtUsd(cap.recommended_buy_usd)}
            </b>
            {!cap.feasible && (
              <span className="text-[#f87171] block text-[9px] mt-0.5">
                ✗ Depth at target threshold below ${num(cap.min_buy_usd, 0)} floor
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Drift distribution table */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-3 mb-3" data-testid="drift-distribution-table">
        <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase mb-2">
          Drift Distribution &middot; Primary Horizons (BDAG flip workflow)
        </div>
        <div className="overflow-x-auto">
          <table className="w-full font-mono text-[10px]">
            <thead className="text-[#5a6573]">
              <tr className="border-b border-[#1f2a36]">
                <th className="text-left py-1 pr-2">Horizon</th>
                <th className="text-right">Samples</th>
                <th className="text-right">Avg</th>
                <th className="text-right">Median</th>
                <th className="text-right">Worst</th>
                <th className="text-right">P95 adv.</th>
                <th className="text-right">P99 adv.</th>
                <th className="text-right">Stdev</th>
                <th className="text-right pl-2">Source</th>
              </tr>
            </thead>
            <tbody>
              {PRIMARY_HORIZONS_S.map((h) => {
                const d = drift[String(h)] || {};
                return (
                  <tr key={h} className="border-b border-[#0f1620]" data-testid={`drift-row-${h}`}>
                    <td className="py-1 text-[#c9d4e0] font-bold">{horizonLabel(h)}</td>
                    <td className="text-right text-[#8b97a6]">{d.samples ?? "—"}</td>
                    <td className="text-right text-[#c9d4e0]">{pct(d.avg_pct)}</td>
                    <td className="text-right text-[#8b97a6]">{pct(d.median_pct)}</td>
                    <td className="text-right text-[#f87171]">{pct(d.worst_pct)}</td>
                    <td className="text-right text-[#ffb224]">{pct(d.p95_adverse_pct)}</td>
                    <td className="text-right text-[#fb8b3a]">{pct(d.p99_adverse_pct)}</td>
                    <td className="text-right text-[#8b97a6]">{pct(d.stdev_pct)}</td>
                    <td className="text-right text-[#5a6573] pl-2">{d.source || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <details className="mt-2">
          <summary className="font-mono text-[9px] text-[#5a6573] uppercase tracking-wider cursor-pointer hover:text-[#8b97a6]">
            Secondary horizons (informational only)
          </summary>
          <table className="w-full font-mono text-[10px] mt-2">
            <tbody>
              {SECONDARY_HORIZONS_S.map((h) => {
                const d = drift[String(h)] || {};
                return (
                  <tr key={h} className="border-b border-[#0f1620]" data-testid={`drift-row-${h}`}>
                    <td className="py-1 text-[#8b97a6] font-bold">{horizonLabel(h)}</td>
                    <td className="text-right text-[#5a6573]">n={d.samples ?? "—"}</td>
                    <td className="text-right text-[#8b97a6]">avg {pct(d.avg_pct)}</td>
                    <td className="text-right text-[#f87171]">worst {pct(d.worst_pct)}</td>
                    <td className="text-right text-[#ffb224]">p95 {pct(d.p95_adverse_pct)}</td>
                    <td className="text-right text-[#5a6573] pl-2">{d.source || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      </div>

      {/* Survivability matrix */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-3 mb-3" data-testid="drift-survivability-matrix">
        <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase mb-2">
          Opportunity Survivability Matrix &middot; P(spread survives) by horizon
        </div>
        <div className="overflow-x-auto">
          <table className="w-full font-mono text-[10px]">
            <thead className="text-[#5a6573]">
              <tr className="border-b border-[#1f2a36]">
                <th className="text-left py-1 pr-2">Spread</th>
                {PRIMARY_HORIZONS_S.map((h) => (
                  <th key={h} className="text-right">{horizonLabel(h)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SPREADS_PCT.map((s) => (
                <tr key={s} className="border-b border-[#0f1620]" data-testid={`surv-row-${s}`}>
                  <td className="py-1 text-[#c9d4e0] font-bold">{s}%</td>
                  {PRIMARY_HORIZONS_S.map((h) => {
                    const cell = surv.matrix?.[String(s)]?.[String(h)] || {};
                    return (
                      <td
                        key={h}
                        className="text-right"
                        style={{ background: survColor(cell.survival_prob) }}
                        data-testid={`surv-${s}-${h}`}
                        title={`expected remaining: ${pct(cell.expected_remaining_pct)}`}
                      >
                        {cell.survival_prob == null ? "—" : pctRaw(cell.survival_prob)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="font-mono text-[9px] text-[#5a6573] mt-1.5">
          {surv.method || "—"}
        </div>
      </div>

      {/* Liquidity survivability */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-3">
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="drift-liquidity-depth">
          <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase mb-2">
            Bid Depth Stability ({liq.samples} snaps · {liq.window_minutes}min)
          </div>
          <table className="w-full font-mono text-[10px]">
            <thead className="text-[#5a6573]">
              <tr className="border-b border-[#1f2a36]">
                <th className="text-left py-1 pr-2">Band</th>
                <th className="text-right">Mean</th>
                <th className="text-right">Median</th>
                <th className="text-right">Min</th>
                <th className="text-right">P5 worst</th>
                <th className="text-right pl-2">Avail.</th>
              </tr>
            </thead>
            <tbody>
              {DEPTH_BANDS.map((b) => {
                const d = liq.depth_stability?.[String(b)] || {};
                return (
                  <tr key={b} className="border-b border-[#0f1620]" data-testid={`depth-band-${b}`}>
                    <td className="py-1 text-[#c9d4e0] font-bold">{b}%</td>
                    <td className="text-right text-[#c9d4e0]">{fmtUsd(d.mean_usd)}</td>
                    <td className="text-right text-[#8b97a6]">{fmtUsd(d.median_usd)}</td>
                    <td className="text-right text-[#f87171]">{fmtUsd(d.min_usd)}</td>
                    <td className="text-right text-[#ffb224]">{fmtUsd(d.p5_worst_usd)}</td>
                    <td className="text-right text-[#34d399] pl-2">{pctRaw(d.availability_pct)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="font-mono text-[10px] text-[#8b97a6] mt-2">
            decay rate (depth@2%):&nbsp;
            <b className="text-[#fb8b3a]" data-testid="liquidity-decay-rate">
              {num(liq.liquidity_decay_rate_pct_per_sample, 2)}%
              {liq.liquidity_decay_sample_interval_s && (
                <span className="text-[#5a6573]"> /{num(liq.liquidity_decay_sample_interval_s, 0)}s sample</span>
              )}
            </b>
          </div>
        </div>

        <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="drift-buyer-disappearance">
          <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase mb-2">
            Buyer Disappearance Probability &middot; P(depth@2% &lt; $50)
          </div>
          <table className="w-full font-mono text-[10px]">
            <thead className="text-[#5a6573]">
              <tr className="border-b border-[#1f2a36]">
                <th className="text-left py-1 pr-2">Horizon</th>
                <th className="text-right">Probability</th>
              </tr>
            </thead>
            <tbody>
              {[...PRIMARY_HORIZONS_S, ...SECONDARY_HORIZONS_S].map((h) => {
                const p = liq.buyer_disappearance_prob?.[String(h)];
                const color = p == null ? "#5a6573" :
                  p < 0.10 ? "#34d399" : p < 0.30 ? "#ffb224" : "#f87171";
                return (
                  <tr key={h} className="border-b border-[#0f1620]" data-testid={`buyer-dis-${h}`}>
                    <td className="py-1 text-[#c9d4e0]">{horizonLabel(h)}</td>
                    <td className="text-right font-bold" style={{ color }}>{pctRaw(p)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cycle-duration mapping */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-3 mb-3" data-testid="drift-cycle-duration">
        <div className="font-mono text-[9px] text-[#6b7888] tracking-widest uppercase mb-2">
          Cycle-Duration Mapping &middot; expected: <span className="text-[#34d399]">{horizonLabel(dur.current_expected_cycle_s)}</span> ({dur.current_cycle_source})
        </div>
        <table className="w-full font-mono text-[10px]">
          <thead className="text-[#5a6573]">
            <tr className="border-b border-[#1f2a36]">
              <th className="text-left py-1 pr-2">Cycle takes</th>
              <th className="text-right">Price survival</th>
              <th className="text-right">Liquidity survival</th>
              <th className="text-right pl-2">Combined</th>
            </tr>
          </thead>
          <tbody>
            {CYCLE_DURATIONS_S.map((d) => {
              const r = dur.rows?.[String(d)] || {};
              const isExp = d === dur.current_expected_cycle_s;
              return (
                <tr key={d} className="border-b border-[#0f1620]" data-testid={`cycle-dur-${d}`}
                    style={isExp ? { background: "rgba(52,211,153,0.06)" } : undefined}>
                  <td className="py-1 text-[#c9d4e0] font-bold">{horizonLabel(d)}{isExp && <span className="text-[#34d399] text-[9px] ml-1">▶</span>}</td>
                  <td className="text-right text-[#c9d4e0]">{pctRaw(r.price_survival_prob)}</td>
                  <td className="text-right text-[#8b97a6]">{pctRaw(r.liquidity_survival_prob)}</td>
                  <td className="text-right font-bold pl-2"
                      style={{ color: r.combined_survival_prob > 0.7 ? "#34d399" :
                                       r.combined_survival_prob > 0.4 ? "#ffb224" : "#f87171" }}>
                    {pctRaw(r.combined_survival_prob)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer: provenance + actions */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 flex items-center justify-between flex-wrap gap-2">
        <div className="font-mono text-[9px] text-[#5a6573] leading-4">
          <div>
            computed at <span className="text-[#8b97a6]">{fmtTime(snap.computed_at)}</span> &middot;
            {" "}{num(snap.compute_time_ms, 0)}ms &middot; samples:&nbsp;
            1m={samples.candles_1m} 5m={samples.candles_5m} 15m={samples.candles_15m} ob={samples.orderbook_snapshots}
          </div>
          <div>
            model: {snap.model?.kind} &middot; prior weight {num(snap.model?.prior_weight, 2)} &middot;
            calibrated on {snap.model?.calibration_n || 0} closed cycles
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[#5a6573] font-mono text-[9px]">history: {hist.length} pts</span>
          <button
            data-testid="drift-recompute-btn"
            disabled={loading}
            onClick={recompute}
            className="px-3 py-1 border border-[#34d39966] text-[#34d399] hover:bg-[#34d39911] text-[10px] tracking-wider uppercase font-mono disabled:opacity-50"
          >
            {loading ? "computing…" : "recompute now"}
          </button>
        </div>
      </div>
      {runError && <div className="text-[#f87171] mt-2 font-mono text-[10px]" data-testid="drift-recompute-error">{runError}</div>}
    </div>
  );
};
