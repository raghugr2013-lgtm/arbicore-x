"""Tests for D-3.1 — DEX pool discovery sources + DEXQuoteCache + DexScreener HINT.

Covers:
  - BaseDEXPoolSource ABC contract
  - Source factory builds exactly 8 venue sources
  - Source IDs match the SOURCE_REGISTRY universe
  - Graceful disable when credentials_env_var absent
  - Cross-DEX divergence math (DEXQuoteCache + observed-pool emission)
  - INV-1: discover() returns DiscoveryCandidate only (never CanonicalOpportunity)
  - INV-2: no EmissionBus calls in this module
  - INV-3 attribution: per-source registry_source_id matches the venue quoter id
  - SourceHealth shape (graceful-disable + happy path)
  - DexScreener HINT round-robin + threshold gating
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from arbicore.models.discovery import DiscoveryCandidate, SourceHealth
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.enums import OpportunityType
from arbicore.scanners.dex_arbitrage import (
    DEXQuoteCache, BaseDEXPoolSource,
    UniswapV3PoolSource, PancakeV3PoolSource, AerodromePoolSource,
    RaydiumPoolSource, build_all_dex_sources,
)
from arbicore.scanners.discovery.dexscreener_hint import DexScreenerHintSource
from arbicore.data.provenance import SOURCE_REGISTRY


# ============================================================================
# DEXQuoteCache
# ============================================================================

def test_quote_cache_basic_put_get():
    c = DEXQuoteCache()
    c.put(chain="ethereum", dex="uniswap_v3", pair_canonical="WETH/USDC",
          mid=2000.0, pool_liquidity_usd=10_000_000.0,
          source_id="uniswap_v3_quoter_ethereum")
    cq = c.get(chain="ethereum", dex="uniswap_v3", pair_canonical="WETH/USDC")
    assert cq is not None
    assert cq.mid == 2000.0


def test_quote_cache_reference_mid_is_median():
    c = DEXQuoteCache()
    c.put(chain="ethereum", dex="uniswap_v3", pair_canonical="WETH/USDC",
          mid=2000.0, pool_liquidity_usd=None,
          source_id="uniswap_v3_quoter_ethereum")
    c.put(chain="arbitrum", dex="uniswap_v3", pair_canonical="WETH/USDC",
          mid=2010.0, pool_liquidity_usd=None,
          source_id="uniswap_v3_quoter_arbitrum")
    c.put(chain="base", dex="uniswap_v3", pair_canonical="WETH/USDC",
          mid=2030.0, pool_liquidity_usd=None,
          source_id="uniswap_v3_quoter_base")
    assert c.reference_mid(pair_canonical="WETH/USDC") == 2010.0


def test_quote_cache_divergence_bps():
    c = DEXQuoteCache()
    c.put(chain="ethereum", dex="uniswap_v3", pair_canonical="WETH/USDC",
          mid=2000.0, pool_liquidity_usd=None, source_id="x")
    c.put(chain="arbitrum", dex="uniswap_v3", pair_canonical="WETH/USDC",
          mid=2020.0, pool_liquidity_usd=None, source_id="y")
    # arbitrum vs reference (median = 2010):  (2020-2010)/2010 * 10000 ≈ 49.75 bps
    div = c.divergence_bps(chain="arbitrum", dex="uniswap_v3",
                           pair_canonical="WETH/USDC")
    assert div is not None
    assert abs(div - 49.75) < 0.5


def test_quote_cache_returns_none_when_stale():
    """ttl=0 → any positive-age entry is stale; verified by sleeping minimal."""
    c = DEXQuoteCache(ttl_s=0.0)
    c.put(chain="ethereum", dex="uniswap_v3", pair_canonical="WETH/USDC",
          mid=2000.0, pool_liquidity_usd=None, source_id="x")
    import time as _t
    _t.sleep(0.01)
    assert c.get(chain="ethereum", dex="uniswap_v3",
                 pair_canonical="WETH/USDC") is None


# ============================================================================
# Source class hierarchy
# ============================================================================

def test_base_source_is_abstract():
    with pytest.raises(TypeError):
        BaseDEXPoolSource(
            quote_cache=DEXQuoteCache(),
            config_loader=lambda: {},
        )


def test_subclass_without_dex_chain_raises():
    class _Bad(BaseDEXPoolSource):
        async def _poll_pool_mids(self, active_pairs):
            return []
    with pytest.raises(TypeError):
        _Bad(quote_cache=DEXQuoteCache(), config_loader=lambda: {})


# ============================================================================
# Factory
# ============================================================================

def test_build_all_dex_sources_universe():
    sources = build_all_dex_sources(
        quote_cache=DEXQuoteCache(), config_loader=lambda: {},
    )
    assert len(sources) == 8
    ids = sorted(s.source_id for s in sources)
    expected = sorted([
        "venue_dex_pool:uniswap_v3:ethereum",
        "venue_dex_pool:uniswap_v3:arbitrum",
        "venue_dex_pool:uniswap_v3:base",
        "venue_dex_pool:pancake_v3:bnb",
        "venue_dex_pool:pancake_v3:arbitrum",
        "venue_dex_pool:pancake_v3:base",
        "venue_dex_pool:aerodrome:base",
        "venue_dex_pool:raydium:solana",
    ])
    assert ids == expected
    # All registry_source_id values exist in SOURCE_REGISTRY (INV-3 attribution)
    for s in sources:
        assert s.registry_source_id in SOURCE_REGISTRY
    # Every source declares DEX_ARBITRAGE
    for s in sources:
        assert s.opportunity_types == {OpportunityType.DEX_ARBITRAGE}


# ============================================================================
# Graceful disable
# ============================================================================

def test_evm_v3_sources_graceful_disable_without_key(monkeypatch):
    monkeypatch.delenv("GRAPH_GATEWAY_API_KEY", raising=False)
    src = UniswapV3PoolSource(
        chain="ethereum",
        quote_cache=DEXQuoteCache(),
        config_loader=lambda: {"tier_a_pairs": ["WETH/USDC@ethereum"]},
    )
    assert src.credentials_available is False
    candidates = asyncio.run(src.discover())
    assert candidates == []
    health = asyncio.run(src.health())
    assert health.ok is False
    assert health.last_error and "credentials_missing" in health.last_error


def test_aerodrome_source_has_no_credentials_gate(monkeypatch):
    """Aerodrome uses heritage DexScreener proxy — no Graph key required."""
    monkeypatch.delenv("GRAPH_GATEWAY_API_KEY", raising=False)
    src = AerodromePoolSource(
        quote_cache=DEXQuoteCache(),
        config_loader=lambda: {"tier_a_pairs": ["AERO/USDC@base"]},
    )
    assert src.credentials_available is True
    candidates = asyncio.run(src.discover())
    assert candidates == []  # stubbed _poll_pool_mids returns []


def test_raydium_source_graceful_disable(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    src = RaydiumPoolSource(
        quote_cache=DEXQuoteCache(),
        config_loader=lambda: {"tier_a_pairs": ["SOL/USDC@solana"]},
    )
    assert src.credentials_available is False
    assert asyncio.run(src.discover()) == []


# ============================================================================
# Active-pair filtering
# ============================================================================

def test_source_filters_pairs_to_own_chain():
    src = UniswapV3PoolSource(
        chain="arbitrum",
        quote_cache=DEXQuoteCache(),
        config_loader=lambda: {"tier_a_pairs": [
            "WETH/USDC@ethereum", "WETH/USDC@arbitrum", "ARB/USDC@arbitrum",
            "SOL/USDC@solana",
        ]},
    )
    pairs = src._active_pairs_for_self(src._config_loader())
    assert pairs == ["WETH/USDC@arbitrum", "ARB/USDC@arbitrum"]


# ============================================================================
# Divergence → DiscoveryCandidate emission (INV-1 typing)
# ============================================================================

def test_source_emits_candidate_when_divergence_exceeds_threshold(monkeypatch):
    """Inject a non-empty _poll_pool_mids result + seed cross-source quotes
    into the shared cache; assert one DiscoveryCandidate is emitted, fully
    typed (INV-1 — never a CanonicalOpportunity)."""
    monkeypatch.setenv("GRAPH_GATEWAY_API_KEY", "fake-key")
    cache = DEXQuoteCache()
    # Pre-seed the cache with a "competing" DEX's quote so divergence math
    # can produce a finite ref_mid.
    cache.put(
        chain="arbitrum", dex="uniswap_v3", pair_canonical="WETH/USDC@ethereum",
        mid=2000.0, pool_liquidity_usd=10_000_000.0,
        source_id="uniswap_v3_quoter_arbitrum",
    )

    class _PatchedEth(UniswapV3PoolSource):
        async def _poll_pool_mids(self, active_pairs):
            return [{
                "pair_canonical": "WETH/USDC@ethereum",
                "mid": 2050.0,            # +250 bps vs the cached ref
                "pool_liquidity_usd": 12_000_000.0,
                "pool_address": "0x" + "ab" * 20,
            }]

    src = _PatchedEth(
        chain="ethereum", quote_cache=cache,
        config_loader=lambda: {
            "tier_a_pairs": ["WETH/USDC@ethereum"],
            "discovery_sources": {
                "venue_dex_pool:uniswap_v3:ethereum": {
                    "pool_divergence_threshold_bps": 30,
                },
            },
        },
    )
    candidates = asyncio.run(src.discover())
    assert len(candidates) == 1
    c = candidates[0]
    assert isinstance(c, DiscoveryCandidate)
    # INV-1: not a CanonicalOpportunity
    assert not isinstance(c, CanonicalOpportunity)
    assert c.opportunity_type == OpportunityType.DEX_ARBITRAGE
    assert c.hint_source == "venue_dex_pool:uniswap_v3:ethereum"
    assert c.subject_id == "WETH/USDC@ethereum"
    assert c.asset == "WETH"
    # Divergence reflected in metric
    assert "divergence_bps" in c.hint_metric
    assert c.hint_metric["self_dex"] == "uniswap_v3"
    assert c.hint_metric["self_chain"] == "ethereum"


def test_source_skips_emit_when_only_one_observer(monkeypatch):
    """Even if observed-mid differs wildly from cache, refuse to emit if no
    second DEX has reported a fresh mid for the same pair."""
    monkeypatch.setenv("GRAPH_GATEWAY_API_KEY", "fake-key")

    class _SoloObserver(UniswapV3PoolSource):
        async def _poll_pool_mids(self, active_pairs):
            return [{
                "pair_canonical": "WETH/USDC@ethereum",
                "mid": 2050.0, "pool_liquidity_usd": 1, "pool_address": "0xabc",
            }]

    cache = DEXQuoteCache()
    src = _SoloObserver(
        chain="ethereum", quote_cache=cache,
        config_loader=lambda: {"tier_a_pairs": ["WETH/USDC@ethereum"]},
    )
    candidates = asyncio.run(src.discover())
    assert candidates == []


# ============================================================================
# DexScreener HINT source
# ============================================================================

def test_dexscreener_hint_construction_no_credentials():
    src = DexScreenerHintSource(config_loader=lambda: {})
    assert src.source_id == "dexscreener_hint"
    assert src.credentials_env_var is None
    assert src.tier == 2
    assert src.opportunity_types == {OpportunityType.DEX_ARBITRAGE}
    # SOURCE_REGISTRY classifies dexscreener_hint
    assert "dexscreener_hint" in SOURCE_REGISTRY


def test_dexscreener_hint_empty_universe():
    src = DexScreenerHintSource(config_loader=lambda: {})
    assert asyncio.run(src.discover()) == []


def test_dexscreener_hint_emits_when_divergence_exceeds_threshold():
    class _Patched(DexScreenerHintSource):
        async def _fetch_pair_dex_quotes(self, pair_canonical):
            return [
                {"dex": "uniswap_v3", "chain": "ethereum", "mid": 2000.0,
                 "h24_volume_usd": 100_000_000.0},
                {"dex": "pancake_v3", "chain": "bnb", "mid": 2020.0,
                 "h24_volume_usd": 100_000.0},
            ]

    src = _Patched(config_loader=lambda: {
        "tier_a_pairs": ["WETH/USDC@ethereum"],
        "discovery_sources": {"dexscreener_hint": {"ds_divergence_threshold_bps": 40}},
    })
    candidates = asyncio.run(src.discover())
    assert len(candidates) == 1
    c = candidates[0]
    assert isinstance(c, DiscoveryCandidate)
    assert not isinstance(c, CanonicalOpportunity)
    assert c.hint_source == "dexscreener_hint"
    assert c.hint_metric["observation_count"] == 2
    assert c.hint_metric["divergence_bps"] >= 40


def test_dexscreener_hint_volume_floor_filters_thin_dexes():
    class _Patched(DexScreenerHintSource):
        async def _fetch_pair_dex_quotes(self, pair_canonical):
            return [
                {"dex": "uniswap_v3", "chain": "ethereum", "mid": 2000.0,
                 "h24_volume_usd": 100_000_000.0},
                {"dex": "pancake_v3", "chain": "bnb", "mid": 2200.0,
                 "h24_volume_usd": 1_000.0},   # below volume floor
            ]

    src = _Patched(config_loader=lambda: {
        "tier_a_pairs": ["WETH/USDC@ethereum"],
        "discovery_sources": {"dexscreener_hint": {
            "ds_divergence_threshold_bps": 40, "volume_floor_usd": 50_000,
        }},
    })
    candidates = asyncio.run(src.discover())
    assert candidates == []  # filtered down to 1 observation → no divergence


# ============================================================================
# INV-2: no EmissionBus calls anywhere in D-3.1 source / hint modules
# ============================================================================

def _module_has_no_emission_bus_usage(mod) -> bool:
    """AST-walk: no `EmissionBus` Name node and no `.emit()` Call.
    Docstring mentions are NOT flagged (they're string constants, not names)."""
    import ast
    tree = ast.parse(open(mod.__file__).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "EmissionBus":
            return False
        if (isinstance(node, ast.Attribute) and node.attr == "emit"
                and isinstance(node.ctx, ast.Load)):
            # any .emit attribute reference in code (not in a string)
            return False
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "emit":
                return False
    return True


def test_inv_2_no_emission_bus_in_dex_sources_module():
    import arbicore.scanners.dex_arbitrage.sources as mod
    assert _module_has_no_emission_bus_usage(mod)


def test_inv_2_no_emission_bus_in_dexscreener_hint_module():
    import arbicore.scanners.discovery.dexscreener_hint as mod
    assert _module_has_no_emission_bus_usage(mod)


def test_inv_2_no_emission_bus_in_quote_cache_module():
    import arbicore.scanners.dex_arbitrage.quote_cache as mod
    assert _module_has_no_emission_bus_usage(mod)
