"""M2.5 — on-chain USDC-denominated multi-token USD price feed (offline).

Deterministic doubles only (no RPC): a fake quote_route_fn returns real-shaped
USDC outputs so we can prove:
  * USDC = configured numéraire (peg), never quoted;
  * non-anchor tokens priced from genuine on-chain quotes (direct + via-WETH);
  * stablecoins peg-guarded → out-of-band fails closed;
  * freshness/staleness (block lag + unverifiable head) fails closed;
  * unknown / no-path / quote-failure fails closed;
  * full provenance retained per token;
  * integration with OnChainReserveTVLProvider drives Gate 8 correctly.
The REAL QuoterRegistry path is validated live on the VPS.
"""
from __future__ import annotations

import asyncio

from arbicore.discovery import base_pool_registry as reg
from arbicore.searcher.price_feed import OnChainUsdPriceFeed, PricePoint
from arbicore.scanners.flash_loan_arbitrage.tvl_provider import (
    OnChainReserveTVLProvider,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate8LiquidityDepth,
)

USDC_DEC = 6


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _pools():
    return reg.get_canonical_pools()


def _addr(sym):
    return OnChainUsdPriceFeed(quote_route_fn=_noop, pools=_pools())._addr[sym.upper()]


async def _noop(hops):
    return None


def _feed(route_fn, *, head_block_fn=None, **kw):
    return OnChainUsdPriceFeed(
        quote_route_fn=route_fn, pools=_pools(), head_block_fn=head_block_fn,
        numeraire="USDC", stable_peg_usd=1.0,
        stables=("USDC", "USDT", "DAI", "USDbC"), peg_band_bps=200.0,
        ttl_s=12.0, max_block_lag=5, **kw)


def _usdc_out(usd, block=1000):
    """Build a quote_route_fn result paying `usd` USDC (6-dec) at `block`."""
    return {"final_out_wei": int(usd * 10 ** USDC_DEC), "block": block,
            "quoter": "0xQuoterV2"}


# ── numéraire is a configured anchor, never quoted ──────────────────────────
def test_usdc_numeraire_is_configured_peg_not_quoted():
    calls = []

    async def route_fn(hops):
        calls.append(hops)
        return _usdc_out(999.0)  # would be absurd if ever used

    feed = _feed(route_fn)
    assert _run(feed.price_source("USDC")) == 1.0
    assert calls == [], "numéraire must never hit an on-chain quote"
    prov = feed.provenance_for(["USDC"])[0]
    assert prov["source"] == "configured_numeraire" and prov["status"] == "ok"


# ── genuine on-chain pricing (direct + via-WETH) ────────────────────────────
def test_weth_priced_from_direct_onchain_quote():
    async def route_fn(hops):
        assert len(hops) == 1  # WETH/USDC direct pool exists
        return _usdc_out(3125.50, block=1000)

    feed = _feed(route_fn, head_block_fn=None)
    px = _run(feed.price_source("WETH"))
    assert abs(px - 3125.50) < 1e-6
    prov = feed.provenance_for(["WETH"])[0]
    assert prov["source"] == "onchain_usdc_direct"
    assert prov["path"] == ["WETH", "USDC"]
    assert prov["pools"] and prov["quoter"] == "0xQuoterV2"
    assert prov["block"] == 1000


def test_via_weth_two_hop_pricing_for_token_without_direct_usdc_pool():
    # weETH has no direct /USDC pool in the registry but weETH/WETH + WETH/USDC
    # do → must resolve via the two-hop path.
    async def route_fn(hops):
        assert len(hops) == 2
        return _usdc_out(3000.0)

    feed = _feed(route_fn)
    px = _run(feed.price_source("weETH"))
    assert abs(px - 3000.0) < 1e-6
    prov = feed.provenance_for(["weETH"])[0]
    assert prov["source"] == "onchain_usdc_via_weth"
    assert prov["path"] == ["WEETH", "WETH", "USDC"]


# ── cbETH: direct /USDC pool EXISTS in registry but is unpriceable on-chain ──
# (real on Base — cbETH/USDC 0.05% has ~no liquidity). The direct quote must
# NOT short-circuit to None; the feed must fall through to the genuine two-hop
# cbETH → WETH → USDC route (deep liquidity). Regression for the live VPS
# WETH=priced / cbETH=None blocker.
def test_cbeth_direct_quote_fails_falls_through_to_two_hop():
    hop_lens = []

    async def route_fn(hops):
        hop_lens.append(len(hops))
        if len(hops) == 1:
            return None            # direct cbETH/USDC pool exists but no liquidity
        return _usdc_out(2493.0)   # two-hop cbETH→WETH→USDC succeeds

    feed = _feed(route_fn)
    px = _run(feed.price_source("cbETH"))
    assert px is not None and abs(px - 2493.0) < 1e-6
    prov = feed.provenance_for(["cbETH"])[0]
    assert prov["source"] == "onchain_usdc_via_weth"
    assert prov["path"] == ["CBETH", "WETH", "USDC"]
    assert prov["status"] == "ok"
    assert len(prov["pools"]) == 2
    # direct attempted FIRST (1 hop), then the two-hop fallback (2 hops).
    assert hop_lens == [1, 2]


def test_cbeth_both_routes_fail_stays_fail_closed():
    # Direct AND two-hop both unpriceable → None (Gate 8 fails closed as today).
    async def route_fn(hops):
        return None

    feed = _feed(route_fn)
    assert _run(feed.price_source("cbETH")) is None
    assert feed.provenance_for(["cbETH"])[0]["status"] == "quote_failed"


def test_cbeth_direct_quote_used_when_it_succeeds():
    # Control: when the direct pool IS priceable, keep direct (no needless hop).
    hop_lens = []

    async def route_fn(hops):
        hop_lens.append(len(hops))
        return _usdc_out(2500.0)

    feed = _feed(route_fn)
    px = _run(feed.price_source("cbETH"))
    assert px is not None and abs(px - 2500.0) < 1e-6
    prov = feed.provenance_for(["cbETH"])[0]
    assert prov["source"] == "onchain_usdc_direct"
    assert prov["path"] == ["CBETH", "USDC"]
    assert hop_lens == [1]  # only the direct hop is quoted


# ── stablecoin peg guard ────────────────────────────────────────────────────
def test_stable_in_band_passes():
    async def route_fn(hops):
        return _usdc_out(1.005)  # 50 bps — inside 200 bps band

    feed = _feed(route_fn)
    assert abs(_run(feed.price_source("USDT")) - 1.005) < 1e-6
    assert feed.provenance_for(["USDT"])[0]["status"] == "ok"


def test_stable_out_of_band_fails_closed():
    async def route_fn(hops):
        return _usdc_out(1.05)  # 500 bps — outside band → reject

    feed = _feed(route_fn)
    assert _run(feed.price_source("DAI")) is None
    assert feed.provenance_for(["DAI"])[0]["status"] == "peg_out_of_band"


# ── freshness / staleness ───────────────────────────────────────────────────
def test_stale_block_lag_fails_closed():
    async def route_fn(hops):
        return _usdc_out(3000.0, block=1000)

    async def head():
        return 1010  # 10 blocks ahead > max_block_lag(5)

    feed = _feed(route_fn, head_block_fn=head)
    assert _run(feed.price_source("WETH")) is None
    p = feed.provenance_for(["WETH"])[0]
    assert p["status"] == "stale" and p["stale"] is True


def test_fresh_block_within_lag_passes():
    async def route_fn(hops):
        return _usdc_out(3000.0, block=1000)

    async def head():
        return 1003  # within 5

    feed = _feed(route_fn, head_block_fn=head)
    assert abs(_run(feed.price_source("WETH")) - 3000.0) < 1e-6


def test_unverifiable_head_fails_closed():
    async def route_fn(hops):
        return _usdc_out(3000.0, block=1000)

    async def head():
        return None  # head source configured but unavailable → fail closed

    feed = _feed(route_fn, head_block_fn=head)
    assert _run(feed.price_source("WETH")) is None
    assert feed.provenance_for(["WETH"])[0]["status"] == "stale_unverifiable"


# ── missing / no-path / quote failure ───────────────────────────────────────
def test_unknown_token_no_path():
    feed = _feed(_noop)
    assert _run(feed.price_source("SHIB")) is None
    assert feed.provenance_for(["SHIB"])[0]["status"] == "no_path"


def test_quote_failure_fails_closed():
    async def route_fn(hops):
        return None  # e.g. non-ok route / RPC error

    feed = _feed(route_fn)
    assert _run(feed.price_source("WETH")) is None
    assert feed.provenance_for(["WETH"])[0]["status"] == "quote_failed"


def test_provenance_for_unqueried_token_marks_not_evaluated():
    feed = _feed(_noop)
    assert feed.provenance_for(["AERO"])[0]["status"] == "not_evaluated"


# ── integration: feed → OnChainReserveTVLProvider → Gate 8 ──────────────────
def test_feed_drives_gate8_pass_when_both_tokens_priced():
    async def route_fn(hops):
        return _usdc_out(3000.0)  # WETH ~ $3000; USDC=peg

    feed = _feed(route_fn)
    weth = _addr("WETH")
    usdc = _addr("USDC")

    async def reserves_fn(chain, pool):
        # 100 WETH + 300k USDC → ~$600k TVL
        return ("WETH", 100.0, "USDC", 300_000.0)

    async def price_fn(chain, token):
        sym = "WETH" if token.lower() == weth.lower() else (
            "USDC" if token.lower() == usdc.lower() else token)
        return await feed.price_source(sym)

    tvl = _run(OnChainReserveTVLProvider(reserves_fn, price_fn)
               .get_pool_tvl_usd("base", "0xpool"))
    assert tvl is not None and tvl > 100_000.0
    g8 = FlashLoanGate8LiquidityDepth({}).evaluate(
        min_pool_tvl_usd_in_route=tvl)
    assert g8.passed is True


def test_feed_gate8_fail_closed_when_one_token_unpriceable():
    async def route_fn(hops):
        return None  # every quote fails → WETH unpriceable

    feed = _feed(route_fn)

    async def reserves_fn(chain, pool):
        return ("WETH", 100.0, "USDC", 300_000.0)

    async def price_fn(chain, token):
        # USDC resolves (peg) but WETH fails → TVL None
        sym = "USDC" if "833589" in token.lower() else "WETH"
        return await feed.price_source(sym)

    tvl = _run(OnChainReserveTVLProvider(reserves_fn, price_fn)
               .get_pool_tvl_usd("base", "0xpool"))
    assert tvl is None
    g8 = FlashLoanGate8LiquidityDepth({}).evaluate(
        min_pool_tvl_usd_in_route=(tvl or 0.0))
    assert g8.passed is False
