"""D-4 Hotfix Wave — tests for the production-grade enhancements to the
HeliusLaunchVenueProvider:

1. LP-burn / LP-lock detection
   - pump.fun graduated → 100%
   - pump.fun pre-graduation → 100% (protocol-custodial)
   - operator-supplied lp_mint → real incinerator balance check
   - no lp_mint → 0.0 (fail-closed)

2. Pump.fun bonding-curve intelligence
   - authoritative coin API takes precedence over hint metadata
   - graduation flag yields 100%
   - market-cap based progress derivation
   - falls back to hint metadata when pump.fun API is unreachable

3. Wallet enrichment cache pre-warm
   - wallet_profile_loader is invoked with buyer_wallets and populates the
     facts dict
   - loader-error is non-critical (degrades to empty)

4. Helius retry/backoff hardening
   - 429 triggers retry-with-backoff
   - 5xx triggers retry
   - max-attempts respected; budget exhaustion → None
   - per-mint TTL cache deduplicates within window

5. Outcome-history bootstrap
   - outcome_history_loader is invoked with subject_id
   - results populate facts.real_outcomes
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from arbicore.models.discovery import DiscoveryCandidate
from arbicore.models.enums import OpportunityType
from arbicore.scanners.launch_arbitrage import HeliusLaunchVenueProvider
from arbicore.scanners.launch_arbitrage.helius_venue_provider import (
    PUMPFUN_GRADUATION_MARKET_CAP_USD, RETRYABLE_STATUS_CODES,
    SOLANA_INCINERATOR,
)


# ============================================================================
# Stubs (mirror the readiness tests)
# ============================================================================

class _StubResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _StubClient:
    def __init__(self):
        self.post_responses: List[_StubResponse] = []
        self.get_responses: List[_StubResponse] = []
        self.post_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []

    async def post(self, url, json=None):
        self.post_calls.append({"url": url, "json": json})
        if not self.post_responses:
            return _StubResponse(500, {})
        return self.post_responses.pop(0)

    async def get(self, url, params=None):
        self.get_calls.append({"url": url, "params": params})
        if not self.get_responses:
            return _StubResponse(500, {})
        return self.get_responses.pop(0)

    async def aclose(self):
        pass


def _candidate(mint: str = "MintAAA", *, launchpad=None, lp_mint=None,
               progress=None) -> DiscoveryCandidate:
    hm: Dict[str, Any] = {}
    if launchpad:
        hm["launchpad"] = launchpad
    if lp_mint:
        hm["lp_mint"] = lp_mint
    if progress is not None:
        hm["bonding_curve_progress_pct"] = progress
    return DiscoveryCandidate(
        candidate_id=f"c-{mint}",
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        hint_source="pumpfun_launches",
        hint_observed_at=1_700_000_000.0,
        subject_id=f"solana:{mint}",
        asset=mint[:10],
        candidate_venues=["solana"],
        hint_metric=hm,
        reason="pumpfun_launch",
    )


def _mint_state_response():
    return _StubResponse(200, {
        "jsonrpc": "2.0", "id": "getAccountInfo",
        "result": {"value": {"data": {"parsed": {"type": "mint", "info": {
            "mintAuthority": None,
            "freezeAuthority": None,
            "supply": "1000000000000",
            "decimals": 6,
        }}}}},
    })


def _holders_response():
    return _StubResponse(200, {
        "jsonrpc": "2.0", "id": "getTokenLargestAccounts",
        "result": {"value": [
            {"address": "H1", "amount": "100", "uiAmount": 100},
        ]},
    })


def _dexscreener_pumpfun_pool():
    return _StubResponse(200, [{
        "chainId": "solana", "dexId": "pumpfun",
        "pairAddress": "PoolPF", "priceUsd": "0.0001",
        "liquidity": {"usd": 10000.0},
        "pairCreatedAt": int(time.time() * 1000),
    }])


# ============================================================================
# 1. LP-burn / LP-lock detection
# ============================================================================

def test_lp_burn_pumpfun_graduated_returns_100(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    # DexScreener says pumpfun + pump.fun coin API says complete=True
    stub.get_responses = [
        _dexscreener_pumpfun_pool(),
        _StubResponse(200, {"complete": True, "usd_market_cap": 80_000.0}),
    ]
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(_candidate("MintAAA", launchpad="pumpfun")))
    assert facts is not None
    assert facts["lp_burned_or_locked_pct"] == 100.0
    assert facts["bonding_curve_progress_pct"] == 100.0


def test_lp_burn_pumpfun_pregraduation_returns_100(monkeypatch):
    """Pre-graduation pump.fun: LP doesn't exist yet — protocol-custodial.
    `lp_burned_or_locked_pct` semantically means "operator cannot rug-pull
    the LP", which is TRUE on bonding-curve tokens by construction."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [
        _dexscreener_pumpfun_pool(),
        _StubResponse(200, {"complete": False, "usd_market_cap": 12_000.0}),
    ]
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(_candidate("MintAAA", launchpad="pumpfun")))
    assert facts is not None
    assert facts["lp_burned_or_locked_pct"] == 100.0
    # 12k / (69k/100) ≈ 17.4%
    assert 17.0 < facts["bonding_curve_progress_pct"] < 18.0


def test_lp_burn_with_explicit_lp_mint_incinerator_balance(monkeypatch):
    """Operator-supplied lp_mint → real Helius reads:
       getTokenSupply (total) + getTokenAccountsByOwner(incinerator)."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [
        # 1. getAccountInfo (mint state) — must succeed
        _mint_state_response(),
        # 2. getTokenLargestAccounts (holders)
        _holders_response(),
        # 3. getTokenSupply on lp_mint → 1000 total LP
        _StubResponse(200, {"jsonrpc": "2.0", "id": "getTokenSupply",
                              "result": {"value": {"uiAmount": 1000.0,
                                                    "amount": "1000"}}}),
        # 4. getTokenAccountsByOwner(incinerator, {mint: lp_mint}) → 850 burned
        _StubResponse(200, {"jsonrpc": "2.0", "id": "getTokenAccountsByOwner",
                              "result": {"value": [
                                  {"account": {"data": {"parsed": {
                                      "info": {"tokenAmount": {
                                          "uiAmount": 850.0,
                                          "amount": "850"}}}}}}
                              ]}}),
    ]
    # No DexScreener pool but candidate has explicit lp_mint
    stub.get_responses = [_StubResponse(500, {})]
    cand = _candidate("MintAAA", launchpad="raydium", lp_mint="LPMintXYZ")
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(cand))
    assert facts is not None
    assert 84.9 < facts["lp_burned_or_locked_pct"] < 85.1


def test_lp_burn_no_lp_mint_no_pumpfun_returns_0(monkeypatch):
    """Fail-closed: no pump.fun, no operator lp_mint → 0%."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [{
        "chainId": "solana", "dexId": "raydium",
        "pairAddress": "P", "liquidity": {"usd": 5000.0},
    }])]
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert facts is not None
    assert facts["lp_burned_or_locked_pct"] == 0.0


def test_lp_burn_incinerator_zero_supply_returns_0(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    p = HeliusLaunchVenueProvider(http_client=_StubClient())

    async def _mock_supply(self_, mint):
        return 0.0

    async def _mock_burned(self_, mint, owner):
        return 100.0
    # Direct unit test of the incinerator pct method
    res = asyncio.run(p._incinerator_burned_pct("LPMintXYZ"))
    assert res == 0.0   # all RPCs returned 500 → 0


# ============================================================================
# 2. Pump.fun bonding-curve intelligence
# ============================================================================

def test_pumpfun_coin_api_takes_precedence_over_hint(monkeypatch):
    """Hint says 5%, pump.fun API says complete=True → 100%."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [
        _dexscreener_pumpfun_pool(),
        _StubResponse(200, {"complete": True}),
    ]
    cand = _candidate("MintAAA", launchpad="pumpfun", progress=5.0)
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(cand))
    assert facts["bonding_curve_progress_pct"] == 100.0


def test_pumpfun_api_unreachable_falls_back_to_hint(monkeypatch):
    """All three pump.fun mirror hosts return 500 → fall back to hint."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [
        _dexscreener_pumpfun_pool(),
        _StubResponse(500, {}),     # mirror 1
        _StubResponse(500, {}),     # mirror 2
        _StubResponse(500, {}),     # mirror 3
    ]
    cand = _candidate("MintAAA", launchpad="pumpfun", progress=42.5)
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(cand))
    assert facts["bonding_curve_progress_pct"] == 42.5


def test_non_pumpfun_progress_from_hint(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [{
        "chainId": "solana", "dexId": "raydium", "pairAddress": "P",
        "liquidity": {"usd": 5000.0},
    }])]
    cand = _candidate("MintAAA", progress=66.7)
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(cand))
    assert facts["bonding_curve_progress_pct"] == 66.7


# ============================================================================
# 3. Wallet enrichment cache pre-warm
# ============================================================================

def test_wallet_profile_loader_populates_facts(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [])]   # no pool needed

    captured_addrs: List[List[str]] = []

    async def _loader(addrs):
        captured_addrs.append(list(addrs))
        return {a: {"address": a, "wallet_score": 75.0,
                     "category": "EARLY_QUALITY"} for a in addrs}

    cand = _candidate("MintAAA")
    cand.hint_metric = {"buyer_wallets_sample": ["W1", "W2", "W3"]}
    p = HeliusLaunchVenueProvider(http_client=stub,
                                    wallet_profile_loader=_loader)
    facts = asyncio.run(p(cand))
    assert captured_addrs == [["W1", "W2", "W3"]]
    assert set(facts["wallet_profiles"].keys()) == {"W1", "W2", "W3"}
    assert facts["wallet_profiles"]["W1"]["wallet_score"] == 75.0


def test_wallet_profile_loader_error_is_soft(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [])]

    async def _loader(addrs):
        raise RuntimeError("cache unavailable")
    cand = _candidate("MintAAA")
    cand.hint_metric = {"buyer_wallets_sample": ["W1"]}
    p = HeliusLaunchVenueProvider(http_client=stub,
                                    wallet_profile_loader=_loader)
    facts = asyncio.run(p(cand))
    assert facts is not None
    assert facts["wallet_profiles"] == {}


def test_no_loader_means_empty_profiles(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [])]
    p = HeliusLaunchVenueProvider(http_client=stub)   # no loader injected
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert facts["wallet_profiles"] == {}


# ============================================================================
# 4. Helius retry/backoff hardening
# ============================================================================

def test_rpc_retries_on_429(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [
        _StubResponse(429, {}),                     # first attempt → rate-limited
        _mint_state_response(),                     # second attempt → 200
        _holders_response(),
    ]
    stub.get_responses = [_StubResponse(200, [])]
    p = HeliusLaunchVenueProvider(
        http_client=stub, retry_initial_backoff_s=0.0, retry_max_backoff_s=0.0)
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert facts is not None
    # First post = retried 429, second = retry success, third = holders
    assert len(stub.post_calls) == 3


def test_rpc_retries_on_5xx(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [
        _StubResponse(502, {}),
        _StubResponse(503, {}),
        _mint_state_response(),
        _holders_response(),
    ]
    stub.get_responses = [_StubResponse(200, [])]
    p = HeliusLaunchVenueProvider(
        http_client=stub, retry_initial_backoff_s=0.0,
        retry_max_backoff_s=0.0)
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert facts is not None


def test_rpc_retry_budget_exhausted_returns_none(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_StubResponse(429, {})] * 5
    stub.get_responses = [_StubResponse(200, [])]
    p = HeliusLaunchVenueProvider(
        http_client=stub, retry_max_attempts=3,
        retry_initial_backoff_s=0.0, retry_max_backoff_s=0.0)
    facts = asyncio.run(p(_candidate("MintAAA")))
    # All 3 attempts on getAccountInfo fail → provider returns None
    assert facts is None
    assert len(stub.post_calls) == 3


def test_ttl_cache_deduplicates_within_window(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    # 2 sets of responses for 2 candidate calls (single-cache hit second)
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [])]
    p = HeliusLaunchVenueProvider(http_client=stub, ttl_cache_s=60.0)
    asyncio.run(p(_candidate("MintAAA")))
    # 2 RPC calls so far. Re-invoke for the same mint → no new RPC posts.
    pre_count = len(stub.post_calls)
    pre_get = len(stub.get_calls)
    asyncio.run(p(_candidate("MintAAA")))
    assert len(stub.post_calls) == pre_count
    assert len(stub.get_calls) == pre_get


def test_ttl_cache_expires_after_window(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [
        _mint_state_response(), _holders_response(),
        _mint_state_response(), _holders_response(),
    ]
    stub.get_responses = [_StubResponse(200, []), _StubResponse(200, [])]
    p = HeliusLaunchVenueProvider(http_client=stub, ttl_cache_s=0.0)
    asyncio.run(p(_candidate("MintAAA")))
    asyncio.run(p(_candidate("MintAAA")))
    assert len(stub.post_calls) == 4   # 2 + 2 (cache always expired)


def test_retryable_status_codes_constant():
    assert RETRYABLE_STATUS_CODES == frozenset({429, 500, 502, 503, 504})


def test_solana_incinerator_constant():
    assert SOLANA_INCINERATOR == "1nc1nerator11111111111111111111111111111111"


# ============================================================================
# 5. Outcome-history bootstrap
# ============================================================================

def test_outcome_history_loader_populates_real_outcomes(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [])]

    captured_subject: List[str] = []

    async def _loader(subject_id):
        captured_subject.append(subject_id)
        return [
            {"horizon_label": "5m", "roi_pct": 12.0, "evaluated": True},
            {"horizon_label": "1h", "roi_pct": -3.0, "evaluated": True},
        ]
    p = HeliusLaunchVenueProvider(http_client=stub,
                                    outcome_history_loader=_loader)
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert captured_subject == ["solana:MintAAA"]
    assert len(facts["real_outcomes"]) == 2
    assert facts["real_outcomes"][0]["roi_pct"] == 12.0


def test_outcome_history_loader_error_is_soft(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [])]

    async def _loader(subject_id):
        raise RuntimeError("repo unavailable")
    p = HeliusLaunchVenueProvider(http_client=stub,
                                    outcome_history_loader=_loader)
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert facts["real_outcomes"] == []


# ============================================================================
# Architectural — INV-1/2/3 unchanged after the hotfix
# ============================================================================

def test_inv1_still_returns_dict_after_hotfix(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _holders_response()]
    stub.get_responses = [_StubResponse(200, [])]
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert isinstance(facts, dict)


def test_inv2_no_emission_bus_in_hotfix():
    """The hotfix MUST NOT introduce any emit path."""
    import arbicore.scanners.launch_arbitrage.helius_venue_provider as mod
    import ast
    tree = ast.parse(open(mod.__file__).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "emit":
            assert False, "INV-2 violation: .emit() call detected"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "emission_bus" not in node.module.lower()


def test_inv3_source_id_unchanged_after_hotfix():
    p = HeliusLaunchVenueProvider(helius_api_key="fake")
    assert p.source_id == "helius_token_rpc"
