import { VerdictBadge } from "@/components/VerdictBadge";
import { fmtPct, fmtQty, pctClass } from "@/lib/fmt";

export const VenueMatrix = ({ matrix }) => {
  const venues = matrix || [];
  const best = venues.filter((v) => v.verdict && v.verdict !== "NO_GO")
    .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))[0];
  const rows = [
    ["Verdict", (v) => <VerdictBadge verdict={v.verdict} size="sm" />],
    ["Route confidence", (v) => (
      <span className={`font-bold ${v.confidence >= 70 ? "text-[#34d399]" : v.confidence >= 45 ? "text-[#fbbf24]" : "text-[#f87171]"}`}>
        {v.confidence != null ? `${Math.round(v.confidence)}%` : "—"}
      </span>
    )],
    ["Net spread", (v) => <span className={pctClass(v.net_spread_pct)}>{fmtPct(v.net_spread_pct)}</span>],
    ["Recommended size", (v) => <span className="text-[#ffb224]">{fmtQty(v.recommended)}</span>],
    ["Safety score", (v) => (v.overall != null ? Math.round(v.overall) : "—")],
    ["Deposits", (v) => (
      v.deposit_enabled === true ? <span className="text-[#34d399]">enabled</span>
      : v.deposit_enabled === false ? <span className="text-[#f87171]">DISABLED</span>
      : <span className="text-[#6b7888]">unknown</span>
    )],
  ];
  return (
    <div className="panel" data-testid="venue-matrix">
      <div className="panel-title">
        Venue Matrix — side-by-side route evaluation
        {best && <span className="float-right text-[#34d399]">best executable: {best.exchange.toUpperCase()}</span>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="panel-th">
              <th className="text-left w-36">Metric</th>
              {venues.map((v) => (
                <th key={v.exchange} className={`text-center ${best?.exchange === v.exchange ? "text-[#34d399]" : ""}`}>
                  {v.exchange.toUpperCase()}
                  {v.source === "sim" && <span className="ml-1 text-[8px] text-[#38bdf8]">SIM</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, render]) => (
              <tr key={label} className="border-b border-[#1f2a36]/50">
                <td className="py-1.5 text-[10px] uppercase tracking-wider text-[#6b7888]">{label}</td>
                {venues.map((v) => (
                  <td key={v.exchange} data-testid={`matrix-${label.toLowerCase().replace(/ /g, "-")}-${v.exchange}`}
                      className={`text-center py-1.5 ${best?.exchange === v.exchange ? "bg-[#34d399]/5" : ""}`}>
                    {v.listed === false ? <span className="text-[#3d4a59]">not listed</span>
                      : v.listed == null ? <span className="text-[#3d4a59]">…</span>
                      : render(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
