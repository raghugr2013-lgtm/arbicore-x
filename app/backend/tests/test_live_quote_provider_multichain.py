"""Route integrity for the chain/venue-aware live quote provider (SHADOW).

Proves: chain preserved, venue preserved, chain-correct token + pool addresses,
fee tier preserved, hop N output feeds hop N+1 (deferred to QuoterRegistry),
quote/RPC/unsupported-venue/fallback all fail closed, and no passthrough becomes
a real quote. Deterministic + offline. No signing/broadcast.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from eth_abi import encode as _enc
from eth_utils import to_checksum_address

from arbicore.chains.registries import tokens_for
from arbicore.discovery import univ3_pool_resolver as R
from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    make_live_quote_provider,
)

CHAIN = "arbitrum"
_t = tokens_for(CHAIN)
WETH, USDC = _t["WETH"]["address"], _t["USDC"]["address"]
POOL = to_checksum_address("0x" + "c3" * 20)
FACTORY = R.univ3_factory_for(CHAIN)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _healthy_eth_call():
    async def eth_call(to, data):
        sel = data[:10]
        if to.lower() == FACTORY.lower():
            return "0x" + _enc(["address"], [POOL]).hex()
        if sel == R._SEL_TOKEN0:
            return "0x" + _enc(["address"], [to_checksum_address(WETH)]).hex()
        if sel == R._SEL_TOKEN1:
            return "0x" + _enc(["address"], [to_checksum_address(USDC)]).hex()
        if sel == R._SEL_FEE:
            return "0x" + _enc(["uint24"], [500]).hex()
        if sel == R._SEL_LIQUIDITY:
            return "0x" + _enc(["uint128"], [10**18]).hex()
        raise AssertionError(sel)
    return eth_call


class _FakeQuoter:
    def __init__(self, *, status="ok", hop_status="ok", final=2_000_000):
        self.status, self.hop_status, self.final = status, hop_status, final
        self.last_chain = None
        self.last_hops = None

    async def quote_route(self, *, chain, hops, rpc_url=None):
        self.last_chain, self.last_hops = chain, hops
        hop_objs = [SimpleNamespace(dex=h["dex"], status=self.hop_status,
                                    block_number=100 + i)
                    for i, h in enumerate(hops)]
        return SimpleNamespace(status=self.status, hops=hop_objs,
                               final_amount_out_wei=self.final,
                               aggregate_gas_estimate_units=210_000)


class _RecordingTVL:
    def __init__(self):
        self.calls = []

    async def get_pool_tvl_usd(self, chain, addr):
        self.calls.append((chain, addr))
        return 500_000.0


def _meta(**over):
    m = {
        "chain": CHAIN,
        "cycle_token_path": ["WETH", "USDC", "WETH"],
        "borrow_amount_wei": 10**18,
        "route_hops": [
            {"dex": "uniswap_v3", "token_in": "WETH", "token_out": "USDC", "fee": 500},
            {"dex": "uniswap_v3", "token_in": "USDC", "token_out": "WETH", "fee": 500},
        ],
    }
    m.update(over)
    return m


def _provider(quoter, *, eth_call=None, tvl=None):
    return make_live_quote_provider(
        quoter, tvl_provider=tvl,
        eth_call_for_chain=(lambda c: eth_call) if eth_call else None)


def test_chain_venue_token_fee_and_pool_are_chain_correct():
    q = _FakeQuoter()
    tvl = _RecordingTVL()
    prov = _provider(q, eth_call=_healthy_eth_call(), tvl=tvl)
    facts = _run(prov(_meta(), 10_000.0))
    assert facts is not None
    # chain preserved end-to-end
    assert q.last_chain == CHAIN and facts["chain"] == CHAIN
    # venue + fee + chain-correct tokens on the hop plan sent to the quoter
    assert q.last_hops[0]["dex"] == "uniswap_v3"
    assert q.last_hops[0]["fee"] == 500
    assert q.last_hops[0]["token_in"] == WETH and q.last_hops[0]["token_out"] == USDC
    # hop N output -> hop N+1 input is deferred to QuoterRegistry: only hop0 has
    # an explicit amount_in, later hops are chained by quote_route.
    assert q.last_hops[0]["amount_in_wei"] == 10**18
    assert "amount_in_wei" not in q.last_hops[1]
    # pool address is chain-correct (resolved on-chain) and used for real TVL
    assert (CHAIN, POOL) in tvl.calls
    assert facts["hop_legs"][0]["depth_usd"] == 500_000.0
    assert facts["hop_legs"][0]["venue_id"] == f"uniswap_v3:{CHAIN}"


def test_quote_failure_fails_closed():
    q = _FakeQuoter(status="fallback:break_even")
    prov = _provider(q, eth_call=_healthy_eth_call())
    assert _run(prov(_meta(), 10_000.0)) is None


def test_passthrough_hop_cannot_become_real_quote():
    q = _FakeQuoter(status="ok", hop_status="fallback:revert")
    prov = _provider(q, eth_call=_healthy_eth_call())
    assert _run(prov(_meta(), 10_000.0)) is None


def test_rpc_failure_fails_closed():
    async def boom(to, data):
        raise RuntimeError("rpc_down")
    q = _FakeQuoter()
    prov = _provider(q, eth_call=boom)
    assert _run(prov(_meta(), 10_000.0)) is None
    assert q.last_hops is None            # never even reached the quoter


def test_missing_rpc_for_nonbase_fails_closed():
    q = _FakeQuoter()
    prov = make_live_quote_provider(q, eth_call_for_chain=None)  # no RPC seam
    assert _run(prov(_meta(), 10_000.0)) is None


def test_unsupported_venue_family_fails_closed():
    q = _FakeQuoter()
    prov = _provider(q, eth_call=_healthy_eth_call())
    meta = _meta(route_hops=[
        {"dex": "curve_stable", "token_in": "WETH", "token_out": "USDC", "fee": 0},
        {"dex": "curve_stable", "token_in": "USDC", "token_out": "WETH", "fee": 0},
    ])
    assert _run(prov(meta, 10_000.0)) is None


def test_non_closed_cycle_fails_closed():
    q = _FakeQuoter()
    prov = _provider(q, eth_call=_healthy_eth_call())
    meta = _meta(cycle_token_path=["WETH", "USDC", "USDC"])
    assert _run(prov(meta, 10_000.0)) is None


def test_zero_borrow_amount_fails_closed():
    q = _FakeQuoter()
    prov = _provider(q, eth_call=_healthy_eth_call())
    assert _run(prov(_meta(borrow_amount_wei=0), 10_000.0)) is None
