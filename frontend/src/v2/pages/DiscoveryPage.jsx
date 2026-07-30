/**
 * ArbiCore X — UI v2 · Discovery page (Slice 2)
 * Two-pane inbox: candidate list (left) + selected candidate detail (right).
 * Reuses filter-chip pattern from OpportunitiesPage; reuses Primitives.
 */
import { useEffect, useMemo, useState } from "react";
import { v2Api } from "@/v2/lib/api";
import { ConfidencePill, MetricStat } from "@/v2/components/Primitives";
import { toast } from "sonner";

const STATUS_OPTS = ["ALL", "NEW", "WATCHING", "PROMOTED", "DISMISSED"];
const KIND_OPTS = ["ALL", "asset", "venue_pair", "chain"];

function Chip({ active, onClick, children, testid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      style={{
        padding: "3px 10px",
        border: `1px solid ${active ? "var(--v2-accent-base)" : "var(--v2-border-subtle)"}`,
        background: active ? "var(--v2-accent-subtle)" : "var(--v2-bg-panel)",
        color: active ? "var(--v2-accent-base)" : "var(--v2-text-secondary)",
        fontFamily: "var(--v2-font-mono)",
        fontSize: 10,
        letterSpacing: 1,
        borderRadius: 2,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function StatusTag({ status }) {
  const map = {
    NEW: "var(--v2-regime-active)",
    WATCHING: "var(--v2-accent-base)",
    PROMOTED: "var(--v2-verdict-go)",
    DISMISSED: "var(--v2-text-muted)",
  };
  const color = map[status] || "var(--v2-text-muted)";
  return (
    <span
      style={{
        padding: "1px 6px",
        fontFamily: "var(--v2-font-mono)",
        fontSize: 9,
        letterSpacing: 1,
        border: `1px solid ${color}`,
        color,
        borderRadius: 2,
      }}
    >
      {status}
    </span>
  );
}

function Detail({ cand, onAction, busy }) {
  if (!cand) {
    return (
      <div className="v2-empty" data-testid="v2-discovery-detail-empty">
        {"> Select a candidate on the left to see details.\n> Every candidate is a source-scored asset, venue-pair or chain awaiting operator triage."}
      </div>
    );
  }
  const row = (k, v, mono) => (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--v2-border-subtle)" }}>
      <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11, letterSpacing: 1, textTransform: "uppercase" }}>{k}</span>
      <span style={{ color: "var(--v2-text-primary)", fontFamily: mono ? "var(--v2-font-mono)" : "var(--v2-font-body)", fontSize: 12 }}>{v}</span>
    </div>
  );
  return (
    <div data-testid={`v2-discovery-detail-${cand.id}`}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <div>
          <div style={{ color: "var(--v2-text-strong)", fontSize: 16, fontWeight: 600 }}>{cand.asset}</div>
          <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11, marginTop: 4 }}>
            {cand.kind} · {cand.chain} · from {cand.source}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ConfidencePill value={cand.score} label="SCORE" />
          <StatusTag status={cand.status} />
        </div>
      </div>
      <div style={{ background: "var(--v2-bg-panel)", border: "1px solid var(--v2-border-subtle)", padding: 12, marginBottom: 12, borderRadius: 2 }}>
        <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginBottom: 4 }}>Why surfaced</div>
        <div style={{ fontSize: 13 }}>{cand.why}</div>
      </div>
      {row("Signals", (cand.signals || []).join(", ") || "—", true)}
      {row("First seen", cand.seen_at, true)}

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <button
          onClick={() => onAction(cand.id, "watch")}
          disabled={busy}
          data-testid={`v2-discovery-action-watch-${cand.id}`}
          style={{ flex: 1, padding: "6px 10px", background: "transparent", color: "var(--v2-accent-base)", border: "1px solid var(--v2-accent-base)", fontFamily: "var(--v2-font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: 1.5, borderRadius: 2, cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.5 : 1 }}
        >
          WATCH
        </button>
        <button
          onClick={() => onAction(cand.id, "promote")}
          disabled={busy}
          data-testid={`v2-discovery-action-promote-${cand.id}`}
          style={{ flex: 1, padding: "6px 10px", background: "var(--v2-accent-base)", color: "var(--v2-accent-onSolid)", border: "1px solid var(--v2-accent-base)", fontFamily: "var(--v2-font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: 1.5, borderRadius: 2, cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.5 : 1 }}
        >
          PROMOTE
        </button>
        <button
          onClick={() => onAction(cand.id, "dismiss")}
          disabled={busy}
          data-testid={`v2-discovery-action-dismiss-${cand.id}`}
          style={{ flex: 1, padding: "6px 10px", background: "transparent", color: "var(--v2-verdict-no-hard)", border: "1px solid var(--v2-verdict-no-hard)", fontFamily: "var(--v2-font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: 1.5, borderRadius: 2, cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.5 : 1 }}
        >
          DISMISS
        </button>
      </div>
    </div>
  );
}

export default function DiscoveryPage() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState({});
  const [status, setStatus] = useState("ALL");
  const [kind, setKind] = useState("ALL");
  const [selectedId, setSelectedId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetch = async () => {
    setLoading(true);
    try {
      const r = await v2Api.discoveryCandidates({ status, kind, limit: 100 });
      setItems(r.items || []);
      setStats(r.stats || {});
      if (!r.items?.find((c) => c.id === selectedId)) setSelectedId(r.items?.[0]?.id || null);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetch(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [status, kind]);

  const selected = useMemo(() => items.find((c) => c.id === selectedId) || null, [items, selectedId]);

  const doAction = async (id, action) => {
    setBusy(true);
    try {
      await v2Api.discoveryAction(id, action);
      toast.success(`${action.toUpperCase()} · ${id}`);
      await fetch();
    } catch (e) { toast.error("Action failed"); }
    finally { setBusy(false); }
  };

  return (
    <section data-testid="v2-discovery">
      <h1 className="v2-page__title">Discovery</h1>
      <p className="v2-page__lede">
        Inbox of candidate assets, venue-pairs and chains surfaced from external sources.
      </p>

      <div style={{ display: "flex", gap: 20, marginBottom: 14 }} data-testid="v2-discovery-stats">
        <MetricStat value={stats.total ?? 0} label="total" testid="v2-discovery-stat-total" />
        <MetricStat value={stats.new ?? 0} label="new" testid="v2-discovery-stat-new" accent />
        <MetricStat value={stats.watching ?? 0} label="watching" testid="v2-discovery-stat-watching" />
        <MetricStat value={stats.promoted ?? 0} label="promoted" testid="v2-discovery-stat-promoted" />
        <MetricStat value={stats.dismissed ?? 0} label="dismissed" testid="v2-discovery-stat-dismissed" />
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14, alignItems: "center" }} data-testid="v2-discovery-filters">
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginRight: 4 }}>Status</span>
        {STATUS_OPTS.map((s) => (<Chip key={s} active={status === s} onClick={() => setStatus(s)} testid={`v2-discovery-filter-status-${s}`}>{s}</Chip>))}
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", marginLeft: 12, marginRight: 4 }}>Kind</span>
        {KIND_OPTS.map((k) => (<Chip key={k} active={kind === k} onClick={() => setKind(k)} testid={`v2-discovery-filter-kind-${k}`}>{k}</Chip>))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(320px, 420px) 1fr", gap: 12 }}>
        <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2, maxHeight: "70vh", overflowY: "auto" }} data-testid="v2-discovery-list">
          {loading && (<div style={{ padding: 14, color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>Loading…</div>)}
          {!loading && items.length === 0 && (
            <div className="v2-empty" style={{ margin: 12 }}>{"> 0 candidates match the current filters.\n> Broaden Status or Kind to see more."}</div>
          )}
          {!loading && items.map((c) => (
            <div
              key={c.id}
              data-testid={`v2-discovery-item-${c.id}`}
              onClick={() => setSelectedId(c.id)}
              style={{
                padding: "10px 12px",
                cursor: "pointer",
                background: selectedId === c.id ? "var(--v2-bg-selected)" : "transparent",
                borderBottom: "1px solid var(--v2-border-subtle)",
                borderLeft: selectedId === c.id ? "2px solid var(--v2-accent-base)" : "2px solid transparent",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "var(--v2-text-strong)", fontSize: 13, fontWeight: 500 }}>{c.asset}</span>
                <StatusTag status={c.status} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
                <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>{c.kind} · {c.chain}</span>
                <ConfidencePill value={c.score} label="SCORE" />
              </div>
            </div>
          ))}
        </div>
        <div style={{ border: "1px solid var(--v2-border-subtle)", background: "var(--v2-bg-surface)", borderRadius: 2, padding: 16 }} data-testid="v2-discovery-detail">
          <Detail cand={selected} onAction={doAction} busy={busy} />
        </div>
      </div>
    </section>
  );
}
