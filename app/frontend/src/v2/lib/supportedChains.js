/**
 * Canonical Network Config allowlist fallback.
 *
 * Prefer the backend GET /arbicore/settings/network `supported_chains` field
 * (sourced from NetworkConfigRepo.SUPPORTED_CHAINS). This constant is only
 * used when the API payload is unavailable so the UI still shows all six.
 *
 * Order matches backend SUPPORTED_CHAINS.
 */
export const FALLBACK_SUPPORTED_CHAINS = Object.freeze([
  "base",
  "ethereum",
  "arbitrum",
  "optimism",
  "polygon",
  "bnb",
]);

/**
 * Resolve the operator-facing chain allowlist from a network GET payload.
 * Always returns a non-empty list of known chain ids (never invents others).
 */
export function resolveSupportedChains(payload) {
  const fromApi = payload?.supported_chains;
  if (Array.isArray(fromApi) && fromApi.length > 0) {
    const allow = new Set(FALLBACK_SUPPORTED_CHAINS);
    const filtered = fromApi
      .filter((c) => typeof c === "string" && allow.has(c));
    if (filtered.length > 0) return filtered;
  }
  return [...FALLBACK_SUPPORTED_CHAINS];
}

/**
 * Chains on the allowlist that are not currently enabled — candidates for
 * "Add Network" (enablement only; does not invent unsupported chains).
 */
export function unusedAllowlistChains(supportedChains, chainsEnabled) {
  const enabled = chainsEnabled || {};
  return (supportedChains || []).filter((c) => !enabled[c]);
}

/**
 * Enable an allowlisted chain in a Network Config form draft.
 * Returns `{ ok, form, error }`. Does not APPLY — VALIDATE→APPLY remains
 * the operator lifecycle.
 */
export function enableAllowlistedChain(form, chain, supportedChains) {
  const allow = supportedChains || FALLBACK_SUPPORTED_CHAINS;
  if (!allow.includes(chain)) {
    return { ok: false, form, error: `unsupported chain '${chain}'` };
  }
  if (form?.chains_enabled?.[chain]) {
    return { ok: false, form, error: `chain '${chain}' already enabled` };
  }
  const next = JSON.parse(JSON.stringify(form || {}));
  next.chains_enabled = { ...(next.chains_enabled || {}), [chain]: true };
  next.rpc_urls = { ...(next.rpc_urls || {}) };
  if (!Array.isArray(next.rpc_urls[chain])) next.rpc_urls[chain] = [];
  next.executor_addresses = { ...(next.executor_addresses || {}) };
  if (next.executor_addresses[chain] == null) next.executor_addresses[chain] = "";
  next.mev_relay_urls = { ...(next.mev_relay_urls || {}) };
  if (next.mev_relay_urls[chain] == null) next.mev_relay_urls[chain] = "";
  next.gas_settings = { ...(next.gas_settings || {}) };
  if (!next.gas_settings[chain] || typeof next.gas_settings[chain] !== "object") {
    next.gas_settings[chain] = {
      gas_price_gwei: null,
      max_fee_gwei: null,
      prio_fee_gwei: null,
    };
  }
  next.native_price_usd = { ...(next.native_price_usd || {}) };
  if (!Object.prototype.hasOwnProperty.call(next.native_price_usd, chain)) {
    next.native_price_usd[chain] = null;
  }
  return { ok: true, form: next, error: null };
}
