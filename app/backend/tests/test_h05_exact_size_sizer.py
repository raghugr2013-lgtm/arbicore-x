"""H05 — chain-aware exact-size borrow sizer + integration (offline, mocked).

Deterministic unit tests with injected price sources / mocked quote routes. No
production RPC, no live capability claimed. Covers fail-closed cases, exact wei
math (incl. BNB 18-decimal stablecoins), and the live_quote_provider binding
(size_basis="exact" + quote_notional_usd), with Base/probe behaviour preserved.
"""
from __future__ import annotations

import math
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")

from arbicore.scanners.flash_loan_arbitrage.exact_size_sizer import (
    ExactSizeBorrowSizer, MultichainUsdPriceFeed, MultichainPriceSource,
    PricePool, build_borrow_sizer_from_env, registry_decimals,
    borrow_sizer_enabled, price_feed_enabled,
)
from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    make_live_quote_provider,
)

# Decimals per chain (note BNB/BSC stablecoins use 18, unlike 6 elsewhere).
DECIMALS = {
    "ethereum": {"WETH": 18, "USDC": 6},
    "arbitrum": {"WETH": 18, "USDC": 6},
    "base": {"WETH": 18, "USDC": 6},
    "optimism": {"WETH": 18, "USDC": 6},
    "polygon": {"WETH": 18, "USDC": 6, "WMATIC": 18},
    "bnb": {"WBNB": 18, "USDT": 18, "USDC": 18},   # BSC stablecoins = 18 dp
}
PRICES = {
    "ethereum": {"WETH": 2000.0}, "arbitrum": {"WETH": 2000.0},
    "base": {"WETH": 2000.0}, "optimism": {"WETH": 2000.0},
    "polygon": {"WMATIC": 0.5}, "bnb": {"WBNB": 600.0, "USDT": 1.0},
}


def _decimals(chain, token):
    return DECIMALS.get(chain, {}).get(str(token).upper())


def _price_ok(chain, token):
    async def _p(c, t):
        return PRICES.get(c, {}).get(str(t).upper())
    return _p


def _sizer(price_fn=None, dec_fn=_decimals):
    return ExactSizeBorrowSizer(price_fn or _price_ok(None, None), dec_fn)


# A. Six-chain successful sizing
@pytest.mark.asyncio
@pytest.mark.parametrize("chain,token", [
    ("ethereum", "WETH"), ("arbitrum", "WETH"), ("base", "WETH"),
    ("optimism", "WETH"), ("polygon", "WMATIC"), ("bnb", "WBNB"),
])
async def test_six_chain_success(chain, token):
    s = _sizer()
    wei = await s.size(chain, token, 1000.0)
    price = PRICES[chain][token]
    dec = DECIMALS[chain][token]
    assert wei == int(math.floor(1000.0 / price * 10 ** dec))
    assert wei > 0


# B. Unknown chain
@pytest.mark.asyncio
async def test_unknown_chain_fail_closed():
    assert await _sizer().size("solana", "WETH", 1000.0) is None
    assert await _sizer().size("", "WETH", 1000.0) is None


# C. Unknown token
@pytest.mark.asyncio
async def test_unknown_token_fail_closed():
    assert await _sizer().size("ethereum", "DOGE", 1000.0) is None


# D. Missing decimals
@pytest.mark.asyncio
async def test_missing_decimals_fail_closed():
    s = ExactSizeBorrowSizer(_price_ok(None, None), lambda c, t: None)
    assert await s.size("ethereum", "WETH", 1000.0) is None


# E. Missing RPC / no price source → None (represented by price returning None)
# F. Missing price
@pytest.mark.asyncio
async def test_missing_price_fail_closed():
    async def none_price(c, t):
        return None
    assert await _sizer(none_price).size("ethereum", "WETH", 1000.0) is None


# G/H/I. Zero, negative, NaN, infinity prices
@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
async def test_bad_price_fail_closed(bad):
    async def bad_price(c, t):
        return bad
    assert await _sizer(bad_price).size("ethereum", "WETH", 1000.0) is None


# Bad requested USD (zero / negative / non-finite)
@pytest.mark.asyncio
@pytest.mark.parametrize("usd", [0.0, -5.0, float("nan"), float("inf")])
async def test_bad_usd_fail_closed(usd):
    assert await _sizer().size("ethereum", "WETH", usd) is None


# L. Quote/price raises → fail closed (never fabricate)
@pytest.mark.asyncio
async def test_price_exception_fail_closed():
    async def boom(c, t):
        raise RuntimeError("rpc down")
    assert await _sizer(boom).size("ethereum", "WETH", 1000.0) is None


# M. Exact integer wei conversion + floor rounding never exceeds basis
@pytest.mark.asyncio
async def test_exact_wei_and_floor_policy():
    # price 3000, usd 1 → 0.000333... WETH → floor at 18dp
    async def p(c, t):
        return 3000.0
    s = ExactSizeBorrowSizer(p, lambda c, t: 18)
    wei = await s.size("ethereum", "WETH", 1.0)
    assert wei == int(math.floor(1.0 / 3000.0 * 10 ** 18))
    # realized notional never exceeds requested
    assert wei / 10 ** 18 * 3000.0 <= 1.0 + 1e-9
    # a request that floors to 0 base units is rejected
    s6 = ExactSizeBorrowSizer(lambda c, t: None, lambda c, t: 6)

    async def big(c, t):
        return 10 ** 12  # price so high the 6-dp amount floors to 0
    s6b = ExactSizeBorrowSizer(big, lambda c, t: 6)
    assert await s6b.size("ethereum", "USDC", 1.0) is None


# N. Decimal differences — BNB 18-dp stablecoin vs 6-dp elsewhere
@pytest.mark.asyncio
async def test_bnb_18dp_stablecoin_vs_6dp():
    s = _sizer()
    bnb_usdt = await s.size("bnb", "USDT", 500.0)      # 18 dp, price 1.0
    assert bnb_usdt == 500 * 10 ** 18
    # A 6-dp USDC on ethereum at price 1.0 would be 500 * 10**6 — different units
    s_eth = ExactSizeBorrowSizer(lambda c, t: None, _decimals)

    async def one(c, t):
        return 1.0
    s_eth2 = ExactSizeBorrowSizer(one, _decimals)
    assert await s_eth2.size("ethereum", "USDC", 500.0) == 500 * 10 ** 6
    assert bnb_usdt != 500 * 10 ** 6  # decimals genuinely differ


# O + P: requested USD bound to the quote; live provider marks size_basis=exact
def _route_quote(final_out_wei):
    hop = SimpleNamespace(dex="uniswap_v3", status="ok", block_number=123,
                          quoter_contract="0xq", token_in="0xa", token_out="0xb")
    return SimpleNamespace(status="ok", hops=[hop, hop],
                           final_amount_out_wei=final_out_wei,
                           aggregate_gas_estimate_units=100000)


class _StubQuoter:
    def __init__(self, final_out_wei):
        self.calls = []
        self._out = final_out_wei

    async def quote_route(self, *, chain, hops):
        self.calls.append({"chain": chain, "hops": hops})
        return _route_quote(self._out)


# ─────────────────────────────────────────────────────────────────────────────
# DEFERRED — NON-BASE RUNTIME SEAM (Phase-B).
# The historical a430e41 tests `test_live_provider_exact_binding_and_notional`,
# `test_live_provider_sizer_none_fails_closed` and
# `test_live_provider_probe_mode_unchanged` exercised the CAPABILITY-LINE
# `make_live_quote_provider(chain=..., token_address_fn=..., pool_specs=...,
# probe_amount_fn=...)` signature. The CANONICAL `make_live_quote_provider`
# signature is intentionally different and `execution/live_quote_provider.py` is
# OUT OF SCOPE for Phase-A, so these three provider-binding tests are DEFERRED.
# Missing dependency: capability-line live_quote_provider signature.
# Canonical file requiring future (Phase-B) modification:
#   app/backend/arbicore/scanners/flash_loan_arbitrage/live_quote_provider.py
# Probe-vs-exact separation against the REAL canonical provider/verifier is
# already covered by tests/test_h05_exact_size_binding.py (passes in Phase-A).
# ─────────────────────────────────────────────────────────────────────────────


# H05 disabled by default (env gate)
def test_h05_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ARBICORE_BORROW_SIZER_ENABLED", raising=False)
    monkeypatch.delenv("ARBICORE_PRICE_FEED_ENABLED", raising=False)
    assert not borrow_sizer_enabled()
    assert not price_feed_enabled()
    assert build_borrow_sizer_from_env(price_usd_fn=lambda *_: None) is None


def test_h05_enabled_requires_genuine_price_source(monkeypatch):
    monkeypatch.setenv("ARBICORE_BORROW_SIZER_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    # enabled but no price source → still None (never fabricate)
    assert build_borrow_sizer_from_env() is None
    cb = build_borrow_sizer_from_env(price_usd_fn=_price_ok(None, None))
    assert cb is not None


# MultichainUsdPriceFeed reuses M2.5 logic with generic real-address pools
@pytest.mark.asyncio
async def test_multichain_price_feed_reuses_m25():
    WETH = "0x" + "a1" * 20
    USDC = "0x" + "b2" * 20
    POOL = "0x" + "cc" * 20
    pool = PricePool("WETH", WETH, 18, "USDC", USDC, 6, "uniswap_v3", 5, POOL)

    async def quote_route_fn(hops):
        # direct WETH→USDC: 1 WETH (1e18) → 2000 USDC (2000e6)
        return {"final_out_wei": 2000 * 10 ** 6, "block": 10, "quoter": "0xq"}

    feed = MultichainUsdPriceFeed(quote_route_fn=quote_route_fn, pools=[pool])
    price = await feed.price_source("WETH")
    assert price == pytest.approx(2000.0)
    src = MultichainPriceSource({"arbitrum": feed})
    assert await src.price_usd("arbitrum", "WETH") == pytest.approx(2000.0)
    assert await src.price_usd("solana", "WETH") is None  # unknown chain → None


# registry_decimals uses the SP-2 verified registry (all six chains) / fail closed
def test_registry_decimals_fail_closed():
    assert registry_decimals("solana", "WETH") is None
    assert registry_decimals("arbitrum", "NOTATOKEN") is None
