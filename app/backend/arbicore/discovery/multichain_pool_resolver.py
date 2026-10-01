"""SP-5 · Multichain on-chain pool-address resolver (read-only, fail-closed).

Resolves an SP-2 candidate ``(dex, token-pair, fee)`` to its REAL on-chain
Uniswap-V3 pool contract address via the DEX factory:

    getPool(address tokenA, address tokenB, uint24 fee)

and reads each token's ``decimals()``, producing:

  * the real ``pool_contract_address`` (SP-3 quote path can restrict to venues
    that actually exist on-chain), and
  * the ``pool_meta`` entry EXACTLY in the shape the SP-4 TVL path expects:
        pool_address(lower) -> (t0_id, t0_addr, dec0, t1_id, t1_addr, dec1)

This REUSES the existing on-chain call convention and helpers from
``searcher/aero_resolver`` (``EthCall``, ``_sel``/``_enc_addr``/``_enc_uint``/
``_decode_addr``, ``SEL_TOKEN0``/``SEL_TOKEN1``) — it is NOT a second
pool-discovery architecture, only the Uniswap-V3 factory analogue of the
existing Aerodrome resolver.

FAIL-CLOSED: a pool resolves ONLY when every check passes (supported chain +
dex, valid distinct token pair, non-zero factory result, on-chain
``token0()``/``token1()`` match the requested pair, readable ``decimals()``).
Otherwise ``None`` — no pool address is fabricated and no unrelated pool is ever
accepted. No signing / broadcast / execution / threshold change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from eth_utils import to_checksum_address

from ..searcher.aero_resolver import (  # reuse existing conventions/helpers
    EthCall, _sel, _enc_addr, _enc_uint, _decode_addr, SEL_TOKEN0, SEL_TOKEN1,
)

# Uniswap-V3 factory + ERC-20 selectors.
SEL_GETPOOL_UINT24 = _sel("getPool(address,address,uint24)")
SEL_DECIMALS = _sel("decimals()")

_SUPPORTED_CHAINS = ("ethereum", "arbitrum", "optimism", "polygon", "bnb")
_SUPPORTED_DEXES = ("uniswap_v3",)  # UniV3 getPool(address,address,uint24) only


@dataclass
class ResolvedPool:
    chain: str
    dex: str
    address: str                 # real, checksummed pool contract address
    token_a: str
    token_a_addr: str
    token_b: str
    token_b_addr: str
    fee: int                     # uint24 fee (e.g. 500 / 3000 / 10000)
    pool_meta: Dict[str, tuple]  # SP-4 input: {addr.lower(): (t0_id,t0_addr,d0,t1_id,t1_addr,d1)}
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainResolution:
    chain: str
    pool_meta: Dict[str, tuple]            # merged SP-4 input
    resolved_specs: List[Dict[str, Any]]   # SP-3-compatible (real pool_contract_address)
    unresolved: List[str]                  # venue_ids that failed closed


class MultichainPoolResolver:
    """Read-only Uniswap-V3 pool resolver for the five non-Base chains."""

    def __init__(self, eth_call: EthCall, chain: str, *,
                 factory_by_dex: Optional[Dict[str, str]] = None,
                 token_resolver: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self._eth = eth_call
        self._chain = (chain or "").strip().lower()
        self._factories = {
            (k or "").lower(): to_checksum_address(v)
            for k, v in (factory_by_dex or {}).items() if v
        }
        if token_resolver is not None:
            self._token = token_resolver
        else:
            from . import multichain_pool_registry as _mreg
            self._token = lambda sym: _mreg.token_address(self._chain, sym)

    async def _call(self, to: str, data: str) -> Optional[str]:
        try:
            return await self._eth(to, data)
        except Exception:  # noqa: BLE001 — RPC failure ⇒ fail closed
            return None

    async def _decimals(self, token_addr: str) -> Optional[int]:
        raw = await self._call(token_addr, SEL_DECIMALS)
        if not raw:
            return None
        try:
            d = int(raw, 16)
        except (ValueError, TypeError):
            return None
        return d if 0 <= d <= 36 else None

    async def _validate_tokens(self, pool: str, a: str, b: str) -> bool:
        r0 = _decode_addr(await self._call(pool, SEL_TOKEN0))
        r1 = _decode_addr(await self._call(pool, SEL_TOKEN1))
        if r0 is None or r1 is None:
            return False
        # Set-equality: UniV3 orders token0/token1 by address; never accept an
        # unrelated pool whose tokens don't match the requested pair.
        return {r0.lower(), r1.lower()} == {a.lower(), b.lower()}

    async def resolve(self, dex: str, sym_a: str, sym_b: str,
                      fee: int) -> Optional[ResolvedPool]:
        d = (dex or "").lower()
        if self._chain not in _SUPPORTED_CHAINS or d not in _SUPPORTED_DEXES:
            return None
        factory = self._factories.get(d)
        if factory is None:
            return None
        a = self._token(sym_a)
        b = self._token(sym_b)
        if not a or not b or a.lower() == b.lower():
            return None
        try:
            fee_i = int(fee)
        except (ValueError, TypeError):
            return None
        if fee_i <= 0:
            return None
        data = SEL_GETPOOL_UINT24 + _enc_addr(a) + _enc_addr(b) + _enc_uint(fee_i)
        addr = _decode_addr(await self._call(factory, data))  # zero/malformed → None
        if addr is None:
            return None
        if not await self._validate_tokens(addr, a, b):
            return None
        da = await self._decimals(a)
        db = await self._decimals(b)
        if da is None or db is None:
            return None
        a_cs, b_cs = to_checksum_address(a), to_checksum_address(b)
        meta = {addr.lower(): (sym_a, a_cs, da, sym_b, b_cs, db)}
        return ResolvedPool(
            chain=self._chain, dex=d, address=addr,
            token_a=sym_a, token_a_addr=a_cs, token_b=sym_b, token_b_addr=b_cs,
            fee=fee_i, pool_meta=meta,
            provenance={
                "method": "getPool(address,address,uint24)", "factory": factory,
                "chain": self._chain, "args": [a_cs, b_cs, fee_i],
                "validated": {"non_zero": True, "token_pair": True,
                              "decimals": True},
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )


async def resolve_chain(chain: str, eth_call: EthCall, *,
                        specs: Optional[List[Dict[str, Any]]] = None,
                        factory_by_dex: Optional[Dict[str, str]] = None,
                        token_resolver: Optional[Callable[[str], Optional[str]]] = None,
                        ) -> ChainResolution:
    """Smallest SP-2 → resolver → (pool_meta + resolved_specs) integration.

    Pulls SP-2 candidate specs + verified v3 factory addresses from the SP-2
    read-only registry (unless injected), resolves each candidate on-chain, and
    returns the SP-4 ``pool_meta`` plus SP-3-compatible ``resolved_specs`` (same
    fields as the candidate spec, now carrying the REAL ``pool_contract_address``
    and ``resolution="onchain_resolved"``). Candidates that fail any check are
    omitted from ``pool_meta``/``resolved_specs`` and listed in ``unresolved``
    (Gate 8 keeps failing closed for them). Does not modify SP-2/SP-3/SP-4.
    """
    from . import multichain_pool_registry as mreg
    c = (chain or "").strip().lower()
    if specs is None:
        specs = mreg.pool_candidate_specs(c)
    if factory_by_dex is None:
        factory_by_dex = {
            d["dex"]: d.get("factory")
            for d in mreg.dex_specs(c)
            if d.get("kind") == "v3" and d.get("factory")
        }
    resolver = MultichainPoolResolver(
        eth_call, c, factory_by_dex=factory_by_dex, token_resolver=token_resolver)

    pool_meta: Dict[str, tuple] = {}
    resolved_specs: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    for row in specs:
        vid = row.get("venue_id")
        fee_bps = row.get("fee_bps")
        if fee_bps is None:
            unresolved.append(vid)
            continue
        rp = await resolver.resolve(row.get("dex"), row.get("token_a"),
                                    row.get("token_b"), int(fee_bps) * 100)
        if rp is None:
            unresolved.append(vid)
            continue
        pool_meta.update(rp.pool_meta)
        resolved_specs.append({
            **row,
            "pool_contract_address": rp.address,
            "resolution": "onchain_resolved",
        })
    return ChainResolution(chain=c, pool_meta=pool_meta,
                           resolved_specs=resolved_specs, unresolved=unresolved)


__all__ = [
    "MultichainPoolResolver", "ResolvedPool", "ChainResolution", "resolve_chain",
    "SEL_GETPOOL_UINT24", "SEL_DECIMALS",
]
