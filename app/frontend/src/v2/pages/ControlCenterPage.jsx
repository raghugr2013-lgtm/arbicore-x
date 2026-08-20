/**
 * ArbiCore X — Operator Control Center (P0-1 / P0-2)
 *
 * Renders the BACKEND-AUTHORITATIVE readiness + mode model. The UI only
 * REQUESTS mode changes; the backend decides. LIMITED_LIVE / FULL_AUTOMATION
 * are shown locked with their exact blockers. Includes a persistent
 * Emergency Stop wired to the authoritative kill switch.
 *
 * No readiness is ever computed client-side. No fake values.
 */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const MONO = "var(--v2-font-mono, ui-monospace, SFMono-Regular, monospace)";

const TONE = {
  GREEN:  { bg: "#022c22", fg: "#4ade80", border: "#065f46", dot: "#22c55e" },
  YELLOW: { bg: "#3d2500", fg: "#fbbf24", border: "#78350f", dot: "#f59e0b" },
  RED:    { bg: "#3a0a0a", fg: "#f87171", border: "#7f1d1d", dot: "#ef4444" },
  INFO:   { bg: "#0f172a", fg: "#93c5fd", border: "#1e3a8a", dot: "#3b82f6" },
};

const Pill = ({ status }) => {
  const t = TONE[status] || TONE.INFO;
  return (
    <span data-testid={`cc-pill-${status}`} style={{
      background: t.bg, color: t.fg, border: `1px solid ${t.border}`,
      fontFamily: MONO, fontSize: 10, padding: "2px 8px", borderRadius: 2,
      textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600,
    }}>{status}</span>
  );
};

const List = ({ label, items, color }) =>
  (items && items.length) ? (
    <div style={{ marginTop: 6 }}>
      <div style={{ color: "#64748b", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.6 }}>{label}</div>
      {items.map((x, i) => (
        <div key={i} style={{ color, fontSize: 11, fontFamily: MONO, wordBreak: "break-word" }}>• {x}</div>
      ))}
    </div>
  ) : null;

export default function ControlCenterPage() {
  const [readiness, setReadiness] = useState(null);
  const [kill, setKill] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [r, k] = await Promise.all([
        axios.get(`${API}/arbicore/control/readiness`, { timeout: 20000 }),
        axios.get(`${API}/arbicore/execution/kill-switch`, { timeout: 15000 }),
      ]);
      setReadiness(r.data);
      setKill(k.data?.state || null);
    } catch (e) {
      setErr(String(e?.response?.data?.detail || e?.message || e));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const requestMode = async (mode) => {
    setBusy(true); setMsg(null); setErr(null);
    try {
      const r = await axios.post(`${API}/arbicore/control/mode`, { mode });
      const d = r.data;
      setMsg(d.applied
        ? `Mode applied → ${d.current_mode}`
        : `Refused: ${d.decision?.reason || "not permitted"}`);
      await load();
    } catch (e) {
      setErr(String(e?.response?.data?.detail || e?.message || e));
    } finally { setBusy(false); }
  };

  const toggleKill = async () => {
    setBusy(true); setMsg(null); setErr(null);
    const engaged = kill?.engaged;
    const path = engaged ? "disengage" : "engage";
    try {
      const r = await axios.post(`${API}/arbicore/execution/kill-switch/${path}`,
        { reason: engaged ? "operator resume via Control Center" : "operator EMERGENCY STOP via Control Center" });
      setKill(r.data?.state || null);
      await load();
    } catch (e) {
      setErr(String(e?.response?.data?.detail || e?.message || e));
    } finally { setBusy(false); }
  };

  const overall = readiness?.overall_status || "INFO";
  const modes = readiness?.modes || {};
  const components = readiness?.components || [];
  const engaged = !!kill?.engaged;

  return (
    <div data-testid="control-center-root" style={{ padding: "20px 24px", maxWidth: 1180, margin: "0 auto" }}>
      {/* Header + Emergency Stop */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
        <div>
          <h1 style={{ color: "#e2e8f0", fontSize: 22, fontWeight: 600, margin: 0, letterSpacing: 1.2 }}>Control Center</h1>
          <div style={{ color: "#64748b", fontFamily: MONO, fontSize: 11, marginTop: 4 }}>
            Backend-authoritative readiness · SHADOW / PAPER only · live modes hard-gated
          </div>
        </div>
        <button
          data-testid="emergency-stop-btn"
          onClick={toggleKill}
          disabled={busy}
          style={{
            background: engaged ? "#022c22" : "#7f1d1d",
            color: engaged ? "#4ade80" : "#fff",
            border: `1px solid ${engaged ? "#065f46" : "#ef4444"}`,
            padding: "12px 22px", fontFamily: MONO, fontSize: 13, fontWeight: 700,
            cursor: busy ? "not-allowed" : "pointer", textTransform: "uppercase",
            letterSpacing: 1, borderRadius: 3, boxShadow: engaged ? "none" : "0 0 18px rgba(239,68,68,.35)",
          }}
        >{engaged ? "▶ Resume (kill switch ON)" : "■ Emergency Stop"}</button>
      </div>

      {msg && <div data-testid="cc-msg" style={{ background: "#0f172a", border: "1px solid #1e3a8a", color: "#93c5fd", padding: "8px 12px", marginBottom: 12, fontFamily: MONO, fontSize: 11 }}>{msg}</div>}
      {err && <div data-testid="cc-err" style={{ background: "#3a0a0a", border: "1px solid #7f1d1d", color: "#fca5a5", padding: "8px 12px", marginBottom: 12, fontFamily: MONO, fontSize: 11 }}>{err}</div>}

      {/* Kill-switch banner */}
      <div data-testid="cc-killswitch-state" style={{
        background: engaged ? "#3a0a0a" : "#0a0f18",
        border: `1px solid ${engaged ? "#7f1d1d" : "#1c2733"}`,
        padding: "10px 14px", marginBottom: 16, borderRadius: 2,
        display: "flex", justifyContent: "space-between", fontFamily: MONO, fontSize: 12,
      }}>
        <span style={{ color: engaged ? "#f87171" : "#4ade80" }}>
          KILL SWITCH: {engaged ? "ENGAGED — execution denied (scanning/analytics continue)" : "DISENGAGED — normal safety gates apply"}
        </span>
        {kill?.reason && <span style={{ color: "#64748b" }}>reason: {kill.reason}</span>}
      </div>

      {/* Overall */}
      <section style={{ background: "var(--v2-bg-surface, #0f141c)", border: "1px solid #1c2733", padding: 16, marginBottom: 16, borderRadius: 2, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ color: "#64748b", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.8 }}>Overall readiness</div>
          <div style={{ color: "#e2e8f0", fontSize: 18, fontFamily: MONO }}>current mode: {readiness?.current_mode || "—"}</div>
        </div>
        <Pill status={overall} />
      </section>

      {/* Modes */}
      <h2 style={{ color: "#e2e8f0", fontSize: 13, textTransform: "uppercase", letterSpacing: 1.4, margin: "6px 0 10px" }}>Operating Modes</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: 12, marginBottom: 22 }}>
        {["SHADOW", "PAPER", "PROFIT_ENGINE", "LIMITED_LIVE", "FULL_AUTOMATION"].map((m) => {
          const e = modes[m] || {};
          const t = TONE[e.status] || TONE.INFO;
          const locked = e.can_activate === false;
          return (
            <div key={m} data-testid={`mode-card-${m}`} style={{ background: "#0a0f18", border: `1px solid ${t.border}`, borderRadius: 3, padding: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 600 }}>{m.replace("_", " ")}</span>
                <Pill status={e.status || "INFO"} />
              </div>
              <button
                data-testid={`mode-select-${m}`}
                onClick={() => requestMode(m)}
                disabled={busy || locked}
                title={locked ? "Locked by backend" : "Request this mode"}
                style={{
                  width: "100%", padding: "8px 0", fontFamily: MONO, fontSize: 11,
                  fontWeight: 600, letterSpacing: 0.6, textTransform: "uppercase", borderRadius: 2,
                  cursor: (busy || locked) ? "not-allowed" : "pointer",
                  background: locked ? "#1a1414" : t.bg, color: locked ? "#f87171" : t.fg,
                  border: `1px solid ${t.border}`,
                }}
              >{locked ? "🔒 Locked" : "Select"}</button>
              <List label="blockers" items={e.blockers} color="#f87171" />
              <List label="warnings" items={e.warnings} color="#fbbf24" />
              <List label="requirements" items={e.requirements} color="#93c5fd" />
            </div>
          );
        })}
      </div>

      {/* Components */}
      <h2 style={{ color: "#e2e8f0", fontSize: 13, textTransform: "uppercase", letterSpacing: 1.4, margin: "6px 0 10px" }}>Readiness Components</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 10 }}>
        {components.map((c) => {
          const t = TONE[c.status] || TONE.INFO;
          return (
            <div key={c.name} data-testid={`component-${c.name}`} style={{ background: "#0a0f18", borderLeft: `3px solid ${t.border}`, borderRadius: 2, padding: "10px 12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "#e2e8f0", fontSize: 12 }}>{c.name}</span>
                <Pill status={c.status} />
              </div>
              <List label="passed" items={c.passed} color="#4ade80" />
              <List label="warnings" items={c.warnings} color="#fbbf24" />
              <List label="blockers" items={c.blockers} color="#f87171" />
              <List label="requirements" items={c.requirements} color="#93c5fd" />
            </div>
          );
        })}
      </div>
    </div>
  );
}
