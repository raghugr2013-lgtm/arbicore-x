/**
 * ArbiCore X — UI v2 · Global keyboard shortcut hook (Slice 1)
 * ⌘K / Ctrl+K → openPalette
 * Esc          → closeAll
 * G+letter     → jump to section (Home=H, Discovery=D, Opportunities=O, Portfolio=P, Intelligence=I, Operations=N, Settings=S)
 * ?            → open shortcut reference (deferred to Slice 6)
 * A / R        → forwarded via onOpportunityAction (row-scoped)
 */
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

const SECTION_MAP = {
  h: "/v2",
  d: "/v2/discovery",
  o: "/v2/opportunities",
  p: "/v2/portfolio",
  i: "/v2/intelligence",
  n: "/v2/operations",
  s: "/v2/settings",
};

function isEditable(el) {
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

export function useKeyboardShortcuts({ onPalette, onEscape, onOpportunityAction } = {}) {
  const navigate = useNavigate();
  const gPending = useRef(false);
  const gTimeout = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if (isEditable(e.target)) {
        if (e.key === "Escape") onEscape && onEscape();
        return;
      }
      // ⌘K / Ctrl+K
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        onPalette && onPalette();
        return;
      }
      if (e.key === "Escape") {
        onEscape && onEscape();
        return;
      }
      // G+letter section jump
      if (gPending.current) {
        gPending.current = false;
        clearTimeout(gTimeout.current);
        const path = SECTION_MAP[e.key.toLowerCase()];
        if (path) {
          e.preventDefault();
          navigate(path);
        }
        return;
      }
      if (e.key === "g" || e.key === "G") {
        gPending.current = true;
        gTimeout.current = setTimeout(() => { gPending.current = false; }, 900);
        return;
      }
      // Opportunity actions
      if ((e.key === "a" || e.key === "A") && onOpportunityAction) {
        onOpportunityAction("approve");
        return;
      }
      if ((e.key === "r" || e.key === "R") && onOpportunityAction) {
        onOpportunityAction("reject");
        return;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, onPalette, onEscape, onOpportunityAction]);
}
