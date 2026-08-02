import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtUsd, fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PRESETS = [50, 100, 500, 1000, 5000];

const fmtPrice = (v) => (v == null ? "—" : Number(v).toExponential(4));
const fmtPct = (v) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(3)}%`);
const fmtNum = (v) => (v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }));

const VERDICT_C = { READY: "#34d399", WAIT: "#ffb224", NO_GO: "#f87171" };
const STATUS_C = { ACTIVE: "#34d399", ok: "#34d399",
                   WAITING: "#ffb224", needs_samples: "#ffb224", low_confidence: "#ffb224", stale_base: "#ffb224",
                   not_configured: "#6b7888", endpoint_unknown: "#6b7888", unavailable: "#f87171",
                   fetch_error: "#f87171", not_implemented_yet: "#6b7888" };

export const QuoteResolverPanel = () => {
  const [amount, setAmount] = useState("50");
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = useCallback(async (amt) => {
    setLoading(true);
    try {
      const r = await axios.post(`${API}/execution/quote-resolver`,
        { investment_usd: parseFloat(amt) });
      setD(r.data);
    } catch (e) {
      toast.error(`Quote failed: ${e.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { run("50"); }, [run]);

  const submit = (e) => {
    e.preventDefault();
    const a = parseFloat(amount);
    if (!(a > 0)) { toast.error("Enter positive USDT amount."); return; }
    run(amount);
  };

  if (!d) {
    return (
      <div className="panel" data-testid="quote-resolver-panel">
        <div className="panel-title">Pre-Trade Quote Resolver</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
      </div>
    );
  }

  const q = d.quote || {};
  const ec = d.economics || {};
  const verdict = d.verdict || "—";
  const vc = VERDICT_C[verdict] || "#6b7888";
  const sd = d.strategy_details?.executed_calibration?.calibration || {};
  const xc = d.cross_check || {};

  return (
    <div className="panel" data-testid="quote-resolver-panel">
      <div className="panel-title">
        Pre-Trade Quote Resolver — non-committing, no signature, no wallet
        <span className="float-right text-[#3d4a59]">
          read-only{loading && <span className="text-[#38bdf8] ml-2">↻</span>}
        </span>
      </div>

      {/* Verdict banner */}
      <div className="border p-3 mb-3" data-testid="quote-resolver-banner"
           style={{ borderColor: vc + "66", background: vc + "1a" }}>
        <div className="flex items-baseline justify-between flex-wrap gap-3">
          <div>
            <div className="text-[9px] tracking-widest uppercase" style={{ color: vc }}>VERDICT</div>
            <div className="font-mono text-3xl font-bold mt-0.5" style={{ color: vc }}
                 data-testid="quote-resolver-verdict">{verdict}</div>
          </div>
          <div className="font-mono text-[10px] text-[#c9d4e0] max-w-[680px] flex-1">
            {(d.reasons || []).map((r, i) => <div key={i}>• {r}</div>)}
          </div>
        </div>
      </div>

      {/* Test-amount form */}
      <form onSubmit={submit} className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3 flex flex-wrap items-center gap-2" data-testid="quote-resolver-form">
        <span className="text-[9px] uppercase tracking-widest text-[#6b7888] mr-1">Test amount (USDT)</span>
        {PRESETS.map((p) => (
          <button key={p} type="button" data-testid={`quote-preset-${p}`}
                  onClick={() => { setAmount(String(p)); run(p); }}
                  className={`px-2.5 py-1 font-mono text-[10px] font-bold border ${
                    String(p) === String(amount)
                      ? "border-[#a78bfa] text-[#a78bfa] bg-[#a78bfa]/10"
                      : "border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0]"
                  }`}>${p}</button>
        ))}
        <input data-testid="quote-resolver-input" type="number" step="any" min="0"
               value={amount} onChange={(e) => setAmount(e.target.value)}
               className="bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0] w-32" />
        <button data-testid="quote-resolver-submit" type="submit" disabled={loading}
                className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider">
          {loading ? "QUOTING…" : "→ QUOTE"}
        </button>
      </form>

      {/* Headline economics */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-[#1f2a36] border border-[#1f2a36] mb-3 font-mono" data-testid="quote-headline">
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">INPUT</div>
          <div className="text-lg font-bold text-[#c9d4e0]" data-testid="quote-headline-input">{fmtUsd(d.input_usd)}</div>
        </div>
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">BDAG EXPECTED</div>
          <div className="text-lg font-bold text-[#34d399]" data-testid="quote-headline-bdag">{fmtNum(q.bdag_expected)}</div>
        </div>
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">EFFECTIVE PRICE</div>
          <div className="text-lg font-bold text-[#a78bfa]" data-testid="quote-headline-price">${fmtPrice(q.effective_price)}</div>
        </div>
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">IMPLIED BONUS</div>
          <div className="text-lg font-bold text-[#ffb224]" data-testid="quote-headline-bonus">{fmtPct(q.implied_bonus_pct)}</div>
        </div>
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">FRESH ROI</div>
          <div className="text-lg font-bold" data-testid="quote-headline-roi"
               style={{ color: (ec.roi_pct ?? -1) >= 2 ? "#34d399" : (ec.roi_pct ?? -1) > 0 ? "#ffb224" : "#f87171" }}>
            {ec.roi_pct == null ? "—" : `${ec.roi_pct}%`}
          </div>
        </div>
      </div>

      {/* Executable economics breakdown */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="quote-economics">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-1">EXECUTABLE ECONOMICS · at the quoted price</div>
        {ec.available === false ? (
          <div className="font-mono text-[10px] text-[#f87171] py-2">{ec.reason}</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 font-mono text-[10px]">
            <div className="text-[#6b7888]">BDAG bought: <b className="text-[#c9d4e0]">{fmtNum(ec.bdag_bought)}</b></div>
            <div className="text-[#6b7888]">BDAG after transfer: <b className="text-[#c9d4e0]">{fmtNum(ec.bdag_after_transfer)}</b></div>
            <div className="text-[#6b7888]">Sell venue: <b className="text-[#c9d4e0]">{(ec.venue || "—").toUpperCase()}</b></div>
            <div className="text-[#6b7888]">Best bid · weighted sell: <b className="text-[#c9d4e0]">${fmtPrice(ec.best_bid_used)}</b> · <b className="text-[#c9d4e0]">${fmtPrice(ec.weighted_sell_price_used)}</b></div>
            <div className="text-[#6b7888]">Gross proceeds: <b className="text-[#34d399]">{fmtUsd(ec.gross_proceeds_usd)}</b></div>
            <div className="text-[#6b7888]">Total fees: <b className="text-[#f87171]">{fmtUsd(ec.total_fees_usd)}</b></div>
            <div className="text-[#6b7888]">  · trading {ec.trading_fee_pct}%: {fmtUsd(ec.trading_fee_usd)}</div>
            <div className="text-[#6b7888]">  · USDT withdrawal (BEP20): {fmtUsd(ec.usdt_withdrawal_fee_usd)}</div>
            <div className="text-[#6b7888]">  · BDAG transfer: {ec.bdag_transfer_fee_bdag} BDAG · {fmtUsd(ec.bdag_transfer_fee_usd)}</div>
            <div className="text-[#6b7888]">  · BSC purchase gas: {fmtUsd(ec.purchase_gas_usd)}</div>
            <div className="text-[#6b7888]">Net profit: <b className="text-[#34d399]">{fmtUsd(ec.net_profit_usd)}</b></div>
            <div className="text-[#6b7888]">Wallet received USDT: <b className="text-[#34d399]">{fmtUsd(ec.wallet_received_usd)}</b></div>
            <div className="text-[#6b7888]">Meets Coinstore min deposit ({ec.coinstore_min_deposit_bdag} BDAG):
              <b className="ml-1" style={{ color: ec.meets_coinstore_min_deposit ? "#34d399" : "#f87171" }}>
                {ec.meets_coinstore_min_deposit ? "YES" : "NO"}</b></div>
          </div>
        )}
      </div>

      {/* Calibration detail */}
      {sd.confidence && (
        <div className="border border-[#a78bfa]/30 bg-[#10081a] p-2 mb-3" data-testid="quote-calibration">
          <div className="text-[9px] tracking-widest uppercase text-[#a78bfa] mb-1">CALIBRATION · executed-history bonus factor</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-1 font-mono text-[10px]">
            <div className="text-[#6b7888]">Live API base: <b className="text-[#c9d4e0]" data-testid="quote-cal-base">${fmtPrice(sd.live_api_base_price)}</b></div>
            <div className="text-[#6b7888]">Rolling avg effective: <b className="text-[#34d399]">${fmtPrice(sd.rolling_avg_effective_price)}</b></div>
            <div className="text-[#6b7888]">Bonus factor: <b className="text-[#a78bfa]" data-testid="quote-cal-bonus">{sd.bonus_factor}</b> ({fmtPct(sd.implied_bonus_pct)})</div>
            <div className="text-[#6b7888]">Samples: <b className="text-[#c9d4e0]" data-testid="quote-cal-samples">{sd.samples_count} / min {sd.min_samples_required}</b>
              · confidence <b style={{ color: sd.confidence === "high" ? "#34d399" : sd.confidence === "medium" ? "#ffb224" : "#f87171" }}>{sd.confidence.toUpperCase()}</b></div>
          </div>
        </div>
      )}

      {/* Strategies */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="quote-strategies">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-2">QUOTE STRATEGIES · precedence-ordered</div>
        <div className="space-y-1.5">
          {(d.strategies || []).map((s) => (
            <div key={s.strategy} className="font-mono text-[10px]" data-testid={`quote-strategy-${s.strategy}`}>
              <div className="flex items-baseline justify-between gap-2 flex-wrap">
                <span className="text-[#c9d4e0] font-bold">{s.label}</span>
                <span className="text-[9px] font-bold tracking-widest"
                      style={{ color: STATUS_C[s.status] || "#8b97a6" }}
                      data-testid={`quote-strategy-${s.strategy}-status`}>
                  {String(s.status || "—").toUpperCase()}{s.production_grade ? " · PROD-GRADE" : ""}
                </span>
              </div>
              <div className="text-[#6b7888] ml-2">{s.note}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Cross-check */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3 font-mono text-[10px]" data-testid="quote-cross-check">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-1">CROSS-CHECK</div>
        <div className="text-[#8b97a6]">
          Executable-Quote authoritative source: <b className="text-[#c9d4e0]">{xc.executable_quote_authoritative_source || "—"}</b>
          {" "}@ <b className="text-[#c9d4e0]">${fmtPrice(xc.executable_quote_authoritative_value)}</b>.
          Match with this quote:
          <b className="ml-1" style={{ color: xc.matches_chosen_quote === true ? "#34d399" :
                                              xc.matches_chosen_quote === false ? "#f87171" : "#6b7888" }}
             data-testid="quote-cross-check-match">
            {xc.matches_chosen_quote === true ? "YES ✓" : xc.matches_chosen_quote === false ? "NO ✗" : "—"}
          </b>
        </div>
      </div>

      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 font-mono text-[10px]" data-testid="quote-consumption-status">
        <div className="text-[#ffb224]">★ <b>{d.consumed_by_arbicore_for_roi ? "WIRED INTO FRESH-CYCLE ROI" : "NOT WIRED INTO FRESH-CYCLE ROI YET"}</b></div>
        <div className="text-[#8b97a6] mt-1">{d.consumed_by_arbicore_note}</div>
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">{d.note}</div>
    </div>
  );
};
