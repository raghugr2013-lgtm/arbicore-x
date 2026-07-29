export const fmtPrice = (v) =>
  v == null ? "—" : v < 0.01 ? v.toFixed(7) : v.toLocaleString(undefined, { maximumFractionDigits: 2 });

export const fmtQty = (v) => {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return v.toFixed(a < 10 ? 2 : 0);
};

export const fmtPct = (v, signed = true) =>
  v == null ? "—" : `${signed && v > 0 ? "+" : ""}${v.toFixed(2)}%`;

export const fmtUsd = (v) => (v == null ? "—" : "$" + fmtQty(v));

export const pctClass = (v) =>
  v == null ? "text-[#6b7888]" : v > 0 ? "text-[#34d399]" : v < 0 ? "text-[#f87171]" : "text-[#c9d4e0]";

export const VERDICT_STYLE = {
  GO: "bg-[#34d399] text-black",
  WAIT: "bg-[#fbbf24] text-black",
  NO_GO: "bg-[#f87171] text-black",
};

export const fmtTime = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], { hour12: false });
  } catch {
    return "—";
  }
};
