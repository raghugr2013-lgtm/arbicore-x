"""Emergent B1 — multichain ExactSizeBorrowSizer wiring (offline).

Proves the canonical flash-loan scanner uses build_h05_borrow_sizer /
build_multichain_price_source (six-chain), preserves Base feed behavior, and
fails closed on missing feeds. No RPC, no deploy, no signing.
"""
from __future__ import annotations

import inspect
import math
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")

import arbicore.runtime.composition as comp
from arbicore.runtime.composition import (
    _H05_CHAINS,
    _build_base_exact_size_borrow_sizer,
    build_h05_borrow_sizer,
    build_multichain_price_source,
)
from arbicore.scanners.flash_loan_arbitrage.exact_size_sizer import (
    ExactSizeBorrowSizer,
    MultichainPriceSource,
    MultichainUsdPriceFeed,
    PricePool,
    build_borrow_sizer_from_env,
)

SIX = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")

DECIMALS = {
    "ethereum": {"WETH": 18, "USDC": 6},
    "arbitrum": {"WETH": 18, "USDC": 6},
    "base": {"WETH": 18, "USDC": 6},
    "optimism": {"WETH": 18, "USDC": 6},
    "polygon": {"WETH": 18, "USDC": 6, "WMATIC": 18},
    "bnb": {"WBNB": 18, "USDT": 18, "USDC": 18},
}
PRICES = {
    "ethereum": {"WETH": 2000.0},
    "arbitrum": {"WETH": 2000.0},
    "base": {"WETH": 2000.0},
    "optimism": {"WETH": 2000.0},
    "polygon": {"WMATIC": 0.5, "WETH": 2000.0},
    "bnb": {"WBNB": 600.0},
}
TOKENS = {
    "ethereum": "WETH",
    "arbitrum": "WETH",
    "base": "WETH",
    "optimism": "WETH",
    "polygon": "WMATIC",
    "bnb": "WBNB",
}


class _CapturingQuoter:
    async def quote_route(self, *, chain, hops):
        hop = SimpleNamespace(dex="uniswap_v3", status="ok", block_number=1,
                              quoter_contract="0xq")
        return SimpleNamespace(status="ok", hops=[hop],
                               final_amount_out_wei=2000 * 10 ** 6,
                               aggregate_gas_estimate_units=1)


def _eth_ok(chain):
    async def eth_call(to, data):
        return None
    return eth_call


def _pool(token_sym: str, token_dec: int = 18):
    t0 = "0x" + "a1" * 20
    usdc = "0x" + "b2" * 20
    pool = "0x" + "cc" * 20
    return PricePool(token_sym, t0, token_dec, "USDC", usdc, 6,
                     "uniswap_v3", 5, pool)


async def _fake_resolve(chain, eth_call, *, token="WETH", dec=18):
    addr = "0x" + "cc" * 20
    t0 = "0x" + "a1" * 20
    usdc = "0x" + "b2" * 20
    return SimpleNamespace(
        resolved_specs=[{
            "venue_id": "v", "dex": "uniswap_v3", "token_a": token,
            "token_b": "USDC", "fee_bps": 5, "pool_contract_address": addr,
        }],
        pool_meta={addr.lower(): (token, t0, dec, "USDC", usdc, 6)},
        unresolved=[],
    )


# 1. Six-chain MultichainPriceSource
@pytest.mark.asyncio
async def test_six_chain_multichain_price_source(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_USD_NUMERAIRE", "USDC")

    async def resolve(chain, eth_call):
        tok = "WBNB" if chain == "bnb" else ("WMATIC" if chain == "polygon" else "WETH")
        return await _fake_resolve(chain, eth_call, token=tok)

    src = await build_multichain_price_source(
        _CapturingQuoter(), chains=SIX, eth_call_factory=_eth_ok, resolver=resolve)
    assert src is not None
    assert set(src.configured_chains()) == set(SIX)
    assert tuple(_H05_CHAINS) == SIX


# 2. ExactSizeBorrowSizer Ethereum exact-size
@pytest.mark.asyncio
async def test_ethereum_exact_size():
    async def price(c, t):
        return PRICES["ethereum"].get(str(t).upper())

    s = ExactSizeBorrowSizer(price, lambda c, t: DECIMALS[c].get(str(t).upper()))
    wei = await s.size("ethereum", "WETH", 1000.0)
    assert wei == int(math.floor(1000.0 / 2000.0 * 10 ** 18))
    assert wei > 0


# 3. Exact-size for all supported chains with valid feeds
@pytest.mark.asyncio
@pytest.mark.parametrize("chain", list(SIX))
async def test_exact_size_all_supported_chains(chain):
    token = TOKENS[chain]

    async def price(c, t):
        return PRICES.get(c, {}).get(str(t).upper())

    s = ExactSizeBorrowSizer(price, lambda c, t: DECIMALS.get(c, {}).get(str(t).upper()))
    wei = await s.size(chain, token, 1000.0)
    px = PRICES[chain][token]
    dec = DECIMALS[chain][token]
    assert wei == int(math.floor(1000.0 / px * 10 ** dec))


# 4. Missing-feed fail-closed
@pytest.mark.asyncio
async def test_missing_feed_fail_closed(monkeypatch):
    monkeypatch.setenv("ARBICORE_BORROW_SIZER_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")

    async def none_price(c, t):
        return None

    s = ExactSizeBorrowSizer(none_price, lambda c, t: 18)
    assert await s.size("ethereum", "WETH", 1000.0) is None

    # Chain omitted from MultichainPriceSource → None (never fabricate)
    src = MultichainPriceSource({"base": SimpleNamespace(
        price_source=lambda token: _async_none())})
    assert await src.price_usd("ethereum", "WETH") is None

    # build_h05 with empty source → no sizer callback (or callback that fails closed)
    async def empty_src(*a, **k):
        return None
    monkeypatch.setattr(comp, "build_multichain_price_source", empty_src)
    assert await build_h05_borrow_sizer(_CapturingQuoter()) is None


async def _async_none():
    return None


# 5. Base regression — existing Base feed instance preserved
@pytest.mark.asyncio
async def test_base_feed_instance_preserved(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_USD_NUMERAIRE", "USDC")

    class _BaseFeed:
        async def price_source(self, token):
            return 2000.0 if str(token).upper() == "WETH" else None

    base_feed = _BaseFeed()

    async def resolve(chain, eth_call):
        return await _fake_resolve(chain, eth_call)

    src = await build_multichain_price_source(
        _CapturingQuoter(), chains=("base", "ethereum"),
        eth_call_factory=_eth_ok, resolver=resolve, base_feed=base_feed)
    assert src is not None
    assert src._feeds["base"] is base_feed
    assert await src.price_usd("base", "WETH") == pytest.approx(2000.0)

    # Prior Base-only helper still produces a working Base-scoped sizer
    monkeypatch.setenv("ARBICORE_BORROW_SIZER_ENABLED", "true")
    legacy = _build_base_exact_size_borrow_sizer(base_feed)
    assert legacy is not None
    assert await legacy("base", "WETH", 1000.0) == 5 * 10 ** 17
    # Non-Base must NOT be sized from Base-only legacy helper
    assert await legacy("ethereum", "WETH", 1000.0) is None


# 6. Live composition wiring — generalized H05 sizer is wired
@pytest.mark.asyncio
async def test_canonical_wiring_uses_h05_sizer(monkeypatch):
    monkeypatch.setenv("ARBICORE_BORROW_SIZER_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")

    h05_calls = []
    base_only_calls = []
    captured = {}

    async def fake_h05(quoter_registry, *, price_source=None, chains=_H05_CHAINS,
                       base_feed=None):
        h05_calls.append({"base_feed": base_feed, "chains": chains})

        async def sizer(chain, token, usd):
            return 10 ** 17
        return sizer

    def fake_base_only(price_feed):
        base_only_calls.append(price_feed)
        return None

    def fake_make_live(quoter_registry, *, tvl_provider=None, borrow_sizer=None,
                       eth_call_for_chain=None):
        captured["borrow_sizer"] = borrow_sizer
        return lambda *a, **k: None

    # Minimal stubs so wiring can proceed offline
    monkeypatch.setattr(comp, "build_h05_borrow_sizer", fake_h05)
    monkeypatch.setattr(comp, "_build_base_exact_size_borrow_sizer", fake_base_only)
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.live_quote_provider.make_live_quote_provider",
        fake_make_live,
    )
    monkeypatch.setattr(
        "arbicore.searcher.runtime.make_base_eth_call_from_env", lambda: None)
    monkeypatch.setattr(
        "arbicore.searcher.runtime.make_eth_call_for_chain_from_env", lambda ch: None)
    monkeypatch.setattr(
        "arbicore.searcher.price_feed.build_base_price_feed_from_env",
        lambda qr=None: SimpleNamespace(price_source=lambda t: None,
                                        provenance_for=lambda t: {}),
    )
    monkeypatch.setattr(
        "arbicore.searcher.runtime.make_base_price_source_from_env", lambda: None)
    monkeypatch.setattr(
        "arbicore.searcher.runtime.build_base_tvl_provider",
        lambda *a, **k: None)
    monkeypatch.setattr(comp, "attach_measured_tvl_path",
                        lambda *a, **k: None, raising=False)

    # Patch attach via the import site used inside the function
    import arbicore.scanners.flash_loan_arbitrage.pool_tvl_propagation as ptvl
    monkeypatch.setattr(ptvl, "attach_measured_tvl_path", lambda *a, **k: None)

    monkeypatch.setattr(comp, "make_flash_loan_evidence_sink", lambda: None)
    monkeypatch.setattr(comp, "_os_env_on", lambda *a, **k: False)
    monkeypatch.setattr(comp, "_refresh_base_v3_eligibility",
                        lambda eth: _async_empty_elig())
    monkeypatch.setattr(comp, "_failclosed_exclude_all_base_univ3", lambda: None)

    class _Scanner:
        quote_provider_is_default = False
        scanner_id = "flash_loan_arbitrage"

        def set_quote_provider(self, p):
            self.quote_provider = p

        def set_price_provenance_fn(self, fn):
            pass

        def set_evidence_sink(self, sink):
            pass

    monkeypatch.setattr(comp, "get_flash_loan_arb_scanner", lambda: _Scanner())

    scanner, meta = await comp._wire_canonical_flash_loan_scanner(object())
    assert h05_calls, "build_h05_borrow_sizer must be invoked by canonical wiring"
    assert not base_only_calls, (
        "canonical wiring must NOT call Base-only _build_base_exact_size_borrow_sizer"
    )
    assert captured.get("borrow_sizer") is not None
    assert await captured["borrow_sizer"]("ethereum", "WETH", 1000.0) == 10 ** 17

    # Source-level guard: wiring body references build_h05_borrow_sizer
    src = inspect.getsource(comp._wire_canonical_flash_loan_scanner)
    assert "build_h05_borrow_sizer" in src
    assert "_build_base_exact_size_borrow_sizer(price_feed)" not in src


async def _async_empty_elig():
    return {"checked": 0, "eligible": 0, "excluded": 0, "reason": "test"}
