"""Opportunity engine — parallel fail-closed discovery + capability matrix.

Deterministic + offline (injected eth_call). Verifies: parallel discovery is
non-blocking (one failed chain doesn't stop others), per-task timeout fails
closed, real pools resolve, and the matrix reports distinct states with explicit
blockers and NEVER marks anything limited-live eligible from code/config alone.
No fabrication, no signing/broadcast.
"""
from __future__ import annotations

import asyncio

from eth_abi import encode as _enc
from eth_utils import to_checksum_address

from arbicore.chains.registries import tokens_for
from arbicore.discovery import opportunity_engine as E
from arbicore.discovery import univ3_pool_resolver as R

CHAIN = "arbitrum"
_t = tokens_for(CHAIN)
WETH, USDC = _t["WETH"]["address"], _t["USDC"]["address"]
POOL = to_checksum_address("0x" + "b2" * 20)
FACTORY = R.univ3_factory_for(CHAIN)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _healthy_eth_call(pool=POOL, t0=WETH, t1=USDC, fee=500, liq=10**18):
    async def eth_call(to, data):
        sel = data[:10]
        if to.lower() == FACTORY.lower():
            return "0x" + _enc(["address"], [to_checksum_address(pool)]).hex()
        if sel == R._SEL_TOKEN0:
            return "0x" + _enc(["address"], [to_checksum_address(t0)]).hex()
        if sel == R._SEL_TOKEN1:
            return "0x" + _enc(["address"], [to_checksum_address(t1)]).hex()
        if sel == R._SEL_FEE:
            return "0x" + _enc(["uint24"], [int(fee)]).hex()
        if sel == R._SEL_LIQUIDITY:
            return "0x" + _enc(["uint128"], [int(liq)]).hex()
        raise AssertionError(sel)
    return eth_call


def test_enumerate_capabilities_is_wide_not_base_only():
    caps = E.enumerate_capabilities()
    for c in ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"):
        assert c in caps["chains"], c
    assert "uniswap_v3" in caps["venues"]["arbitrum"]
    assert set(caps["strategies"]) == set(E.IMPLEMENTED_STRATEGIES)


def test_parallel_discovery_is_nonblocking_and_fail_closed():
    # arbitrum healthy; ethereum has no RPC (None); polygon RPC raises. One bad
    # chain must NOT stop the others.
    async def raising(to, data):
        raise RuntimeError("rpc_down")

    def eth_call_for_chain(chain):
        return {"arbitrum": _healthy_eth_call(),
                "polygon": raising,
                "ethereum": None}.get(chain)

    tasks = [
        {"chain": "arbitrum", "token_a": WETH, "token_b": USDC, "fee": 500},
        {"chain": "ethereum", "token_a": WETH, "token_b": USDC, "fee": 500},
        {"chain": "polygon", "token_a": WETH, "token_b": USDC, "fee": 500},
    ]
    res = _run(E.discover_pools_parallel(tasks, eth_call_for_chain=eth_call_for_chain))
    by_chain = {r["chain"]: r for r in res}
    assert by_chain["arbitrum"]["resolved"] is True
    assert by_chain["arbitrum"]["pool"]["pool_address"] == POOL
    assert by_chain["ethereum"]["resolved"] is False
    assert by_chain["ethereum"]["reason"] == "chain_rpc_unavailable"
    assert by_chain["polygon"]["resolved"] is False
    # resolver swallows the RPC fault fail-closed => reported as invalid/unreadable
    assert by_chain["polygon"]["reason"] == "pool_invalid_or_unreadable"


def test_per_task_timeout_fails_closed():
    async def hang(to, data):
        await asyncio.sleep(10)

    def eth_call_for_chain(chain):
        return hang

    tasks = [{"chain": "arbitrum", "token_a": WETH, "token_b": USDC, "fee": 500}]
    res = _run(E.discover_pools_parallel(
        tasks, eth_call_for_chain=eth_call_for_chain, per_task_timeout_s=0.05))
    assert res[0]["resolved"] is False
    assert res[0]["pool"] is None


def test_invalid_pool_excluded_but_search_continues():
    # zero-liquidity => invalid => excluded, but returns a row (not an exception).
    def eth_call_for_chain(chain):
        return _healthy_eth_call(liq=0)
    tasks = [{"chain": "arbitrum", "token_a": WETH, "token_b": USDC, "fee": 500}]
    res = _run(E.discover_pools_parallel(tasks, eth_call_for_chain=eth_call_for_chain))
    assert res[0]["resolved"] is False
    assert res[0]["reason"] == "pool_invalid_or_unreadable"


def test_matrix_has_distinct_states_and_no_auto_eligibility():
    m = E.build_opportunity_matrix()
    assert m["summary"]["limited_live_eligible_count"] == 0
    assert m["safety"]["signed"] is False and m["safety"]["broadcast"] is False
    assert m["summary"]["row_count"] > 0
    for r in m["rows"]:
        assert r["limited_live_eligible"] is False
        assert r["blocker"]
        # never infer live dims from implemented/config
        assert r["quote"] == "requires_runtime"
    # arbitrum univ3 is discoverable (factory registered); its blocker in this
    # pod (no RPC) must be the RPC one, not a discovery one.
    arb_uni = next(r for r in m["rows"]
                   if r["chain"] == "arbitrum" and r["venue"] == "uniswap_v3")
    assert arb_uni["discoverable"] is True
    assert arb_uni["blocker"] == "no_operator_configured_rpc"


def test_non_univ3_venue_without_resolver_is_blocked_not_crashing():
    m = E.build_opportunity_matrix()
    # e.g. optimism velodrome_v2 / arbitrum camelot_v3 have adapters but no
    # generic pool-resolution seam in this slice => blocked, not fabricated.
    non_uni = [r for r in m["rows"]
               if r["venue"] not in ("uniswap_v3",) and r["chain"] != "base"]
    assert non_uni  # such rows exist
    assert all(r["limited_live_eligible"] is False for r in non_uni)
