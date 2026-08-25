import { API_BASE } from "@/lib/apiBase";
/** Guided Flash Loan Journey (Phase 10.7) — 14 stages, progressive unlock. */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";

const API = API_BASE;
const MONO = "var(--v2-font-mono, ui-monospace, monospace)";
const TONE = {
  READY:   { bg: "#022c22", fg: "#4ade80", bd: "#065f46" },
  WAIT:    { bg: "#3d2500", fg: "#fbbf24", bd: "#78350f" },
  BLOCKED: { bg: "#3a0a0a", fg: "#f87171", bd: "#7f1d1d" },
  INFO:    { bg: "#0f172a", fg: "#93c5fd", bd: "#1e3a8a" },
};

const Pill = ({ status }) => {
  const t = TONE[status] || TONE.INFO;
  return <span style={{ background: t.bg, color: t.fg, border: `1px solid ${t.bd}`, fontFamily: MONO, fontSize: 10, padding: "2px 10px", borderRadius: 2, textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600 }}>{status}</span>;
};

export default function FlashLoanJourneyPage() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/arbicore/wizard/journey`, { timeout: 12000 });
      setData(r.data); setErr(null);
    } catch (e) { setErr(String(e?.message || e)); }
  }, []);
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, [load]);

  const markVpsReady = async () => {
    if (!window.confirm("Mark the system as VALIDATED and ready for VPS deployment? This closes the operator journey.")) return;
    setBusy(true);
    try {
      const reason = window.prompt("Reason (evidence of success):") || "operator validated LIMITED_LIVE";
      const r = await axios.post(`${API}/arbicore/wizard/journey/mark-vps-ready`, { reason });
      if (r.data?.ok) { alert("System marked VPS-ready. Journey complete."); load(); }
      else alert(`Failed: ${r.data?.error || "unknown"}`);
    } catch (e) { alert(`Failed: ${e.message}`); }
    setBusy(false);
  };

  const stages = data?.stages || [];
  const completed = data?.completed;
  const currentIdx = data?.current_stage_index ?? 0;
  const readyCount = stages.filter(s => s.status === "READY" || s.status === "INFO").length;
  const pct = stages.length ? Math.round((readyCount / stages.length) * 100) : 0;

  return (
    <div data-testid="journey-root" style={{ padding: "20px 24px", maxWidth: 980, margin: "0 auto" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ color: "#e2e8f0", fontSize: 22, fontWeight: 600, margin: 0, letterSpacing: 1.2 }}>Flash Loan Operator Journey</h1>
        <div style={{ color: "#64748b", fontFamily: MONO, fontSize: 11, marginTop: 4 }}>Fourteen stages · progressive unlock · auto-detects completion every 5s</div>
      </div>

      {/* Progress bar */}
      <div style={{ background: "#0f141c", border: "1px solid #1c2733", padding: 14, marginBottom: 14, borderRadius: 2 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ color: "#e2e8f0", fontSize: 13 }}>Progress · {readyCount}/{stages.length} stages complete</span>
          <span style={{ color: "#ffb224", fontFamily: MONO, fontSize: 13, fontWeight: 600 }}>{pct}%</span>
        </div>
        <div style={{ height: 6, background: "#0a0f18", border: "1px solid #1c2733", borderRadius: 2, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${pct}%`, background: completed ? "#4ade80" : "#ffb224", transition: "width 500ms" }} />
        </div>
      </div>

      {err && <div data-testid="journey-err" style={{ background: "#3a0a0a", border: "1px solid #7f1d1d", color: "#fca5a5", padding: "10px 14px", marginBottom: 14, fontFamily: MONO, fontSize: 11 }}>{err}</div>}

      {/* Stages */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
        {stages.map((s, i) => {
          const t = TONE[s.status] || TONE.INFO;
          const locked = !s.unlocked;
          return (
            <div key={s.key} data-testid={`journey-stage-${s.key}`}
              style={{
                background: locked ? "#050810" : "#0a0f18",
                borderLeft: `3px solid ${s.is_current ? "#ffb224" : t.bd}`,
                padding: "12px 16px", opacity: locked ? 0.45 : 1,
                display: "flex", justifyContent: "space-between", alignItems: "center",
                borderRadius: 2,
              }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flex: 1 }}>
                <span style={{ fontFamily: MONO, color: s.is_current ? "#ffb224" : "#64748b", fontSize: 12, width: 32, fontWeight: s.is_current ? 700 : 400 }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div style={{ display: "flex", flexDirection: "column", gap: 3, flex: 1 }}>
                  <span style={{ color: "#e2e8f0", fontSize: 13, fontWeight: s.is_current ? 600 : 500 }}>{s.label}</span>
                  {s.detail && <span style={{ color: "#94a3b8", fontSize: 11, fontFamily: MONO }}>{s.detail}</span>}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <Pill status={s.status} />
                {s.fix_path && !locked && s.status !== "READY" && (
                  <Link to={s.fix_path} data-testid={`journey-fix-${s.key}`}
                    style={{ background: "#ffb224", color: "#0b0f14", padding: "4px 12px", fontFamily: MONO, fontSize: 10, fontWeight: 600, textDecoration: "none", borderRadius: 2, textTransform: "uppercase", letterSpacing: 0.5 }}>OPEN →</Link>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Final action */}
      {stages.length > 0 && stages[13].status !== "READY" && stages[12].status === "READY" && (
        <div data-testid="journey-mark-vps" style={{ background: "#0f141c", border: "1px solid #ffb224", padding: 18, borderRadius: 2, textAlign: "center" }}>
          <div style={{ color: "#ffb224", fontSize: 13, marginBottom: 8, fontFamily: MONO, textTransform: "uppercase", letterSpacing: 0.8 }}>Final step</div>
          <div style={{ color: "#e2e8f0", fontSize: 12, marginBottom: 12 }}>
            Review Post-Trade + Telegram alerts + Evidence bundles. When satisfied, mark the system as validated and ready for VPS deployment.
          </div>
          <button onClick={markVpsReady} disabled={busy} data-testid="journey-mark-vps-btn"
            style={{ background: "#ffb224", color: "#0b0f14", border: "none", padding: "10px 24px", fontFamily: MONO, fontSize: 12, fontWeight: 600, cursor: busy ? "not-allowed" : "pointer", borderRadius: 2, textTransform: "uppercase", letterSpacing: 0.8 }}>
            MARK VPS-READY
          </button>
        </div>
      )}

      {completed && (
        <div data-testid="journey-complete" style={{ background: "#022c22", border: "1px solid #065f46", padding: 18, borderRadius: 2, textAlign: "center" }}>
          <div style={{ color: "#4ade80", fontSize: 16, fontWeight: 600, marginBottom: 6 }}>✓ Journey Complete</div>
          <div style={{ color: "#94a3b8", fontSize: 12 }}>
            ArbiCore X is validated. You may now provision the Contabo VPS and export config from Settings › Audit.
          </div>
        </div>
      )}
    </div>
  );
}
