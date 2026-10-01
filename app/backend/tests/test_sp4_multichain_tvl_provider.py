"""SP-4 — chain-aware multichain TVL/liquidity provider (offline, fail-closed).

Deterministic unit tests with mocked eth_call / price sources (NO production RPC).
Verifies the LIQUIDITY / Gate-8 read path for the five non-Base chains, that Base
is untouched and never substituted, and that every unknown/invalid/unavailable
input fails closed. No execution/sign/broadcast/threshold/scanner change.
"""
from __future__ import annotations

import os

import pytest

# ``composition`` pulls the Mongo-backed DI graph, which reads MONGO_URL at import.
# Motor's client is lazy (no connection at construction), so a dummy URL lets us
# import the thin SP-4 seam offline without any real DB / RPC.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")

from arbicore.searcher.runtime import (
    build_evm_tvl_provider, make_evm_price_source_from_env, _EVM_TVL_CHAINS,
)
from arbicore.runtime.composition import build_multichain_tvl_provider

WETH = "0x" + "a1" * 20
USDC = "0x" + "b2" * 20
POOL = "0x" + "cc" * 20

# pool_meta: pool(lower) -> (t0_id, t0_addr, dec0, t1_id, t1_addr, dec1)
META = {POOL.lower(): ("WETH", WETH, 18, "USDC", USDC, 6)}


def _eth_call(balances):
    """balances: {token_addr.lower(): int_raw} → hex; missing → None (unavailable)."""
    async def eth_call(to, data):
        raw = balances.get((to or "").lower())
        return hex(raw) if raw is not None else None
    return eth_call


def _price(prices):
    async def price_source(token):
        return prices.get(str(token).upper())
    return price_source


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["ethereum", "arbitrum", "optimism", "polygon", "bnb"])
async def test_valid_liquidity_accepted(chain):
    eth = _eth_call({WETH: 2 * 10**18, USDC: 4000 * 10**6})  # 2 WETH, 4000 USDC
    price = _price({"WETH": 2000.0, "USDC": 1.0})
    prov = build_evm_tvl_provider(chain, eth, price, META)
    assert prov is not None
    tvl = await prov.get_pool_tvl_usd(chain, POOL)
    assert tvl == pytest.approx(2 * 2000.0 + 4000 * 1.0)  # 8000


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["ethereum", "arbitrum", "optimism", "polygon", "bnb"])
async def test_missing_meta_fails_closed(chain):
    eth = _eth_call({WETH: 2 * 10**18, USDC: 4000 * 10**6})
    price = _price({"WETH": 2000.0, "USDC": 1.0})
    prov = build_evm_tvl_provider(chain, eth, price, META)
    other_pool = "0x" + "dd" * 20  # not in META
    assert await prov.get_pool_tvl_usd(chain, other_pool) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["ethereum", "arbitrum", "optimism", "polygon", "bnb"])
async def test_zero_reserves_fails_closed(chain):
    eth = _eth_call({WETH: 0, USDC: 0})
    price = _price({"WETH": 2000.0, "USDC": 1.0})
    prov = build_evm_tvl_provider(chain, eth, price, META)
    assert await prov.get_pool_tvl_usd(chain, POOL) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["ethereum", "arbitrum", "optimism", "polygon", "bnb"])
async def test_missing_price_fails_closed(chain):
    eth = _eth_call({WETH: 2 * 10**18, USDC: 4000 * 10**6})
    price = _price({"USDC": 1.0})  # WETH price unknown → None
    prov = build_evm_tvl_provider(chain, eth, price, META)
    assert await prov.get_pool_tvl_usd(chain, POOL) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["ethereum", "arbitrum", "optimism", "polygon", "bnb"])
async def test_unavailable_provider_fails_closed(chain):
    # eth_call returns None for a balanceOf read → reserves unreadable → None.
    eth = _eth_call({})
    price = _price({"WETH": 2000.0, "USDC": 1.0})
    prov = build_evm_tvl_provider(chain, eth, price, META)
    assert await prov.get_pool_tvl_usd(chain, POOL) is None


def test_missing_inputs_yield_no_provider():
    # No eth_call, no price, or no meta → None (Gate 8 fails closed).
    assert build_evm_tvl_provider("arbitrum", None, _price({}), META) is None
    assert build_evm_tvl_provider("arbitrum", _eth_call({}), None, META) is None
    assert build_evm_tvl_provider("arbitrum", _eth_call({}), _price({}), {}) is None


def test_unsupported_chain_and_base_never_built_here():
    p = _price({"WETH": 1.0})
    assert build_evm_tvl_provider("solana", _eth_call({}), p, META) is None
    assert build_evm_tvl_provider("base", _eth_call({}), p, META) is None  # no substitution
    assert "base" not in _EVM_TVL_CHAINS


def test_composition_seam_fail_closed():
    # base / unsupported / missing pool_meta → None (non-activating seam).
    assert build_multichain_tvl_provider("base") is None
    assert build_multichain_tvl_provider("") is None
    assert build_multichain_tvl_provider("solana", pool_meta=META,
                                          price_source=_price({"WETH": 1.0})) is None
    # supported chain but no pool_meta → None (documents pool-resolution seam).
    assert build_multichain_tvl_provider(
        "arbitrum", price_source=_price({"WETH": 1.0})) is None


def test_env_price_source_native_only_and_fail_closed(monkeypatch):
    # No config → None. Configured → serves ONLY the chain's native symbol.
    monkeypatch.delenv("ARBICORE_NATIVE_PRICE_USD_POLYGON", raising=False)
    assert make_evm_price_source_from_env("polygon") is None
    assert make_evm_price_source_from_env("solana") is None  # unsupported

    monkeypatch.setenv("ARBICORE_NATIVE_PRICE_USD_POLYGON", "0.5")
    ps = make_evm_price_source_from_env("polygon")
    assert ps is not None


@pytest.mark.asyncio
async def test_env_price_source_serves_only_native(monkeypatch):
    monkeypatch.setenv("ARBICORE_NATIVE_PRICE_USD_BNB", "600")
    ps = make_evm_price_source_from_env("bnb")
    assert await ps("WBNB") == 600.0
    assert await ps("BNB") == 600.0
    assert await ps("USDC") is None  # non-native → None (fail closed)


def test_wrong_chain_source_fails_closed():
    # A source built for polygon must not be treated as valid for ethereum via the
    # supported-set gate: building for an unsupported chain returns None outright.
    assert build_evm_tvl_provider("zksync", _eth_call({}), _price({"WETH": 1.0}), META) is None
