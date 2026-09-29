"""H05 runtime-composition wiring tests (offline, mocked).

Proves: (1) the exact-size borrow_sizer callback is actually injected into the
live quote provider; (2) all six chains build their OWN chain-specific
quote/RPC path (no Base/cross-chain leakage); (3) H05 stays disabled by default
so probe behaviour is preserved. No production RPC; no execution/sign/broadcast.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")

from arbicore.runtime.composition import (
    build_h05_borrow_sizer, build_multichain_price_source,
    build_multichain_quote_provider, _H05_CHAINS,
)

CHAINS = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")


def test_h05_chains_are_the_canonical_six():
    assert set(_H05_CHAINS) == set(CHAINS)


@pytest.mark.asyncio
async def test_sizer_none_when_disabled(monkeypatch):
    monkeypatch.delenv("ARBICORE_BORROW_SIZER_ENABLED", raising=False)
    monkeypatch.delenv("ARBICORE_PRICE_FEED_ENABLED", raising=False)
    assert await build_h05_borrow_sizer() is None
    assert await build_multichain_price_source() is None


# ── stubs for per-chain isolation proof ──────────────────────────────────────
def _chain_addr(chain, sym):
    # deterministic, chain-SPECIFIC token address (proves no cross-chain leak)
    tag = {"ethereum": "e1", "arbitrum": "a2", "base": "ba", "optimism": "07",
           "polygon": "b0", "bnb": "bb"}[chain]
    s = "01" if sym.upper() == "WETH" else "02"
    return "0x" + (tag + s) * 10


class _CapturingQuoter:
    def __init__(self):
        self.chains_seen = []

    async def quote_route(self, *, chain, hops):
        self.chains_seen.append(chain)
        hop = SimpleNamespace(dex="uniswap_v3", status="ok", block_number=100,
                              quoter_contract="0xq")
        # WETH(1e18) -> USDC(2000e6): a genuine-looking closed quote per chain
        return SimpleNamespace(status="ok", hops=[hop],
                               final_amount_out_wei=2000 * 10 ** 6,
                               aggregate_gas_estimate_units=1)


def _stub_eth_factory(chain):
    async def eth_call(to, data):
        return None  # resolver is stubbed, so eth_call body is never used
    return eth_call


def _stub_resolver_factory():
    async def resolve_chain(chain, eth_call):
        # one real-address WETH/USDC pool per chain, chain-specific addresses
        weth = _chain_addr(chain, "WETH")
        usdc = _chain_addr(chain, "USDC")
        pool = "0x" + ("cc" if chain != "bnb" else "dd") * 20
        return SimpleNamespace(
            chain=chain,
            pool_meta={pool.lower(): ("WETH", weth, 18, "USDC", usdc, 6)},
            resolved_specs=[{"venue_id": f"{chain}:v", "dex": "uniswap_v3",
                             "token_a": "WETH", "token_b": "USDC", "fee_bps": 5,
                             "pool_contract_address": pool,
                             "resolution": "onchain_resolved"}],
            unresolved=[])
    return resolve_chain


@pytest.mark.asyncio
async def test_six_chains_use_own_quote_path(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_USD_NUMERAIRE", "USDC")  # M2.5 numeraire
    q = _CapturingQuoter()
    src = await build_multichain_price_source(
        q, eth_call_factory=_stub_eth_factory, resolver=_stub_resolver_factory())
    assert src is not None
    assert set(src.configured_chains()) == set(CHAINS)  # all six built a feed
    # each chain prices WETH via ITS OWN quote_route(chain=...) call
    for ch in CHAINS:
        q.chains_seen.clear()
        price = await src.price_usd(ch, "WETH")
        assert price == pytest.approx(2000.0)
        assert q.chains_seen and set(q.chains_seen) == {ch}  # only THAT chain
    # unknown chain → None (fail closed, no leakage)
    assert await src.price_usd("solana", "WETH") is None


@pytest.mark.asyncio
async def test_callback_injected_into_quote_provider(monkeypatch):
    monkeypatch.setenv("ARBICORE_BORROW_SIZER_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")

    # a genuine (stubbed) price source → real sizer callback
    class _Src:
        async def price_usd(self, chain, token):
            return 2000.0 if str(token).upper() == "WETH" else None

    cb = await build_h05_borrow_sizer(price_source=_Src())
    assert cb is not None
    # exact size = $1000 / $2000 * 1e18 = 5e17
    assert await cb("arbitrum", "WETH", 1000.0) == 5 * 10 ** 17

    # inject into make_multichain_quote_provider via the composition seam and
    # prove the exact size reaches the quoter + the facts are marked exact.
    class _Q:
        def __init__(self):
            self.first_amt = None

        async def quote_route(self, *, chain, hops):
            self.first_amt = hops[0].get("amount_in_wei")
            hop = SimpleNamespace(dex="uniswap_v3", status="ok",
                                  block_number=1, quoter_contract="0xq")
            return SimpleNamespace(status="ok", hops=[hop, hop],
                                   final_amount_out_wei=6 * 10 ** 17,
                                   aggregate_gas_estimate_units=1)

    q = _Q()
    prov = build_multichain_quote_provider(q, "arbitrum", borrow_sizer=cb)
    assert prov is not None
    facts = await prov({"route_pools": ["v0", "v1"],
                        "cycle_token_path": ["WETH", "USDC", "WETH"],
                        "borrow_token": "WETH"}, 1000.0)
    assert facts is not None
    assert facts["size_basis"] == "exact"
    assert facts["quote_notional_usd"] == 1000.0
    assert q.first_amt == 5 * 10 ** 17  # exact size actually injected


@pytest.mark.asyncio
async def test_probe_preserved_when_no_sizer():
    # build_multichain_quote_provider without a sizer → probe (size_basis=probe)
    class _Q:
        async def quote_route(self, *, chain, hops):
            hop = SimpleNamespace(dex="uniswap_v3", status="ok",
                                  block_number=1, quoter_contract="0xq")
            return SimpleNamespace(status="ok", hops=[hop, hop],
                                   final_amount_out_wei=6 * 10 ** 17,
                                   aggregate_gas_estimate_units=1)

    prov = build_multichain_quote_provider(_Q(), "arbitrum")
    assert prov is not None
    facts = await prov({"route_pools": ["v0", "v1"],
                        "cycle_token_path": ["WETH", "USDC", "WETH"],
                        "borrow_token": "WETH"}, 1000.0)
    assert facts["size_basis"] == "probe"
    assert facts["quote_notional_usd"] is None
