/**
 * ArbiCore X — UI v2 · Wallet & Capital Intelligence
 *
 * READ-ONLY on-chain monitoring for the configured Base gas/execution wallet:
 * live balances, full transaction statement, DEX classification, flash-loan
 * money trail and capital reconciliation. Public addresses only — never keys.
 * SHADOW-safe. All state is backend-authoritative.
 */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const MONO = "var(--v2-font-mono, ui-monospace, monospace)";

const C = {
  bg: "#0b0f14", panel: "#111820", border: "#1e2a36", borderSoft: "#172230",
  text: "#e2e8f0", sub: "#94a3b8", muted: "#64748b",
  green: "#34d399", yellow: "#fbbf24", red: "#f87171", accent: "#38bdf8",
};

const fmtUsd = (v) => (v == null ? "—" : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`);
const fmtNum = (v, d = 6) => (v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));
const shortHash = (h) => (h ? `${h.slice(0, 10)}…${h.slice(-6)}` : "—");
const shortAddr = (a) => (a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "—");

function Panel({ title, right, children, testid }) {
  return (
    <div data-testid={testid} style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 8, padding: 18, marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div style={{ color: C.sub, fontSize: 11, letterSpacing: 1.2, textTransform: "uppercase", fontFamily: MONO }}>{title}</div>
        {right}
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value, sub, color }) {
  return (
    <div style={{ minWidth: 120 }}>
      <div style={{ color: C.muted, fontSize: 10, letterSpacing: 0.8, textTransform: "uppercase" }}>{label}</div>
      <div style={{ color: color || C.text, fontSize: 20, fontFamily: MONO, marginTop: 4 }}>{value}</div>
      {sub != null && <div style={{ color: C.muted, fontSize: 11, fontFamily: MONO }}>{sub}</div>}
    </div>
  );
}

function Tag({ children, color, ...rest }) {
  const c = color || C.muted;
  return <span {...rest} style={{ padding: "1px 7px", fontFamily: MONO, fontSize: 10, letterSpacing: 0.6, border: `1px solid ${c}`, color: c, borderRadius: 3 }}>{children}</span>;
}

export default function CapitalIntelligencePage() {
  const [address, setAddress] = useState("");
  const [wallets, setWallets] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ tx_type: "", venue: "", status: "" });
  const [statement, setStatement] = useState(null);
  const [trail, setTrail] = useState(null);
  const [trailLoading, setTrailLoading] = useState(false);

  const load = useCallback(async (addr) => {
    setLoading(true); setError(null);
    const params = addr ? { address: addr } : {};
    const cfg = { params, timeout: 90000 };
    // Fetch each panel independently so a slow (rate-limited) balance read
    // never blocks the others — each panel renders as soon as it resolves.
    const [balR, stmtR, recR, venR, walR] = await Promise.allSettled([
      axios.get(`${API}/arbicore/capital/balances`, cfg),
      axios.get(`${API}/arbicore/capital/statement`, { ...cfg, params: { ...params, limit: 50 } }),
      axios.get(`${API}/arbicore/capital/reconciliation`, cfg),
      axios.get(`${API}/arbicore/capital/venue-stats`, cfg),
      axios.get(`${API}/arbicore/capital/wallets`, { timeout: 20000 }),
    ]);
    const pick = (r) => (r.status === "fulfilled" ? r.value.data : null);
    const bal = pick(balR), stmt = pick(stmtR), rec = pick(recR), ven = pick(venR), wal = pick(walR);
    setData({ balances: bal, statement: stmt, reconciliation: rec, venue_stats: ven });
    if (stmt) setStatement(stmt);
    if (wal?.wallets) setWallets(wal.wallets);
    if (!addr && bal?.address) setAddress(bal.address);
    if (!bal && !stmt && !rec) {
      const err = [balR, stmtR, recR].find((r) => r.status === "rejected");
      setError(err?.reason?.response?.data?.detail || err?.reason?.message || "failed to load");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(""); }, [load]);

  const applyFilters = useCallback(async () => {
    try {
      const params = { address, ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) };
      const res = await axios.get(`${API}/arbicore/capital/statement`, { params, timeout: 90000 });
      setStatement(res.data);
    } catch (e) { setError(e.message); }
  }, [address, filters]);

  const openTrail = useCallback(async (hash) => {
    setTrail(null); setTrailLoading(true);
    try {
      const res = await axios.get(`${API}/arbicore/capital/money-trail`, {
        params: { address, tx_hash: hash }, timeout: 90000,
      });
      setTrail(res.data);
    } catch (e) { setTrail({ ok: false, reason: e.message, tx_hash: hash }); }
    finally { setTrailLoading(false); }
  }, [address]);

  const bal = data?.balances;
  const rec = data?.reconciliation;
  const stats = data?.venue_stats;
  const txs = statement?.transactions || [];

  return (
    <div data-testid="capital-intelligence-page" style={{ background: C.bg, minHeight: "100%", padding: 24, color: C.text, fontFamily: "var(--v2-font-sans, system-ui)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 26, margin: 0, letterSpacing: -0.5 }}>Wallet & Capital Intelligence</h1>
          <div style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>Read-only on-chain monitoring · public addresses only · SHADOW-safe</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            data-testid="capital-wallet-select"
            value={address}
            onChange={(e) => { setAddress(e.target.value); load(e.target.value); }}
            style={{ background: C.panel, color: C.text, border: `1px solid ${C.border}`, borderRadius: 6, padding: "7px 10px", fontFamily: MONO, fontSize: 12 }}
          >
            {wallets.length === 0 && <option value={address}>{shortAddr(address)}</option>}
            {wallets.map((w) => (
              <option key={w.address} value={w.address}>{w.label || w.wallet_id} · {shortAddr(w.address)}</option>
            ))}
          </select>
          <button data-testid="capital-refresh-btn" onClick={() => load(address)} style={{ background: C.accent, color: "#04121c", border: "none", borderRadius: 6, padding: "8px 14px", fontFamily: MONO, fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
            {loading ? "Syncing…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && <div data-testid="capital-error" style={{ background: "#2a1214", border: `1px solid ${C.red}`, color: C.red, padding: 12, borderRadius: 6, marginBottom: 16, fontFamily: MONO, fontSize: 12 }}>{String(error)}</div>}

      {/* Live balances */}
      <Panel title="Live Balances" testid="capital-balances-panel"
        right={<span style={{ color: C.muted, fontSize: 11, fontFamily: MONO }}>block {bal?.block_number ?? "—"} · synced {bal?.last_sync ? new Date(bal.last_sync).toLocaleTimeString() : "—"}</span>}>
        {bal && bal.available === false && (
          <div data-testid="capital-balances-unavailable" style={{ border: `1px dashed ${C.yellow}`, background: "#1c1a10", color: C.yellow, padding: "8px 12px", borderRadius: 6, marginBottom: 12, fontFamily: MONO, fontSize: 12 }}>
            UNAVAILABLE — {bal.unavailable_reason || "on-chain balance source unavailable"}. Total value shown as "—" (not $0).
          </div>
        )}
        <div style={{ display: "flex", gap: 32, flexWrap: "wrap", marginBottom: 12 }}>
          <Stat label="Address" value={<span data-testid="capital-address" style={{ fontSize: 13 }}>{shortAddr(bal?.address)}</span>} />
          <Stat label="Gas / Native (ETH)" value={<span data-testid="capital-native-balance">{fmtNum(bal?.native?.balance, 8)}</span>} sub={fmtUsd(bal?.native?.value_usd)} color={C.green} />
          <Stat label="Total Value" value={<span data-testid="capital-total-usd">{fmtUsd(bal?.total_value_usd)}</span>} />
          <Stat label="ETH Price" value={fmtUsd(bal?.eth_price_usd)} />
          <Stat label="Tokens Held" value={<span data-testid="capital-token-count">{bal?.tokens?.length ?? 0}</span>} />
        </div>
        {bal?.tokens?.length > 0 && (
          <table data-testid="capital-tokens-table" style={{ width: "100%", borderCollapse: "collapse", fontFamily: MONO, fontSize: 12 }}>
            <thead><tr style={{ color: C.muted, textAlign: "left" }}>
              {["Token", "Balance", "Price", "Value"].map((h) => <th key={h} style={{ padding: "6px 8px", borderBottom: `1px solid ${C.borderSoft}` }}>{h}</th>)}
            </tr></thead>
            <tbody>
              {bal.tokens.map((t) => (
                <tr key={t.address} data-testid={`capital-token-${t.symbol}`}>
                  <td style={{ padding: "6px 8px" }}>{t.symbol}</td>
                  <td style={{ padding: "6px 8px" }}>{fmtNum(t.balance, 6)}</td>
                  <td style={{ padding: "6px 8px" }}>{t.priced ? fmtUsd(t.price_usd) : <Tag>unpriced</Tag>}</td>
                  <td style={{ padding: "6px 8px" }}>{t.value_usd != null ? fmtUsd(t.value_usd) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {/* Reconciliation */}
      <Panel title="Capital Reconciliation" testid="capital-reconciliation-panel"
        right={<Tag color={rec?.reconciled ? C.green : C.yellow} data-testid="capital-reconciled-tag">{rec?.reconciled ? "RECONCILED" : "RESIDUAL ≠ 0"}</Tag>}>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <Stat label="Start (ETH)" value={fmtNum(rec?.start_balance, 8)} sub={fmtUsd(rec?.start_balance_usd)} />
          <Stat label="+ Inflows" value={fmtNum(rec?.inflows, 8)} sub={fmtUsd(rec?.inflows_usd)} color={C.green} />
          <Stat label="− Outflows" value={fmtNum(rec?.outflows, 8)} sub={fmtUsd(rec?.outflows_usd)} color={C.red} />
          <Stat label="− Fees" value={fmtNum(rec?.fees, 8)} sub={fmtUsd(rec?.fees_usd)} color={C.yellow} />
          <Stat label="= End (ETH)" value={<span data-testid="capital-end-balance">{fmtNum(rec?.end_balance, 8)}</span>} sub={fmtUsd(rec?.end_balance_usd)} color={C.accent} />
          <Stat label="Residual" value={<span data-testid="capital-residual">{fmtNum(rec?.residual, 10)}</span>} color={rec?.reconciled ? C.green : C.yellow} />
        </div>
        {rec && !rec.statement_complete && (
          <div data-testid="capital-statement-incomplete" style={{ marginTop: 12, color: C.yellow, fontSize: 12, fontFamily: MONO }}>
            ⚠ Statement incomplete: {rec.statement_note || "transaction source unavailable"}
          </div>
        )}
      </Panel>

      {/* Transaction statement */}
      <Panel title="Transaction Statement" testid="capital-statement-panel"
        right={<span style={{ color: C.muted, fontSize: 11, fontFamily: MONO }}>{statement?.count ?? 0} tx · source {statement?.source_ok ? "live" : "unavailable"}</span>}>
        <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
          {[
            { k: "tx_type", opts: ["", "dex_swap", "flash_loan", "executor_call", "native_transfer", "transfer"] },
            { k: "venue", opts: ["", "uniswap_v3", "aerodrome", "balancer_vault"] },
            { k: "status", opts: ["", "success", "failed"] },
          ].map(({ k, opts }) => (
            <select key={k} data-testid={`capital-filter-${k}`} value={filters[k]}
              onChange={(e) => setFilters((f) => ({ ...f, [k]: e.target.value }))}
              style={{ background: C.bg, color: C.text, border: `1px solid ${C.border}`, borderRadius: 5, padding: "5px 8px", fontFamily: MONO, fontSize: 11 }}>
              {opts.map((o) => <option key={o} value={o}>{o || `all ${k}`}</option>)}
            </select>
          ))}
          <button data-testid="capital-apply-filters-btn" onClick={applyFilters} style={{ background: C.borderSoft, color: C.text, border: `1px solid ${C.border}`, borderRadius: 5, padding: "5px 12px", fontFamily: MONO, fontSize: 11, cursor: "pointer" }}>Apply</button>
        </div>
        {!statement?.source_ok && (
          <div data-testid="capital-source-note" style={{ color: C.yellow, fontSize: 12, fontFamily: MONO, marginBottom: 10 }}>
            {statement?.source_reason || "transaction index unavailable"}
          </div>
        )}
        {txs.length === 0 ? (
          <div data-testid="capital-no-tx" style={{ color: C.muted, fontFamily: MONO, fontSize: 12, padding: 8 }}>No transactions for the current filters.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table data-testid="capital-statement-table" style={{ width: "100%", borderCollapse: "collapse", fontFamily: MONO, fontSize: 11 }}>
              <thead><tr style={{ color: C.muted, textAlign: "left" }}>
                {["Time", "Hash", "Type", "Dir", "Venue", "ETH", "Fee", "Status", ""].map((h) => <th key={h} style={{ padding: "6px 8px", borderBottom: `1px solid ${C.borderSoft}`, whiteSpace: "nowrap" }}>{h}</th>)}
              </tr></thead>
              <tbody>
                {txs.map((t) => (
                  <tr key={t.hash} data-testid={`capital-tx-row`}>
                    <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>{t.datetime ? new Date(t.datetime).toLocaleString() : "—"}</td>
                    <td style={{ padding: "6px 8px" }}><a href={`https://basescan.org/tx/${t.hash}`} target="_blank" rel="noreferrer" style={{ color: C.accent, textDecoration: "none" }}>{shortHash(t.hash)}</a></td>
                    <td style={{ padding: "6px 8px" }}><Tag color={t.tx_type === "flash_loan" || t.tx_type === "executor_call" ? C.accent : C.muted}>{t.tx_type}</Tag></td>
                    <td style={{ padding: "6px 8px" }}><Tag color={t.direction === "in" ? C.green : t.direction === "out" ? C.red : C.muted}>{t.direction}</Tag></td>
                    <td style={{ padding: "6px 8px" }}>{t.venue || "—"}</td>
                    <td style={{ padding: "6px 8px" }}>{fmtNum(t.native_amount, 6)}</td>
                    <td style={{ padding: "6px 8px" }}>{fmtNum(t.fee_eth, 8)}</td>
                    <td style={{ padding: "6px 8px" }}><Tag color={t.status === "success" ? C.green : C.red}>{t.status}</Tag></td>
                    <td style={{ padding: "6px 8px" }}>
                      <button data-testid="capital-trail-btn" onClick={() => openTrail(t.hash)} style={{ background: "transparent", color: C.accent, border: `1px solid ${C.border}`, borderRadius: 4, padding: "2px 8px", fontFamily: MONO, fontSize: 10, cursor: "pointer" }}>Trail</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* Money trail */}
      {(trail || trailLoading) && (
        <Panel title="Flash-Loan Money Trail" testid="capital-money-trail-panel"
          right={<button data-testid="capital-trail-close" onClick={() => setTrail(null)} style={{ background: "transparent", color: C.muted, border: `1px solid ${C.border}`, borderRadius: 4, padding: "2px 8px", fontFamily: MONO, fontSize: 10, cursor: "pointer" }}>Close</button>}>
          {trailLoading ? <div style={{ color: C.muted, fontFamily: MONO }}>Reconstructing…</div> : (
            <div style={{ fontFamily: MONO, fontSize: 12 }}>
              <div style={{ color: C.sub, marginBottom: 8 }}>tx {shortHash(trail?.tx_hash)} · legs {trail?.leg_count ?? 0} · realized P/L {trail?.realized_pl_usd != null ? fmtUsd(trail.realized_pl_usd) : "—"}</div>
              {!trail?.ok && <div style={{ color: C.yellow }}>{trail?.reason}</div>}
              {trail?.legs?.length ? (
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead><tr style={{ color: C.muted, textAlign: "left" }}>{["#", "Token", "Amount", "Dir", "From", "To"].map((h) => <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.borderSoft}` }}>{h}</th>)}</tr></thead>
                  <tbody>
                    {trail.legs.map((l, i) => (
                      <tr key={i}>
                        <td style={{ padding: "4px 8px" }}>{i + 1}</td>
                        <td style={{ padding: "4px 8px" }}>{l.token}</td>
                        <td style={{ padding: "4px 8px" }}>{fmtNum(l.amount, 8)}</td>
                        <td style={{ padding: "4px 8px" }}><Tag color={l.direction === "in" ? C.green : l.direction === "out" ? C.red : C.muted}>{l.direction}</Tag></td>
                        <td style={{ padding: "4px 8px" }}>{shortAddr(l.from)}</td>
                        <td style={{ padding: "4px 8px" }}>{shortAddr(l.to)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (trail?.ok && <div style={{ color: C.muted }}>No ERC-20 legs (native-only or not indexed).</div>)}
            </div>
          )}
        </Panel>
      )}

      {/* Venue / pair stats */}
      <Panel title="Per-Venue / Pair Statistics" testid="capital-venue-stats-panel">
        {stats?.by_venue?.length ? (
          <table data-testid="capital-venue-stats-table" style={{ width: "100%", borderCollapse: "collapse", fontFamily: MONO, fontSize: 12 }}>
            <thead><tr style={{ color: C.muted, textAlign: "left" }}>{["Venue", "Tx", "Success", "Failed", "Fees (ETH)", "Top Pairs"].map((h) => <th key={h} style={{ padding: "6px 8px", borderBottom: `1px solid ${C.borderSoft}` }}>{h}</th>)}</tr></thead>
            <tbody>
              {stats.by_venue.map((v) => (
                <tr key={v.venue}>
                  <td style={{ padding: "6px 8px" }}>{v.venue}</td>
                  <td style={{ padding: "6px 8px" }}>{v.tx_count}</td>
                  <td style={{ padding: "6px 8px", color: C.green }}>{v.success}</td>
                  <td style={{ padding: "6px 8px", color: C.red }}>{v.failed}</td>
                  <td style={{ padding: "6px 8px" }}>{fmtNum(v.total_fee_eth, 8)}</td>
                  <td style={{ padding: "6px 8px" }}>{Object.keys(v.pairs || {}).join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div data-testid="capital-no-venue-stats" style={{ color: C.muted, fontFamily: MONO, fontSize: 12 }}>
            No DEX activity yet{stats && !stats.source_ok ? ` (${stats.source_note || "tx source unavailable"})` : ""}.
          </div>
        )}
      </Panel>
    </div>
  );
}
