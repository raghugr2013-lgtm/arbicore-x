import { API_BASE } from "@/lib/apiBase";
/**
 * ArbiCore X — UI v2 · Flash Loan Operator page (Phase 7B)
 *
 * A single page that walks the operator through the full LIMITED_LIVE
 * flash-loan validation workflow using only the Wave 6A/6B/6C/6D/6E/7A/7C
 * endpoints that are already live.
 *
 * Every action is a single POST to a mounted API.  No hidden state.
 */
import { useEffect, useMemo, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = API_BASE;

const CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon"];
const ROLES = ["gas", "treasury", "watch_only"];

const cx = (...c) => c.filter(Boolean).join(" ");

const Card = ({ title, subtitle, children, testId }) => (
  <section
    data-testid={testId}
    style={{
      background: "var(--v2-bg-surface, #0f141c)",
      border: "1px solid var(--v2-border-subtle, #1c2733)",
      padding: 20,
      marginBottom: 16,
      borderRadius: 2,
    }}
  >
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
      <h2 style={{ color: "var(--v2-text-primary, #e2e8f0)", fontSize: 15, fontWeight: 600, margin: 0, textTransform: "uppercase", letterSpacing: 1.5 }}>{title}</h2>
      {subtitle && <span style={{ color: "var(--v2-text-muted, #64748b)", fontSize: 12 }}>{subtitle}</span>}
    </div>
    {children}
  </section>
);

const Btn = ({ children, onClick, danger, subtle, disabled, testId, style }) => (
  <button
    data-testid={testId}
    onClick={onClick}
    disabled={disabled}
    style={{
      background: danger ? "#8b1a1a" : subtle ? "transparent" : "var(--v2-accent, #ffb224)",
      color: danger ? "#fff" : subtle ? "var(--v2-text-primary, #e2e8f0)" : "#0b0f14",
      border: subtle ? "1px solid #2a3441" : "none",
      padding: "8px 14px",
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.5 : 1,
      fontFamily: "var(--v2-font-mono, monospace)",
      fontSize: 12,
      fontWeight: 600,
      textTransform: "uppercase",
      letterSpacing: 0.6,
      borderRadius: 2,
      ...(style || {}),
    }}
  >{children}</button>
);

const Field = ({ label, value, onChange, placeholder, type = "text", testId, mono = true }) => (
  <label style={{ display: "block", marginBottom: 10 }}>
    <span style={{ fontSize: 11, color: "var(--v2-text-muted, #64748b)", textTransform: "uppercase", letterSpacing: 0.8, display: "block", marginBottom: 4 }}>{label}</span>
    <input
      data-testid={testId}
      type={type}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: "100%", padding: "7px 10px",
        background: "#0a0f18", border: "1px solid #1c2733",
        color: "#e2e8f0", fontFamily: mono ? "var(--v2-font-mono, monospace)" : "inherit",
        fontSize: 12, borderRadius: 2, outline: "none",
      }}
    />
  </label>
);

const Row = ({ children, gap = 8, wrap = false }) => (
  <div style={{ display: "flex", gap, alignItems: "center", flexWrap: wrap ? "wrap" : "nowrap" }}>{children}</div>
);

const Chip = ({ label, tone = "info" }) => {
  const tones = {
    info: { bg: "#1e293b", fg: "#93c5fd" },
    ok: { bg: "#022c22", fg: "#4ade80" },
    warn: { bg: "#3d2500", fg: "#fbbf24" },
    crit: { bg: "#3a0a0a", fg: "#f87171" },
    muted: { bg: "#0f141c", fg: "#64748b" },
  };
  const t = tones[tone] || tones.info;
  return <span style={{ background: t.bg, color: t.fg, fontFamily: "var(--v2-font-mono, monospace)", fontSize: 10, padding: "2px 8px", borderRadius: 2, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</span>;
};

const Json = ({ value, maxHeight = 240 }) => (
  <pre style={{
    background: "#050810", border: "1px solid #1c2733",
    color: "#94a3b8", fontFamily: "var(--v2-font-mono, monospace)",
    fontSize: 11, padding: 12, margin: 0, borderRadius: 2,
    maxHeight, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-all",
  }}>{JSON.stringify(value, null, 2)}</pre>
);

// ---------------------------------------------------------------------------
// Global always-visible Kill Switch banner
// ---------------------------------------------------------------------------

function KillSwitchBanner({ state, onEngage, onDisengage }) {
  const engaged = state?.engaged;
  return (
    <div data-testid="flops-kill-banner" style={{
      background: engaged ? "#3a0a0a" : "#022c22",
      border: `1px solid ${engaged ? "#7f1d1d" : "#065f46"}`,
      padding: "10px 16px",
      marginBottom: 16,
      display: "flex", justifyContent: "space-between", alignItems: "center",
    }}>
      <div>
        <strong style={{ color: engaged ? "#f87171" : "#4ade80", fontFamily: "var(--v2-font-mono, monospace)", fontSize: 12, letterSpacing: 1 }}>
          KILL SWITCH — {engaged ? "ENGAGED" : "DISENGAGED"}
        </strong>
        {engaged && <div style={{ color: "#fca5a5", fontSize: 11, marginTop: 4 }}>Reason: {state?.reason} — actor: {state?.actor}</div>}
      </div>
      {engaged
        ? <Btn testId="flops-kill-disengage" onClick={onDisengage} subtle>Disengage</Btn>
        : <Btn testId="flops-kill-engage" danger onClick={onEngage}>Engage Kill Switch</Btn>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function FlashLoanOperatorPage() {
  // Kill switch
  const [ksState, setKsState] = useState(null);
  const refreshKS = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/arbicore/execution/kill-switch`); setKsState(data.state); } catch { /* noop */ }
  }, []);
  useEffect(() => { refreshKS(); const t = setInterval(refreshKS, 8_000); return () => clearInterval(t); }, [refreshKS]);
  const engageKS = async () => {
    const reason = window.prompt("Reason for engaging the kill switch?");
    if (!reason) return;
    await axios.post(`${API}/arbicore/execution/kill-switch/engage`, { reason, actor: "operator@ui" });
    toast.warning("Kill switch engaged");
    refreshKS();
  };
  const disengageKS = async () => {
    const reason = window.prompt("Reason for disengaging the kill switch?");
    if (!reason) return;
    await axios.post(`${API}/arbicore/execution/kill-switch/disengage`, { reason, actor: "operator@ui" });
    toast.success("Kill switch disengaged");
    refreshKS();
  };

  // Step 1: Wallets
  const [wallets, setWallets] = useState([]);
  const [selectedWalletId, setSelectedWalletId] = useState(null);
  const [newWallet, setNewWallet] = useState({ label: "", chain: "base", execution_role: "gas", address: "", secret_handle_id: "" });
  // Available secrets (populates the dropdown in the wallet form so the
  // operator never has to type or paste a handle_id).
  const [availableSecrets, setAvailableSecrets] = useState([]);
  const refreshWallets = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/arbicore/execution/wallets`); setWallets(data.items || []); }
    catch { setWallets([]); }
  }, []);
  const refreshSecrets = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/arbicore/execution/secrets`);
      // Only surface secrets that can sign EVM transactions.
      const evmSigners = (data.items || []).filter(
        (s) => s.scope === "evm_sign" || s.algorithm === "eth_privkey",
      );
      setAvailableSecrets(evmSigners);
    } catch { setAvailableSecrets([]); }
  }, []);
  useEffect(() => { refreshWallets(); refreshSecrets(); }, [refreshWallets, refreshSecrets]);
  const submitWallet = async () => {
    // Backend requires a caller-supplied wallet_id; auto-generate a stable
    // slug from the label + a short random suffix so the operator never has
    // to think about this.
    const slug = (newWallet.label || "wallet")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 32) || "wallet";
    const suffix = Math.random().toString(36).slice(2, 8);
    const body = {
      ...newWallet,
      wallet_id: `${slug}-${suffix}`,
      // watch_only / treasury wallets MUST NOT carry a secret handle
      secret_handle_id: newWallet.execution_role === "gas" ? newWallet.secret_handle_id : "",
    };
    try {
      const { data } = await axios.post(`${API}/arbicore/execution/wallets`, body);
      const row = data.item || data.wallet;
      if (row) {
        toast.success(`Wallet registered — ${row.wallet_id}`);
        setSelectedWalletId(row.wallet_id);
      } else if (data.error) {
        toast.error(data.error);
        return;
      }
      setNewWallet({ label: "", chain: "base", execution_role: "gas", address: "", secret_handle_id: "" });
      refreshWallets();
    } catch (e) { toast.error(e?.response?.data?.error || e?.message || "Failed"); }
  };

  // Step 2: Secrets — canonical UI lives at /v2/settings/secrets (see card below).

  // Step 3: Wallet health + balance
  const [health, setHealth] = useState(null);
  const [balance, setBalance] = useState(null);
  const refreshHealth = useCallback(async () => {
    if (!selectedWalletId) return;
    try {
      const [b, h] = await Promise.all([
        axios.get(`${API}/arbicore/execution/wallets/${selectedWalletId}/balance`),
        axios.get(`${API}/arbicore/execution/wallets/${selectedWalletId}/health`),
      ]);
      setBalance(b.data.reading);
      setHealth(h.data.report);
    } catch { /* noop */ }
  }, [selectedWalletId]);
  useEffect(() => { refreshHealth(); }, [refreshHealth]);

  // Step 4: Mode ladder
  const [modes, setModes] = useState([]);
  const refreshModes = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/arbicore/execution/mode`); setModes(data.items || []); } catch { /* noop */ }
  }, []);
  useEffect(() => { refreshModes(); }, [refreshModes]);
  const promoteMode = async (strategy, targetMode) => {
    if (!window.confirm(`Promote ${strategy} to ${targetMode}?`)) return;
    try {
      // Backend contract: POST /arbicore/execution/mode/{strategy} expects
      // {"to_mode": "..."} — NOT {"mode": "..."}.  (Fixed 2026-08-01.)
      const { data } = await axios.post(
        `${API}/arbicore/execution/mode/${strategy}`,
        { to_mode: targetMode, actor: "operator@ui", reason: "UI promotion" },
      );
      if (data.error) {
        toast.error(data.error);
        return;
      }
      const newMode = (data.mode && (data.mode.mode || data.mode)) || targetMode;
      toast.success(`${strategy} → ${newMode}`);
      await refreshModes();
    } catch (e) {
      toast.error(e?.response?.data?.error || e?.message || "Failed");
    }
  };

  // Step 5: Continuous discovery
  const [discoveryStatus, setDiscoveryStatus] = useState(null);
  const [opps, setOpps] = useState([]);
  const refreshDiscovery = useCallback(async () => {
    try {
      const [s, o] = await Promise.all([
        axios.get(`${API}/arbicore/execution/discovery/status`),
        axios.get(`${API}/arbicore/execution/opportunities?limit=20`),
      ]);
      setDiscoveryStatus(s.data);
      setOpps(o.data.items || []);
    } catch { /* noop */ }
  }, []);
  useEffect(() => { refreshDiscovery(); const t = setInterval(refreshDiscovery, 15_000); return () => clearInterval(t); }, [refreshDiscovery]);
  const tickDiscovery = async () => {
    try { await axios.post(`${API}/arbicore/execution/discovery/tick`); toast.info("Discovery tick complete"); refreshDiscovery(); }
    catch (e) { toast.error(e?.message || "Failed"); }
  };

  // Step 6: Opportunity → Plan → Certify → Broadcast
  const [selectedOpp, setSelectedOpp] = useState(null);
  const [certReport, setCertReport] = useState(null);
  const [broadcastReceipt, setBroadcastReceipt] = useState(null);
  const [confirmChecked, setConfirmChecked] = useState(false);

  // Phase 10.10.1 · Persist-first flow.
  // The certification endpoint does NOT persist plans — it returns a report
  // whose plan_id has no corresponding row in _EXECUTION_PLANS_REPO.  So we
  // must call /plans/build FIRST (which persists), then /certification/run
  // for the verdict display, and broadcast uses the persisted plan_id from
  // /plans/build.
  const [persistedPlanId, setPersistedPlanId] = useState(null);

  const buildAndCertify = async (body) => {
    // 1) Build & persist the plan
    let builtPlanId = null;
    try {
      const { data: buildResp } = await axios.post(
        `${API}/arbicore/execution/plans/build`, body,
      );
      if (buildResp.error) {
        toast.error(`Build failed: ${buildResp.error}`);
        console.error("plans/build error", buildResp);
        return;
      }
      builtPlanId = buildResp.plan?.plan_id;
      if (!builtPlanId) {
        toast.error("Build returned no plan_id");
        console.error("plans/build unexpected shape", buildResp);
        return;
      }
      // Phase 10.10.5 — the ONLY plan_id the broadcaster will accept.
      console.log(`[10.10.5] built+persisted plan_id: ${builtPlanId}`);
      setPersistedPlanId(builtPlanId);
    } catch (e) {
      toast.error(`Build failed: ${e?.response?.data?.error || e?.message}`);
      return;
    }
    // 2) Run certification for the verdict display
    try {
      const { data: certResp } = await axios.post(
        `${API}/arbicore/execution/certification/run`, body,
      );
      if (certResp.error) toast.error(certResp.error);
      // Merge the persisted plan_id into the report so the broadcast
      // buttons pick it up.
      setCertReport({ ...(certResp.report || {}), plan_id: builtPlanId });
      const verdict = certResp.report?.verdict;
      toast.info(`Plan ${builtPlanId.slice(0, 14)}… · verdict: ${verdict}`);
    } catch (e) {
      toast.error(`Certification failed: ${e?.response?.data?.error || e?.message}`);
    }
  };

  const certifyPlan = async () => {
    if (!selectedOpp) return;
    await buildAndCertify({
      strategy: selectedOpp.strategy,
      chain: selectedOpp.chain,
      borrow_token: selectedOpp.borrow_token,
      borrow_amount_wei: selectedOpp.borrow_amount_wei,
      borrow_amount_usd: selectedOpp.borrow_amount_usd,
      flash_loan_provider: selectedOpp.flash_loan_provider,
      swap_hops: selectedOpp.swap_hops,
      signer_wallet_id: selectedWalletId,
      opportunity_id: selectedOpp.opportunity_id,
      quote_effective_out_wei: selectedOpp.swap_hops?.[selectedOpp.swap_hops.length - 1]?.min_amount_out_wei,
    });
  };

  const broadcastPlan = async () => {
    const planId = persistedPlanId || certReport?.plan_id;
    // Phase 10.10.5 — explicit logging so any ID divergence is visible.
    console.log(`[10.10.5] broadcast — persistedPlanId=${persistedPlanId} certReport.plan_id=${certReport?.plan_id} using=${planId}`);
    if (!planId) { toast.error("No plan built yet"); return; }
    if (!confirmChecked) { toast.error("Check the confirm box first"); return; }
    if (!window.confirm("This will submit a REAL transaction to the RPC endpoint if every safety gate passes. Continue?")) return;
    try {
      const { data } = await axios.post(`${API}/arbicore/execution/plans/${planId}/broadcast`, {
        confirm: true, actor: "operator@ui",
      });
      if (data.error) {
        if (String(data.error).includes("not found")) {
          toast.error(`Plan ${planId.slice(0, 14)}… is not persisted. Click "Run full certification (manual plan)" once more — this rebuilds and re-persists the plan.`);
          setPersistedPlanId(null);
          setCertReport(null);
        } else {
          toast.error(data.error);
        }
        return;
      }
      setBroadcastReceipt(data.receipt);
      if (data.receipt?.broadcast_sent) toast.success(`Broadcast sent — tx ${data.receipt.tx_hash}`);
      else toast.warning(`Broadcast held — ${(data.receipt?.denied_reasons || [])[0] || "gate denied"}`);
    } catch (e) { toast.error(e?.response?.data?.error || e?.message || "Failed"); }
  };

  const previewBroadcast = async () => {
    const planId = persistedPlanId || certReport?.plan_id;
    if (!planId) { toast.error("No plan built yet"); return; }
    try {
      const { data } = await axios.post(`${API}/arbicore/execution/plans/${planId}/broadcast`, {
        confirm: false, actor: "operator@ui",
      });
      if (data.error) { toast.error(data.error); return; }
      setBroadcastReceipt(data.receipt);
      toast.info("Broadcast preview (dry, held at confirm gate)");
    } catch (e) { toast.error(e?.response?.data?.error || e?.message || "Failed"); }
  };

  const modeMap = useMemo(() => {
    const m = {};
    for (const r of modes) m[r.strategy] = r.mode;
    return m;
  }, [modes]);

  // --- Step 5b: Manual Plan Composer (G4) ---------------------------------
  // Reuses the same POST /api/arbicore/execution/certification/run endpoint
  // that the discovery path uses.  No new backend logic.
  const BASE_WETH  = "0x4200000000000000000000000000000000000006";
  const BASE_USDC  = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";

  // Blank plan skeleton
  const blankPlan = () => ({
    strategy: "flash_loan_arbitrage",
    chain: "base",
    flash_loan_provider: "balancer_v2",
    borrow_token: BASE_WETH,
    borrow_amount_wei: "100000000000000000",     // 0.1 WETH
    borrow_amount_usd: "250",
    swap_hops: [
      { dex: "uniswap_v3", token_in: BASE_WETH, token_out: BASE_USDC, fee_tier_bps: 5,
        amount_in_wei: "100000000000000000", min_amount_out_wei: "249500000" },
      { dex: "uniswap_v3", token_in: BASE_USDC, token_out: BASE_WETH, fee_tier_bps: 5,
        amount_in_wei: "249500000", min_amount_out_wei: "100050000000000000" },
    ],
  });

  // Preset A — Intentional Revert Tx#1: last hop min_out is set so high
  // the router will revert with V3TooLittleReceived (selector 0x39d35496).
  // Value 9e18 wei = 9 ETH — 900× the expected 0.01 WETH output but
  // safely under MongoDB int64 (2^63-1 ≈ 9.22e18) so /plans/build can
  // persist the document.  Prior value "999999999999999999999" (999e18)
  // triggered OverflowError inside BSON encoding.
  const presetRevert = () => ({
    ...blankPlan(),
    borrow_amount_wei: "10000000000000000",       // 0.01 WETH — tiny
    borrow_amount_usd: "25",
    swap_hops: [
      { dex: "uniswap_v3", token_in: BASE_WETH, token_out: BASE_USDC, fee_tier_bps: 5,
        amount_in_wei: "10000000000000000", min_amount_out_wei: "24500000" },
      { dex: "uniswap_v3", token_in: BASE_USDC, token_out: BASE_WETH, fee_tier_bps: 5,
        amount_in_wei: "24500000",
        // 9 ETH — impossibly high for a 0.01 WETH round-trip; router will revert
        min_amount_out_wei: "9000000000000000000" },
    ],
  });

  // Preset B — Minimal Value-Producing Tx#2: realistic min_out that would
  // succeed if the price differential is favourable at broadcast time.
  const presetViable = () => ({
    ...blankPlan(),
    borrow_amount_wei: "10000000000000000",       // 0.01 WETH — smallest safe test
    borrow_amount_usd: "25",
    swap_hops: [
      { dex: "uniswap_v3", token_in: BASE_WETH, token_out: BASE_USDC, fee_tier_bps: 5,
        amount_in_wei: "10000000000000000", min_amount_out_wei: "24500000" },
      { dex: "uniswap_v3", token_in: BASE_USDC, token_out: BASE_WETH, fee_tier_bps: 5,
        amount_in_wei: "24500000", min_amount_out_wei: "10005000000000000" },
    ],
  });

  const [manualPlan, setManualPlan] = useState(blankPlan);
  const [showManualJson, setShowManualJson] = useState(false);

  const setHopField = (idx, field, value) => {
    setManualPlan((prev) => {
      const hops = [...prev.swap_hops];
      hops[idx] = { ...hops[idx], [field]: value };
      return { ...prev, swap_hops: hops };
    });
  };
  const addHop = () => setManualPlan((prev) => ({
    ...prev,
    swap_hops: [...prev.swap_hops, { dex: "uniswap_v3", token_in: "", token_out: "", fee_tier_bps: 5, amount_in_wei: "0", min_amount_out_wei: "0" }],
  }));
  const removeHop = (i) => setManualPlan((prev) => ({
    ...prev, swap_hops: prev.swap_hops.filter((_, idx) => idx !== i),
  }));

  const certifyManualPlan = async () => {
    if (!selectedWalletId) { toast.error("Select a registered wallet first (step 1)"); return; }
    const body = {
      strategy: manualPlan.strategy,
      chain: manualPlan.chain,
      flash_loan_provider: manualPlan.flash_loan_provider,
      borrow_token: manualPlan.borrow_token,
      borrow_amount_wei: String(manualPlan.borrow_amount_wei || "0"),
      borrow_amount_usd: parseFloat(manualPlan.borrow_amount_usd || "0"),
      swap_hops: manualPlan.swap_hops.map((h) => ({
        dex: h.dex,
        token_in: h.token_in,
        token_out: h.token_out,
        fee_tier_bps: parseInt(h.fee_tier_bps || "0", 10),
        amount_in_wei: String(h.amount_in_wei || "0"),
        min_amount_out_wei: String(h.min_amount_out_wei || "0"),
      })),
      signer_wallet_id: selectedWalletId,
      opportunity_id: `manual-${Date.now()}`,
      quote_effective_out_wei: String(
        manualPlan.swap_hops[manualPlan.swap_hops.length - 1]?.min_amount_out_wei || "0"
      ),
    };
    // Phase 10.10.1 · build-then-certify: /plans/build persists, /certification/run returns the verdict.
    await buildAndCertify(body);
  };

  return (
    <div data-testid="flash-loan-operator-page" style={{ padding: 24, color: "#e2e8f0", background: "#050810", minHeight: "100vh", fontFamily: "var(--v2-font-sans, system-ui)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 24, letterSpacing: 2, margin: "0 0 6px", color: "#ffb224" }}>FLASH LOAN OPERATOR</h1>
          <p style={{ color: "#64748b", fontSize: 12, marginBottom: 16, textTransform: "uppercase", letterSpacing: 1 }}>Phase 7B · Controlled LIMITED_LIVE validation workflow</p>
        </div>
        <a
          href="/v2/journey"
          data-testid="flops-open-journey-link"
          style={{
            background: "transparent",
            color: "#ffb224",
            border: "1px solid #ffb224",
            padding: "10px 16px",
            fontFamily: "var(--v2-font-mono, monospace)",
            fontSize: 12,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: 1,
            borderRadius: 2,
            textDecoration: "none",
            whiteSpace: "nowrap",
          }}
        >
          🧭 Open 14-Stage Journey →
        </a>
      </div>

      <KillSwitchBanner state={ksState} onEngage={engageKS} onDisengage={disengageKS} />

      {/* STEP 1 — Wallet registration */}
      <Card title="1 · Wallets" subtitle={`${wallets.length} registered`} testId="flops-wallets-card">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <Field label="Wallet label (any name for your records)" value={newWallet.label} onChange={(v) => setNewWallet({...newWallet, label: v})} placeholder="Base Gas Wallet #1" testId="flops-wallet-name" mono={false} />
            <Row gap={8}>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, display: "block", marginBottom: 4 }}>Chain</label>
                <select data-testid="flops-wallet-chain" value={newWallet.chain} onChange={(e) => setNewWallet({...newWallet, chain: e.target.value})} style={{ width: "100%", padding: "7px 10px", background: "#0a0f18", border: "1px solid #1c2733", color: "#e2e8f0", fontFamily: "monospace", fontSize: 12, borderRadius: 2 }}>
                  {CHAINS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, display: "block", marginBottom: 4 }}>Role</label>
                <select data-testid="flops-wallet-role" value={newWallet.execution_role} onChange={(e) => setNewWallet({...newWallet, execution_role: e.target.value})} style={{ width: "100%", padding: "7px 10px", background: "#0a0f18", border: "1px solid #1c2733", color: "#e2e8f0", fontFamily: "monospace", fontSize: 12, borderRadius: 2 }}>
                  {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </Row>
            <Field label="Address (0x…)" value={newWallet.address} onChange={(v) => setNewWallet({...newWallet, address: v})} placeholder="0x…" testId="flops-wallet-address" />
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: "block", fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 4 }}>
                Secret handle{" "}
                <span style={{ textTransform: "none", letterSpacing: 0, color: "#475569" }}>
                  (choose from Settings › Secrets)
                </span>
              </label>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <select
                  data-testid="flops-wallet-secret-handle"
                  value={newWallet.secret_handle_id}
                  onChange={(e) => setNewWallet({ ...newWallet, secret_handle_id: e.target.value })}
                  disabled={newWallet.execution_role !== "gas"}
                  style={{
                    flex: 1,
                    padding: "7px 10px",
                    background: "#0a0f18",
                    border: "1px solid #1c2733",
                    color: "#e2e8f0",
                    fontFamily: "monospace",
                    fontSize: 12,
                    borderRadius: 2,
                    opacity: newWallet.execution_role !== "gas" ? 0.4 : 1,
                  }}
                >
                  <option value="">
                    {newWallet.execution_role !== "gas"
                      ? "(not required for watch_only / treasury)"
                      : availableSecrets.length
                      ? "— select a secret —"
                      : "no secrets yet · store one in Settings › Secrets"}
                  </option>
                  {availableSecrets.map((s) => (
                    <option key={s.handle_id} value={s.handle_id}>
                      {s.label ? `${s.label} · ` : ""}{s.handle_id}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={refreshSecrets}
                  title="Reload the list of stored secrets"
                  data-testid="flops-wallet-refresh-secrets"
                  style={{
                    background: "transparent",
                    color: "#94a3b8",
                    border: "1px solid #1c2733",
                    padding: "6px 10px",
                    fontSize: 11,
                    fontFamily: "monospace",
                    cursor: "pointer",
                    borderRadius: 2,
                  }}
                >
                  ↻
                </button>
              </div>
              {newWallet.execution_role === "gas" && availableSecrets.length === 0 && (
                <a href="/v2/settings/secrets" style={{ display: "inline-block", marginTop: 6, fontSize: 11, color: "var(--v2-accent, #ffb224)" }}>
                  Open Settings › Secrets to store one first →
                </a>
              )}
            </div>
            <Btn testId="flops-wallet-submit" onClick={submitWallet}>Register wallet</Btn>
          </div>
          <div>
            <h3 style={{ fontSize: 12, color: "#64748b", textTransform: "uppercase", letterSpacing: 1, marginTop: 0 }}>Registered wallets</h3>
            {wallets.length === 0 && <div style={{ color: "#475569", fontSize: 12 }}>No wallets yet.</div>}
            {wallets.map(w => (
              <div key={w.wallet_id} data-testid={`flops-wallet-row-${w.wallet_id}`} onClick={() => setSelectedWalletId(w.wallet_id)} style={{ padding: 10, marginBottom: 6, background: selectedWalletId === w.wallet_id ? "#0e2540" : "#0a0f18", border: `1px solid ${selectedWalletId === w.wallet_id ? "#3b82f6" : "#1c2733"}`, cursor: "pointer", borderRadius: 2 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <strong style={{ fontSize: 12 }}>{w.label || w.name || w.wallet_id}</strong>
                  <Row gap={6}>
                    <Chip label={w.chain} tone="info" />
                    <Chip label={w.execution_role} tone={w.execution_role === "gas" ? "warn" : "muted"} />
                  </Row>
                </div>
                <div style={{ fontFamily: "monospace", fontSize: 11, color: "#94a3b8", marginTop: 4 }}>{w.address}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* STEP 2 — Secret Registry — redirect to Settings (Phase 10.5 canonical UI) */}
      <Card title="2 · Secret Registry" subtitle="Store the burner private key in Settings › Secrets" testId="flops-secrets-card">
        <p style={{ color: "#94a3b8", fontSize: 12, marginTop: 0, lineHeight: 1.55 }}>
          Store your gas-wallet private key in the canonical Secrets manager. It is encrypted-at-rest
          with Fernet (AES-128-CBC + HMAC-SHA256). The plaintext never appears in any response.
        </p>
        <ol style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.8, paddingLeft: 20, marginTop: 0 }}>
          <li>Click <strong>Open Settings › Secrets</strong> below.</li>
          <li>Add a secret with <em>scope=evm_sign</em>, <em>algorithm=eth_privkey</em>, and your 64-hex private key.</li>
          <li>Come back to Card 1 above — the new secret will appear in the <em>Secret handle</em> dropdown automatically. (Hit ↻ to refresh if needed.)</li>
        </ol>
        <a
          href="/v2/settings/secrets"
          data-testid="flops-open-secrets-link"
          style={{
            display: "inline-block",
            background: "var(--v2-accent, #ffb224)",
            color: "#0b0f14",
            padding: "8px 16px",
            fontFamily: "var(--v2-font-mono, monospace)",
            fontSize: 12,
            fontWeight: 600,
            textDecoration: "none",
            textTransform: "uppercase",
            letterSpacing: 0.8,
            borderRadius: 2,
            marginTop: 8,
          }}
        >
          Open Settings › Secrets →
        </a>
      </Card>

      {/* STEP 3 — Wallet Health + Balance */}
      <Card title="3 · Wallet Status · Gas Balance · Health" subtitle={selectedWalletId ? `wallet=${selectedWalletId}` : "select a wallet above"} testId="flops-health-card">
        <Btn testId="flops-refresh-health" subtle onClick={refreshHealth}>Refresh</Btn>
        {balance && (
          <div style={{ marginTop: 16 }}>
            <Row gap={16}>
              <div>
                <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 1 }}>Gas balance</div>
                <div data-testid="flops-balance-value" style={{ fontSize: 24, fontFamily: "monospace", color: balance.ok ? "#4ade80" : "#f87171" }}>
                  {balance.balance_native} {balance.symbol}
                </div>
                {balance.balance_usd != null && <div style={{ color: "#94a3b8", fontSize: 12 }}>~${balance.balance_usd}</div>}
              </div>
              <div>
                <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 1 }}>Block</div>
                <div style={{ fontSize: 14, fontFamily: "monospace" }}>{balance.block_number ?? "—"}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 1 }}>RPC</div>
                <div style={{ fontSize: 12, fontFamily: "monospace", color: "#94a3b8" }}>{balance.rpc_endpoint_redacted || "—"}</div>
              </div>
            </Row>
          </div>
        )}
        {health && (
          <div style={{ marginTop: 20 }}>
            <Row gap={12}>
              <Chip label={`overall ${health.overall_status}`} tone={health.overall_status === "READY" ? "ok" : health.overall_status === "WAIT" ? "warn" : "crit"} />
              <Chip label={`shadow ${health.ready_for_shadow ? "ready" : "not-ready"}`} tone={health.ready_for_shadow ? "ok" : "warn"} />
              <Chip label={`limited-live ${health.ready_for_limited_live ? "ready" : "not-ready"}`} tone={health.ready_for_limited_live ? "ok" : "warn"} />
            </Row>
            <div style={{ marginTop: 12 }}>
              {health.checks?.map(c => (
                <div key={c.key} data-testid={`flops-health-check-${c.key}`} style={{ display: "flex", padding: "6px 10px", background: "#0a0f18", border: "1px solid #1c2733", marginBottom: 4, alignItems: "center", gap: 12 }}>
                  <Chip label={c.status} tone={c.status === "READY" ? "ok" : c.status === "WAIT" ? "warn" : "crit"} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12 }}>{c.label}</div>
                    <div style={{ fontSize: 11, color: "#64748b" }}>{c.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* STEP 4 — Mode ladder */}
      <Card title="4 · Execution Mode Ladder" subtitle="OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE" testId="flops-mode-card">
        {modes.map(r => (
          <div key={r.strategy} data-testid={`flops-mode-row-${r.strategy}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "#0a0f18", border: "1px solid #1c2733", marginBottom: 4 }}>
            <div>
              <strong style={{ fontSize: 12 }}>{r.strategy}</strong>
              <span style={{ fontFamily: "monospace", fontSize: 11, color: "#94a3b8", marginLeft: 10 }}>{r.mode}</span>
            </div>
            <Row gap={6}>
              {["PAPER", "SHADOW", "LIMITED_LIVE"].map(m => (
                <Btn key={m} subtle testId={`flops-mode-promote-${r.strategy}-${m}`} onClick={() => promoteMode(r.strategy, m)} disabled={r.mode === m}>{m}</Btn>
              ))}
            </Row>
          </div>
        ))}
      </Card>

      {/* STEP 5 — Continuous Discovery */}
      <Card title="5 · Continuous Discovery" subtitle={discoveryStatus?.running ? `running (${discoveryStatus.interval_s}s)` : "stopped"} testId="flops-discovery-card">
        <Row gap={8}>
          <Btn testId="flops-discovery-tick" onClick={tickDiscovery}>Tick now</Btn>
          <Btn testId="flops-discovery-refresh" subtle onClick={refreshDiscovery}>Refresh</Btn>
          <span style={{ fontSize: 11, color: "#64748b" }}>last: {discoveryStatus?.last_run_at || "—"}</span>
        </Row>
        <div style={{ marginTop: 12 }}>
          {opps.length === 0 && <div style={{ color: "#475569", fontSize: 12 }}>No opportunities discovered yet.</div>}
          {opps.map(o => (
            <div key={o.opportunity_id} data-testid={`flops-opp-row-${o.opportunity_id}`} onClick={() => setSelectedOpp(o)} style={{
              padding: 10, marginBottom: 6,
              background: selectedOpp?.opportunity_id === o.opportunity_id ? "#0e2540" : "#0a0f18",
              border: `1px solid ${selectedOpp?.opportunity_id === o.opportunity_id ? "#3b82f6" : "#1c2733"}`,
              cursor: "pointer",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong style={{ fontSize: 12 }}>{o.opportunity_id}</strong>
                <Row gap={6}>
                  <Chip label={o.status} tone={o.status === "confirmed" ? "ok" : "muted"} />
                  <Chip label={`conf ${o.confidence}`} tone={o.confidence >= 0.55 ? "ok" : "warn"} />
                  <Chip label={o.chain} tone="info" />
                  <Chip label={o.flash_loan_provider} tone="info" />
                </Row>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
                borrow ${o.borrow_amount_usd} · net_profit ${o.net_profit_usd} · {o.profitable ? "profitable" : "not profitable"}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* STEP 5B — Manual Plan Composer (G4) — auto-discovery deferred to 10.9 */}
      <Card
        title="5B · Manual Plan Composer  ·  v10.10.6.1"
        subtitle={selectedWalletId
          ? `signer=${selectedWalletId}  ·  build-then-certify pipeline  ·  persistedPlanId=${persistedPlanId ? persistedPlanId.slice(0,20) + "…" : "(none yet)"}`
          : "select a registered wallet in step 1 first"}
        testId="flops-manual-plan-card"
      >
        <p style={{ color: "#94a3b8", fontSize: 12, marginTop: 0, lineHeight: 1.55 }}>
          Auto-discovery for the Flash Loan family is deferred until after your first successful LIMITED_LIVE tx.
          Compose the plan below and click <strong>Run full certification</strong>. Load a preset for the two
          canonical validation transactions:
        </p>

        <Row gap={8} wrap>
          <Btn testId="flops-manual-preset-revert" onClick={() => setManualPlan(presetRevert())}>
            🅐 Load Tx#1 · Intentional Revert
          </Btn>
          <Btn testId="flops-manual-preset-viable" subtle onClick={() => setManualPlan(presetViable())}>
            🅑 Load Tx#2 · Minimal Viable
          </Btn>
          <Btn testId="flops-manual-preset-blank" subtle onClick={() => setManualPlan(blankPlan())}>
            Reset to blank
          </Btn>
          <label style={{ fontSize: 11, color: "#94a3b8", display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
            <input type="checkbox" checked={showManualJson} onChange={(e) => setShowManualJson(e.target.checked)} data-testid="flops-manual-json-toggle" />
            Show raw JSON
          </label>
        </Row>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 14 }}>
          <div>
            <label style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, display: "block", marginBottom: 4 }}>Chain</label>
            <select data-testid="flops-manual-chain" value={manualPlan.chain} onChange={(e) => setManualPlan({ ...manualPlan, chain: e.target.value })}
              style={{ width:"100%", padding:"7px 10px", background:"#0a0f18", border:"1px solid #1c2733", color:"#e2e8f0", fontFamily:"monospace", fontSize:12, borderRadius:2 }}>
              {CHAINS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, display: "block", marginBottom: 4 }}>Provider</label>
            <select data-testid="flops-manual-provider" value={manualPlan.flash_loan_provider} onChange={(e) => setManualPlan({ ...manualPlan, flash_loan_provider: e.target.value })}
              style={{ width:"100%", padding:"7px 10px", background:"#0a0f18", border:"1px solid #1c2733", color:"#e2e8f0", fontFamily:"monospace", fontSize:12, borderRadius:2 }}>
              <option value="balancer_v2">balancer_v2</option>
            </select>
          </div>
          <Field label="Strategy" value={manualPlan.strategy} onChange={(v) => setManualPlan({ ...manualPlan, strategy: v })} testId="flops-manual-strategy" />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 10, marginTop: 10 }}>
          <Field label="Borrow token (Base WETH = 0x4200…0006)" value={manualPlan.borrow_token} onChange={(v) => setManualPlan({ ...manualPlan, borrow_token: v })} testId="flops-manual-borrow-token" />
          <Field label="Borrow amount (wei)" value={manualPlan.borrow_amount_wei} onChange={(v) => setManualPlan({ ...manualPlan, borrow_amount_wei: v })} testId="flops-manual-borrow-amount-wei" />
          <Field label="Borrow amount (USD est.)" value={manualPlan.borrow_amount_usd} onChange={(v) => setManualPlan({ ...manualPlan, borrow_amount_usd: v })} testId="flops-manual-borrow-amount-usd" />
        </div>

        <div style={{ marginTop: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8 }}>
              Swap hops ({manualPlan.swap_hops.length})
            </span>
            <Btn subtle testId="flops-manual-add-hop" onClick={addHop}>+ Add hop</Btn>
          </div>
          {manualPlan.swap_hops.map((hop, i) => (
            <div key={i} data-testid={`flops-manual-hop-${i}`} style={{ padding: 10, background: "#0a0f18", border: "1px solid #1c2733", marginBottom: 6, borderRadius: 2 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontFamily: "monospace", fontSize: 11, color: "#ffb224" }}>Hop {i + 1}</span>
                {manualPlan.swap_hops.length > 1 && (
                  <button onClick={() => removeHop(i)} style={{ background: "transparent", color: "#f87171", border: "1px solid #7f1d1d", fontSize: 10, padding: "2px 8px", cursor: "pointer", borderRadius: 2 }}>× remove</button>
                )}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr 2fr 1fr", gap: 8 }}>
                <div>
                  <label style={{ fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, display: "block", marginBottom: 4 }}>DEX</label>
                  <select value={hop.dex} onChange={(e) => setHopField(i, "dex", e.target.value)}
                    style={{ width:"100%", padding:"6px 8px", background:"#050810", border:"1px solid #1c2733", color:"#e2e8f0", fontFamily:"monospace", fontSize:11, borderRadius:2 }}>
                    <option value="uniswap_v3">uniswap_v3</option>
                    <option value="aerodrome">aerodrome</option>
                  </select>
                </div>
                <Field label="Token in" value={hop.token_in} onChange={(v) => setHopField(i, "token_in", v)} />
                <Field label="Token out" value={hop.token_out} onChange={(v) => setHopField(i, "token_out", v)} />
                <Field label="Fee bps" value={hop.fee_tier_bps} onChange={(v) => setHopField(i, "fee_tier_bps", v)} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 6 }}>
                <Field label="Amount in (wei)" value={hop.amount_in_wei} onChange={(v) => setHopField(i, "amount_in_wei", v)} />
                <Field label="Min amount out (wei)" value={hop.min_amount_out_wei} onChange={(v) => setHopField(i, "min_amount_out_wei", v)} />
              </div>
            </div>
          ))}
        </div>

        {showManualJson && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 4 }}>Composed plan (will be sent to /certification/run)</div>
            <Json value={manualPlan} maxHeight={200} />
          </div>
        )}

        <Row gap={8} wrap>
          <Btn testId="flops-manual-certify" onClick={certifyManualPlan} disabled={!selectedWalletId}>
            Run full certification (manual plan)
          </Btn>
          <span style={{ fontSize: 11, color: "#64748b" }}>
            The certification report will render in step 6 below.
          </span>
        </Row>
      </Card>

      {/* STEP 6 — Certification + Broadcast */}
      <Card title="6 · Certification & Broadcast" subtitle={selectedOpp ? `opp=${selectedOpp.opportunity_id}` : "select an opportunity above"} testId="flops-broadcast-card">
        <Row gap={8}>
          <Btn testId="flops-cert-run" onClick={certifyPlan} disabled={!selectedOpp}>Run full certification</Btn>
          <Btn testId="flops-broadcast-preview" subtle onClick={previewBroadcast} disabled={!certReport}>Preview broadcast (dry)</Btn>
          <label style={{ fontSize: 12, color: "#94a3b8", display: "flex", alignItems: "center", gap: 6 }}>
            <input data-testid="flops-broadcast-confirm-check" type="checkbox" checked={confirmChecked} onChange={(e) => setConfirmChecked(e.target.checked)} />
            I understand this will submit a real transaction.
          </label>
          <Btn testId="flops-broadcast-submit" danger onClick={broadcastPlan} disabled={!certReport || !confirmChecked}>Broadcast LIMITED_LIVE</Btn>
        </Row>
        {certReport && (
          <div style={{ marginTop: 16 }}>
            <Row gap={12} wrap>
              <Chip label={`verdict ${certReport.verdict}`} tone={certReport.verdict === "PASS" ? "ok" : certReport.verdict === "WAIT" ? "warn" : "crit"} />
              <Chip label={`plan ${certReport.plan_id?.slice(0, 12)}…`} tone="info" />
              <Chip label={`broadcast=${certReport.would_broadcast ? "true" : "false"}`} tone={certReport.would_broadcast ? "crit" : "ok"} />
            </Row>
            <div style={{ marginTop: 10 }}>
              {certReport.stages?.map(s => (
                <div key={s.stage} style={{ display: "flex", padding: "6px 10px", background: "#0a0f18", border: "1px solid #1c2733", marginBottom: 3, gap: 10, alignItems: "center" }}>
                  <Chip label={s.status} tone={s.status === "PASS" ? "ok" : s.status === "WAIT" ? "warn" : s.status === "BLOCKED" ? "crit" : "muted"} />
                  <div style={{ flex: 1, fontSize: 12 }}>{s.stage} — <span style={{ color: "#64748b" }}>{s.detail}</span></div>
                </div>
              ))}
            </div>
          </div>
        )}
        {broadcastReceipt && (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: 12, color: "#64748b", textTransform: "uppercase", letterSpacing: 1 }}>Broadcast receipt</h3>
            <Row gap={12} wrap>
              <Chip label={broadcastReceipt.broadcast_sent ? "SENT" : "HELD"} tone={broadcastReceipt.broadcast_sent ? "ok" : "warn"} />
              {broadcastReceipt.tx_hash && <Chip label={`tx ${broadcastReceipt.tx_hash?.slice(0, 14)}…`} tone="info" />}
              {broadcastReceipt.signer_address && <Chip label={`signer ${broadcastReceipt.signer_address?.slice(0, 10)}…`} tone="muted" />}
            </Row>
            <div style={{ marginTop: 10 }}>
              {Object.entries(broadcastReceipt.gate_ladder || {}).map(([k, v]) => (
                <div key={k} style={{ display: "flex", padding: "5px 10px", background: "#0a0f18", border: "1px solid #1c2733", marginBottom: 3, gap: 10 }}>
                  <Chip label={v} tone={v === "PASS" || v === "SENT" ? "ok" : v === "HELD" ? "warn" : "crit"} />
                  <div style={{ fontSize: 12 }}>{k}</div>
                </div>
              ))}
            </div>
            {broadcastReceipt.denied_reasons?.length > 0 && (
              <div style={{ marginTop: 10, padding: 10, background: "#3a0a0a", border: "1px solid #7f1d1d", color: "#fca5a5", fontFamily: "monospace", fontSize: 11 }}>
                {broadcastReceipt.denied_reasons.map((r, i) => <div key={i}>· {r}</div>)}
              </div>
            )}
            {(broadcastReceipt.preflight_revert_data || broadcastReceipt.preflight_revert_source === "unavailable" || broadcastReceipt.preflight_revert_source === "no_call_obj") && (
              <div data-testid="flops-preflight-revert-details" style={{ marginTop: 10, padding: 12, background: "#1e293b", border: "1px solid #334155", color: "#e2e8f0", fontFamily: "monospace", fontSize: 11 }}>
                <div style={{ color: "#94a3b8", textTransform: "uppercase", letterSpacing: 0.8, fontSize: 10, marginBottom: 6, display: "flex", gap: 8, alignItems: "center" }}>
                  <span>Preflight revert</span>
                  {broadcastReceipt.preflight_revert_source && (
                    <span data-testid="flops-preflight-revert-source" style={{ padding: "2px 6px", background: broadcastReceipt.preflight_revert_source === "eth_call" ? "#0b3b2e" : broadcastReceipt.preflight_revert_source === "debug_traceCall" ? "#3b2e0b" : "#3b0b0b", color: "#e2e8f0", borderRadius: 3, fontSize: 9, letterSpacing: 0.5 }}>
                      via {broadcastReceipt.preflight_revert_source}
                    </span>
                  )}
                </div>
                {broadcastReceipt.preflight_revert_data ? (
                  <div style={{ marginBottom: 4 }}>
                    <span style={{ color: "#64748b" }}>raw data: </span>
                    <code data-testid="flops-preflight-revert-raw" style={{ color: "#ffb224", wordBreak: "break-all" }}>{broadcastReceipt.preflight_revert_data}</code>
                  </div>
                ) : (
                  <div data-testid="flops-preflight-revert-unavailable" style={{ marginBottom: 4, color: "#f87171" }}>
                    raw data unavailable — RPC omitted <code>error.data</code> and <code>debug_traceCall</code> could not recover it.
                  </div>
                )}
                {(!broadcastReceipt.preflight_revert_data && broadcastReceipt.preflight_trace_diagnostic?.length > 0) && (
                  <div data-testid="flops-preflight-trace-diagnostic" style={{ marginTop: 6, padding: 6, background: "#0f172a", border: "1px solid #1e293b", color: "#cbd5e1", fontSize: 11 }}>
                    <div style={{ color: "#94a3b8", textTransform: "uppercase", letterSpacing: 0.6, fontSize: 9, marginBottom: 4 }}>debug_traceCall attempts</div>
                    {broadcastReceipt.preflight_trace_diagnostic.map((d, i) => {
                      const outcomeColor = d.outcome === "recovered" ? "#34d399"
                        : d.outcome === "method_not_found" ? "#f59e0b"
                        : d.outcome === "forbidden" ? "#f97316"
                        : d.outcome === "empty_output" ? "#a78bfa"
                        : "#f87171";
                      return (
                        <div key={i} data-testid={`flops-preflight-trace-attempt-${i}`} style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 3, fontFamily: "monospace" }}>
                          <span style={{ color: "#64748b", minWidth: 78 }}>{d.tracer}</span>
                          <span style={{ color: outcomeColor, minWidth: 130 }}>{d.outcome}</span>
                          <span style={{ color: "#cbd5e1", wordBreak: "break-word" }}>
                            {d.rpc_code != null ? `code=${d.rpc_code} ` : ""}{d.rpc_message || d.source || ""}
                          </span>
                        </div>
                      );
                    })}
                    {(() => {
                      const diag = broadcastReceipt.preflight_trace_diagnostic;
                      const allMethodNotFound = diag.every((d) => d.outcome === "method_not_found");
                      const anyForbidden = diag.some((d) => d.outcome === "forbidden");
                      const anyEmpty = diag.some((d) => d.outcome === "empty_output");
                      let rec = null;
                      if (allMethodNotFound) {
                        rec = "This RPC provider does not expose the debug_* namespace. Switch the operator RPC endpoint (Settings → Network) to one that supports debug_traceCall — recommended: Alchemy, QuickNode, Tenderly, or a self-hosted geth/erigon node with --http.api=eth,debug.";
                      } else if (anyForbidden) {
                        rec = "The RPC provider recognises debug_traceCall but refuses this API key (likely a paid-tier method). Upgrade the plan or switch endpoint (Alchemy Growth+, QuickNode Build+ tiers include debug_*).";
                      } else if (anyEmpty) {
                        rec = "debug_traceCall returned no revert bytes (empty output). The revert likely occurred outside the traced frame — try running the plan through Tenderly's UI simulator for a full call graph.";
                      } else {
                        rec = "debug_traceCall failed with an unexpected error (see attempts above). Check the operator RPC endpoint health, or switch to a known-good provider.";
                      }
                      return (
                        <div data-testid="flops-preflight-trace-recommendation" style={{ marginTop: 6, padding: 6, background: "#1e293b", border: "1px solid #334155", color: "#fde68a", fontFamily: "system-ui, sans-serif", fontSize: 11, lineHeight: 1.4 }}>
                          <strong style={{ color: "#fbbf24" }}>Recommendation:</strong> {rec}
                        </div>
                      );
                    })()}
                  </div>
                )}
                {broadcastReceipt.preflight_revert_decoded && (
                  <div style={{ marginBottom: 4 }}>
                    <span style={{ color: "#64748b" }}>decoded selector: </span>
                    <code data-testid="flops-preflight-revert-decoded" style={{ color: "#34d399" }}>{broadcastReceipt.preflight_revert_decoded}</code>
                  </div>
                )}
                {broadcastReceipt.preflight_revert_component && (
                  <div style={{ marginBottom: 4 }}>
                    <span style={{ color: "#64748b" }}>origin: </span>
                    <code data-testid="flops-preflight-revert-component" style={{ color: "#60a5fa" }}>{broadcastReceipt.preflight_revert_component}</code>
                  </div>
                )}
                {broadcastReceipt.preflight_revert_explanation && (
                  <div data-testid="flops-preflight-revert-explanation" style={{ marginTop: 6, padding: 6, background: "#0f172a", border: "1px solid #1e293b", color: "#cbd5e1", fontFamily: "system-ui, sans-serif", fontSize: 11, lineHeight: 1.4 }}>
                    {broadcastReceipt.preflight_revert_explanation}
                  </div>
                )}
              </div>
            )}
            <details style={{ marginTop: 10 }}>
              <summary style={{ cursor: "pointer", color: "#94a3b8", fontSize: 11 }}>Raw receipt JSON</summary>
              <div style={{ marginTop: 8 }}><Json value={broadcastReceipt} maxHeight={320} /></div>
            </details>
          </div>
        )}
      </Card>
    </div>
  );
}
