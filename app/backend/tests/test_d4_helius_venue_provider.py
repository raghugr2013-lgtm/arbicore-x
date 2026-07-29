"""Operational readiness — tests for the reference HeliusLaunchVenueProvider.

These tests do not hit the network. They mock httpx responses to validate:
  - Graceful disable when HELIUS_API_KEY is absent (returns None)
  - mint state extraction (mintAuthority null → revoked True)
  - getTokenLargestAccounts projection to verifier holder shape
  - DexScreener best-pool selection (sort by USD liquidity)
  - facts dict has every key the verifier reads
  - INV-3: source_id == 'helius_token_rpc' (REAL classification)
  - INV-1: returns dict, NEVER a CanonicalOpportunity
  - Composition wiring: scanner.venue_provider_is_default reflects opt-in
  - End-to-end: provider+verifier combination produces a CONFIRMED canonical
    against a synthetic happy-path token, OR DENIED on conservative defaults
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import OpportunityType
from arbicore.scanners.launch_arbitrage import (
    HeliusLaunchVenueProvider, LaunchArbitrageScanner,
)
from arbicore.scanners.launch_arbitrage.scanner import _noop_venue_provider


# ============================================================================
# httpx mocking
# ============================================================================

class _StubResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _StubClient:
    """Minimal httpx.AsyncClient stub. ``post`` services Helius RPC;
    ``get`` services DexScreener."""

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


def _candidate(mint: str = "MintAAA") -> DiscoveryCandidate:
    return DiscoveryCandidate(
        candidate_id=f"c-{mint}",
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        hint_source="dexscreener_fresh_launch",
        hint_observed_at=1_700_000_000.0,
        subject_id=f"solana:{mint}",
        asset=mint[:10],
        candidate_venues=["solana"],
        hint_metric={"boost_amount": 10.0, "socials_present": True},
        reason="dexscreener_fresh_launch:/token-profiles/latest/v1",
    )


# ============================================================================
# Construction / dormancy
# ============================================================================

def test_provider_without_helius_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    p = HeliusLaunchVenueProvider()
    assert p.credentials_available is False


def test_provider_returns_none_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    p = HeliusLaunchVenueProvider()
    facts = asyncio.run(p(_candidate()))
    assert facts is None


def test_provider_returns_none_when_subject_id_has_no_mint():
    cand = _candidate("")
    cand.subject_id = "ethereum:0xabc"
    p = HeliusLaunchVenueProvider(helius_api_key="fake-key")
    facts = asyncio.run(p(cand))
    # No `solana:` prefix and no hint_metric.token_mint
    assert facts is None


# ============================================================================
# Happy-path projection
# ============================================================================

def _mint_state_response():
    return _StubResponse(200, {
        "jsonrpc": "2.0", "id": "getAccountInfo",
        "result": {"value": {
            "lamports": 1, "owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "executable": False, "rentEpoch": 0,
            "data": {
                "program": "spl-token",
                "parsed": {
                    "type": "mint",
                    "info": {
                        "mintAuthority": None,            # revoked
                        "freezeAuthority": None,          # revoked
                        "supply": "1000000000000",
                        "decimals": 6,
                    },
                },
            },
        }},
    })


def _largest_holders_response():
    return _StubResponse(200, {
        "jsonrpc": "2.0", "id": "getTokenLargestAccounts",
        "result": {"value": [
            {"address": "Holder1", "amount": "500000000000", "uiAmount": 500000},
            {"address": "Holder2", "amount": "300000000000", "uiAmount": 300000},
            {"address": "Holder3", "amount": "100000000000", "uiAmount": 100000},
        ]},
    })


def _dexscreener_response():
    return _StubResponse(200, [
        {
            "chainId": "solana", "dexId": "raydium",
            "pairAddress": "PoolXYZ",
            "priceUsd": "0.000123",
            "liquidity": {"usd": 50000.0},
            "volume": {"h24": 12345.0},
            "priceChange": {"h24": 12.5},
            "pairCreatedAt": 1_700_000_000_000,
        },
        {
            "chainId": "solana", "dexId": "pumpfun",
            "pairAddress": "PoolPF",
            "priceUsd": "0.00009",
            "liquidity": {"usd": 5000.0},        # lower — sorts second
            "pairCreatedAt": 1_700_000_000_000,
        },
    ])


def test_provider_happy_path_returns_full_facts_dict(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _largest_holders_response()]
    stub.get_responses = [_dexscreener_response()]
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert facts is not None
    # INV-3 source classification
    assert facts["source_id"] == "helius_token_rpc"
    # Mint state
    assert facts["mint_authority_revoked"] is True
    assert facts["freeze_authority_revoked"] is True
    assert facts["total_supply"] == 1000000.0     # 1e12 / 1e6
    # Holders
    assert len(facts["holders"]) == 3
    assert facts["holders"][0]["address"] == "Holder1"
    assert facts["holders"][0]["balance"] == 500000.0
    # DexScreener — best pool (highest liquidity) is raydium
    assert facts["launchpad"] == "raydium"
    assert facts["primary_venue_id"] == "raydium:solana:PoolXYZ"
    assert facts["secondary_venue_id"].startswith("raydium_secondary:")
    assert facts["listing_price_usd"] == 0.000123
    assert facts["liquidity_usd"] == 50000.0
    # token_intel shape consumed by PhaseClassifier+Timeline
    assert facts["token_intel"]["launchpad_id"] == "raydium"
    assert facts["token_intel"]["liquidity_usd"] == 50000.0
    # Conservative defaults (gap §6) — fail-closed
    assert facts["lp_burned_or_locked_pct"] == 0.0
    assert facts["bonding_curve_progress_pct"] is None
    assert facts["wallet_profiles"] == {}
    # Bootstrap state
    assert facts["real_outcomes"] == []
    assert facts["synthetic_outcomes"] == []


def test_provider_facts_dict_has_all_verifier_required_keys(monkeypatch):
    """The verifier's facts protocol — every key it reads in verify()
    must be present in the facts dict the provider returns."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _largest_holders_response()]
    stub.get_responses = [_dexscreener_response()]
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(_candidate("MintAAA")))
    REQUIRED = {
        "primary_venue_id", "secondary_venue_id", "chain", "source_id",
        "listing_price_usd", "liquidity_usd", "primary_fee_bps",
        "secondary_fee_bps", "slippage_primary_pct", "slippage_secondary_pct",
        "mint_authority_revoked", "freeze_authority_revoked",
        "lp_burned_or_locked_pct", "total_supply", "holders", "launchpad",
        "age_hours", "buyer_wallets", "wallet_profiles", "signal_categories",
        "real_outcomes", "synthetic_outcomes", "token_intel", "signals",
        "verified_at_ts", "notional_usd", "bonding_curve_progress_pct",
    }
    missing = REQUIRED - set(facts.keys())
    assert not missing, f"provider facts dict missing required keys: {missing}"


def test_provider_returns_none_when_mint_account_missing(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    stub = _StubClient()
    # getAccountInfo returns null value (account doesn't exist)
    stub.post_responses = [_StubResponse(200, {
        "jsonrpc": "2.0", "id": "getAccountInfo",
        "result": {"value": None},
    })]
    p = HeliusLaunchVenueProvider(http_client=stub)
    assert asyncio.run(p(_candidate("MintBAD"))) is None


def test_provider_returns_none_on_rpc_http_error(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    stub = _StubClient()
    stub.post_responses = [_StubResponse(500, {})]
    p = HeliusLaunchVenueProvider(http_client=stub)
    assert asyncio.run(p(_candidate("MintXYZ"))) is None


def test_provider_dexscreener_failure_is_soft(monkeypatch):
    """DexScreener failure is non-critical — provider still returns facts
    with default venues (so the verifier can still run mint/freeze gates)."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _largest_holders_response()]
    stub.get_responses = [_StubResponse(500, {})]   # dexscreener fails
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(_candidate("MintAAA")))
    assert facts is not None
    assert facts["primary_venue_id"].startswith("unknown:solana:")
    assert facts["liquidity_usd"] == 0.0
    # Critical gate-relevant fields preserved
    assert facts["mint_authority_revoked"] is True
    assert facts["freeze_authority_revoked"] is True


def test_provider_slippage_estimate_bounded(monkeypatch):
    """Slippage estimate must be bounded: 0% lower, 10% upper cap when
    liquidity is shallow/zero."""
    assert HeliusLaunchVenueProvider._estimate_slippage_pct(250, 0) == 10.0
    # Deep pool → very small slip
    assert HeliusLaunchVenueProvider._estimate_slippage_pct(
        250, 10_000_000) < 0.1
    # Mid pool — bounded under cap
    val = HeliusLaunchVenueProvider._estimate_slippage_pct(250, 50_000)
    assert 0.0 <= val <= 10.0


# ============================================================================
# Architectural invariants
# ============================================================================

def test_provider_inv1_returns_dict_never_canonical(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    stub = _StubClient()
    stub.post_responses = [_mint_state_response(), _largest_holders_response()]
    stub.get_responses = [_dexscreener_response()]
    p = HeliusLaunchVenueProvider(http_client=stub)
    facts = asyncio.run(p(_candidate("MintAAA")))
    # INV-1: provider must never construct a CanonicalOpportunity
    assert not isinstance(facts, CanonicalOpportunity)
    assert isinstance(facts, dict)


def test_provider_inv2_does_not_import_emission_bus():
    """Provider module must not depend on EmissionBus (INV-2).
    Strips docstrings/comments before scanning to avoid matching the
    invariant-explanation prose at the top of the module."""
    import arbicore.scanners.launch_arbitrage.helius_venue_provider as mod
    import ast
    tree = ast.parse(open(mod.__file__).read())
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.extend(a.name for a in node.names)
            if node.module:
                imported_names.append(node.module)
        elif isinstance(node, ast.Import):
            imported_names.extend(a.name for a in node.names)
    # Strip docstrings — verify no actual import of EmissionBus exists
    for n in imported_names:
        assert "emission_bus" not in n.lower(), \
            f"INV-2 violation: provider imports {n}"
    # Also AST-walk all attribute accesses — no .emit() call to anything
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "emit":
            assert False, "INV-2 violation: provider has a .emit() call"


def test_provider_inv3_source_id_real_classification():
    p = HeliusLaunchVenueProvider(helius_api_key="fake-key")
    assert p.source_id == "helius_token_rpc"


# ============================================================================
# Scanner / composition wiring smoke
# ============================================================================

def _make_scanner(*, enabled=False, cfg=None):
    cfg = cfg or {
        "interval_s": 60, "default_notional_usd": 250.0,
        "gate_thresholds": {"default": {
            "min_composite_launch_score": 0.0,    # relaxed for smoke
            "min_bonding_curve_progress_pct": 0.0,
            "min_holders": 0,
            "min_smart_money_entries": 0,
            "max_holder_concentration_top10_pct": 100.0,
            "min_confidence": 0.0,
        }},
        "rug_gate": {
            "require_mint_authority_revoked": True,
            "require_freeze_authority_revoked": True,
            "min_lp_burned_or_locked_pct": 0.0,   # bypassed for smoke
            "max_holder_concentration_top10_pct": 100.0,
        },
        "roi_probability": {"min_sample_size": 4},
        "discovery_sources": {},
    }
    return LaunchArbitrageScanner(
        emission_bus=None, discovery_queue=None,
        venue_capability_repo=None,
        config_loader=lambda: cfg, state_loader=lambda: {"enabled": enabled},
    )


def test_scanner_default_provider_is_noop_until_helius_wired():
    s = _make_scanner()
    assert s.venue_provider_is_default is True


def test_scanner_set_venue_provider_to_helius_flips_flag(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    s = _make_scanner()
    p = HeliusLaunchVenueProvider()
    s.set_venue_provider(p)
    assert s.venue_provider_is_default is False
    # The verifier picks up the swap on next verify() call
    assert s._verifier.venue_provider is p


def test_provider_end_to_end_verifier_confirms_or_denies_with_gate_reason(
        monkeypatch):
    """End-to-end: stubbed Helius+DexScreener → provider → verifier produces
    either a confirmed canonical OR a precise gate-rejection outcome.
    With our smoke config (mint+freeze revoked, gates relaxed, LP-burn
    threshold=0), this run should CONFIRM a canonical."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    stub = _StubClient()
    stub.post_responses = [
        _mint_state_response(), _largest_holders_response()]
    stub.get_responses = [_dexscreener_response()]
    p = HeliusLaunchVenueProvider(http_client=stub)
    s = _make_scanner()
    s.set_venue_provider(p)
    canonical, outcome = asyncio.run(
        s._verifier.verify(_candidate("MintAAA")))
    assert canonical is not None, f"expected confirm, got outcome={outcome!r}"
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    # INV-3: provenance derives from leg source_id = helius_token_rpc (REAL)
    from arbicore.models.enums import DataProvenance
    assert canonical.source_data_quality == DataProvenance.REAL
    # category_metadata vocab fold-in
    assert canonical.category_metadata["launchpad"] == "raydium"
    assert canonical.category_metadata["mint_authority_revoked"] is True
    assert canonical.category_metadata["freeze_authority_revoked"] is True


def test_provider_end_to_end_gate6_rejection_when_mint_authority_present(
        monkeypatch):
    """Mint authority NOT revoked → Gate 6 rug-risk hard rejection."""
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    bad_mint_state = _StubResponse(200, {
        "jsonrpc": "2.0", "id": "getAccountInfo",
        "result": {"value": {"data": {"parsed": {"type": "mint", "info": {
            "mintAuthority": "AttackerWalletXYZ",
            "freezeAuthority": None,
            "supply": "1000000000000", "decimals": 6,
        }}}}},
    })
    stub = _StubClient()
    stub.post_responses = [bad_mint_state, _largest_holders_response()]
    stub.get_responses = [_dexscreener_response()]
    p = HeliusLaunchVenueProvider(http_client=stub)
    s = _make_scanner()
    s.set_venue_provider(p)
    canonical, outcome = asyncio.run(
        s._verifier.verify(_candidate("MintAAA")))
    assert canonical is None
    assert outcome.startswith(VerifiedOutcome.DENIED_GATE_PREFIX + "gate_6:")
    assert "mint_authority" in outcome.lower()


# ============================================================================
# Composition opt-in wiring
# ============================================================================

def test_composition_module_exposes_helius_provider_class():
    """The composition module imports HeliusLaunchVenueProvider so the
    optional auto-wire path at boot is available."""
    from arbicore.runtime import composition as comp
    assert hasattr(comp, "HeliusLaunchVenueProvider")
