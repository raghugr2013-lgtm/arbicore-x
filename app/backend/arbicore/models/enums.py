"""ArbiCore X — Shared enumerations.

These enums form part of the canonical contract. Every module across the
platform (scanner, validators, scoring, confidence, learning) MUST use these
values rather than free-form strings.
"""
from __future__ import annotations

from enum import Enum


class OpportunityType(str, Enum):
    """Supported opportunity families. One canonical model serves all of them."""

    CEX_ARBITRAGE = "CEX_ARBITRAGE"
    DEX_ARBITRAGE = "DEX_ARBITRAGE"
    FUNDING_ARBITRAGE = "FUNDING_ARBITRAGE"
    CROSS_CHAIN_ARBITRAGE = "CROSS_CHAIN_ARBITRAGE"
    LAUNCH_ARBITRAGE = "LAUNCH_ARBITRAGE"
    FLASH_LOAN_ARBITRAGE = "FLASH_LOAN_ARBITRAGE"  # future rebuild — detection only


class StrategyType(str, Enum):
    """Flash-loan sub-strategy dimension (multi-strategy expansion, Phase 2).

    Additive to ``OpportunityType``. ``opportunity_type`` stays the coarse
    family (e.g. FLASH_LOAN_ARBITRAGE / DEX_ARBITRAGE); ``strategy`` refines
    it into the concrete route-building strategy. Optional everywhere — legacy
    rows and non-flash families simply leave it ``None``.
    """

    GENERIC_DEX = "GENERIC_DEX"          # simple 2-hop cross-DEX / fee-tier arb
    TRIANGULAR = "TRIANGULAR"            # 3-leg single-chain cycle
    STABLECOIN = "STABLECOIN"            # stable-pair / peg arb
    MULTI_HOP = "MULTI_HOP"              # >3-leg route
    LST_LRT = "LST_LRT"                  # liquid (re)staking token arb
    LIQUIDATION = "LIQUIDATION"          # atomic flash-funded liquidation
    COLLATERAL_DEBT = "COLLATERAL_DEBT"  # atomic collateral/debt swap


class OpportunityStatus(str, Enum):
    """Canonical lifecycle. Execution states exist in the contract for future
    use but NO module in Phase 1/B may transition an opportunity into them."""

    CANDIDATE = "candidate"
    VALIDATED = "validated"
    APPROVED = "approved"
    EXECUTED = "executed"      # reserved for future execution layer
    COMPLETED = "completed"    # reserved for future execution layer
    REJECTED = "rejected"


class MarketRegime(str, Enum):
    UNKNOWN = "UNKNOWN"
    CALM = "CALM"
    VOLATILE = "VOLATILE"
    ILLIQUID = "ILLIQUID"
    TRENDING = "TRENDING"


class RouteHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    NEW = "NEW"
    EPHEMERAL = "EPHEMERAL"
    SHORT_LIVED = "SHORT_LIVED"
    PERSISTENT = "PERSISTENT"


class MevRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DataProvenance(str, Enum):
    """Trust classification for every data source.

    Hierarchy (high to low): VERIFIED_REAL > REAL > SIMULATED > CONTAMINATED > DEAD.

    Only ``VERIFIED_REAL`` and ``REAL`` may influence learning, confidence
    calibration, adaptive weighting, route success statistics, or any future
    AI model.
    """

    VERIFIED_REAL = "VERIFIED_REAL"   # operator-verified live data (Phase D promotion)
    REAL = "REAL"
    SIMULATED = "SIMULATED"
    CONTAMINATED = "CONTAMINATED"
    DEAD = "DEAD"


# Provenance values that are allowed to feed the learning subsystem.
# Phase B: extended from {REAL} to {VERIFIED_REAL, REAL}.
LEARNING_ELIGIBLE_PROVENANCE = frozenset({
    DataProvenance.VERIFIED_REAL,
    DataProvenance.REAL,
})
