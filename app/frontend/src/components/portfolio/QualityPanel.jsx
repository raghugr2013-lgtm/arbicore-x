import { fmtPct, fmtQty, fmtUsd } from "@/lib/fmt";

const LABEL_STYLE = {
  "READY": { color: "#34d399" },
  "PROMISING": { color: "#fbbf24" },
  "NOT READY": { color: "#f87171" },
  "INSUFFICIENT DATA": { color: "#6b7888" },
};

const FACTORS = [
  ["frequency", "Frequency"], ["duration", "Duration"], ["spread", "Spread"],
  ["capacity", "Capacity"], ["confidence", "Confidence"], ["stability", "Stability"],
  ["exchange_health", "Exch. health"], ["gate_reliability", "Gate reliab."],
];

const Metric = ({ label, value }) => (
  <div>
    <div className="text-[8px] uppercase tracking-wider text-[#6b7888]">{label}</div>
    <div className="text-[11px] font-bold text-[#c9d4e0]">{value ?? "—"}</div>
  </div>
);

export const QualityPanel = ({ data, hours, setHours }) => {
  const venues = data?.venues || [];
  return (
    <div className="panel" data-testid="quality-panel">
      <div className="panel-title">
        Opportunity Quality — Automation Readiness
        <span className="float-right flex gap-1">
          {[[24, "24h"], [168, "7d"], [720, "30d"]].map(([h, l]) => (
            <button key={h} data-testid={`quality-range-${h}`} onClick={() => setHours(h)}
                    className={`px-1.5 ${hours === h ? "text-[#ffb224]" : "text-[#6b7888] hover:text-[#c9d4e0]"}`}>
              {l}
            </button>
          ))}
        </span>
      </div>
      {venues.length === 0 && <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3 font-mono">
        {venues.map((v, rank) => {
          const ls = LABEL_STYLE[v.readiness_label] || LABEL_STYLE["INSUFFICIENT DATA"];
          const m = v.metrics || {};
          return (
            <div key={v.exchange} className="border border-[#1f2a36] p-3" data-testid={`quality-venue-${v.exchange}`}>
              <div className="flex items-center gap-2">
                <span className="text-[#3d4a59] text-[10px]">#{rank + 1}</span>
                <span className="font-bold uppercase text-sm">{v.exchange}</span>
                <div className="flex-1" />
                <span className="text-2xl font-bold" data-testid={`quality-score-${v.exchange}`} style={{ color: ls.color }}>
                  {v.readiness_score != null ? v.readiness_score : "—"}
                </span>
              </div>
              <div className="text-[9px] font-bold tracking-[0.2em] mb-2" style={{ color: ls.color }}
                   data-testid={`quality-label-${v.exchange}`}>
                {v.readiness_label}
              </div>
              <div className="grid grid-cols-3 gap-x-2 gap-y-1.5 mb-2">
                <Metric label="Episodes/day" value={m.episodes_per_day} />
                <Metric label="Avg duration" value={m.avg_duration_min != null ? `${m.avg_duration_min}m` : null} />
                <Metric label="Avg spread" value={m.avg_net_spread_pct != null ? fmtPct(m.avg_net_spread_pct) : null} />
                <Metric label="Avg capacity" value={m.avg_capacity_base != null ? fmtQty(m.avg_capacity_base) : null} />
                <Metric label="Avg confidence" value={m.avg_confidence} />
                <Metric label="GO minutes" value={m.go_minutes} />
                <Metric label="Deployable" value={m.est_deployable_base != null ? fmtQty(m.est_deployable_base) : (m.free_base == null ? "no key" : null)} />
                <Metric label="Profit/day (liq)" value={m.est_profit_per_day_quote != null ? fmtUsd(m.est_profit_per_day_quote) : null} />
                <Metric label="Profit/day (depl)" value={m.est_deployable_profit_per_day_quote != null ? fmtUsd(m.est_deployable_profit_per_day_quote) : null} />
              </div>
              <div className="space-y-0.5">
                {FACTORS.map(([k, label]) => {
                  const fv = (v.factors || {})[k];
                  return (
                    <div key={k} className="flex items-center gap-2 text-[9px]">
                      <span className="w-20 text-[#6b7888]">{label}</span>
                      <div className="flex-1 h-1 bg-[#1f2a36]">
                        <div className="h-1" style={{ width: `${fv || 0}%`, background: scoreBar(fv) }} />
                      </div>
                      <span className="w-8 text-right" style={{ color: scoreBar(fv) }}>{fv != null ? Math.round(fv) : "—"}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      <div className="font-mono text-[9px] text-[#3d4a59] mt-2" data-testid="quality-note">
        Identifies which opportunities may justify FUTURE automation — no execution capability exists in this build.
        READY ≥70 · PROMISING 45–69 · NOT READY &lt;45
      </div>
    </div>
  );
};

const scoreBar = (v) => (v == null ? "#3d4a59" : v >= 70 ? "#34d399" : v >= 45 ? "#fbbf24" : "#f87171");
