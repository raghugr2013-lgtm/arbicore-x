/**
 * ArbiCore X — UI v2 · Home page (Slice 0 preview)
 *
 * Slice 0 delivers three vitals cards that prove the backend delta is
 * wired end-to-end:
 *
 *   1. Regime — from GET /api/arbicore/dashboard/pulse (regime card)
 *   2. Opportunity vitals — from the same pulse response
 *   3. Deployable capital / anomalies — pointer to canonical endpoints
 *
 * Slice 1 replaces this with the full Pulse → Priorities → Vitals band
 * layout, universal opportunity cards, and the ⌘K palette.
 */
import { useEffect, useState } from "react";
import { v2Api } from "@/v2/lib/api";

function Card({ title, children, testid }) {
  return (
    <div className="v2-panel" data-testid={testid}>
      <div className="v2-panel__title">{title}</div>
      {children}
    </div>
  );
}

function useAsync(fn) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, data: null, error: null });
    fn()
      .then((data) => !cancelled && setState({ loading: false, data, error: null }))
      .catch((e) => !cancelled && setState({ loading: false, data: null, error: e }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return state;
}

export default function HomePage() {
  const pulse = useAsync(() => v2Api.pulse());
  const deck = useAsync(() => v2Api.deck(5));

  return (
    <section data-testid="v2-home">
      <h1 className="v2-page__title">Home</h1>
      <p className="v2-page__lede">
        Slice 0 preview — wired to <code className="v2-kbd">/api/arbicore/dashboard/pulse</code>{" "}
        and <code className="v2-kbd">/api/arbicore/dashboard/deck</code>. Full Pulse → Priorities → Vitals arrives in Slice 1.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 16 }}>
        <Card title="Regime" testid="v2-home-regime">
          {pulse.loading && <div className="v2-empty">Loading…</div>}
          {pulse.error && <div className="v2-empty">{"> Unable to reach backend. Endpoint may not be deployed yet."}</div>}
          {!pulse.loading && !pulse.error && (
            pulse.data?.regime ? (
              <div>
                <div className="v2-num" style={{ fontSize: 20, color: "var(--v2-text-strong)" }}>
                  {pulse.data.regime.regime || "—"}
                </div>
                <div style={{ color: "var(--v2-text-muted)", fontSize: 11, fontFamily: "var(--v2-font-mono)", marginTop: 4 }}>
                  confidence {(pulse.data.regime.confidence * 100).toFixed(0)}%
                  {pulse.data.regime.tags?.length ? ` · ${pulse.data.regime.tags.join(", ")}` : ""}
                </div>
              </div>
            ) : (
              <div className="v2-empty">{"> No regime snapshot yet."}</div>
            )
          )}
        </Card>

        <Card title="Opportunity vitals" testid="v2-home-vitals">
          {pulse.loading && <div className="v2-empty">Loading…</div>}
          {pulse.error && <div className="v2-empty">{"> Unable to reach backend."}</div>}
          {!pulse.loading && !pulse.error && (
            <div style={{ display: "flex", gap: 24 }}>
              <div>
                <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-text-strong)" }}>
                  {pulse.data?.opportunity_vitals?.total ?? 0}
                </div>
                <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", letterSpacing: 1, textTransform: "uppercase" }}>
                  total
                </div>
              </div>
              <div>
                <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-text-strong)" }}>
                  {Object.keys(pulse.data?.opportunity_vitals?.by_family || {}).length}
                </div>
                <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", letterSpacing: 1, textTransform: "uppercase" }}>
                  families
                </div>
              </div>
              <div>
                <div className="v2-num" style={{ fontSize: 24, color: "var(--v2-text-strong)" }}>
                  {pulse.data?.route_learning?.tracked_routes ?? 0}
                </div>
                <div style={{ color: "var(--v2-text-muted)", fontSize: 10, fontFamily: "var(--v2-font-mono)", letterSpacing: 1, textTransform: "uppercase" }}>
                  routes learned
                </div>
              </div>
            </div>
          )}
        </Card>

        <Card title="Priorities · fresh opportunities" testid="v2-home-deck">
          {deck.loading && <div className="v2-empty">Loading…</div>}
          {deck.error && <div className="v2-empty">{"> Unable to reach backend."}</div>}
          {!deck.loading && !deck.error && (
            deck.data?.fresh_opportunities_total ? (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {deck.data.fresh_opportunities.slice(0, 5).map((o) => (
                  <li
                    key={o.id}
                    data-testid={`v2-home-deck-item-${o.id}`}
                    style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "6px 0", borderBottom: "1px solid var(--v2-border-subtle)" }}
                  >
                    <span style={{ fontFamily: "var(--v2-font-mono)", fontSize: 12, color: "var(--v2-text-primary)" }}>
                      {o.opportunity_type || "—"} · {o.chain || "—"}
                    </span>
                    <span className="v2-num" style={{ fontSize: 12, color: "var(--v2-accent-base)" }}>
                      {(o.confidence * 100).toFixed(0)}%
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="v2-empty">{"> No fresh opportunities.\n> Scanners may be paused or gates are pruning routes."}</div>
            )
          )}
        </Card>
      </div>

      <div className="v2-panel" data-testid="v2-home-note">
        <div className="v2-panel__title">Slice 0 · what shipped</div>
        <ul style={{ margin: 0, paddingLeft: 20, color: "var(--v2-text-secondary)" }}>
          <li>Backend delta: 4 additive composed endpoints (see network tab).</li>
          <li>Feature flag: <code className="v2-kbd">REACT_APP_ENABLE_UI_V2</code> (build-time) + <code className="v2-kbd">?ui_v2=1</code> runtime override.</li>
          <li>Application shell: 48 px header · 64 px left rail · 7 canonical sections.</li>
          <li>Theme tokens: obsidian surfaces, amber accent, IBM Plex Mono + Archivo — scoped to <code className="v2-kbd">.ui-v2-root</code>.</li>
        </ul>
      </div>
    </section>
  );
}
