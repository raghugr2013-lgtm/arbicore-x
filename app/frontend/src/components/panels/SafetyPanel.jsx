import { Check, X } from "lucide-react";
import { VerdictBadge } from "@/components/VerdictBadge";

const Bar = ({ label, value, testId }) => {
  const color = value >= 70 ? "#34d399" : value >= 40 ? "#fbbf24" : "#f87171";
  return (
    <div className="mb-2" data-testid={testId}>
      <div className="flex justify-between text-[10px] font-mono mb-0.5">
        <span className="uppercase tracking-widest text-[#6b7888]">{label}</span>
        <span style={{ color }} className="font-bold">{Math.round(value ?? 0)}</span>
      </div>
      <div className="h-1.5 bg-[#1f2a36] flex gap-px">
        {Array.from({ length: 20 }).map((_, i) => (
          <div key={i} className="flex-1" style={{ background: i < Math.round((value ?? 0) / 5) ? color : "transparent" }} />
        ))}
      </div>
    </div>
  );
};

export const SafetyPanel = ({ evaluation }) => {
  const s = evaluation?.scores || {};
  const gates = evaluation?.gates || [];
  const reasons = evaluation?.reasons || [];
  const overall = s.overall;
  const overallColor = overall >= 70 ? "#34d399" : overall >= 45 ? "#fbbf24" : "#f87171";
  return (
    <div className="panel" data-testid="safety-panel">
      <div className="panel-title">Safety Score · GO / NO-GO</div>
      <div className="flex items-center gap-4 mb-3">
        <div data-testid="overall-score" className="font-mono text-5xl font-bold" style={{ color: overallColor }}>
          {overall == null ? "—" : Math.round(overall)}
        </div>
        <div className="flex flex-col gap-1.5">
          <VerdictBadge verdict={evaluation?.verdict} />
          <span className="text-[10px] font-mono text-[#6b7888]">OVERALL / 100</span>
        </div>
      </div>
      <Bar label="Spread" value={s.spread} testId="score-spread" />
      <Bar label="Liquidity" value={s.liquidity} testId="score-liquidity" />
      <Bar label="Volatility" value={s.volatility} testId="score-volatility" />
      <Bar label="Transfer risk" value={s.transfer_risk} testId="score-transfer" />

      <div className="mt-3 border-t border-[#1f2a36] pt-2">
        <div className="text-[10px] uppercase tracking-widest text-[#6b7888] mb-1">Hard gates</div>
        {gates.map((g) => (
          <div key={g.id} data-testid={`gate-${g.id}`} className="flex items-start gap-1.5 text-xs py-0.5 font-mono">
            {g.passed ? (
              <Check size={13} className="text-[#34d399] mt-0.5 shrink-0" />
            ) : (
              <X size={13} className="text-[#f87171] mt-0.5 shrink-0" />
            )}
            <span className={g.passed ? "text-[#6b7888]" : "text-[#f87171]"}>
              <b>{g.id}</b> — {g.detail}
            </span>
          </div>
        ))}
      </div>
      {reasons.length > 0 && (
        <div className="mt-2 border-t border-[#1f2a36] pt-2" data-testid="verdict-reasons">
          <div className="text-[10px] uppercase tracking-widest text-[#6b7888] mb-1">Reasons</div>
          {reasons.map((r, i) => (
            <div key={i} className="text-xs text-[#c9d4e0] py-0.5">› {r}</div>
          ))}
        </div>
      )}
    </div>
  );
};
