import { API_BASE } from "@/lib/apiBase";
/**
 * ArbiCore X — UI v2 · Post-Trade Dashboard (Phase 9)
 *
 * Renders the most recent broadcast attempts (LIMITED_LIVE preferred)
 * alongside their evidence trail:
 *   - tx_hash (linked to BaseScan if base chain)
 *   - gas used / gas price / nonce
 *   - flash loan amount + borrow token
 *   - preflight status
 *   - evidence bundle reference
 *   - certification snapshot
 *   - calibration + adaptive-weight updates (companion widgets)
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";

const API = API_BASE;
const MONO = "var(--v2-font-mono, ui-monospace, SFMono-Regular, monospace)";

const explorerFor = (chain, txHash) => {
  if (!txHash) return null;
  if ((chain || "").toLowerCase() === "base") return `https://basescan.org/tx/${txHash}`;
  return null;
};

const Chip = ({ label, tone = "info" }) => {
  const tones = {
    info:  { bg: "#0f172a", fg: "#93c5fd", bd: "#1e3a8a" },
    ok:    { bg: "#022c22", fg: "#4ade80", bd: "#065f46" },
    warn:  { bg: "#3d2500", fg: "#fbbf24", bd: "#78350f" },
    crit:  { bg: "#3a0a0a", fg: "#f87171", bd: "#7f1d1d" },
    muted: { bg: "#0f141c", fg: "#64748b", bd: "#1c2733" },
  };
  const t = tones[tone] || tones.info;
  return (
    <span style={{
      background: t.bg, color: t.fg, border: `1px solid ${t.bd}`,
      fontFamily: MONO, fontSize: 10, padding: "2px 8px", borderRadius: 2,
      textTransform: "uppercase", letterSpacing: 0.6, fontWeight: 600,
    }}>{label}</span>
  );
};

const Card = ({ title, subtitle, children, testId }) => (
  <section
    data-testid={testId}
    style={{
      background: "var(--v2-bg-surface, #0f141c)",
      border: "1px solid var(--v2-border-subtle, #1c2733)",
      padding: 18, marginBottom: 14, borderRadius: 2,
    }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
      <h2 style={{ color: "#e2e8f0", fontSize: 14, fontWeight: 600, margin: 0, textTransform: "uppercase", letterSpacing: 1.4 }}>{title}</h2>
      {subtitle && <span style={{ color: "#64748b", fontSize: 11 }}>{subtitle}</span>}
    </div>
    {children}
  </section>
);

const KV = ({ k, v, mono = true, testId }) => (
  <div style={{ display: "grid", gridTemplateColumns: "160px 1fr", gap: 10, alignItems: "baseline" }}>
    <span style={{ color: "#64748b", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>{k}</span>
    <span data-testid={testId} style={{ color: "#e2e8f0", fontSize: 12, fontFamily: mono ? MONO : "inherit", wordBreak: "break-all" }}>{v}</span>
  </div>
);


function BroadcastReceipt({ item }) {
  const url = explorerFor(item.chain, item.tx_hash);
  const sent = !!item.broadcast_sent;
  const tone = sent ? "ok" : (item.gate_denied ? "warn" : "muted");
  return (
    <div data-testid={`pt-receipt-${item.plan_id}`} style={{
      background: "#0a0f18",
      borderLeft: `3px solid ${sent ? "#065f46" : (item.gate_denied ? "#78350f" : "#1c2733")}`,
      padding: "14px 18px", marginBottom: 8, borderRadius: 2,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10, alignItems: "center" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Chip label={item.mode || "n/a"} tone={sent ? "ok" : "muted"} />
          <span style={{ color: "#e2e8f0", fontFamily: MONO, fontSize: 12, fontWeight: 600 }}>{item.plan_id}</span>
          <span style={{ color: "#64748b", fontSize: 11 }}>{item.strategy}</span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {sent && <Chip label="broadcast_sent" tone="ok" />}
          {item.preflight_ok && <Chip label="preflight_ok" tone="ok" />}
          {item.gate_denied && <Chip label={`gate: ${item.gate_denied}`} tone="warn" />}
        </div>
      </div>

      <div style={{ display: "grid", gap: 6 }}>
        <KV k="tx_hash" testId="pt-tx-hash" v={
          item.tx_hash
            ? (url
                ? <a href={url} target="_blank" rel="noreferrer" style={{ color: "var(--v2-accent, #ffb224)" }}>{item.tx_hash}</a>
                : item.tx_hash)
            : "—"
        }/>
        <KV k="chain"           v={item.chain || "—"} />
        <KV k="borrow_token"    v={item.borrow_token || "—"} />
        <KV k="borrow_amount"   v={item.borrow_amount_wei ? String(item.borrow_amount_wei) + " wei" : "—"} />
        <KV k="recipient"       v={item.recipient || "—"} />
        <KV k="profit_recipient"v={item.profit_recipient || "—"} />
        <KV k="gas_used"        v={item.gas_used ? String(item.gas_used) : "—"} />
        <KV k="gas_price_wei"   v={item.gas_price_wei ? String(item.gas_price_wei) : "—"} />
        <KV k="nonce"           v={item.nonce != null ? String(item.nonce) : "—"} />
        <KV k="evidence_ref"    v={item.evidence_ref || "pending"} />
        <KV k="attempted_at"    v={item.attempted_at || "—"} />
        {item.denied_reason && <KV k="denied_reason" v={item.denied_reason} />}
      </div>
    </div>
  );
}


export default function PostTradeDashboardPage() {
  const [state, setState] = useState(null);
  const [cal, setCal]     = useState(null);
  const [adw, setAdw]     = useState(null);
  const [ev,  setEv]      = useState(null);
  const [err, setErr]     = useState(null);

  const load = useCallback(async () => {
    try {
      const [r1, r2, r3, r4] = await Promise.allSettled([
        axios.get(`${API}/arbicore/post-trade/latest?limit=10`, { timeout: 10000 }),
        axios.get(`${API}/arbicore/intelligence/calibration/history?limit=5`, { timeout: 10000 }),
        axios.get(`${API}/arbicore/intelligence/adaptive-weights/history?limit=5`, { timeout: 10000 }),
        axios.get(`${API}/arbicore/intelligence/evidence/history?limit=5`, { timeout: 10000 }),
      ]);
      if (r1.status === "fulfilled") setState(r1.value.data); else setErr(String(r1.reason));
      if (r2.status === "fulfilled") setCal(r2.value.data);
      if (r3.status === "fulfilled") setAdw(r3.value.data);
      if (r4.status === "fulfilled") setEv(r4.value.data);
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, [load]);

  const receipts = useMemo(() => state?.receipts || [], [state]);

  return (
    <div data-testid="pt-root" style={{ padding: "20px 24px", maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ color: "#e2e8f0", fontSize: 22, fontWeight: 600, margin: 0, letterSpacing: 1.2 }}>
          Post-Trade Dashboard
        </h1>
        <div style={{ color: "#64748b", fontFamily: MONO, fontSize: 11, marginTop: 4 }}>
          Every broadcast attempt · tx_hash · gas · evidence · learning updates
        </div>
      </div>

      {err && (
        <div data-testid="pt-err" style={{
          background: "#3a0a0a", border: "1px solid #7f1d1d",
          color: "#fca5a5", padding: "10px 14px", marginBottom: 14,
          fontFamily: MONO, fontSize: 11,
        }}>{err}</div>
      )}

      <Card testId="pt-latest" title="Latest broadcast attempts" subtitle={`${receipts.length} shown`}>
        {receipts.length === 0 && (
          <div data-testid="pt-empty" style={{ color: "#64748b", fontFamily: MONO, fontSize: 12, padding: "18px 0" }}>
            No broadcast attempts recorded yet. Once the operator confirms the first LIMITED_LIVE
            plan, the receipt will land here alongside its evidence bundle and learning update.
          </div>
        )}
        {receipts.map((r) => <BroadcastReceipt key={r.plan_id} item={r} />)}
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
        <Card testId="pt-calibration" title="Calibration">
          <SummaryList items={cal?.items || []} labelKey="calibrator_version" secondaryKey="created_at" empty="No calibration ticks yet." />
        </Card>
        <Card testId="pt-adw" title="Adaptive Weights">
          <SummaryList items={adw?.items || []} labelKey="strategy" secondaryKey="created_at" empty="No adaptive-weight recommendations yet." />
        </Card>
        <Card testId="pt-evidence" title="Evidence Bundles">
          <SummaryList items={ev?.items || []} labelKey="bundle_hash" secondaryKey="created_at" empty="No evidence bundles yet." />
        </Card>
      </div>
    </div>
  );
}


const SummaryList = ({ items, labelKey, secondaryKey, empty }) => {
  if (!items || items.length === 0) {
    return <div style={{ color: "#64748b", fontFamily: MONO, fontSize: 11 }}>{empty}</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {items.slice(0, 5).map((it, i) => (
        <div key={i} style={{
          background: "#050810", border: "1px solid #1c2733",
          padding: "8px 12px", borderRadius: 2,
        }}>
          <div style={{ color: "#e2e8f0", fontSize: 11, fontFamily: MONO, wordBreak: "break-all" }}>
            {String(it[labelKey] || it.id || "—").slice(0, 40)}
          </div>
          <div style={{ color: "#64748b", fontSize: 10, fontFamily: MONO }}>
            {String(it[secondaryKey] || "").slice(0, 24)}
          </div>
        </div>
      ))}
    </div>
  );
};
