/**
 * ArbiCore X — UI v2 · Settings page (Slice 5)
 * Sub-rail: Account · Vault · Execution · Exchanges · Notifications · Documentation · Operational
 */
import { useEffect, useState } from "react";
import { Route, Routes, NavLink, Navigate } from "react-router-dom";
import { toast } from "sonner";
import { v2Api } from "@/v2/lib/api";

const SUB = [
  { key: "account", label: "Account" },
  { key: "network", label: "Network" },
  { key: "scanner", label: "Scanner" },
  { key: "secrets", label: "Secrets" },
  { key: "vault", label: "Vault" },
  { key: "execution", label: "Execution" },
  { key: "exchanges", label: "Exchanges" },
  { key: "telegram", label: "Telegram" },
  { key: "notifications", label: "Notifications" },
  { key: "documentation", label: "Documentation" },
  { key: "operational", label: "Operational" },
  { key: "audit", label: "Audit" },
];

function SubNav() {
  return (
    <nav data-testid="v2-settings-subnav" style={{ display: "flex", flexWrap: "wrap", gap: 4, borderBottom: "1px solid var(--v2-border-subtle)", marginBottom: 16, paddingBottom: 8 }}>
      {SUB.map((s) => (
        <NavLink
          key={s.key}
          to={`/v2/settings/${s.key}`}
          data-testid={`v2-settings-tab-${s.key}`}
          style={({ isActive }) => ({
            padding: "5px 10px",
            fontFamily: "var(--v2-font-mono)",
            fontSize: 11,
            letterSpacing: 1,
            textTransform: "uppercase",
            color: isActive ? "var(--v2-accent-base)" : "var(--v2-text-secondary)",
            borderBottom: isActive ? "1px solid var(--v2-accent-base)" : "1px solid transparent",
            textDecoration: "none",
          })}
        >
          {s.label}
        </NavLink>
      ))}
    </nav>
  );
}

function StateTag({ value, map }) {
  const color = map?.[value] || "var(--v2-text-muted)";
  return (
    <span style={{ padding: "1px 6px", fontFamily: "var(--v2-font-mono)", fontSize: 9, letterSpacing: 1, border: `1px solid ${color}`, color, borderRadius: 2 }}>
      {value || "—"}
    </span>
  );
}

function useAsync(fn, deps = []) {
  const [s, setS] = useState({ loading: true, data: null, error: null });
  const [k, setK] = useState(0);
  useEffect(() => {
    let alive = true;
    setS((p) => ({ ...p, loading: true }));
    fn().then((d) => alive && setS({ loading: false, data: d, error: null }))
        .catch((e) => alive && setS({ loading: false, data: null, error: e }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, k]);
  return [s, () => setK((x) => x + 1)];
}

const EX_STATE = { CONNECTED: "var(--v2-verdict-go)", DEGRADED: "var(--v2-verdict-no-soft)", DISCONNECTED: "var(--v2-verdict-no-hard)" };
const VAULT_KIND = { COLD: "var(--v2-verdict-go)", HOT: "var(--v2-accent-base)", MULTISIG: "var(--v2-regime-active)", EXCHANGE: "var(--v2-text-secondary)" };

const TH = { textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" };
const TD = { padding: "6px 10px" };
const TABLE = { width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 };
const CARD = { border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 };
const LABEL_STYLE = { color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginBottom: 4, display: "block" };
const INPUT_STYLE = { padding: "6px 10px", background: "var(--v2-bg-panel)", border: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-primary)", fontFamily: "var(--v2-font-mono)", fontSize: 12, borderRadius: 2, width: "100%", boxSizing: "border-box" };
const BTN_PRIMARY = { padding: "6px 14px", background: "var(--v2-accent-base)", color: "var(--v2-accent-onSolid)", border: "1px solid var(--v2-accent-base)", fontFamily: "var(--v2-font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: 1.5, borderRadius: 2, cursor: "pointer" };
const BTN_GHOST = { padding: "4px 10px", background: "transparent", border: "1px solid var(--v2-accent-base)", color: "var(--v2-accent-base)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer" };

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <span style={LABEL_STYLE}>{label}</span>
      {children}
    </div>
  );
}

function Toggle({ value, onChange, testid }) {
  return (
    <button
      onClick={() => onChange(!value)}
      data-testid={testid}
      style={{ padding: "4px 12px", background: value ? "var(--v2-accent-base)" : "var(--v2-bg-panel)", color: value ? "var(--v2-accent-onSolid)" : "var(--v2-text-secondary)", border: `1px solid ${value ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`, fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer", fontWeight: 700 }}
    >
      {value ? "ON" : "OFF"}
    </button>
  );
}

/* -------------------- Account -------------------- */
function Account() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.accountGet());
  const [form, setForm] = useState(null);
  useEffect(() => { if (data?.account) setForm({ ...data.account }); }, [data]);
  const save = async () => {
    if (!form) return;
    try {
      await v2Api.accountPatch({
        display_name: form.display_name,
        email: form.email,
        mfa_enabled: form.mfa_enabled,
        session_ttl_min: Number(form.session_ttl_min),
      });
      toast.success("Account saved");
      reload();
    } catch (e) { toast.error("Save failed"); }
  };
  if (loading || !form) return <div className="v2-empty">Loading account…</div>;
  return (
    <section data-testid="v2-settings-account">
      <div className="v2-panel" style={{ maxWidth: 640 }}>
        <div className="v2-panel__title">Operator account</div>
        <Field label="Username">
          <input value={form.username} disabled style={{ ...INPUT_STYLE, opacity: 0.6 }} data-testid="v2-settings-account-username" />
        </Field>
        <Field label="Display name">
          <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-account-display" />
        </Field>
        <Field label="Email">
          <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-account-email" />
        </Field>
        <Field label="Role">
          <span style={{ color: "var(--v2-text-primary)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>{form.role}</span>
        </Field>
        <div style={{ display: "flex", gap: 24, marginBottom: 12 }}>
          <div>
            <span style={LABEL_STYLE}>MFA</span>
            <Toggle value={!!form.mfa_enabled} onChange={(v) => setForm({ ...form, mfa_enabled: v })} testid="v2-settings-account-mfa" />
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Session TTL (minutes)">
              <input type="number" value={form.session_ttl_min} onChange={(e) => setForm({ ...form, session_ttl_min: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-account-ttl" />
            </Field>
          </div>
        </div>
        <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, marginBottom: 12 }}>
          Last login {form.last_login_at?.slice(0, 19)} · Created {form.created_at?.slice(0, 10)}
        </div>
        <button style={BTN_PRIMARY} onClick={save} data-testid="v2-settings-account-save">SAVE</button>
      </div>
    </section>
  );
}

/* -------------------- Secrets (Phase 10.5) -------------------- */
const SECRET_SCOPES = ["evm_sign", "custom", "cex_read", "cex_trade", "cex_withdraw"];
const SECRET_ALGOS = ["eth_privkey", "cex_api_secret", "telegram_bot_token", "generic_bytes", "generic_utf8"];

function Secrets() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.secretsList());
  const [form, setForm] = useState({ plaintext: "", scope: "evm_sign", algorithm: "eth_privkey", label: "" });
  const [rotateId, setRotateId] = useState(null);
  const [rotateText, setRotateText] = useState("");
  const [busy, setBusy] = useState(false);
  const [testResult, setTestResult] = useState({});

  const doAdd = async () => {
    if (!form.plaintext.trim()) { toast.error("Plaintext required"); return; }
    setBusy(true);
    try {
      const r = await v2Api.secretsPut(form);
      if (r.ok) { toast.success(`Secret stored (${r.handle.mask})`); setForm({ ...form, plaintext: "", label: "" }); reload(); }
      else toast.error(r.error || "Add failed");
    } catch (e) { toast.error(`Add failed: ${e.message}`); }
    setBusy(false);
  };
  const doDelete = async (id) => {
    if (!window.confirm(`Delete secret ${id}?`)) return;
    setBusy(true);
    try { await v2Api.secretsDelete(id); toast.success("Deleted"); reload(); }
    catch (e) { toast.error(`Delete failed: ${e.message}`); }
    setBusy(false);
  };
  const doTest = async (id) => {
    try {
      const r = await v2Api.secretsTest(id);
      setTestResult({ ...testResult, [id]: r });
      r.ok ? toast.success("Test passed") : toast.error(`Test failed: ${r.error || "check"}`);
    } catch (e) { toast.error(`Test error: ${e.message}`); }
  };
  const doRotate = async () => {
    if (!rotateText.trim()) { toast.error("New plaintext required"); return; }
    setBusy(true);
    try {
      const r = await v2Api.secretsRotate(rotateId, rotateText);
      if (r.ok) { toast.success(`Rotated → ${r.new_handle.handle_id.slice(0, 12)}…`); setRotateId(null); setRotateText(""); reload(); }
      else toast.error(r.error || "Rotate failed");
    } catch (e) { toast.error(`Rotate failed: ${e.message}`); }
    setBusy(false);
  };

  return (
    <section data-testid="v2-settings-secrets">
      <div className="v2-panel" style={{ marginBottom: 12 }}>
        <div className="v2-panel__title">Add a new secret</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <Field label="Scope">
            <select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} style={INPUT_STYLE} data-testid="v2-secrets-scope">
              {SECRET_SCOPES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Algorithm">
            <select value={form.algorithm} onChange={(e) => setForm({ ...form, algorithm: e.target.value })} style={INPUT_STYLE} data-testid="v2-secrets-algo">
              {SECRET_ALGOS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </Field>
          <Field label="Label (optional)">
            <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="e.g. burner-base-01" style={INPUT_STYLE} data-testid="v2-secrets-label" />
          </Field>
          <Field label={form.algorithm === "eth_privkey" ? "Private key (64 hex chars)" : "Plaintext"}>
            <input type="password" value={form.plaintext} onChange={(e) => setForm({ ...form, plaintext: e.target.value })} placeholder="…" style={INPUT_STYLE} data-testid="v2-secrets-plaintext" />
          </Field>
        </div>
        <div style={{ marginTop: 10 }}>
          <button style={BTN_PRIMARY} onClick={doAdd} disabled={busy} data-testid="v2-secrets-add">STORE SECRET</button>
          <span style={{ marginLeft: 12, color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>
            Fernet-wrapped at rest · never displayed in plaintext
          </span>
        </div>
      </div>

      <div className="v2-panel">
        <div className="v2-panel__title">Registered secrets ({data?.count || 0})</div>
        {loading && <div className="v2-empty">Loading…</div>}
        {!loading && (data?.items || []).length === 0 && <div className="v2-empty">No secrets registered.</div>}
        {!loading && (data?.items || []).length > 0 && (
          <table style={TABLE}>
            <thead>
              <tr>
                <th style={TH}>handle_id</th>
                <th style={TH}>scope</th>
                <th style={TH}>algorithm</th>
                <th style={TH}>label</th>
                <th style={TH}>provider</th>
                <th style={TH}>created</th>
                <th style={TH}>actions</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((h) => (
                <tr key={h.handle_id} data-testid={`v2-secrets-row-${h.handle_id}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                  <td style={{ ...TD, color: "var(--v2-text-muted)", fontSize: 10 }} title={h.handle_id}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <code style={{ background: "#0a0f18", padding: "2px 6px", borderRadius: 2, fontFamily: "var(--v2-font-mono, monospace)" }}>
                        {h.handle_id.slice(0, 20)}…
                      </code>
                      <button
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(h.handle_id);
                            toast.success(`Copied — ${h.handle_id.slice(0, 12)}…`);
                          } catch {
                            // Fallback for non-secure contexts
                            const ta = document.createElement("textarea");
                            ta.value = h.handle_id;
                            document.body.appendChild(ta); ta.select();
                            document.execCommand("copy");
                            document.body.removeChild(ta);
                            toast.success("Copied");
                          }
                        }}
                        title={`Copy full handle_id: ${h.handle_id}`}
                        data-testid={`v2-secrets-copy-${h.handle_id}`}
                        style={{
                          background: "transparent",
                          color: "var(--v2-accent, #ffb224)",
                          border: "1px solid var(--v2-accent, #ffb224)",
                          padding: "2px 8px",
                          fontSize: 9,
                          fontFamily: "var(--v2-font-mono, monospace)",
                          fontWeight: 600,
                          textTransform: "uppercase",
                          letterSpacing: 0.6,
                          cursor: "pointer",
                          borderRadius: 2,
                        }}
                      >
                        COPY
                      </button>
                    </div>
                  </td>
                  <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{h.scope}</td>
                  <td style={{ ...TD }}>{h.algorithm}</td>
                  <td style={{ ...TD }}>{h.label || "—"}</td>
                  <td style={{ ...TD, color: "var(--v2-text-muted)", fontSize: 10 }}>{h.provider}</td>
                  <td style={{ ...TD, color: "var(--v2-text-muted)", fontSize: 10 }}>{(h.created_at || "").slice(0, 19)}</td>
                  <td style={{ ...TD }}>
                    <button style={{ ...BTN_GHOST, padding: "3px 8px", fontSize: 10 }} onClick={() => doTest(h.handle_id)} data-testid={`v2-secrets-test-${h.handle_id}`}>TEST</button>
                    <button style={{ ...BTN_GHOST, padding: "3px 8px", fontSize: 10, marginLeft: 4 }} onClick={() => { setRotateId(h.handle_id); setRotateText(""); }} data-testid={`v2-secrets-rotate-${h.handle_id}`}>ROTATE</button>
                    <button style={{ ...BTN_GHOST, padding: "3px 8px", fontSize: 10, marginLeft: 4, borderColor: "#f87171", color: "#f87171" }} onClick={() => doDelete(h.handle_id)} data-testid={`v2-secrets-delete-${h.handle_id}`}>DEL</button>
                    {testResult[h.handle_id] && (
                      <div style={{ marginTop: 3, color: testResult[h.handle_id].ok ? "#4ade80" : "#f87171", fontSize: 10, fontFamily: "var(--v2-font-mono)" }}>
                        {testResult[h.handle_id].ok ? "✓" : "✗"} {Object.entries(testResult[h.handle_id].checks || {}).map(([k, v]) => `${k}:${v}`).join(" ")}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {rotateId && (
          <div style={{ marginTop: 12, padding: 12, background: "#0a0f18", border: "1px solid var(--v2-accent, #ffb224)", borderRadius: 2 }} data-testid="v2-secrets-rotate-panel">
            <div style={{ color: "var(--v2-accent, #ffb224)", fontSize: 11, marginBottom: 6, fontFamily: "var(--v2-font-mono)" }}>Rotating {rotateId.slice(0, 16)}…</div>
            <input type="password" value={rotateText} onChange={(e) => setRotateText(e.target.value)} placeholder="new plaintext" style={{ ...INPUT_STYLE, marginBottom: 6 }} data-testid="v2-secrets-rotate-input" />
            <button style={BTN_PRIMARY} onClick={doRotate} disabled={busy}>ROTATE</button>
            <button style={{ ...BTN_GHOST, marginLeft: 8 }} onClick={() => { setRotateId(null); setRotateText(""); }}>CANCEL</button>
          </div>
        )}
      </div>
    </section>
  );
}

/* -------------------- Vault -------------------- */
function Vault() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.vaultsGet());
  const [busy, setBusy] = useState(null);
  const doReconcile = async (v) => {
    setBusy(v);
    try { await v2Api.vaultReconcile(v); toast.success(`Reconciled · ${v}`); reload(); }
    catch (e) { toast.error("Reconcile failed"); }
    finally { setBusy(null); }
  };
  return (
    <section data-testid="v2-settings-vault">
      <div style={CARD}>
        <table style={TABLE} data-testid="v2-settings-vault-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Vault", "Kind", "Custody", "Address", "Signers", "State", "Reconciled", "Actions"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {loading && (<tr><td colSpan={8} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).map((v) => (
              <tr key={v.vault} data-testid={`v2-settings-vault-${v.vault}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{v.vault}</td>
                <td style={TD}><StateTag value={v.kind} map={VAULT_KIND} /></td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{v.custody}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{v.address}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{v.signers_required}/{v.signers_total}</td>
                <td style={TD}><StateTag value={v.state} map={{ READY: "var(--v2-verdict-go)", DEGRADED: "var(--v2-verdict-no-soft)" }} /></td>
                <td style={{ ...TD, color: "var(--v2-text-muted)" }}>{v.reconciled_at?.slice(11, 19)}</td>
                <td style={TD}>
                  <button disabled={busy === v.vault} onClick={() => doReconcile(v.vault)} data-testid={`v2-settings-vault-reconcile-${v.vault}`} style={{ ...BTN_GHOST, opacity: busy === v.vault ? 0.5 : 1 }}>RECONCILE</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------- Execution -------------------- */
function Execution() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.executionGet());
  const [form, setForm] = useState(null);
  useEffect(() => { if (data?.config) setForm({ ...data.config }); }, [data]);
  const save = async () => {
    try {
      await v2Api.executionPatch({
        max_position_usd: Number(form.max_position_usd),
        max_daily_notional_usd: Number(form.max_daily_notional_usd),
        slippage_bps: Number(form.slippage_bps),
        min_confidence: Number(form.min_confidence),
        min_safety: Number(form.min_safety),
        freshness_max_s: Number(form.freshness_max_s),
        auto_execute_enabled: !!form.auto_execute_enabled,
        auto_execute_verdict: form.auto_execute_verdict,
      });
      toast.success("Execution config saved");
      reload();
    } catch (e) { toast.error("Save failed"); }
  };
  if (loading || !form) return <div className="v2-empty">Loading execution config…</div>;
  return (
    <section data-testid="v2-settings-execution">
      <div className="v2-panel" style={{ maxWidth: 720 }}>
        <div className="v2-panel__title">Execution policy</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <Field label="Max position (USD)"><input type="number" value={form.max_position_usd} onChange={(e) => setForm({ ...form, max_position_usd: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-execution-maxpos" /></Field>
          <Field label="Max daily notional (USD)"><input type="number" value={form.max_daily_notional_usd} onChange={(e) => setForm({ ...form, max_daily_notional_usd: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-execution-maxdaily" /></Field>
          <Field label="Slippage (bps)"><input type="number" value={form.slippage_bps} onChange={(e) => setForm({ ...form, slippage_bps: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-execution-slippage" /></Field>
          <Field label="Freshness max (s)"><input type="number" value={form.freshness_max_s} onChange={(e) => setForm({ ...form, freshness_max_s: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-execution-freshness" /></Field>
          <Field label="Min confidence"><input type="number" step="0.01" value={form.min_confidence} onChange={(e) => setForm({ ...form, min_confidence: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-execution-minconf" /></Field>
          <Field label="Min safety"><input type="number" step="0.01" value={form.min_safety} onChange={(e) => setForm({ ...form, min_safety: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-execution-minsafety" /></Field>
        </div>
        <div style={{ display: "flex", gap: 24, alignItems: "flex-end", marginTop: 8, marginBottom: 12 }}>
          <div>
            <span style={LABEL_STYLE}>Auto-execute</span>
            <Toggle value={!!form.auto_execute_enabled} onChange={(v) => setForm({ ...form, auto_execute_enabled: v })} testid="v2-settings-execution-auto" />
          </div>
          <div style={{ flex: 1, maxWidth: 200 }}>
            <Field label="Auto-execute verdict"><input value={form.auto_execute_verdict} onChange={(e) => setForm({ ...form, auto_execute_verdict: e.target.value })} style={INPUT_STYLE} data-testid="v2-settings-execution-verdict" /></Field>
          </div>
          <div>
            <span style={LABEL_STYLE}>Kill-switch wired</span>
            <StateTag value={form.kill_switch_wired ? "WIRED" : "OFF"} map={{ WIRED: "var(--v2-verdict-go)", OFF: "var(--v2-verdict-no-hard)" }} />
          </div>
        </div>
        <button style={BTN_PRIMARY} onClick={save} data-testid="v2-settings-execution-save">SAVE</button>
      </div>
    </section>
  );
}

/* -------------------- Exchanges -------------------- */
function Exchanges() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.exchangesGet());
  const [busy, setBusy] = useState(null);
  const doTest = async (k) => {
    setBusy(k);
    try {
      const res = await v2Api.exchangeTest(k);
      res.ok ? toast.success(`${k}: ${res.state} · ${res.latency_ms}ms`) : toast.error(`${k}: ${res.state}`);
      reload();
    } catch (e) { toast.error("Test failed"); }
    finally { setBusy(null); }
  };
  return (
    <section data-testid="v2-settings-exchanges">
      <div style={CARD}>
        <table style={TABLE} data-testid="v2-settings-exchanges-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Exchange", "Kind", "Role", "API key", "Read-only", "State", "Last tested", "Actions"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {loading && (<tr><td colSpan={8} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).map((x) => (
              <tr key={x.key} data-testid={`v2-settings-exchange-${x.key}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{x.label}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{x.kind}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{x.role}</td>
                <td style={{ ...TD, color: "var(--v2-text-muted)" }}>{x.api_key_masked}</td>
                <td style={{ ...TD, color: x.read_only ? "var(--v2-accent-base)" : "var(--v2-text-secondary)" }}>{x.read_only ? "YES" : "NO"}</td>
                <td style={TD}><StateTag value={x.state} map={EX_STATE} /></td>
                <td style={{ ...TD, color: "var(--v2-text-muted)" }}>{x.last_tested_at?.slice(11, 19)}</td>
                <td style={TD}><button disabled={busy === x.key} onClick={() => doTest(x.key)} data-testid={`v2-settings-exchange-test-${x.key}`} style={{ ...BTN_GHOST, opacity: busy === x.key ? 0.5 : 1 }}>TEST</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------- Notifications -------------------- */
function Notifications() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.notificationsGet());
  const [form, setForm] = useState(null);
  useEffect(() => { if (data?.config) setForm(JSON.parse(JSON.stringify(data.config))); }, [data]);
  const save = async () => {
    try {
      await v2Api.notificationsPatch({
        telegram_enabled: !!form.telegram_enabled,
        telegram_chat: form.telegram_chat,
        email_enabled: !!form.email_enabled,
        webhook_enabled: !!form.webhook_enabled,
        webhook_url: form.webhook_url,
        severities: form.severities,
        events: form.events,
      });
      toast.success("Notifications saved");
      reload();
    } catch (e) { toast.error("Save failed"); }
  };
  if (loading || !form) return <div className="v2-empty">Loading notifications…</div>;
  return (
    <section data-testid="v2-settings-notifications">
      <div className="v2-panel" style={{ maxWidth: 720 }}>
        <div className="v2-panel__title">Notification channels</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={LABEL_STYLE}>Telegram</span>
              <Toggle value={!!form.telegram_enabled} onChange={(v) => setForm({ ...form, telegram_enabled: v })} testid="v2-settings-notif-telegram" />
            </div>
            <input value={form.telegram_chat} onChange={(e) => setForm({ ...form, telegram_chat: e.target.value })} placeholder="#ops" style={INPUT_STYLE} data-testid="v2-settings-notif-telegram-chat" />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={LABEL_STYLE}>Email</span>
              <Toggle value={!!form.email_enabled} onChange={(v) => setForm({ ...form, email_enabled: v })} testid="v2-settings-notif-email" />
            </div>
            <input value={(form.email_to || []).join(", ")} readOnly style={{ ...INPUT_STYLE, opacity: 0.7 }} />
          </div>
          <div style={{ gridColumn: "span 2" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={LABEL_STYLE}>Webhook</span>
              <Toggle value={!!form.webhook_enabled} onChange={(v) => setForm({ ...form, webhook_enabled: v })} testid="v2-settings-notif-webhook" />
            </div>
            <input value={form.webhook_url} onChange={(e) => setForm({ ...form, webhook_url: e.target.value })} placeholder="https://…" style={INPUT_STYLE} data-testid="v2-settings-notif-webhook-url" />
          </div>
        </div>
        <div className="v2-panel__title" style={{ marginTop: 16 }}>Severities</div>
        <div style={{ display: "flex", gap: 12 }}>
          {["info", "warn", "error"].map((s) => (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{s.toUpperCase()}</span>
              <Toggle value={!!form.severities?.[s]} onChange={(v) => setForm({ ...form, severities: { ...form.severities, [s]: v } })} testid={`v2-settings-notif-sev-${s}`} />
            </div>
          ))}
        </div>
        <div className="v2-panel__title" style={{ marginTop: 16 }}>Events</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {Object.keys(form.events || {}).map((e) => (
            <div key={e} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{e}</span>
              <Toggle value={!!form.events[e]} onChange={(v) => setForm({ ...form, events: { ...form.events, [e]: v } })} testid={`v2-settings-notif-evt-${e}`} />
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16 }}>
          <button style={BTN_PRIMARY} onClick={save} data-testid="v2-settings-notif-save">SAVE</button>
        </div>
      </div>
    </section>
  );
}

/* -------------------- Network (Phase 10.1) -------------------- */
const CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon"];

function Network() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.networkGet());
  const [form, setForm] = useState(null);
  const [validation, setValidation] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data?.config) setForm(JSON.parse(JSON.stringify(data.config))); }, [data]);
  const validate = async () => {
    try {
      const r = await v2Api.networkValidate(form);
      setValidation(r);
      if (r.ok) toast.success("Validation passed");
      else toast.error(`Validation failed — ${r.errors.length} error(s)`);
    } catch { toast.error("Validation error"); }
  };
  const saveDraft = async () => {
    setBusy(true);
    try {
      await v2Api.networkDraft(form);
      toast.success("Draft saved");
      reload();
    } catch (e) { toast.error(`Draft failed: ${e.message}`); }
    setBusy(false);
  };
  const apply = async () => {
    if (!window.confirm("Apply network config to LIVE? This immediately drives every downstream endpoint.")) return;
    setBusy(true);
    try {
      const reason = window.prompt("Reason for this change:") || "operator update";
      await v2Api.networkApply({ patch: form, reason });
      toast.success("Applied");
      reload();
    } catch (e) { toast.error(`Apply failed: ${e.message}`); }
    setBusy(false);
  };
  const rollback = async () => {
    if (!window.confirm("Rollback to previous revision?")) return;
    setBusy(true);
    try {
      await v2Api.networkRollback({ reason: "operator rollback" });
      toast.success("Rolled back");
      reload();
    } catch (e) { toast.error(`Rollback failed: ${e.message}`); }
    setBusy(false);
  };
  if (loading || !form) return <div className="v2-empty">Loading network config…</div>;
  return (
    <section data-testid="v2-settings-network">
      <div className="v2-panel" style={{ maxWidth: 900 }}>
        <div className="v2-panel__title">Per-chain RPC endpoints</div>
        {CHAINS.map((c) => (
          <div key={c} style={{ marginBottom: 14, borderBottom: "1px solid var(--v2-border-subtle)", paddingBottom: 12 }} data-testid={`v2-settings-network-chain-${c}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ color: "var(--v2-text-strong)", fontFamily: "var(--v2-font-mono)", fontSize: 13, textTransform: "uppercase", letterSpacing: 1.2 }}>{c}</span>
              <Toggle
                value={!!form.chains_enabled?.[c]}
                onChange={(v) => setForm({ ...form, chains_enabled: { ...form.chains_enabled, [c]: v } })}
                testid={`v2-settings-network-toggle-${c}`}
              />
            </div>
            <Field label="RPC URLs (comma-separated; primary first)">
              <input
                data-testid={`v2-settings-network-rpc-${c}`}
                value={(form.rpc_urls?.[c] || []).join(", ")}
                onChange={(e) => {
                  const urls = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
                  setForm({ ...form, rpc_urls: { ...form.rpc_urls, [c]: urls } });
                }}
                placeholder={c === "base" ? "https://mainnet.base.org" : "https://…"}
                style={INPUT_STYLE}
              />
            </Field>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <Field label="Executor address">
                <input
                  data-testid={`v2-settings-network-exec-${c}`}
                  value={form.executor_addresses?.[c] || ""}
                  onChange={(e) => setForm({ ...form, executor_addresses: { ...form.executor_addresses, [c]: e.target.value.trim() } })}
                  placeholder="0x…" style={INPUT_STYLE}
                />
              </Field>
              <Field label="MEV relay URL">
                <input
                  value={form.mev_relay_urls?.[c] || ""}
                  onChange={(e) => setForm({ ...form, mev_relay_urls: { ...form.mev_relay_urls, [c]: e.target.value.trim() } })}
                  placeholder="https://…" style={INPUT_STYLE}
                />
              </Field>
              <Field label="Gas price (gwei)">
                <input type="number" step="0.001"
                  value={form.gas_settings?.[c]?.gas_price_gwei ?? ""}
                  onChange={(e) => setForm({ ...form, gas_settings: { ...form.gas_settings, [c]: { ...form.gas_settings[c], gas_price_gwei: e.target.value === "" ? null : parseFloat(e.target.value) } } })}
                  style={INPUT_STYLE} />
              </Field>
              <Field label="Native price (USD)">
                <input type="number" step="0.01"
                  value={form.native_price_usd?.[c] ?? ""}
                  onChange={(e) => setForm({ ...form, native_price_usd: { ...form.native_price_usd, [c]: e.target.value === "" ? null : parseFloat(e.target.value) } })}
                  style={INPUT_STYLE} />
              </Field>
            </div>
          </div>
        ))}
        {validation && (
          <div data-testid="v2-settings-network-validation" style={{ padding: "8px 12px", marginBottom: 10, background: validation.ok ? "#022c22" : "#3a0a0a", border: `1px solid ${validation.ok ? "#065f46" : "#7f1d1d"}`, color: validation.ok ? "#4ade80" : "#fca5a5", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
            {validation.ok ? "✓ VALID" : `✗ ${validation.errors.length} ERROR(S)`}
            {validation.errors.map((e, i) => (<div key={i}>· {e}</div>))}
            {validation.warnings.map((w, i) => (<div key={i} style={{ color: "#fbbf24" }}>! {w}</div>))}
          </div>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <button style={BTN_GHOST} onClick={validate} disabled={busy} data-testid="v2-settings-network-validate">VALIDATE</button>
          <button style={BTN_GHOST} onClick={saveDraft} disabled={busy} data-testid="v2-settings-network-draft">SAVE DRAFT</button>
          <button style={BTN_PRIMARY} onClick={apply} disabled={busy} data-testid="v2-settings-network-apply">APPLY</button>
          <button style={{ ...BTN_GHOST, borderColor: "#f87171", color: "#f87171" }} onClick={rollback} disabled={busy} data-testid="v2-settings-network-rollback">ROLLBACK</button>
        </div>
        {data?.draft && (
          <div style={{ marginTop: 12, padding: 8, background: "#3d2500", border: "1px solid #78350f", color: "#fbbf24", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
            Pending draft (not applied). Click APPLY to promote or reload to discard.
          </div>
        )}
      </div>
    </section>
  );
}

/* -------------------- Scanner (Phase 10.4 — multi-family) -------------------- */
function Scanner() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.scannerGet());
  const [selectedFamily, setSelectedFamily] = useState("flash_loan_arb");
  const [globalForm, setGlobalForm] = useState(null);
  const [familyForm, setFamilyForm] = useState(null);
  const [globalValidation, setGlobalValidation] = useState(null);
  const [familyValidation, setFamilyValidation] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tokenInput, setTokenInput] = useState({});

  useEffect(() => { if (data?.global) setGlobalForm(JSON.parse(JSON.stringify(data.global))); }, [data]);
  useEffect(() => {
    if (data?.families?.[selectedFamily]) {
      setFamilyForm(JSON.parse(JSON.stringify(data.families[selectedFamily])));
      setFamilyValidation(null);
    }
  }, [data, selectedFamily]);

  const setGlobalPath = (path, value) => {
    setGlobalForm((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const parts = path.split(".");
      let cur = next;
      for (let i = 0; i < parts.length - 1; i++) {
        if (cur[parts[i]] == null) cur[parts[i]] = {};
        cur = cur[parts[i]];
      }
      cur[parts[parts.length - 1]] = value;
      return next;
    });
  };
  const setFamilyPath = (path, value) => {
    setFamilyForm((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const parts = path.split(".");
      let cur = next;
      for (let i = 0; i < parts.length - 1; i++) {
        if (cur[parts[i]] == null) cur[parts[i]] = {};
        cur = cur[parts[i]];
      }
      cur[parts[parts.length - 1]] = value;
      return next;
    });
  };

  const doGlobalValidate = async () => {
    try {
      const r = await v2Api.scannerGlobalValidate(globalForm);
      setGlobalValidation(r);
      r.ok ? toast.success("Global valid") : toast.error(`${r.errors.length} error(s)`);
    } catch { toast.error("Validation failed"); }
  };
  const doGlobalApply = async () => {
    if (!window.confirm("Apply global scanner config to LIVE?")) return;
    setBusy(true);
    try {
      const reason = window.prompt("Reason:") || "operator update";
      await v2Api.scannerGlobalApply({ patch: globalForm, reason });
      toast.success("Global applied"); reload();
    } catch (e) { toast.error(`Apply failed: ${e.message}`); }
    setBusy(false);
  };
  const doGlobalRollback = async () => {
    if (!window.confirm("Rollback global to previous revision?")) return;
    setBusy(true);
    try { await v2Api.scannerGlobalRollback({ reason: "operator rollback" }); toast.success("Rolled back"); reload(); }
    catch (e) { toast.error(`Rollback failed: ${e.message}`); }
    setBusy(false);
  };
  const doFamilyValidate = async () => {
    try {
      const r = await v2Api.scannerFamilyValidate(selectedFamily, familyForm);
      setFamilyValidation(r);
      r.ok ? toast.success(`${selectedFamily} valid`) : toast.error(`${r.errors.length} error(s)`);
    } catch { toast.error("Validation failed"); }
  };
  const doFamilyApply = async () => {
    if (!window.confirm(`Apply ${selectedFamily} config to LIVE?`)) return;
    setBusy(true);
    try {
      const reason = window.prompt("Reason:") || "operator update";
      await v2Api.scannerFamilyApply(selectedFamily, { patch: familyForm, reason });
      toast.success(`${selectedFamily} applied`); reload();
    } catch (e) { toast.error(`Apply failed: ${e.message}`); }
    setBusy(false);
  };
  const doFamilyRollback = async () => {
    if (!window.confirm(`Rollback ${selectedFamily}?`)) return;
    setBusy(true);
    try { await v2Api.scannerFamilyRollback(selectedFamily, { reason: "operator rollback" }); toast.success("Rolled back"); reload(); }
    catch (e) { toast.error(`Rollback failed: ${e.message}`); }
    setBusy(false);
  };
  const doPause = async () => { await v2Api.scannerPause("operator pause"); toast.success("Paused"); reload(); };
  const doResume = async () => { await v2Api.scannerResume("operator resume"); toast.success("Resumed"); reload(); };
  const doReload = async () => { await v2Api.scannerReload("operator reload"); toast.success("Reloaded"); reload(); };

  if (loading || !globalForm || !familyForm) return <div className="v2-empty">Loading scanner config…</div>;

  const familyIds = data?.family_ids || [];
  const familyLabels = data?.family_labels || {};
  const supportedDex = data?.market_families_supported || [];
  const paused = !!globalForm.paused;
  const enabled = !!globalForm.enabled;
  const chains = ["base", "ethereum", "arbitrum", "optimism", "polygon"];

  return (
    <section data-testid="v2-settings-scanner">
      {/* Runtime bar */}
      <div className="v2-panel" style={{ marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ color: "var(--v2-text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Runtime</span>
          <span data-testid="v2-scanner-state-pill" style={{
            background: paused ? "#3d2500" : (enabled ? "#022c22" : "#3a0a0a"),
            color: paused ? "#fbbf24" : (enabled ? "#4ade80" : "#f87171"),
            border: `1px solid ${paused ? "#78350f" : (enabled ? "#065f46" : "#7f1d1d")}`,
            padding: "3px 12px", fontFamily: "var(--v2-font-mono)", fontSize: 11,
            textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600,
          }}>{paused ? "PAUSED" : (enabled ? "RUNNING" : "DISABLED")}</span>
          {globalForm.runtime?.last_reload_at && (
            <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>
              last_reload: {(globalForm.runtime.last_reload_at || "").slice(0, 19)} · {globalForm.runtime.last_reload_by || "-"}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {paused
            ? <button style={BTN_GHOST} onClick={doResume} data-testid="v2-scanner-resume">RESUME</button>
            : <button style={BTN_GHOST} onClick={doPause} data-testid="v2-scanner-pause">PAUSE</button>}
          <button style={BTN_GHOST} onClick={doReload} data-testid="v2-scanner-reload">RELOAD</button>
        </div>
      </div>

      {/* Global config */}
      <div className="v2-panel" style={{ marginBottom: 12 }}>
        <div className="v2-panel__title">Global (cross-family)</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <span style={LABEL_STYLE}>Scanner enabled</span>
          <Toggle value={enabled} onChange={(v) => setGlobalPath("enabled", v)} testid="v2-scanner-enabled" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
          <Field label="Worker concurrency"><input type="number" min="1" value={globalForm.worker_concurrency} onChange={(e) => setGlobalPath("worker_concurrency", Number(e.target.value))} style={INPUT_STYLE} data-testid="v2-scanner-workers" /></Field>
          <Field label="Max concurrent scans"><input type="number" min="1" value={globalForm.max_concurrent_scans} onChange={(e) => setGlobalPath("max_concurrent_scans", Number(e.target.value))} style={INPUT_STYLE} /></Field>
          <Field label="Cache (s)"><input type="number" min="1" value={globalForm.opportunity_cache_s} onChange={(e) => setGlobalPath("opportunity_cache_s", Number(e.target.value))} style={INPUT_STYLE} /></Field>
          <Field label="Expiry (s)"><input type="number" min="1" value={globalForm.opportunity_expiry_s} onChange={(e) => setGlobalPath("opportunity_expiry_s", Number(e.target.value))} style={INPUT_STYLE} /></Field>
        </div>

        <div style={{ marginTop: 12, marginBottom: 6, color: "var(--v2-text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Chains</div>
        {chains.map((c) => (
          <div key={c} data-testid={`v2-scanner-chain-${c}`}
            style={{ display: "grid", gridTemplateColumns: "80px 60px 1fr 1fr 1fr", gap: 10, alignItems: "center", padding: "4px 0", borderBottom: "1px solid var(--v2-border-subtle)" }}>
            <span style={{ color: "var(--v2-text-primary)", fontFamily: "var(--v2-font-mono)", fontSize: 12, textTransform: "uppercase" }}>{c}</span>
            <Toggle value={!!globalForm.networks?.[c]?.enabled} onChange={(v) => setGlobalPath(`networks.${c}.enabled`, v)} testid={`v2-scanner-chain-toggle-${c}`} />
            <Field label="Priority"><input type="number" min="0" value={globalForm.networks?.[c]?.rpc_priority ?? 0} onChange={(e) => setGlobalPath(`networks.${c}.rpc_priority`, Number(e.target.value))} style={INPUT_STYLE} /></Field>
            <Field label="Max gas (gwei)"><input type="number" step="0.01" min="0" value={globalForm.networks?.[c]?.max_gas_gwei ?? 0} onChange={(e) => setGlobalPath(`networks.${c}.max_gas_gwei`, Number(e.target.value))} style={INPUT_STYLE} /></Field>
            <Field label="Max latency (ms)"><input type="number" min="0" value={globalForm.networks?.[c]?.max_latency_ms ?? 1500} onChange={(e) => setGlobalPath(`networks.${c}.max_latency_ms`, Number(e.target.value))} style={INPUT_STYLE} /></Field>
          </div>
        ))}

        <div style={{ marginTop: 12, marginBottom: 6, color: "var(--v2-text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>DEX / market families</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          {supportedDex.map((f) => (
            <div key={f} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0" }}>
              <span style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>{f}</span>
              <Toggle value={!!globalForm.market_families?.[f]} onChange={(v) => setGlobalPath(`market_families.${f}`, v)} testid={`v2-scanner-mf-${f}`} />
            </div>
          ))}
        </div>

        <div style={{ marginTop: 12, marginBottom: 6, color: "var(--v2-text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>Token / pair families</div>
        {["stables", "eth_pairs", "wbtc_pairs", "blue_chips", "custom_whitelist", "blacklist"].map((k) => {
          const arr = globalForm.token_families?.[k] || [];
          const buf = tokenInput[k] ?? "";
          return (
            <div key={k} data-testid={`v2-scanner-tf-${k}`} style={{ marginBottom: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <span style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>{k}</span>
                <span style={{ color: "var(--v2-text-muted)", fontSize: 10 }}>{arr.length}</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 4 }}>
                {arr.map((t) => (
                  <span key={t} style={{ padding: "2px 8px", background: "#0a0f18", border: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-primary)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>
                    {t}
                    <button onClick={() => setGlobalPath(`token_families.${k}`, arr.filter((x) => x !== t))} style={{ marginLeft: 6, background: "transparent", border: "none", color: "#f87171", cursor: "pointer", fontSize: 10 }}>×</button>
                  </span>
                ))}
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <input value={buf} onChange={(e) => setTokenInput({ ...tokenInput, [k]: e.target.value })} placeholder="TOKEN" style={{ ...INPUT_STYLE, width: 160, textTransform: "uppercase" }} />
                <button style={BTN_GHOST} onClick={() => {
                  const t = buf.trim().toUpperCase();
                  if (t && !arr.includes(t)) setGlobalPath(`token_families.${k}`, [...arr, t]);
                  setTokenInput({ ...tokenInput, [k]: "" });
                }}>+ ADD</button>
              </div>
            </div>
          );
        })}

        {globalValidation && (
          <div data-testid="v2-scanner-global-validation" style={{ padding: "8px 12px", marginTop: 10, background: globalValidation.ok ? "#022c22" : "#3a0a0a", border: `1px solid ${globalValidation.ok ? "#065f46" : "#7f1d1d"}`, color: globalValidation.ok ? "#4ade80" : "#fca5a5", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
            {globalValidation.ok ? "✓ VALID" : `✗ ${globalValidation.errors.length} ERROR(S)`}
            {globalValidation.errors.map((e, i) => (<div key={i}>· {e}</div>))}
            {globalValidation.warnings.map((w, i) => (<div key={i} style={{ color: "#fbbf24" }}>! {w}</div>))}
          </div>
        )}
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <button style={BTN_GHOST} onClick={doGlobalValidate} disabled={busy} data-testid="v2-scanner-global-validate">VALIDATE</button>
          <button style={BTN_PRIMARY} onClick={doGlobalApply} disabled={busy} data-testid="v2-scanner-global-apply">APPLY GLOBAL</button>
          <button style={{ ...BTN_GHOST, borderColor: "#f87171", color: "#f87171" }} onClick={doGlobalRollback} disabled={busy} data-testid="v2-scanner-global-rollback">ROLLBACK GLOBAL</button>
        </div>
      </div>

      {/* Family selector */}
      <div className="v2-panel" style={{ marginBottom: 12 }}>
        <div className="v2-panel__title">Scanner families ({familyIds.length})</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {familyIds.map((fid) => {
            const fCfg = data?.families?.[fid] || {};
            const active = fid === selectedFamily;
            return (
              <button key={fid} data-testid={`v2-scanner-family-tab-${fid}`}
                onClick={() => setSelectedFamily(fid)}
                style={{
                  padding: "6px 14px",
                  background: active ? "var(--v2-accent, #ffb224)" : "#0a0f18",
                  color: active ? "#0b0f14" : "var(--v2-text-primary)",
                  border: `1px solid ${active ? "var(--v2-accent, #ffb224)" : "var(--v2-border-subtle)"}`,
                  fontFamily: "var(--v2-font-mono)",
                  fontSize: 11, fontWeight: active ? 600 : 400,
                  cursor: "pointer", textTransform: "uppercase", letterSpacing: 0.6,
                  borderRadius: 2,
                }}>
                {familyLabels[fid] || fid}
                <span style={{ marginLeft: 8, opacity: 0.7, fontSize: 9 }}>
                  {fCfg.enabled ? "●" : "○"}
                </span>
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10, padding: "8px 12px", background: "#0a0f18", border: "1px solid var(--v2-border-subtle)" }}>
          <span style={LABEL_STYLE}>{familyLabels[selectedFamily] || selectedFamily} enabled</span>
          <Toggle value={!!familyForm.enabled} onChange={(v) => setFamilyPath("enabled", v)} testid={`v2-scanner-family-${selectedFamily}-enabled`} />
          {familyForm.interval_s !== undefined && (
            <span style={{ marginLeft: 12, color: "var(--v2-text-muted)", fontSize: 11 }}>
              interval_s:
              <input type="number" min="1" value={familyForm.interval_s} onChange={(e) => setFamilyPath("interval_s", Number(e.target.value))}
                style={{ ...INPUT_STYLE, width: 80, marginLeft: 6 }} />
            </span>
          )}
          {familyForm.verifier_concurrency !== undefined && (
            <span style={{ color: "var(--v2-text-muted)", fontSize: 11 }}>
              verifier_concurrency:
              <input type="number" min="1" value={familyForm.verifier_concurrency} onChange={(e) => setFamilyPath("verifier_concurrency", Number(e.target.value))}
                style={{ ...INPUT_STYLE, width: 60, marginLeft: 6 }} />
            </span>
          )}
        </div>

        {/* Family-specific detail — flash_loan providers panel */}
        {selectedFamily === "flash_loan_arb" && familyForm.providers && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ color: "var(--v2-text-muted)", fontSize: 11, textTransform: "uppercase", marginBottom: 6 }}>Flash Loan providers</div>
            {Object.keys(familyForm.providers).map((p) => (
              <div key={p} data-testid={`v2-scanner-fl-provider-${p}`} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <span style={{ color: "var(--v2-text-primary)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>{p} · fee_bps {familyForm.providers[p].fee_bps ?? "—"}</span>
                <Toggle value={!!familyForm.providers[p].enabled} onChange={(v) => setFamilyPath(`providers.${p}.enabled`, v)} testid={`v2-scanner-fl-provider-toggle-${p}`} />
              </div>
            ))}
          </div>
        )}

        {/* CEX arb tier pairs */}
        {(selectedFamily === "cex_arb" || selectedFamily === "funding_arb") && Array.isArray(familyForm.tier_a_pairs) && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ color: "var(--v2-text-muted)", fontSize: 11, textTransform: "uppercase", marginBottom: 6 }}>Tier A pairs</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {familyForm.tier_a_pairs.map((p) => (
                <span key={p} style={{ padding: "2px 8px", background: "#0a0f18", border: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-primary)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>{p}</span>
              ))}
            </div>
          </div>
        )}

        {/* Gate thresholds (all families) */}
        {familyForm.gate_thresholds && (
          <div style={{ marginBottom: 10 }}>
            <div style={{ color: "var(--v2-text-muted)", fontSize: 11, textTransform: "uppercase", marginBottom: 6 }}>Gate thresholds</div>
            {Object.entries(familyForm.gate_thresholds).map(([pair, gates]) => (
              <div key={pair} data-testid={`v2-scanner-gate-${pair}`} style={{ marginBottom: 6 }}>
                <div style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11, marginBottom: 3 }}>{pair}</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                  {Object.entries(gates).map(([gk, gv]) => (
                    typeof gv === "number" && (
                      <Field key={gk} label={gk}>
                        <input type="number" step="0.01" value={gv} onChange={(e) => setFamilyPath(`gate_thresholds.${pair}.${gk}`, Number(e.target.value))} style={INPUT_STYLE} />
                      </Field>
                    )
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {familyValidation && (
          <div data-testid="v2-scanner-family-validation" style={{ padding: "8px 12px", marginTop: 10, background: familyValidation.ok ? "#022c22" : "#3a0a0a", border: `1px solid ${familyValidation.ok ? "#065f46" : "#7f1d1d"}`, color: familyValidation.ok ? "#4ade80" : "#fca5a5", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
            {familyValidation.ok ? "✓ VALID" : `✗ ${familyValidation.errors.length} ERROR(S)`}
            {familyValidation.errors.map((e, i) => (<div key={i}>· {e}</div>))}
            {familyValidation.warnings.map((w, i) => (<div key={i} style={{ color: "#fbbf24" }}>! {w}</div>))}
          </div>
        )}
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <button style={BTN_GHOST} onClick={doFamilyValidate} disabled={busy} data-testid="v2-scanner-family-validate">VALIDATE</button>
          <button style={BTN_PRIMARY} onClick={doFamilyApply} disabled={busy} data-testid="v2-scanner-family-apply">APPLY {selectedFamily.toUpperCase()}</button>
          <button style={{ ...BTN_GHOST, borderColor: "#f87171", color: "#f87171" }} onClick={doFamilyRollback} disabled={busy} data-testid="v2-scanner-family-rollback">ROLLBACK</button>
        </div>
      </div>
    </section>
  );
}

/* -------------------- Telegram (Phase 10.3) -------------------- */
function Telegram() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.telegramGet());
  const [{ data: logData }, reloadLog] = useAsync(() => v2Api.telegramLog(50));
  const [form, setForm] = useState(null);
  const [newToken, setNewToken] = useState("");
  useEffect(() => { if (data?.config) setForm(JSON.parse(JSON.stringify(data.config))); }, [data]);
  const save = async () => {
    try {
      const body = {
        enabled: !!form.enabled,
        chat_id: form.chat_id,
        rules: form.rules,
      };
      if (newToken.trim()) body.bot_token = newToken.trim();
      await v2Api.telegramPut(body);
      toast.success("Telegram config saved");
      setNewToken("");
      reload();
    } catch (e) { toast.error(`Save failed: ${e.message}`); }
  };
  const test = async () => {
    try {
      const r = await v2Api.telegramTest();
      if (r.sent) toast.success("Test message sent");
      else toast.error(`Test failed: ${r.reason}`);
      reloadLog();
    } catch (e) { toast.error(`Test error: ${e.message}`); }
  };
  if (loading || !form) return <div className="v2-empty">Loading Telegram config…</div>;
  return (
    <section data-testid="v2-settings-telegram">
      <div className="v2-panel" style={{ maxWidth: 720, marginBottom: 12 }}>
        <div className="v2-panel__title">Bot configuration</div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
          <span style={LABEL_STYLE}>Enabled</span>
          <Toggle value={!!form.enabled} onChange={(v) => setForm({ ...form, enabled: v })} testid="v2-settings-telegram-enabled" />
          <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>
            {form.token_set ? `Token: ${form.token_mask}` : "No token set"}
          </span>
        </div>
        <Field label="Chat ID (e.g. -1001234567890)">
          <input data-testid="v2-settings-telegram-chat" value={form.chat_id} onChange={(e) => setForm({ ...form, chat_id: e.target.value })} placeholder="chat id" style={INPUT_STYLE} />
        </Field>
        <Field label="Bot token (leave blank to keep current)">
          <input data-testid="v2-settings-telegram-token" type="password" value={newToken} onChange={(e) => setNewToken(e.target.value)} placeholder="123456:AAxxxxxxxxxxxxxx" style={INPUT_STYLE} />
        </Field>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button style={BTN_PRIMARY} onClick={save} data-testid="v2-settings-telegram-save">SAVE</button>
          <button style={BTN_GHOST} onClick={test} data-testid="v2-settings-telegram-test">SEND TEST</button>
        </div>
      </div>

      <div className="v2-panel" style={{ maxWidth: 720, marginBottom: 12 }}>
        <div className="v2-panel__title">Alert rules</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          {Object.entries(form.rules || {})
            .filter(([k]) => typeof form.rules[k] === "boolean")
            .map(([k, v]) => (
              <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "3px 0" }}>
                <span style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{k}</span>
                <Toggle value={!!v} onChange={(nv) => setForm({ ...form, rules: { ...form.rules, [k]: nv } })} testid={`v2-settings-telegram-rule-${k}`} />
              </div>
            ))}
        </div>
        <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <Field label="Cooldown (seconds)">
            <input type="number" min="0" value={form.rules?.cooldown_s ?? 300}
              onChange={(e) => setForm({ ...form, rules: { ...form.rules, cooldown_s: parseInt(e.target.value || "0", 10) } })}
              style={INPUT_STYLE} data-testid="v2-settings-telegram-cooldown" />
          </Field>
          <Field label="Minimum net spread (%)">
            <input type="number" step="0.1" min="0" value={form.rules?.min_net_spread_pct ?? 2.0}
              onChange={(e) => setForm({ ...form, rules: { ...form.rules, min_net_spread_pct: parseFloat(e.target.value || "0") } })}
              style={INPUT_STYLE} />
          </Field>
        </div>
      </div>

      <div className="v2-panel" style={{ maxWidth: 720 }} data-testid="v2-settings-telegram-log">
        <div className="v2-panel__title">Alert history</div>
        {(!logData?.items || logData.items.length === 0)
          ? <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>No alerts sent yet.</div>
          : (
            <table style={TABLE}>
              <thead>
                <tr>
                  <th style={TH}>at</th><th style={TH}>kind</th>
                  <th style={TH}>sent</th><th style={TH}>text</th>
                </tr>
              </thead>
              <tbody>
                {logData.items.slice(0, 15).map((r, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                    <td style={{ ...TD, color: "var(--v2-text-muted)", fontSize: 10 }}>{(r.at || "").slice(0, 19)}</td>
                    <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{r.kind}</td>
                    <td style={{ ...TD }}>{r.sent ? <span style={{ color: "#4ade80" }}>✓</span> : <span style={{ color: "#f87171" }}>✗</span>}</td>
                    <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{(r.text || "").slice(0, 60)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </div>
    </section>
  );
}

/* -------------------- Audit / History (Phase 10.2) -------------------- */
function Audit() {
  const [kind, setKind] = useState("");
  const [{ loading, data }] = useAsync(() => v2Api.configHistory(kind || undefined, 100), [kind]);
  return (
    <section data-testid="v2-settings-audit">
      <div className="v2-panel">
        <div className="v2-panel__title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Configuration change audit</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ ...INPUT_STYLE, width: "auto" }} data-testid="v2-settings-audit-filter">
            <option value="">All kinds</option>
            <option value="network">network</option>
            <option value="operator_account">operator_account</option>
            <option value="execution_settings">execution_settings</option>
            <option value="operational_flags">operational_flags</option>
            <option value="telegram_alerts">telegram_alerts</option>
          </select>
        </div>
        {loading && <div className="v2-empty">Loading…</div>}
        {!loading && (
          <table style={TABLE}>
            <thead>
              <tr>
                <th style={TH}>at</th>
                <th style={TH}>kind</th>
                <th style={TH}>action</th>
                <th style={TH}>actor</th>
                <th style={TH}>reason</th>
                <th style={TH}>revision</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((r, i) => (
                <tr key={i} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                  <td style={{ ...TD, color: "var(--v2-text-muted)", fontSize: 10 }}>{(r.at || "").slice(0, 19)}</td>
                  <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{r.kind}</td>
                  <td style={{ ...TD, color: r.action === "rollback" ? "#fbbf24" : "var(--v2-text-primary)" }}>{r.action}</td>
                  <td style={{ ...TD }}>{r.actor}</td>
                  <td style={{ ...TD, color: "var(--v2-text-muted)" }}>{(r.reason || "").slice(0, 60)}</td>
                  <td style={{ ...TD, color: "var(--v2-text-muted)", fontSize: 10 }}>{(r.revision_id || "").slice(0, 12)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

/* -------------------- Documentation -------------------- */
function Documentation() {
  const [{ loading, data }] = useAsync(() => v2Api.documentationGet());
  const groups = (data?.items || []).reduce((acc, x) => { (acc[x.category] = acc[x.category] || []).push(x); return acc; }, {});
  return (
    <section data-testid="v2-settings-documentation">
      {loading && <div className="v2-empty">Loading docs…</div>}
      {!loading && Object.entries(groups).map(([cat, items]) => (
        <div key={cat} className="v2-panel" style={{ marginBottom: 12 }} data-testid={`v2-settings-doc-group-${cat}`}>
          <div className="v2-panel__title" style={{ textTransform: "uppercase" }}>{cat}</div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((d) => (
              <li key={d.path} data-testid={`v2-settings-doc-${d.path}`} style={{ padding: "6px 0", borderBottom: "1px solid var(--v2-border-subtle)", display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--v2-text-strong)", fontSize: 13 }}>{d.title}</span>
                <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{d.path}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

/* -------------------- Operational -------------------- */
function Operational() {
  const [{ loading, data }, reload] = useAsync(() => v2Api.operationalGet());
  const [form, setForm] = useState(null);
  useEffect(() => { if (data?.config) setForm(JSON.parse(JSON.stringify(data.config))); }, [data]);
  const save = async () => {
    try {
      await v2Api.operationalPatch({
        maintenance_mode: !!form.maintenance_mode,
        trading_paused: !!form.trading_paused,
        read_only: !!form.read_only,
        dev_mode: !!form.dev_mode,
        verbose_logging: !!form.verbose_logging,
        feature_flags: form.feature_flags,
      });
      toast.success("Operational config saved");
      reload();
    } catch (e) { toast.error("Save failed"); }
  };
  if (loading || !form) return <div className="v2-empty">Loading operational config…</div>;
  const MODES = [
    ["maintenance_mode", "Maintenance mode"],
    ["trading_paused", "Trading paused"],
    ["read_only", "Read-only mode"],
    ["dev_mode", "Developer mode"],
    ["verbose_logging", "Verbose logging"],
  ];
  return (
    <section data-testid="v2-settings-operational">
      <div className="v2-panel" style={{ maxWidth: 720 }}>
        <div className="v2-panel__title">Modes</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
          {MODES.map(([k, label]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0" }}>
              <span style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{label}</span>
              <Toggle value={!!form[k]} onChange={(v) => setForm({ ...form, [k]: v })} testid={`v2-settings-op-${k}`} />
            </div>
          ))}
        </div>
        <div className="v2-panel__title" style={{ marginTop: 12 }}>Feature flags</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
          {Object.keys(form.feature_flags || {}).map((k) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0" }}>
              <span style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{k}</span>
              <Toggle value={!!form.feature_flags[k]} onChange={(v) => setForm({ ...form, feature_flags: { ...form.feature_flags, [k]: v } })} testid={`v2-settings-op-flag-${k}`} />
            </div>
          ))}
        </div>
        <button style={BTN_PRIMARY} onClick={save} data-testid="v2-settings-op-save">SAVE</button>
      </div>
    </section>
  );
}

export default function SettingsPage() {
  return (
    <section data-testid="v2-settings">
      <h1 className="v2-page__title">Settings</h1>
      <p className="v2-page__lede">Account · Vault · Execution · Exchanges · Notifications · Documentation · Operational.</p>
      <SubNav />
      <Routes>
        <Route index element={<Navigate to="account" replace />} />
        <Route path="account" element={<Account />} />
        <Route path="network" element={<Network />} />
        <Route path="scanner" element={<Scanner />} />
        <Route path="secrets" element={<Secrets />} />
        <Route path="vault" element={<Vault />} />
        <Route path="execution" element={<Execution />} />
        <Route path="exchanges" element={<Exchanges />} />
        <Route path="telegram" element={<Telegram />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="documentation" element={<Documentation />} />
        <Route path="operational" element={<Operational />} />
        <Route path="audit" element={<Audit />} />
      </Routes>
    </section>
  );
}
