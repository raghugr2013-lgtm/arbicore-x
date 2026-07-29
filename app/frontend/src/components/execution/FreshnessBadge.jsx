// Data-integrity badge: 🟢 LIVE / 🟡 STALE / 🔴 INVALID (no hidden stale value
// should ever drive a decision). Accepts a gate-freshness item ({age_s, threshold_s,
// fresh}) OR explicit { ageS, thresholdS, stale, invalid }.
const STATUS = {
  LIVE: { c: "#34d399", label: "LIVE" },
  STALE: { c: "#ffb224", label: "STALE" },
  INVALID: { c: "#f87171", label: "INVALID" },
};

const compute = ({ item, ageS, thresholdS, stale, invalid }) => {
  if (invalid) return "INVALID";
  const a = item ? item.age_s : ageS;
  let fresh = item ? item.fresh : undefined;
  if (fresh === undefined) {
    if (stale === true) fresh = false;
    else if (stale === false) fresh = true;
    else if (a == null) return "INVALID";
    else if (thresholdS != null) fresh = a <= thresholdS;
    else fresh = true;
  }
  if (a == null && fresh !== true) return "INVALID";
  return fresh === false ? "STALE" : "LIVE";
};

export const FreshnessBadge = ({ item, ageS, thresholdS, stale, invalid, showAge = true, testid }) => {
  const status = compute({ item, ageS, thresholdS, stale, invalid });
  const s = STATUS[status];
  const a = item ? item.age_s : ageS;
  return (
    <span
      data-testid={testid}
      data-freshness={status}
      className="inline-flex items-center gap-1 font-mono text-[8px] font-bold tracking-wider px-1.5 py-0.5 border"
      style={{ borderColor: s.c + "66", color: s.c, background: s.c + "0d" }}
      title={item ? item.source : undefined}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.c }} />
      {s.label}
      {showAge && a != null && <span className="text-[#6b7888] font-normal">· {a}s</span>}
    </span>
  );
};
