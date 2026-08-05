/**
 * ArbiCore X — LoginPage (production entry experience)
 *
 * Institutional-grade dark login card using UI v2 tokens.  Renders as the
 * unauthenticated landing surface at `/login`.
 *
 * v2.9.3 — When `setupComplete === false` the same card switches into the
 * one-time CREATE ADMIN variant (adds "Confirm passphrase" + calls
 * `setup(...)` instead of `login(...)`).  Visual chrome unchanged.
 */
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import "@/v2/theme/tokens.css";
import "@/v2/pages/LoginPage.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const { isAuthenticated, isValidating, setupComplete, login, setup } = useAuth();
  const [username, setUsername] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (isAuthenticated) {
    return <Navigate to="/initialization" replace />;
  }

  // While /auth/status is in flight we don't know yet whether to show setup
  // or login. Render the login skeleton with the submit disabled — this
  // matches the v2 dark aesthetic without popping between two layouts.
  const bootLoading = isValidating && setupComplete === null;
  const isSetup = setupComplete === false;

  async function onSubmit(evt) {
    evt.preventDefault();
    if (submitting || bootLoading) return;
    setError(null);

    if (isSetup) {
      if (passphrase.length < 8) {
        setError("Passphrase must be at least 8 characters.");
        return;
      }
      if (passphrase !== confirm) {
        setError("Passphrases do not match.");
        return;
      }
    }

    setSubmitting(true);
    try {
      if (isSetup) {
        await setup(username, passphrase);
      } else {
        await login({ username, passphrase });
      }
      navigate("/initialization", { replace: true });
    } catch (err) {
      setError(err?.message || (isSetup ? "Setup failed." : "Login failed."));
      setSubmitting(false);
    }
  }

  const heading = isSetup ? "Create administrator" : "ArbiCore X";
  const tag = isSetup
    ? "First-run setup — this creates the sole administrator. Registration locks permanently after this."
    : "Autonomous Institutional Arbitrage Intelligence Platform";
  const submitLabel = submitting
    ? (isSetup ? "Creating…" : "Authenticating…")
    : (isSetup ? "Create admin & enter" : "Sign in");
  const canSubmit = !submitting && !bootLoading && username && passphrase && (!isSetup || confirm);

  return (
    <div className="ui-v2-root arbicore-login" data-testid="login-page">
      <div className="arbicore-login__panel">
        <div className="arbicore-login__brand">
          <div className="arbicore-login__wordmark">{heading}</div>
          <div className="arbicore-login__tag">{tag}</div>
        </div>

        <form className="arbicore-login__form" onSubmit={onSubmit} noValidate>
          <label className="arbicore-login__field">
            <span className="arbicore-login__label">Operator</span>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting || bootLoading}
              spellCheck={false}
              data-testid="login-username-input"
            />
          </label>

          <label className="arbicore-login__field">
            <span className="arbicore-login__label">Passphrase</span>
            <input
              type="password"
              autoComplete={isSetup ? "new-password" : "current-password"}
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              disabled={submitting || bootLoading}
              data-testid="login-passphrase-input"
            />
          </label>

          {isSetup && (
            <label className="arbicore-login__field">
              <span className="arbicore-login__label">Confirm passphrase</span>
              <input
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                disabled={submitting || bootLoading}
                data-testid="login-confirm-input"
              />
            </label>
          )}

          {error && (
            <div className="arbicore-login__error" role="alert" data-testid="login-error">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="arbicore-login__submit"
            disabled={!canSubmit}
            data-testid="login-submit-button"
          >
            {submitLabel}
          </button>
        </form>

        <div className="arbicore-login__footer">
          <span>v2.9.3 · single-admin</span>
          <span className="arbicore-login__footer-sep">·</span>
          <span>{isSetup ? "FIRST-RUN SETUP" : "SHADOW mode"}</span>
        </div>
      </div>
    </div>
  );
}
