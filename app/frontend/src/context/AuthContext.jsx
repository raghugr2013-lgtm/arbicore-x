/**
 * ArbiCore X — AuthContext (v2.0.2 · production entry experience)
 *
 * localStorage-backed session state driving the production Login →
 * Initialization → Dashboard flow.
 *
 * Backend auth endpoint (`/api/auth/login`) currently lives in the dormant
 * canonical routes tree; until it is wired in Sprint 1B this context
 * performs a local session bind (non-empty username + passphrase is
 * accepted).  The session shape and API is designed so the wire-up in
 * Sprint 1B is a drop-in replacement of `login()` internals — no
 * consumer changes required.
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "arbicore.session.v1";

const AuthContext = createContext(null);

function readSession() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.username) return null;
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

  // Login — sprint-1A local stub; drop-in replaceable in Sprint 1B.
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
    // Sprint 1A: no backend round-trip.  We record the session locally so
    // the app can boot into the initialization + dashboard experience.
    const now = new Date().toISOString();
    const sess = { username: cleanUser, role: "operator", createdAt: now, initialized: false };
    writeSession(sess);
    setSession(sess);
    setInitialized(false);
    return sess;
  }, []);

  const logout = useCallback(() => {
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

  // Reset initialized flag on tab open if the session says so (fresh boot
  // after a real deploy should always show the init sequence once).
  useEffect(() => {
    if (session && !session.initialized) setInitialized(false);
  }, [session]);

  const value = useMemo(() => ({
    user: session ? { username: session.username, role: session.role } : null,
    isAuthenticated: Boolean(session),
    isInitialized: Boolean(session) && initialized,
    login,
    logout,
    markInitialized,
  }), [session, initialized, login, logout, markInitialized]);

  return React.createElement(AuthContext.Provider, { value }, children);
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    // Preserve back-compat with the earlier preview stub — callers that
    // render outside an AuthProvider (e.g. isolated storybook stubs) see
    // a benign shape rather than a hard crash.
    return {
      user: null,
      isAuthenticated: false,
      isInitialized: false,
      login: async () => { throw new Error("AuthProvider not mounted"); },
      logout: () => {},
      markInitialized: () => {},
    };
  }
  return ctx;
}
