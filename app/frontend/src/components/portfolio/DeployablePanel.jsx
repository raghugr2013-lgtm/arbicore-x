import { fmtPct, fmtQty, fmtUsd } from "@/lib/fmt";

const FACTOR_STYLE = {
  LIQUIDITY_LIMITED: { color: "#34d399", label: "LIQUIDITY LIMITED" },
  CAPITAL_LIMITED: { color: "#fbbf24", label: "CAPITAL LIMITED" },
  DEPOSIT_GATE_LIMITED: { color: "#f87171", label: "DEPOSIT GATE LIMITED" },
  WITHDRAWAL_GATE_LIMITED: { color: "#fb923c", label: "WITHDRAWAL GATE LIMITED" },
  ROUTE_LIMITED: { color: "#6b7888", label: "ROUTE LIMITED" },
  NO_KEY: { color: "#38bdf8", label: "NO KEY — LIQUIDITY VIEW" },
};

export const DeployablePanel = ({ data }) => {
  const venues = data?.venues || [];
  return (
    <div className="panel" data-testid="deployable-panel">
      <div className="panel-title">
        Deployable Capital Engine — {data?.base || "BDAG"}/{data?.quote || "USDT"}
        <span className="float-right text-[#3d4a59]">analysis only · no transfers</span>
      </div>
      {venues.length === 0 && <div className="font-mono text-[11px] text-[#6b7888]">waiting for evaluation…</div>}
      <div className="space-y-2">
        {venues.map((v) => {
          const f = FACTOR_STYLE[v.limiting_factor] || FACTOR_STYLE.ROUTE_LIMITED;
          return (
            <div key={v.exchange} className="border border-[#1f2a36] p-2.5 font-mono"
                 data-testid={`deployable-venue-${v.exchange}`}>
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="font-bold uppercase">{v.exchange}</span>
                <span className="text-[9px] font-bold tracking-wider px-1.5 py-0.5 border"
                      data-testid={`deployable-factor-${v.exchange}`}
                      style={{ color: f.color, borderColor: `${f.color}66`, background: `${f.color}14` }}>
                  {f.label}
                </span>
                {v.net_spread_pct != null && (
                  <span className={v.net_spread_pct >= 0 ? "text-[#34d399]" : "text-[#f87171]"}>
                    net {fmtPct(v.net_spread_pct)}
                  </span>
                )}
                <div className="flex-1" />
                {v.est_profit_quote != null && (
                  <span className="text-[#34d399] font-bold">est {fmtUsd(v.est_profit_quote)}</span>
                )}
                {v.est_profit_quote == null && v.potential_profit_quote != null && (
                  <span className="text-[#38bdf8]">potential {fmtUsd(v.potential_profit_quote)}</span>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-0.5 mt-1.5 text-[10px]">
                <div><span className="text-[#6b7888]">free base </span>{v.free_base != null ? fmtQty(v.free_base) : "—"}</div>
                <div><span className="text-[#6b7888]">free quote </span>{v.free_quote != null ? fmtUsd(v.free_quote) : "—"}</div>
                <div><span className="text-[#6b7888]">book capacity </span>{v.liquidity_capacity_base != null ? fmtQty(v.liquidity_capacity_base) : "—"}</div>
                <div><span className="text-[#6b7888]">deployable </span>
                  <span className="text-[#ffb224] font-bold">{v.deployable_base != null ? fmtQty(v.deployable_base) : "—"}</span>
                  {v.deployable_quote_value != null && <span className="text-[#6b7888]"> ({fmtUsd(v.deployable_quote_value)})</span>}
                </div>
              </div>
              {v.reason && <div className="text-[9px] text-[#6b7888] mt-1">{v.reason}</div>}
              {(v.secondary_factors || []).map((s, i) => (
                <div key={i} className="text-[9px] text-[#fb923c] mt-0.5">⚠ {s}</div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
};
