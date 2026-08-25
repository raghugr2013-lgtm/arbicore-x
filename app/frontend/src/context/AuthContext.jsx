import { API_BASE } from "@/lib/apiBase";
/**
 * ArbiCore X — AuthContext (v2.9.3 · canonical single-admin, cookie-based)
 *
 * Wire-up for the canonical Tree-A backend authentication surface
 * (routes/auth.py + services/auth.py).  Session lives entirely server-side
 * as httpOnly access_token + refresh_token cookies signed with JWT_SECRET.
 *
 * Contract exposed by useAuth():
 *   { user, role, isAuthenticated, isValidating, isInitialized,
 *     setupComplete, login, setup, logout, markInitialized }
 *
 * Also exports the helper `formatApiErrorDetail` used by Settings sections
 * (SecuritySection, TelegramSection, VaultSection).
 *
 * Historical note: v2.0.3's rewrite of this file consumed the retired
 * Tree-B bearer-token endpoints and dropped the setup / setupComplete
 * surface.  v2.9.3 restores the canonical contract without altering any
 * other frontend module.
 */
import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";
import axios from "axios";

const API = API_BASE;

// v2.9.3 — Canonical auth uses httpOnly cookies. Make every axios call in
// the app credentialed by default so business endpoints (e.g. Settings ➜
// Change Password, Vault, Telegram) automatically send the session cookie
// without touching each component.
axios.defaults.withCredentials = true;

// All auth traffic MUST send cookies; the backend sets httpOnly access_token
// + refresh_token on /setup and /login.
const client = axios.create({
  baseURL: API,
  withCredentials: true,
  timeout: 12000,
  validateStatus: () => true,
});

const AuthContext = createContext(null);

/**
 * Turn any FastAPI error payload (string, dict, or Pydantic validation list)
 * into a short human-readable string suitable for toast/inline display.
 * This helper is imported directly by Settings components; do not rename.
 */
export function formatApiErrorDetail(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      if (!d || typeof d !== "object") return String(d);
      const loc = Array.isArray(d.loc) ? d.loc.join(".") : "";
      return loc ? `${loc}: ${d.msg || ""}` : (d.msg || JSON.stringify(d));
    }).join(" · ");
  }
  if (typeof detail === "object") {
    if (detail.msg) return detail.msg;
    try { return JSON.stringify(detail); } catch { return String(detail); }
  }
  return String(detail);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [setupComplete, setSetupComplete] = useState(null);   // null = unknown yet
  const [isValidating, setIsValidating] = useState(true);
  const [isInitialized, setIsInitialized] = useState(false);

  /**
   * Boot: check /api/auth/status → setupComplete, then /api/auth/me for
   * existing session cookies.  Errors are non-fatal; we degrade to "no
   * session" without blocking render.
   */
  const bootstrap = useCallback(async () => {
    setIsValidating(true);
    try {
      const s = await client.get("/auth/status");
      if (s.status === 200 && s.data && typeof s.data.setup_complete === "boolean") {
        setSetupComplete(s.data.setup_complete);
      } else {
        // Backend reachable but unexpected shape — treat as setup_complete
        // so login form (not setup form) is shown; safer default.
        setSetupComplete(true);
      }
    } catch {
      // Network unreachable — leave setupComplete as null so LoginPage can
      // show a neutral "connecting…" state instead of the setup card.
      setSetupComplete(null);
    }

    try {
      const me = await client.get("/auth/me");
      if (me.status === 200 && me.data && me.data.id) {
        setUser(me.data);
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setIsValidating(false);
    }
  }, []);

  useEffect(() => { bootstrap(); }, [bootstrap]);

  /**
   * First-run admin creation.  Only valid while setupComplete === false.
   * Server sets cookies and returns the public user document.
   */
  const setup = useCallback(async (username, password) => {
    const u = (username || "").trim();
    if (u.length < 3) throw new Error("Username must be at least 3 characters.");
    if (!password || password.length < 8) throw new Error("Password must be at least 8 characters.");
    const res = await client.post("/auth/setup", { username: u, password });
    if (res.status === 403) {
      throw new Error(formatApiErrorDetail(res.data?.detail) || "Setup is locked.");
    }
    if (res.status !== 200 || !res.data || !res.data.id) {
      throw new Error(formatApiErrorDetail(res.data?.detail) || `Setup failed (HTTP ${res.status}).`);
    }
    setUser(res.data);
    setSetupComplete(true);
    setIsInitialized(false);
    return res.data;
  }, []);

  /**
   * Login accepts either (username, password) positional or an object
   * ({ username, passphrase }) — the latter is what v2/pages/LoginPage.jsx
   * uses.  Both names refer to the same secret; we forward as `password`.
   */
  const login = useCallback(async (...args) => {
    let u = "", p = "";
    if (args.length === 1 && typeof args[0] === "object" && args[0] !== null) {
      u = args[0].username || "";
      p = args[0].password || args[0].passphrase || "";
    } else {
      u = args[0] || "";
      p = args[1] || "";
    }
    u = u.trim();
    if (!u || !p) {
      const err = new Error("Username and password are required.");
      err.code = "EMPTY_CREDENTIALS";
      throw err;
    }
    const res = await client.post("/auth/login", { username: u, password: p });
    if (res.status === 401) {
      const e = new Error(formatApiErrorDetail(res.data?.detail) || "Invalid username or password.");
      e.code = "INVALID_CREDENTIALS";
      throw e;
    }
    if (res.status === 429) {
      const e = new Error(formatApiErrorDetail(res.data?.detail) || "Too many attempts — try again later.");
      e.code = "LOCKED";
      throw e;
    }
    if (res.status !== 200 || !res.data || !res.data.id) {
      const e = new Error(formatApiErrorDetail(res.data?.detail) || `Login failed (HTTP ${res.status}).`);
      e.code = "LOGIN_FAILED";
      throw e;
    }
    setUser(res.data);
    setSetupComplete(true);
    setIsInitialized(false);
    return res.data;
  }, []);

  const logout = useCallback(async () => {
    try { await client.post("/auth/logout"); } catch { /* logout locally anyway */ }
    setUser(null);
    setIsInitialized(false);
  }, []);

  /**
   * Bump server-side session_version → invalidates every issued token,
   * including this one. Used by SecuritySection.
   */
  const logoutAll = useCallback(async () => {
    try { await client.post("/auth/logout-all"); } catch { /* fall through */ }
    setUser(null);
    setIsInitialized(false);
  }, []);

  const markInitialized = useCallback(() => { setIsInitialized(true); }, []);

  const value = useMemo(() => ({
    user,
    role: user?.role || null,
    isAuthenticated: Boolean(user),
    isValidating,
    isInitialized,
    setupComplete,
    login,
    setup,
    logout,
    logoutAll,
    markInitialized,
  }), [user, isValidating, isInitialized, setupComplete, login, setup, logout, logoutAll, markInitialized]);

  return React.createElement(AuthContext.Provider, { value }, children);
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    return {
      user: null, role: null,
      isAuthenticated: false, isValidating: false, isInitialized: false,
      setupComplete: null,
      login: async () => { throw new Error("AuthProvider not mounted"); },
      setup: async () => { throw new Error("AuthProvider not mounted"); },
      logout: async () => {},
      logoutAll: async () => {},
      markInitialized: () => {},
    };
  }
  return ctx;
}
