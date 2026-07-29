import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtPrice = (v) => (v == null ? "—" : Number(v).toExponential(4));
const fmtPct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(3)}%`);

const SRC_LABEL = {
  executed_history: "Executed Price History",
  live_swap_ui: "Live Swap UI Quote Endpoint",
  sw_api_fallback: "sw-api Fallback",
};
const SRC_C = {
  executed_history: "#34d399",
  live_swap_ui: "#38bdf8",
  sw_api_fallback: "#ffb224",
};

export const ExecutableQuoteResolverPanel = () => {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    axios.get(`${API}/execution/executable-quote`)
      .then((r) => setD(r.data)).catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  if (!d) {
    return (
      <div className="panel" data-testid="executable-quote-panel">
        <div className="panel-title">Executable Quote Resolver</div>
        <div className="font-mono text-[11px] text-[#6b7888]">resolving…</div>
      </div>
    );
  }

  const auth = d.authoritative || {};
  const sbs = d.side_by_side || [];
  const sources = d.sources || {};
  const exec = sources.executed_history || {};
  const secondary = d.secondary_observation || {};
  const minSamples = d.thresholds?.min_executed_samples_for_authoritative || 3;

  return (
    <div className="panel" data-testid="executable-quote-panel">
      <div className="panel-title">
        Executable Quote Resolver — 3 sources, precedence chain
        <span className="float-right text-[#3d4a59]">
          read-only{loading && <span className="text-[#38bdf8] ml-2">↻</span>}
        </span>
      </div>

      {/* Authoritative banner */}
      <div className="border border-[#34d399]/60 bg-[#0a130e] p-3 mb-3" data-testid="quote-authoritative-banner">
        <div className="flex items-baseline justify-between flex-wrap gap-3">
          <div>
            <div className="text-[9px] tracking-widest uppercase text-[#34d399]">AUTHORITATIVE QUOTE</div>
            <div className="font-mono text-2xl font-bold text-[#34d399] mt-0.5" data-testid="quote-authoritative-price">
              ${fmtPrice(auth.value)} <span className="text-[10px] text-[#6b7888]">/ BDAG</span>
            </div>
            <div className="text-[10px] font-mono text-[#c9d4e0] mt-1" data-testid="quote-authoritative-source">
              source: <b style={{ color: SRC_C[auth.source] }}>{SRC_LABEL[auth.source] || "—"}</b>
            </div>
          </div>
          <div className="text-[10px] font-mono text-[#8b97a6] max-w-[680px] flex-1" data-testid="quote-authoritative-explanation">
            {d.authoritative_explanation}
          </div>
        </div>
        <div className="mt-3 text-[10px] font-mono text-[#a78bfa] flex flex-wrap gap-2 items-baseline" data-testid="quote-effective-completed-swaps">
          <span className="text-[9px] text-[#6b7888] tracking-widest uppercase">Effective price from completed swaps</span>
          <span className="text-[#34d399] font-bold text-base">
            {d.effective_price_from_completed_swaps != null
              ? `$${fmtPrice(d.effective_price_from_completed_swaps)}`
              : "—"}
          </span>
          <span className="text-[8px] text-[#5a6573]">
            (rolling avg over {exec.count || 0} operator-recorded executed swap{exec.count === 1 ? "" : "s"} ·
            need ≥{minSamples} for authoritative)
          </span>
        </div>
      </div>

      {/* Side-by-side 3-source comparison */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3" data-testid="quote-side-by-side">
        {sbs.map((row) => (
          <div key={row.source}
               className="border p-3"
               style={{
                 borderColor: row.is_authoritative ? SRC_C[row.source] : "#1f2a36",
                 background: row.is_authoritative ? `${SRC_C[row.source]}12` : "#0a0e13",
               }}
               data-testid={`quote-source-${row.source}`}>
            <div className="flex items-center justify-between mb-2">
              <div className="text-[9px] tracking-widest uppercase" style={{ color: SRC_C[row.source] }}>
                {SRC_LABEL[row.source]}
              </div>
              {row.is_authoritative && (
                <span className="px-1.5 py-0.5 bg-[#34d399] text-[#0a0e13] font-bold text-[8px] tracking-widest"
                      data-testid={`quote-source-${row.source}-auth-badge`}>★ AUTH</span>
              )}
            </div>
            <div className="font-mono text-xl font-bold text-[#c9d4e0]" data-testid={`quote-source-${row.source}-value`}>
              {row.value != null ? `$${fmtPrice(row.value)}` : "—"}
            </div>
            <div className="font-mono text-[10px] mt-1">
              <span className="text-[#6b7888]">delta vs auth: </span>
              <span style={{ color: row.delta_pct_vs_authoritative === 0 ? "#34d399"
                                : (Math.abs(row.delta_pct_vs_authoritative ?? 0) >= 5 ? "#f87171" : "#ffb224") }}
                    data-testid={`quote-source-${row.source}-delta`}>
                {fmtPct(row.delta_pct_vs_authoritative)}
              </span>
            </div>
            <div className="font-mono text-[9px] text-[#5a6573] mt-1">
              fetched: {fmtTime(row.fetched_at)}
            </div>
            <div className="font-mono text-[9px] text-[#3d4a59] mt-1" style={{ opacity: row.available ? 1 : 0.5 }}>
              {row.available ? "available" : "unavailable"}
            </div>
          </div>
        ))}
      </div>

      {/* Precedence chain explanation */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="quote-chain">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-2">
          PRECEDENCE CHAIN · default {d.precedence?.join(" → ")}
        </div>
        <ol className="space-y-1.5 font-mono text-[10px]">
          {(d.chain || []).map((c, i) => (
            <li key={i} className="border-l-2 pl-2"
                style={{ borderColor: c.won ? "#34d399" : "#3d4a59" }}
                data-testid={`quote-chain-step-${c.source}`}>
              <div>
                <span className="font-bold" style={{ color: c.won ? "#34d399" : "#6b7888" }}>
                  {c.won ? "✓ " : "○ "}
                </span>
                <span className="text-[#c9d4e0] font-bold">{SRC_LABEL[c.source] || c.source}</span>
                <span className="ml-2 text-[#8b97a6]">value={c.value != null ? `$${fmtPrice(c.value)}` : "—"}</span>
                {c.count != null && <span className="ml-2 text-[#5a6573]">(samples: {c.count})</span>}
              </div>
              <div className="text-[#6b7888] ml-3">{c.reason}</div>
            </li>
          ))}
        </ol>
      </div>

      {/* Executed history detail */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="quote-executed-history">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[9px] tracking-widest uppercase text-[#6b7888]">
            EXECUTED PRICE HISTORY · rolling window {exec.rolling_window} · {exec.count || 0} samples
          </div>
          {exec.ok && (
            <div className="text-[9px] font-mono text-[#5a6573]">
              avg=${fmtPrice(exec.value)} · median=${fmtPrice(exec.median)} ·
              σ=${fmtPrice(exec.stdev)} · range [${fmtPrice(exec.min)} – ${fmtPrice(exec.max)}]
            </div>
          )}
        </div>
        {(exec.samples || []).length === 0 ? (
          <div className="font-mono text-[10px] text-[#3d4a59] py-2">{exec.note}</div>
        ) : (
          <table className="w-full text-[10px] font-mono">
            <thead><tr className="panel-th text-[#6b7888]">
              <th className="text-left">When</th>
              <th className="text-right">USDT in</th>
              <th className="text-right">BDAG received</th>
              <th className="text-right">Effective $/BDAG</th>
              <th className="text-right">UI displayed</th>
            </tr></thead>
            <tbody>
              {(exec.samples || []).map((s, i) => (
                <tr key={i} className="border-b border-[#1f2a36]/40" data-testid={`quote-executed-sample-${i}`}>
                  <td className="py-1 text-[#6b7888]">{fmtTime(s.created_at)}</td>
                  <td className="py-1 text-right text-[#c9d4e0]">${s.investment_usd}</td>
                  <td className="py-1 text-right text-[#c9d4e0]">{Number(s.bdag_received).toLocaleString()}</td>
                  <td className="py-1 text-right text-[#34d399] font-bold">${fmtPrice(s.effective_price)}</td>
                  <td className="py-1 text-right text-[#ffb224]">{s.reported_ui_price ? `$${fmtPrice(s.reported_ui_price)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="text-[8px] text-[#3d4a59] mt-1 font-mono">
          Add more measurements via the Buy-Price Audit panel above (Empirical Test form).
          The resolver becomes authoritative on this source as soon as samples ≥ {minSamples}.
        </div>
      </div>

      {/* Live UI endpoint detail (newly discovered) */}
      <div className="border border-[#38bdf8]/30 bg-[#0a1018] p-2 mb-3" data-testid="quote-live-ui-detail">
        <div className="text-[9px] tracking-widest uppercase text-[#38bdf8] mb-1">
          LIVE SWAP UI QUOTE ENDPOINT — discovered via network capture
        </div>
        <div className="font-mono text-[10px] text-[#c9d4e0]">
          URL: <a href={sources.live_swap_ui?.url} target="_blank" rel="noreferrer"
                  className="text-[#38bdf8] underline">
            {sources.live_swap_ui?.url}
          </a>
        </div>
        <div className="font-mono text-[10px] text-[#8b97a6] mt-1">
          {sources.live_swap_ui?.discovery}
        </div>
        <div className="font-mono text-[10px] text-[#5a6573] mt-1">
          response: <code className="text-[#c9d4e0]">{"{ok: true, data: { BDAG: "}</code>
          <code className="text-[#34d399] font-bold">{fmtPrice(sources.live_swap_ui?.value)}</code>
          <code className="text-[#c9d4e0]">{" }}"}</code>
          {" · "}
          source-side fetchedAt: {fmtTime(sources.live_swap_ui?.raw_fetched_at)}
          {" · "}
          latency {sources.live_swap_ui?.latency_ms}ms
        </div>
        <div className="font-mono text-[10px] text-[#6b7888] mt-2">
          <b className="text-[#ffb224]">Key finding:</b> this endpoint returns the SAME numeric value as
          sw-api/getInfo, which means the ~10% bonus the operator observes empirically is applied by the
          swap contract itself, not by either API. Therefore, only <b className="text-[#34d399]">Executed
          Price History</b> captures the true settlement price.
        </div>
      </div>

      {/* Secondary observation (presale orderBook) */}
      {secondary.implied_price_from_latest_orders != null && (
        <div className="border border-[#a78bfa]/30 bg-[#100a18] p-2 mb-3" data-testid="quote-secondary">
          <div className="text-[9px] tracking-widest uppercase text-[#a78bfa] mb-1">
            SECONDARY OBSERVATION · cross-check only
          </div>
          <div className="font-mono text-[10px] text-[#c9d4e0]">
            <b>{secondary.label}</b>
          </div>
          <div className="font-mono text-[10px] mt-1">
            <span className="text-[#6b7888]">implied price (mean of last {secondary.sample_count} orders): </span>
            <span className="text-[#a78bfa] font-bold">${fmtPrice(secondary.implied_price_from_latest_orders)}</span>
            <span className="text-[#5a6573] ml-3">stage: {secondary.stage} · next-stage price: ${secondary.next_stage_token_price}</span>
          </div>
          <div className="font-mono text-[9px] text-[#3d4a59] mt-1">{secondary.note}</div>
        </div>
      )}

      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 font-mono text-[10px]" data-testid="quote-consumption-status">
        <div className="text-[#ffb224]">
          ★ <b>{d.consumed_by_arbicore_for_roi ? "WIRED INTO FRESH-CYCLE ROI" : "NOT WIRED INTO FRESH-CYCLE ROI YET"}</b>
        </div>
        <div className="text-[#8b97a6] mt-1">{d.consumed_by_arbicore_note}</div>
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">{d.note}</div>
    </div>
  );
};
