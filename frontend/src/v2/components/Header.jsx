/**
 * ArbiCore X — UI v2 · Header (Slice 0)
 *
 * 7-slot top bar mirroring the Binance Desktop pattern (design_language.md §4).
 * Slot layout (left → right):
 *   1. Brand mark (locked to rail width for visual alignment)
 *   2. Section breadcrumb — reflects current /v2/... route
 *   3. Global search / palette entry (⌘K)
 *   4. Regime chip (live, populated in Slice 1)
 *   5. System status chip (live, populated in Slice 1)
 *   6. Alert badge (populated in Slice 1)
 *   7. User / logout
 *
 * Slice 0 responsibility: get the layout correct. Live data wiring for
 * slots 4–6 is deferred to Slice 1 alongside the shared component library.
 */
import { Search } from "lucide-react";
import { useLocation } from "react-router-dom";
import { NAV_SECTIONS } from "@/v2/lib/nav";

function useSectionForPath(pathname) {
  const match = NAV_SECTIONS.find((s) => {
    if (s.end) return pathname === s.path;
    return pathname === s.path || pathname.startsWith(`${s.path}/`);
  });
  return match || NAV_SECTIONS[0];
}

export function Header({ username, onLogout }) {
  const { pathname } = useLocation();
  const section = useSectionForPath(pathname);

  return (
    <header className="v2-header" data-testid="v2-header">
      <div className="v2-header__slot v2-header__slot--brand" data-testid="v2-header-brand">
        ARBICORE
      </div>

      <div className="v2-header__slot" data-testid="v2-header-breadcrumb">
        <span style={{ color: "var(--v2-text-muted)", fontSize: 11, letterSpacing: 1.5, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)" }}>
          {section.label}
        </span>
      </div>

      <div className="v2-header__slot v2-header__slot--grow" data-testid="v2-header-search">
        <button
          type="button"
          data-testid="v2-header-palette-trigger"
          disabled
          title="Command palette (⌘K) — activates in Slice 1"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 10px",
            background: "var(--v2-bg-panel)",
            border: "1px solid var(--v2-border-subtle)",
            color: "var(--v2-text-muted)",
            fontFamily: "var(--v2-font-mono)",
            fontSize: 12,
            borderRadius: 2,
            cursor: "not-allowed",
            width: 320,
            maxWidth: "60%",
            justifyContent: "flex-start",
          }}
        >
          <Search size={14} />
          <span>Search assets, venues, opportunities…</span>
          <span className="v2-header__kbd" style={{ marginLeft: "auto" }}>⌘K</span>
        </button>
      </div>

      <div className="v2-header__slot" data-testid="v2-header-regime">
        <span className="v2-header__chip" title="Market regime — live in Slice 1">
          <span style={{ width: 6, height: 6, background: "var(--v2-regime-calm)", borderRadius: "50%" }} />
          REGIME · —
        </span>
      </div>

      <div className="v2-header__slot" data-testid="v2-header-status">
        <span className="v2-header__chip v2-header__chip--accent" title="System heartbeat — live in Slice 1">
          UI V2 · SLICE 0
        </span>
      </div>

      <div className="v2-header__slot" data-testid="v2-header-alerts">
        <span className="v2-header__chip" title="Alerts — live in Slice 1">
          ALERTS · 0
        </span>
      </div>

      <div className="v2-header__slot" data-testid="v2-header-user">
        <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
          ◉ {username || "guest"}
        </span>
        {onLogout && (
          <button
            type="button"
            onClick={onLogout}
            data-testid="v2-header-logout"
            style={{
              marginLeft: 8,
              padding: "3px 8px",
              background: "transparent",
              border: "1px solid var(--v2-border-subtle)",
              color: "var(--v2-text-muted)",
              fontFamily: "var(--v2-font-mono)",
              fontSize: 10,
              letterSpacing: 1,
              cursor: "pointer",
              borderRadius: 2,
            }}
          >
            LOGOUT
          </button>
        )}
      </div>
    </header>
  );
}
