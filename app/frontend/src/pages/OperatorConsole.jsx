import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtUsd, fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PRESETS = [50, 100, 250, 500, 1000];

const fmtPrice = (v) => (v == null ? "—" : Number(v).toExponential(4));
const fmtPct = (v, signed = true) =>
  v == null ? "—" : `${signed && v > 0 ? "+" : ""}${Number(v).toFixed(3)}%`;
const fmtNum = (v, d = 2) =>
  v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d });
const fmtDur = (s) => {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m ${Math.round(s % 60)}s`;
  return `${Math.round(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
};

const VERDICT_C = {
  HIGH_CONFIDENCE: "#34d399",
  TRADEABLE: "#ffb224",
  NOT_TRADEABLE: "#f87171",
};
const RISK_C = { LOW: "#34d399", MEDIUM: "#ffb224", HIGH: "#f87171" };
const STAB_C = { STABLE: "#34d399", MODERATE: "#ffb224", VOLATILE: "#f87171" };

const Section = ({ title, badge, badgeColor, children, testid }) => (
  <div className="panel" data-testid={testid}>
    <div className="panel-title flex items-center justify-between">
      <span>{title}</span>
      {badge && (
        <span
          className="text-[9px] font-bold tracking-widest px-2 py-0.5 border"
          style={{ borderColor: (badgeColor || "#6b7888") + "66", color: badgeColor || "#6b7888" }}
          data-testid={`${testid}-badge`}
        >
          {badge}
        </span>
      )}
    </div>
    {children}
  </div>
);

const StatTile = ({ label, value, color = "#c9d4e0", testid }) => (
  <div className="bg-[#10161e] px-3 py-2" data-testid={testid}>
    <div className="text-[8px] tracking-widest text-[#6b7888] uppercase">{label}</div>
    <div className="text-lg font-bold font-mono" style={{ color }}>
      {value}
    </div>
  </div>
);

const Banner = ({ tone, label, value, sub, testid }) => {
  const c = tone || "#6b7888";
  return (
    <div className="border p-4 mb-4" style={{ borderColor: c + "66", background: c + "1a" }} data-testid={testid}>
      <div className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <div className="text-[9px] tracking-widest uppercase" style={{ color: c }}>
            {label}
          </div>
          <div className="font-mono text-3xl font-bold mt-0.5" style={{ color: c }} data-testid={`${testid}-value`}>
            {value}
          </div>
        </div>
        {sub && <div className="font-mono text-[10px] text-[#c9d4e0] max-w-[680px] flex-1">{sub}</div>}
      </div>
    </div>
  );
};

export default function OperatorConsole() {
  const [size, setSize] = useState("50");
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (amt) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/execution/operator-console`, {
        params: { investment_usd: parseFloat(amt) || 50 },
      });
      setD(r.data);
    } catch (e) {
      toast.error(`Console load failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const sizeRef = useRef(size);
  useEffect(() => {
    sizeRef.current = size;
  }, [size]);

  useEffect(() => {
    const fetcher = () => load(sizeRef.current);
    fetcher();
    const t = setInterval(fetcher, 15000);
    return () => clearInterval(t);
  }, [load]);

  if (!d) {
    return (
      <div className="px-4 pb-10 max-w-[1500px] mx-auto" data-testid="operator-console-page">
        <div className="font-mono text-sm text-[#6b7888] py-10">loading operator console…</div>
      </div>
    );
  }

  const m = d.monitor || {};
  const risk = d.risk || {};
  const v = d.verdict || {};
  const qv = d.quote_verification || {};
  const a = d.actions || {};
  const verdictColor = VERDICT_C[v.verdict] || "#6b7888";
  const riskColor = RISK_C[risk.risk_level] || "#6b7888";
  const stabColor = STAB_C[risk.buyer_stability_label] || "#6b7888";

  const openLink = (url) => {
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="px-4 pb-10 max-w-[1500px] mx-auto" data-testid="operator-console-page">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 py-3 border-b border-[#1f2a36] mb-4">
        <div className="font-mono text-sm font-bold tracking-wider">OPERATOR CONSOLE</div>
        <span className="text-[10px] font-mono text-[#38bdf8]" data-testid="oc-phase">
          {d.phase}
        </span>
        <div className="flex-1" />
        <span
          className="text-[10px] font-mono font-bold px-2 py-0.5 border border-[#f87171] text-[#f87171]"
          data-testid="oc-execution-disabled"
        >
          EXECUTION DISABLED · HUMAN-IN-THE-LOOP
        </span>
        {loading && <span className="text-[10px] font-mono text-[#38bdf8]">↻ refreshing</span>}
      </div>

      {/* Guardrails strip */}
      <div
        className="mb-4 border px-3 py-2 font-mono text-[11px]"
        style={{ borderColor: "rgba(248,113,113,0.4)", background: "rgba(248,113,113,0.05)", color: "#f87171" }}
        data-testid="oc-guardrails-banner"
      >
        ◆ NO transaction signing. NO transaction submission. NO autonomous execution. NO fund movement. Operator
        remains the final authority — every button below is a workflow helper only.
      </div>

      {/* Verdict banner (top) */}
      <Banner
        tone={verdictColor}
        label="OPPORTUNITY VERDICT"
        value={(v.verdict || "—").replace("_", " ")}
        sub={(v.reasons || []).map((r, i) => (
          <div key={i}>• {r}</div>
        ))}
        testid="oc-verdict-banner"
      />

      {/* Size selector */}
      <div
        className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-4 flex flex-wrap items-center gap-2"
        data-testid="oc-size-form"
      >
        <span className="text-[9px] uppercase tracking-widest text-[#6b7888] mr-1">Investment size (USDT)</span>
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            data-testid={`oc-size-${p}`}
            onClick={() => {
              setSize(String(p));
              load(String(p));
            }}
            className={`px-2.5 py-1 font-mono text-[10px] font-bold border ${
              String(p) === String(size)
                ? "border-[#a78bfa] text-[#a78bfa] bg-[#a78bfa]/10"
                : "border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0]"
            }`}
          >
            ${p}
          </button>
        ))}
        <input
          data-testid="oc-size-input"
          type="number"
          step="any"
          min="0"
          value={size}
          onChange={(e) => setSize(e.target.value)}
          className="bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0] w-32"
        />
        <button
          data-testid="oc-size-submit"
          onClick={() => load(size)}
          disabled={loading}
          className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider"
        >
          {loading ? "LOADING…" : "→ REFRESH"}
        </button>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* 1. Live Opportunity Monitor */}
        <div className="col-span-12">
          <Section
            title="1. LIVE OPPORTUNITY MONITOR"
            badge={m.venue ? m.venue.toUpperCase() : "—"}
            badgeColor="#38bdf8"
            testid="oc-monitor"
          >
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-px bg-[#1f2a36] border border-[#1f2a36] font-mono">
              <StatTile
                label="Captured BDAG Price"
                value={`$${fmtPrice(m.captured_bdag_price)}`}
                color="#a78bfa"
                testid="oc-monitor-captured-price"
              />
              <StatTile
                label="Coinstore Best Bid"
                value={`$${fmtPrice(m.coinstore_best_bid)}`}
                color="#34d399"
                testid="oc-monitor-best-bid"
              />
              <StatTile
                label="Book Depth (BDAG)"
                value={fmtNum(m.coinstore_orderbook_depth_base, 0)}
                testid="oc-monitor-depth-base"
              />
              <StatTile
                label="Book Depth (USDT)"
                value={fmtUsd(m.coinstore_orderbook_depth_quote)}
                testid="oc-monitor-depth-quote"
              />
              <StatTile
                label="Gross Spread"
                value={fmtPct(m.gross_spread_pct)}
                color={(m.gross_spread_pct ?? 0) > 0 ? "#34d399" : "#f87171"}
                testid="oc-monitor-gross-spread"
              />
              <StatTile
                label="Net Spread"
                value={fmtPct(m.net_spread_pct)}
                color={(m.net_spread_pct ?? 0) > 0 ? "#34d399" : "#f87171"}
                testid="oc-monitor-net-spread"
              />
              <StatTile
                label={`Net Profit @ $${size}`}
                value={fmtUsd(m.net_profit_usd)}
                color={(m.net_profit_usd ?? 0) > 0 ? "#34d399" : "#f87171"}
                testid="oc-monitor-net-profit"
              />
            </div>
            <div className="font-mono text-[10px] text-[#6b7888] mt-2">
              Captured-price source: <b className="text-[#c9d4e0]">{m.captured_price_source || "—"}</b> · age{" "}
              <b className="text-[#c9d4e0]">{m.captured_price_age_s == null ? "—" : `${m.captured_price_age_s}s`}</b>
              {" · "} Order-book levels: <b className="text-[#c9d4e0]">{m.coinstore_total_levels ?? "—"}</b>
            </div>
          </Section>
        </div>

        {/* 2. Cycle Risk Engine */}
        <div className="col-span-12">
          <Section
            title="2. CYCLE RISK ENGINE"
            badge={risk.risk_level || "—"}
            badgeColor={riskColor}
            testid="oc-risk"
          >
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-px bg-[#1f2a36] border border-[#1f2a36] font-mono">
              <StatTile
                label="Closed Cycles Observed"
                value={fmtNum(risk.closed_cycles_observed, 0)}
                testid="oc-risk-cycles"
              />
              <StatTile
                label="Avg Cycle Duration"
                value={fmtDur(risk.avg_cycle_duration_s)}
                testid="oc-risk-avg-dur"
              />
              <StatTile
                label="Worst Cycle Duration"
                value={fmtDur(risk.worst_cycle_duration_s)}
                color="#f87171"
                testid="oc-risk-worst-dur"
              />
              <StatTile
                label="Buyer Stability"
                value={risk.buyer_stability_label || "—"}
                color={stabColor}
                testid="oc-risk-stability"
              />
              <StatTile
                label="Best-Bid CV"
                value={risk.best_bid_cv_pct == null ? "—" : `${risk.best_bid_cv_pct}%`}
                testid="oc-risk-cv"
              />
              <StatTile
                label="Drift Risk Estimate"
                value={risk.drift_estimate_pct_over_cycle == null ? "—" : `${risk.drift_estimate_pct_over_cycle}%`}
                color={riskColor}
                testid="oc-risk-drift"
              />
            </div>
            <div className="font-mono text-[10px] text-[#6b7888] mt-2 flex flex-wrap items-center gap-x-6 gap-y-1">
              <div>
                Risk-adjusted profit:{" "}
                <b
                  style={{ color: (risk.risk_adjusted_profit_usd ?? 0) > 0 ? "#34d399" : "#f87171" }}
                  data-testid="oc-risk-adjusted-profit"
                >
                  {fmtUsd(risk.risk_adjusted_profit_usd)}
                </b>
              </div>
              <div>
                Probability profit disappears:{" "}
                <b
                  style={{
                    color:
                      risk.probability_profit_disappears == null
                        ? "#6b7888"
                        : risk.probability_profit_disappears >= 0.5
                          ? "#f87171"
                          : risk.probability_profit_disappears >= 0.05
                            ? "#ffb224"
                            : "#34d399",
                  }}
                  data-testid="oc-risk-prob-disappear"
                >
                  {risk.probability_profit_disappears == null
                    ? "—"
                    : `${(risk.probability_profit_disappears * 100).toFixed(1)}%`}
                </b>
              </div>
              <div>
                Historical worst drift:{" "}
                <b className="text-[#f87171]" data-testid="oc-risk-hist-worst-drift">
                  {risk.historical_worst_drift_pct == null
                    ? "—"
                    : `${Number(risk.historical_worst_drift_pct).toFixed(3)}%`}
                </b>
              </div>
              <div className="text-[#3d4a59]">{risk.note}</div>
            </div>
            {risk.closed_cycles_observed === 0 && (
              <div
                className="mt-2 border border-[#ffb224]/40 bg-[#ffb224]/10 px-3 py-2 font-mono text-[10px] text-[#ffb224]"
                data-testid="oc-risk-no-cycles"
              >
                ⚠ No closed cycles recorded yet — duration metrics will populate after the first manual cycle is
                stamped through the Arbitrage Cycle tracker.
              </div>
            )}
          </Section>
        </div>

        {/* 3. Opportunity Verdict (detail) */}
        <div className="col-span-12 xl:col-span-7">
          <Section title="3. OPPORTUNITY VERDICT" badge={(v.verdict || "—").replace("_", " ")} badgeColor={verdictColor} testid="oc-verdict-detail">
            <div className="font-mono text-[11px] text-[#c9d4e0] space-y-1 mb-3" data-testid="oc-verdict-reasons">
              {(v.reasons || []).map((r, i) => (
                <div key={i}>• {r}</div>
              ))}
            </div>
            <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 font-mono text-[10px] text-[#6b7888] space-y-1">
              {Object.entries(v.definitions || {}).map(([k, val]) => (
                <div key={k}>
                  <b style={{ color: VERDICT_C[k] || "#c9d4e0" }}>{k.replace("_", " ")}</b> — {val}
                </div>
              ))}
            </div>
          </Section>
        </div>

        {/* 4. Quote Verification */}
        <div className="col-span-12 xl:col-span-5">
          <Section
            title="4. QUOTE VERIFICATION"
            badge={qv.fresh ? "FRESH" : qv.available ? "STALE" : "MISSING"}
            badgeColor={qv.fresh ? "#34d399" : qv.available ? "#ffb224" : "#f87171"}
            testid="oc-quote"
          >
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[10px] text-[#c9d4e0]">
              <div className="text-[#6b7888]">
                Captured At: <b className="text-[#c9d4e0]" data-testid="oc-quote-captured-at">{fmtTime(qv.captured_at)}</b>
              </div>
              <div className="text-[#6b7888]">
                Age:{" "}
                <b
                  style={{ color: qv.fresh ? "#34d399" : "#f87171" }}
                  data-testid="oc-quote-age"
                >
                  {qv.age_s == null ? "—" : `${qv.age_s}s / ${qv.fresh_window_s}s window`}
                </b>
              </div>
              <div className="text-[#6b7888]">
                Source: <b className="text-[#c9d4e0]">{qv.source || "—"}</b>
              </div>
              <div className="text-[#6b7888]">
                Input → Allocation:{" "}
                <b className="text-[#c9d4e0]">
                  {fmtUsd(qv.input_amount)} → {fmtNum(qv.bdag_allocated, 0)} BDAG
                </b>
              </div>
              <div className="text-[#6b7888]">
                Effective Price: <b className="text-[#a78bfa]">${fmtPrice(qv.effective_price)}</b>
              </div>
            </div>
            <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mt-3 font-mono text-[10px] text-[#6b7888]">
              {qv.note}
            </div>
            {!qv.fresh && (
              <div
                className="mt-2 border border-[#f87171]/40 bg-[#f87171]/10 px-3 py-2 font-mono text-[10px] text-[#f87171]"
                data-testid="oc-quote-stale-warning"
              >
                ✗ Quote is not fresh — re-run the capture bookmarklet on the swap page (or use the manual capture form
                on the Execution screen) before considering this opportunity executable.
              </div>
            )}
          </Section>
        </div>

        {/* 5. Human-in-the-Loop Actions */}
        <div className="col-span-12">
          <Section
            title="5. HUMAN-IN-THE-LOOP ACTIONS"
            badge="WORKFLOW HELPERS — NO SIGNING"
            badgeColor="#f87171"
            testid="oc-actions"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
              <ActionButton
                action={a.open_swap_page}
                onClick={() => openLink(a.open_swap_page?.url)}
                color="#38bdf8"
                testid="oc-action-open-swap"
              />
              <ActionButton
                action={a.verify_quote}
                onClick={() => load(size)}
                color="#a78bfa"
                testid="oc-action-verify-quote"
              />
              <ActionButton
                action={a.execute_trade}
                onClick={() => {
                  if (!a.execute_trade?.enabled) {
                    toast.error("EXECUTE is disabled — verdict must be HIGH CONFIDENCE with a fresh quote.");
                    return;
                  }
                  toast.warning("Opening swap page. ArbiCore will NOT sign — you sign in your own wallet.");
                  openLink(a.execute_trade?.url);
                }}
                color="#34d399"
                testid="oc-action-execute"
              />
              <ActionButton
                action={a.open_coinstore}
                onClick={() => openLink(a.open_coinstore?.url)}
                color="#ffb224"
                testid="oc-action-open-coinstore"
              />
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

const ActionButton = ({ action, onClick, color = "#34d399", testid }) => {
  if (!action) return null;
  const enabled = action.enabled !== false;
  return (
    <div className="border border-[#1f2a36] bg-[#0a0e13] p-3 flex flex-col" data-testid={testid}>
      <button
        type="button"
        onClick={onClick}
        disabled={!enabled}
        data-testid={`${testid}-btn`}
        className="px-3 py-2 font-mono text-xs font-bold tracking-wider border disabled:opacity-30 disabled:cursor-not-allowed"
        style={{
          borderColor: enabled ? color : "#1f2a36",
          color: enabled ? color : "#3d4a59",
          background: enabled ? `${color}1a` : "transparent",
        }}
      >
        {action.label}
      </button>
      <div className="font-mono text-[9px] text-[#6b7888] mt-2">{action.note}</div>
    </div>
  );
};
