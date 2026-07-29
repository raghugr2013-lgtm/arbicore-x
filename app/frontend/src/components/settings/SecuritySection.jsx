import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { formatApiErrorDetail, useAuth } from "@/context/AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const SecuritySection = () => {
  const { user, logoutAll } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const changePassword = async (e) => {
    e.preventDefault();
    if (next.length < 8) return toast.error("New password must be at least 8 characters");
    if (next !== confirm) return toast.error("Passwords do not match");
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/auth/change-password`, {
        current_password: current, new_password: next,
      });
      toast.success(data.message);
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    }
    setBusy(false);
  };

  return (
    <div className="space-y-4" data-testid="security-section">
      <div className="panel">
        <div className="panel-title">Account</div>
        <div className="font-mono text-[11px] text-[#c9d4e0]" data-testid="security-account-info">
          <span className="text-[#6b7888]">operator:</span> <span className="font-bold">{user?.username}</span>{" "}
          <span className="text-[#6b7888]">role:</span> <span className="text-[#ffb224]">{user?.role}</span>
          <div className="text-[#6b7888] mt-1">single-admin system — registration is permanently locked</div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Change password</div>
        <form onSubmit={changePassword} className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-2xl">
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Current</label>
            <input data-testid="security-current-password" type="password" value={current} required
                   onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">New (min 8)</label>
            <input data-testid="security-new-password" type="password" value={next} required minLength={8}
                   onChange={(e) => setNext(e.target.value)} autoComplete="new-password"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Confirm</label>
            <input data-testid="security-confirm-password" type="password" value={confirm} required
                   onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div className="md:col-span-3">
            <button data-testid="security-change-password-btn" type="submit" disabled={busy}
                    className="font-mono text-[10px] font-bold tracking-widest px-4 py-2 border border-[#ffb224] text-[#ffb224] bg-[#ffb224]/10 hover:bg-[#ffb224]/20 disabled:opacity-50">
              {busy ? "…" : "CHANGE PASSWORD"}
            </button>
            <span className="ml-3 font-mono text-[9px] text-[#3d4a59]">revokes every other session; this one stays alive</span>
          </div>
        </form>
      </div>

      <div className="panel">
        <div className="panel-title">Sessions</div>
        <button data-testid="security-logout-all-btn" onClick={logoutAll}
                className="font-mono text-[10px] font-bold tracking-widest px-4 py-2 border border-[#f87171] text-[#f87171] bg-[#f87171]/10 hover:bg-[#f87171]/20">
          LOGOUT FROM ALL SESSIONS
        </button>
        <span className="ml-3 font-mono text-[9px] text-[#3d4a59]">bumps the session version — every issued token (including this one) becomes invalid</span>
      </div>

      <div className="panel">
        <div className="panel-title">Backup &amp; recovery</div>
        <div className="font-mono text-[11px] text-[#6b7888] space-y-1">
          <div>• Forgot password → run <span className="text-[#c9d4e0]">cd /app/backend && python reset_admin.py</span> on the host; setup re-opens. Market data &amp; vault keys are untouched.</div>
          <div>• Locked out (5 failed logins) → wait 15 minutes, or clear <span className="text-[#c9d4e0]">login_attempts</span> in MongoDB.</div>
          <div>• Back up <span className="text-[#c9d4e0]">backend/.env</span> — losing <span className="text-[#f87171]">VAULT_KEY</span> makes stored exchange keys permanently undecryptable.</div>
          <div>• Full procedure: ARCHITECTURE → “Dashboard Auth &amp; Key Vault Security”.</div>
        </div>
      </div>
    </div>
  );
};
