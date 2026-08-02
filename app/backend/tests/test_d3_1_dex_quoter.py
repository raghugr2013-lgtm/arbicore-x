"""Tests for D-3.1 — DEX quoter abstractions.

Covers:
  - BaseDEXQuoter ABC contract (must set chain/dex/source_id)
  - DEXQuoteResult shape
  - Graceful disable when rpc_env_var absent
  - INV-3 attribution via source_id
  - build_default_quoters() returns the full D-3 quoter universe
  - EVMV3Quoter rejects unknown (dex, chain) combinations
"""
from __future__ import annotations

import asyncio
import os

import pytest

from arbicore.scanners.dex_arbitrage.quoter import (
    BaseDEXQuoter, DEXQuoteResult, EVMV3Quoter, RaydiumQuoter,
    EVM_V3_QUOTER_CONTRACTS, build_default_quoters,
)
from arbicore.data.provenance import SOURCE_REGISTRY


# ----- ABC contract --------------------------------------------------------

def test_base_quoter_is_abstract():
    """BaseDEXQuoter cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseDEXQuoter()  # type: ignore[abstract]


def test_subclass_missing_class_attrs_raises():
    class _Bad(BaseDEXQuoter):
        async def _quote_impl(self, **_):
            return DEXQuoteResult(ok=False, chain="x", dex="y")
    with pytest.raises(TypeError):
        _Bad()


# ----- EVMV3Quoter ---------------------------------------------------------

def test_evmv3_quoter_known_combinations_construct_cleanly():
    for (dex, chain), addr in EVM_V3_QUOTER_CONTRACTS.items():
        q = EVMV3Quoter(chain=chain, dex=dex, source_id=f"{dex}_quoter_{chain}")
        assert q.chain == chain
        assert q.dex == dex
        assert q.source_id == f"{dex}_quoter_{chain}"
        assert q.quoter_address == addr
        # Every D-3 quoter source_id is registered (INV-3 attribution path)
        assert q.source_id in SOURCE_REGISTRY


def test_evmv3_quoter_unknown_combination_raises():
    with pytest.raises(ValueError):
        EVMV3Quoter(chain="cardano", dex="uniswap_v3", source_id="bogus")


def test_evmv3_quoter_graceful_disable_when_no_creds(monkeypatch):
    monkeypatch.delenv("ALCHEMY_API_KEY", raising=False)
    q = EVMV3Quoter(chain="ethereum", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_ethereum")
    assert q.credentials_available is False
    res = asyncio.run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0))
    assert isinstance(res, DEXQuoteResult)
    assert res.ok is False
    assert res.reason.startswith("credentials_missing:ALCHEMY_API_KEY")
    assert res.source_id == "uniswap_v3_quoter_ethereum"


def test_evmv3_quoter_with_creds_invokes_impl(monkeypatch):
    """When credentials are present, _quote_impl runs. D-3.1 stub returns
    ok=False reason='not_yet_wired:...' — but it must reach _quote_impl
    (proven by the distinct reason)."""
    monkeypatch.setenv("ALCHEMY_API_KEY", "fake-key-for-test")
    q = EVMV3Quoter(chain="ethereum", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_ethereum")
    res = asyncio.run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0))
    assert res.ok is False
    assert res.reason.startswith("not_yet_wired:")
    assert res.source_id == "uniswap_v3_quoter_ethereum"
    assert res.size_in_usd == 1000.0


def test_quoter_invalid_direction_returns_clean_result(monkeypatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "fake-key")
    q = EVMV3Quoter(chain="ethereum", dex="uniswap_v3",
                    source_id="uniswap_v3_quoter_ethereum")
    res = asyncio.run(q.quote(pair_canonical="WETH/USDC",
                              size_in_usd=1000.0, direction="diagonal"))
    assert res.ok is False
    assert res.reason == "invalid_direction"


def test_quoter_swallows_exceptions(monkeypatch):
    """A buggy _quote_impl never escapes — always returns ok=False."""
    monkeypatch.setenv("ALCHEMY_API_KEY", "fake-key")

    class _Boom(EVMV3Quoter):
        async def _quote_impl(self, **_):
            raise RuntimeError("kaboom")

    q = _Boom(chain="ethereum", dex="uniswap_v3",
              source_id="uniswap_v3_quoter_ethereum")
    res = asyncio.run(q.quote(pair_canonical="WETH/USDC", size_in_usd=1000.0))
    assert res.ok is False
    assert res.reason.startswith("quoter_error:RuntimeError:kaboom")


# ----- RaydiumQuoter -------------------------------------------------------

def test_raydium_quoter_class_constants():
    q = RaydiumQuoter()
    assert q.chain == "solana"
    assert q.dex == "raydium"
    assert q.source_id == "raydium_quoter_solana"
    assert q.source_id in SOURCE_REGISTRY
    assert q.rpc_env_var == "HELIUS_API_KEY"


def test_raydium_quoter_graceful_disable(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    q = RaydiumQuoter()
    res = asyncio.run(q.quote(pair_canonical="SOL/USDC", size_in_usd=1000.0))
    assert res.ok is False
    assert res.reason.startswith("credentials_missing:HELIUS_API_KEY")


def test_raydium_quoter_with_creds(monkeypatch):
    monkeypatch.setenv("HELIUS_API_KEY", "fake-key")
    q = RaydiumQuoter()
    res = asyncio.run(q.quote(pair_canonical="SOL/USDC", size_in_usd=1000.0))
    assert res.ok is False
    assert res.reason.startswith("not_yet_wired:")


# ----- Factory -------------------------------------------------------------

def test_build_default_quoters_returns_full_universe():
    quoters = build_default_quoters()
    # 7 EVM V3 + 1 Raydium = 8
    assert len(quoters) == 8
    source_ids = sorted(q.source_id for q in quoters)
    expected = sorted([
        "uniswap_v3_quoter_ethereum", "uniswap_v3_quoter_arbitrum",
        "uniswap_v3_quoter_base",
        "pancake_v3_quoter_bnb", "pancake_v3_quoter_arbitrum",
        "pancake_v3_quoter_base",
        "aerodrome_quoter_base",
        "raydium_quoter_solana",
    ])
    assert source_ids == expected
    # All source_ids are registered in SOURCE_REGISTRY (INV-3 attribution)
    for sid in source_ids:
        assert sid in SOURCE_REGISTRY


# ----- INV-2 sanity --------------------------------------------------------

def test_quoter_module_has_no_emission_bus_calls():
    """INV-2 (AST-level): no EmissionBus symbol and no .emit attribute use."""
    import ast
    import arbicore.scanners.dex_arbitrage.quoter as mod
    tree = ast.parse(open(mod.__file__).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "EmissionBus":
            raise AssertionError("EmissionBus symbol used in quoter module")
        if isinstance(node, ast.Attribute) and node.attr == "emit":
            raise AssertionError(".emit attribute used in quoter module")
