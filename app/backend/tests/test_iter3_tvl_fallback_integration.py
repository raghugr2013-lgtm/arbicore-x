"""iteration_3 (testing agent) — END-TO-END verification that the TVL
reserves_fn registry fallback aligns with runtime-resolved Aerodrome/Slipstream
addresses using the REAL canonical registry (no registry mocking).

Flow under test:
  1. build_pool_meta_for_reserves(pools)  -> snapshot BEFORE resolution
  2. set_runtime_resolved_address(...)    -> runtime address written to registry
  3. reserves_fn(chain, <new checksummed address>) must still return reserves
     (pool_meta MISS -> canonical_pool_by_address fallback)
"""
import pytest

import arbicore.discovery.base_pool_registry as reg
from arbicore.searcher.v3_state import (
    build_pool_meta_for_reserves, make_base_v3_reserves_fn)

# a deterministic non-zero fake address (never used for signing/broadcast)
FAKE_ADDR = "0x1111111111111111111111111111111111111111"


@pytest.fixture
def registry_snapshot():
    """Snapshot/restore the module-global canonical registry."""
    pools = list(reg._POOLS)
    by_id = dict(reg._BY_ID)
    by_addr = dict(reg._BY_ADDRESS)
    yield
    reg._POOLS[:] = pools
    reg._BY_ID.clear()
    reg._BY_ID.update(by_id)
    reg._BY_ADDRESS.clear()
    reg._BY_ADDRESS.update(by_addr)


@pytest.mark.asyncio
async def test_runtime_resolved_pool_gets_tvl_via_registry_fallback(
        registry_snapshot):
    unresolved = reg.unresolved_pools()
    if not unresolved:
        pytest.skip("no unresolved/runtime_getpool pools in registry")
    target = unresolved[0]

    # 1. pool_meta snapshotted BEFORE runtime resolution
    pool_meta = build_pool_meta_for_reserves(reg.get_canonical_pools())
    assert FAKE_ADDR.lower() not in pool_meta

    # 2. runtime resolution writes the address into the ONE registry
    assert reg.set_runtime_resolved_address(
        target.canonical_id, FAKE_ADDR,
        provenance={"method": "test_harness"}) is True
    resolved = reg.canonical_pool_by_id(target.canonical_id)
    assert resolved.address.lower() == FAKE_ADDR.lower()
    assert resolved.address_resolution == reg.RUNTIME_RESOLVED

    calls = []

    async def fake_eth(to, data):
        calls.append((to, data))
        # token0 balance then token1 balance
        dec = (resolved.token0_decimals if to == resolved.token0_address
               else resolved.token1_decimals)
        return hex(3 * 10 ** int(dec))

    rfn = make_base_v3_reserves_fn(fake_eth, pool_meta)

    # 3. checksummed runtime address must resolve through the fallback
    res = await rfn("base", resolved.address)
    assert res is not None, "reserves_fn failed closed on a resolved pool"
    t0, r0, t1, r1 = res
    assert t0 == resolved.token0_symbol
    assert t1 == resolved.token1_symbol
    assert r0 == pytest.approx(3.0)
    assert r1 == pytest.approx(3.0)
    # balanceOf(pool) was called against the pool address, not the token
    assert len(calls) == 2
    assert all(resolved.address.lower().replace("0x", "") in d for _, d in calls)

    # lowercase form must behave identically (case-insensitivity)
    assert await rfn("base", resolved.address.lower()) == res


@pytest.mark.asyncio
async def test_reserves_fn_fail_closed_on_truly_unknown_pool():
    async def fake_eth(to, data):  # pragma: no cover - must not be reached
        raise AssertionError("eth_call must not run for an unknown pool")

    rfn = make_base_v3_reserves_fn(fake_eth, {})
    assert await rfn("base", "0xdeadbeef00000000000000000000000000000000") is None
    assert await rfn("base", "") is None
    assert await rfn("base", None) is None


@pytest.mark.asyncio
async def test_reserves_fn_fail_closed_on_zero_or_bad_balance(
        registry_snapshot):
    unresolved = reg.unresolved_pools()
    if not unresolved:
        pytest.skip("no unresolved pools")
    target = unresolved[0]
    reg.set_runtime_resolved_address(
        target.canonical_id, FAKE_ADDR, provenance={"method": "t"})

    async def zero_eth(to, data):
        return "0x" + "0" * 64

    async def bad_eth(to, data):
        return "not-hex"

    async def empty_eth(to, data):
        return None

    for fn in (zero_eth, bad_eth, empty_eth):
        rfn = make_base_v3_reserves_fn(fn, {})
        assert await rfn("base", FAKE_ADDR) is None, f"{fn.__name__} not closed"
