/**
 * ArbiCore X — AuthContext (v2.0.3 · backend-integrated)
 *
 * Real backend authentication via /api/auth/login (JWT bearer).
 * Session persisted in localStorage; refreshed via /api/auth/me on mount.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;
const STORAGE_KEY = "arbicore.session.v2";

const AuthContext = createContext(null);

function readSession() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || !parsed.token || !parsed.user) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeSession(sess) {
  try {
    if (sess) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sess));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch { /* ignore */ }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => readSession());
  const [initialized, setInitialized] = useState(() => Boolean(readSession()?.initialized));
  const [validating, setValidating] = useState(() => Boolean(readSession()));

  // Validate token via /auth/me on mount — logs out silently if revoked / expired.
  useEffect(() => {
    let cancelled = false;
    async function validate() {
      const s = readSession();
      if (!s?.token) { setValidating(false); return; }
      try {
        const res = await axios.get(`${API}/auth/me`, {
          headers: { Authorization: `Bearer ${s.token}` },
          timeout: 8000,
          validateStatus: () => true,
        });
        if (cancelled) return;
        if (res.status !== 200 || !res.data?.authenticated) {
          writeSession(null);
          setSession(null);
          setInitialized(false);
        }
      } catch {
        // network error during boot — keep local session (offline-tolerant)
      } finally {
        if (!cancelled) setValidating(false);
      }
    }
    validate();
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async ({ username, passphrase }) => {
    const cleanUser = (username || "").trim();
    const cleanPass = (passphrase || "").trim();
    if (!cleanUser || !cleanPass) {
      const err = new Error("Username and passphrase are required.");
      err.code = "EMPTY_CREDENTIALS";
      throw err;
    }
    if (cleanPass.length < 4) {
      const err = new Error("Passphrase too short.");
      err.code = "WEAK_PASSPHRASE";
      throw err;
    }
    let res;
    try {
      res = await axios.post(`${API}/auth/login`, {
        username: cleanUser,
        password: cleanPass,
      }, { timeout: 10000, validateStatus: () => true });
    } catch (err) {
      const e = new Error("Cannot reach authentication service.");
      e.code = "NETWORK_ERROR";
      throw e;
    }
    if (res.status === 401) {
      const e = new Error("Invalid credentials.");
      e.code = "INVALID_CREDENTIALS";
      throw e;
    }
    if (res.status !== 200 || !res.data?.token) {
      const e = new Error(res.data?.detail || `Login failed (HTTP ${res.status}).`);
      e.code = "LOGIN_FAILED";
      throw e;
    }
    const sess = {
      token: res.data.token,
      tokenType: res.data.token_type || "bearer",
      expiresAt: res.data.expires_at,
      user: res.data.user,
      initialized: false,
    };
    writeSession(sess);
    setSession(sess);
    setInitialized(false);
    return sess;
  }, []);

  const logout = useCallback(async () => {
    const s = readSession();
    if (s?.token) {
      try {
        await axios.post(`${API}/auth/logout`, null, {
          headers: { Authorization: `Bearer ${s.token}` },
          timeout: 5000,
          validateStatus: () => true,
        });
      } catch { /* ignore — we log out locally regardless */ }
    }
    writeSession(null);
    setSession(null);
    setInitialized(false);
  }, []);

  const markInitialized = useCallback(() => {
    setInitialized(true);
    setSession((prev) => {
      if (!prev) return prev;
      const updated = { ...prev, initialized: true };
      writeSession(updated);
      return updated;
    });
  }, []);

  const value = useMemo(() => ({
    user: session?.user || null,
    role: session?.user?.role || null,
    token: session?.token || null,
    isAuthenticated: Boolean(session?.token),
    isInitialized: Boolean(session?.token) && initialized,
    isValidating: validating,
    login,
    logout,
    markInitialized,
  }), [session, initialized, validating, login, logout, markInitialized]);

  return React.createElement(AuthContext.Provider, { value }, children);
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    return {
      user: null, role: null, token: null,
      isAuthenticated: false, isInitialized: false, isValidating: false,
      login: async () => { throw new Error("AuthProvider not mounted"); },
      logout: async () => {},
      markInitialized: () => {},
    };
  }
  return ctx;
}
