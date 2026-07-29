"""Tests for D-3.2 — DEXQuoteVerifier.

Covers:
  - Verifier construction
  - Malformed candidate.subject_id → ERROR_PREFIX
  - No quoters available for chain → DENIED_VENUE_UNREADABLE
  - All quoters return ok=False (graceful-disable / not_yet_wired) → DENIED_VENUE_UNREADABLE
  - Same DEX wins buy and sell → DENIED_VENUE_DISAGREES
  - Negative spread → DENIED_VENUE_DISAGREES
  - Happy path: 2 DEX, positive spread → CanonicalOpportunity built via
    universal verification_evidence substrate; INV-1 typing; INV-3 provenance
  - Gate 1 placeholder rejection passes opp back with rejected metadata
  - Gate 1 placeholder pass → run_universal_gates engaged → opp VALIDATED
  - INV-2: verifier module does NOT call EmissionBus.emit()
  - INV-3 attribution: source_data_quality comes from quoter SOURCE_REGISTRY
"""
from __future__ import annotations

import asyncio
import ast
import inspect

import pytest

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import (
    DataProvenance, OpportunityStatus, OpportunityType,
)
from arbicore.scanners.dex_arbitrage import DEXQuoteVerifier
from arbicore.scanners.dex_arbitrage.quoter import (
    BaseDEXQuoter, DEXQuoteResult,
)


# ============================================================================
# Mock quoter — returns canned DEXQuoteResults for tests
# ============================================================================

class _MockQuoter(BaseDEXQuoter):
    rpc_env_var = None  # never gated by creds

    def __init__(self, *, chain: str, dex: str, buy_price: float,
                 sell_price: float, pool_address: str = "0xpool",
                 pool_liquidity_usd: float = 10_000_000.0,
                 ok: bool = True) -> None:
        self.chain = chain
        self.dex = dex
        self.source_id = f"{dex}_quoter_{chain}"
        super().__init__()
        self._buy_price = buy_price
        self._sell_price = sell_price
        self._pool_address = pool_address
        self._pool_liquidity_usd = pool_liquidity_usd
        self._ok = ok

    async def _quote_impl(self, *, pair_canonical, size_in_usd, direction):
        if not self._ok:
            return DEXQuoteResult(
                ok=False, chain=self.chain, dex=self.dex,
                source_id=self.source_id, reason="mock_disabled",
            )
        price = self._buy_price if direction == "buy" else self._sell_price
        return DEXQuoteResult(
            ok=True, chain=self.chain, dex=self.dex,
            source_id=self.source_id,
            pool_address=self._pool_address,
            token_in=pair_canonical.split("/")[0],
            token_out=pair_canonical.split("/")[1].split("@")[0],
            size_in_usd=size_in_usd,
            amount_in=size_in_usd,
            amount_out=size_in_usd * price,
            effective_price=price,
            mid_price=price,
            slippage_pct=0.05,
            fee_tier_bps=5,
            pool_liquidity_usd=self._pool_liquidity_usd,
            gas_estimate_usd=2.0,
            age_ms=120,
        )


# ============================================================================
# Capability repo stub
# ============================================================================

class _StubCaps:
    async def is_gate_3_pass(self, venue_id, base, quote):
        return True, "ok"


def _make_candidate(subject_id: str = "WETH/USDC@arbitrum") -> DiscoveryCandidate:
    return DiscoveryCandidate(
        candidate_id="cand_test",
        opportunity_type=OpportunityType.DEX_ARBITRAGE,
        hint_source="venue_dex_pool:uniswap_v3:arbitrum",
        subject_id=subject_id,
        asset=subject_id.split("/")[0] if "/" in subject_id else None,
        candidate_venues=["uniswap_v3:arbitrum", "pancake_v3:arbitrum"],
    )


def _make_cfg(min_pct: float = 0.30):
    return {
        "default_notional_usd": 1000.0,
        "gate_thresholds": {
            "default": {
                "min_net_spread_after_slip_after_gas_pct": min_pct,
                "min_depth_usd": 5000,
                "min_confidence": 55,
            },
        },
    }


# ============================================================================
# Construction
# ============================================================================

def test_verifier_construction_requires_quoters():
    with pytest.raises(ValueError):
        DEXQuoteVerifier(quoters=[], venue_caps=_StubCaps())


def test_verifier_opportunity_type():
    v = DEXQuoteVerifier(
        quoters=[_MockQuoter(chain="arbitrum", dex="uniswap_v3",
                             buy_price=2000.0, sell_price=2000.0)],
        venue_caps=_StubCaps(),
    )
    assert v.opportunity_type == OpportunityType.DEX_ARBITRAGE


# ============================================================================
# Malformed subject
# ============================================================================

def test_verifier_malformed_subject_id_returns_error():
    v = DEXQuoteVerifier(
        quoters=[_MockQuoter(chain="arbitrum", dex="uniswap_v3",
                             buy_price=2000.0, sell_price=2000.0)],
        venue_caps=_StubCaps(),
    )
    cand = _make_candidate(subject_id="malformed_no_at_sign")
    opp, tag = asyncio.run(v.verify(cand))
    assert opp is None
    assert tag.startswith("error:")


# ============================================================================
# No quoters on chain
# ============================================================================

def test_verifier_no_quoter_for_chain_returns_unreadable():
    v = DEXQuoteVerifier(
        quoters=[_MockQuoter(chain="arbitrum", dex="uniswap_v3",
                             buy_price=2000.0, sell_price=2000.0)],
        venue_caps=_StubCaps(),
    )
    cand = _make_candidate(subject_id="WETH/USDC@base")
    opp, tag = asyncio.run(v.verify(cand))
    assert opp is None
    assert tag == VerifiedOutcome.DENIED_VENUE_UNREADABLE


# ============================================================================
# All quoters disabled (graceful-disable simulation)
# ============================================================================

def test_verifier_returns_unreadable_when_all_quoters_disabled():
    v = DEXQuoteVerifier(
        quoters=[
            _MockQuoter(chain="arbitrum", dex="uniswap_v3",
                        buy_price=2000.0, sell_price=2000.0, ok=False),
            _MockQuoter(chain="arbitrum", dex="pancake_v3",
                        buy_price=2010.0, sell_price=2010.0, ok=False),
        ],
        venue_caps=_StubCaps(),
    )
    opp, tag = asyncio.run(v.verify(_make_candidate()))
    assert opp is None
    assert tag == VerifiedOutcome.DENIED_VENUE_UNREADABLE


# ============================================================================
# Same DEX wins both legs
# ============================================================================

def test_verifier_rejects_when_same_dex_wins_both_legs():
    """uniswap has the best buy AND best sell → DENIED_VENUE_DISAGREES."""
    v = DEXQuoteVerifier(
        quoters=[
            _MockQuoter(chain="arbitrum", dex="uniswap_v3",
                        buy_price=1990.0, sell_price=2050.0),  # best on both
            _MockQuoter(chain="arbitrum", dex="pancake_v3",
                        buy_price=2000.0, sell_price=2040.0),
        ],
        venue_caps=_StubCaps(),
    )
    opp, tag = asyncio.run(v.verify(_make_candidate()))
    assert opp is None
    assert tag == VerifiedOutcome.DENIED_VENUE_DISAGREES


# ============================================================================
# Negative spread
# ============================================================================

def test_verifier_rejects_negative_spread():
    """Both sides identical → spread_pct == 0 → DENIED_VENUE_DISAGREES."""
    v = DEXQuoteVerifier(
        quoters=[
            _MockQuoter(chain="arbitrum", dex="uniswap_v3",
                        buy_price=2000.0, sell_price=2000.0),
            _MockQuoter(chain="arbitrum", dex="pancake_v3",
                        buy_price=2000.0, sell_price=2000.0),
        ],
        venue_caps=_StubCaps(),
    )
    opp, tag = asyncio.run(v.verify(_make_candidate()))
    assert opp is None
    assert tag == VerifiedOutcome.DENIED_VENUE_DISAGREES


# ============================================================================
# Happy path — VALIDATED
# ============================================================================

def test_verifier_happy_path_emits_canonical_validated():
    v = DEXQuoteVerifier(
        quoters=[
            _MockQuoter(chain="arbitrum", dex="uniswap_v3",
                        buy_price=1990.0, sell_price=2010.0,
                        pool_liquidity_usd=10_000_000.0),
            _MockQuoter(chain="arbitrum", dex="pancake_v3",
                        buy_price=2010.0, sell_price=2030.0,
                        pool_liquidity_usd=8_000_000.0),
        ],
        venue_caps=_StubCaps(),
        config_loader=lambda: _make_cfg(min_pct=0.30),
    )
    cand = _make_candidate()
    opp, tag = asyncio.run(v.verify(cand))
    assert isinstance(opp, CanonicalOpportunity)
    assert opp.opportunity_type == OpportunityType.DEX_ARBITRAGE
    assert opp.status == OpportunityStatus.VALIDATED
    assert tag.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    # INV-1: candidate is not the canonical row
    assert opp.opportunity_id != cand.candidate_id
    # INV-3: provenance derived from leg quoter SOURCE_REGISTRY (both REAL)
    assert opp.source_data_quality == DataProvenance.REAL
    # Buy = lowest ask, sell = highest bid
    assert opp.buy_venue == "uniswap_v3:arbitrum"   # buy=1990 < 2010
    assert opp.sell_venue == "pancake_v3:arbitrum"  # sell=2030 > 2010
    assert opp.buy_price == 1990.0
    assert opp.sell_price == 2030.0
    # Spread = (2030 - 1990) / 1990 * 100 ≈ 2.01%
    assert abs(opp.spread_pct - 2.0101) < 0.001
    # Category metadata populated
    assert opp.category_metadata["chain"] == "arbitrum"
    assert opp.category_metadata["buy_dex"] == "uniswap_v3"
    assert opp.category_metadata["sell_dex"] == "pancake_v3"
    # Audit trail
    assert opp.metadata["discovery_candidate_id"] == "cand_test"
    assert opp.metadata["verifier_id"] == "dex_quote_verifier"
    assert "uniswap_v3_quoter_arbitrum" in opp.metadata["leg_source_ids"]
    assert "pancake_v3_quoter_arbitrum" in opp.metadata["leg_source_ids"]


# ============================================================================
# Gate-1 placeholder rejection (still emits CANDIDATE with rejection meta)
# ============================================================================

def test_verifier_gate1_placeholder_rejects_thin_spread():
    """Set min_net = 5% but actual spread only ~2% → Gate 1 rejects."""
    v = DEXQuoteVerifier(
        quoters=[
            _MockQuoter(chain="arbitrum", dex="uniswap_v3",
                        buy_price=1990.0, sell_price=2010.0,
                        pool_liquidity_usd=10_000_000.0),
            _MockQuoter(chain="arbitrum", dex="pancake_v3",
                        buy_price=2010.0, sell_price=2030.0,
                        pool_liquidity_usd=8_000_000.0),
        ],
        venue_caps=_StubCaps(),
        config_loader=lambda: _make_cfg(min_pct=5.0),
    )
    opp, tag = asyncio.run(v.verify(_make_candidate()))
    assert opp is not None                                 # still returned for evidence
    assert opp.status == OpportunityStatus.CANDIDATE       # not validated
    assert tag.startswith(VerifiedOutcome.DENIED_GATE_PREFIX)
    assert "economics" in tag
    assert opp.metadata.get("rejected_at_gate") == 1
    assert opp.metadata.get("rejected_gate_name") == "economics"


# ============================================================================
# Gate-2 (liquidity) rejection via universal pipeline
# ============================================================================

def test_verifier_gate2_liquidity_rejection():
    v = DEXQuoteVerifier(
        quoters=[
            _MockQuoter(chain="arbitrum", dex="uniswap_v3",
                        buy_price=1990.0, sell_price=2010.0,
                        pool_liquidity_usd=100.0),     # below min_depth_usd
            _MockQuoter(chain="arbitrum", dex="pancake_v3",
                        buy_price=2010.0, sell_price=2030.0,
                        pool_liquidity_usd=200.0),
        ],
        venue_caps=_StubCaps(),
        config_loader=lambda: _make_cfg(min_pct=0.30),
    )
    opp, tag = asyncio.run(v.verify(_make_candidate()))
    assert opp is not None
    assert tag.startswith(VerifiedOutcome.DENIED_GATE_PREFIX)
    assert "liquidity" in tag
    assert opp.metadata.get("rejected_at_gate") == 2


# ============================================================================
# INV-2 — verifier module has no EmissionBus / .emit() usage
# ============================================================================

def test_inv2_dex_verifier_module_has_no_emit():
    import arbicore.scanners.dex_arbitrage.verifier as mod
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "EmissionBus":
            raise AssertionError("DEXQuoteVerifier imports EmissionBus")
        if isinstance(node, ast.Attribute) and node.attr == "emit":
            raise AssertionError("DEXQuoteVerifier uses .emit attribute")


def test_inv2_filter_module_has_no_emit():
    import arbicore.scanners.dex_arbitrage.filter as mod
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "EmissionBus":
            raise AssertionError("dex filter imports EmissionBus")
        if isinstance(node, ast.Attribute) and node.attr == "emit":
            raise AssertionError("dex filter uses .emit attribute")


# ============================================================================
# Protocol-agnosticism (architectural check)
# ============================================================================

def test_verifier_uses_universal_evidence_substrate():
    """Architectural assertion: the DEX verifier MUST import the universal
    verification_evidence substrate, not re-implement canonical construction
    inline. This is what enables D-4/D-5/D-6 reuse."""
    import arbicore.scanners.dex_arbitrage.verifier as mod
    src = inspect.getsource(mod)
    assert "from ..verification_evidence import" in src
    assert "build_canonical_from_evidence" in src
    assert "VerificationEvidence" in src
    assert "LegEvidence" in src
