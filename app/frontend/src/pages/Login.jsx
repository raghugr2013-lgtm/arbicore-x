import { useState } from "react";
import { Navigate } from "react-router-dom";
import { formatApiErrorDetail, useAuth } from "@/context/AuthContext";

export default function Login() {
  const { user, setupComplete, login, setup } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const isSetup = setupComplete === false;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (isSetup) {
      if (password.length < 8) return setError("Password must be at least 8 characters");
      if (password !== confirm) return setError("Passwords do not match");
    }
    setBusy(true);
    try {
      if (isSetup) await setup(username.trim(), password);
      else await login(username.trim(), password);
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    }
    setBusy(false);
  };

  return (
    <div className="min-h-[calc(100vh-60px)] flex items-center justify-center px-4" data-testid="login-page">
      <div className="w-full max-w-sm border border-[#1f2a36] bg-[#10161e] p-6">
        <div className="font-mono text-[10px] tracking-[0.3em] text-[#ffb224] mb-1">
          {isSetup ? "FIRST-RUN SETUP" : "RESTRICTED TERMINAL"}
        </div>
        <h1 className="font-mono text-lg font-bold tracking-wider text-[#c9d4e0] mb-1">
          {isSetup ? "CREATE ADMIN ACCOUNT" : "OPERATOR LOGIN"}
        </h1>
        <p className="font-mono text-[11px] text-[#6b7888] mb-5">
          {setupComplete === null
            ? "checking auth state…"
            : isSetup
              ? "No account exists yet. Define the single admin credential — registration locks permanently after this."
              : "Single-admin system. Sessions use httpOnly JWT cookies."}
        </p>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Username</label>
            <input data-testid="auth-username-input" value={username} onChange={(e) => setUsername(e.target.value)}
                   autoComplete="username" required minLength={3}
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Password</label>
            <input data-testid="auth-password-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   autoComplete={isSetup ? "new-password" : "current-password"} required
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          {isSetup && (
            <div>
              <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Confirm password</label>
              <input data-testid="auth-confirm-input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                     autoComplete="new-password" required
                     className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
            </div>
          )}
          {error && (
            <div data-testid="auth-error" className="border border-[#f87171]/40 bg-[#f87171]/10 px-3 py-2 font-mono text-[11px] text-[#f87171]">
              {error}
            </div>
          )}
          <button data-testid="auth-submit-btn" type="submit" disabled={busy || setupComplete === null}
                  className="w-full font-mono text-[11px] font-bold tracking-[0.2em] px-3 py-2.5 border border-[#ffb224] text-[#ffb224] bg-[#ffb224]/10 hover:bg-[#ffb224]/20 transition-colors disabled:opacity-50">
            {busy ? "…" : isSetup ? "CREATE ADMIN & ENTER" : "AUTHENTICATE"}
          </button>
        </form>
        {!isSetup && (
          <p className="mt-4 font-mono text-[9px] text-[#3d4a59]">
            Lost the password? Run <span className="text-[#6b7888]">python reset_admin.py</span> on the backend host to re-open setup.
          </p>
        )}
      </div>
    </div>
  );
}
