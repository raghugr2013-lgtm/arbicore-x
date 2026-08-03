/**
 * ArbiCore X — LoginPage (production entry experience)
 *
 * Institutional-grade dark login card using UI v2 tokens.  Renders as the
 * unauthenticated landing surface at `/login`.  On successful login the
 * user is routed to `/initialization`.
 */
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import "@/v2/theme/tokens.css";
import "@/v2/pages/LoginPage.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const { isAuthenticated, login } = useAuth();
  const [username, setUsername] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (isAuthenticated) {
    return <Navigate to="/initialization" replace />;
  }

  async function onSubmit(evt) {
    evt.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await login({ username, passphrase });
      navigate("/initialization", { replace: true });
    } catch (err) {
      setError(err?.message || "Login failed.");
      setSubmitting(false);
    }
  }

  return (
    <div className="ui-v2-root arbicore-login" data-testid="login-page">
      <div className="arbicore-login__panel">
        <div className="arbicore-login__brand">
          <div className="arbicore-login__wordmark">ArbiCore X</div>
          <div className="arbicore-login__tag">Autonomous Institutional Arbitrage Intelligence Platform</div>
        </div>

        <form className="arbicore-login__form" onSubmit={onSubmit} noValidate>
          <label className="arbicore-login__field">
            <span className="arbicore-login__label">Operator</span>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting}
              spellCheck={false}
              data-testid="login-username-input"
            />
          </label>

          <label className="arbicore-login__field">
            <span className="arbicore-login__label">Passphrase</span>
            <input
              type="password"
              autoComplete="current-password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              disabled={submitting}
              data-testid="login-passphrase-input"
            />
          </label>

          {error && (
            <div className="arbicore-login__error" role="alert" data-testid="login-error">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="arbicore-login__submit"
            disabled={submitting || !username || !passphrase}
            data-testid="login-submit-button"
          >
            {submitting ? "Authenticating…" : "Sign in"}
          </button>
        </form>

        <div className="arbicore-login__footer">
          <span>v2.0.1 · MID foundation</span>
          <span className="arbicore-login__footer-sep">·</span>
          <span>SHADOW mode</span>
        </div>
      </div>
    </div>
  );
}
