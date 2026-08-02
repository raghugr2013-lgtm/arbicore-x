import { VERDICT_STYLE } from "@/lib/fmt";

export const VerdictBadge = ({ verdict, size = "lg" }) => {
  if (!verdict) {
    return (
      <span data-testid="verdict-badge" className="font-mono text-xs px-3 py-1 border border-[#1f2a36] text-[#6b7888]">
        EVALUATING…
      </span>
    );
  }
  const cls = VERDICT_STYLE[verdict] || "bg-[#1f2a36] text-[#c9d4e0]";
  const pad = size === "lg" ? "px-4 py-1.5 text-sm" : "px-2 py-0.5 text-[10px]";
  return (
    <span data-testid="verdict-badge" className={`font-mono font-bold tracking-widest ${pad} ${cls}`}>
      {verdict.replace("_", " ")}
    </span>
  );
};
