"""P1 regression — H06 endpoint chain-identity guard + H07 TVL chain-scoping.

H06: an RPC endpoint may only be used for a chain if eth_chainId proves it
serves that chain; wrong/ambiguous/unreadable identity fails closed (endpoint
dropped from selection AND failover). H07: a chain-scoped TVL provider must not
feed depth into a route on a different chain.
Offline / deterministic (eth_chainId reader is stubbed).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from arbicore.execution import quoter as q
from arbicore.scanners.flash_loan_arbitrage import live_quote_provider as lqp


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---- H06 endpoint chain-identity ------------------------------------------

def _stub_chain_reader(mapping):
    async def _reader(url, timeout=8.0):
        return mapping.get(url)
    return _reader


def test_expected_ids_cover_six_chains():
    for name, cid in (("base", 8453), ("ethereum", 1), ("arbitrum", 42161),
                      ("optimism", 10), ("polygon", 137), ("bnb", 56)):
        assert q._expected_chain_id(name) == cid
    assert q._expected_chain_id("solana") is None  # unknown → None (fail closed)


def test_endpoint_must_match_chain_id():
    q._HOST_CHAIN_ID.clear()
    q._read_chain_id = _stub_chain_reader({
        "https://base-node": 8453, "https://eth-node": 1, "https://liar": 999})
    # correct chain
    assert _run(q._endpoint_serves_chain("https://base-node", "base")) is True
    # a Base-labelled request pointed at an Ethereum node → fail closed
    q._HOST_CHAIN_ID.clear()
    assert _run(q._endpoint_serves_chain("https://eth-node", "base")) is False
    # unknown observed id → fail closed
    q._HOST_CHAIN_ID.clear()
    assert _run(q._endpoint_serves_chain("https://liar", "base")) is False
    # unknown target chain → fail closed
    assert _run(q._endpoint_serves_chain("https://base-node", "dogechain")) is False


def test_unreadable_endpoint_fails_closed_and_is_reprobed():
    q._HOST_CHAIN_ID.clear()
    q._read_chain_id = _stub_chain_reader({})  # every read returns None
    assert _run(q._endpoint_serves_chain("https://dead", "base")) is False
    # a transient failure is NOT cached, so a later successful read can recover
    q._read_chain_id = _stub_chain_reader({"https://dead": 8453})
    assert _run(q._endpoint_serves_chain("https://dead", "base")) is True


def test_failover_filters_to_verified_endpoints_in_order():
    q._HOST_CHAIN_ID.clear()
    q._read_chain_id = _stub_chain_reader({
        "https://eth-node": 1, "https://base-a": 8453, "https://base-b": 8453})
    out = _run(q._verified_chain_endpoints(
        ["https://eth-node", "https://base-a", "https://base-b"], "base"))
    assert out == ["https://base-a", "https://base-b"]


def test_default_backend_enables_guard_injected_backend_disables():
    # production path (no injected backends) → guard ON
    assert q.QuoterRegistry()._verify_chain_identity is True
    # unit path (custom backend injected) → guard OFF unless forced
    reg = q.QuoterRegistry(backends=[q.UniV3QuoterV2()])
    assert reg._verify_chain_identity is False
    assert q.QuoterRegistry(backends=[q.UniV3QuoterV2()],
                            verify_chain_identity=True)._verify_chain_identity is True


# ---- H07 TVL chain-scoping -------------------------------------------------

class _AnyChainTVL:
    def __init__(self):
        self.calls = []

    async def get_pool_tvl_usd(self, chain, addr):
        self.calls.append((chain, addr))
        return 500_000.0


class _FakeReg:
    async def quote_route(self, *, chain, hops):
        hop = SimpleNamespace(dex="uniswap_v3", status="ok", block_number=7)
        return SimpleNamespace(status="ok", final_amount_out_wei=int(1.05e16),
                               aggregate_gas_estimate_units=300_000,
                               hops=[hop, hop])


def _meta(chain):
    return {"chain": chain, "borrow_token": "WETH", "route_pools": ["p1", "p2"],
            "cycle_token_path": ["WETH", "USDC", "WETH"]}


def test_tvl_provider_not_consulted_off_its_chain():
    tvl = _AnyChainTVL()
    # provider declared for base, but we quote an ethereum route (base leg is
    # handled via _plan_base; here we just assert the TVL guard on chain match)
    prov = lqp.make_live_quote_provider(
        _FakeReg(), tvl_provider=tvl, tvl_provider_chain="base")
    # base route → provider may be consulted
    _run(prov(_meta("base"), 10_000.0))
    base_calls = list(tvl.calls)
    # ethereum route with a base-scoped provider → provider MUST NOT be called
    tvl.calls.clear()
    _run(prov(_meta("ethereum"), 10_000.0))
    assert tvl.calls == [], "H07: base-scoped TVL provider leaked into ethereum route"
