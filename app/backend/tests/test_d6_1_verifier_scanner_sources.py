"""D-6.1 — Verifier + Scanner + Sources + Invariants tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import (
    DiscoveryCandidate, VerifiedOutcome, make_candidate_id,
)
from arbicore.models.enums import (
    DataProvenance, MevRiskLevel, OpportunityType, OpportunityStatus,
)
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
    MevRiskScorer,
)
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FlashLoanEconomicsAssessor,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)
from arbicore.scanners.flash_loan_arbitrage.route_search import (
    PoolNode, RouteSearchEngine,
)
from arbicore.scanners.flash_loan_arbitrage.scanner import (
    FlashLoanArbitrageScanner,
)
from arbicore.scanners.flash_loan_arbitrage.sources import (
    RouteSearchDiscoverySource, build_all_flash_loan_sources,
)
from arbicore.scanners.flash_loan_arbitrage.verifier import (
    FlashLoanOpportunityVerifier,
)


_GATES = {
    "min_atomic_profit_usd": 25.0,
    "min_pool_tvl_usd_in_route": 100_000.0,
    "max_flash_loan_mev_risk_class": "MEDIUM",
}


def _pool(addr, a, b, *, tvl=1_000_000.0, fee_bps=30,
           dex="uniswap_v3", chain="ethereum"):
    return PoolNode(pool_address=addr, dex_protocol=dex, chain=chain,
                     token_a=a, token_b=b, tvl_usd=tvl, fee_bps=fee_bps)


def _cfg() -> Dict[str, Any]:
    return {
        "interval_s": 60,
        "default_notional_usd": 10_000.0,
        "providers": {
            "aave_v3":   {"enabled": False, "fee_bps": 5},
            "balancer_v2": {"enabled": False, "fee_bps": 0},
            "uniswap_v3": {"enabled": False, "fee_bps_default": 30},
        },
        "chains": {c: {"enabled": False, "gas_token": "ETH",
                        "tx_gas_units": 800_000}
                    for c in ("ethereum", "arbitrum", "base",
                               "optimism", "polygon")},
        "route_search": {
            "max_hops": 4, "wall_clock_cap_s": 5.0,
            "candidate_cap": 64, "min_pool_tvl_usd": 100_000,
        },
        "gate_thresholds": {"default": _GATES},
        "roi_probability": {"min_sample_size": 2},
    }


# ============================================================================
# RouteSearchDiscoverySource
# ============================================================================

def test_source_disabled_by_default():
    cfg = _cfg()
    pools = [_pool("p1", "USDC", "WETH"), _pool("p2", "WETH", "USDC")]
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    s = RouteSearchDiscoverySource(route_engine=engine,
                                    config_loader=lambda: cfg)
    out = asyncio.run(s.discover())
    assert out == []


def test_source_emits_candidates_when_enabled():
    cfg = _cfg()
    cfg["chains"]["ethereum"]["enabled"] = True
    cfg["providers"]["aave_v3"]["enabled"] = True
    pools = [_pool("p1", "USDC", "WETH"), _pool("p2", "WETH", "USDC")]
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    s = RouteSearchDiscoverySource(route_engine=engine,
                                    config_loader=lambda: cfg,
                                    borrow_token_set=["USDC"])
    out = asyncio.run(s.discover())
    assert out
    for c in out:
        assert c.opportunity_type == OpportunityType.FLASH_LOAN_ARBITRAGE
        assert c.hint_metric["chain"] == "ethereum"
        assert c.hint_metric["provider"] == "aave_v3"
        assert c.hint_source == "flash_loan_route_search"


def test_inv1_source_emits_discovery_candidate_only():
    cfg = _cfg()
    cfg["chains"]["ethereum"]["enabled"] = True
    cfg["providers"]["aave_v3"]["enabled"] = True
    pools = [_pool("p1", "USDC", "WETH"), _pool("p2", "WETH", "USDC")]
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    s = RouteSearchDiscoverySource(route_engine=engine,
                                    config_loader=lambda: cfg,
                                    borrow_token_set=["USDC"])
    out = asyncio.run(s.discover())
    assert all(isinstance(c, DiscoveryCandidate) for c in out)


def test_inv2_sources_no_emission_bus():
    import arbicore.scanners.flash_loan_arbitrage.sources as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "_bus.emit(" not in text


def test_factory_returns_two_sources():
    pools = []
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    out = build_all_flash_loan_sources(
        route_engine=engine, config_loader=lambda: _cfg())
    ids = sorted(s.source_id for s in out)
    assert ids == ["flash_loan_provider_health", "flash_loan_route_search"]


# ============================================================================
# Verifier
# ============================================================================

def _build_verifier(provider, outcome_loader=None):
    return FlashLoanOpportunityVerifier(
        quote_provider=provider,
        economics_assessor=FlashLoanEconomicsAssessor(
            roi_engine=ROIProbabilityEngine(min_sample=2),
            default_borrow_amount_usd=10_000.0),
        mev_scorer=MevRiskScorer(),
        gate_7=FlashLoanGate7AtomicProfit(thresholds=_GATES),
        gate_8=FlashLoanGate8LiquidityDepth(thresholds=_GATES),
        gate_9=FlashLoanGate9FlashLoanMev(thresholds=_GATES),
        outcome_history_loader=outcome_loader,
        default_borrow_amount_usd=10_000.0,
    )


def _candidate(*, provider="aave_v3", chain="ethereum") -> DiscoveryCandidate:
    hm = {
        "chain": chain, "provider": provider,
        "borrow_token": "USDC", "hop_count": 2,
        "min_tvl_usd": 500_000.0,
        "estimated_total_fee_pct": 0.6,
        "route_pools": ["p1", "p2"],
        "route_dex_protocols": ["uniswap_v3", "sushiswap"],
        "cycle_token_path": ["USDC", "WETH", "USDC"],
        "route_search_wall_ms": 12,
        "route_search_candidates_explored": 4,
    }
    subject = f"flash_loan:{provider}:{chain}:USDC:r1"
    cid = make_candidate_id(
        hint_source="t",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id=subject, asset="USDC",
        candidate_venues=["p1", "p2"], hint_observed_at=1.0,
    )
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="t", hint_observed_at=1.0, subject_id=subject,
        asset="USDC", candidate_venues=["p1", "p2"], hint_metric=hm,
        reason="t",
    )


def test_verifier_denied_when_provider_returns_none():
    async def provider(hm, amt): return None
    v = _build_verifier(provider)
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is None
    assert tag == VerifiedOutcome.DENIED_VENUE_UNREADABLE


def test_verifier_emits_canonical_on_happy_path():
    async def provider(hm, amt):
        return {
            "flash_loan_pool_address": "0xpool",
            "flash_loan_fee_bps_override": 5,
            "hop_legs": [
                {"venue_id": "p1", "fee_bps": 30, "slippage_pct": 0.05,
                  "source_id": "uniswap_v3_quoter_ethereum",
                  "depth_usd": 500_000, "dex_protocol": "uniswap_v3"},
                {"venue_id": "p2", "fee_bps": 30, "slippage_pct": 0.05,
                  "source_id": "uniswap_v3_quoter_ethereum",
                  "depth_usd": 500_000, "dex_protocol": "sushiswap"},
            ],
            "gross_profit_pct": 2.0,
            "verified_at_ts": 1.0,
            "min_pool_tvl_usd_in_route": 500_000.0,
        }
    v = _build_verifier(provider)
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is not None
    assert tag.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    assert out.opportunity_type == OpportunityType.FLASH_LOAN_ARBITRAGE
    assert out.opportunity_id.startswith("flash_loan_arb:")
    assert out.status == OpportunityStatus.CANDIDATE


def test_inv3_provenance_real_from_legs():
    async def provider(hm, amt):
        return {
            "flash_loan_pool_address": "0xpool",
            "hop_legs": [
                {"venue_id": "p1", "fee_bps": 30, "slippage_pct": 0.05,
                  "source_id": "uniswap_v3_quoter_ethereum", "depth_usd": 500_000},
                {"venue_id": "p2", "fee_bps": 30, "slippage_pct": 0.05,
                  "source_id": "uniswap_v3_quoter_ethereum", "depth_usd": 500_000},
            ],
            "gross_profit_pct": 2.0,
            "min_pool_tvl_usd_in_route": 500_000.0,
        }
    v = _build_verifier(provider)
    out, _ = asyncio.run(v.verify(_candidate()))
    assert out.source_data_quality == DataProvenance.REAL


def test_gate7_rejects_unprofitable():
    async def provider(hm, amt):
        return {
            "hop_legs": [
                {"venue_id": "p1", "fee_bps": 30, "slippage_pct": 5.0,
                  "source_id": "uniswap_v3_quoter_ethereum"},
            ],
            "gross_profit_pct": 0.0,  # no profit
            "min_pool_tvl_usd_in_route": 500_000.0,
        }
    v = _build_verifier(provider)
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is None
    assert "gate_7" in tag


def test_gate8_rejects_thin_liquidity():
    async def provider(hm, amt):
        return {
            "hop_legs": [{"venue_id": "p1", "fee_bps": 5,
                          "slippage_pct": 0.01,
                          "source_id": "uniswap_v3_quoter_ethereum"}],
            "gross_profit_pct": 2.0,
            "min_pool_tvl_usd_in_route": 1_000.0,  # below floor
        }
    cand = _candidate()
    cand.hint_metric["min_tvl_usd"] = 1_000.0
    v = _build_verifier(provider)
    out, tag = asyncio.run(v.verify(cand))
    assert out is None
    assert "gate_8" in tag


def test_outcome_history_loader_called():
    captured = {}

    async def loader(corridor):
        captured["c"] = corridor
        return [{"realized_pct": 0.4}]
    async def provider(hm, amt):
        return {
            "hop_legs": [{"venue_id": "p1", "fee_bps": 5,
                          "slippage_pct": 0.01,
                          "source_id": "uniswap_v3_quoter_ethereum",
                          "depth_usd": 500_000}],
            "gross_profit_pct": 2.0,
            "min_pool_tvl_usd_in_route": 500_000.0,
        }
    v = _build_verifier(provider, outcome_loader=loader)
    asyncio.run(v.verify(_candidate()))
    assert captured["c"]["chain"] == "ethereum"
    assert captured["c"]["provider"] == "aave_v3"


def test_category_metadata_vocab_discipline():
    from arbicore.models.category_metadata import KNOWN_CATEGORY_METADATA_KEYS
    async def provider(hm, amt):
        return {
            "hop_legs": [{"venue_id": "p1", "fee_bps": 5,
                          "slippage_pct": 0.01,
                          "source_id": "uniswap_v3_quoter_ethereum",
                          "depth_usd": 500_000}],
            "gross_profit_pct": 2.0,
            "min_pool_tvl_usd_in_route": 500_000.0,
        }
    v = _build_verifier(provider)
    out, _ = asyncio.run(v.verify(_candidate()))
    vocab = KNOWN_CATEGORY_METADATA_KEYS[OpportunityType.FLASH_LOAN_ARBITRAGE]
    unknown = set(out.category_metadata.keys()) - vocab
    assert not unknown, f"unknown vocab: {unknown}"


def test_inv2_verifier_no_emission_bus():
    import arbicore.scanners.flash_loan_arbitrage.verifier as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "_bus.emit(" not in text


def test_inv1_verifier_uses_build_canonical_from_evidence():
    import arbicore.scanners.flash_loan_arbitrage.verifier as mod
    text = open(mod.__file__).read()
    assert "build_canonical_from_evidence" in text
    assert "CanonicalOpportunity(" not in text


# ============================================================================
# Scanner
# ============================================================================

def _make_scanner(*, enabled: bool, quote_provider=None, pools=None):
    cfg = _cfg()
    state = {"enabled": enabled}
    queue = MagicMock()
    queue.upsert_many = AsyncMock(return_value=None)
    queue.claim_batch = AsyncMock(return_value=[])
    queue.mark_processed = AsyncMock(return_value=None)
    bus = MagicMock()
    bus.emit = AsyncMock(return_value=None)
    return FlashLoanArbitrageScanner(
        emission_bus=bus,
        discovery_queue=queue,
        venue_capability_repo=MagicMock(),
        config_loader=lambda: cfg,
        state_loader=lambda: state,
        pool_loader=lambda c: pools or [],
        quote_provider=quote_provider,
    ), bus, queue, cfg, state


def test_scanner_id():
    s, *_ = _make_scanner(enabled=False)
    assert s.scanner_id == "flash_loan_arb"
    assert s.opportunity_type == OpportunityType.FLASH_LOAN_ARBITRAGE


def test_scanner_disabled_at_boot():
    s, *_ = _make_scanner(enabled=False)
    assert not s.is_enabled()
    assert s.quote_provider_is_default


def test_scanner_tick_noops_when_disabled():
    s, bus, queue, *_ = _make_scanner(enabled=False)
    asyncio.run(s._tick())
    bus.emit.assert_not_called()
    queue.claim_batch.assert_not_called()


def test_scanner_emits_when_provider_returns_facts():
    pools = [_pool("p1", "USDC", "WETH"), _pool("p2", "WETH", "USDC")]

    async def provider(hm, amt):
        return {
            "hop_legs": [{"venue_id": "p1", "fee_bps": 5,
                          "slippage_pct": 0.01,
                          "source_id": "uniswap_v3_quoter_ethereum",
                          "depth_usd": 500_000}],
            "gross_profit_pct": 2.0,
            "min_pool_tvl_usd_in_route": 500_000.0,
        }
    s, bus, queue, cfg, _ = _make_scanner(
        enabled=True, quote_provider=provider, pools=pools)
    # Enable Aave + Ethereum so the source emits a candidate.
    cfg["providers"]["aave_v3"]["enabled"] = True
    cfg["chains"]["ethereum"]["enabled"] = True
    cand = _candidate()
    queue.claim_batch = AsyncMock(return_value=[cand])
    asyncio.run(s._tick())
    bus.emit.assert_called_once()
    emitted = bus.emit.call_args.args[0]
    assert isinstance(emitted, CanonicalOpportunity)
    assert emitted.opportunity_type == OpportunityType.FLASH_LOAN_ARBITRAGE
    assert bus.emit.call_args.kwargs["actor"] == "flash_loan_arb_scanner"


def test_scanner_default_provider_yields_denied_unreadable():
    s, bus, queue, *_ = _make_scanner(enabled=True)
    queue.claim_batch = AsyncMock(return_value=[_candidate()])
    asyncio.run(s._tick())
    bus.emit.assert_not_called()
    assert s.stats["denied_venue_unreadable"] == 1


def test_inv2_scanner_single_emit_site():
    import arbicore.scanners.flash_loan_arbitrage.scanner as mod
    text = open(mod.__file__).read()
    assert text.count("self._bus.emit(") == 1


def test_set_quote_provider_changes_default_flag():
    s, *_ = _make_scanner(enabled=False)
    async def p(hm, amt): return None
    s.set_quote_provider(p)
    assert not s.quote_provider_is_default


# ============================================================================
# Invariants
# ============================================================================

def test_emit_site_count_is_six_at_d6_1():
    from pathlib import Path
    scanners_root = Path("/app/backend/arbicore/scanners")
    emit_files = [
        f for f in scanners_root.rglob("scanner.py")
        if "self._bus.emit(" in f.read_text(encoding="utf-8")
    ]
    assert len(emit_files) == 6
    names = sorted(f.parent.name for f in emit_files)
    assert names == ["cex_arbitrage", "cross_chain_arbitrage",
                      "dex_arbitrage", "flash_loan_arbitrage",
                      "funding_arbitrage", "launch_arbitrage"]


def test_flash_loan_package_files_inv2_clean():
    from pathlib import Path
    pkg = Path("/app/backend/arbicore/scanners/flash_loan_arbitrage")
    for f in pkg.glob("*.py"):
        if f.name == "scanner.py":
            continue
        text = f.read_text(encoding="utf-8")
        assert "from ...emission_bus" not in text
        assert "_bus.emit(" not in text


def test_only_verifier_constructs_canonical_in_flash_loan_pkg():
    from pathlib import Path
    pkg = Path("/app/backend/arbicore/scanners/flash_loan_arbitrage")
    for f in pkg.glob("*.py"):
        if f.name in {"__init__.py", "verifier.py"}:
            continue
        text = f.read_text(encoding="utf-8")
        assert "build_canonical_from_evidence" not in text
        assert "CanonicalOpportunity(" not in text


def test_d6_1_routes_registered():
    from arbicore.routes.scanners import router
    paths = {r.path for r in router.routes if "flash_loan_arb" in r.path}
    expected = {
        "/api/arbicore/scanners/flash_loan_arb/status",
        "/api/arbicore/scanners/flash_loan_arb/kill",
        "/api/arbicore/scanners/flash_loan_arb/resume",
        "/api/arbicore/scanners/flash_loan_arb/config",
        "/api/arbicore/scanners/flash_loan_arb/gate-analysis",
        "/api/arbicore/scanners/flash_loan_arb/source-health",
        "/api/arbicore/scanners/flash_loan_arb/providers/{provider_id}/enable",
        "/api/arbicore/scanners/flash_loan_arb/providers/{provider_id}/disable",
        "/api/arbicore/scanners/flash_loan_arb/chains/{chain_id}/enable",
        "/api/arbicore/scanners/flash_loan_arb/chains/{chain_id}/disable",
        "/api/arbicore/scanners/flash_loan_arb/preview",
    }
    assert expected <= paths


def test_composition_factory_present():
    from arbicore.runtime import composition
    assert hasattr(composition, "get_flash_loan_arb_scanner")
    src = open(composition.__file__).read()
    assert "FlashLoanArbitrageScanner" in src
    assert "ARBICORE_SCANNER_FLASH_LOAN_ARB" in src
