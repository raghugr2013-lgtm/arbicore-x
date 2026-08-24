"""ArbiCore X — Milestone 1: canonical Base pool registry (REAL addresses).

ONE canonical source of pool identity for every consumer (route/discovery/quote
today; WSS log subscription + on-chain V3 state reads in later milestones).

Design principles (per master brief §9):
  * Do NOT duplicate pool metadata. This registry is DERIVED from the existing
    ``base_venues.VENUES`` / ``base_venues.TOKENS`` — the single venue list is
    still authored there. We add REAL contract identity on top.
  * Do NOT fabricate an address. Each pool carries an explicit
    ``address_resolution`` provenance:
        - ``deterministic_verified`` : address computed via CREATE2 using the
          canonical Uniswap-V3 factory + POOL_INIT_CODE_HASH. The derivation is
          proven offline by known-answer tests against publicly-deployed Base
          pools (see tests/test_m1_base_pool_registry.py). No RPC required.
        - ``runtime_getpool``        : address must be resolved on-chain via a
          factory ``getPool`` call on the VPS (Aerodrome SlipStream + classic —
          their factory/deployer/init-code derivation is NOT established from
          this repo, so we refuse to guess it).
        - ``unresolved``             : neither path available (should be empty).

INVARIANTS: never fabricates liquidity/TVL (TVL is out of scope here); the
``canonical_id`` matches ``base_venues._venue_id`` so existing consumers can be
migrated 1:1 without a parallel pool list. Existing ``build_pool_graph()`` is
left UNCHANGED — this module is purely additive until the registry is proven.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from eth_abi import encode as _abi_encode
from eth_utils import keccak as _keccak, to_checksum_address as _checksum

from . import base_venues

CHAIN = base_venues.CHAIN  # "base"

# ── Uniswap V3 canonical deterministic-derivation constants (Base 8453) ─────
# Factory: Uniswap docs — v3-base-deployments (BaseScan-verified).
# INIT_CODE_HASH: canonical UniswapV3Pool creation-code hash, identical across
# all canonical Uniswap V3 deployments (Uniswap v3-periphery PoolAddress.sol /
# v3-sdk constants.ts). Both are cross-checked offline by known-answer tests
# against the publicly-deployed Base pools:
#   WETH/USDC 0.05% -> 0xd0b53D9277642d899DF5C87A3966A349A798F224
#   WETH/USDC 0.01% -> 0xb4CB800910B228ED3d0834cF79D697127BBB00e5
BASE_UNIV3_FACTORY = _checksum("0x33128a8fC17869897dcE68Ed026d694621f6FDfD")
UNIV3_POOL_INIT_CODE_HASH = bytes.fromhex(
    "e34f199b19b2b4f47f68442619d555527d244f78a3297ea89325f843f87b8b54"
)

# ``getPool(address,address,uint24)`` selector — used by the VPS runtime path
# to resolve/verify addresses on-chain (keccak("getPool(address,address,uint24)")[:4]).
UNIV3_GET_POOL_SELECTOR = "0x1698ee82"

DETERMINISTIC_VERIFIED = "deterministic_verified"
RUNTIME_GETPOOL = "runtime_getpool"
UNRESOLVED = "unresolved"


# ── Canonical pool record ───────────────────────────────────────────────────
@dataclass(frozen=True)
class CanonicalPool:
    """One canonical Base pool with enough identity for ALL consumers."""

    canonical_id: str            # == base_venues._venue_id(dex, a, b, param)
    dex: str                     # 'uniswap_v3' | 'aerodrome_slipstream' | 'aerodrome'
    kind: str                    # 'v3' | 'v2' | 'stable'  (matches PoolState.kind)
    chain: str
    # token orientation is BY ADDRESS (on-chain token0/token1), NOT by symbol.
    token0_symbol: str
    token0_address: str
    token0_decimals: int
    token1_symbol: str
    token1_address: str
    token1_decimals: int
    fee_ppm: Optional[int]       # UniV3 fee (500/3000/10000/100); None otherwise
    fee_bps: Optional[int]       # nominal fee in bps hint (None => dynamic)
    tick_spacing: Optional[int]  # Aerodrome SlipStream / UniV3 tick spacing
    stable: Optional[bool]       # Aerodrome classic: stable vs volatile
    address: Optional[str]       # real contract address (checksummed) or None
    address_resolution: str      # deterministic_verified|runtime_getpool|unresolved
    provenance: str              # human-readable derivation source
    resolver: Dict[str, Any] = field(default_factory=dict)  # VPS getPool hint

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "dex": self.dex,
            "kind": self.kind,
            "chain": self.chain,
            "token0": {"symbol": self.token0_symbol, "address": self.token0_address,
                       "decimals": self.token0_decimals},
            "token1": {"symbol": self.token1_symbol, "address": self.token1_address,
                       "decimals": self.token1_decimals},
            "fee_ppm": self.fee_ppm,
            "fee_bps": self.fee_bps,
            "tick_spacing": self.tick_spacing,
            "stable": self.stable,
            "address": self.address,
            "address_resolution": self.address_resolution,
            "provenance": self.provenance,
            "resolver": dict(self.resolver),
        }


# ── Deterministic Uniswap V3 pool address (CREATE2) ─────────────────────────
def _order_by_address(addr_a: str, addr_b: str) -> bool:
    """True if addr_a is token0 (numerically-lower address), matching the
    on-chain Uniswap ``token0 < token1`` convention."""
    return int(addr_a, 16) < int(addr_b, 16)


def compute_univ3_pool_address(token_a: str, token_b: str, fee_ppm: int) -> str:
    """CREATE2 address of the canonical Uniswap-V3 pool for (token_a, token_b, fee).

    Symmetric in the token arguments (they are address-sorted internally).
    Returns a checksummed 20-byte address. Proven correct by known-answer tests.
    """
    a = _checksum(token_a)
    b = _checksum(token_b)
    token0, token1 = (a, b) if _order_by_address(a, b) else (b, a)
    salt = _keccak(_abi_encode(["address", "address", "uint24"],
                               [token0, token1, int(fee_ppm)]))
    raw = _keccak(b"\xff" + bytes.fromhex(BASE_UNIV3_FACTORY[2:]) + salt
                  + UNIV3_POOL_INIT_CODE_HASH)[12:]
    return _checksum(raw)


# ── Registry construction (derived from base_venues — single source) ────────
def _token_meta(symbol: str) -> Tuple[str, int]:
    meta = base_venues.TOKENS[symbol]
    return _checksum(meta["address"]), int(meta["decimals"])


def _orient(a_sym: str, b_sym: str) -> Tuple[str, str, str, str]:
    """Return (t0_sym, t0_addr, t1_sym, t1_addr) address-ordered."""
    a_addr, _ = _token_meta(a_sym)
    b_addr, _ = _token_meta(b_sym)
    if _order_by_address(a_addr, b_addr):
        return a_sym, a_addr, b_sym, b_addr
    return b_sym, b_addr, a_sym, a_addr


def _build_one(dex: str, a: str, b: str, param: Any) -> CanonicalPool:
    canonical_id = base_venues._venue_id(dex, a, b, param)
    t0_sym, t0_addr, t1_sym, t1_addr = _orient(a, b)
    _, d0 = _token_meta(t0_sym)
    _, d1 = _token_meta(t1_sym)

    if dex == "uniswap_v3":
        fee_ppm = int(param)
        address = compute_univ3_pool_address(t0_addr, t1_addr, fee_ppm)
        return CanonicalPool(
            canonical_id=canonical_id, dex=dex, kind="v3", chain=CHAIN,
            token0_symbol=t0_sym, token0_address=t0_addr, token0_decimals=d0,
            token1_symbol=t1_sym, token1_address=t1_addr, token1_decimals=d1,
            fee_ppm=fee_ppm, fee_bps=fee_ppm // 100, tick_spacing=None, stable=None,
            address=address, address_resolution=DETERMINISTIC_VERIFIED,
            provenance="univ3_create2:base_factory+init_code_hash (KAT-proven)",
            resolver={"method": "getPool", "factory": BASE_UNIV3_FACTORY,
                      "selector": UNIV3_GET_POOL_SELECTOR,
                      "args": [t0_addr, t1_addr, fee_ppm]},
        )

    if dex == "aerodrome_slipstream":
        # Concentrated-liquidity, but the Aerodrome CL factory/init-code
        # derivation is NOT established from this repo → refuse to guess.
        return CanonicalPool(
            canonical_id=canonical_id, dex=dex, kind="v3", chain=CHAIN,
            token0_symbol=t0_sym, token0_address=t0_addr, token0_decimals=d0,
            token1_symbol=t1_sym, token1_address=t1_addr, token1_decimals=d1,
            fee_ppm=None, fee_bps=None, tick_spacing=int(param), stable=None,
            address=None, address_resolution=RUNTIME_GETPOOL,
            provenance="aerodrome_slipstream:resolve_on_vps (no verified init-code)",
            resolver={"method": "getPool_by_tickspacing",
                      "args": [t0_addr, t1_addr, int(param)],
                      "note": "resolve via Aerodrome CL factory on VPS"},
        )

    # aerodrome classic (v2/stable)
    is_stable = (param == "stable")
    return CanonicalPool(
        canonical_id=canonical_id, dex=dex,
        kind="stable" if is_stable else "v2", chain=CHAIN,
        token0_symbol=t0_sym, token0_address=t0_addr, token0_decimals=d0,
        token1_symbol=t1_sym, token1_address=t1_addr, token1_decimals=d1,
        fee_ppm=None, fee_bps=None, tick_spacing=None, stable=is_stable,
        address=None, address_resolution=RUNTIME_GETPOOL,
        provenance="aerodrome_classic:resolve_on_vps (poolFor via factory)",
        resolver={"method": "poolFor", "args": [t0_addr, t1_addr, is_stable],
                  "note": "resolve via Aerodrome PoolFactory on VPS"},
    )


def build_canonical_pools() -> List[CanonicalPool]:
    """Derive the canonical registry from ``base_venues.VENUES`` (1:1)."""
    return [_build_one(dex, a, b, param)
            for (dex, a, b, param) in base_venues.VENUES]


# Module-level immutable snapshot + lookup indexes.
_POOLS: List[CanonicalPool] = build_canonical_pools()
_BY_ID: Dict[str, CanonicalPool] = {p.canonical_id: p for p in _POOLS}
_BY_ADDRESS: Dict[str, CanonicalPool] = {
    p.address.lower(): p for p in _POOLS if p.address
}


def get_canonical_pools() -> List[CanonicalPool]:
    return list(_POOLS)


def canonical_pool_by_id(canonical_id: str) -> Optional[CanonicalPool]:
    return _BY_ID.get(canonical_id)


def canonical_pool_by_address(address: str) -> Optional[CanonicalPool]:
    return _BY_ADDRESS.get((address or "").lower())


def resolved_addresses() -> Dict[str, str]:
    """{canonical_id: real_address} for every deterministically-verified pool."""
    return {p.canonical_id: p.address for p in _POOLS
            if p.address and p.address_resolution == DETERMINISTIC_VERIFIED}


def unresolved_pools() -> List[CanonicalPool]:
    """Pools still needing on-chain resolution (runtime_getpool/unresolved)."""
    return [p for p in _POOLS if p.address_resolution != DETERMINISTIC_VERIFIED]


def registry_summary() -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for p in _POOLS:
        counts[p.address_resolution] = counts.get(p.address_resolution, 0) + 1
    return {
        "chain": CHAIN,
        "total": len(_POOLS),
        "by_resolution": counts,
        "univ3_factory": BASE_UNIV3_FACTORY,
        "deterministic_verified": counts.get(DETERMINISTIC_VERIFIED, 0),
        "runtime_getpool": counts.get(RUNTIME_GETPOOL, 0),
        "unresolved": counts.get(UNRESOLVED, 0),
    }


__all__ = [
    "CHAIN", "CanonicalPool",
    "BASE_UNIV3_FACTORY", "UNIV3_POOL_INIT_CODE_HASH", "UNIV3_GET_POOL_SELECTOR",
    "DETERMINISTIC_VERIFIED", "RUNTIME_GETPOOL", "UNRESOLVED",
    "compute_univ3_pool_address", "build_canonical_pools",
    "get_canonical_pools", "canonical_pool_by_id", "canonical_pool_by_address",
    "resolved_addresses", "unresolved_pools", "registry_summary",
]
