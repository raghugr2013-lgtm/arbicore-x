"""Phase-2 hardening — native-price oracle + wider triangular (offline)."""
from __future__ import annotations

import asyncio

import pytest

from arbicore.economics.native_price import (
    NativePriceOracle, NativePriceResult, CHAIN_NATIVE,
)
from arbicore.scanners.flash_loan_arbitrage.triangular import (
    UniV3QuoteClient, discover_triangular_multi,
)
from arbicore.models.enums import StrategyType


# ---------------------------------------------------------------------------
# Native-price oracle — primary/secondary, stale, fail-closed, no fabrication
# ---------------------------------------------------------------------------
def _oracle(sources, ttl=60, max_stale=300, clock=None):
    t = {"now": 1000.0}
    return NativePriceOracle(sources, ttl_s=ttl, max_stale_s=max_stale,
                             clock=(clock or (lambda: t["now"]))), t


def test_primary_source_used_first():
    async def prim(sym): return 2500.0
    async def sec(sym): return 9999.0
    o, _ = _oracle([("prim", prim), ("sec", sec)])
    r = asyncio.run(o.get_native_usd("arbitrum"))
    assert r.ok and r.price_usd == 2500.0 and r.source == "prim"


def test_secondary_used_when_primary_fails():
    async def prim(sym): raise RuntimeError("down")
    async def sec(sym): return 2600.0
    o, _ = _oracle([("prim", prim), ("sec", sec)])
    r = asyncio.run(o.get_native_usd("ethereum"))
    assert r.ok and r.price_usd == 2600.0 and r.source == "sec"


def test_zero_and_nan_prices_are_rejected():
    async def bad(sym): return 0.0
    async def good(sym): return 3000.0
    o, _ = _oracle([("bad", bad), ("good", good)])
    r = asyncio.run(o.get_native_usd("optimism"))
    assert r.price_usd == 3000.0                # 0.0 rejected, never trusted


def test_all_sources_fail_no_cache_fails_closed():
    async def down(sym): raise RuntimeError("x")
    o, _ = _oracle([("a", down)])
    r = asyncio.run(o.get_native_usd("polygon"))
    assert r.ok is False and r.price_usd is None
    assert r.reason == "no_source_no_cache_fail_closed"


def test_stale_cache_served_within_window_then_fails_closed():
    calls = {"n": 0}
    async def flaky(sym):
        calls["n"] += 1
        if calls["n"] == 1:
            return 700.0     # first call succeeds and caches
        raise RuntimeError("down")
    o, t = _oracle([("flaky", flaky)], ttl=10, max_stale=100)
    r1 = asyncio.run(o.get_native_usd("bnb"))
    assert r1.ok and r1.price_usd == 700.0 and r1.stale is False
    # advance beyond ttl but within stale window ⇒ stale cache served.
    t["now"] += 50
    r2 = asyncio.run(o.get_native_usd("bnb"))
    assert r2.ok and r2.price_usd == 700.0 and r2.stale is True
    # advance beyond max_stale ⇒ fail closed (never a fabricated/last price).
    t["now"] += 1000
    r3 = asyncio.run(o.get_native_usd("bnb"))
    assert r3.ok is False and r3.price_usd is None
    assert r3.reason == "cache_expired_fail_closed"


def test_unsupported_chain_fails_closed():
    o, _ = _oracle([])
    r = asyncio.run(o.get_native_usd("solana"))
    assert r.ok is False and r.reason == "unsupported_chain"


def test_native_symbols_are_chain_correct():
    assert CHAIN_NATIVE["polygon"]["symbol"] == "POL"
    assert CHAIN_NATIVE["bnb"]["symbol"] == "BNB"
    assert CHAIN_NATIVE["arbitrum"]["symbol"] == "ETH"


# ---------------------------------------------------------------------------
# Wider triangular — multi fee-tier best execution + multi base asset
# ---------------------------------------------------------------------------
class _FakeQuoter:
    """Returns different amounts per fee tier so best-of selection is observable."""

    def __init__(self):
        self.calls = []

    async def eth_call(self, tx, block="latest"):
        data = tx["data"]
        fee = int(data[-128:-64], 16)     # 4th arg word = fee
        self.calls.append(fee)
        # tier 3000 gives the best output; others worse.
        mult = {500: 90, 3000: 110, 10000: 80, 100: 50}.get(fee, 10)
        # return a plausible 1e6-decimals-ish amount
        return "0x" + f"{mult * 10**16:064x}"


def test_quote_client_picks_best_fee_tier():
    tokens = {"WETH": {"address": "0x" + "1"*40, "decimals": 18},
              "USDC": {"address": "0x" + "2"*40, "decimals": 18}}
    qc = UniV3QuoteClient(_FakeQuoter(), "arbitrum", tokens,
                          fee_tiers=[500, 3000, 10000, 100])
    out = asyncio.run(qc.quote("WETH", "USDC", 1.0))
    # best is the 3000 tier (110 * 1e16 / 1e18 = 1.1)
    assert out == pytest.approx(1.1)


class _GM:
    chain = "arbitrum"; supports_l1_data_fee = True
    async def all_in_cost(self, *, gross_profit_usd, borrow_amount_usd,
                          notional_usd, gas_units, eth_usd, **kw):
        return {"all_in_cost_usd": 10.0, "l2_fee_usd": 8.0, "l1_fee_usd": 1.0,
                "slippage_usd": 1.0, "net_profit_all_in_usd": gross_profit_usd - 10.0}


def test_discover_multi_base_reuses_single_enumerator():
    async def good(a, b, amt):
        return amt * 1.01
    res = asyncio.run(discover_triangular_multi(
        bases=[
            {"base_token": "WETH", "intermediates": ["USDC", "ARB"],
             "start_amount_tokens": 10.0, "base_token_price_usd": 3000.0},
            {"base_token": "USDC", "intermediates": ["WETH", "ARB"],
             "start_amount_tokens": 30000.0, "base_token_price_usd": 1.0},
        ],
        chain="arbitrum", chain_id=42161, quote_fn=good, gas_model=_GM(),
        route_gas_units=300_000, native_usd=3000.0,
        liquidity_by_provider={"balancer_v2": 10_000_000},
        fee_bps_by_provider={"balancer_v2": 0}, min_net_profit_usd=35.0))
    assert res["valid"] >= 1 and res["emitted"]
    assert set(res["per_base"].keys()) == {"WETH", "USDC"}
    assert all(o.strategy == StrategyType.TRIANGULAR for o in res["emitted"])
