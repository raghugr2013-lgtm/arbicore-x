/**
 * ArbiCore X — UI v2 · Per-opportunity Execution Timeline (Phase 8)
 *
 * Read-only composition view of every audit collection touched by an
 * opportunity across its full institutional lifecycle:
 *
 *   Discovery → Ranking → Confidence → Certification → Lifecycle/FSM →
 *   Simulation → Approval / Rejection → Execution Planning →
 *   Broadcast (or SHADOW) → Settlement → Learning update →
 *   Calibration update → Adaptive Weight update → Evidence Bundle →
 *   Final Outcome → Archive.
 *
 * Data source: GET /api/arbicore/opportunities/{id}/timeline — a pure
 * server-side join across existing audit collections.  This component
 * introduces no new persistence, no new workflow.
 */
import { useEffect, useState } from "react";
import { v2Api } from "@/v2/lib/api";

const KIND_LABEL = {
  opportunity_state: "Lifecycle",
  discovery:         "Discovery",
  execution_plan:    "Execution Planning",
  mode_transition:   "Mode / Ladder",
  capital_policy:    "Capital Policy",
  kill_switch:       "Kill Switch",
  evidence:          "Evidence Bundle",
  simulation:        "Simulation",
  broadcast:         "Broadcast Decision",
  settlement:        "Settlement",
  learning:          "Learning Update",
  calibration:       "Calibration Update",
  adaptive_weights:  "Adaptive Weight Update",
  wallet_registry:   "Wallet Registry",
  archive:           "Archive",
};

const KIND_COLOR = {
  opportunity_state: "var(--v2-accent-base)",
  discovery:         "var(--v2-text-secondary)",
  execution_plan:    "var(--v2-verdict-go)",
  mode_transition:   "var(--v2-text-secondary)",
  capital_policy:    "var(--v2-text-secondary)",
  kill_switch:       "var(--v2-verdict-no-hard)",
  evidence:          "var(--v2-accent-base)",
  simulation:        "var(--v2-text-secondary)",
  broadcast:         "var(--v2-accent-base)",
  settlement:        "var(--v2-verdict-go)",
  learning:          "var(--v2-text-secondary)",
  calibration:       "var(--v2-text-secondary)",
  adaptive_weights:  "var(--v2-text-secondary)",
  wallet_registry:   "var(--v2-text-secondary)",
  archive:           "var(--v2-text-muted)",
};

function fmtTs(v) {
  if (!v) return "—";
  try { return new Date(v).toISOString().replace("T", " ").replace("Z", " UTC"); }
  catch { return String(v); }
}

function summarisePayload(kind, payload) {
  if (!payload || typeof payload !== "object") return "";
  if (kind === "opportunity_state") {
    return `status=${payload.status} · conf=${payload.confidence_score} · ${payload.source_data_quality}`;
  }
  if (kind === "execution_plan") {
    return `plan_id=${payload.plan_id || payload.id || "—"} · ${payload.strategy || payload.chain || ""}`;
  }
  if (kind === "evidence") {
    return `bundle=${payload.bundle_id || payload.cycle_id || "—"} · verify=${payload.verification_status || "?"}`;
  }
  if (kind === "mode_transition") {
    return `${payload.from_mode ?? payload.from ?? "?"} → ${payload.to_mode ?? payload.to ?? payload.mode ?? "?"}${payload.strategy ? " · " + payload.strategy : ""}`;
  }
  if (kind === "capital_policy") {
    return `strategy=${payload.strategy || "?"} · action=${payload.action || "update"}`;
  }
  if (kind === "kill_switch") {
    return `engaged=${payload.engaged ? "YES" : "no"} · by=${payload.actor || "system"}`;
  }
  if (kind === "discovery") {
    return `status=${payload.status || "?"} · profit=$${payload.net_profit_usd ?? "—"}`;
  }
  // Generic fallback — first few interesting keys.
  const keys = Object.keys(payload).filter(
    (k) => !["_id", "opportunity_id"].includes(k)
  ).slice(0, 3);
  return keys.map((k) => `${k}=${JSON.stringify(payload[k]).slice(0, 32)}`).join(" · ");
}

export function ExecutionTimeline({ opportunityId }) {
  const [state, setState] = useState({ loading: true, events: [], error: null });

  useEffect(() => {
    let cancelled = false;
    if (!opportunityId) return;
    setState({ loading: true, events: [], error: null });
    v2Api.opportunityTimeline(opportunityId)
      .then((d) => { if (!cancelled) setState({ loading: false, events: d.events || [], error: null }); })
      .catch((e) => { if (!cancelled) setState({ loading: false, events: [], error: String(e) }); });
    return () => { cancelled = true; };
  }, [opportunityId]);

  if (state.loading) {
    return <div className="v2-empty" data-testid="v2-timeline-loading">{"> Loading execution timeline…"}</div>;
  }
  if (state.error) {
    return <div className="v2-empty" data-testid="v2-timeline-error">{`> timeline error: ${state.error}`}</div>;
  }
  if (state.events.length === 0) {
    return (
      <div className="v2-empty" data-testid="v2-timeline-empty">
        {"> No lifecycle events recorded yet.\n> Timeline populates automatically as this opportunity moves through the pipeline."}
      </div>
    );
  }

  return (
    <div data-testid="v2-timeline">
      <div style={{
        color: "var(--v2-text-secondary)", fontSize: 11, letterSpacing: 1,
        textTransform: "uppercase", fontFamily: "var(--v2-font-mono)", margin: "8px 0 6px",
      }}>
        {state.events.length} events · newest first
      </div>
      <div style={{ position: "relative", paddingLeft: 14 }}>
        <div style={{
          position: "absolute", left: 5, top: 6, bottom: 6, width: 1,
          background: "var(--v2-border-subtle)",
        }} />
        {state.events.map((ev, i) => {
          const label = KIND_LABEL[ev.kind] || ev.kind;
          const color = KIND_COLOR[ev.kind] || "var(--v2-text-secondary)";
          const summary = summarisePayload(ev.kind, ev.payload);
          return (
            <div key={i} style={{ position: "relative", padding: "8px 0 10px 8px", borderBottom: "1px solid var(--v2-border-subtle)" }}
                 data-testid={`v2-timeline-event-${i}`}>
              <div style={{
                position: "absolute", left: -13, top: 12, width: 9, height: 9,
                borderRadius: 9, background: color, border: "2px solid var(--v2-bg-surface)",
              }} />
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span style={{ color, fontFamily: "var(--v2-font-mono)", fontSize: 11, letterSpacing: 1, textTransform: "uppercase" }}>
                  {label}
                </span>
                <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>
                  {fmtTs(ev.at)}
                </span>
              </div>
              {summary && (
                <div style={{ color: "var(--v2-text-secondary)", fontFamily: "var(--v2-font-mono)", fontSize: 11, marginTop: 3, wordBreak: "break-all" }}>
                  {summary}
                </div>
              )}
              <div style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10, marginTop: 2 }}>
                collection: {ev.collection}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
