"""D-6.0 substrate seeding tests."""
from __future__ import annotations

from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
from arbicore.data.scanner_config_repo import (
    DEFAULT_FLASH_LOAN_ARB_CONFIG,
)
from arbicore.models.category_metadata import (
    KNOWN_CATEGORY_METADATA_KEYS,
)
from arbicore.models.enums import MevRiskLevel, OpportunityType
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
    MevRiskScorer,
)
from arbicore.scanners.verification_evidence import EvidenceLegRole


# ============================================================================
# 1. category_metadata vocabulary populated
# ============================================================================

def test_flash_loan_vocab_filled():
    keys = KNOWN_CATEGORY_METADATA_KEYS[OpportunityType.FLASH_LOAN_ARBITRAGE]
    assert len(keys) >= 24
    for k in ("flash_loan_provider", "chain", "flash_loan_borrow_token",
               "flash_loan_borrow_amount_usd", "flash_loan_fee_bps",
               "flash_loan_fee_usd", "route_pools", "route_dex_protocols",
               "cycle_token_path", "hop_count",
               "atomic_profit_usd", "atomic_profit_pct",
               "gas_cost_usd", "gas_drag_pct",
               "min_pool_tvl_usd_in_route",
               "flash_loan_mev_risk_class",
               "simulated_atomicity_ok"):
        assert k in keys


# ============================================================================
# 2. SOURCE_REGISTRY entries seeded
# ============================================================================

def test_aave_v3_flashloan_provenance_real():
    assert SOURCE_REGISTRY["aave_v3_flashloan_real"].provenance == \
        DataProvenance.REAL


def test_balancer_v2_flashloan_provenance_real():
    assert SOURCE_REGISTRY["balancer_v2_flashloan_real"].provenance == \
        DataProvenance.REAL


def test_uniswap_v3_flashloan_provenance_real():
    assert SOURCE_REGISTRY["uniswap_v3_flashloan_real"].provenance == \
        DataProvenance.REAL


# ============================================================================
# 3. EvidenceLegRole extended
# ============================================================================

def test_evidence_leg_role_flash_loan_borrow():
    assert EvidenceLegRole.FLASH_LOAN_BORROW == "borrow"


def test_evidence_leg_role_flash_loan_repay():
    assert EvidenceLegRole.FLASH_LOAN_REPAY == "repay"


# ============================================================================
# 4. MevRiskScorer atomicity input
# ============================================================================

def test_mev_scorer_atomic_increases_score():
    sc = MevRiskScorer()
    base = sc.classify(source_chain_congestion=30,
                        destination_chain_congestion=30,
                        asset="USDC", notional_usd=1000)
    atomic = sc.classify(source_chain_congestion=30,
                          destination_chain_congestion=30,
                          asset="USDC", notional_usd=1000,
                          is_atomic=True)
    assert atomic["is_atomic"] is True
    assert atomic["score"] > base["score"]


def test_mev_scorer_bridge_optional():
    sc = MevRiskScorer()
    v = sc.classify(source_chain_congestion=20,
                     destination_chain_congestion=20,
                     asset="USDC", notional_usd=1000,
                     is_atomic=True)
    assert v["bridge"] == "atomic_flashloan"
    assert v["level"] == MevRiskLevel.LOW


def test_mev_scorer_back_compat_bridge_arg():
    """Existing D-5 callers using bridge=... keep working."""
    sc = MevRiskScorer()
    v = sc.classify(bridge="lifi", source_chain_congestion=40,
                     destination_chain_congestion=40, asset="USDC",
                     notional_usd=1000)
    assert v["bridge"] == "lifi"
    assert v["is_atomic"] is False


# ============================================================================
# 5. scanner_config defaults locked
# ============================================================================

def test_provider_scope_locked():
    providers = DEFAULT_FLASH_LOAN_ARB_CONFIG["providers"]
    assert set(providers.keys()) == {"aave_v3", "balancer_v2", "uniswap_v3"}
    for p in providers.values():
        assert p["enabled"] is False


def test_chain_scope_locked():
    chains = DEFAULT_FLASH_LOAN_ARB_CONFIG["chains"]
    assert set(chains.keys()) == {"ethereum", "arbitrum", "base",
                                     "optimism", "polygon"}
    assert "solana" not in chains
    for c in chains.values():
        assert c["enabled"] is False


def test_route_search_budget_locked():
    rs = DEFAULT_FLASH_LOAN_ARB_CONFIG["route_search"]
    assert rs["max_hops"] == 4
    assert rs["wall_clock_cap_s"] == 5.0
    assert rs["candidate_cap"] == 64


def test_atomic_profit_floor_locked():
    gates = DEFAULT_FLASH_LOAN_ARB_CONFIG["gate_thresholds"]["default"]
    assert gates["min_atomic_profit_usd"] == 25.0


def test_scanner_state_disabled_by_default():
    assert DEFAULT_FLASH_LOAN_ARB_CONFIG["enabled"] is False


def test_mev_cap_default_is_medium():
    gates = DEFAULT_FLASH_LOAN_ARB_CONFIG["gate_thresholds"]["default"]
    assert gates["max_flash_loan_mev_risk_class"] == "MEDIUM"


# ============================================================================
# 6. Out-of-scope items NOT seeded
# ============================================================================

def test_no_extra_providers():
    providers = DEFAULT_FLASH_LOAN_ARB_CONFIG["providers"]
    for forbidden in ("maker", "dydx", "morpho", "compound"):
        assert forbidden not in providers


def test_no_solana():
    assert "solana" not in DEFAULT_FLASH_LOAN_ARB_CONFIG["chains"]
