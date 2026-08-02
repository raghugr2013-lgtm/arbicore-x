import { fmtPct, fmtPrice, fmtUsd, pctClass } from "@/lib/fmt";

const StatusDot = ({ ok, unknown }) => (
  <span
    className={`inline-block w-2 h-2 ${
      unknown ? "bg-[#6b7888]" : ok ? "bg-[#34d399]" : "bg-[#f87171]"
    }`}
  />
);

export const OpportunityMonitor = ({ comparison }) => (
  <div className="panel" data-testid="opportunity-monitor">
    <div className="panel-title">Opportunity Monitor — venue comparison</div>
    <table className="w-full text-sm">
      <thead>
        <tr className="panel-th">
          <th className="text-left">Venue</th>
          <th className="text-left">Market</th>
          <th className="text-right">Last</th>
          <th className="text-right">Spread vs Buy</th>
          <th className="text-right">24h Vol</th>
          <th className="text-center">Dep</th>
          <th className="text-center">Wd</th>
          <th className="text-right">Age</th>
        </tr>
      </thead>
      <tbody className="font-mono">
        {(comparison || []).map((c) => (
          <tr
            key={c.exchange}
            data-testid={`opp-row-${c.exchange}`}
            className={`border-b border-[#1f2a36]/60 hover:bg-[#141b24] ${
              c.primary ? "bg-[#141b24]/70" : ""
            }`}
          >
            <td className="py-1.5 uppercase font-bold text-xs tracking-wider">
              {c.exchange}
              {c.primary && <span className="ml-1.5 text-[9px] text-[#ffb224]">EXIT</span>}
              {c.source === "sim" && <span className="ml-1.5 text-[9px] text-[#38bdf8]">SIM</span>}
            </td>
            <td className="text-xs">
              {c.listed === false ? (
                <span className="text-[#6b7888]">not listed</span>
              ) : c.listed ? (
                <span className="text-[#34d399]">live</span>
              ) : (
                <span className="text-[#6b7888]">…</span>
              )}
            </td>
            <td className="text-right">{fmtPrice(c.last)}</td>
            <td className={`text-right font-bold ${pctClass(c.gross_spread_pct)}`}>
              {fmtPct(c.gross_spread_pct)}
            </td>
            <td className="text-right text-[#c9d4e0]">{fmtUsd(c.volume_24h_quote)}</td>
            <td className="text-center">
              <StatusDot ok={c.deposit_enabled === true} unknown={c.deposit_enabled == null} />
            </td>
            <td className="text-center">
              <StatusDot ok={c.withdraw_enabled === true} unknown={c.withdraw_enabled == null} />
            </td>
            <td className="text-right text-xs text-[#6b7888]">
              {c.ticker_age_s == null ? "—" : `${Math.round(c.ticker_age_s)}s`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    <div className="mt-2 text-[10px] font-mono text-[#6b7888]">
      DEP/WD: ● enabled · ● disabled · ● unknown (no public flag — verified in Phase 2)
    </div>
  </div>
);
