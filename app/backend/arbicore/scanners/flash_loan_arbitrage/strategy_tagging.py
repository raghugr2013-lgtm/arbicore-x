"""Phase-2 Part D · Flash-loan strategy classification + honest emit.

Tags every flash-loan candidate with a canonical ``StrategyType`` and the
``chain`` / ``chain_id`` dimensions at EMIT time, then carries them end-to-end
through the canonical model (→ persistence → API → UI, all already dimension-
aware). Reuses the existing ``CanonicalOpportunity`` — no parallel schema.

Strategy families (flash-loan-dependent only — NO capital/CEX strategies):
    GENERIC_DEX  simple 2-hop cross-DEX / fee-tier arb
    STABLECOIN   every leg token is a stablecoin (peg arb)
    TRIANGULAR   3-leg single-chain cycle (A→B→C→A)
    MULTI_HOP    > 3 legs
    LST_LRT      route touches a liquid (re)staking token

Pure / deterministic. Emits DETECTION-ONLY opportunities: never a positive
profit by default, never an execution instruction. Economics must be supplied
from a real calculation; missing economics stay ``None`` (fail-closed).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...models.canonical import CanonicalOpportunity
from ...models.enums import (
    DataProvenance, OpportunityType, StrategyType,
)

# Canonical symbol sets (case-insensitive) reused for classification.
STABLE_SYMBOLS = frozenset({
    "USDC", "USDC.E", "USDT", "DAI", "USDBC", "FRAX", "LUSD", "TUSD", "GUSD",
    "USDD", "MIM", "SUSD",
})
LST_LRT_SYMBOLS = frozenset({
    "WSTETH", "STETH", "RETH", "CBETH", "WEETH", "EETH", "EZETH", "RSETH",
    "SFRXETH", "FRXETH", "OSETH", "ANKRETH",
})


def _norm(sym: str) -> str:
    return (sym or "").strip().upper()


def classify_strategy(route_tokens: List[str], *,
                      hop_count: Optional[int] = None) -> StrategyType:
    """Classify a route into a canonical flash-loan strategy.

    ``route_tokens`` is the ordered token path (symbols). ``hop_count`` overrides
    the leg count derived from the path when supplied.
    """
    toks = [_norm(t) for t in (route_tokens or []) if t]
    n_unique = len(set(toks))
    legs = hop_count if hop_count is not None else max(0, len(toks) - 1)

    # Priority: LST/LRT flavour, then stable, then structural shape.
    if any(t in LST_LRT_SYMBOLS for t in toks):
        return StrategyType.LST_LRT
    if toks and all(t in STABLE_SYMBOLS for t in toks):
        return StrategyType.STABLECOIN
    # Triangular = closed 3-node cycle (first == last, 3 distinct nodes).
    if len(toks) >= 4 and toks[0] == toks[-1] and n_unique == 3:
        return StrategyType.TRIANGULAR
    if legs > 3:
        return StrategyType.MULTI_HOP
    return StrategyType.GENERIC_DEX


def emit_flash_candidate(
    *,
    asset: str,
    chain: str,
    chain_id: int,
    route_tokens: List[str],
    buy_venue: Optional[str] = None,
    sell_venue: Optional[str] = None,
    spread_pct: Optional[float] = None,
    expected_profit_usd: Optional[float] = None,
    capital_required_usd: Optional[float] = None,
    provenance: DataProvenance = DataProvenance.SIMULATED,
    risk_score: Optional[float] = None,
    confidence_score: Optional[float] = None,
    hop_count: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> CanonicalOpportunity:
    """Build a detection-only flash-loan ``CanonicalOpportunity``.

    Sets ``strategy`` + ``chain_id`` so the dimensions propagate end-to-end.
    Assessment scores are marked assessed ONLY when a real value is supplied
    (so a genuine zero survives; an unsupplied score defaults to 0 and stays
    UNASSESSED at the display contract). Never fabricates economics.
    """
    strategy = classify_strategy(route_tokens, hop_count=hop_count)
    md: Dict[str, Any] = dict(metadata or {})
    md.setdefault("route_tokens", [_norm(t) for t in route_tokens])
    if risk_score is not None:
        md["risk_assessed"] = True
    if confidence_score is not None:
        md["confidence_assessed"] = True

    return CanonicalOpportunity(
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        strategy=strategy,
        asset=asset,
        chain=(chain or "").lower(),
        chain_id=int(chain_id),
        buy_venue=buy_venue,
        sell_venue=sell_venue,
        spread_pct=spread_pct,
        expected_profit_usd=expected_profit_usd,
        capital_required_usd=capital_required_usd,
        risk_score=float(risk_score) if risk_score is not None else 0.0,
        confidence_score=float(confidence_score) if confidence_score is not None else 0.0,
        source_data_quality=provenance,
        metadata=md,
    )


__all__ = [
    "STABLE_SYMBOLS", "LST_LRT_SYMBOLS",
    "classify_strategy", "emit_flash_candidate",
]
