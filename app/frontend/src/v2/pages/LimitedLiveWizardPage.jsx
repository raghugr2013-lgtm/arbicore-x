/**
 * ArbiCore X — UI v2 · Guided LIMITED_LIVE Wizard (Phase 9)
 *
 * A read-only, tap-and-go dashboard that walks the operator through every
 * step required before the first controlled Flash Loan broadcast.  It
 * polls `/api/arbicore/wizard/state` every 5s and composes a single view
 * of readiness across:
 *
 *   1. RPC configuration          6. Executor identity verification
 *   2. Wallet registration        7. Kill Switch
 *   3. Secret registration        8. Certification pass
 *   4. Gas wallet balance         9. Execution mode
 *   5. FlashLoanReceiver deploy  10. Final execution checklist
 *
 * Nothing on this page mutates state directly — every action links out to
 * the existing Flash Loan Operator page for the actual operation.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const POLL_MS = 5000;

const TONE = {
  READY:   { bg: "#022c22", fg: "#4ade80", border: "#065f46", label: "READY"   },
  WAIT:    { bg: "#3d2500", fg: "#fbbf24", border: "#78350f", label: "WAIT"    },
  BLOCKED: { bg: "#3a0a0a", fg: "#f87171", border: "#7f1d1d", label: "BLOCKED" },
  INFO:    { bg: "#0f172a", fg: "#93c5fd", border: "#1e3a8a", label: "INFO"    },
};

const MONO = "var(--v2-font-mono, ui-monospace, SFMono-Regular, monospace)";
const Card = ({ title, subtitle, children, testId }) => (
  <section
    data-testid={testId}
    style={{
      background: "var(--v2-bg-surface, #0f141c)",
      border: "1px solid var(--v2-border-subtle, #1c2733)",
      padding: 18,
      marginBottom: 14,
      borderRadius: 2,
    }}
  >
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
      <h2 style={{ color: "#e2e8f0", fontSize: 14, fontWeight: 600, margin: 0, textTransform: "uppercase", letterSpacing: 1.4 }}>{title}</h2>
      {subtitle && <span style={{ color: "#64748b", fontSize: 11 }}>{subtitle}</span>}
    </div>
    {children}
  </section>
);

const Pill = ({ status, size = "sm" }) => {
  const t = TONE[status] || TONE.INFO;
  const pad = size === "lg" ? "5px 14px" : "2px 10px";
  const fs  = size === "lg" ? 12 : 10;
  return (
    <span
      data-testid={`wiz-pill-${status}`}
      style={{
        background: t.bg, color: t.fg, border: `1px solid ${t.border}`,
        fontFamily: MONO, fontSize: fs, padding: pad, borderRadius: 2,
        textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600,
      }}
    >
      {t.label}
    </span>
  );
};

const StepRow = ({ step, index }) => {
  const t = TONE[step.status] || TONE.INFO;
  const [expanded, setExpanded] = useState(false);
  const showFix = step.fix_path && (step.status === "BLOCKED" || step.status === "WAIT");
  return (
    <div
      data-testid={`wiz-step-${step.key}`}
      style={{
        borderLeft: `3px solid ${t.border}`,
        background: "#0a0f18",
        padding: "12px 16px",
        marginBottom: 8,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontFamily: MONO, color: "#64748b", fontSize: 12, width: 24 }}>
            {String(index + 1).padStart(2, "0")}
          </span>
          <span style={{ color: "#e2e8f0", fontSize: 13, fontWeight: 500 }}>{step.label}</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Pill status={step.status} />
          {showFix && (
            <Link to={step.fix_path}
              data-testid={`wiz-step-fix-${step.key}`}
              style={{
                background: "var(--v2-accent, #ffb224)", color: "#0b0f14",
                border: "none", padding: "3px 10px",
                fontFamily: MONO, fontSize: 10, fontWeight: 600,
                cursor: "pointer", borderRadius: 2,
                textTransform: "uppercase", letterSpacing: 0.5,
                textDecoration: "none",
              }}
            >FIX →</Link>
          )}
          <button
            data-testid={`wiz-step-toggle-${step.key}`}
            onClick={() => setExpanded((v) => !v)}
            style={{
              background: "transparent", border: "1px solid #1c2733",
              color: "#94a3b8", fontFamily: MONO, fontSize: 10,
              padding: "3px 8px", cursor: "pointer", borderRadius: 2,
              textTransform: "uppercase", letterSpacing: 0.5,
            }}
          >{expanded ? "hide" : "detail"}</button>
        </div>
      </div>
      {step.detail && (
        <div style={{ color: "#94a3b8", fontSize: 12, fontFamily: MONO }}>{step.detail}</div>
      )}
      {expanded && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, paddingLeft: 36, marginTop: 4 }}>
          {step.reason && (
            <div style={{ color: "#93c5fd", fontSize: 11, fontFamily: MONO }}>
              why: {step.reason}
            </div>
          )}
          {step.action_hint && (
            <div style={{ color: "#fbbf24", fontSize: 11, fontFamily: MONO }}>
              → {step.action_hint}
            </div>
          )}
          {step.fix_path && (
            <div style={{ color: "#64748b", fontSize: 10, fontFamily: MONO }}>
              fix_path: <Link to={step.fix_path} style={{ color: "#93c5fd" }}>{step.fix_path}</Link>
            </div>
          )}
          {step.evidence && Object.keys(step.evidence).length > 0 && (
            <pre style={{
              background: "#050810", border: "1px solid #1c2733",
              color: "#64748b", fontFamily: MONO, fontSize: 10,
              padding: 10, margin: 0, borderRadius: 2,
              maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}>{JSON.stringify(step.evidence, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
};


export default function LimitedLiveWizardPage() {
  const [state, setState] = useState(null);
  const [prereqs, setPrereqs] = useState(null);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    try {
      const [r1, r2] = await Promise.all([
        axios.get(`${API}/arbicore/wizard/state`, { timeout: 12000 }),
        axios.get(`${API}/arbicore/wizard/flash-loan-prereqs`, { timeout: 12000 }),
      ]);
      setState(r1.data);
      setPrereqs(r2.data);
      setErr(null);
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(() => setTick((t) => t + 1), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => { load(); /* refetch on tick */ }, [tick, load]);

  const overall = state?.overall_status || "INFO";
  const ready = !!state?.ready_to_broadcast;
  const steps = useMemo(() => state?.steps || [], [state]);
  const blockers = state?.blockers || [];

  return (
    <div data-testid="wizard-root" style={{ padding: "20px 24px", maxWidth: 1080, margin: "0 auto" }}>
      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 20,
      }}>
        <div>
          <h1 style={{
            color: "#e2e8f0", fontSize: 22, fontWeight: 600, margin: 0,
            letterSpacing: 1.2,
          }}>Guided LIMITED_LIVE Wizard</h1>
          <div style={{ color: "#64748b", fontFamily: MONO, fontSize: 11, marginTop: 4 }}>
            Flash Loan · Base · updates every {POLL_MS / 1000}s
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Pill status={overall} size="lg" />
          <Link
            to="/v2/flash-loan-operator"
            data-testid="wiz-goto-operator"
            style={{
              background: ready ? "var(--v2-accent, #ffb224)" : "transparent",
              color: ready ? "#0b0f14" : "#94a3b8",
              border: ready ? "none" : "1px solid #1c2733",
              padding: "9px 16px", fontFamily: MONO, fontSize: 12,
              fontWeight: 600, textDecoration: "none",
              textTransform: "uppercase", letterSpacing: 0.6, borderRadius: 2,
              pointerEvents: ready ? "auto" : "auto",
              opacity: ready ? 1 : 0.65,
            }}
          >Open Operator Page →</Link>
        </div>
      </div>

      {err && (
        <div data-testid="wiz-err" style={{
          background: "#3a0a0a", border: "1px solid #7f1d1d",
          color: "#fca5a5", padding: "10px 14px", marginBottom: 16,
          fontFamily: MONO, fontSize: 11,
        }}>Wizard state unavailable: {err}</div>
      )}

      {/* Summary strip */}
      <Card testId="wiz-summary" title="Broadcast readiness" subtitle={state?.generated_at}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          <SumTile label="Overall"   value={overall}                 mono />
          <SumTile label="Strategy"  value={state?.strategy || "—"}  mono />
          <SumTile label="Chain"     value={state?.chain || "—"}     mono />
          <SumTile label="Blockers"  value={String(blockers.length)} mono />
        </div>
        {blockers.length > 0 && (
          <div style={{ marginTop: 12, color: "#fca5a5", fontSize: 11, fontFamily: MONO }}>
            <strong>Blocking:</strong> {blockers.join(", ")}
          </div>
        )}
        {ready && (
          <div data-testid="wiz-ready-banner" style={{
            marginTop: 12, padding: "10px 14px",
            background: "#022c22", border: "1px solid #065f46",
            color: "#4ade80", fontFamily: MONO, fontSize: 12,
          }}>
            ✓ All prerequisites cleared. Operator may proceed to broadcast.
          </div>
        )}
      </Card>

      {/* Steps */}
      <Card testId="wiz-steps" title="Ten-step operator checklist">
        {steps.length === 0 && (
          <div style={{ color: "#64748b", fontFamily: MONO, fontSize: 12 }}>loading…</div>
        )}
        {steps.map((s, i) => <StepRow key={s.key} step={s} index={i} />)}
      </Card>

      {/* Phase 10.6 · Flash Loan family prereqs */}
      {prereqs && (
        <Card testId="wiz-fl-prereqs" title="Flash Loan family prerequisites"
              subtitle={prereqs.ok ? "READY" : `${prereqs.unmet.length} unmet`}>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {(prereqs.checks || []).map((c) => {
              const t = TONE[c.status] || TONE.INFO;
              return (
                <div key={c.key} data-testid={`wiz-fl-${c.key}`}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "8px 12px",
                    background: "#0a0f18",
                    borderLeft: `3px solid ${t.border}`,
                  }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ color: "#e2e8f0", fontSize: 12, fontFamily: MONO }}>{c.key}</span>
                    <span style={{ color: "#94a3b8", fontSize: 11, fontFamily: MONO }}>{c.detail}</span>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <Pill status={c.status} />
                    {c.fix_path && c.status !== "READY" && (
                      <Link to={c.fix_path}
                        data-testid={`wiz-fl-fix-${c.key}`}
                        style={{
                          background: "var(--v2-accent, #ffb224)", color: "#0b0f14",
                          border: "none", padding: "3px 10px",
                          fontFamily: MONO, fontSize: 10, fontWeight: 600,
                          borderRadius: 2, textDecoration: "none",
                          textTransform: "uppercase", letterSpacing: 0.5,
                        }}
                      >FIX →</Link>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}

const SumTile = ({ label, value, mono }) => (
  <div style={{
    background: "#050810", border: "1px solid #1c2733",
    padding: "10px 14px", borderRadius: 2,
  }}>
    <div style={{ color: "#64748b", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 4 }}>{label}</div>
    <div style={{ color: "#e2e8f0", fontSize: 14, fontFamily: mono ? MONO : "inherit", fontWeight: 600 }}>{value}</div>
  </div>
);
