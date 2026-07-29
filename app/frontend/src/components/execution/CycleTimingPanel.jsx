import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PRESETS = [50, 100, 250, 500, 1000];

const fmtPct = (v, d = 3) =>
  v == null ? "—" : `${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(d)}%`;
const fmtDur = (s) => {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m ${Math.round(s % 60)}s`;
  return `${(s / 3600).toFixed(1)}h`;
};
const fmtNum = (v, d = 2) =>
  v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d });

const RISK_C = { LOW: "#34d399", MEDIUM: "#ffb224", HIGH: "#f87171" };

export const CycleTimingPanel = () => {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [forecast, setForecast] = useState(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [form, setForm] = useState({ captured_price: "0.000036",
                                      best_bid: "0.0000394",
                                      investment_usd: "50",
                                      taker_fee_pct: "0.20" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/execution/cycle-timing?limit=100`);
      setReport(r.data);
    } catch (e) {
      toast.error(`Load failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runForecast = async () => {
    setForecastLoading(true);
    try {
      const r = await axios.get(`${API}/execution/cycle-timing/forecast`, {
        params: {
          captured_price: parseFloat(form.captured_price),
          best_bid: parseFloat(form.best_bid),
          investment_usd: parseFloat(form.investment_usd),
          taker_fee_pct: parseFloat(form.taker_fee_pct) || 0.2,
        },
      });
      setForecast(r.data);
    } catch (e) {
      toast.error(`Forecast failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setForecastLoading(false);
    }
  };

  if (!report) {
    return (
      <div className="panel" data-testid="cycle-timing-panel">
        <div className="panel-title">CYCLE TIMING + RISK DECAY</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
      </div>
    );
  }

  const closedN = report.closed_cycles_used || 0;
  const tot = report.total_duration_s || {};
  const stages = report.stage_durations_s || [];
  const drift = report.drift_distribution_pct || {};
  const endD = drift.end_drift_pct || {};
  const worstD = drift.worst_drift_pct || {};
  const bestD = drift.best_drift_pct || {};

  return (
    <div className="panel" data-testid="cycle-timing-panel">
      <div className="panel-title flex items-center justify-between flex-wrap gap-2">
        <span>CYCLE TIMING + RISK DECAY</span>
        <div className="flex items-center gap-2">
          <span
            className="text-[9px] font-bold tracking-widest px-2 py-0.5 border"
            style={{
              borderColor: closedN > 0 ? "#34d399" : "#ffb224",
              color: closedN > 0 ? "#34d399" : "#ffb224",
            }}
            data-testid="ct-history-badge"
          >
            {closedN} CLOSED CYCLES
          </span>
          <span className="text-[9px] font-bold tracking-widest px-2 py-0.5 border border-[#f87171] text-[#f87171]">
            READ-ONLY · NO SIGNING
          </span>
        </div>
      </div>

      {closedN === 0 && (
        <div
          className="mb-3 border border-[#ffb224]/40 bg-[#ffb224]/10 px-3 py-2 font-mono text-[10px] text-[#ffb224]"
          data-testid="ct-no-history-banner"
        >
          ⚠ No CLOSED cycles yet — duration + drift aggregates will populate once the first cycle reaches WITHDRAWN/CLOSED via the
          Wallet Observer (Iter9) or operator stamping. The forecast below still computes deterministic profit math without history.
        </div>
      )}

      {/* Top: total duration + summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-[#1f2a36] border border-[#1f2a36] font-mono mb-3" data-testid="ct-top-stats">
        <Tile lbl="Closed Cycles" v={fmtNum(closedN, 0)} c="#a78bfa" />
        <Tile lbl="Avg Cycle"     v={fmtDur(tot.avg)}    c="#c9d4e0" testid="ct-avg" />
        <Tile lbl="P95 Cycle"     v={fmtDur(tot.p95)}    c="#ffb224" testid="ct-p95" />
        <Tile lbl="Worst Cycle"   v={fmtDur(tot.worst)}  c="#f87171" testid="ct-worst" />
        <Tile lbl="Stdev"         v={fmtDur(tot.stdev)}  c="#38bdf8" />
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Stage-by-stage durations */}
        <div className="col-span-12 xl:col-span-7">
          <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="ct-stages">
            <div className="text-[10px] tracking-widest text-[#a78bfa] uppercase mb-2">
              Stage-by-Stage Durations (avg / median / p95 / worst)
            </div>
            <div className="overflow-x-auto">
              <table className="w-full font-mono text-[10px]" data-testid="ct-stages-table">
                <thead className="text-[#6b7888] uppercase tracking-widest">
                  <tr className="border-b border-[#1f2a36]">
                    <th className="text-left py-1 pr-2">Stage</th>
                    <th className="text-right pr-2">N</th>
                    <th className="text-right pr-2">Avg</th>
                    <th className="text-right pr-2">Median</th>
                    <th className="text-right pr-2">P95</th>
                    <th className="text-right">Worst</th>
                  </tr>
                </thead>
                <tbody className="text-[#c9d4e0]">
                  {stages.map((s) => (
                    <tr key={s.stage} className="border-b border-[#1f2a36]/60" data-testid={`ct-stage-${s.stage}`}>
                      <td className="py-1 pr-2">{s.stage.replace(/_/g, " ")}</td>
                      <td className="pr-2 text-right text-[#6b7888]">{s.count}</td>
                      <td className="pr-2 text-right">{fmtDur(s.avg)}</td>
                      <td className="pr-2 text-right">{fmtDur(s.median)}</td>
                      <td className="pr-2 text-right text-[#ffb224]">{fmtDur(s.p95)}</td>
                      <td className="text-right text-[#f87171]">{fmtDur(s.worst)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Drift distribution */}
        <div className="col-span-12 xl:col-span-5">
          <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="ct-drift">
            <div className="text-[10px] tracking-widest text-[#a78bfa] uppercase mb-2">
              Drift Distribution (Coinstore best_bid over cycle window)
            </div>
            <DriftBlock label="End-of-cycle drift"  d={endD} testid="ct-drift-end" />
            <DriftBlock label="Worst observed drift" d={worstD} testid="ct-drift-worst" tone="negative" />
            <DriftBlock label="Best observed drift"  d={bestD} testid="ct-drift-best" tone="positive" />
            <div className="font-mono text-[9px] text-[#6b7888] mt-2">
              {drift.samples_used ?? 0} cycles supplied drift samples. Each cycle's drift is measured against its own
              best_bid_at_quote anchor, using the Coinstore orderbook_snapshots inside the cycle window.
            </div>
          </div>
        </div>

        {/* Risk Decay Forecast */}
        <div className="col-span-12">
          <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="ct-forecast">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
              <div className="text-[10px] tracking-widest text-[#a78bfa] uppercase">
                Risk-Adjusted Profit Forecast (Risk Decay)
              </div>
              <div className="flex items-center gap-2">
                <button
                  data-testid="ct-forecast-run"
                  onClick={runForecast}
                  disabled={forecastLoading}
                  className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider"
                >
                  {forecastLoading ? "FORECASTING…" : "→ RUN FORECAST"}
                </button>
                <button
                  data-testid="ct-reload"
                  onClick={load}
                  disabled={loading}
                  className="px-3 py-1 border border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0] font-mono text-[10px] font-bold tracking-wider"
                >
                  ↻ RELOAD HISTORY
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3">
              <Field testid="ct-fc-captured" label="Captured BDAG price ($)" value={form.captured_price} onChange={(v) => setForm({ ...form, captured_price: v })} />
              <Field testid="ct-fc-bestbid"  label="Coinstore best bid ($)" value={form.best_bid} onChange={(v) => setForm({ ...form, best_bid: v })} />
              <div>
                <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Investment (USDT)</div>
                <div className="flex flex-wrap gap-1">
                  {PRESETS.map((p) => (
                    <button
                      key={p}
                      data-testid={`ct-fc-preset-${p}`}
                      type="button"
                      onClick={() => setForm({ ...form, investment_usd: String(p) })}
                      className={`px-2 py-0.5 font-mono text-[9px] border ${
                        String(p) === String(form.investment_usd)
                          ? "border-[#a78bfa] text-[#a78bfa] bg-[#a78bfa]/10"
                          : "border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0]"
                      }`}
                    >
                      ${p}
                    </button>
                  ))}
                </div>
                <input
                  data-testid="ct-fc-investment"
                  type="number"
                  value={form.investment_usd}
                  onChange={(e) => setForm({ ...form, investment_usd: e.target.value })}
                  className="w-full mt-1 bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[10px] text-[#c9d4e0]"
                />
              </div>
              <Field testid="ct-fc-takerfee" label="Coinstore taker fee %" value={form.taker_fee_pct} onChange={(v) => setForm({ ...form, taker_fee_pct: v })} />
            </div>

            {forecast?.available && <ForecastResult f={forecast} />}
            {forecast && forecast.available === false && (
              <div className="font-mono text-[10px] text-[#f87171]">{forecast.note}</div>
            )}
            {!forecast && (
              <div className="font-mono text-[10px] text-[#6b7888]">
                Tweak inputs and click <b>RUN FORECAST</b> — the engine applies historical drift distribution to the
                opportunity to compute risk-adjusted profit and the probability the profit disappears mid-cycle.
              </div>
            )}
          </div>
        </div>

        {/* Per-cycle rows (if any) */}
        {(report.per_cycle || []).length > 0 && (
          <div className="col-span-12">
            <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="ct-per-cycle">
              <div className="text-[10px] tracking-widest text-[#a78bfa] uppercase mb-2">Per-Cycle Detail</div>
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-[10px]">
                  <thead className="text-[#6b7888] uppercase tracking-widest">
                    <tr className="border-b border-[#1f2a36]">
                      <th className="text-left py-1 pr-2">Cycle</th>
                      <th className="text-left pr-2">Quote</th>
                      <th className="text-right pr-2">Total</th>
                      <th className="text-right pr-2">End Drift</th>
                      <th className="text-right pr-2">Worst Drift</th>
                      <th className="text-right pr-2">Realized ROI</th>
                      <th className="text-right">Net Profit</th>
                    </tr>
                  </thead>
                  <tbody className="text-[#c9d4e0]">
                    {report.per_cycle.map((c) => (
                      <tr key={c.cycle_id} className="border-b border-[#1f2a36]/60">
                        <td className="py-1 pr-2 text-[#34d399]">{(c.cycle_id || "").slice(0, 8)}…</td>
                        <td className="pr-2 text-[#6b7888]">{(c.quote_at || "").slice(11, 19)}</td>
                        <td className="pr-2 text-right">{fmtDur(c.total_duration_s)}</td>
                        <td className="pr-2 text-right" style={{ color: ((c.drift?.end_drift_pct) ?? 0) >= 0 ? "#34d399" : "#f87171" }}>
                          {fmtPct(c.drift?.end_drift_pct)}
                        </td>
                        <td className="pr-2 text-right text-[#f87171]">{fmtPct(c.drift?.worst_drift_pct)}</td>
                        <td className="pr-2 text-right" style={{ color: (c.realized_roi_pct ?? 0) >= 0 ? "#34d399" : "#f87171" }}>
                          {fmtPct(c.realized_roi_pct)}
                        </td>
                        <td className="text-right" style={{ color: (c.net_profit_usd ?? 0) >= 0 ? "#34d399" : "#f87171" }}>
                          {fmtUsd(c.net_profit_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="font-mono text-[10px] text-[#6b7888] mt-3">
        ◆ Cycle Timing + Risk Decay engine is read-only. Aggregates use REAL closed cycles only. The forecast applies the
        historical drift distribution to a hypothetical opportunity and surfaces the probability that profit disappears
        before the cycle completes (= % of historical cycles whose worst drift exceeded the spread).
      </div>
    </div>
  );
};

const Tile = ({ lbl, v, c = "#c9d4e0", testid }) => (
  <div className="bg-[#10161e] px-3 py-2" data-testid={testid}>
    <div className="text-[8px] tracking-widest text-[#6b7888] uppercase">{lbl}</div>
    <div className="text-base font-bold font-mono" style={{ color: c }}>{v}</div>
  </div>
);

const Field = ({ label, value, onChange, testid }) => (
  <div>
    <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">{label}</div>
    <input
      data-testid={testid}
      type="number"
      step="any"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[10px] text-[#c9d4e0]"
    />
  </div>
);

const DriftBlock = ({ label, d, testid, tone }) => {
  if (!d || (d.count ?? 0) === 0) {
    return (
      <div className="mb-2" data-testid={testid}>
        <div className="text-[9px] uppercase tracking-widest text-[#6b7888]">{label}</div>
        <div className="text-[10px] font-mono text-[#6b7888]">no samples yet</div>
      </div>
    );
  }
  const avgC = tone === "negative" ? "#f87171" : tone === "positive" ? "#34d399" : "#c9d4e0";
  return (
    <div className="mb-2" data-testid={testid}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[9px] uppercase tracking-widest text-[#6b7888]">{label}</span>
        <span className="text-[9px] text-[#6b7888]">n={d.count}</span>
      </div>
      <div className="grid grid-cols-5 gap-1 mt-1 font-mono text-[10px]">
        <span className="text-[#6b7888]">avg</span>
        <span className="text-[#6b7888]">p5</span>
        <span className="text-[#6b7888]">p50</span>
        <span className="text-[#6b7888]">p95</span>
        <span className="text-[#6b7888]">{tone === "negative" ? "worst" : "best"}</span>

        <span style={{ color: avgC }}>{fmtPct(d.avg, 3)}</span>
        <span>{fmtPct(d.p5, 3)}</span>
        <span>{fmtPct(d.median, 3)}</span>
        <span>{fmtPct(d.p95, 3)}</span>
        <span style={{ color: tone === "negative" ? "#f87171" : "#34d399" }}>
          {fmtPct(tone === "negative" ? d.worst : d.best, 3)}
        </span>
      </div>
    </div>
  );
};

const ForecastResult = ({ f }) => {
  const profitC = (v) => ((v ?? 0) >= 0 ? "#34d399" : "#f87171");
  const probDis = f.probability_profit_disappears;
  const probColor = probDis == null
    ? "#6b7888"
    : probDis >= 0.5 ? "#f87171" : probDis >= 0.05 ? "#ffb224" : "#34d399";
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3" data-testid="ct-forecast-result">
      {/* Profit ladder */}
      <div className="border border-[#1f2a36] bg-[#10161e] p-3 md:col-span-2">
        <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-2">Risk-Adjusted Profit Ladder</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-[#1f2a36] border border-[#1f2a36] font-mono">
          <Tile lbl="Expected (raw)" v={fmtUsd(f.expected_profit_usd)} c={profitC(f.expected_profit_usd)} testid="ct-fc-expected" />
          <Tile lbl="Avg-drift adjusted" v={fmtUsd(f.risk_adjusted_profit_avg_usd)} c={profitC(f.risk_adjusted_profit_avg_usd)} testid="ct-fc-avg" />
          <Tile lbl="P5-drift adjusted" v={fmtUsd(f.risk_adjusted_profit_p5_usd)} c={profitC(f.risk_adjusted_profit_p5_usd)} testid="ct-fc-p5" />
          <Tile lbl="Worst-drift adjusted" v={fmtUsd(f.risk_adjusted_profit_worst_usd)} c={profitC(f.risk_adjusted_profit_worst_usd)} testid="ct-fc-worst" />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 mt-2 text-[10px] font-mono text-[#6b7888]">
          <span>spread {fmtPct(f.spread_pct, 3)}</span>
          <span>gross ${fmtNum(f.expected_gross_proceeds_usd, 2)}</span>
          <span>fees ${fmtNum(f.trading_fee_usd, 4)}</span>
          <span>breakeven drift {fmtPct(f.breakeven_drift_pct, 3)}</span>
        </div>
      </div>

      {/* Probability profit disappears */}
      <div className="border border-[#1f2a36] bg-[#10161e] p-3" data-testid="ct-fc-prob">
        <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-2">Probability profit disappears</div>
        <div className="font-mono text-4xl font-bold" style={{ color: probColor }} data-testid="ct-fc-prob-value">
          {probDis == null ? "—" : `${(probDis * 100).toFixed(1)}%`}
        </div>
        <div className="font-mono text-[9px] text-[#6b7888] mt-1">
          history n={f.history_samples_used} · avg cycle {fmtDur(f.expected_cycle_duration_s_avg)} · p95 {fmtDur(f.expected_cycle_duration_s_p95)}
        </div>
        <div className="font-mono text-[9px] text-[#6b7888] mt-2">
          Bracketed estimate from the worst-drift percentile ladder. Treat as a directional risk gauge until ≥20
          cycles seed the distribution.
        </div>
      </div>
    </div>
  );
};
