/** Display helpers for the ledger research view. Null stays unavailable. Zero stays zero. */

export const RESEARCH_ACTIONS = ["Download Excel"];

export function displayScalar(value) {
  if (value === null || value === undefined || value === "") return "unavailable";
  if (typeof value === "number" && Object.is(value, 0)) return "0";
  return String(value);
}

export function displayMoney(value) {
  if (value === null || value === undefined) return "unavailable";
  const num = Number(value);
  if (!Number.isFinite(num)) return "unavailable";
  const sign = num < 0 ? "-" : "";
  return `${sign}$${Math.abs(num).toFixed(2)}`;
}

export function orderedLegs(legs) {
  return [...(legs || [])].sort((a, b) => Number(a?.leg_index ?? 0) - Number(b?.leg_index ?? 0));
}

export function pageWindow(total, page, pageSize) {
  const size = Math.min(100, Math.max(1, Number(pageSize) || 1));
  const current = Math.max(1, Number(page) || 1);
  const start = (current - 1) * size;
  const count = Math.max(0, Number(total) || 0);
  return {
    page: current,
    pageSize: size,
    start,
    end: Math.min(count, start + size),
    total: count,
  };
}
