/**
 * ArbiCore X — UI v2 · Feature flag resolver (Slice 0)
 *
 * Two-tier check:
 *  1. Build-time: `REACT_APP_ENABLE_UI_V2` (baked into the bundle by CRA).
 *  2. Runtime override (developer convenience): `?ui_v2=1` query param or
 *     `localStorage.arbicore_ui_v2 = "1"`. Neither is authoritative in
 *     production; they exist so operators can preview /v2 while the flag
 *     defaults to off.
 *
 * The legacy UI must never call this — it lives entirely inside src/v2/.
 */

const TRUTHY = new Set(["1", "true", "yes", "on"]);

function readBuildFlag() {
  const v = process.env.REACT_APP_ENABLE_UI_V2;
  if (!v) return false;
  return TRUTHY.has(String(v).trim().toLowerCase());
}

function readRuntimeOverride() {
  try {
    const search = typeof window !== "undefined" ? window.location.search : "";
    if (search) {
      const params = new URLSearchParams(search);
      const q = params.get("ui_v2");
      if (q && TRUTHY.has(q.toLowerCase())) return true;
      if (q && ["0", "false", "off", "no"].includes(q.toLowerCase())) return false;
    }
    if (typeof window !== "undefined" && window.localStorage) {
      const ls = window.localStorage.getItem("arbicore_ui_v2");
      if (ls && TRUTHY.has(ls.toLowerCase())) return true;
    }
  } catch (_e) {
    /* SSR / privacy modes — ignore */
  }
  return null;
}

export function isUiV2Enabled() {
  const override = readRuntimeOverride();
  if (override !== null) return override;
  return readBuildFlag();
}
