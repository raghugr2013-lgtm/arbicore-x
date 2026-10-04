"""B1 — multichain exact-size sizing (chain-aware live wiring).

Confirms the live canonical scanner now sizes all six supported chains via the
EXISTING generalized H05 infrastructure (no parallel architecture), preserving
the Base feed instance and staying fail-closed when a chain has no feed.
"""
import os

import pytest

from arbicore.scanners.flash_loan_arbitrage.exact_size_sizer import (
    ExactSizeBorrowSizer, MultichainPriceSource)
from arbicore.runtime import composition as C

SIX = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")


class _Feed:
    def __init__(self, price):
        self._price = price

    async def price_source(self, token):
        return self._price


def _sizer(price_by_chain, decimals=18):
    src = MultichainPriceSource({c: _Feed(p) for c, p in price_by_chain.items()})

    def _dec(chain, token):
        return decimals
    return ExactSizeBorrowSizer(src.price_usd, _dec), src


# 1. MultichainPriceSource for all six chains
async def test_multichain_price_source_all_six_chains():
    src = MultichainPriceSource({c: _Feed(1000.0 + i) for i, c in enumerate(SIX)})
    assert sorted(src.configured_chains()) == sorted(SIX)
    for i, c in enumerate(SIX):
        assert await src.price_usd(c, "WETH") == 1000.0 + i


# 2. Ethereum exact-size calculation
async def test_ethereum_exact_size_calculation():
    sizer, _ = _sizer({"ethereum": 2000.0}, decimals=18)
    wei = await sizer.size("ethereum", "WETH", 10_000.0)
    assert wei == 5 * 10 ** 18  # floor(10000/2000 * 1e18)


# 3. Exact-size for every supported chain with a valid feed
async def test_exact_size_all_supported_chains():
    sizer, _ = _sizer({c: 2000.0 for c in SIX}, decimals=18)
    for c in SIX:
        assert await sizer.size(c, "WETH", 2000.0) == 1 * 10 ** 18


# 4. Missing-feed fail-closed (Base-only source cannot size Ethereum)
async def test_missing_feed_fail_closed():
    sizer, src = _sizer({"base": 2000.0}, decimals=18)
    assert await src.price_usd("ethereum", "WETH") is None
    assert await sizer.size("ethereum", "WETH", 10_000.0) is None  # no fabrication


# 5. Base feed instance preservation via the live wiring helper
async def test_base_feed_instance_preserved(monkeypatch):
    os.environ["ARBICORE_BORROW_SIZER_ENABLED"] = "1"
    os.environ["ARBICORE_PRICE_FEED_ENABLED"] = "1"
    base_feed = _Feed(3000.0)
    built = MultichainPriceSource({"ethereum": _Feed(2000.0), "base": _Feed(1.0)})

    async def _fake_build_src(quoter_registry=None, *, chains=None):
        return built
    captured = {}

    async def _fake_build_sizer(quoter_registry=None, *, price_source=None, chains=None):
        captured["price_source"] = price_source
        return "SIZER"

    monkeypatch.setattr(C, "build_multichain_price_source", _fake_build_src)
    monkeypatch.setattr(C, "build_h05_borrow_sizer", _fake_build_sizer)

    out = await C._build_live_h05_borrow_sizer(None, base_feed)
    assert out == "SIZER"
    # the EXISTING live Base feed instance is preserved (identity), Ethereum kept
    assert captured["price_source"]._feeds["base"] is base_feed
    assert "ethereum" in captured["price_source"]._feeds


# 6. Canonical/live composition wiring references the six-chain helper
async def test_canonical_wiring_uses_six_chain_helper():
    import inspect
    src = inspect.getsource(C._wire_canonical_flash_loan_scanner)
    assert "_build_live_h05_borrow_sizer" in src
    assert "borrow_sizer=b1_sizer" in src
    # six-chain set is the canonical _H05_CHAINS (all six, unchanged)
    assert set(C._H05_CHAINS) == set(SIX)


# 7. Base regression — disabled => None (probe-sized, verifier fails closed)
async def test_base_regression_disabled_returns_none(monkeypatch):
    monkeypatch.delenv("ARBICORE_BORROW_SIZER_ENABLED", raising=False)
    out = await C._build_live_h05_borrow_sizer(None, _Feed(3000.0))
    assert out is None
