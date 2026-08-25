/**
 * ArbiCore X — API base normalization (single source of truth).
 *
 * Frontend code historically mixed three patterns:
 *   `${REACT_APP_BACKEND_URL}/api`, direct origin usage, and `/api/...` paths.
 * Under a same-origin validator (REACT_APP_BACKEND_URL=/api) the naive
 * `${BASE}/api` produced `/api/api/...`. This module normalizes the env var so
 * every caller resolves to exactly one `/api` segment.
 *
 * Supported REACT_APP_BACKEND_URL values:
 *   - "https://arbicorex.coinnike.com"  (production absolute)  -> API_BASE ".../api"
 *   - "/api"                            (same-origin validator) -> API_BASE "/api"
 *   - ""                                (same-origin root)      -> API_BASE "/api"
 *   - trailing slashes / trailing "/api" are tolerated.
 *
 * Exports:
 *   API_BASE       — prefix for callers that append route paths (…/arbicore/…).
 *   BACKEND_ORIGIN — origin WITHOUT /api, for callers that append their own /api.
 *   apiUrl(path)   — join helper guaranteeing a single /api.
 */

/** Normalize to a base that ends in exactly one `/api` (no trailing slash). */
export function computeApiBase(raw) {
  const noTrail = String(raw == null ? "" : raw).trim().replace(/\/+$/, "");
  if (noTrail === "") return "/api";
  if (noTrail === "/api") return "/api";
  if (noTrail.endsWith("/api")) return noTrail;
  return `${noTrail}/api`;
}

/** Origin WITHOUT the /api suffix ("" for same-origin). */
export function computeOrigin(raw) {
  const noTrail = String(raw == null ? "" : raw).trim().replace(/\/+$/, "");
  if (noTrail === "/api" || noTrail === "") return "";
  if (noTrail.endsWith("/api")) return noTrail.slice(0, -"/api".length);
  return noTrail;
}

export const API_BASE = computeApiBase(process.env.REACT_APP_BACKEND_URL);
export const BACKEND_ORIGIN = computeOrigin(process.env.REACT_APP_BACKEND_URL);

/** Join API_BASE with a route path, guaranteeing exactly one leading slash. */
export function apiUrl(path = "") {
  const p = String(path || "");
  const withSlash = p.startsWith("/") ? p : `/${p}`;
  return `${API_BASE}${withSlash}`;
}
