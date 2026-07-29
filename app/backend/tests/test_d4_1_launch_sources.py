"""D-4.1 — Launch Intelligence DiscoverySources tests.

Covers:
  - Package importable; class symbols exposed
  - Each source subclasses DiscoverySource
  - INV-1: every discover() returns DiscoveryCandidate ONLY (never Canonical)
  - INV-2: no EmissionBus / .emit() references anywhere in the source module
  - INV-3: aggregator HINT sources are marked HINT-only in SOURCE_REGISTRY;
           the per-source provenance_of_hint is REAL (telemetry-only).
  - Per-source enable flag respected (boot disabled → discover() returns [])
  - Aggregators' parsers parse the documented payload shapes correctly
  - Credentialed sources (Helius, Bitquery) graceful-disable when env absent
  - Bitquery scaffolded_only flag still gates even with key set
  - Per-source health() reflects the documented contract
"""
from __future__ import annotations

import ast
import asyncio
import os
from typing import Any, Dict, List

import pytest

from arbicore.data.provenance import SOURCE_REGISTRY
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import DiscoveryCandidate
from arbicore.models.enums import DataProvenance, OpportunityType
from arbicore.scanners.discovery_source import DiscoverySource
from arbicore.scanners.launch_arbitrage import (
    BitqueryWalletSource,
    DexScreenerFreshLaunchSource,
    HeliusWalletSource,
    JupiterTrendingSource,
    PumpfunLaunchesSource,
)


# ============================================================================
# Mock HTTP client
# ============================================================================

class _Resp:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _MockClient:
    """Sequential mock — every call returns the next configured response."""

    def __init__(self, responses):
        if not isinstance(responses, list):
            responses = [responses]
        self._responses = list(responses)
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append((url, params))
        if not self._responses:
            return _Resp(503, {"error": "no_more_responses"})
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    async def aclose(self):
        pass


def _cfg(*, sources_enabled: Dict[str, bool] | None = None,
         extra_overrides: Dict[str, Dict[str, Any]] | None = None
         ) -> Dict[str, Any]:
    sources_enabled = sources_enabled or {}
    extra_overrides = extra_overrides or {}
    ds: Dict[str, Dict[str, Any]] = {}
    for sid in ("dexscreener_fresh_launch", "pumpfun_launches",
                "jupiter_trending", "helius_wallet_source",
                "bitquery_wallet_source"):
        ds[sid] = {"enabled": sources_enabled.get(sid, False)}
        ds[sid].update(extra_overrides.get(sid, {}))
    # Mirror the substrate config block we care about
    return {"discovery_sources": ds}


# ============================================================================
# Package + ABC compliance
# ============================================================================

def test_package_exports_all_five_sources():
    import arbicore.scanners.launch_arbitrage as pkg
    for cls_name in ("DexScreenerFreshLaunchSource", "PumpfunLaunchesSource",
                     "JupiterTrendingSource", "HeliusWalletSource",
                     "BitqueryWalletSource"):
        assert hasattr(pkg, cls_name)


@pytest.mark.parametrize("cls", [
    DexScreenerFreshLaunchSource, PumpfunLaunchesSource, JupiterTrendingSource,
    HeliusWalletSource, BitqueryWalletSource,
])
def test_each_source_subclasses_discoverysource(cls):
    assert issubclass(cls, DiscoverySource)


def test_each_source_declares_launch_arbitrage():
    for cls in (DexScreenerFreshLaunchSource, PumpfunLaunchesSource,
                 JupiterTrendingSource, HeliusWalletSource, BitqueryWalletSource):
        assert cls.opportunity_types == {OpportunityType.LAUNCH_ARBITRAGE}


# ============================================================================
# Default-disabled (boot dormancy)
# ============================================================================

def test_all_sources_boot_disabled_return_empty():
    """With no per-source `enabled=true` in config, discover() returns []."""
    cfg = _cfg()
    # DexScreener
    s1 = DexScreenerFreshLaunchSource(
        config_loader=lambda: cfg,
        http_client=_MockClient([_Resp(200, [])]),
    )
    # Pumpfun
    s2 = PumpfunLaunchesSource(
        config_loader=lambda: cfg,
        http_client=_MockClient([_Resp(200, [])]),
    )
    # Jupiter
    s3 = JupiterTrendingSource(
        config_loader=lambda: cfg,
        http_client=_MockClient([_Resp(200, [])]),
    )
    # Helius (needs env)
    os.environ["HELIUS_API_KEY"] = "fake-key"
    s4 = HeliusWalletSource(
        config_loader=lambda: cfg,
        token_universe_loader=lambda: ["sometoken"],
        http_client=_MockClient([_Resp(200, [])]),
    )
    # Bitquery
    s5 = BitqueryWalletSource(config_loader=lambda: cfg)

    try:
        for s in (s1, s2, s3, s4, s5):
            assert asyncio.run(s.discover()) == []
    finally:
        os.environ.pop("HELIUS_API_KEY", None)


# ============================================================================
# DexScreenerFreshLaunchSource — happy path
# ============================================================================

def test_dex_fresh_launch_happy_path():
    cfg = _cfg(sources_enabled={"dexscreener_fresh_launch": True})
    payload = [
        {"tokenAddress": "0xabc", "chainId": "ethereum",
         "description": "AwesomeToken", "links": [{"type": "twitter"}],
         "amount": 100},
        {"tokenAddress": "0xdef", "chainId": "base",
         "description": "OtherToken", "links": [], "amount": 50},
    ]
    src = DexScreenerFreshLaunchSource(
        config_loader=lambda: cfg,
        http_client=_MockClient([_Resp(200, payload)]),
    )
    cands = asyncio.run(src.discover())
    assert len(cands) == 2
    for c in cands:
        assert isinstance(c, DiscoveryCandidate)
        assert not isinstance(c, CanonicalOpportunity)
        assert c.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE
        assert c.hint_source == "dexscreener_fresh_launch"
    # Boost amount and socials flag captured
    assert cands[0].hint_metric["boost_amount"] == 100
    assert cands[0].hint_metric["socials_present"] is True
    assert cands[1].hint_metric["socials_present"] is False


def test_dex_fresh_launch_endpoint_rotation():
    """Cursor rotates across the 3 endpoints over successive calls."""
    cfg = _cfg(sources_enabled={"dexscreener_fresh_launch": True})
    client = _MockClient([_Resp(200, []), _Resp(200, []), _Resp(200, [])])
    src = DexScreenerFreshLaunchSource(config_loader=lambda: cfg, http_client=client)
    for _ in range(3):
        asyncio.run(src.discover())
    seen_endpoints = sorted({
        url.replace(DexScreenerFreshLaunchSource.base_url, "")
        for url, _ in client.calls
    })
    assert seen_endpoints == sorted(DexScreenerFreshLaunchSource.ENDPOINT_ROTATION)


def test_dex_fresh_launch_malformed_rows_no_crash():
    cfg = _cfg(sources_enabled={"dexscreener_fresh_launch": True})
    payload = [
        {"tokenAddress": None, "chainId": "ethereum"},
        {"tokenAddress": "0xabc"},  # missing chainId
        {"tokenAddress": "0xdef", "chainId": "base",
         "description": "Good", "amount": 42},
    ]
    src = DexScreenerFreshLaunchSource(
        config_loader=lambda: cfg,
        http_client=_MockClient([_Resp(200, payload)]),
    )
    cands = asyncio.run(src.discover())
    assert len(cands) == 1


def test_dex_fresh_launch_network_error_graceful():
    cfg = _cfg(sources_enabled={"dexscreener_fresh_launch": True})
    src = DexScreenerFreshLaunchSource(
        config_loader=lambda: cfg,
        http_client=_MockClient([RuntimeError("network down")]),
    )
    assert asyncio.run(src.discover()) == []
    h = asyncio.run(src.health())
    assert h.ok is False
    assert h.last_error and "RuntimeError" in h.last_error


# ============================================================================
# PumpfunLaunchesSource
# ============================================================================

def test_pumpfun_happy_path_bonding_curve_window():
    cfg = _cfg(
        sources_enabled={"pumpfun_launches": True},
        extra_overrides={"pumpfun_launches": {
            "min_market_cap_usd": 5_000,
            "max_market_cap_usd": 100_000,
            "max_age_hours": 24,
        }},
    )
    import time as _t
    now = _t.time()
    payload = [
        {"mint": "Mint1", "symbol": "BONK", "name": "BonkPup",
         "usd_market_cap": 30_000, "created_timestamp": now - 7200},
        # Out of window — too small
        {"mint": "Mint2", "symbol": "SMALL", "usd_market_cap": 1_000,
         "created_timestamp": now},
        # Out of window — too large
        {"mint": "Mint3", "symbol": "BIG", "usd_market_cap": 250_000,
         "created_timestamp": now},
        # Too old
        {"mint": "Mint4", "symbol": "OLD", "usd_market_cap": 30_000,
         "created_timestamp": now - 48 * 3600},
    ]
    src = PumpfunLaunchesSource(
        config_loader=lambda: cfg,
        http_client=_MockClient([_Resp(200, payload)]),
    )
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    c = cands[0]
    assert c.asset == "BONK"
    assert c.subject_id == "solana:Mint1"
    assert 0 < c.hint_metric["bonding_curve_progress_pct"] <= 100
    assert c.hint_metric["launchpad"] == "pumpfun"


def test_pumpfun_single_base_success():
    """v3 base returns 200 with payload — candidate emitted."""
    cfg = _cfg(
        sources_enabled={"pumpfun_launches": True},
        extra_overrides={"pumpfun_launches": {
            "min_market_cap_usd": 0, "max_market_cap_usd": 1_000_000,
            "max_age_hours": 1_000_000,
        }},
    )
    import time as _t
    payload = [{"mint": "X", "symbol": "X", "usd_market_cap": 20_000,
                "created_timestamp": _t.time()}]
    client = _MockClient([_Resp(200, payload)])
    src = PumpfunLaunchesSource(config_loader=lambda: cfg, http_client=client)
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    assert len(client.calls) == 1  # only v3 base after upstream-drift cleanup


def test_pumpfun_all_bases_fail_graceful():
    cfg = _cfg(sources_enabled={"pumpfun_launches": True})
    client = _MockClient([RuntimeError("v3 base down")])
    src = PumpfunLaunchesSource(config_loader=lambda: cfg, http_client=client)
    assert asyncio.run(src.discover()) == []
    h = asyncio.run(src.health())
    assert h.ok is False
    assert "RuntimeError" in (h.last_error or "")


# ============================================================================
# JupiterTrendingSource
# ============================================================================

def test_jupiter_trending_volume_floor_filter():
    cfg = _cfg(
        sources_enabled={"jupiter_trending": True},
        extra_overrides={"jupiter_trending": {"min_volume_usd_24h": 50_000}},
    )
    payload = [
        {"address": "Tok1", "symbol": "GOOD", "volume24h": 100_000, "priceUsd": 1.0},
        {"address": "Tok2", "symbol": "THIN", "volume24h": 1_000, "priceUsd": 0.01},
    ]
    src = JupiterTrendingSource(
        config_loader=lambda: cfg,
        http_client=_MockClient([_Resp(200, payload)]),
    )
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    assert cands[0].asset == "GOOD"


def test_jupiter_single_base_success():
    """Single base (post-2025 datapi.jup.ag) returns 200 with payload."""
    cfg = _cfg(sources_enabled={"jupiter_trending": True})
    # New schema: {"pools": [{...,"baseAsset":{...}}]}
    payload = {"pools": [
        {"chain": "solana", "volume24h": 9_999_999,
         "baseAsset": {"id": "Mint1", "symbol": "GOOD",
                       "holderCount": 5000,
                       "audit": {"topHoldersPercentage": 25.0}}},
    ]}
    client = _MockClient([_Resp(200, payload)])
    src = JupiterTrendingSource(config_loader=lambda: cfg, http_client=client)
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    assert cands[0].asset == "GOOD"
    # New schema propagates holder enrichment into hint_metric
    assert cands[0].hint_metric.get("holder_count") == 5000
    assert cands[0].hint_metric.get("top10_concentration_pct") == 25.0
    assert len(client.calls) == 1


# ============================================================================
# HeliusWalletSource — graceful disable + happy path
# ============================================================================

def test_helius_graceful_disable_when_env_absent(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    src = HeliusWalletSource(
        config_loader=lambda: _cfg(sources_enabled={"helius_wallet_source": True}),
        token_universe_loader=lambda: ["mint1"],
        http_client=_MockClient([_Resp(200, [])]),
    )
    assert asyncio.run(src.discover()) == []
    h = asyncio.run(src.health())
    assert h.ok is False
    assert h.last_error == "credentials_missing:HELIUS_API_KEY"


def test_helius_empty_universe_returns_empty(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    src = HeliusWalletSource(
        config_loader=lambda: _cfg(sources_enabled={"helius_wallet_source": True}),
        token_universe_loader=lambda: [],
        http_client=_MockClient([_Resp(200, [])]),
    )
    cands = asyncio.run(src.discover())
    assert cands == []
    h = asyncio.run(src.health())
    # Empty universe is normal — no error
    assert h.last_error is None or h.last_error == ""


def test_helius_happy_path_emits_candidate(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    # Helius parsed-tx payload shape
    payload = [
        {"signature": "sig1", "feePayer": "wallet_aaa", "timestamp": 1_700_000_000},
        {"signature": "sig2", "feePayer": "wallet_bbb", "timestamp": 1_700_000_010},
        {"signature": "sig3", "feePayer": "wallet_ccc", "timestamp": 1_700_000_020},
    ]
    src = HeliusWalletSource(
        config_loader=lambda: _cfg(sources_enabled={"helius_wallet_source": True}),
        token_universe_loader=lambda: ["MintX"],
        http_client=_MockClient([_Resp(200, payload)]),
    )
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c, DiscoveryCandidate)
    assert not isinstance(c, CanonicalOpportunity)
    assert c.hint_source == "helius_wallet_source"
    assert c.subject_id == "solana:MintX"
    assert c.hint_metric["recent_buyer_count"] == 3
    assert len(c.hint_metric["buyer_wallets_sample"]) == 3
    assert c.hint_metric["token_mint"] == "MintX"


def test_helius_round_robin_token_cursor(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    # 3 cycles, 3 tokens → each token polled exactly once in 3 cycles
    client = _MockClient([_Resp(200, []), _Resp(200, []), _Resp(200, [])])
    universe = ["m1", "m2", "m3"]
    src = HeliusWalletSource(
        config_loader=lambda: _cfg(sources_enabled={"helius_wallet_source": True}),
        token_universe_loader=lambda: universe,
        http_client=client,
    )
    for _ in range(3):
        asyncio.run(src.discover())
    polled_tokens = sorted({url.split("/")[-2] for url, _ in client.calls})
    assert polled_tokens == ["m1", "m2", "m3"]


def test_helius_network_error_graceful(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    src = HeliusWalletSource(
        config_loader=lambda: _cfg(sources_enabled={"helius_wallet_source": True}),
        token_universe_loader=lambda: ["MintX"],
        http_client=_MockClient([RuntimeError("upstream")]),
    )
    assert asyncio.run(src.discover()) == []
    h = asyncio.run(src.health())
    assert h.ok is False
    assert "RuntimeError" in (h.last_error or "")


# ============================================================================
# BitqueryWalletSource — scaffolded but never live at D-4.1
# ============================================================================

def test_bitquery_scaffolded_state_returns_empty(monkeypatch):
    """Default config has scaffolded_only=True via DEFAULT_LAUNCH_ARB_CONFIG."""
    monkeypatch.delenv("BITQUERY_API_KEY", raising=False)
    cfg = _cfg(extra_overrides={"bitquery_wallet_source": {"scaffolded_only": True}})
    src = BitqueryWalletSource(config_loader=lambda: cfg)
    assert asyncio.run(src.discover()) == []
    h = asyncio.run(src.health())
    assert h.ok is False
    assert h.last_error == "scaffolded_only:true"


def test_bitquery_scaffolded_gate_beats_enabled(monkeypatch):
    """Even with enabled=True + key set, scaffolded_only still gates."""
    monkeypatch.setenv("BITQUERY_API_KEY", "fake")
    cfg = _cfg(
        sources_enabled={"bitquery_wallet_source": True},
        extra_overrides={"bitquery_wallet_source": {"scaffolded_only": True}},
    )
    src = BitqueryWalletSource(config_loader=lambda: cfg)
    assert asyncio.run(src.discover()) == []
    h = asyncio.run(src.health())
    assert h.ok is False
    assert h.last_error == "scaffolded_only:true"


def test_bitquery_unscaffolded_but_no_key_graceful(monkeypatch):
    monkeypatch.delenv("BITQUERY_API_KEY", raising=False)
    cfg = _cfg(
        sources_enabled={"bitquery_wallet_source": True},
        extra_overrides={"bitquery_wallet_source": {"scaffolded_only": False}},
    )
    src = BitqueryWalletSource(config_loader=lambda: cfg)
    assert asyncio.run(src.discover()) == []
    h = asyncio.run(src.health())
    assert h.ok is False
    assert h.last_error == "credentials_missing:BITQUERY_API_KEY"


# ============================================================================
# INV-3 — registry markers
# ============================================================================

@pytest.mark.parametrize("source_id", [
    "dexscreener_fresh_launch", "pumpfun_launches", "jupiter_trending",
])
def test_inv_3_aggregator_marked_hint_only(source_id):
    entry = SOURCE_REGISTRY[source_id]
    assert "HINT-ONLY" in entry.reason
    assert "INV-3" in entry.reason
    assert entry.provenance == DataProvenance.REAL


# ============================================================================
# INV-2 — no emission bus references in any source module
# ============================================================================

def _module_has_no_emission_bus_usage(mod) -> bool:
    tree = ast.parse(open(mod.__file__).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "EmissionBus":
            return False
        if (isinstance(node, ast.Attribute) and node.attr == "emit"
                and isinstance(node.ctx, ast.Load)):
            return False
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "emit":
                return False
    return True


def test_inv_2_no_emission_bus_in_launch_sources_module():
    import arbicore.scanners.launch_arbitrage.sources as mod
    assert _module_has_no_emission_bus_usage(mod)


# ============================================================================
# Mock fixture sanity (REUSE WITH REFINEMENT from legacy)
# ============================================================================

def test_mock_wallet_provider_deterministic():
    from tests.fixtures.mock_wallet_provider import MockWalletProvider
    p = MockWalletProvider(seed=42)
    a = asyncio.run(p.recent_buyers("tokX", reference_ts=1_700_000_000))
    b = asyncio.run(p.recent_buyers("tokX", reference_ts=1_700_000_000))
    assert a == b   # deterministic per (seed, token, reference_ts)
    assert all("wallet" in r for r in a)


def test_mock_wallet_provider_distinct_per_token():
    from tests.fixtures.mock_wallet_provider import MockWalletProvider
    p = MockWalletProvider(seed=42)
    a = asyncio.run(p.recent_buyers("tokA", reference_ts=1_700_000_000))
    b = asyncio.run(p.recent_buyers("tokB", reference_ts=1_700_000_000))
    assert a != b


# ============================================================================
# Dormancy invariants — D-4.1 must NOT ship D-4.2+ surfaces
# ============================================================================

def test_no_launch_scanner_orchestrator_yet():
    """D-4.5 lands the orchestrator — assertion INVERTED at D-4.5 landing."""
    import arbicore.scanners.launch_arbitrage.scanner as mod  # noqa: F401
    assert hasattr(mod, "LaunchArbitrageScanner")


def test_no_launch_verifier_yet():
    """D-4.4 ships the verifier — assertion INVERTED at D-4.4 landing."""
    import arbicore.scanners.launch_arbitrage.verifier as mod  # noqa: F401
    assert hasattr(mod, "LaunchOpportunityVerifier")


def test_no_wallet_enrichment_orchestrator_yet():
    """D-4.2 lands the wallet enrichment pipeline."""
    from pathlib import Path
    p = Path("/app/backend/arbicore/scanners/launch_arbitrage/wallet_enrichment.py")
    assert not p.exists()
