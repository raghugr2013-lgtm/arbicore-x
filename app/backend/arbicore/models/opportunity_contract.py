"""ArbiCore X — Opportunity Display Contract (single authoritative boundary).

Phase-2 Part A: the ONE place that translates a ``CanonicalOpportunity`` into
the operator-visible display contract. Every API surface (opportunities list,
opportunity detail, discovery feed, dashboard deck) delegates here so the
data-truth rules cannot drift between endpoints.

CORE INVARIANT (data-truth):
    DISCOVERED / UNVERIFIED opportunities must not expose economically
    authoritative values unless the evidence required for those values
    actually exists.

    * missing            -> None (UNAVAILABLE, rendered "—")   — never 0
    * unknown            -> None                                — never $0
    * unassessed risk    -> safety None                         — never SAFE 100
    * unassessed conf    -> confidence None                     — never CONF 0
    * unpriced           -> no profitability implied
    * invalid / absurd   -> rejected & surfaced via data_quality_flags,
                            never clamped to a "plausible" value
    * genuine 0          -> stays 0 ONLY when an assessment marker proves the
                            value was actually assessed
    * genuine negative   -> stays negative (a real loss is a real loss)

Provenance (REAL / VERIFIED_REAL) means the SOURCE DATA is real. It is NOT, by
itself, evidence that a risk score or a confidence score was ever computed, nor
that economics were validated. Those are orthogonal axes and are gated
independently here (this is the specific defect the newest validator exposed:
REAL-provenance discovery rows were showing SAFE 100 / CONF 0).

Pure / offline. No Mongo, no RPC, no network I/O.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .enums import OpportunityStatus


# --------------------------------------------------------------------------
# Plausibility bounds (env-overridable, fail-safe defaults).
# These REJECT & SURFACE absurd values — they never clamp a value into a
# "plausible" range (that would fabricate financial truth).
# --------------------------------------------------------------------------
def _cfg_f(key: str, default: float) -> float:
    try:
        v = float(os.environ.get(key, "") or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def max_plausible_return() -> float:
    """Fractional return (profit/capital) above which a value is implausible.

    Default 5.0 == +500%. A genuine flash-loan arb never returns 500% of the
    capital at risk; such a figure is a unit/mapping/borrow-size bug and must be
    surfaced as suspect, not shown as authoritative.
    """
    return _cfg_f("ARBICORE_MAX_PLAUSIBLE_RETURN", 5.0)


def max_uncontextualized_profit_usd() -> float:
    """Absolute profit above which — WITHOUT a positive capital figure to
    contextualise it — the value is treated as suspect (cannot be validated)."""
    return _cfg_f("ARBICORE_MAX_UNCONTEXTUALIZED_PROFIT_USD", 100_000.0)


# --------------------------------------------------------------------------
# Provenance / economic-state helpers (single source of truth).
# --------------------------------------------------------------------------
def provenance_str(opp) -> str:
    q = opp.source_data_quality
    return q.value if hasattr(q, "value") else str(q)


def is_real_provenance(opp) -> bool:
    """True only when backed by REAL / VERIFIED_REAL source data."""
    return provenance_str(opp) in ("REAL", "VERIFIED_REAL")


def economic_state(opp) -> str:
    """Honest lifecycle-vs-economics ladder.

    DISCOVERED         raw candidate, nothing priced
    LIVE_QUOTED        a live spread / venue price exists (not yet real-verified)
    VERIFIED           REAL provenance + at least one economic figure
    ECONOMICALLY_VALID REAL provenance + positive expected profit + spread
    """
    real = is_real_provenance(opp)
    has_spread = opp.spread_pct is not None
    has_price = opp.buy_price is not None or opp.sell_price is not None
    profit = opp.expected_profit_usd
    if real and profit is not None and float(profit) > 0 and has_spread:
        return "ECONOMICALLY_VALID"
    if real and (has_spread or profit is not None):
        return "VERIFIED"
    if has_spread or has_price:
        return "LIVE_QUOTED"
    return "DISCOVERED"


# --------------------------------------------------------------------------
# Assessment gating — a score is authoritative ONLY when genuinely assessed.
# --------------------------------------------------------------------------
def _assessment_marked(opp, key: str) -> bool:
    """True when a scanner explicitly asserts the assessment was performed.

    Lets a GENUINE zero survive (invariant: "a genuine mathematical zero must
    remain zero") without letting an initialization-default 0.0 masquerade as a
    real assessment. Scanners set e.g. ``metadata={"risk_assessed": True}``.
    """
    md = getattr(opp, "metadata", None)
    if isinstance(md, dict) and md.get(key) is True:
        return True
    return False


def assessed_confidence(opp) -> tuple[Optional[float], bool]:
    raw = float(opp.confidence_score or 0.0)
    assessed = bool(raw > 0.0 or _assessment_marked(opp, "confidence_assessed"))
    if not assessed:
        return None, False
    val = raw / 100.0 if raw > 1.0 else raw
    return round(val, 4), True


def assessed_safety(opp) -> tuple[Optional[float], bool]:
    raw = float(opp.risk_score or 0.0)
    assessed = bool(raw > 0.0 or _assessment_marked(opp, "risk_assessed"))
    if not assessed:
        return None, False
    safety = round(1.0 - min(1.0, raw / 100.0), 4)
    return safety, True


# --------------------------------------------------------------------------
# Economics gating + plausibility rejection.
# --------------------------------------------------------------------------
def _economics(opp) -> tuple[Optional[float], Optional[int], Optional[float], List[str]]:
    """Return (expected_profit_usd, capital_required_usd, return_pct, flags).

    Rules:
      * A present figure that is a genuine number (incl. negative / zero) is
        preserved — we never coerce None to 0.
      * ``return_pct`` is a real fraction (profit / capital) only when both are
        present and capital > 0. It is NEVER expected_profit re-labelled as a %.
      * Absurd values are REJECTED (set to None) and SURFACED via ``flags`` —
        never clamped to a plausible-looking number.
    """
    flags: List[str] = []

    profit = (float(opp.expected_profit_usd)
              if opp.expected_profit_usd is not None else None)

    capital = None
    if opp.capital_required_usd is not None:
        capital = float(opp.capital_required_usd)
        if capital < 0:
            flags.append("invalid_negative_capital")
            capital = None

    return_pct = None
    if profit is not None and capital is not None and capital > 0:
        return_pct = profit / capital

    # Plausibility: reject & surface, do not clamp.
    if return_pct is not None and abs(return_pct) > max_plausible_return():
        flags.append("implausible_return")
        return_pct = None
        profit = None
    elif (profit is not None and (capital is None or capital == 0)
            and abs(profit) > max_uncontextualized_profit_usd()):
        # A large profit with no capital to contextualise it cannot be
        # validated — surface it as suspect rather than authoritative.
        flags.append("uncontextualized_large_profit")
        profit = None

    profit_out = round(profit, 2) if profit is not None else None
    capital_out = int(round(capital)) if capital is not None else None
    return_out = round(return_pct, 4) if return_pct is not None else None
    return profit_out, capital_out, return_out, flags


def _spread_bps(opp) -> Optional[int]:
    # spread_pct is in percent; None stays None (no 0.0 bps coercion).
    return int(round(opp.spread_pct * 100)) if opp.spread_pct is not None else None


def _verdict(opp, econ_valid: bool) -> str:
    if opp.status == OpportunityStatus.REJECTED:
        return "HARD_NO"
    if opp.status == OpportunityStatus.APPROVED and econ_valid:
        return "GO"
    if econ_valid:
        return "SOFT_NO"   # economically valid but not operator-approved
    return "UNVERIFIED"    # raw / not economically validated


def _age_s(opp) -> Optional[int]:
    from datetime import datetime as _dt, timezone as _tz
    try:
        created = _dt.fromisoformat((opp.created_at or "").replace("Z", "+00:00"))
        return max(0, int((_dt.now(_tz.utc) - created).total_seconds()))
    except Exception:
        return None  # unknown age -> UNAVAILABLE, not "0s fresh"


def _enum_value(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


def build_display_contract(opp) -> Dict[str, Any]:
    """CanonicalOpportunity -> frontend v2 opportunity contract (authoritative)."""
    econ_state = economic_state(opp)
    econ_valid = econ_state == "ECONOMICALLY_VALID"

    confidence, confidence_assessed = assessed_confidence(opp)
    safety, safety_assessed = assessed_safety(opp)
    profit, capital, return_pct, flags = _economics(opp)

    # Strategy / chain dimensions carried end-to-end (Phase 2).
    strategy = _enum_value(opp.strategy) if opp.strategy is not None else None

    return {
        "id": opp.opportunity_id,
        "subject_id": opp.subject_id or opp.asset,
        "opportunity_type": _enum_value(opp.opportunity_type),
        "strategy": strategy,
        "chain": opp.chain or "-",
        "chain_id": opp.chain_id,
        "verdict": _verdict(opp, econ_valid),
        "economic_state": econ_state,
        "confidence": confidence,
        "confidence_assessed": confidence_assessed,
        "safety": safety,
        "safety_assessed": safety_assessed,
        "spread_bps": _spread_bps(opp),
        "capital_required_usd": capital,
        "depth_usd": None,  # real pool TVL not available on canonical rows
        "expected_profit_usd": profit,
        "return_pct": return_pct,
        "data_quality_flags": flags,
        "age_s": _age_s(opp),
        "route": opp.route,
        "status": _enum_value(opp.status),
        "source_data_quality": provenance_str(opp),
        "canonical": True,
    }


def build_discovery_contract(opp) -> Dict[str, Any]:
    """CanonicalOpportunity -> Discovery UI contract (authoritative)."""
    confidence, score_assessed = assessed_confidence(opp)
    otype = _enum_value(opp.opportunity_type)
    provenance = provenance_str(opp)
    canonical_status = _enum_value(opp.status)

    has_route = bool(opp.route) or bool(opp.buy_venue and opp.sell_venue)
    kind = "venue_pair" if has_route else "asset"
    asset_label = opp.asset or opp.subject_id or opp.opportunity_id

    parts: List[str] = [otype.replace("_", " ").title()]
    if opp.chain:
        parts.append(f"on {opp.chain}")
    if opp.spread_pct is not None:
        parts.append(f"spread {opp.spread_pct:.2f}%")
    if confidence is not None:
        parts.append(f"confidence {confidence:.2f}")
    why = " · ".join(parts)

    signals = [f"type:{otype.lower()}", f"provenance:{provenance.lower()}"]
    if opp.strategy is not None:
        signals.append(f"strategy:{_enum_value(opp.strategy).lower()}")
    if opp.chain:
        signals.append(f"chain:{opp.chain}")
    if opp.route:
        signals.append(f"route:{opp.route}")

    from .enums import OpportunityStatus as _S
    status_map = {
        _S.CANDIDATE.value: "NEW",
        _S.VALIDATED.value: "WATCHING",
        _S.APPROVED.value: "PROMOTED",
        _S.REJECTED.value: "DISMISSED",
    }
    return {
        "id": opp.opportunity_id,
        "asset": asset_label,
        "kind": kind,
        "chain": opp.chain or "-",
        "source": f"canonical:{provenance.lower()}",
        "score": confidence,
        "score_assessed": score_assessed,
        "status": status_map.get(canonical_status, "NEW"),
        "why": why,
        "signals": signals,
        "seen_at": opp.created_at,
    }


def build_deck_row(opp) -> Dict[str, Any]:
    """Compact dashboard-deck row (authoritative assessment gating)."""
    confidence, assessed = assessed_confidence(opp)
    return {
        "id": opp.opportunity_id,
        "opportunity_type": _enum_value(opp.opportunity_type),
        "subject_id": opp.subject_id or opp.asset or opp.opportunity_id,
        "chain": opp.chain,
        "confidence": confidence,
        "confidence_assessed": assessed,
        "status": _enum_value(opp.status),
        "created_at": opp.created_at,
    }


__all__ = [
    "provenance_str", "is_real_provenance", "economic_state",
    "assessed_confidence", "assessed_safety",
    "build_display_contract", "build_discovery_contract", "build_deck_row",
    "max_plausible_return", "max_uncontextualized_profit_usd",
]
