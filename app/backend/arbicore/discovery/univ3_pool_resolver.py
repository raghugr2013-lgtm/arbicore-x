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
# UniswapV2-family (getPair + getReserves) — direct V2 forks share this ABI.
_SEL_GET_PAIR = "0x" + function_signature_to_4byte_selector(
    "getPair(address,address)").hex()
_SEL_GET_RESERVES = "0x" + function_signature_to_4byte_selector(
    "getReserves()").hex()

_ZERO_ADDR = "0x" + "0" * 40


def univ3_family_factory_for(chain: str, dex: str = "uniswap_v3") -> Optional[str]:
    """Factory for a specific UniV3-ABI venue (``abi == 'univ3'``) on ``chain``.
    Covers Uniswap V3 AND its DIRECT forks (Sushi V3, Pancake V3) that share the
    exact ``getPool(address,address,uint24)`` ABI. Returns None for a venue whose
    ABI is NOT univ3 (e.g. Algebra) — the caller must not resolve it here."""
    from ..chains.registries import dexes_for
    for d in dexes_for(chain):
        if d.get("dex") == dex and d.get("abi") == "univ3" and d.get("factory"):
            return d["factory"]
    return None


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
    eth_call: EthCall, factory: Optional[str] = None, dex: str = "uniswap_v3",
) -> Optional[Dict[str, Any]]:
    """Resolve + validate a real UniV3-ABI pool (Uniswap V3 or a DIRECT fork —
    Sushi V3 / Pancake V3 — selected via ``dex``). Returns a validated descriptor
    or ``None`` (fail-closed) on ANY of: no registered factory, factory read
    failure, zero/nonexistent pool address, unreadable/malformed token/fee/
    liquidity state, token pair mismatch, fee-tier inconsistency, or non-positive
    liquidity."""
    if factory is None:
        factory = univ3_family_factory_for(chain, dex)
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
        "dex": dex,
        "pool_address": pool,
        "factory": to_checksum_address(factory),
        "token0": t0,
        "token1": t1,
        "fee": pool_fee,
        "liquidity": liquidity,
        "resolution": "onchain_factory_getPool",
    }


async def resolve_univ2_pool(
    chain: str, token_a: str, token_b: str, *,
    eth_call: EthCall, dex: str = "sushiswap_v2", factory: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve + validate a real UniswapV2-ABI pair (Uniswap V2 or a DIRECT fork,
    e.g. SushiSwap V2) via ``factory.getPair(tokenA,tokenB)`` + on-chain
    ``token0/token1/getReserves``. Fail-closed (``None``) on ANY of: no registered
    factory, factory read failure, zero/nonexistent pair, unreadable/malformed
    state, token-pair mismatch, or non-positive reserves. No address / reserve /
    pairing is ever fabricated."""
    from ..chains.registries import dexes_for
    if factory is None:
        for d in dexes_for(chain):
            if d.get("dex") == dex and d.get("abi") == "univ2" and d.get("factory"):
                factory = d["factory"]
                break
    if not factory:
        return None
    try:
        a = to_checksum_address(token_a)
        b = to_checksum_address(token_b)
    except Exception:  # noqa: BLE001 — malformed inputs fail closed
        return None

    # 1) factory.getPair(tokenA, tokenB) -> pair address
    try:
        data = _SEL_GET_PAIR + _abi_encode(["address", "address"], [a, b]).hex()
        (pair_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(factory, data)))
        pair = to_checksum_address(pair_raw)
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("getPair unreadable chain=%s dex=%s %s/%s: %s",
                   chain, dex, token_a, token_b, exc)
        return None
    if pair.lower() == _ZERO_ADDR:      # nonexistent pair
        return None

    # 2) validate pair state — token0/token1 + reserves (all must read)
    try:
        (t0_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(pair, _SEL_TOKEN0)))
        (t1_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(pair, _SEL_TOKEN1)))
        r0, r1, _ts = _abi_decode(
            ["uint112", "uint112", "uint32"],
            _to_bytes(await eth_call(pair, _SEL_GET_RESERVES)))
        t0 = to_checksum_address(t0_raw)
        t1 = to_checksum_address(t1_raw)
        r0 = int(r0)
        r1 = int(r1)
    except Exception as exc:  # noqa: BLE001 — unreadable/malformed state fails closed
        _LOG.debug("pair state unreadable chain=%s pair=%s: %s", chain, pair, exc)
        return None

    if {t0.lower(), t1.lower()} != {a.lower(), b.lower()}:
        return None
    if r0 <= 0 or r1 <= 0:              # empty reserves excluded fail-closed
        return None

    return {
        "chain": chain,
        "dex": dex,
        "pool_address": pair,
        "factory": to_checksum_address(factory),
        "token0": t0,
        "token1": t1,
        "reserve0": r0,
        "reserve1": r1,
        "resolution": "onchain_factory_getPair",
    }


__all__ = ["resolve_univ3_pool", "resolve_univ2_pool", "univ3_factory_for",
           "univ3_family_factory_for", "EthCall"]
