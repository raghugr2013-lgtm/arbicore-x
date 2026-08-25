import { API_BASE } from "@/lib/apiBase";
/**
 * ArbiCore X — UI v2 · Executor Verification panel (Phase 9)
 *
 * Standalone dashboard that verifies a deployed FlashLoanReceiver
 * contract using the read-only `/api/arbicore/executor/verify`
 * endpoint.  Displays each individual check and the aggregate ready
 * status; supports overriding the address (useful for verifying a
 * fresh deploy before wiring it into the env var).
 */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API = API_BASE;
const MONO = "var(--v2-font-mono, ui-monospace, SFMono-Regular, monospace)";

const TONE = {
  READY:   { bg: "#022c22", fg: "#4ade80", border: "#065f46" },
  WAIT:    { bg: "#3d2500", fg: "#fbbf24", border: "#78350f" },
  BLOCKED: { bg: "#3a0a0a", fg: "#f87171", border: "#7f1d1d" },
  INFO:    { bg: "#0f172a", fg: "#93c5fd", border: "#1e3a8a" },
};

const Pill = ({ status }) => {
  const t = TONE[status] || TONE.INFO;
  return (
    <span
      data-testid={`exec-pill-${status}`}
      style={{
        background: t.bg, color: t.fg, border: `1px solid ${t.border}`,
        fontFamily: MONO, fontSize: 10, padding: "2px 8px", borderRadius: 2,
        textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600,
      }}
    >
      {status}
    </span>
  );
};

const CheckRow = ({ label, check }) => (
  <div style={{
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "10px 14px", background: "#0a0f18",
    borderLeft: `3px solid ${(TONE[check.status] || TONE.INFO).border}`,
    marginBottom: 6,
  }}>
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ color: "#e2e8f0", fontSize: 13 }}>{label}</span>
      {check.detail && (
        <span style={{ color: "#94a3b8", fontSize: 11, fontFamily: MONO, wordBreak: "break-all" }}>
          {check.detail}
        </span>
      )}
    </div>
    <Pill status={check.status} />
  </div>
);

export default function ExecutorVerifyPage() {
  const [address, setAddress] = useState("");
  const [expectedOwner, setExpectedOwner] = useState("");
  const [state, setState] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params = new URLSearchParams();
      if (address) params.set("address", address);
      if (expectedOwner) params.set("expected_owner", expectedOwner);
      const r = await axios.get(
        `${API}/arbicore/executor/verify${params.toString() ? "?" + params : ""}`,
        { timeout: 15000 },
      );
      setState(r.data);
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, [address, expectedOwner]);

  useEffect(() => { load(); }, [load]);

  const CHECK_LABELS = {
    address_configured: "1. Contract address configured",
    rpc_available:      "2. RPC available (Base)",
    contract_deployed:  "3. Contract deployed (bytecode present)",
    vault_matches:      "4. VAULT() matches Balancer V2 Vault",
    router_matches:     "5. ROUTER() matches Uniswap V3 SwapRouter02",
    owner_matches:      "6. owner() matches expected (optional)",
  };

  const overall = state?.overall_status || "INFO";

  return (
    <div data-testid="exec-verify-root" style={{ padding: "20px 24px", maxWidth: 960, margin: "0 auto" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ color: "#e2e8f0", fontSize: 22, fontWeight: 600, margin: 0, letterSpacing: 1.2 }}>
          Executor Verification
        </h1>
        <div style={{ color: "#64748b", fontFamily: MONO, fontSize: 11, marginTop: 4 }}>
          Verify a deployed FlashLoanReceiver contract on Base mainnet
        </div>
      </div>

      <section style={{
        background: "var(--v2-bg-surface, #0f141c)",
        border: "1px solid #1c2733",
        padding: 18, marginBottom: 14, borderRadius: 2,
      }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <label>
            <span style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, display: "block", marginBottom: 4 }}>
              Executor address (optional — defaults to env)
            </span>
            <input
              data-testid="exec-addr-input"
              value={address}
              onChange={(e) => setAddress(e.target.value.trim())}
              placeholder="0x… (leave blank to use ARBICORE_EXECUTOR_ADDRESS_BASE)"
              style={{
                width: "100%", padding: "8px 10px", background: "#0a0f18",
                border: "1px solid #1c2733", color: "#e2e8f0",
                fontFamily: MONO, fontSize: 12, borderRadius: 2, outline: "none",
              }}
            />
          </label>
          <label>
            <span style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, display: "block", marginBottom: 4 }}>
              Expected owner (optional)
            </span>
            <input
              data-testid="exec-owner-input"
              value={expectedOwner}
              onChange={(e) => setExpectedOwner(e.target.value.trim())}
              placeholder="0x… (the burner wallet that deployed the contract)"
              style={{
                width: "100%", padding: "8px 10px", background: "#0a0f18",
                border: "1px solid #1c2733", color: "#e2e8f0",
                fontFamily: MONO, fontSize: 12, borderRadius: 2, outline: "none",
              }}
            />
          </label>
          <button
            data-testid="exec-verify-btn"
            onClick={load}
            disabled={loading}
            style={{
              background: "var(--v2-accent, #ffb224)", color: "#0b0f14",
              border: "none", padding: "9px 18px", fontFamily: MONO,
              fontSize: 12, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
              textTransform: "uppercase", letterSpacing: 0.6, borderRadius: 2,
            }}
          >{loading ? "Verifying…" : "Verify"}</button>
        </div>
      </section>

      {err && (
        <div data-testid="exec-err" style={{
          background: "#3a0a0a", border: "1px solid #7f1d1d",
          color: "#fca5a5", padding: "10px 14px", marginBottom: 14,
          fontFamily: MONO, fontSize: 11,
        }}>{err}</div>
      )}

      {state && (
        <section style={{
          background: "var(--v2-bg-surface, #0f141c)",
          border: "1px solid #1c2733", padding: 18, marginBottom: 14, borderRadius: 2,
        }}>
          <div style={{
            display: "flex", justifyContent: "space-between",
            alignItems: "center", marginBottom: 12,
          }}>
            <h2 style={{ color: "#e2e8f0", fontSize: 14, fontWeight: 600, margin: 0, textTransform: "uppercase", letterSpacing: 1.4 }}>
              Verification result
            </h2>
            <Pill status={overall} />
          </div>

          <div style={{
            padding: "10px 14px",
            background: "#050810", border: "1px solid #1c2733",
            marginBottom: 14, borderRadius: 2,
          }}>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 10, fontSize: 12, fontFamily: MONO, color: "#94a3b8" }}>
              <span>Chain:</span>          <span style={{ color: "#e2e8f0" }}>{state.chain}</span>
              <span>Address:</span>        <span style={{ color: "#e2e8f0", wordBreak: "break-all" }}>{state.address || "—"}</span>
              <span>Expected VAULT:</span> <span style={{ color: "#e2e8f0", wordBreak: "break-all" }}>{state.expected?.vault || "—"}</span>
              <span>Expected ROUTER:</span><span style={{ color: "#e2e8f0", wordBreak: "break-all" }}>{state.expected?.router || "—"}</span>
              <span>Ready:</span>          <span style={{ color: state.ready ? "#4ade80" : "#fbbf24" }}>{state.ready ? "YES" : "NO"}</span>
            </div>
          </div>

          {state.checks && Object.entries(CHECK_LABELS).map(([key, label]) => (
            <CheckRow key={key} label={label} check={state.checks[key] || { status: "INFO", detail: "n/a" }} />
          ))}
        </section>
      )}
    </div>
  );
}
