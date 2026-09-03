"""Phase-2 hardening · Stable, deterministic live-opportunity identifiers.

A live opportunity's IDENTITY is its route: (type, chain, symbol, buy-venue,
sell-venue, direction). The economic figures (price, spread, size) update every
tick but the identity does NOT. Keying on a random uuid per emission produced
(a) duplicate-key churn in the operator feed and (b) a different id for the same
opportunity on every refresh. This helper derives a STABLE id from the route so
the same opportunity keeps one identity end-to-end, and re-emissions update
rather than duplicate.
"""
from __future__ import annotations


def _slug(v: object) -> str:
    return str(v if v is not None else "?").strip().replace("/", "").replace(" ", "").lower()


def stable_live_id(*, opportunity_type: str, chain: str, symbol: str,
                   venue_buy: object = None, venue_sell: object = None) -> str:
    """Deterministic id for a live opportunity route (direction-aware)."""
    return (f"live:{_slug(opportunity_type)}:{_slug(chain)}:"
            f"{_slug(symbol)}:{_slug(venue_buy)}-{_slug(venue_sell)}")


__all__ = ["stable_live_id"]
