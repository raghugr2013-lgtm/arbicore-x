import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ORIGIN = process.env.REACT_APP_BACKEND_URL;
const SCRIPT_URL = `${ORIGIN.replace(/\/$/, "")}/arbicore-companion.user.js`.replace("/api", "");

const STATE_C = {
  QUOTED: "#38bdf8", SWAP_SUBMITTED: "#ffb224", SWAP_CONFIRMED: "#a78bfa",
  BDAG_RECEIVED: "#a78bfa", TRANSFER_SUBMITTED: "#ffb224",
  DEPOSIT_CONFIRMED: "#a78bfa", SOLD: "#a78bfa", WITHDRAWN: "#34d399",
  CLOSED: "#34d399", ABORTED: "#f87171", DRAFT: "#6b7888",
};
const NEXT_STATE = {
  QUOTED: "SWAP_SUBMITTED", SWAP_SUBMITTED: "SWAP_CONFIRMED",
  SWAP_CONFIRMED: "BDAG_RECEIVED", BDAG_RECEIVED: "TRANSFER_SUBMITTED",
  TRANSFER_SUBMITTED: "DEPOSIT_CONFIRMED", DEPOSIT_CONFIRMED: "SOLD",
  SOLD: "WITHDRAWN", WITHDRAWN: "CLOSED",
};

const FRESH_QUOTE_MAX_AGE_S = 300;   // matches buy_price authority
const fmtAge = (s) => (s == null ? "—" : s < 60 ? `${Math.round(s)}s` : `${Math.round(s / 60)}m`);
const num = (v, d = 2) => (v == null || isNaN(v) ? "—" : Number(v).toFixed(d));

export const ArbitrageCyclesPanel = () => {
  const [d, setD] = useState(null);
  const [seed, setSeed] = useState(null);          // last fetched seed snapshot
  const [seedAt, setSeedAt] = useState(null);
  const [overrideMode, setOverrideMode] = useState(false);
  const [form, setForm] = useState({ input_amount: "50", quote_price: "", bdag_expected: "",
                                     best_bid: "", expected_roi_pct: "", note: "" });
  const [posting, setPosting] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/execution/arb-cycles`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  // Authoritative seed fetcher — quote-capture + operator-console in parallel.
  // Reads ONLY; never writes back. No backend changes.
  const fetchSeed = useCallback(async () => {
    try {
      const [qc, oc] = await Promise.all([
        axios.get(`${API}/execution/quote-capture`).then((r) => r.data).catch(() => null),
        axios.get(`${API}/execution/operator-console`).then((r) => r.data).catch(() => null),
      ]);
      const cap = qc?.latest || {};
      const mon = oc?.monitor || {};
      const hd = oc?.historical_drift || {};
      const quote_price = cap.available && cap.fresh ? cap.effective_price : null;
      const best_bid    = mon.best_bid ?? null;
      const expected_roi_pct = mon.net_spread_pct ?? null;
      setSeed({
        quote: {
          value:      quote_price,
          source:     cap.source || (quote_price ? "quote_capture" : null),
          age_s:      cap.age_s ?? null,
          fresh:      !!(cap.available && cap.fresh),
        },
        bid: {
          value:      best_bid,
          source:     "operator_console.monitor.best_bid (coinstore)",
          age_s:      mon.book_age_s ?? null,
        },
        roi: {
          value:      expected_roi_pct,
          source:     "operator_console.monitor.net_spread_pct",
          gross:      mon.gross_spread_pct ?? null,
        },
        sizing: {
          min_buy_usd:         hd.min_buy_usd ?? 50,
          recommended_buy_usd: hd.recommended_buy_usd ?? null,
          max_buy_usd:         hd.max_buy_usd ?? null,
          feasible:            hd.feasible ?? null,
          capacity_score:      hd.opportunity_capacity_score_0_100 ?? null,
          source:              hd.available !== false ? "historical_drift.opportunity_capacity" : null,
        },
        regime: hd.regime ?? null,
        risk:   { label: hd.risk_label ?? null, score: hd.risk_score_0_100 ?? null },
      });
      setSeedAt(new Date().toISOString());
    } catch (e) {
      // soft fail — operator can override
    }
  }, []);

  useEffect(() => {
    load();
    fetchSeed();
    const t1 = setInterval(load, 20000);
    const t2 = setInterval(fetchSeed, 20000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [load, fetchSeed]);

  // Derive bdag_expected from current input + (seeded or override) quote price.
  // Memo, NOT setState-in-effect (avoids unnecessary re-renders and lint flag).
  const derivedBdagExpected = useMemo(() => {
    const amt = parseFloat(form.input_amount);
    const seededPrice = seed?.quote?.value;
    const priceForCalc = overrideMode ? parseFloat(form.quote_price) : seededPrice;
    if (amt > 0 && priceForCalc > 0) return amt / priceForCalc;
    return null;
  }, [form.input_amount, form.quote_price, seed?.quote?.value, overrideMode]);

  const canSubmit = (() => {
    if (overrideMode) {
      const a = parseFloat(form.input_amount), p = parseFloat(form.quote_price), b = parseFloat(form.bdag_expected);
      return a > 0 && p > 0 && b > 0;
    }
    if (!seed?.quote?.fresh) return false;
    const amt = parseFloat(form.input_amount);
    if (!(amt > 0)) return false;
    if (!(derivedBdagExpected > 0)) return false;
    if (seed?.sizing?.min_buy_usd && amt < seed.sizing.min_buy_usd) return false;
    if (seed?.sizing?.max_buy_usd && amt > seed.sizing.max_buy_usd) return false;
    return true;
  })();

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) {
      toast.error(overrideMode
        ? "Override mode requires positive input, quote price, BDAG expected."
        : "No fresh quote — capture one first, or enable Override mode for manual entry.");
      return;
    }
    const amt = parseFloat(form.input_amount);
    const price = overrideMode ? parseFloat(form.quote_price) : seed.quote.value;
    const bdag = overrideMode ? parseFloat(form.bdag_expected) : derivedBdagExpected;
    const bid = overrideMode ? (form.best_bid ? parseFloat(form.best_bid) : null) : seed?.bid?.value;
    const roi = overrideMode ? (form.expected_roi_pct ? parseFloat(form.expected_roi_pct) : null) : seed?.roi?.value;

    // Provenance: stored in `note` (the only operator-text field accepted by the
    // existing backend schema — keeps this a frontend-only change while still
    // preserving authoritative metadata with the cycle record).
    const userNote = (form.note || "").trim();
    const meta = {
      mode: overrideMode ? "manual_override" : "seeded",
      seeded_at: seedAt,
      quote: overrideMode ? { manual: true } : { source: seed?.quote?.source, age_s: seed?.quote?.age_s },
      bid:   overrideMode ? { manual: true } : { source: seed?.bid?.source,   age_s: seed?.bid?.age_s   },
      roi:   overrideMode ? { manual: true } : { source: seed?.roi?.source, gross_spread_pct: seed?.roi?.gross },
      sizing: overrideMode ? { manual: true } : seed?.sizing,
      regime: seed?.regime, risk: seed?.risk,
    };
    const finalNote = `ArbiCore-${meta.mode} | ${JSON.stringify(meta)}${userNote ? " | " + userNote : ""}`;

    setPosting(true);
    try {
      await axios.post(`${API}/execution/arb-cycles`, {
        input_amount: amt, quote_price: price, bdag_expected: bdag,
        best_bid: bid, expected_roi_pct: roi,
        note: finalNote,
      });
      toast.success(`Cycle opened (QUOTED) — ${meta.mode}`);
      setForm({ input_amount: String(seed?.sizing?.recommended_buy_usd || 50),
                quote_price: "", bdag_expected: "", best_bid: "", expected_roi_pct: "", note: "" });
      load();
    } catch (err) {
      toast.error(`Open failed: ${err.response?.data?.detail || err.message}`);
    } finally { setPosting(false); }
  };

  const transition = async (id, to, fields) => {
    try {
      await axios.post(`${API}/execution/arb-cycles/${id}/transition`, { to_state: to, fields });
      toast.success(`→ ${to}`); load();
    } catch (err) { toast.error(`${err.response?.data?.detail || err.message}`); }
  };

  const abort = async (id) => {
    if (!confirm("Abort this cycle?")) return;
    try {
      await axios.post(`${API}/execution/arb-cycles/${id}/abort`); toast.success("ABORTED"); load();
    } catch (err) { toast.error(`${err.response?.data?.detail || err.message}`); }
  };

  if (!d) return (
    <div className="panel" data-testid="arbitrage-cycles-panel">
      <div className="panel-title">Arbitrage Cycles</div>
      <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
    </div>
  );

  const cycles = d.cycles || [];
  const stats = d.statistics || {};

  return (
    <div className="panel" data-testid="arbitrage-cycles-panel">
      <div className="panel-title">
        Arbitrage Cycle Evidence — every real BDAG→Coinstore cycle, 12-field record
        <span className="float-right text-[#3d4a59]">{stats.closed_count || 0} closed · read-only tracking</span>
      </div>

      {/* Stats strip */}
      {stats.closed_count > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-[#1f2a36] border border-[#1f2a36] mb-3 font-mono" data-testid="cycles-stats">
          <div className="bg-[#10161e] px-3 py-2"><div className="text-[8px] tracking-widest text-[#6b7888]">CLOSED CYCLES</div>
            <div className="text-lg font-bold text-[#c9d4e0]">{stats.closed_count}</div></div>
          {stats.duration_s && (
            <div className="bg-[#10161e] px-3 py-2"><div className="text-[8px] tracking-widest text-[#6b7888]">MEDIAN DURATION</div>
              <div className="text-lg font-bold text-[#38bdf8]">{stats.duration_s.median}s</div>
              <div className="text-[8px] text-[#5a6573]">p95 {stats.duration_s.p95}s · worst {stats.duration_s.worst}s</div></div>
          )}
          {stats.realized_roi_pct && (
            <div className="bg-[#10161e] px-3 py-2"><div className="text-[8px] tracking-widest text-[#6b7888]">MEDIAN ROI</div>
              <div className="text-lg font-bold text-[#34d399]">{stats.realized_roi_pct.median}%</div>
              <div className="text-[8px] text-[#5a6573]">worst {stats.realized_roi_pct.worst}% · best {stats.realized_roi_pct.best}%</div></div>
          )}
          {stats.drift_pct_at_sell && (
            <div className="bg-[#10161e] px-3 py-2"><div className="text-[8px] tracking-widest text-[#6b7888]">MEDIAN DRIFT</div>
              <div className="text-lg font-bold text-[#ffb224]">{stats.drift_pct_at_sell.avg}%</div></div>
          )}
        </div>
      )}

      {/* Companion setup */}
      <div className="border border-[#38bdf8]/40 bg-[#0a1018] p-3 mb-3" data-testid="companion-setup">
        <div className="text-[9px] tracking-widest uppercase text-[#38bdf8] mb-1">ARBICORE COMPANION USERSCRIPT</div>
        <div className="font-mono text-[10px] text-[#c9d4e0] mb-2">
          One-file Tampermonkey script. Observes the swap UI after wallet connection and POSTs captured
          quotes to ArbiCore. Does NOT sign or submit anything.
        </div>
        <ol className="font-mono text-[10px] text-[#8b97a6] space-y-0.5 mb-2">
          <li>1. Install Tampermonkey for your browser.</li>
          <li>2. Open <a href={SCRIPT_URL} target="_blank" rel="noreferrer" className="text-[#38bdf8] underline" data-testid="companion-script-link">{SCRIPT_URL}</a> — Tampermonkey will prompt to install.</li>
          <li>3. Set the quote-capture key once via the Tampermonkey script editor:
            <code className="text-[#a78bfa] ml-1">GM_setValue("arbicore_key", "&lt;KEY from ArbiCore admin&gt;")</code></li>
          <li>4. Visit purchase3.blockdag.network/swap — the script auto-arms. Type any amount → quote captured.</li>
        </ol>
        <a href={SCRIPT_URL} target="_blank" rel="noreferrer"
           className="inline-block px-3 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 font-mono text-[10px] font-bold tracking-wider">
          ↓ INSTALL USERSCRIPT
        </a>
      </div>

      {/* New cycle form — AUTO-SEEDED from authoritative system values */}
      <form onSubmit={submit} className="border border-[#34d399]/40 bg-[#0a120e] p-3 mb-3" data-testid="cycle-create-form">
        <div className="flex items-baseline justify-between mb-2">
          <div className="text-[9px] tracking-widest uppercase text-[#34d399]">
            OPEN NEW CYCLE · {overrideMode ? "MANUAL OVERRIDE" : "auto-seeded from live system state"}
          </div>
          <div className="flex items-center gap-2 font-mono text-[9px]">
            <span className="text-[#5a6573]">seed updated: {seedAt ? fmtTime(seedAt) : "—"}</span>
            <button type="button" data-testid="cycle-seed-refresh" onClick={fetchSeed}
                    className="px-1.5 py-0.5 border border-[#1f2a36] text-[#8b97a6] hover:text-[#c9d4e0]">↻ refresh</button>
            <label className="flex items-center gap-1 cursor-pointer">
              <input type="checkbox" checked={overrideMode}
                     onChange={(e) => setOverrideMode(e.target.checked)}
                     data-testid="cycle-override-toggle" className="accent-[#ffb224]" />
              <span className={overrideMode ? "text-[#ffb224] font-bold" : "text-[#5a6573]"}>Override (manual)</span>
            </label>
          </div>
        </div>

        {/* Fresh-quote banner */}
        {!overrideMode && (
          <div className={"mb-2 px-2 py-1 font-mono text-[10px] border " + (
            seed?.quote?.fresh
              ? "border-[#34d399]/40 text-[#34d399] bg-[#34d399]/05"
              : "border-[#f87171]/40 text-[#f87171] bg-[#f87171]/05")}
               data-testid="cycle-fresh-quote-banner">
            {seed?.quote?.fresh
              ? <>✓ Fresh executable quote · age {fmtAge(seed.quote.age_s)} · source <b>{seed.quote.source}</b></>
              : <>✗ No fresh quote (capture one via the userscript or quote-capture panel, or enable Override).</>}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
          {/* INPUT AMOUNT — operator chooses */}
          <div data-testid="cycle-input-amount-cell">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase mb-0.5">Input (USDT)</div>
            <input data-testid="cycle-input-amount" type="number" step="any" min={seed?.sizing?.min_buy_usd || 50}
                   max={seed?.sizing?.max_buy_usd || undefined}
                   value={form.input_amount}
                   onChange={(e) => setForm({ ...form, input_amount: e.target.value })}
                   className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[12px] text-[#c9d4e0]" />
            <div className="text-[8px] text-[#5a6573] mt-0.5">operator-set · BDAG floor $50</div>
          </div>

          {/* QUOTE PRICE — auto-seeded */}
          <div data-testid="cycle-quote-price-cell">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase mb-0.5">Quote $/BDAG</div>
            {overrideMode ? (
              <input data-testid="cycle-quote-price" type="number" step="any" placeholder="manual"
                     value={form.quote_price}
                     onChange={(e) => setForm({ ...form, quote_price: e.target.value })}
                     className="w-full bg-[#0e141c] border border-[#ffb224] px-2 py-1 font-mono text-[12px] text-[#ffb224]" />
            ) : (
              <div className="w-full bg-[#0a0e13] border border-[#34d399]/30 px-2 py-1 font-mono text-[12px] text-[#34d399]"
                   data-testid="cycle-quote-price-seeded">
                {seed?.quote?.value ? Number(seed.quote.value).toExponential(4) : "—"}
              </div>
            )}
            <div className="text-[8px] text-[#5a6573] mt-0.5">
              {overrideMode ? "manual" : `${seed?.quote?.source || "—"} · ${fmtAge(seed?.quote?.age_s)}`}
            </div>
          </div>

          {/* BDAG EXPECTED — auto-calculated */}
          <div data-testid="cycle-bdag-expected-cell">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase mb-0.5">BDAG expected</div>
            {overrideMode ? (
              <input data-testid="cycle-bdag-expected" type="number" step="any" placeholder="manual"
                     value={form.bdag_expected}
                     onChange={(e) => setForm({ ...form, bdag_expected: e.target.value })}
                     className="w-full bg-[#0e141c] border border-[#ffb224] px-2 py-1 font-mono text-[12px] text-[#ffb224]" />
            ) : (
              <div className="w-full bg-[#0a0e13] border border-[#34d399]/30 px-2 py-1 font-mono text-[12px] text-[#34d399]"
                   data-testid="cycle-bdag-expected-derived">
                {derivedBdagExpected != null ? Math.round(derivedBdagExpected).toLocaleString() : "—"}
              </div>
            )}
            <div className="text-[8px] text-[#5a6573] mt-0.5">derived = input / quote</div>
          </div>

          {/* BEST BID — auto-seeded */}
          <div data-testid="cycle-best-bid-cell">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase mb-0.5">Coinstore bid</div>
            {overrideMode ? (
              <input data-testid="cycle-best-bid" type="number" step="any" placeholder="manual"
                     value={form.best_bid}
                     onChange={(e) => setForm({ ...form, best_bid: e.target.value })}
                     className="w-full bg-[#0e141c] border border-[#ffb224] px-2 py-1 font-mono text-[12px] text-[#ffb224]" />
            ) : (
              <div className="w-full bg-[#0a0e13] border border-[#34d399]/30 px-2 py-1 font-mono text-[12px] text-[#34d399]"
                   data-testid="cycle-best-bid-seeded">
                {seed?.bid?.value ? Number(seed.bid.value).toExponential(4) : "—"}
              </div>
            )}
            <div className="text-[8px] text-[#5a6573] mt-0.5">{overrideMode ? "manual" : "operator-console · live"}</div>
          </div>

          {/* EXPECTED ROI — auto-seeded */}
          <div data-testid="cycle-expected-roi-cell">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase mb-0.5">Expected ROI (net)</div>
            {overrideMode ? (
              <input data-testid="cycle-expected-roi" type="number" step="any" placeholder="manual"
                     value={form.expected_roi_pct}
                     onChange={(e) => setForm({ ...form, expected_roi_pct: e.target.value })}
                     className="w-full bg-[#0e141c] border border-[#ffb224] px-2 py-1 font-mono text-[12px] text-[#ffb224]" />
            ) : (
              <div className="w-full bg-[#0a0e13] border border-[#34d399]/30 px-2 py-1 font-mono text-[12px] text-[#34d399]"
                   data-testid="cycle-expected-roi-seeded">
                {seed?.roi?.value != null ? `${Number(seed.roi.value).toFixed(2)}%` : "—"}
              </div>
            )}
            <div className="text-[8px] text-[#5a6573] mt-0.5">
              {overrideMode ? "manual" : `gross ${num(seed?.roi?.gross, 2)}% → net (after fees)`}
            </div>
          </div>
        </div>

        {/* SIZING STRIP — min / recommended / max */}
        <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-[#1f2a36]"
             data-testid="cycle-sizing-strip">
          <div className="text-center">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase">Minimum Buy</div>
            <div className="font-mono text-base font-bold text-[#c9d4e0]" data-testid="cycle-min-buy">
              {fmtUsd(seed?.sizing?.min_buy_usd || 50)}
            </div>
            <div className="text-[8px] text-[#5a6573]">BDAG swap floor</div>
          </div>
          <div className="text-center">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase">Recommended</div>
            <div className="font-mono text-base font-bold text-[#34d399]" data-testid="cycle-recommended-buy">
              {seed?.sizing?.recommended_buy_usd != null ? fmtUsd(seed.sizing.recommended_buy_usd) : "—"}
            </div>
            <div className="text-[8px] text-[#5a6573]">
              opp_capacity score {num(seed?.sizing?.capacity_score, 0)}/100
            </div>
          </div>
          <div className="text-center">
            <div className="text-[8px] tracking-widest text-[#6b7888] uppercase">Max Safe</div>
            <div className="font-mono text-base font-bold text-[#ffb224]" data-testid="cycle-max-safe-buy">
              {seed?.sizing?.max_buy_usd != null ? fmtUsd(seed.sizing.max_buy_usd) : "—"}
            </div>
            <div className="text-[8px] text-[#5a6573]">
              profitable depth @ 8% net target
            </div>
          </div>
        </div>
        <div className="text-[8px] text-[#5a6573] mt-1 font-mono">
          sizing source: <span className="text-[#8b97a6]">{seed?.sizing?.source || "—"}</span>
          {seed?.regime && <> · regime <b className="text-[#c9d4e0]">{seed.regime}</b></>}
          {seed?.risk?.label && <> · risk <b className="text-[#c9d4e0]">{seed.risk.label}</b> ({num(seed?.risk?.score, 0)}/100)</>}
          {!seed?.sizing?.feasible && seed?.sizing?.source &&
            <span className="text-[#f87171] ml-2">⚠ depth below target — recommended buy may be ≤ minimum</span>}
        </div>

        {/* NOTE + SUBMIT */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mt-2 items-end">
          <input data-testid="cycle-note" type="text" placeholder="optional note"
                 value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })}
                 className="md:col-span-3 bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
          <button data-testid="cycle-create-submit" type="submit" disabled={posting || !canSubmit}
                  className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-30 disabled:cursor-not-allowed font-mono text-[10px] font-bold tracking-wider">
            {posting ? "OPENING…" : canSubmit ? "+ OPEN CYCLE" : "✗ NOT READY"}
          </button>
        </div>
        <div className="text-[8px] text-[#5a6573] mt-1 font-mono">
          provenance is stored in the cycle record via the `note` field (auto-prefixed `ArbiCore-seeded` or `ArbiCore-manual_override`).
        </div>
      </form>

      {/* Cycle list with state transition controls */}
      <div className="space-y-2" data-testid="cycle-list">
        {cycles.length === 0 ? (
          <div className="font-mono text-[10px] text-[#3d4a59] text-center py-3">No cycles yet — open one once you've captured a fresh quote.</div>
        ) : cycles.map((c) => {
          const next = NEXT_STATE[c.state];
          const a = c.actuals || {};
          return (
            <div key={c.id} className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid={`cycle-${c.id}`}>
              <div className="flex items-baseline justify-between gap-2 flex-wrap mb-1">
                <div className="font-mono text-[10px]">
                  <span className="font-bold" style={{ color: STATE_C[c.state] || "#6b7888" }} data-testid={`cycle-${c.id}-state`}>{c.state}</span>
                  <span className="text-[#6b7888] ml-2">id={c.id.slice(0, 8)}</span>
                  <span className="text-[#c9d4e0] ml-2">${c.input_amount_usd} → ~{Number(c.bdag_expected).toLocaleString()} BDAG @ ${Number(c.quote_price).toExponential(4)}</span>
                  {c.expected_roi_pct != null && <span className="text-[#a78bfa] ml-2">exp ROI {c.expected_roi_pct}%</span>}
                </div>
                <div className="flex gap-1">
                  {next && (
                    <button onClick={() => transition(c.id, next)}
                            data-testid={`cycle-${c.id}-advance`}
                            className="px-2 py-0.5 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 font-mono text-[9px] font-bold tracking-wider">
                      → {next}
                    </button>
                  )}
                  {!["CLOSED", "ABORTED"].includes(c.state) && (
                    <button onClick={() => abort(c.id)}
                            data-testid={`cycle-${c.id}-abort`}
                            className="px-2 py-0.5 border border-[#f87171] text-[#f87171] hover:bg-[#f87171]/10 font-mono text-[9px] font-bold tracking-wider">
                      ABORT
                    </button>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-0.5 font-mono text-[9px] text-[#6b7888]">
                <div>quote_at: <span className="text-[#c9d4e0]">{fmtTime(c.quote_at)}</span></div>
                <div>swap_submitted: <span className="text-[#c9d4e0]">{fmtTime(c.swap_submitted_at)}</span></div>
                <div>swap_confirmed: <span className="text-[#c9d4e0]">{fmtTime(c.swap_confirmed_at)}</span></div>
                <div>bdag_received: <span className="text-[#c9d4e0]">{fmtTime(c.bdag_received_at)}</span></div>
                <div>transfer_submitted: <span className="text-[#c9d4e0]">{fmtTime(c.transfer_submitted_at)}</span></div>
                <div>deposit_confirmed: <span className="text-[#c9d4e0]">{fmtTime(c.deposit_confirmed_at)}</span></div>
                <div>sell_executed: <span className="text-[#c9d4e0]">{fmtTime(c.sell_executed_at)}</span></div>
                <div>withdrawal_completed: <span className="text-[#c9d4e0]">{fmtTime(c.withdrawal_completed_at)}</span></div>
              </div>
              {(a.net_profit_usd != null || a.realized_roi_pct != null || a.total_cycle_duration_s != null) && (
                <div className="mt-1 font-mono text-[10px] text-[#34d399]">
                  net <b>{fmtUsd(a.net_profit_usd)}</b> · realized ROI <b>{a.realized_roi_pct}%</b> ·
                  duration <b>{a.total_cycle_duration_s}s</b>
                  {a.drift_pct_at_sell != null && <> · drift {a.drift_pct_at_sell}%</>}
                </div>
              )}
              {c.aborted_reason && <div className="mt-1 font-mono text-[10px] text-[#f87171]">aborted: {c.aborted_reason}</div>}
            </div>
          );
        })}
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        No signing, no submission, no fund movement. Operator stamps each transition. The dataset
        becomes the foundation for the risk engine and future automation.
      </div>
    </div>
  );
};
