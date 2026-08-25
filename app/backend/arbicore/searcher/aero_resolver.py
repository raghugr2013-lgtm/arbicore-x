"""M2.6 · Aerodrome / Aerodrome-Slipstream pool address resolution (on-chain).

Resolves the ``runtime_getpool`` canonical pools (which carry ``address=None``)
to their REAL on-chain contract address via the DEX factory's ``getPool`` call,
then VALIDATES the result before it may enter the liquidity/reserves path.

Reuses the existing on-chain call convention (``eth_call: async (to, data) ->
hex``) and the existing approved Aerodrome classic PoolFactory. The Slipstream
CL factory is environment-configurable (``ARBICORE_AERO_CL_FACTORY_BASE``).

FAIL-CLOSED — a pool resolves ONLY when every check passes; otherwise the
resolver returns None and the pool stays unresolved (Gate 8 keeps failing
closed). Checks: RPC ok · non-zero address · on-chain ``token0()``/``token1()``
match the canonical address-ordered pair · pool type matches (classic
``stable()`` / slipstream ``tickSpacing()``). No pool address is ever
fabricated or hard-coded.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from eth_utils import (function_signature_to_4byte_selector,
                       to_checksum_address)

EthCall = Callable[[str, str], Awaitable[Optional[str]]]  # (to, data) -> hex

CHAIN = "base"

# Existing approved Aerodrome classic PoolFactory (reused from the repo:
# execution/aerodrome_settlement.AERODROME_POOL_FACTORY). Env-overridable.
DEFAULT_AERO_POOL_FACTORY = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
# Canonical Aerodrome Slipstream CLFactory on Base (operator-approved default,
# env-overridable). Every resolution is on-chain-validated, so a wrong factory
# can only cause fail-closed, never a bad pool.
DEFAULT_AERO_CL_FACTORY = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"


def _sel(sig: str) -> str:
    return "0x" + function_signature_to_4byte_selector(sig).hex()


# factory getPool selectors
SEL_GETPOOL_BOOL = _sel("getPool(address,address,bool)")     # classic
SEL_GETPOOL_INT24 = _sel("getPool(address,address,int24)")   # slipstream CL
# pool-side validation views
SEL_TOKEN0 = _sel("token0()")
SEL_TOKEN1 = _sel("token1()")
SEL_TICK_SPACING = _sel("tickSpacing()")
SEL_STABLE = _sel("stable()")


def _enc_addr(a: str) -> str:
    return a.lower().replace("0x", "").rjust(64, "0")


def _enc_uint(n: int) -> str:
    return ("%x" % int(n)).rjust(64, "0")


def _decode_addr(raw: Optional[str]) -> Optional[str]:
    if not raw or len(raw) < 66:
        return None
    tail = raw[-40:]
    try:
        if int(tail, 16) == 0:
            return None
    except ValueError:
        return None
    return to_checksum_address("0x" + tail)


@dataclass
class ResolutionResult:
    canonical_id: str
    address: str
    provenance: Dict[str, Any] = field(default_factory=dict)


class AerodromePoolResolver:
    """On-chain resolver for Aerodrome classic + Slipstream pools."""

    def __init__(
        self, eth_call: EthCall, *,
        chain: str = CHAIN,
        classic_factory: str = DEFAULT_AERO_POOL_FACTORY,
        cl_factory: Optional[str] = DEFAULT_AERO_CL_FACTORY,
        get_block: Optional[Callable[[], Awaitable[Optional[int]]]] = None,
    ) -> None:
        self._eth = eth_call
        self._chain = chain
        self._classic = (to_checksum_address(classic_factory)
                         if classic_factory else None)
        self._cl = to_checksum_address(cl_factory) if cl_factory else None
        self._get_block = get_block

    async def _call(self, to: str, data: str) -> Optional[str]:
        try:
            return await self._eth(to, data)
        except Exception:  # noqa: BLE001 — RPC failure ⇒ fail closed
            return None

    async def _validate_tokens(self, pool: str, t0_addr: str,
                               t1_addr: str) -> bool:
        r0 = _decode_addr(await self._call(pool, SEL_TOKEN0))
        r1 = _decode_addr(await self._call(pool, SEL_TOKEN1))
        if r0 is None or r1 is None:
            return False
        return (r0.lower() == t0_addr.lower()
                and r1.lower() == t1_addr.lower())

    async def _validate_tick_spacing(self, pool: str, expected: int) -> bool:
        raw = await self._call(pool, SEL_TICK_SPACING)
        if not raw:
            return False
        try:
            return int(raw, 16) == int(expected)
        except (ValueError, TypeError):
            return False

    async def _validate_stable(self, pool: str, expected: bool) -> bool:
        raw = await self._call(pool, SEL_STABLE)
        if not raw:
            return False
        try:
            return bool(int(raw, 16)) == bool(expected)
        except (ValueError, TypeError):
            return False

    async def resolve(self, pool) -> Optional[ResolutionResult]:
        """Resolve+validate ONE canonical pool. None ⇒ fail closed."""
        dex = pool.dex
        if dex not in ("aerodrome", "aerodrome_slipstream"):
            return None
        if (pool.chain or "").lower() != self._chain:   # wrong chain
            return None
        t0, t1 = pool.token0_address, pool.token1_address

        if dex == "aerodrome_slipstream":
            if self._cl is None:
                return None   # CL factory not configured ⇒ fail closed
            ts = pool.tick_spacing
            if ts is None:
                return None
            data = (SEL_GETPOOL_INT24 + _enc_addr(t0) + _enc_addr(t1)
                    + _enc_uint(int(ts)))
            addr = _decode_addr(await self._call(self._cl, data))
            if addr is None:
                return None
            if not await self._validate_tokens(addr, t0, t1):
                return None
            if not await self._validate_tick_spacing(addr, int(ts)):
                return None
            method = "cl_getPool(address,address,int24)"
            factory = self._cl
            type_check = {"tick_spacing": int(ts)}
        else:  # aerodrome classic
            if self._classic is None:
                return None
            stable = bool(pool.stable)
            data = (SEL_GETPOOL_BOOL + _enc_addr(t0) + _enc_addr(t1)
                    + _enc_uint(1 if stable else 0))
            addr = _decode_addr(await self._call(self._classic, data))
            if addr is None:
                return None
            if not await self._validate_tokens(addr, t0, t1):
                return None
            if not await self._validate_stable(addr, stable):
                return None
            method = "getPool(address,address,bool)"
            factory = self._classic
            type_check = {"stable": stable}

        block = None
        if self._get_block is not None:
            try:
                block = await self._get_block()
            except Exception:  # noqa: BLE001
                block = None

        return ResolutionResult(
            canonical_id=pool.canonical_id, address=addr,
            provenance={
                "method": method, "factory": factory, "chain": self._chain,
                "args": [t0, t1], "type_check": type_check,
                "validated": {"non_zero": True, "token_pair": True,
                              "pool_type": True},
                "block": block, "ts": datetime.now(timezone.utc).isoformat(),
            })

    async def resolve_all(self, pools) -> Dict[str, ResolutionResult]:
        """Resolve every Aerodrome/Slipstream ``runtime_getpool`` pool. Pools
        that fail any check are simply omitted (stay unresolved → Gate 8 keeps
        failing closed)."""
        out: Dict[str, ResolutionResult] = {}
        for p in pools:
            if p.dex not in ("aerodrome", "aerodrome_slipstream"):
                continue
            res = await self.resolve(p)
            if res is not None:
                out[res.canonical_id] = res
        return out


def build_base_aero_resolver_from_env(
    eth_call: Optional[EthCall],
    get_block: Optional[Callable[[], Awaitable[Optional[int]]]] = None,
) -> Optional[AerodromePoolResolver]:
    """Build the resolver from operator env, or None when no eth_call (preview).

    ``ARBICORE_AERO_POOL_FACTORY_BASE`` (default: repo classic factory) and
    ``ARBICORE_AERO_CL_FACTORY_BASE`` (default: canonical Slipstream CLFactory)
    are both env-overridable."""
    if eth_call is None:
        return None
    return AerodromePoolResolver(
        eth_call,
        classic_factory=(os.environ.get("ARBICORE_AERO_POOL_FACTORY_BASE")
                         or DEFAULT_AERO_POOL_FACTORY),
        cl_factory=(os.environ.get("ARBICORE_AERO_CL_FACTORY_BASE")
                    or DEFAULT_AERO_CL_FACTORY),
        get_block=get_block,
    )


async def resolve_and_propagate(
    eth_call: Optional[EthCall],
    pool_ids: Optional[List[str]] = None,
    *,
    get_block: Optional[Callable[[], Awaitable[Optional[int]]]] = None,
) -> int:
    """M2.6 PROPAGATION — resolve+VALIDATE the Aerodrome/Slipstream
    ``runtime_getpool`` pools on-chain and write the REAL, validated addresses
    into the ONE canonical registry via ``set_runtime_resolved_address``.

    This aligns the TVL/address source-of-truth with the (already working)
    quote path: the quote path resolves Aerodrome/Slipstream addresses on the
    fly, but until now the resolved address was never persisted back into the
    registry, so ``canonical_pool_by_id(pid).address`` stayed ``None`` and the
    TVL provider (and the VPS probe) could not measure depth.

    ``pool_ids`` restricts work to a specific route (list of canonical ids);
    ``None`` ⇒ every currently-unresolved Aerodrome/Slipstream pool. Fully
    FAIL-CLOSED: pools that fail ANY on-chain check are simply skipped and stay
    unresolved, so Gate 8 keeps denying. No address is ever fabricated. Returns
    the number of pools newly propagated into the registry."""
    if eth_call is None:
        return 0
    from ..discovery import base_pool_registry as _reg
    resolver = build_base_aero_resolver_from_env(eth_call, get_block=get_block)
    if resolver is None:
        return 0
    if pool_ids is None:
        targets = _reg.unresolved_pools()
    else:
        seen: set = set()
        targets = []
        for pid in pool_ids:
            if pid in seen:
                continue
            seen.add(pid)
            cp = _reg.canonical_pool_by_id(pid)
            if (cp is not None and cp.address is None
                    and cp.dex in ("aerodrome", "aerodrome_slipstream")):
                targets.append(cp)
    if not targets:
        return 0
    results = await resolver.resolve_all(targets)
    n = 0
    for cid, res in results.items():
        if _reg.set_runtime_resolved_address(
                cid, res.address, provenance=res.provenance):
            n += 1
    return n


__all__ = [
    "AerodromePoolResolver", "ResolutionResult",
    "build_base_aero_resolver_from_env", "resolve_and_propagate",
    "DEFAULT_AERO_POOL_FACTORY", "DEFAULT_AERO_CL_FACTORY",
    "SEL_GETPOOL_BOOL", "SEL_GETPOOL_INT24",
]
