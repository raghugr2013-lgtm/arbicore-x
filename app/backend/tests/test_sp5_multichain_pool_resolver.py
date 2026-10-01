"""SP-5 — multichain on-chain pool resolver (offline, mocked eth_call).

Deterministic unit tests with a fully mocked eth_call. These tests do NOT and
cannot demonstrate live on-chain capability — they verify the resolver's
logic, fail-closed behavior, and SP-3/SP-4 compatibility only.
"""
from __future__ import annotations

import os

import pytest
from eth_utils import to_checksum_address

# SP-4 seam import pulls composition (Mongo-backed DI); motor is lazy → dummy URL.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")

from arbicore.discovery.multichain_pool_resolver import (
    MultichainPoolResolver, resolve_chain,
    SEL_GETPOOL_UINT24, SEL_DECIMALS,
)
from arbicore.searcher.aero_resolver import SEL_TOKEN0, SEL_TOKEN1
from arbicore.runtime.composition import build_multichain_tvl_provider

WETH = to_checksum_address("0x" + "a1" * 20)
USDC = to_checksum_address("0x" + "b2" * 20)
POOL = to_checksum_address("0x" + "cc" * 20)
FACTORY = to_checksum_address("0x" + "f0" * 20)

TOKENS = {"WETH": WETH, "USDC": USDC}


def _word_addr(addr: str) -> str:
    return "0x" + addr.lower().replace("0x", "").rjust(64, "0")


def _word_uint(n: int) -> str:
    return "0x" + ("%x" % int(n)).rjust(64, "0")


class FakeEth:
    """Mock eth_call dispatching by selector. Configurable for each scenario."""

    def __init__(self, *, pool=POOL, token0=WETH, token1=USDC,
                 decimals=None, fail=False, malformed_getpool=False,
                 fail_decimals=False):
        self.pool = pool
        self.token0 = token0
        self.token1 = token1
        self.decimals = decimals if decimals is not None else {
            WETH.lower(): 18, USDC.lower(): 6}
        self.fail = fail
        self.malformed_getpool = malformed_getpool
        self.fail_decimals = fail_decimals

    async def __call__(self, to, data):
        if self.fail:
            return None
        sel = data[:10]
        if sel == SEL_GETPOOL_UINT24:
            if self.malformed_getpool:
                return "0xdead"  # too short → decode fails closed
            return _word_addr(self.pool) if self.pool else _word_addr("0x" + "00" * 20)
        if sel == SEL_TOKEN0:
            return _word_addr(self.token0)
        if sel == SEL_TOKEN1:
            return _word_addr(self.token1)
        if sel == SEL_DECIMALS:
            if self.fail_decimals:
                return None
            return _word_uint(self.decimals.get((to or "").lower(), 18))
        return None


def _resolver(eth, chain="arbitrum"):
    return MultichainPoolResolver(
        eth, chain, factory_by_dex={"uniswap_v3": FACTORY},
        token_resolver=lambda s: TOKENS.get(str(s).upper()))


# 1. Successful getPool resolution + 4/9. decimals + metadata propagation
@pytest.mark.asyncio
async def test_successful_resolution_and_metadata():
    rp = await _resolver(FakeEth()).resolve("uniswap_v3", "WETH", "USDC", 500)
    assert rp is not None
    assert rp.address.lower() == POOL.lower()
    assert rp.pool_meta[POOL.lower()] == ("WETH", WETH, 18, "USDC", USDC, 6)
    assert rp.provenance["method"] == "getPool(address,address,uint24)"


# 2. Zero-address / nonexistent pool → fail closed
@pytest.mark.asyncio
async def test_zero_address_pool_fails_closed():
    rp = await _resolver(FakeEth(pool=None)).resolve("uniswap_v3", "WETH", "USDC", 500)
    assert rp is None


# 3. Invalid token pair → fail closed
@pytest.mark.asyncio
async def test_invalid_token_pair_fails_closed():
    r = _resolver(FakeEth())
    assert await r.resolve("uniswap_v3", "WETH", "UNKNOWN", 500) is None  # unknown symbol
    assert await r.resolve("uniswap_v3", "WETH", "WETH", 500) is None     # identical


# 5. RPC/eth_call failure → fail closed
@pytest.mark.asyncio
async def test_rpc_failure_fails_closed():
    rp = await _resolver(FakeEth(fail=True)).resolve("uniswap_v3", "WETH", "USDC", 500)
    assert rp is None


@pytest.mark.asyncio
async def test_decimals_failure_fails_closed():
    rp = await _resolver(FakeEth(fail_decimals=True)).resolve("uniswap_v3", "WETH", "USDC", 500)
    assert rp is None


# 6. Malformed/unexpected return data → fail closed
@pytest.mark.asyncio
async def test_malformed_getpool_fails_closed():
    rp = await _resolver(FakeEth(malformed_getpool=True)).resolve("uniswap_v3", "WETH", "USDC", 500)
    assert rp is None


# 7. Unsupported chain / DEX → fail closed
@pytest.mark.asyncio
async def test_unsupported_chain_and_dex_fail_closed():
    assert await _resolver(FakeEth(), chain="base").resolve("uniswap_v3", "WETH", "USDC", 500) is None
    assert await _resolver(FakeEth(), chain="solana").resolve("uniswap_v3", "WETH", "USDC", 500) is None
    assert await _resolver(FakeEth()).resolve("camelot_v3", "WETH", "USDC", 500) is None  # unsupported dex


# 8/10. No accidental fallback to an unrelated pool (token0/token1 mismatch)
@pytest.mark.asyncio
async def test_no_accidental_unrelated_pool():
    other = to_checksum_address("0x" + "99" * 20)
    # getPool returns POOL, but the pool's token0/token1 don't match the pair.
    rp = await _resolver(FakeEth(token0=other, token1=USDC)).resolve(
        "uniswap_v3", "WETH", "USDC", 500)
    assert rp is None


@pytest.mark.asyncio
async def test_missing_factory_fails_closed():
    r = MultichainPoolResolver(FakeEth(), "arbitrum", factory_by_dex={},
                               token_resolver=lambda s: TOKENS.get(str(s).upper()))
    assert await r.resolve("uniswap_v3", "WETH", "USDC", 500) is None


# resolve_chain integration → SP-3-compatible resolved_specs + unresolved list
@pytest.mark.asyncio
async def test_resolve_chain_integration_and_sp3_shape():
    specs = [
        {"venue_id": "uniswap_v3:WETH:USDC:5", "dex": "uniswap_v3",
         "token_a": "WETH", "token_b": "USDC", "fee_bps": 5,
         "pool_contract_address": None, "resolution": "onchain_pending"},
        {"venue_id": "uniswap_v3:WETH:UNKNOWN:5", "dex": "uniswap_v3",
         "token_a": "WETH", "token_b": "UNKNOWN", "fee_bps": 5,
         "pool_contract_address": None, "resolution": "onchain_pending"},
    ]
    res = await resolve_chain(
        "arbitrum", FakeEth(), specs=specs,
        factory_by_dex={"uniswap_v3": FACTORY},
        token_resolver=lambda s: TOKENS.get(str(s).upper()))
    assert POOL.lower() in res.pool_meta
    assert len(res.resolved_specs) == 1
    rs = res.resolved_specs[0]
    for k in ("venue_id", "dex", "token_a", "token_b", "fee_bps", "pool_contract_address"):
        assert k in rs
    assert rs["pool_contract_address"].lower() == POOL.lower()
    assert rs["resolution"] == "onchain_resolved"
    assert "uniswap_v3:WETH:UNKNOWN:5" in res.unresolved


# 9 (end-to-end): SP-5 pool_meta feeds SP-4 TVL path and computes real TVL
@pytest.mark.asyncio
async def test_sp5_pool_meta_feeds_sp4_tvl():
    res = await resolve_chain(
        "arbitrum", FakeEth(),
        specs=[{"venue_id": "v", "dex": "uniswap_v3", "token_a": "WETH",
                "token_b": "USDC", "fee_bps": 5,
                "pool_contract_address": None, "resolution": "onchain_pending"}],
        factory_by_dex={"uniswap_v3": FACTORY},
        token_resolver=lambda s: TOKENS.get(str(s).upper()))
    assert res.pool_meta  # populated

    async def price_source(token):
        return {"WETH": 2000.0, "USDC": 1.0}.get(str(token).upper())

    async def tvl_eth_call(to, data):
        # ERC-20 balanceOf(pool) reads for the SP-4 reserves fn.
        bal = {WETH.lower(): 2 * 10**18, USDC.lower(): 4000 * 10**6}
        return _word_uint(bal.get((to or "").lower(), 0))

    # Feed SP-5 pool_meta straight into the SP-4 provider (no redesign).
    from arbicore.searcher.runtime import build_evm_tvl_provider
    prov = build_evm_tvl_provider("arbitrum", tvl_eth_call, price_source, res.pool_meta)
    assert prov is not None
    tvl = await prov.get_pool_tvl_usd("arbitrum", POOL)
    assert tvl == pytest.approx(2 * 2000.0 + 4000 * 1.0)  # 8000

    # And the composition seam accepts the same pool_meta — now UNDER the
    # canonical operator-RPC gate (H06 remediation). With NO operator RPC it
    # FAILS CLOSED (None); only a configured operator RPC yields a provider.
    import os
    for _k in ("ARBITRUM_RPC_URL", "PROVIDER_RPC_URL_ARBITRUM",
               "PROVIDER_RPC_URLS_ARBITRUM", "ARBICORE_RPC_URL_ARBITRUM"):
        os.environ.pop(_k, None)
    assert build_multichain_tvl_provider(
        "arbitrum", pool_meta=res.pool_meta, price_source=price_source) is None
    os.environ["ARBITRUM_RPC_URL"] = "https://arb.operator.example/rpc"
    try:
        assert build_multichain_tvl_provider(
            "arbitrum", pool_meta=res.pool_meta, price_source=price_source) is not None
    finally:
        os.environ.pop("ARBITRUM_RPC_URL", None)
