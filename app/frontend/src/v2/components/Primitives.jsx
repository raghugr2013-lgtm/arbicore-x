/**
 * ArbiCore X — UI v2 · Small state primitives (Slice 1)
 * VerdictBadge · ConfidencePill · FreshnessBadge · SafetyPill · MetricStat
 * All are dumb, tokens-driven, and reused across Home + Opportunities + Drawer.
 */

export function VerdictBadge({ verdict, testid }) {
  const norm = (verdict || "").toUpperCase();
  const map = {
    GO: { label: "GO", color: "var(--v2-verdict-go)" },
    SOFT_NO: { label: "SOFT NO", color: "var(--v2-verdict-no-soft)" },
    HARD_NO: { label: "HARD NO", color: "var(--v2-verdict-no-hard)" },
    UNVERIFIED: { label: "UNVERIFIED", color: "var(--v2-text-muted)" },
  };
  const spec = map[norm] || { label: norm || "—", color: "var(--v2-text-muted)" };
  return (
    <span
      data-testid={testid}
      style={{
        display: "inline-block",
        padding: "2px 8px",
        fontFamily: "var(--v2-font-mono)",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 1,
        color: spec.color,
        border: `1px solid ${spec.color}`,
        background: "transparent",
        borderRadius: 2,
      }}
    >
      {spec.label}
    </span>
  );
}

function bandColor(v, low, mid) {
  if (v >= 0.7) return "var(--v2-conf-high)";
  if (v >= 0.4) return "var(--v2-conf-mid)";
  return "var(--v2-conf-low)";
}

export function ConfidencePill({ value, label = "CONF", testid }) {
  // Truth rule: null/undefined → UNAVAILABLE ("—"), NOT a coerced 0.
  if (value == null || Number.isNaN(Number(value))) {
    return (
      <span
        data-testid={testid}
        title="No real assessment available"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "2px 8px",
          border: "1px dashed var(--v2-border-subtle)",
          background: "var(--v2-bg-panel)",
          borderRadius: 2,
          fontFamily: "var(--v2-font-mono)",
          fontSize: 10,
          letterSpacing: 1,
          color: "var(--v2-text-muted)",
        }}
      >
        <span>{label}</span>
        <span style={{ fontWeight: 700 }}>—</span>
      </span>
    );
  }
  const pct = Math.max(0, Math.min(1, Number(value)));
  const color = bandColor(pct);
  return (
    <span
      data-testid={testid}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "2px 8px",
        border: "1px solid var(--v2-border-subtle)",
        background: "var(--v2-bg-panel)",
        borderRadius: 2,
        fontFamily: "var(--v2-font-mono)",
        fontSize: 10,
        letterSpacing: 1,
      }}
    >
      <span style={{ color: "var(--v2-text-muted)" }}>{label}</span>
      <span style={{ color, fontWeight: 700 }}>{Math.round(pct * 100)}</span>
      <span
        aria-hidden="true"
        style={{
          display: "inline-block",
          width: 34,
          height: 4,
          background: "var(--v2-border-subtle)",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <span style={{ display: "block", width: `${pct * 100}%`, height: "100%", background: color }} />
      </span>
    </span>
  );
}

export function SafetyPill({ value, testid }) {
  return <ConfidencePill value={value} label="SAFE" testid={testid} />;
}

export function FreshnessBadge({ ageSeconds, testid }) {
  if (ageSeconds == null || Number.isNaN(Number(ageSeconds))) {
    return (
      <span data-testid={testid} style={{ fontFamily: "var(--v2-font-mono)", fontSize: 10, color: "var(--v2-text-muted)" }}>
        —
      </span>
    );
  }
  const age = Number(ageSeconds);
  let color = "var(--v2-fresh-fresh)";
  let label = `${age}s`;
  if (age > 60) { color = "var(--v2-fresh-stalled)"; label = `${Math.round(age / 60)}m`; }
  else if (age > 15) { color = "var(--v2-fresh-stale)"; }
  return (
    <span
      data-testid={testid}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontFamily: "var(--v2-font-mono)",
        fontSize: 10,
        color,
      }}
    >
      <span style={{ display: "inline-block", width: 6, height: 6, background: color, borderRadius: "50%" }} />
      {label} ago
    </span>
  );
}

export function MetricStat({ value, label, testid, accent }) {
  return (
    <div data-testid={testid} style={{ minWidth: 88 }}>
      <div className="v2-num" style={{ fontSize: 22, color: accent ? "var(--v2-accent-base)" : "var(--v2-text-strong)" }}>
        {value ?? "—"}
      </div>
      <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>
        {label}
      </div>
    </div>
  );
}

/** Number formatter used across cards + tables. */
export function fmtUsd(n) {
  if (n == null) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}k`;
  return `$${Number(n).toFixed(0)}`;
}

export function fmtPct(n) {
  if (n == null) return "—";
  return `${(Number(n) * 100).toFixed(2)}%`;
}

export function fmtBps(n) {
  if (n == null) return "—";
  return `${Number(n).toFixed(1)} bps`;
}

/** Data-provenance chip — SIMULATED / REAL / VERIFIED_REAL. */
export function ProvenanceChip({ value, testid }) {
  const norm = (value || "").toUpperCase();
  const map = {
    VERIFIED_REAL: { label: "VERIFIED", color: "var(--v2-verdict-go)" },
    REAL: { label: "REAL", color: "var(--v2-accent-base)" },
    SIMULATED: { label: "SIMULATED", color: "var(--v2-conf-mid)" },
    CONTAMINATED: { label: "CONTAMINATED", color: "var(--v2-verdict-no-hard)" },
    DEAD: { label: "DEAD", color: "var(--v2-verdict-no-hard)" },
  };
  const spec = map[norm] || { label: norm || "—", color: "var(--v2-text-muted)" };
  return (
    <span
      data-testid={testid}
      title={`Data provenance: ${norm || "unknown"}`}
      style={{
        display: "inline-block",
        padding: "1px 6px",
        fontFamily: "var(--v2-font-mono)",
        fontSize: 9,
        letterSpacing: 1,
        color: spec.color,
        border: `1px solid ${spec.color}`,
        background: "transparent",
        borderRadius: 2,
      }}
    >
      {spec.label}
    </span>
  );
}
