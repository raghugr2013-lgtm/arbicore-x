"""Milestone 1 — canonical Base pool registry tests (deterministic, offline).

Proves the Uniswap-V3 CREATE2 address derivation against publicly-deployed Base
pools (known-answer tests), plus token-ordering / fee-tier handling and the
resolution-provenance contract. No RPC, no network — fully deterministic.
"""
from __future__ import annotations

from eth_utils import to_checksum_address

from arbicore.discovery import base_pool_registry as reg
from arbicore.discovery import base_venues


WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Publicly-deployed Base Uniswap V3 pools (independently verifiable on BaseScan /
# GeckoTerminal). These anchor the CREATE2 derivation.
KAT = {
    (500): "0xd0b53D9277642d899DF5C87A3966A349A798F224",   # WETH/USDC 0.05%
    (100): "0xb4CB800910B228ED3d0834cF79D697127BBB00e5",   # WETH/USDC 0.01%
}


# ── CREATE2 known-answer (proves factory + init-code-hash + encoding) ───────
def test_kat_weth_usdc_500():
    got = reg.compute_univ3_pool_address(WETH, USDC, 500)
    assert got == to_checksum_address(KAT[500])


def test_kat_weth_usdc_100():
    got = reg.compute_univ3_pool_address(WETH, USDC, 100)
    assert got == to_checksum_address(KAT[100])


def test_address_derivation_is_symmetric_in_token_args():
    assert (reg.compute_univ3_pool_address(WETH, USDC, 500)
            == reg.compute_univ3_pool_address(USDC, WETH, 500))


def test_fee_tiers_produce_distinct_addresses():
    a500 = reg.compute_univ3_pool_address(WETH, USDC, 500)
    a3000 = reg.compute_univ3_pool_address(WETH, USDC, 3000)
    a10000 = reg.compute_univ3_pool_address(WETH, USDC, 10000)
    assert len({a500, a3000, a10000}) == 3


def test_computed_addresses_are_valid_checksummed_20_bytes():
    addr = reg.compute_univ3_pool_address(WETH, USDC, 3000)
    assert addr == to_checksum_address(addr)
    assert len(bytes.fromhex(addr[2:])) == 20


# ── Token ordering (on-chain token0 < token1 by address) ────────────────────
def test_univ3_pools_are_address_ordered():
    for p in reg.get_canonical_pools():
        if p.dex != "uniswap_v3":
            continue
        assert int(p.token0_address, 16) < int(p.token1_address, 16), p.canonical_id


def test_orientation_symbols_map_to_correct_addresses():
    for p in reg.get_canonical_pools():
        a0 = to_checksum_address(base_venues.TOKENS[p.token0_symbol]["address"])
        a1 = to_checksum_address(base_venues.TOKENS[p.token1_symbol]["address"])
        assert p.token0_address == a0
        assert p.token1_address == a1
        assert p.token0_decimals == base_venues.TOKENS[p.token0_symbol]["decimals"]
        assert p.token1_decimals == base_venues.TOKENS[p.token1_symbol]["decimals"]


# ── Fee-tier handling ───────────────────────────────────────────────────────
def test_univ3_fee_ppm_and_bps():
    for p in reg.get_canonical_pools():
        if p.dex != "uniswap_v3":
            continue
        assert p.fee_ppm in (100, 500, 3000, 10000)
        assert p.fee_bps == p.fee_ppm // 100
        assert p.kind == "v3"


def test_aerodrome_slipstream_carries_tick_spacing_not_fee():
    for p in reg.get_canonical_pools():
        if p.dex != "aerodrome_slipstream":
            continue
        assert p.tick_spacing is not None
        assert p.fee_ppm is None


def test_aerodrome_classic_stable_flag_and_kind():
    for p in reg.get_canonical_pools():
        if p.dex != "aerodrome":
            continue
        assert p.stable in (True, False)
        assert p.kind == ("stable" if p.stable else "v2")


# ── Resolution provenance contract ──────────────────────────────────────────
def test_univ3_pools_are_deterministic_verified_with_address():
    for p in reg.get_canonical_pools():
        if p.dex != "uniswap_v3":
            continue
        assert p.address_resolution == reg.DETERMINISTIC_VERIFIED
        assert p.address and p.address == to_checksum_address(p.address)


def test_aerodrome_pools_are_runtime_getpool_without_address():
    for p in reg.get_canonical_pools():
        if p.dex.startswith("aerodrome"):
            assert p.address_resolution == reg.RUNTIME_GETPOOL
            assert p.address is None
            assert p.resolver.get("method")


def test_no_unresolved_pools():
    assert reg.unresolved_pools() != [] or True  # informational
    assert all(p.address_resolution != reg.UNRESOLVED
               for p in reg.get_canonical_pools())


def test_deterministic_addresses_match_standalone_computation():
    for p in reg.get_canonical_pools():
        if p.address_resolution != reg.DETERMINISTIC_VERIFIED:
            continue
        recomputed = reg.compute_univ3_pool_address(
            p.token0_address, p.token1_address, p.fee_ppm)
        assert recomputed == p.address


# ── Canonical-id bridge to the existing synthetic venue ids (no dup metadata) ─
def test_canonical_id_matches_base_venues_synthetic_id():
    pools, _specs = base_venues.build_pool_graph()
    synthetic_ids = {pn.pool_address for pn in pools}
    canonical_ids = {p.canonical_id for p in reg.get_canonical_pools()}
    assert canonical_ids == synthetic_ids


def test_registry_covers_exactly_base_venues():
    assert len(reg.get_canonical_pools()) == len(base_venues.VENUES)
    for (dex, a, b, param) in base_venues.VENUES:
        cid = base_venues._venue_id(dex, a, b, param)
        assert reg.canonical_pool_by_id(cid) is not None


def test_lookup_by_address_roundtrip():
    for p in reg.get_canonical_pools():
        if p.address:
            assert reg.canonical_pool_by_address(p.address) is p
            assert reg.canonical_pool_by_address(p.address.lower()) is p


# ── Determinism / stability ─────────────────────────────────────────────────
def test_build_is_deterministic():
    a = [p.to_dict() for p in reg.build_canonical_pools()]
    b = [p.to_dict() for p in reg.build_canonical_pools()]
    assert a == b


def test_registry_summary_counts_consistent():
    s = reg.registry_summary()
    assert s["total"] == len(base_venues.VENUES)
    assert (s["deterministic_verified"] + s["runtime_getpool"]
            + s["unresolved"]) == s["total"]
    assert s["univ3_factory"] == reg.BASE_UNIV3_FACTORY


def test_existing_build_pool_graph_unchanged():
    """Preserve existing discovery/FlashLoan behavior: build_pool_graph must
    still return synthetic ids with tvl_usd sentinel (registry is additive)."""
    pools, specs = base_venues.build_pool_graph()
    assert len(pools) == len(base_venues.VENUES)
    assert all(pn.tvl_usd == 0.0 for pn in pools)
    # synthetic id, NOT a real address, remains the pool_address here.
    assert all(":" in pn.pool_address for pn in pools)
