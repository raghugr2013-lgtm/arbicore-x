"""Z8/Z9 regression — canonical registry IS the flash-loan scanner's Base
route universe (identity-preserving, fail-closed).

Proves the disconnect is closed WITHOUT weakening any gate or fabricating
anything:
  * the RouteSearchEngine loader is now sourced from base_pool_registry
    (single source of truth), not the legacy base_venues parallel graph;
  * only pools with a genuine RESOLVED on-chain address enter the live path
    (deterministic UniV3 offline; runtime-resolved Aerodrome after the VPS
    getPool mutation) — unresolved/synthetic-only ids are excluded (fail-closed);
  * venue specs come from the ONE registry and are byte-identical to the
    frozen base_venues specs (no drift, no behavioural change for resolved pools);
  * resolver failure / zero / unknown-id are rejected (no fabricated address);
  * runtime resolution propagates into the loader;
  * nothing here signs or broadcasts.
"""
from __future__ import annotations

import asyncio

import pytest
from eth_utils import to_checksum_address

from arbicore.discovery import base_pool_registry as reg
from arbicore.discovery import base_venues


# ── force a PRISTINE registry per test (robust to xdist module co-scheduling:
#    sibling modules mutate the shared module-global registry via
#    set_runtime_resolved_address and don't always restore it). We rebuild the
#    deterministic offline baseline (19 deterministic_verified + 11
#    runtime_getpool w/ address=None) before each test and restore whatever was
#    there afterwards — so these tests neither depend on nor cause pollution. ──
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


# ── canonical population invariants ─────────────────────────────────────────
def test_thirty_canonical_pools():
    assert len(reg.get_canonical_pools()) == 30 == len(base_venues.VENUES)


def test_nineteen_deterministic_addresses_offline():
    det = [p for p in reg.get_canonical_pools()
           if p.address_resolution == reg.DETERMINISTIC_VERIFIED and p.address]
    assert len(det) == 19
    assert all(p.dex == "uniswap_v3" for p in det)


def test_eleven_runtime_pools_without_fabricated_address_offline():
    rt = [p for p in reg.get_canonical_pools()
          if p.address_resolution == reg.RUNTIME_GETPOOL]
    assert len(rt) == 11
    assert all(p.address is None and p.dex.startswith("aerodrome") for p in rt)


# ── loader is canonical + fail-closed ───────────────────────────────────────
def test_loader_excludes_unresolved_failclosed():
    nodes, specs = reg.build_canonical_pool_graph(resolved_only=True)
    assert len(nodes) == 19                    # only deterministic UniV3 offline
    assert len(specs) == 30                    # specs are metadata for ALL pools


def test_loader_full_graph_includes_all_when_requested():
    nodes, _ = reg.build_canonical_pool_graph(resolved_only=False)
    assert len(nodes) == 30


def test_loader_node_identity_is_canonical_id_backed_by_real_address():
    """Every id entering the route search maps to a canonical pool that owns a
    genuine resolved contract address — no synthetic-only id reaches the graph."""
    nodes, _ = reg.build_canonical_pool_graph(resolved_only=True)
    for n in nodes:
        cp = reg.canonical_pool_by_id(n.pool_address)   # pool_address == canonical_id
        assert cp is not None, n.pool_address
        assert cp.address and cp.address == to_checksum_address(cp.address)
        assert n.tvl_usd == 0.0                          # never fabricated
        assert n.dex_protocol == cp.dex
        assert {n.token_a, n.token_b} == {cp.token0_symbol, cp.token1_symbol}


def test_specs_identical_to_frozen_base_venues():
    _, canon = base_venues.build_pool_graph()
    reg_specs = reg.canonical_pool_specs()
    _, canon_specs = reg.build_canonical_pool_graph(resolved_only=False)
    assert reg_specs == canon == canon_specs           # single source, no drift


# ── resolver → loader propagation + fail-closed on bad input ────────────────
_FAKE_AERO = to_checksum_address("0x" + "ab" * 20)


def test_runtime_resolution_enters_loader():
    target = next(p.canonical_id for p in reg.get_canonical_pools()
                  if p.address_resolution == reg.RUNTIME_GETPOOL)
    before = {n.pool_address for n in reg.build_canonical_pool_graph()[0]}
    assert target not in before                        # excluded while unresolved

    ok = reg.set_runtime_resolved_address(
        target, _FAKE_AERO, provenance={"method": "getPool_by_tickspacing"})
    assert ok is True
    after = {n.pool_address for n in reg.build_canonical_pool_graph()[0]}
    assert target in after and len(after) == len(before) + 1


def test_resolver_failure_and_zero_address_fail_closed():
    target = next(p.canonical_id for p in reg.get_canonical_pools()
                  if p.address_resolution == reg.RUNTIME_GETPOOL)
    assert reg.set_runtime_resolved_address(target, "", provenance={}) is False
    zero = "0x" + "00" * 20
    assert reg.set_runtime_resolved_address(target, zero, provenance={}) is False
    # still excluded from the live universe (no fabricated address slipped in)
    assert target not in {n.pool_address
                          for n in reg.build_canonical_pool_graph()[0]}


def test_unknown_id_rejected():
    assert reg.set_runtime_resolved_address(
        "uniswap_v3:NOPE:NADA:500", _FAKE_AERO, provenance={}) is False


# ── the live quote provider consumes canonical specs (no legacy graph) ──────
def test_live_quote_provider_uses_canonical_specs():
    import arbicore.scanners.flash_loan_arbitrage.live_quote_provider as lqp
    src = __import__("inspect").getsource(lqp)
    assert "canonical_pool_specs" in src
    assert "build_pool_graph" not in src               # legacy source removed


def test_composition_base_universe_is_canonical_resolved():
    # Source-level assertion (avoids importing composition, which needs Mongo):
    # the Base loader + pool-universe size are sourced from the canonical graph,
    # and the legacy base_venues build_pool_graph loader is gone.
    import os.path as _p
    path = _p.join(_p.dirname(reg.__file__), "..", "runtime", "composition.py")
    with open(_p.normpath(path)) as f:
        src = f.read()
    assert "build_canonical_pool_graph" in src
    assert "_canonical_base_graph(resolved_only=True)" in src
    assert "_base_pools, _ = _bpg()" not in src        # legacy Base loader removed


# ── no broadcast/signing in the discovery loader path ───────────────────────
def test_building_graph_is_pure_readonly():
    # build must not require RPC/network and must be deterministic.
    a = reg.build_canonical_pool_graph()[0]
    b = reg.build_canonical_pool_graph()[0]
    assert [n.pool_address for n in a] == [n.pool_address for n in b]



# ── G2×Z8 end-to-end: on-chain IDENTITY validation gates loader admission ───
# Proves the intersection of the Z8 loader fix and the G2 resolver: a runtime
# Aerodrome/Slipstream pool enters the canonical live-path loader ONLY after the
# resolver's on-chain token0/token1 + pool-type identity checks pass; an
# identity MISMATCH keeps it out (fail-closed). Uses a mocked eth_call — no RPC,
# no signing, no broadcast.
from arbicore.searcher import aero_resolver as _ar  # noqa: E402


def _slipstream_target():
    return next(p for p in reg.get_canonical_pools()
                if p.dex == "aerodrome_slipstream"
                and p.address_resolution == reg.RUNTIME_GETPOOL)


def _mk_eth_call(*, t0_addr, t1_addr, tick_spacing, pool="0x" + "cd" * 20):
    enc_a = lambda a: "0x" + a.lower().replace("0x", "").rjust(64, "0")
    enc_u = lambda n: "0x" + ("%x" % int(n)).rjust(64, "0")

    async def eth_call(to, data):
        if data.startswith(_ar.SEL_GETPOOL_INT24):
            return enc_a(pool)
        if data == _ar.SEL_TOKEN0:
            return enc_a(t0_addr)
        if data == _ar.SEL_TOKEN1:
            return enc_a(t1_addr)
        if data == _ar.SEL_TICK_SPACING:
            return enc_u(tick_spacing)
        return None
    return eth_call


def test_identity_validated_pool_enters_loader():
    p = _slipstream_target()
    ok_call = _mk_eth_call(t0_addr=p.token0_address, t1_addr=p.token1_address,
                           tick_spacing=p.tick_spacing)
    n = asyncio.new_event_loop().run_until_complete(
        _ar.resolve_and_propagate(ok_call, [p.canonical_id]))
    assert n == 1
    cp = reg.canonical_pool_by_id(p.canonical_id)
    assert cp.address_resolution == reg.RUNTIME_RESOLVED and cp.address
    assert p.canonical_id in {x.pool_address
                              for x in reg.build_canonical_pool_graph()[0]}


def test_identity_mismatch_blocks_loader_admission():
    p = _slipstream_target()
    wrong = "0x" + "11" * 20  # token0 != canonical → identity check fails
    bad_call = _mk_eth_call(t0_addr=wrong, t1_addr=p.token1_address,
                            tick_spacing=p.tick_spacing)
    n = asyncio.new_event_loop().run_until_complete(
        _ar.resolve_and_propagate(bad_call, [p.canonical_id]))
    assert n == 0                                   # rejected, fail-closed
    cp = reg.canonical_pool_by_id(p.canonical_id)
    assert cp.address is None                       # no fabricated address
    assert p.canonical_id not in {x.pool_address
                                  for x in reg.build_canonical_pool_graph()[0]}
