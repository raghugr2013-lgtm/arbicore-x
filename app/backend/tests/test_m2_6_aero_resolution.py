"""M2.6 — Aerodrome / Slipstream on-chain pool resolution (offline, fail-closed).

Deterministic doubles (no RPC): a FakeChain answers factory getPool + pool
token0/token1/tickSpacing/stable so we can prove resolution and every
fail-closed branch, plus the integration invariant:
  unresolved pool → Gate 8 FAIL; resolved + valid liquidity → Gate 8 evaluates.
"""
from __future__ import annotations

import asyncio

from arbicore.discovery import base_pool_registry as reg
from arbicore.searcher import aero_resolver as ar
from arbicore.searcher.aero_resolver import (
    AerodromePoolResolver, build_base_aero_resolver_from_env,
    SEL_GETPOOL_BOOL, SEL_GETPOOL_INT24, SEL_TOKEN0, SEL_TOKEN1,
    SEL_TICK_SPACING, SEL_STABLE, DEFAULT_AERO_CL_FACTORY,
    DEFAULT_AERO_POOL_FACTORY,
)
from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    _resolve_pool_tvls, _route_min_tvl,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate8LiquidityDepth,
)

POOL = "0xAb1234000000000000000000000000000000CdEf"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _word_addr(a):
    return "0x" + a.lower().replace("0x", "").rjust(64, "0")


def _word_uint(n):
    return "0x" + ("%x" % int(n)).rjust(64, "0")


def _slipstream_pool():
    for p in reg.get_canonical_pools():
        if p.dex == "aerodrome_slipstream":
            return p
    raise AssertionError("no slipstream pool in registry")


def _classic_pool():
    for p in reg.get_canonical_pools():
        if p.dex == "aerodrome":
            return p
    raise AssertionError("no classic aerodrome pool in registry")


class FakeChain:
    """Configurable on-chain double. Any field left None triggers a fail-closed
    branch (returns None / zero) or a mismatch."""

    def __init__(self, pool, *, factory_returns=POOL, token0=None, token1=None,
                 tick_spacing=None, stable=None, raise_on=None,
                 tick_read_none=False):
        self.pool = pool
        self.factory_returns = factory_returns
        self.token0 = token0 if token0 is not None else pool.token0_address
        self.token1 = token1 if token1 is not None else pool.token1_address
        self.tick_spacing = (tick_spacing if tick_spacing is not None
                             else pool.tick_spacing)
        self.tick_read_none = tick_read_none
        self.stable = stable if stable is not None else bool(pool.stable)
        self.raise_on = raise_on or set()

    async def eth_call(self, to, data):
        sel = data[:10]
        if sel in self.raise_on:
            raise RuntimeError("rpc down")
        if sel in (SEL_GETPOOL_BOOL, SEL_GETPOOL_INT24):
            if self.factory_returns is None:
                return None
            if self.factory_returns == "zero":
                return _word_uint(0)
            return _word_addr(self.factory_returns)
        if sel == SEL_TOKEN0:
            return _word_addr(self.token0)
        if sel == SEL_TOKEN1:
            return _word_addr(self.token1)
        if sel == SEL_TICK_SPACING:
            return None if self.tick_read_none else _word_uint(self.tick_spacing)
        if sel == SEL_STABLE:
            return _word_uint(1 if self.stable else 0)
        return None


def _resolver(fake, **kw):
    return AerodromePoolResolver(fake.eth_call, **kw)


# ── happy paths ──────────────────────────────────────────────────────────────
def test_valid_slipstream_resolution():
    p = _slipstream_pool()
    r = _run(_resolver(FakeChain(p)).resolve(p))
    assert r is not None
    assert r.address.lower() == POOL.lower()
    assert r.provenance["method"] == "cl_getPool(address,address,int24)"
    assert r.provenance["type_check"]["tick_spacing"] == p.tick_spacing
    assert r.provenance["validated"]["token_pair"] is True


def test_valid_classic_resolution():
    p = _classic_pool()
    r = _run(_resolver(FakeChain(p)).resolve(p))
    assert r is not None
    assert r.address.lower() == POOL.lower()
    assert r.provenance["method"] == "getPool(address,address,bool)"
    assert r.provenance["type_check"]["stable"] == bool(p.stable)


# ── fail-closed branches ─────────────────────────────────────────────────────
def test_zero_address_fails_closed():
    p = _slipstream_pool()
    assert _run(_resolver(FakeChain(p, factory_returns="zero")).resolve(p)) is None


def test_no_pool_none_return_fails_closed():
    p = _slipstream_pool()
    assert _run(_resolver(FakeChain(p, factory_returns=None)).resolve(p)) is None


def test_rpc_failure_on_getpool_fails_closed():
    p = _slipstream_pool()
    fake = FakeChain(p, raise_on={SEL_GETPOOL_INT24})
    assert _run(_resolver(fake).resolve(p)) is None


def test_rpc_failure_on_validation_fails_closed():
    p = _classic_pool()
    fake = FakeChain(p, raise_on={SEL_TOKEN0})
    assert _run(_resolver(fake).resolve(p)) is None


def test_token_pair_mismatch_fails_closed():
    p = _slipstream_pool()
    fake = FakeChain(p, token0="0x000000000000000000000000000000000000dEaD")
    assert _run(_resolver(fake).resolve(p)) is None


def test_wrong_tick_spacing_fails_closed():
    p = _slipstream_pool()
    fake = FakeChain(p, tick_spacing=(int(p.tick_spacing) + 1))
    assert _run(_resolver(fake).resolve(p)) is None


def test_wrong_stable_flag_fails_closed():
    p = _classic_pool()
    fake = FakeChain(p, stable=(not bool(p.stable)))
    assert _run(_resolver(fake).resolve(p)) is None


def test_tick_spacing_read_unavailable_fails_closed():
    p = _slipstream_pool()
    fake = FakeChain(p, tick_read_none=True)   # tickSpacing() returns None
    assert _run(_resolver(fake).resolve(p)) is None


def test_cl_factory_unset_fails_closed():
    p = _slipstream_pool()
    r = _run(_resolver(FakeChain(p), cl_factory=None).resolve(p))
    assert r is None


def test_wrong_chain_fails_closed():
    import dataclasses
    p = dataclasses.replace(_slipstream_pool(), chain="arbitrum")
    assert _run(_resolver(FakeChain(p)).resolve(p)) is None


def test_env_builder_none_without_eth_call():
    assert build_base_aero_resolver_from_env(None) is None


def test_env_builder_defaults():
    r = build_base_aero_resolver_from_env(FakeChain(_slipstream_pool()).eth_call)
    assert r is not None
    assert r._cl.lower() == DEFAULT_AERO_CL_FACTORY.lower()
    assert r._classic.lower() == DEFAULT_AERO_POOL_FACTORY.lower()


# ── registry round-trip + Gate 8 integration ────────────────────────────────
def _snapshot_registry():
    return (list(reg._POOLS), dict(reg._BY_ID), dict(reg._BY_ADDRESS))


def _restore_registry(snap):
    pools, by_id, by_addr = snap
    reg._POOLS[:] = pools
    reg._BY_ID.clear(); reg._BY_ID.update(by_id)
    reg._BY_ADDRESS.clear(); reg._BY_ADDRESS.update(by_addr)


def test_resolved_addresses_includes_runtime_resolved_pools():
    # Audit 2026-06: resolved_addresses() must surface BOTH deterministic
    # (UniV3) AND genuinely on-chain-resolved (RUNTIME_RESOLVED Aerodrome/
    # Slipstream) real addresses, while still excluding unresolved pools
    # (fail-closed). Prevents the §4 "resolved on-chain yet real_address=null"
    # discrepancy for any consumer of this accessor.
    snap = _snapshot_registry()
    try:
        p = _slipstream_pool()
        pid = p.canonical_id
        # unresolved → absent from resolved_addresses (fail-closed)
        assert pid not in reg.resolved_addresses()
        ok = reg.set_runtime_resolved_address(
            pid, POOL, provenance={"method": "cl_getPool"})
        assert ok is True
        ra = reg.resolved_addresses()
        # now present with the genuine on-chain-resolved address
        assert pid in ra
        assert ra[pid].lower() == POOL.lower()
        # deterministic UniV3 pools remain present too
        assert any(
            cp.address_resolution == reg.DETERMINISTIC_VERIFIED
            and cp.canonical_id in ra
            for cp in reg.get_canonical_pools())
        # a still-unresolved runtime_getpool pool stays excluded
        assert any(
            cp.canonical_id not in ra
            for cp in reg.get_canonical_pools()
            if cp.address_resolution == reg.RUNTIME_GETPOOL)
    finally:
        _restore_registry(snap)


def test_set_runtime_resolved_address_roundtrip_and_guards():
    snap = _snapshot_registry()
    try:
        p = _slipstream_pool()
        assert p.address is None
        ok = reg.set_runtime_resolved_address(
            p.canonical_id, POOL, provenance={"method": "cl_getPool"})
        assert ok is True
        got = reg.canonical_pool_by_id(p.canonical_id)
        assert got.address.lower() == POOL.lower()
        assert got.address_resolution == reg.RUNTIME_RESOLVED
        assert reg.canonical_pool_by_address(POOL) is not None
        # guards: zero + unknown id refused
        assert reg.set_runtime_resolved_address(
            p.canonical_id, "0x" + "0" * 40, provenance={}) is False
        assert reg.set_runtime_resolved_address(
            "nope", POOL, provenance={}) is False
    finally:
        _restore_registry(snap)


def test_integration_unresolved_gate8_fail_then_resolved_evaluates():
    snap = _snapshot_registry()
    try:
        p = _slipstream_pool()
        pid = p.canonical_id

        class _TVL:  # returns real depth only for the resolved address
            async def get_pool_tvl_usd(self, chain, pool_address):
                cp = reg.canonical_pool_by_id(pid)
                if cp.address and pool_address.lower() == cp.address.lower():
                    return 750_000.0
                return None

        # BEFORE resolution: address None → skipped → min tvl 0 → Gate 8 FAIL
        tvls = _run(_resolve_pool_tvls([pid], _TVL()))
        min_tvl = _route_min_tvl(tvls, [pid])
        assert min_tvl == 0.0
        assert FlashLoanGate8LiquidityDepth({}).evaluate(
            min_pool_tvl_usd_in_route=min_tvl).passed is False

        # resolve on-chain (validated) then record into the registry
        res = _run(_resolver(FakeChain(p)).resolve(p))
        assert res is not None
        assert reg.set_runtime_resolved_address(
            pid, res.address, provenance=res.provenance) is True

        # AFTER resolution: real depth flows via the EXISTING reserves path
        tvls = _run(_resolve_pool_tvls([pid], _TVL()))
        min_tvl = _route_min_tvl(tvls, [pid])
        assert min_tvl == 750_000.0
        assert FlashLoanGate8LiquidityDepth({}).evaluate(
            min_pool_tvl_usd_in_route=min_tvl).passed is True
    finally:
        _restore_registry(snap)


def test_resolve_all_skips_failures():
    p = _slipstream_pool()
    # factory returns zero for everything → nothing resolves
    fake = FakeChain(p, factory_returns="zero")
    out = _run(_resolver(fake).resolve_all(reg.unresolved_pools()))
    assert out == {}
