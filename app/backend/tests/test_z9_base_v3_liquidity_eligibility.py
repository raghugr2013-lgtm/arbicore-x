"""P0-3 regression — runtime Base UniV3 liquidity() eligibility filter.

Companion to ``test_z8_canonical_scanner_loader_integration.py``. Proves the
runtime-only eligibility mechanism in ``arbicore.runtime.composition``
(``_refresh_base_v3_eligibility`` + ``_BASE_V3_INELIGIBLE`` + the Base branch of
the canonical route loader) behaves exactly as specified, WITHOUT mutating the
pure/deterministic canonical pool registry and WITHOUT signing/broadcasting:

  A. ZERO-LIQUIDITY EXCLUSION — a canonical resolved Base UniV3 pool whose real
     ``liquidity()`` is 0 is excluded from the runtime scanner universe.
  B. POSITIVE-LIQUIDITY ELIGIBILITY — a canonical resolved Base UniV3 pool with
     positive ``liquidity()`` stays eligible / in the universe.
  C. CANONICAL REGISTRY PRESERVATION — runtime filtering never deletes, mutates
     or removes the pool from the canonical registry; identity stays intact.
  D. FAIL-CLOSED READ FAILURE — missing / empty / malformed / unreadable
     ``liquidity()`` (and a missing eth_call provider) cause runtime exclusion
     rather than eligibility.

  E. AERODROME/SLIPSTREAM EXEMPTION — the UniV3 ``liquidity()`` rule is never
     applied to Aerodrome/Slipstream pools (their liquidity state is not
     represented by the UniV3 ``liquidity()`` selector).

The concrete zero-liquidity subject mirrors the real VPS finding: the Base
UniV3 USDC/cbETH 500ppm pool ``0xFdebEDc97D56EDd31AbdcB887570546B257964f2``
(canonical id ``uniswap_v3:USDC:cbETH:500``) currently reports liquidity()==0.

Deterministic + offline: a mocked eth_call replaces all RPC. No network, no
signing, no broadcast, no Mongo access (the eligibility helper only reads the
canonical registry).
"""
from __future__ import annotations

import asyncio
import os

# composition -> services.db reads MONGO_URL/DB_NAME at import; provide safe
# local defaults for the test process. The eligibility helper under test never
# touches Mongo (it only reads the canonical registry), so no live DB is used.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_test")

import pytest
from eth_utils import to_checksum_address

from arbicore.discovery import base_pool_registry as reg
from arbicore.runtime import composition


# The exact real VPS finding: Base UniV3 USDC/cbETH 500ppm pool at zero liq.
CBETH_500_ID = "uniswap_v3:USDC:cbETH:500"
CBETH_500_ADDR = "0xFdebEDc97D56EDd31AbdcB887570546B257964f2"

LIQUIDITY_SELECTOR = "0x1a686502"     # UniV3 pool.liquidity()
_POSITIVE_LIQUIDITY = 987_654_321


# ── isolation: pristine canonical registry per test (mirrors z8), plus a clean
#    process-global runtime eligibility snapshot before AND after each test so
#    this module neither depends on nor leaks the shared _BASE_V3_INELIGIBLE. ──
@pytest.fixture(autouse=True)
def _pristine_registry():
    def _install(pools):
        reg._POOLS[:] = pools
        reg._BY_ID.clear()
        reg._BY_ID.update({p.canonical_id: p for p in pools})
        reg._BY_ADDRESS.clear()
        reg._BY_ADDRESS.update({p.address.lower(): p for p in pools if p.address})
    saved = list(reg._POOLS)
    _install(reg.build_canonical_pools())   # deterministic offline baseline
    yield
    _install(saved)


@pytest.fixture(autouse=True)
def _clean_eligibility():
    composition._BASE_V3_INELIGIBLE.clear()
    yield
    composition._BASE_V3_INELIGIBLE.clear()


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _enc_u128(n: int) -> str:
    return "0x" + ("%x" % int(n)).rjust(64, "0")


def _mk_eth_call(*, zero_addrs=(), raise_addrs=(), raw_overrides=None,
                 default=_POSITIVE_LIQUIDITY):
    """Deterministic eth_call double for the UniV3 liquidity() selector.

    Keyed on the pool's real on-chain address (the ``to`` argument the helper
    passes). ``zero_addrs`` return an ABI-encoded 0, ``raise_addrs`` raise (RPC
    unreadable), ``raw_overrides`` return an exact raw string (None/""/malformed
    for the fail-closed cases); everything else returns positive liquidity.
    """
    zero = {a.lower() for a in zero_addrs}
    raising = {a.lower() for a in raise_addrs}
    overrides = {k.lower(): v for k, v in (raw_overrides or {}).items()}

    async def eth_call(to, data):
        assert data == LIQUIDITY_SELECTOR, data      # only liquidity() is read
        key = (to or "").lower()
        if key in raising:
            raise RuntimeError("rpc_unreadable")
        if key in overrides:
            return overrides[key]
        if key in zero:
            return _enc_u128(0)
        return _enc_u128(default)

    return eth_call


def _runtime_base_universe():
    """The ACTUAL Base route universe the synchronous loader exposes: the
    canonical resolved graph minus the runtime UniV3 deny-list. Mirrors the
    Base branch of ``composition.get_flash_loan_arb_scanner``'s
    ``_multichain_pool_loader`` (drift is guarded by
    ``test_loader_source_applies_runtime_ineligible_filter``)."""
    pools = reg.build_canonical_pool_graph(resolved_only=True)[0]
    if composition._BASE_V3_INELIGIBLE:
        pools = [n for n in pools
                 if n.pool_address not in composition._BASE_V3_INELIGIBLE]
    return {n.pool_address for n in pools}


# ── A. zero-liquidity exclusion ─────────────────────────────────────────────
def test_zero_liquidity_univ3_pool_excluded_from_runtime_universe():
    # Sanity: subject is a canonical resolved UniV3 pool in the offline universe.
    assert CBETH_500_ID in _runtime_base_universe()
    cp = reg.canonical_pool_by_id(CBETH_500_ID)
    assert cp is not None and cp.address == CBETH_500_ADDR
    assert cp.dex == "uniswap_v3"

    eth_call = _mk_eth_call(zero_addrs=[CBETH_500_ADDR])
    res = _run(composition._refresh_base_v3_eligibility(eth_call))

    assert res == {"checked": 19, "eligible": 18, "excluded": 1}
    assert CBETH_500_ID in composition._BASE_V3_INELIGIBLE
    universe = _runtime_base_universe()
    assert CBETH_500_ID not in universe          # excluded from live universe
    assert len(universe) == 18


# ── B. positive-liquidity eligibility ───────────────────────────────────────
def test_positive_liquidity_univ3_pool_remains_eligible():
    eth_call = _mk_eth_call()                     # every UniV3 pool positive
    res = _run(composition._refresh_base_v3_eligibility(eth_call))

    assert res == {"checked": 19, "eligible": 19, "excluded": 0}
    assert composition._BASE_V3_INELIGIBLE == set()
    universe = _runtime_base_universe()
    assert CBETH_500_ID in universe               # stays eligible
    assert len(universe) == 19


# ── C. canonical registry preservation ──────────────────────────────────────
def test_runtime_filtering_does_not_mutate_canonical_registry():
    before = reg.canonical_pool_by_id(CBETH_500_ID)
    before_total = len(reg.get_canonical_pools())
    before_full = {n.pool_address
                   for n in reg.build_canonical_pool_graph(resolved_only=False)[0]}

    # Exclude the subject at runtime (zero liquidity).
    eth_call = _mk_eth_call(zero_addrs=[CBETH_500_ADDR])
    _run(composition._refresh_base_v3_eligibility(eth_call))
    assert CBETH_500_ID in composition._BASE_V3_INELIGIBLE   # runtime-ineligible

    # ...yet the canonical pool identity is untouched: not deleted, not mutated.
    after = reg.canonical_pool_by_id(CBETH_500_ID)
    assert after is not None
    assert after.address == before.address == CBETH_500_ADDR
    assert after.address_resolution == before.address_resolution == \
        reg.DETERMINISTIC_VERIFIED
    assert after.canonical_id == before.canonical_id == CBETH_500_ID
    assert len(reg.get_canonical_pools()) == before_total == 30

    # The full canonical graph is unchanged — a runtime-ineligible pool is still
    # a first-class canonical pool that can become eligible again later.
    after_full = {n.pool_address
                  for n in reg.build_canonical_pool_graph(resolved_only=False)[0]}
    assert after_full == before_full
    assert CBETH_500_ID in after_full


# ── D. fail-closed on missing / malformed / unreadable liquidity ────────────
@pytest.mark.parametrize(
    "bad_response",
    [
        None,                       # RPC returned nothing
        "",                         # empty string
        "0x",                       # empty payload
        "0xdeadbeef",               # too short to decode a uint128
        "0x" + "zz" * 32,           # non-hex / malformed
    ],
    ids=["none", "empty", "empty_payload", "too_short", "non_hex"],
)
def test_unreadable_liquidity_fails_closed(bad_response):
    eth_call = _mk_eth_call(raw_overrides={CBETH_500_ADDR: bad_response})
    res = _run(composition._refresh_base_v3_eligibility(eth_call))

    assert res == {"checked": 19, "eligible": 18, "excluded": 1}
    assert CBETH_500_ID in composition._BASE_V3_INELIGIBLE
    assert CBETH_500_ID not in _runtime_base_universe()


def test_exception_during_liquidity_read_fails_closed():
    eth_call = _mk_eth_call(raise_addrs=[CBETH_500_ADDR])
    res = _run(composition._refresh_base_v3_eligibility(eth_call))

    assert res == {"checked": 19, "eligible": 18, "excluded": 1}
    assert CBETH_500_ID in composition._BASE_V3_INELIGIBLE
    assert CBETH_500_ID not in _runtime_base_universe()


def test_missing_eth_call_provider_fails_closed_for_all_univ3():
    res = _run(composition._refresh_base_v3_eligibility(None))

    assert res["reason"] == "base_eth_call_unavailable"
    assert res["checked"] == 0 and res["eligible"] == 0

    univ3_ids = {n.pool_address
                 for n in reg.build_canonical_pool_graph(resolved_only=True)[0]
                 if n.dex_protocol == "uniswap_v3"}
    assert univ3_ids == composition._BASE_V3_INELIGIBLE
    assert res["excluded"] == len(univ3_ids) == 19
    assert _runtime_base_universe() == set()      # nothing trusted ⇒ empty


# ── E. Aerodrome/Slipstream are NOT subjected to the UniV3 liquidity() rule ──
def test_aerodrome_slipstream_not_subjected_to_univ3_liquidity_rule():
    # Resolve one Slipstream pool on-chain so it enters the resolved universe.
    target = next(p.canonical_id for p in reg.get_canonical_pools()
                  if p.dex == "aerodrome_slipstream"
                  and p.address_resolution == reg.RUNTIME_GETPOOL)
    aero_addr = to_checksum_address("0x" + "ab" * 20)
    assert reg.set_runtime_resolved_address(
        target, aero_addr, provenance={"method": "getPool_by_tickspacing"})
    assert target in _runtime_base_universe()

    # eth_call RAISES for the Aerodrome address: if the UniV3 liquidity() rule
    # were (incorrectly) applied to it, the read would fail and it would be
    # excluded. It must instead be skipped entirely.
    eth_call = _mk_eth_call(raise_addrs=[aero_addr])
    res = _run(composition._refresh_base_v3_eligibility(eth_call))

    assert res == {"checked": 19, "eligible": 19, "excluded": 0}  # only UniV3
    assert target not in composition._BASE_V3_INELIGIBLE
    assert target in _runtime_base_universe()     # stays eligible


# ── P0-3 startup-budget remediation: bounded-concurrency liquidity reads ────
def _mk_concurrency_probe(*, delay=0.02, zero_addrs=(),
                          default=_POSITIVE_LIQUIDITY):
    """eth_call double that records peak in-flight concurrency and adds a small
    per-call latency (to simulate real Base RPC round-trips)."""
    state = {"in_flight": 0, "peak": 0, "calls": 0}
    zero = {a.lower() for a in zero_addrs}

    async def eth_call(to, data):
        assert data == LIQUIDITY_SELECTOR, data
        state["calls"] += 1
        state["in_flight"] += 1
        state["peak"] = max(state["peak"], state["in_flight"])
        try:
            await asyncio.sleep(delay)
        finally:
            state["in_flight"] -= 1
        if (to or "").lower() in zero:
            return _enc_u128(0)
        return _enc_u128(default)

    return eth_call, state


def test_liquidity_reads_run_under_bounded_concurrency():
    eth_call, state = _mk_concurrency_probe(delay=0.02)
    res = _run(composition._refresh_base_v3_eligibility(eth_call))
    assert res == {"checked": 19, "eligible": 19, "excluded": 0}
    assert state["calls"] == 19
    # genuinely concurrent (peak > 1) yet bounded to the default limit (8).
    assert 2 <= state["peak"] <= 8


def test_bounded_concurrency_respects_max_concurrency_argument():
    eth_call, state = _mk_concurrency_probe(delay=0.02)
    res = _run(
        composition._refresh_base_v3_eligibility(eth_call, max_concurrency=3))
    assert res["checked"] == 19 and res["eligible"] == 19
    assert 2 <= state["peak"] <= 3          # never more than the requested cap


def test_concurrency_reduces_wall_clock_vs_sequential():
    import time as _t
    delay = 0.02
    eth_call, _ = _mk_concurrency_probe(delay=delay)
    t0 = _t.perf_counter()
    _run(composition._refresh_base_v3_eligibility(eth_call, max_concurrency=8))
    elapsed = _t.perf_counter() - t0
    # 19 strictly-sequential reads would take >= 19*delay; bounded concurrency
    # (8 in-flight) completes in ~3 waves — comfortably sub-sequential. This is
    # the guard that the fix actually relieves the scanner startup budget.
    assert elapsed < (19 * delay) * 0.6


def test_mixed_liquidity_under_concurrency_is_deterministic():
    # One zero-liquidity pool amongst positives, run repeatedly to catch any
    # aggregation race: the exclusion set must be exactly {cbETH 500}.
    for _ in range(5):
        composition._BASE_V3_INELIGIBLE.clear()
        eth_call, _ = _mk_concurrency_probe(
            delay=0.001, zero_addrs=[CBETH_500_ADDR])
        res = _run(composition._refresh_base_v3_eligibility(eth_call))
        assert res == {"checked": 19, "eligible": 18, "excluded": 1}
        assert composition._BASE_V3_INELIGIBLE == {CBETH_500_ID}


# ── P0-3 hardening: fail-closed baseline + per-call timeout (budget guard) ──
def _all_resolved_univ3_ids():
    return {n.pool_address
            for n in reg.build_canonical_pool_graph(resolved_only=True)[0]
            if n.dex_protocol == "uniswap_v3"}


def test_failclosed_helper_excludes_all_resolved_univ3():
    composition._BASE_V3_INELIGIBLE.clear()
    n = composition._failclosed_exclude_all_base_univ3()
    assert n == 19
    assert composition._BASE_V3_INELIGIBLE == _all_resolved_univ3_ids()
    assert _runtime_base_universe() == set()          # nothing admitted


def test_escaping_cancellation_leaves_denylist_failclosed():
    # A BaseException (e.g. a startup-deadline CancelledError) escapes the
    # gather. The pre-seeded fail-closed baseline must remain in force: no
    # unverified pool may be admitted merely because the read did not complete.
    async def eth_call(to, data):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        _run(composition._refresh_base_v3_eligibility(
            eth_call, per_call_timeout_s=None))

    assert composition._BASE_V3_INELIGIBLE == _all_resolved_univ3_ids()
    assert _runtime_base_universe() == set()


def test_stalled_rpc_times_out_and_is_excluded_failclosed():
    # The subject pool's RPC hangs; the per-call timeout classifies it EXCLUDED
    # (fail-closed) rather than waiting — the rest resolve positive.
    async def eth_call(to, data):
        assert data == LIQUIDITY_SELECTOR
        if (to or "").lower() == CBETH_500_ADDR.lower():
            await asyncio.sleep(5)                     # would hang forever
        return _enc_u128(_POSITIVE_LIQUIDITY)

    res = _run(composition._refresh_base_v3_eligibility(
        eth_call, per_call_timeout_s=0.05))
    assert res == {"checked": 19, "eligible": 18, "excluded": 1}
    assert CBETH_500_ID in composition._BASE_V3_INELIGIBLE
    assert CBETH_500_ID not in _runtime_base_universe()


def test_all_rpcs_stalled_refresh_completes_within_budget_failclosed():
    # Even if EVERY Base RPC stalls, the refresh must finish quickly (per-call
    # timeout + bounded concurrency) and exclude every unverified pool — the
    # startup budget can never be consumed by a hung RPC, and nothing is
    # admitted without a positive read.
    import time as _t

    async def eth_call(to, data):
        await asyncio.sleep(10)                        # every read stalls

    t0 = _t.perf_counter()
    res = _run(composition._refresh_base_v3_eligibility(
        eth_call, per_call_timeout_s=0.05, max_concurrency=8))
    elapsed = _t.perf_counter() - t0

    assert res == {"checked": 19, "eligible": 0, "excluded": 19}
    assert composition._BASE_V3_INELIGIBLE == _all_resolved_univ3_ids()
    assert _runtime_base_universe() == set()
    assert elapsed < 1.0                               # ~3 waves * 0.05s


# ── loader wiring: the Base branch actually applies the runtime deny-list ────
def test_loader_source_applies_runtime_ineligible_filter():
    """Source-level guard (mirrors z8's composition source assertions) so the
    functional universe checks above can't silently drift from the real loader.
    """
    import os.path as _p
    path = _p.join(_p.dirname(reg.__file__), "..", "runtime", "composition.py")
    with open(_p.normpath(path)) as f:
        src = f.read()
    assert "_BASE_V3_INELIGIBLE" in src
    assert "n.pool_address not in _BASE_V3_INELIGIBLE" in src
    assert "_refresh_base_v3_eligibility" in src
