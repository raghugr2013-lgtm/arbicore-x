"""T1 independent adversarial verification of the P0-3 bounded-concurrency
Base UniV3 liquidity() eligibility refresh.

Written by the testing agent (NOT part of the certified 13-module validator
scope) to verify the developer's claims independently, plus probe edge cases
the shipped regression module does not cover:
  * peak in-flight actually reaches the cap (8) — genuine parallelism
  * max_concurrency<=0 degrades to sequential and stays correct
  * all-zero liquidity excludes everything (no fail-open)
  * stale exclusions are cleared on a later healthy refresh
  * boundary liquidity values (1, uint128 max) are eligible
  * pools with an unresolved/missing canonical address fail closed
  * HARDENED: an exception escaping the refresh (e.g. registry lookup raising,
    or a CancelledError) leaves the fail-closed baseline in force (all
    unverified UniV3 pools excluded)
  * HARDENED: a per-call timeout bounds each read — a stalled eth_call is
    classified EXCLUDED and can never consume the scanner startup budget
"""
from __future__ import annotations

import asyncio
import os
import time

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_t1_verify")

import pytest

from arbicore.discovery import base_pool_registry as reg
from arbicore.runtime import composition

CBETH_500_ID = "uniswap_v3:USDC:cbETH:500"
CBETH_500_ADDR = "0xFdebEDc97D56EDd31AbdcB887570546B257964f2"
LIQ_SEL = "0x1a686502"
U128_MAX = (1 << 128) - 1


@pytest.fixture(autouse=True)
def _pristine():
    def _install(pools):
        reg._POOLS[:] = pools
        reg._BY_ID.clear()
        reg._BY_ID.update({p.canonical_id: p for p in pools})
        reg._BY_ADDRESS.clear()
        reg._BY_ADDRESS.update({p.address.lower(): p for p in pools if p.address})
    saved = list(reg._POOLS)
    _install(reg.build_canonical_pools())
    composition._BASE_V3_INELIGIBLE.clear()
    yield
    composition._BASE_V3_INELIGIBLE.clear()
    _install(saved)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _enc(n: int) -> str:
    return "0x" + ("%x" % int(n)).rjust(64, "0")


def _probe(delay=0.02, value=987_654_321, zero_addrs=()):
    st = {"in": 0, "peak": 0, "calls": 0}
    zero = {a.lower() for a in zero_addrs}

    async def eth_call(to, data):
        assert data == LIQ_SEL
        st["calls"] += 1
        st["in"] += 1
        st["peak"] = max(st["peak"], st["in"])
        try:
            await asyncio.sleep(delay)
        finally:
            st["in"] -= 1
        return _enc(0 if (to or "").lower() in zero else value)

    return eth_call, st


def _univ3_ids():
    return {n.pool_address
            for n in reg.build_canonical_pool_graph(resolved_only=True)[0]
            if n.dex_protocol == "uniswap_v3"}


# ── parallelism actually reaches the cap ─────────────────────────────────────
def test_peak_inflight_reaches_default_cap_of_8():
    eth_call, st = _probe(delay=0.05)
    res = _run(composition._refresh_base_v3_eligibility(eth_call))
    assert res == {"checked": 19, "eligible": 19, "excluded": 0}
    assert st["calls"] == 19
    assert st["peak"] == 8, f"expected saturation at cap 8, saw {st['peak']}"


def test_wall_clock_matches_three_waves_not_sequential():
    delay = 0.05
    eth_call, _ = _probe(delay=delay)
    t0 = time.perf_counter()
    _run(composition._refresh_base_v3_eligibility(eth_call))
    elapsed = time.perf_counter() - t0
    # 19 pools / cap 8 => 3 waves
    assert 3 * delay <= elapsed < 6 * delay, elapsed
    assert elapsed < 19 * delay * 0.5


@pytest.mark.parametrize("cap", [0, -5])
def test_non_positive_max_concurrency_degrades_to_sequential(cap):
    eth_call, st = _probe(delay=0.001)
    res = _run(composition._refresh_base_v3_eligibility(eth_call,
                                                        max_concurrency=cap))
    assert res == {"checked": 19, "eligible": 19, "excluded": 0}
    assert st["peak"] == 1


def test_cap_one_is_strictly_sequential_and_correct():
    eth_call, st = _probe(delay=0.001, zero_addrs=[CBETH_500_ADDR])
    res = _run(composition._refresh_base_v3_eligibility(eth_call,
                                                        max_concurrency=1))
    assert res == {"checked": 19, "eligible": 18, "excluded": 1}
    assert st["peak"] == 1
    assert composition._BASE_V3_INELIGIBLE == {CBETH_500_ID}


def test_cap_larger_than_pool_count_is_bounded_by_work():
    eth_call, st = _probe(delay=0.01)
    res = _run(composition._refresh_base_v3_eligibility(eth_call,
                                                        max_concurrency=100))
    assert res["eligible"] == 19
    assert st["peak"] == 19


# ── classification correctness / no fail-open ───────────────────────────────
def test_all_zero_liquidity_excludes_every_univ3_pool():
    async def eth_call(to, data):
        return _enc(0)
    res = _run(composition._refresh_base_v3_eligibility(eth_call))
    assert res == {"checked": 19, "eligible": 0, "excluded": 19}
    assert composition._BASE_V3_INELIGIBLE == _univ3_ids()


@pytest.mark.parametrize("value", [1, 2, U128_MAX])
def test_boundary_positive_liquidity_is_eligible(value):
    async def eth_call(to, data):
        return _enc(value)
    res = _run(composition._refresh_base_v3_eligibility(eth_call))
    assert res == {"checked": 19, "eligible": 19, "excluded": 0}


def test_absent_provider_excludes_all_and_empties_universe():
    res = _run(composition._refresh_base_v3_eligibility(None))
    assert res["reason"] == "base_eth_call_unavailable"
    assert res["checked"] == 0 and res["eligible"] == 0
    assert res["excluded"] == 19
    assert composition._BASE_V3_INELIGIBLE == _univ3_ids()
    pools = [n for n in reg.build_canonical_pool_graph(resolved_only=True)[0]
             if n.pool_address not in composition._BASE_V3_INELIGIBLE]
    assert pools == []


def test_recovery_refresh_clears_stale_exclusions():
    # first: everything unreadable -> all excluded
    async def bad(to, data):
        raise RuntimeError("rpc down")
    assert _run(composition._refresh_base_v3_eligibility(bad))["excluded"] == 19
    # then: healthy chain state -> exclusions cleared (re-eligible)
    good, _ = _probe(delay=0)
    res = _run(composition._refresh_base_v3_eligibility(good))
    assert res == {"checked": 19, "eligible": 19, "excluded": 0}
    assert composition._BASE_V3_INELIGIBLE == set()


def test_repeated_refresh_is_idempotent_and_deterministic():
    seen = []
    for _ in range(6):
        eth_call, _ = _probe(delay=0.001, zero_addrs=[CBETH_500_ADDR])
        res = _run(composition._refresh_base_v3_eligibility(eth_call))
        seen.append((tuple(sorted(res.items())),
                     frozenset(composition._BASE_V3_INELIGIBLE)))
    assert len(set(seen)) == 1
    assert seen[0][1] == frozenset({CBETH_500_ID})


def test_missing_canonical_address_is_never_eligible_and_never_read():
    """A canonical pool with no address is dropped from the resolved graph
    entirely (checked=18) and never receives an eth_call -> it can never be
    eligible. Fail-closed by construction."""
    called = []

    async def eth_call(to, data):
        called.append(to)
        return _enc(5)

    target = reg.canonical_pool_by_id(CBETH_500_ID)
    try:
        setattr(target, "address", "")
    except Exception:
        object.__setattr__(target, "address", "")
    res = _run(composition._refresh_base_v3_eligibility(eth_call))
    assert res == {"checked": 18, "eligible": 18, "excluded": 0}
    assert CBETH_500_ADDR.lower() not in [(c or "").lower() for c in called]
    universe = {n.pool_address
                for n in reg.build_canonical_pool_graph(resolved_only=True)[0]
                if n.pool_address not in composition._BASE_V3_INELIGIBLE}
    assert CBETH_500_ID not in universe


def test_aerodrome_pools_never_receive_a_liquidity_call():
    from eth_utils import to_checksum_address
    target = next(p.canonical_id for p in reg.get_canonical_pools()
                  if p.dex == "aerodrome_slipstream"
                  and p.address_resolution == reg.RUNTIME_GETPOOL)
    aero = to_checksum_address("0x" + "cd" * 20)
    assert reg.set_runtime_resolved_address(
        target, aero, provenance={"method": "getPool_by_tickspacing"})
    seen = []

    async def eth_call(to, data):
        seen.append((to or "").lower())
        return _enc(42)

    res = _run(composition._refresh_base_v3_eligibility(eth_call))
    assert res == {"checked": 19, "eligible": 19, "excluded": 0}
    assert aero.lower() not in seen
    assert len(seen) == 19
    assert target not in composition._BASE_V3_INELIGIBLE


# ── HARDENED behavior (previously fail-open hazards; now fail-closed) ───────
def test_exception_escaping_refresh_stays_failclosed():
    """If anything outside the per-pool try/except raises (here: the registry
    lookup), the exception escapes _refresh_base_v3_eligibility — but the
    fail-closed baseline, pre-seeded before any await, keeps every unverified
    UniV3 pool EXCLUDED from the runtime universe (never admitted)."""
    orig = reg.canonical_pool_by_id

    def boom(pool_id):
        raise RuntimeError("registry lookup blew up")

    reg.canonical_pool_by_id = boom
    try:
        async def eth_call(to, data):
            return _enc(7)
        with pytest.raises(RuntimeError):
            _run(composition._refresh_base_v3_eligibility(
                eth_call, per_call_timeout_s=None))
    finally:
        reg.canonical_pool_by_id = orig

    # fail-closed baseline held => nothing survives into the universe
    assert composition._BASE_V3_INELIGIBLE == _univ3_ids()
    surviving = {n.pool_address
                 for n in reg.build_canonical_pool_graph(resolved_only=True)[0]
                 if n.pool_address not in composition._BASE_V3_INELIGIBLE}
    assert surviving == set()


def test_per_call_timeout_bounds_refresh_and_fails_closed():
    """A hanging eth_call no longer stalls startup: each read is bounded by
    per_call_timeout_s and a timed-out pool is EXCLUDED (fail-closed). Even
    with every read hanging, the refresh completes quickly and admits nothing
    — the ~8s scanner startup budget can never be consumed by a hung RPC."""
    async def hanging(to, data):
        await asyncio.sleep(60)
        return _enc(1)

    t0 = time.perf_counter()
    res = _run(composition._refresh_base_v3_eligibility(
        hanging, per_call_timeout_s=0.05, max_concurrency=8))
    elapsed = time.perf_counter() - t0

    assert res == {"checked": 19, "eligible": 0, "excluded": 19}
    assert composition._BASE_V3_INELIGIBLE == _univ3_ids()
    assert elapsed < 1.0                     # ~3 waves * 0.05s, not 60s
