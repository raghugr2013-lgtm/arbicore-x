"""Fail-closed multichain Uniswap-V3 pool resolution.

Resolves a REAL UniV3 pool on-chain from the registered factory for a chain
(``chains/registries.py``) using token addresses + fee tier, then validates it.
No pool address / liquidity / token pairing is ever fabricated: everything is
read on-chain and a pool that is unreadable / invalid / nonexistent / zero-
liquidity is EXCLUDED (returns ``None``) — the same fail-closed pattern as the
Base ``searcher/aero_resolver.py`` and the P0-3 runtime UniV3 liquidity filter.

Discovery-gate only: this module resolves + validates pool identity/state. It
does NOT quote, price, value (TVL), simulate, sign, or broadcast — those remain
separate downstream gates. Base is unaffected (Base uses its canonical
registry); this covers the other registered EVM chains for UniV3.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from eth_abi import decode as _abi_decode
from eth_abi import encode as _abi_encode
from eth_utils import function_signature_to_4byte_selector, to_checksum_address

from ..chains.registries import registry_for

_LOG = logging.getLogger("arbicore.univ3_pool_resolver")

# eth_call(to, data) -> hex string (fail-closed: may raise or return falsy).
EthCall = Callable[[str, str], Awaitable[Optional[str]]]

_SEL_GET_POOL = "0x" + function_signature_to_4byte_selector(
    "getPool(address,address,uint24)").hex()
_SEL_TOKEN0 = "0x" + function_signature_to_4byte_selector("token0()").hex()
_SEL_TOKEN1 = "0x" + function_signature_to_4byte_selector("token1()").hex()
_SEL_FEE = "0x" + function_signature_to_4byte_selector("fee()").hex()
_SEL_LIQUIDITY = "0x" + function_signature_to_4byte_selector("liquidity()").hex()

_ZERO_ADDR = "0x" + "0" * 40


def univ3_factory_for(chain: str) -> Optional[str]:
    """Registered UniV3 factory address for ``chain`` (None if not present)."""
    for d in registry_for(chain).get("dexes", []):
        if d.get("dex") == "uniswap_v3" and d.get("factory"):
            return d["factory"]
    return None


def _to_bytes(raw: Optional[str]) -> bytes:
    if not raw:
        raise ValueError("empty_response")
    return bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)


async def resolve_univ3_pool(
    chain: str, token_a: str, token_b: str, fee: int, *,
    eth_call: EthCall, factory: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve + validate a real UniV3 pool. Returns a validated descriptor or
    ``None`` (fail-closed) on ANY of: no registered factory, factory read
    failure, zero/nonexistent pool address, unreadable/malformed token/fee/
    liquidity state, token pair mismatch, fee-tier inconsistency, or non-positive
    liquidity."""
    if factory is None:
        factory = univ3_factory_for(chain)
    if not factory:
        # Base is served by its own canonical registry (searcher/aero_resolver +
        # base_pool_registry), not this generic resolver — signal explicitly via
        # logs rather than silently. Still fail-closed (None) for any caller.
        if (chain or "").lower() in ("base", "base-sepolia"):
            _LOG.debug("resolve_univ3_pool: chain=%s handled by canonical "
                       "registry, not the generic resolver", chain)
        return None
    try:
        a = to_checksum_address(token_a)
        b = to_checksum_address(token_b)
        fee_i = int(fee)
    except Exception:  # noqa: BLE001 — malformed inputs fail closed
        return None

    # 1) factory.getPool(tokenA, tokenB, fee) -> pool address
    try:
        data = _SEL_GET_POOL + _abi_encode(
            ["address", "address", "uint24"], [a, b, fee_i]).hex()
        (pool_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(factory, data)))
        pool = to_checksum_address(pool_raw)
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("getPool unreadable chain=%s %s/%s fee=%s: %s",
                   chain, token_a, token_b, fee, exc)
        return None
    if pool.lower() == _ZERO_ADDR:      # nonexistent pool
        return None

    # 2) validate pool state — token0/token1, fee, liquidity (all must read)
    try:
        (t0_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(pool, _SEL_TOKEN0)))
        (t1_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(pool, _SEL_TOKEN1)))
        (pool_fee,) = _abi_decode(["uint24"], _to_bytes(await eth_call(pool, _SEL_FEE)))
        (liquidity,) = _abi_decode(["uint128"], _to_bytes(await eth_call(pool, _SEL_LIQUIDITY)))
        t0 = to_checksum_address(t0_raw)
        t1 = to_checksum_address(t1_raw)
        pool_fee = int(pool_fee)
        liquidity = int(liquidity)
    except Exception as exc:  # noqa: BLE001 — unreadable/malformed state fails closed
        _LOG.debug("pool state unreadable chain=%s pool=%s: %s", chain, pool, exc)
        return None

    # token0/token1 must match the requested pair
    if {t0.lower(), t1.lower()} != {a.lower(), b.lower()}:
        return None
    # fee tier consistency
    if pool_fee != fee_i:
        return None
    # readable positive liquidity (zero / negative excluded fail-closed)
    if liquidity <= 0:
        return None

    return {
        "chain": chain,
        "dex": "uniswap_v3",
        "pool_address": pool,
        "factory": to_checksum_address(factory),
        "token0": t0,
        "token1": t1,
        "fee": pool_fee,
        "liquidity": liquidity,
        "resolution": "onchain_factory_getPool",
    }


__all__ = ["resolve_univ3_pool", "univ3_factory_for", "EthCall"]
