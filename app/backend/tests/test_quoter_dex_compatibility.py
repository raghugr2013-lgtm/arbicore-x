"""Existing quoters are reachable from the generic route planner.

Sushi, Camelot, QuickSwap, Pancake, and Aerodrome were dropped because
``_plan_generic_evm`` accepted only Uniswap V3 and Balancer V2. These tests
use injected resolvers. They do not quote mainnet and do not add a quoter.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    _plan_generic_evm, hop_quote_capable, make_live_quote_provider,
)
from arbicore.scanners.flash_loan_arbitrage.route_search import PoolNode

_POOL = "0x" + "ab" * 20
_PID = "0x" + "cd" * 32


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _eth(_to, _data):
    return "0x"


def _meta(chain, dex, *, fee=500, pool="venue", extra=None):
    hop = {"dex": dex, "token_in": "WETH", "token_out": "USDC", "pool": pool}
    back = {"dex": dex, "token_in": "USDC", "token_out": "WETH", "pool": pool}
    if fee is not None:
        hop["fee"] = fee
        back["fee"] = fee
    if extra:
        hop.update(extra)
        back.update(extra)
    return {
        "chain": chain,
        "borrow_token": "WETH",
        "borrow_amount_wei": 10 ** 16,
        "cycle_token_path": ["WETH", "USDC", "WETH"],
        "route_hops": [hop, back],
    }


def _patch_univ3(monkeypatch, result, seen):
    async def _resolve(chain, a, b, fee, *, eth_call, factory=None, dex="uniswap_v3"):
        seen.append({"chain": chain, "dex": dex, "fee": fee})
        return result

    monkeypatch.setattr(
        "arbicore.discovery.univ3_pool_resolver.resolve_univ3_pool", _resolve)


def _patch_univ2(monkeypatch, result, seen):
    async def _resolve(chain, a, b, *, eth_call, dex="sushiswap_v2", factory=None):
        seen.append({"chain": chain, "dex": dex, "univ3": False})
        return result

    monkeypatch.setattr(
        "arbicore.discovery.univ3_pool_resolver.resolve_univ2_pool", _resolve)


def _patch_algebra(monkeypatch, result, seen):
    async def _resolve(chain, a, b, *, eth_call, dex, factory=None):
        seen.append({"chain": chain, "dex": dex})
        return result

    monkeypatch.setattr(
        "arbicore.discovery.algebra_pool_resolver.resolve_algebra_pool", _resolve)


def test_sushi_v3_and_pancake_plan_only_when_resolved(monkeypatch):
    seen = []
    _patch_univ3(monkeypatch, {"pool_address": _POOL}, seen)
    sushi = _run(_plan_generic_evm("arbitrum", _meta("arbitrum", "sushiswap_v3"), _eth))
    assert sushi is not None
    assert sushi[0][0].dex == "sushiswap_v3"
    assert sushi[0][0].pool_address == _POOL
    assert sushi[0][0].fee == 500
    assert seen[-1]["dex"] == "sushiswap_v3"

    seen.clear()
    pancake = _run(_plan_generic_evm("bnb", _meta("bnb", "pancakeswap_v3"), _eth))
    assert pancake is not None
    assert pancake[0][0].dex == "pancakeswap_v3"
    assert seen[-1]["dex"] == "pancakeswap_v3"

    _patch_univ3(monkeypatch, None, seen)
    assert _run(_plan_generic_evm(
        "arbitrum", _meta("arbitrum", "sushiswap_v3"), _eth)) is None
    assert _run(_plan_generic_evm(
        "bnb", _meta("bnb", "pancakeswap_v3"), _eth)) is None


def test_sushi_v3_off_its_chain_does_not_resolve(monkeypatch):
    async def _boom(*_a, **_k):
        raise AssertionError("resolver must not run when the quoter has no contract")

    monkeypatch.setattr(
        "arbicore.discovery.univ3_pool_resolver.resolve_univ3_pool", _boom)
    assert _run(_plan_generic_evm(
        "ethereum", _meta("ethereum", "sushiswap_v3"), _eth)) is None


def test_sushi_v2_uses_pair_resolver_not_univ3(monkeypatch):
    seen = []

    async def _univ3(*_a, **_k):
        raise AssertionError("UniV3 getPool must not plan a V2 hop")

    _patch_univ2(monkeypatch, {"pool_address": _POOL}, seen)
    monkeypatch.setattr(
        "arbicore.discovery.univ3_pool_resolver.resolve_univ3_pool", _univ3)
    planned = _run(_plan_generic_evm(
        "ethereum", _meta("ethereum", "sushiswap_v2", fee=None), _eth))
    assert planned is not None
    assert planned[0][0].dex == "sushiswap_v2"
    assert planned[0][0].fee is None
    assert planned[0][0].pool_address == _POOL
    assert seen and seen[0]["univ3"] is False

    _patch_univ2(monkeypatch, None, seen)
    assert _run(_plan_generic_evm(
        "ethereum", _meta("ethereum", "sushiswap_v2", fee=None), _eth)) is None


def test_algebra_plans_without_inventing_a_fee_tier(monkeypatch):
    seen = []
    _patch_algebra(monkeypatch, {"pool_address": _POOL}, seen)
    camelot = _run(_plan_generic_evm(
        "arbitrum", _meta("arbitrum", "camelot_v3", fee=None), _eth))
    quick = _run(_plan_generic_evm(
        "polygon", _meta("polygon", "quickswap_v3", fee=None), _eth))
    assert camelot is not None and camelot[0][0].fee is None
    assert camelot[0][0].dex == "camelot_v3"
    assert quick is not None and quick[0][0].dex == "quickswap_v3"
    assert quick[0][0].fee is None
    assert {row["dex"] for row in seen} == {"camelot_v3", "quickswap_v3"}

    _patch_algebra(monkeypatch, None, seen)
    assert _run(_plan_generic_evm(
        "arbitrum", _meta("arbitrum", "camelot_v3", fee=None), _eth)) is None


def test_curve_and_velodrome_stay_unplanned():
    assert _run(_plan_generic_evm(
        "ethereum", _meta("ethereum", "curve_stable", fee=0), _eth)) is None
    assert _run(_plan_generic_evm(
        "optimism", _meta("optimism", "velodrome_v2", fee=None), _eth)) is None


def test_balancer_still_requires_explicit_identity():
    synthetic = _meta("ethereum", "balancer_v2", fee=None,
                      pool="balancer_v2:USDC:WETH:x")
    assert _run(_plan_generic_evm("ethereum", synthetic, _eth)) is None
    explicit = _meta("ethereum", "balancer_v2", fee=None, pool="ignored",
                     extra={"pool_id": _PID})
    planned = _run(_plan_generic_evm("ethereum", explicit, _eth))
    assert planned is not None
    assert planned[0][0].dex == "balancer_v2"
    assert planned[0][0].pool_id == _PID
    # BNB has no Balancer vault, so the hop is not quoted there.
    assert _run(_plan_generic_evm("bnb", explicit, _eth)) is None


def test_base_aerodrome_route_hops_use_canonical_identity(monkeypatch):
    slip_id = "aerodrome_slipstream:USDC:WETH:100"
    classic_id = "aerodrome:USDC:WETH:volatile"

    def _by_id(pid):
        if pid == slip_id:
            return SimpleNamespace(
                dex="aerodrome_slipstream", address=_POOL, tick_spacing=100,
                stable=None)
        if pid == classic_id:
            return SimpleNamespace(
                dex="aerodrome", address="0x" + "ef" * 20, tick_spacing=None,
                stable=False)
        return None

    monkeypatch.setattr(
        "arbicore.discovery.base_pool_registry.canonical_pool_by_id", _by_id)

    slip = _run(_plan_generic_evm(
        "base", _meta("base", "aerodrome_slipstream", fee=None, pool=slip_id),
        None))
    assert slip is not None
    assert slip[0][0].dex == "aerodrome_slipstream"
    assert slip[0][0].tick_spacing == 100
    assert slip[0][0].pool_address == _POOL

    classic = _run(_plan_generic_evm(
        "base", _meta("base", "aerodrome", fee=None, pool=classic_id), None))
    assert classic is not None
    assert classic[0][0].stable is False
    assert classic[0][0].pool_address == "0x" + "ef" * 20

    unresolved = SimpleNamespace(
        dex="aerodrome", address=None, tick_spacing=None, stable=False)
    monkeypatch.setattr(
        "arbicore.discovery.base_pool_registry.canonical_pool_by_id",
        lambda _pid: unresolved)
    assert _run(_plan_generic_evm(
        "base", _meta("base", "aerodrome", fee=None, pool=classic_id),
        None)) is None


def test_planned_hop_reaches_the_quoter(monkeypatch):
    _patch_algebra(monkeypatch, {"pool_address": _POOL}, [])

    class _Reg:
        def __init__(self):
            self.hops = None

        async def quote_route(self, *, chain, hops):
            self.hops = hops
            hop = SimpleNamespace(
                dex=hops[0]["dex"], status="ok", block_number=1,
                amount_in_wei=hops[0]["amount_in_wei"], amount_out_wei=10 ** 16,
                token_in=hops[0]["token_in"], token_out=hops[0]["token_out"])
            back = SimpleNamespace(
                dex=hops[1]["dex"], status="ok", block_number=1,
                amount_in_wei=10 ** 16, amount_out_wei=10 ** 16,
                token_in=hops[1]["token_in"], token_out=hops[1]["token_out"])
            return SimpleNamespace(
                status="ok", hops=[hop, back], final_amount_out_wei=10 ** 16,
                aggregate_gas_estimate_units=1)

    reg = _Reg()
    prov = make_live_quote_provider(
        reg, eth_call_for_chain=lambda _c: _eth)
    facts = _run(prov(_meta("arbitrum", "camelot_v3", fee=None), 10_000.0))
    assert facts is not None
    assert reg.hops[0]["dex"] == "camelot_v3"
    assert "fee" not in reg.hops[0]


def test_capability_map_matches_registered_quoters():
    def _pool(dex, chain):
        return PoolNode("x", dex, chain, "WETH", "USDC", 0.0, 30)

    assert hop_quote_capable("ethereum", _pool("sushiswap_v2", "ethereum"))
    assert not hop_quote_capable("arbitrum", _pool("sushiswap_v2", "arbitrum"))
    assert hop_quote_capable("arbitrum", _pool("sushiswap_v3", "arbitrum"))
    assert hop_quote_capable("arbitrum", _pool("camelot_v3", "arbitrum"))
    assert hop_quote_capable("polygon", _pool("quickswap_v3", "polygon"))
    assert hop_quote_capable("bnb", _pool("pancakeswap_v3", "bnb"))
    assert hop_quote_capable("base", _pool("aerodrome", "base"))
    assert hop_quote_capable("base", _pool("aerodrome_slipstream", "base"))
    assert not hop_quote_capable("ethereum", _pool("aerodrome", "ethereum"))
    assert not hop_quote_capable("ethereum", _pool("curve_stable", "ethereum"))
    assert not hop_quote_capable("optimism", _pool("velodrome_v2", "optimism"))
    assert hop_quote_capable("ethereum", _pool("uniswap_v3", "ethereum"))
    assert hop_quote_capable("bnb", _pool("uniswap_v3", "bnb"))
