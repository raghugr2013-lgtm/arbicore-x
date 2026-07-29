export const HoldProbPanel = ({ evaluation }) => {
  const hp = evaluation?.hold_probability || {};
  const conf = evaluation?.confidence || {};
  const active = hp.status === "active" && hp.probability != null;
  const pct = active ? Math.round(hp.probability * 100) : null;
  const color = pct == null ? "#6b7888" : pct >= 75 ? "#34d399" : pct >= 50 ? "#fbbf24" : "#f87171";
  const q = hp.quantiles || {};
  return (
    <div className="panel" data-testid="holdprob-panel">
      <div className="panel-title">Hold Probability — statistical scaffold v1</div>
      <div className="flex items-center gap-5">
        <div data-testid="holdprob-value" className="font-mono text-5xl font-bold" style={{ color }}>
          {pct != null ? `${pct}%` : "—"}
        </div>
        <div className="text-[10px] font-mono text-[#6b7888] leading-relaxed">
          P(bid holds above breakeven<br />through {hp.horizon_min ?? 30}-min transfer window)
          <div className="mt-1 text-[#c9d4e0]" data-testid="holdprob-samples">
            samples: {hp.sample_count ?? 0} · lookback {hp.lookback_h ?? "—"}h
          </div>
        </div>
      </div>
      {!active && (
        <div className="mt-2 border border-[#fbbf24]/30 bg-[#fbbf24]/5 px-2 py-1.5 text-[10px] font-mono text-[#fbbf24]" data-testid="holdprob-collecting">
          COLLECTING DATA — needs ≥30 horizon-window samples ({hp.sample_count ?? 0} so far).
          Method: empirical Δ-distribution, no AI.
        </div>
      )}
      <div className="grid grid-cols-3 gap-2 mt-3 font-mono text-center">
        {[["P10 Δ", q.p10], ["MEDIAN Δ", q.p50], ["P90 Δ", q.p90]].map(([l, v]) => (
          <div key={l} className="border border-[#1f2a36] py-1.5">
            <div className={`text-sm font-bold ${v > 0 ? "text-[#34d399]" : v < 0 ? "text-[#f87171]" : "text-[#6b7888]"}`}>
              {v != null ? `${v > 0 ? "+" : ""}${v}%` : "—"}
            </div>
            <div className="text-[8px] tracking-widest text-[#6b7888]">{l}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 border-t border-[#1f2a36] pt-2">
        <div className="text-[10px] uppercase tracking-widest text-[#6b7888] mb-1">
          Route confidence {conf.score != null && <span className="text-[#ffb224] float-right">{Math.round(conf.score)}%</span>}
        </div>
        <div className="grid grid-cols-2 gap-x-3 text-[10px] font-mono" data-testid="confidence-components">
          {Object.entries(conf.components || {}).map(([k, v]) => (
            <div key={k} className="flex justify-between py-0.5 border-b border-[#1f2a36]/40">
              <span className="text-[#6b7888]">{k.replace(/_/g, " ")}</span>
              <span className={v == null ? "text-[#3d4a59]" : v >= 70 ? "text-[#34d399]" : v >= 40 ? "text-[#fbbf24]" : "text-[#f87171]"}>
                {v != null ? Math.round(v) : "n/a"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
