/**
 * ArbiCore X — UI v2 · Portfolio page (Slice 4)
 * Sub-rail: Positions · Balances · Transfers · Deployable · Treasury · Ledger · Exposure · Allocation
 * All sub-sections read composed portfolio endpoints. Reuses Primitives.
 */
import { useEffect, useState } from "react";
import { Route, Routes, NavLink, Navigate } from "react-router-dom";
import { v2Api } from "@/v2/lib/api";
import { MetricStat, fmtUsd, fmtBps, fmtPct } from "@/v2/components/Primitives";

const SUB = [
  { key: "positions", label: "Positions" },
  { key: "balances", label: "Balances" },
  { key: "transfers", label: "Transfers" },
  { key: "deployable", label: "Deployable" },
  { key: "treasury", label: "Treasury" },
  { key: "ledger", label: "Ledger" },
  { key: "exposure", label: "Exposure" },
  { key: "allocation", label: "Allocation" },
];

function SubNav() {
  return (
    <nav data-testid="v2-portfolio-subnav" style={{ display: "flex", flexWrap: "wrap", gap: 4, borderBottom: "1px solid var(--v2-border-subtle)", marginBottom: 16, paddingBottom: 8 }}>
      {SUB.map((s) => (
        <NavLink
          key={s.key}
          to={`/v2/portfolio/${s.key}`}
          data-testid={`v2-portfolio-tab-${s.key}`}
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

/** Honest banner shown when a data source is not wired / unavailable. */
function UnavailableNote({ data, testid }) {
  if (!data || data.available !== false) return null;
  return (
    <div data-testid={testid} style={{ border: "1px dashed var(--v2-verdict-no-soft)", background: "var(--v2-bg-panel)", color: "var(--v2-verdict-no-soft)", padding: "8px 12px", borderRadius: 2, marginBottom: 12, fontFamily: "var(--v2-font-mono)", fontSize: 11, letterSpacing: 0.5 }}>
      UNAVAILABLE — {data.unavailable_reason || "data source not wired yet"}. Values shown as "—" (not $0).
    </div>
  );
}

function useAsync(fn, deps = []) {
  const [s, setS] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let alive = true;
    setS((p) => ({ ...p, loading: true }));
    fn().then((d) => alive && setS({ loading: false, data: d, error: null }))
        .catch((e) => alive && setS({ loading: false, data: null, error: e }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return s;
}

const SIDE_COLOR = { LONG: "var(--v2-verdict-go)", SHORT: "var(--v2-verdict-no-hard)", LP: "var(--v2-accent-base)" };
const TRANSFER_STATE = { SETTLED: "var(--v2-verdict-go)", PENDING: "var(--v2-verdict-no-soft)", FAILED: "var(--v2-verdict-no-hard)" };
const VAULT_KIND = { COLD: "var(--v2-verdict-go)", HOT: "var(--v2-accent-base)", MULTISIG: "var(--v2-regime-active)", EXCHANGE: "var(--v2-text-secondary)" };
const LEDGER_KIND = { PNL: "var(--v2-accent-base)", FEE: "var(--v2-verdict-no-soft)", TRANSFER: "var(--v2-text-secondary)", DEPOSIT: "var(--v2-verdict-go)", WITHDRAW: "var(--v2-verdict-no-hard)" };
const ALLOC_STATUS = { UNDER: "var(--v2-verdict-no-soft)", OVER: "var(--v2-accent-base)", ON_TARGET: "var(--v2-verdict-go)" };

const TH = { textAlign: "left", padding: "8px 10px", color: "var(--v2-text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: 1, textTransform: "uppercase", borderBottom: "1px solid var(--v2-border-subtle)" };
const TD = { padding: "6px 10px" };
const TABLE = { width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 };
const CARD = { border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2 };

function pnlColor(n) {
  if (n == null) return "var(--v2-text-muted)";
  return n >= 0 ? "var(--v2-verdict-go)" : "var(--v2-verdict-no-hard)";
}

function signedUsd(n) {
  if (n == null) return "—";
  const s = fmtUsd(Math.abs(n));
  return `${n >= 0 ? "+" : "-"}${s}`;
}

/* -------------------- Positions -------------------- */
function Positions() {
  const [venue, setVenue] = useState("ALL");
  const [side, setSide] = useState("ALL");
  const { loading, data } = useAsync(() => v2Api.positions({ venue, side }), [venue, side]);
  const VENUES = ["ALL", "binance", "kucoin", "okx", "bybit", "hyperliquid", "uniswap-v3"];
  const SIDES = ["ALL", "LONG", "SHORT", "LP"];
  return (
    <section data-testid="v2-portfolio-positions">
      <UnavailableNote data={data} testid="v2-portfolio-positions-unavailable" />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div className="v2-panel" data-testid="v2-portfolio-positions-summary-total"><MetricStat label="Positions" value={data?.total ?? "—"} /></div>
        <div className="v2-panel"><MetricStat label="Notional" value={fmtUsd(data?.total_size_usd)} /></div>
        <div className="v2-panel">
          <div className="v2-num" style={{ fontSize: 22, color: pnlColor(data?.total_upnl_usd) }}>{signedUsd(data?.total_upnl_usd)}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Unrealised PnL</div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Venue</span>
        {VENUES.map((v) => (
          <button key={v} onClick={() => setVenue(v)} data-testid={`v2-portfolio-positions-filter-venue-${v}`}
                  style={{ padding: "3px 10px", border: `1px solid ${venue === v ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`, background: venue === v ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)", color: venue === v ? "var(--v2-accent-base)" : "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer" }}>{v}</button>
        ))}
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", margin: "0 4px 0 12px" }}>Side</span>
        {SIDES.map((s) => (
          <button key={s} onClick={() => setSide(s)} data-testid={`v2-portfolio-positions-filter-side-${s}`}
                  style={{ padding: "3px 10px", border: `1px solid ${side === s ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`, background: side === s ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)", color: side === s ? "var(--v2-accent-base)" : "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer" }}>{s}</button>
        ))}
      </div>
      <div style={CARD}>
        <table style={TABLE} data-testid="v2-portfolio-positions-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Position", "Venue", "Market", "Side", "Size", "Entry", "Mark", "uPnL bps", "uPnL"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {loading && (<tr><td colSpan={9} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).length === 0 && (
              <tr><td colSpan={9} style={{ padding: 0 }}><div className="v2-empty" style={{ margin: 12 }}>{"> 0 positions match the current filter."}</div></td></tr>
            )}
            {!loading && (data?.items || []).map((p) => (
              <tr key={p.id} data-testid={`v2-portfolio-position-${p.id}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{p.id}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{p.venue}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{p.market}</td>
                <td style={TD}><StateTag value={p.side} map={SIDE_COLOR} /></td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{fmtUsd(p.size_usd)}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{p.entry_price?.toLocaleString?.() ?? p.entry_price}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{p.mark_price?.toLocaleString?.() ?? p.mark_price}</td>
                <td style={{ ...TD, color: pnlColor(p.upnl_bps) }}>{fmtBps(p.upnl_bps)}</td>
                <td style={{ ...TD, color: pnlColor(p.upnl_usd) }}>{signedUsd(p.upnl_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------- Balances -------------------- */
function Balances() {
  const { loading, data } = useAsync(() => v2Api.balances());
  return (
    <section data-testid="v2-portfolio-balances">
      <UnavailableNote data={data} testid="v2-portfolio-balances-unavailable" />
      <div className="v2-panel" style={{ marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div className="v2-panel__title">Total holdings</div>
          <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-accent-base)" }}>{fmtUsd(data?.total_usd)}</div>
        </div>
        <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{data?.total ?? "—"} rows</div>
      </div>
      <div style={CARD}>
        <table style={TABLE} data-testid="v2-portfolio-balances-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Venue", "Asset", "Total", "Available", "In orders", "USD value"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {loading && (<tr><td colSpan={6} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).map((b, i) => (
              <tr key={`${b.venue}-${b.asset}-${i}`} data-testid={`v2-portfolio-balance-${b.venue}-${b.asset}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{b.venue}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{b.asset}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{b.total}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{b.available}</td>
                <td style={{ ...TD, color: b.in_orders > 0 ? "var(--v2-accent-base)" : "var(--v2-text-muted)" }}>{b.in_orders}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{fmtUsd(b.usd_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------- Transfers -------------------- */
function Transfers() {
  const [status, setStatus] = useState("ALL");
  const { loading, data } = useAsync(() => v2Api.transfers({ status, limit: 100 }), [status]);
  const OPTS = ["ALL", "PENDING", "SETTLED", "FAILED"];
  return (
    <section data-testid="v2-portfolio-transfers">
      <UnavailableNote data={data} testid="v2-portfolio-transfers-unavailable" />
      <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center" }}>
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Status</span>
        {OPTS.map((s) => (
          <button key={s} onClick={() => setStatus(s)} data-testid={`v2-portfolio-transfers-filter-${s}`}
                  style={{ padding: "3px 10px", border: `1px solid ${status === s ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`, background: status === s ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)", color: status === s ? "var(--v2-accent-base)" : "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer" }}>{s}</button>
        ))}
      </div>
      <div style={CARD}>
        <table style={TABLE} data-testid="v2-portfolio-transfers-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Transfer", "Kind", "From", "To", "Asset", "Amount", "USD", "Status", "Settled"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {loading && (<tr><td colSpan={9} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).length === 0 && (
              <tr><td colSpan={9} style={{ padding: 0 }}><div className="v2-empty" style={{ margin: 12 }}>{"> 0 transfers match the current filter."}</div></td></tr>
            )}
            {!loading && (data?.items || []).map((t) => (
              <tr key={t.id} data-testid={`v2-portfolio-transfer-${t.id}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{t.id}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{t.kind}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{t.from}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{t.to}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{t.asset}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{t.amount}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{fmtUsd(t.usd_value)}</td>
                <td style={TD}><StateTag value={t.status} map={TRANSFER_STATE} /></td>
                <td style={{ ...TD, color: "var(--v2-text-muted)" }}>{t.settled_at ? t.settled_at.slice(11, 19) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------- Deployable -------------------- */
function Deployable() {
  const { loading, data } = useAsync(() => v2Api.deployable());
  if (loading) return <div className="v2-empty">Loading deployable capital…</div>;
  return (
    <section data-testid="v2-portfolio-deployable">
      <UnavailableNote data={data} testid="v2-portfolio-deployable-unavailable" />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 12 }}>
        <div className="v2-panel" data-testid="v2-portfolio-deployable-total">
          <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-verdict-go)" }}>{fmtUsd(data?.total_deployable_usd)}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Deployable</div>
        </div>
        <div className="v2-panel">
          <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-text-strong)" }}>{fmtUsd(data?.total_utilised_usd)}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Utilised</div>
        </div>
        <div className="v2-panel">
          <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-accent-base)" }}>{fmtPct(data?.utilisation_pct)}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Utilisation</div>
        </div>
        <div className="v2-panel">
          <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-text-strong)" }}>{fmtUsd(data?.total_capital_usd)}</div>
          <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>Total capital</div>
        </div>
      </div>
      <div style={CARD}>
        <table style={TABLE} data-testid="v2-portfolio-deployable-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Venue", "Deployable", "Utilised", "Utilisation"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {(data?.per_venue || []).map((v) => (
              <tr key={v.venue} data-testid={`v2-portfolio-deployable-${v.venue}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{v.venue}</td>
                <td style={{ ...TD, color: "var(--v2-verdict-go)" }}>{fmtUsd(v.deployable_usd)}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{fmtUsd(v.utilised_usd)}</td>
                <td style={{ ...TD, color: v.utilisation_pct > 0.75 ? "var(--v2-verdict-no-soft)" : "var(--v2-text-secondary)" }}>{fmtPct(v.utilisation_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------- Treasury -------------------- */
function Treasury() {
  const { loading, data } = useAsync(() => v2Api.treasury());
  return (
    <section data-testid="v2-portfolio-treasury">
      <UnavailableNote data={data} testid="v2-portfolio-treasury-unavailable" />
      <div className="v2-panel" style={{ marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div className="v2-panel__title">Treasury total</div>
          <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-accent-base)" }}>{fmtUsd(data?.total_usd)}</div>
        </div>
        <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{data?.vaults?.length ?? 0} vaults</div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
        {loading && <div className="v2-empty">Loading…</div>}
        {!loading && (data?.vaults || []).map((v) => (
          <div key={v.vault} className="v2-panel" data-testid={`v2-portfolio-vault-${v.vault}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="v2-panel__title">{v.vault}</div>
              <StateTag value={v.kind} map={VAULT_KIND} />
            </div>
            <div className="v2-num" style={{ fontSize: 22, color: "var(--v2-text-strong)" }}>{fmtUsd(v.usd_value)}</div>
            <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1 }}>
              {v.custody} · {v.assets} assets · reconciled {v.last_reconciled_at?.slice(11, 19)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* -------------------- Ledger -------------------- */
function Ledger() {
  const [kind, setKind] = useState("ALL");
  const { loading, data } = useAsync(() => v2Api.ledger({ kind, limit: 100 }), [kind]);
  const OPTS = ["ALL", "PNL", "FEE", "TRANSFER", "DEPOSIT", "WITHDRAW"];
  return (
    <section data-testid="v2-portfolio-ledger">
      <UnavailableNote data={data} testid="v2-portfolio-ledger-unavailable" />
      <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Kind</span>
        {OPTS.map((k) => (
          <button key={k} onClick={() => setKind(k)} data-testid={`v2-portfolio-ledger-filter-${k}`}
                  style={{ padding: "3px 10px", border: `1px solid ${kind === k ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`, background: kind === k ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)", color: kind === k ? "var(--v2-accent-base)" : "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, borderRadius: 2, cursor: "pointer" }}>{k}</button>
        ))}
      </div>
      <div style={CARD}>
        <table style={TABLE} data-testid="v2-portfolio-ledger-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Entry", "Kind", "Ref", "Delta", "Balance", "At", "Note"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {loading && (<tr><td colSpan={7} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).map((e) => (
              <tr key={e.id} data-testid={`v2-portfolio-ledger-${e.id}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{e.id}</td>
                <td style={TD}><StateTag value={e.kind} map={LEDGER_KIND} /></td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{e.ref}</td>
                <td style={{ ...TD, color: pnlColor(e.delta_usd) }}>{signedUsd(e.delta_usd)}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{fmtUsd(e.balance_usd)}</td>
                <td style={{ ...TD, color: "var(--v2-text-muted)" }}>{e.at?.slice(11, 19)}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{e.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* -------------------- Exposure -------------------- */
function ExposureBar({ pct }) {
  const w = Math.max(0, Math.min(1, pct)) * 100;
  return (
    <div style={{ width: 120, height: 6, background: "var(--v2-bg-panel)", borderRadius: 2, border: "1px solid var(--v2-border-subtle)", overflow: "hidden" }}>
      <div style={{ width: `${w}%`, height: "100%", background: "var(--v2-accent-base)" }} />
    </div>
  );
}

function Exposure() {
  const { loading, data } = useAsync(() => v2Api.exposure());
  return (
    <section data-testid="v2-portfolio-exposure">
      <UnavailableNote data={data} testid="v2-portfolio-exposure-unavailable" />
      <div className="v2-panel" style={{ marginBottom: 12 }}>
        <div className="v2-panel__title">Total exposure</div>
        <div className="v2-num" style={{ fontSize: 22, color: "var(--v2-accent-base)" }}>{fmtUsd(data?.total_usd)}</div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 12 }}>
        <div style={CARD} data-testid="v2-portfolio-exposure-by-asset">
          <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>By asset</div>
          <table style={TABLE}>
            <tbody>
              {loading && (<tr><td style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
              {!loading && (data?.by_asset || []).map((a) => (
                <tr key={a.asset} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                  <td style={{ ...TD, color: "var(--v2-text-strong)", width: 80 }}>{a.asset}</td>
                  <td style={TD}><ExposureBar pct={a.pct} /></td>
                  <td style={{ ...TD, color: "var(--v2-text-primary)", width: 60 }}>{fmtPct(a.pct)}</td>
                  <td style={{ ...TD, color: "var(--v2-text-secondary)", width: 100 }}>{fmtUsd(a.usd_value)}</td>
                  <td style={{ ...TD, color: pnlColor(a.delta_24h_pct), width: 80 }}>{a.delta_24h_pct == null ? "—" : `${(a.delta_24h_pct * 100).toFixed(2)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={CARD} data-testid="v2-portfolio-exposure-by-chain">
          <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>By chain</div>
          <table style={TABLE}>
            <tbody>
              {loading && (<tr><td style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
              {!loading && (data?.by_chain || []).map((c) => (
                <tr key={c.chain} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                  <td style={{ ...TD, color: "var(--v2-text-strong)", width: 90 }}>{c.chain}</td>
                  <td style={TD}><ExposureBar pct={c.pct} /></td>
                  <td style={{ ...TD, color: "var(--v2-text-primary)", width: 60 }}>{fmtPct(c.pct)}</td>
                  <td style={{ ...TD, color: "var(--v2-text-secondary)", width: 100 }}>{fmtUsd(c.usd_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/* -------------------- Allocation -------------------- */
function Allocation() {
  const { loading, data } = useAsync(() => v2Api.allocation());
  return (
    <section data-testid="v2-portfolio-allocation">
      <UnavailableNote data={data} testid="v2-portfolio-allocation-unavailable" />
      <div className="v2-panel" style={{ marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div className="v2-panel__title">Target vs actual</div>
          <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>Target {fmtUsd(data?.total_target_usd)} · Actual {fmtUsd(data?.total_actual_usd)}</div>
        </div>
      </div>
      <div style={CARD}>
        <table style={TABLE} data-testid="v2-portfolio-allocation-table">
          <thead><tr style={{ background: "var(--v2-bg-panel)" }}>
            {["Bucket", "Target %", "Actual %", "Target", "Actual", "Delta", "Status"].map((h) => <th key={h} style={TH}>{h}</th>)}
          </tr></thead>
          <tbody>
            {loading && (<tr><td colSpan={7} style={{ padding: 16, color: "var(--v2-text-muted)" }}>Loading…</td></tr>)}
            {!loading && (data?.items || []).map((a) => (
              <tr key={a.bucket} data-testid={`v2-portfolio-allocation-${a.bucket}`} style={{ borderBottom: "1px solid var(--v2-border-subtle)" }}>
                <td style={{ ...TD, color: "var(--v2-text-strong)" }}>{a.bucket}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{fmtPct(a.target_pct)}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{fmtPct(a.actual_pct)}</td>
                <td style={{ ...TD, color: "var(--v2-text-secondary)" }}>{fmtUsd(a.target_usd)}</td>
                <td style={{ ...TD, color: "var(--v2-text-primary)" }}>{fmtUsd(a.actual_usd)}</td>
                <td style={{ ...TD, color: pnlColor(a.delta_usd) }}>{signedUsd(a.delta_usd)}</td>
                <td style={TD}><StateTag value={a.status} map={ALLOC_STATUS} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function PortfolioPage() {
  return (
    <section data-testid="v2-portfolio">
      <h1 className="v2-page__title">Portfolio</h1>
      <p className="v2-page__lede">Positions · Balances · Transfers · Deployable · Treasury · Ledger · Exposure · Allocation.</p>
      <SubNav />
      <Routes>
        <Route index element={<Navigate to="positions" replace />} />
        <Route path="positions" element={<Positions />} />
        <Route path="balances" element={<Balances />} />
        <Route path="transfers" element={<Transfers />} />
        <Route path="deployable" element={<Deployable />} />
        <Route path="treasury" element={<Treasury />} />
        <Route path="ledger" element={<Ledger />} />
        <Route path="exposure" element={<Exposure />} />
        <Route path="allocation" element={<Allocation />} />
      </Routes>
    </section>
  );
}
