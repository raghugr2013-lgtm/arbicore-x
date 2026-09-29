"""H05 correction — Base canonical-registry integration in the six-chain price
source (offline, mocked). Proves Base uses the canonical Base pool registry (not
the SP-5 resolver), non-Base still uses SP-5, and everything fails closed.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")

import arbicore.runtime.composition as comp
from arbicore.runtime.composition import (
    build_multichain_price_source, _base_price_pools,
)


class _CapturingQuoter:
    def __init__(self):
        self.chains_seen = []

    async def quote_route(self, *, chain, hops):
        self.chains_seen.append(chain)
        hop = SimpleNamespace(dex="uniswap_v3", status="ok", block_number=1,
                              quoter_contract="0xq")
        return SimpleNamespace(status="ok", hops=[hop],
                               final_amount_out_wei=2000 * 10 ** 6,  # WETH->2000 USDC
                               aggregate_gas_estimate_units=1)


def _eth_ok(chain):
    async def eth_call(to, data):
        return None
    return eth_call


# A + B: Base price source builds from canonical pools and prices WETH->USD
@pytest.mark.asyncio
async def test_base_price_source_and_weth_pricing(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_USD_NUMERAIRE", "USDC")
    q = _CapturingQuoter()
    src = await build_multichain_price_source(
        q, chains=("base",), eth_call_factory=_eth_ok)
    assert src is not None
    assert src.configured_chains() == ["base"]
    price = await src.price_usd("base", "WETH")
    assert price == pytest.approx(2000.0)
    assert set(q.chains_seen) == {"base"}  # Base-specific quoter route used


# C: Base does NOT call resolve_chain
@pytest.mark.asyncio
async def test_base_does_not_use_sp5_resolver(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_USD_NUMERAIRE", "USDC")
    calls = []

    async def spy_resolver(chain, eth_call):
        calls.append(chain)
        return SimpleNamespace(resolved_specs=[], pool_meta={}, unresolved=[])

    q = _CapturingQuoter()
    await build_multichain_price_source(
        q, chains=("base",), eth_call_factory=_eth_ok, resolver=spy_resolver)
    assert calls == []  # SP-5 resolver never invoked for Base


# D: Non-Base chains still use SP-5 resolve_chain
@pytest.mark.asyncio
async def test_nonbase_uses_sp5_resolver(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_USD_NUMERAIRE", "USDC")
    calls = []
    WETH = "0x" + "a1" * 20
    USDC = "0x" + "b2" * 20
    POOL = "0x" + "cc" * 20

    async def spy_resolver(chain, eth_call):
        calls.append(chain)
        return SimpleNamespace(
            resolved_specs=[{"venue_id": "v", "dex": "uniswap_v3",
                             "token_a": "WETH", "token_b": "USDC", "fee_bps": 5,
                             "pool_contract_address": POOL}],
            pool_meta={POOL.lower(): ("WETH", WETH, 18, "USDC", USDC, 6)},
            unresolved=[])

    q = _CapturingQuoter()
    src = await build_multichain_price_source(
        q, chains=("arbitrum",), eth_call_factory=_eth_ok, resolver=spy_resolver)
    assert calls == ["arbitrum"]  # SP-5 used for non-Base
    assert src is not None and src.configured_chains() == ["arbitrum"]


# E: Missing eligible Base pools → fail closed (no feed)
@pytest.mark.asyncio
async def test_base_fail_closed_when_no_eligible_pools(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setattr(comp, "_base_price_pools", lambda: [])
    src = await build_multichain_price_source(
        _CapturingQuoter(), chains=("base",), eth_call_factory=_eth_ok)
    assert src is None  # no eligible base pool → fail closed


@pytest.mark.asyncio
async def test_base_fail_closed_when_no_rpc(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    src = await build_multichain_price_source(
        _CapturingQuoter(), chains=("base",), eth_call_factory=lambda ch: None)
    assert src is None  # no Base RPC → fail closed


# F: flags disabled by default → None
@pytest.mark.asyncio
async def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ARBICORE_PRICE_FEED_ENABLED", raising=False)
    assert await build_multichain_price_source(_CapturingQuoter(),
                                               chains=("base",)) is None


def test_base_price_pools_are_eligible_and_real():
    pools = _base_price_pools()
    assert pools, "expected real canonical Base UniV3 pools"
    for p in pools:
        assert p.dex == "uniswap_v3"
        assert p.address and p.address.startswith("0x")
        assert p.token0_address and p.token1_address
        assert isinstance(p.token0_decimals, int) and isinstance(p.token1_decimals, int)
        assert isinstance(p.fee_bps, int)
