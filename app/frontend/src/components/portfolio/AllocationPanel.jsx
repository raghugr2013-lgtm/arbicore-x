import { fmtUsd } from "@/lib/fmt";

const Bar = ({ pct, color }) => (
  <div className="flex-1 h-1.5 bg-[#1f2a36]">
    <div className="h-1.5" style={{ width: `${Math.min(pct || 0, 100)}%`, background: color }} />
  </div>
);

export const AllocationPanel = ({ data }) => {
  const venues = data?.venues || [];
  return (
    <div className="panel" data-testid="allocation-panel">
      <div className="panel-title">
        Capital Allocation vs Opportunity
        <span className="float-right text-[#3d4a59]">informational — no rebalancing actions</span>
      </div>
      {venues.length === 0 && <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>}
      <div className="font-mono text-[10px] space-y-2">
        {venues.map((v) => (
          <div key={v.exchange} data-testid={`allocation-row-${v.exchange}`}>
            <div className="flex items-center gap-2">
              <span className="w-20 font-bold uppercase text-[11px]">{v.exchange}</span>
              <span className="text-[#6b7888]">
                {v.capital_usd != null ? fmtUsd(v.capital_usd) : "no key"} · {v.go_minutes}m GO
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="w-20 text-[9px] text-[#38bdf8]">capital</span>
              <Bar pct={v.capital_pct} color="#38bdf8" />
              <span className="w-10 text-right">{v.capital_pct != null ? `${v.capital_pct}%` : "—"}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-20 text-[9px] text-[#34d399]">opportunity</span>
              <Bar pct={v.opportunity_pct} color="#34d399" />
              <span className="w-10 text-right">{v.opportunity_pct != null ? `${v.opportunity_pct}%` : "—"}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3">
        <div className="font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Findings</div>
        {(data?.recommendations || []).map((r, i) => (
          <div key={i} className="font-mono text-[10px] text-[#ffb224] py-0.5" data-testid={`allocation-finding-${i}`}>
            ▸ {r}
          </div>
        ))}
      </div>
    </div>
  );
};
