import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fmtUsd, fmtPrice, fmtTime } from "@/lib/fmt";
import { FreshnessBadge } from "@/components/execution/FreshnessBadge";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS = {
  execution_approved: { c: "#34d399", label: "EXECUTION APPROVED" },
  monitor_only: { c: "#ffb224", label: "MONITOR ONLY" },
  disabled: { c: "#6b7888", label: "DISABLED" },
};

const scoreColor = (v) =>
  v == null ? "#3d4a59" : v >= 75 ? "#34d399" : v >= 45 ? "#ffb224" : "#f87171";

const Cell = ({ v, good, bad }) => {
  const c = v === good ? "#34d399" : v === bad ? "#f87171" : "#8b97a6";
  return <span style={{ color: c }}>{(v || "—").toString().toUpperCase()}</span>;
};

const RankList = ({ title, sub, rows, metric, accent, testid }) => (
  <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid={testid}>
    <div className="font-mono text-[11px] font-bold tracking-wider" style={{ color: accent }}>{title}</div>
    <div className="font-mono text-[9px] text-[#6b7888] mb-2">{sub}</div>
    <div className="space-y-1">
      {rows.map((r, i) => {
        const st = STATUS[r.status] || STATUS.disabled;
        return (
          <div key={r.exchange} className="flex items-center gap-2 text-[10px] font-mono"
               data-testid={`${testid}-row-${r.exchange}`}>
            <span className="w-4 text-right text-[#3d4a59]">{i + 1}</span>
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: st.c }} />
            <span className="flex-1 font-bold text-[#c9d4e0]">{r.name}</span>
            <span className="text-[8px] px-1 py-0.5 border" style={{ borderColor: st.c, color: st.c }}>
              {st.label}
            </span>
            <span className="w-9 text-right font-bold" style={{ color: scoreColor(r[metric]) }}>
              {r[metric] ?? "—"}
            </span>
          </div>
        );
      })}
    </div>
  </div>
);

export const ExchangeIntelligencePanel = () => {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/exchanges`).then((r) => setData(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const toggleVerified = async (exchange, current) => {
    setBusy(exchange);
    try {
      await axios.patch(`${API}/execution/exchanges/${exchange}`, { operator_verified: !current });
      load();
    } catch { /* noop */ } finally { setBusy(null); }
  };

  if (!data) {
    return (
      <div className="panel" data-testid="exchange-intel-panel">
        <div className="panel-title">Exchange Intelligence Registry</div>
        <div className="font-mono text-[11px] text-[#6b7888] py-6 text-center" data-testid="exchange-intel-loading">
          loading exchange intelligence…
        </div>
      </div>
    );
  }

  const c = data.counts;
  const basis = data.buy_price_basis || {};

  return (
    <div className="panel" data-testid="exchange-intel-panel">
      <div className="panel-title">
        Exchange Intelligence Registry &amp; Ranking
        <span className="float-right text-[#3d4a59]">read-only · all BDAG venues</span>
      </div>

      {/* classification counts */}
      <div className="flex flex-wrap gap-2 mb-3" data-testid="exchange-intel-counts">
        {[
          ["TOTAL", c.total, "#38bdf8"],
          ["EXECUTION APPROVED", c.execution_approved, "#34d399"],
          ["MONITOR ONLY", c.monitor_only, "#ffb224"],
          ["DISABLED", c.disabled, "#6b7888"],
          ["LIVE OVERLAY", c.live_overlay, "#38bdf8"],
        ].map(([k, v, col]) => (
          <div key={k} className="border border-[#1f2a36] bg-[#0a0e13] px-3 py-1.5">
            <div className="font-mono text-[8px] text-[#6b7888] tracking-wider">{k}</div>
            <div className="font-mono text-sm font-bold" style={{ color: col }}>{v}</div>
          </div>
        ))}
        <div className="flex-1" />
        <div className="border border-[#1f2a36] bg-[#0a0e13] px-3 py-1.5 text-right" data-testid="exchange-intel-basis">
          <div className="font-mono text-[8px] text-[#6b7888] tracking-wider">BUY-PRICE BASIS ({basis.source_label})</div>
          <div className="font-mono text-sm font-bold text-[#ffb224]">{fmtPrice(basis.price)}</div>
        </div>
      </div>

      {/* divergence callout */}
      <div className="mb-3 border px-3 py-2 font-mono text-[10px]" data-testid="exchange-intel-divergence"
           style={{ borderColor: "rgba(56,189,248,0.4)", background: "rgba(56,189,248,0.05)", color: "#38bdf8" }}>
        ◆ Highest profit ≠ best executable. The system prioritizes the <b>Best Executable</b> ranking
        (accessibility · API · live deposit/withdraw gates · trust · liquidity) over raw spread.
      </div>

      {/* two rankings */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <RankList title="BEST PROFIT OPPORTUNITY" sub="raw arbitrage edge × liquidity — regardless of reachability"
                  rows={(data.rankings?.best_profit || []).slice(0, 8)} metric="profit_score"
                  accent="#ffb224" testid="exchange-rank-profit" />
        <RankList title="BEST EXECUTABLE OPPORTUNITY" sub="what we could actually run end-to-end today"
                  rows={(data.rankings?.best_executable || []).slice(0, 8)} metric="executability_score"
                  accent="#34d399" testid="exchange-rank-executable" />
      </div>

      {/* exchange qualification tracking */}
      <div className="mb-4 border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid="exchange-qualification">
        <div className="flex items-center justify-between mb-0.5">
          <div className="font-mono text-[11px] font-bold tracking-wider text-[#38bdf8]">EXCHANGE QUALIFICATION TRACKING</div>
          <FreshnessBadge stale={!c.live_overlay} showAge={false} testid="qualification-freshness" />
        </div>
        <div className="font-mono text-[9px] text-[#6b7888] mb-2">manual verification · India access · deposit/withdrawal reliability · API capability · trust</div>
        <div className="overflow-x-auto">
          <table className="w-full text-[9px] font-mono">
            <thead>
              <tr className="panel-th text-[#6b7888]">
                <th className="text-left">Exchange</th>
                <th className="text-center">Manual Verif.</th>
                <th className="text-center">India</th>
                <th className="text-center">Deposit Rel.</th>
                <th className="text-center">Withdraw Rel.</th>
                <th className="text-center">API</th>
                <th className="text-center">Trust</th>
                <th className="text-right">Qualified</th>
              </tr>
            </thead>
            <tbody>
              {data.exchanges.filter((r) => r.status !== "disabled").map((r) => {
                const q = r.qualification || {};
                const items = Object.fromEntries((q.items || []).map((i) => [i.criterion, i]));
                const dot = (st) => st === "verified" ? "#34d399" : st === "partial" ? "#ffb224" : st === "pending" ? "#6b7888" : "#f87171";
                const cell = (name, extra) => {
                  const it = items[name] || {};
                  return (
                    <td className="py-1.5 text-center">
                      <span className="inline-flex items-center gap-1" title={it.detail || ""}>
                        <span className="w-1.5 h-1.5 rounded-full" style={{ background: dot(it.status) }} />
                        <span style={{ color: dot(it.status) }}>{extra ?? it.value}</span>
                      </span>
                    </td>
                  );
                };
                return (
                  <tr key={r.exchange} className="border-b border-[#1f2a36]/50" data-testid={`qualification-row-${r.exchange}`}>
                    <td className="py-1.5 font-bold text-[#c9d4e0]">{r.name}</td>
                    {cell("Manual Verification", r.operator_verified ? "YES" : "NO")}
                    {cell("India Accessibility")}
                    {cell("Deposit Reliability", r.deposit_reliability)}
                    {cell("Withdrawal Reliability", r.withdrawal_reliability)}
                    {cell("API Capability")}
                    {cell("Trust Score", r.trust_score)}
                    <td className="py-1.5 text-right font-bold" data-testid={`qualification-pct-${r.exchange}`}
                        style={{ color: q.fully_qualified ? "#34d399" : "#ffb224" }}>{q.qualification_pct}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* full registry table */}
      <div className="overflow-x-auto">
        <table className="w-full text-[9px] font-mono" data-testid="exchange-intel-table">
          <thead>
            <tr className="panel-th text-[#6b7888]">
              <th className="text-left">Exchange</th>
              <th className="text-left">Pair</th>
              <th className="text-left">Status</th>
              <th className="text-left">India</th>
              <th className="text-left">KYC</th>
              <th className="text-left">API</th>
              <th className="text-left">Deposit</th>
              <th className="text-left">Withdraw</th>
              <th className="text-right">Liq</th>
              <th className="text-right">24h Vol</th>
              <th className="text-right">Spread</th>
              <th className="text-right">Trust</th>
              <th className="text-right">Profit</th>
              <th className="text-right">Exec</th>
              <th className="text-center">Approved</th>
              <th className="text-right">Verified</th>
            </tr>
          </thead>
          <tbody>
            {data.exchanges.map((r) => {
              const st = STATUS[r.status] || STATUS.disabled;
              return (
                <tr key={r.exchange} className="border-b border-[#1f2a36]/50"
                    data-testid={`exchange-row-${r.exchange}`}>
                  <td className="py-1.5 font-bold text-[#c9d4e0]">{r.name}</td>
                  <td className="py-1.5 text-[#6b7888]">{r.bdag_pair}</td>
                  <td className="py-1.5">
                    <span data-testid={`exchange-status-${r.exchange}`}
                          className="px-1 py-0.5 border text-[8px] font-bold whitespace-nowrap"
                          style={{ borderColor: st.c, color: st.c }}>{st.label}</span>
                  </td>
                  <td className="py-1.5"><Cell v={r.india_accessibility} good="verified" /></td>
                  <td className="py-1.5 text-[#8b97a6]">{r.kyc_requirement?.toUpperCase()}</td>
                  <td className="py-1.5"><Cell v={r.api_availability} good="full" bad="none" /></td>
                  <td className="py-1.5"><Cell v={r.deposit_status} good="open" bad="closed" /></td>
                  <td className="py-1.5"><Cell v={r.withdrawal_status} good="open" bad="closed" /></td>
                  <td className="py-1.5 text-right font-bold" style={{ color: scoreColor(r.liquidity_score) }}>{r.liquidity_score}</td>
                  <td className="py-1.5 text-right" style={{ color: r.vol_reliable ? "#8b97a6" : "#5a4a4a" }}>
                    {r.vol_24h_usd ? `~${fmtUsd(r.vol_24h_usd)}` : "—"}{r.vol_reliable ? "" : "*"}
                  </td>
                  <td className="py-1.5 text-right font-bold" style={{ color: scoreColor(r.spread_score) }}>{r.spread_score ?? "—"}</td>
                  <td className="py-1.5 text-right font-bold" style={{ color: scoreColor(r.trust_score) }}>{r.trust_score}</td>
                  <td className="py-1.5 text-right font-bold" style={{ color: scoreColor(r.profit_score) }}>{r.profit_score ?? "—"}</td>
                  <td className="py-1.5 text-right font-bold" style={{ color: scoreColor(r.executability_score) }}>{r.executability_score}</td>
                  <td className="py-1.5 text-center">
                    <button
                      data-testid={`exchange-verify-${r.exchange}`}
                      onClick={() => toggleVerified(r.exchange, r.operator_verified)}
                      disabled={busy === r.exchange}
                      className="px-1.5 py-0.5 border text-[8px] font-bold"
                      style={{ borderColor: r.execution_approved ? "#34d399" : "#3d4a59",
                               color: r.execution_approved ? "#34d399" : "#6b7888" }}>
                      {r.execution_approved ? "YES" : "NO"}
                    </button>
                  </td>
                  <td className="py-1.5 text-right text-[#6b7888]" data-testid={`exchange-verified-${r.exchange}`}>
                    {r.data_source === "live" ? fmtTime(r.last_verified) : "audit"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        EXECUTION APPROVED = operator-verified loop + full API + gates open + accessible · MONITOR ONLY =
        tracked &amp; ranked, not executable until verified · DISABLED = hard blocker (no API / fake liquidity /
        suspended). * = reported 24h volume exceeds real depth (wash signature). Toggle “Approved” simulates an
        operator verification flag — no execution is enabled. {data.note?.includes("fund movement") ? "No fund movement." : ""}
      </div>
    </div>
  );
};
