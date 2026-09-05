"""Fail-closed Algebra-V3 (Camelot V3 / QuickSwap V3) pool resolution.

Algebra pools are keyed by TOKEN PAIR ONLY (dynamic fee, no fee tier), so the
factory exposes ``poolByPair(address,address)`` instead of Uniswap's
``getPool(address,address,uint24)``. This module resolves + validates a REAL
Algebra pool on-chain from the registered factory (``chains/registries.py``,
``abi == 'algebra'``) and its live ``token0/token1/liquidity`` state.

Discovery-gate ONLY: identity/state validation. It does NOT quote (Algebra uses
a distinct QuoterV2 with a dynamic-fee ABI — a separate future seam), price,
value (TVL), simulate, sign or broadcast. No pool address / liquidity / pairing
is fabricated: an unreadable / nonexistent / zero-liquidity pool returns ``None``
(same fail-closed pattern as ``univ3_pool_resolver``).

Ref: Algebra Integral factory ``poolByPair`` (docs.algebra.finance,
docs.quickswap.exchange), token order-independent, returns address(0) if absent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from eth_abi import decode as _abi_decode
from eth_abi import encode as _abi_encode
from eth_utils import function_signature_to_4byte_selector, to_checksum_address

from ..chains.registries import dexes_for

_LOG = logging.getLogger("arbicore.algebra_pool_resolver")

from .univ3_pool_resolver import EthCall  # reuse the eth_call contract type

_SEL_POOL_BY_PAIR = "0x" + function_signature_to_4byte_selector(
    "poolByPair(address,address)").hex()
_SEL_TOKEN0 = "0x" + function_signature_to_4byte_selector("token0()").hex()
_SEL_TOKEN1 = "0x" + function_signature_to_4byte_selector("token1()").hex()
_SEL_LIQUIDITY = "0x" + function_signature_to_4byte_selector("liquidity()").hex()

_ZERO_ADDR = "0x" + "0" * 40


def algebra_factory_for(chain: str, dex: str) -> Optional[str]:
    """Registered Algebra factory for ``dex`` on ``chain`` (abi == 'algebra')."""
    for d in dexes_for(chain):
        if d.get("dex") == dex and d.get("abi") == "algebra" and d.get("factory"):
            return d["factory"]
    return None


def _to_bytes(raw: Optional[str]) -> bytes:
    if not raw:
        raise ValueError("empty_response")
    return bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)


async def resolve_algebra_pool(
    chain: str, token_a: str, token_b: str, *,
    eth_call: EthCall, dex: str, factory: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve + validate a real Algebra pool. Returns a validated descriptor or
    ``None`` (fail-closed) on ANY of: no registered factory, factory read
    failure, zero/nonexistent pool address, unreadable/malformed token/liquidity
    state, token-pair mismatch, or non-positive liquidity."""
    if factory is None:
        factory = algebra_factory_for(chain, dex)
    if not factory:
        return None
    try:
        a = to_checksum_address(token_a)
        b = to_checksum_address(token_b)
    except Exception:  # noqa: BLE001 — malformed inputs fail closed
        return None

    # 1) factory.poolByPair(tokenA, tokenB) -> pool address (order-independent)
    try:
        data = _SEL_POOL_BY_PAIR + _abi_encode(["address", "address"], [a, b]).hex()
        (pool_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(factory, data)))
        pool = to_checksum_address(pool_raw)
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("poolByPair unreadable chain=%s dex=%s %s/%s: %s",
                   chain, dex, token_a, token_b, exc)
        return None
    if pool.lower() == _ZERO_ADDR:      # nonexistent pool
        return None

    # 2) validate pool state — token0/token1 + liquidity (all must read)
    try:
        (t0_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(pool, _SEL_TOKEN0)))
        (t1_raw,) = _abi_decode(["address"], _to_bytes(await eth_call(pool, _SEL_TOKEN1)))
        (liquidity,) = _abi_decode(["uint128"], _to_bytes(await eth_call(pool, _SEL_LIQUIDITY)))
        t0 = to_checksum_address(t0_raw)
        t1 = to_checksum_address(t1_raw)
        liquidity = int(liquidity)
    except Exception as exc:  # noqa: BLE001 — unreadable/malformed state fails closed
        _LOG.debug("algebra pool state unreadable chain=%s pool=%s: %s",
                   chain, pool, exc)
        return None

    if {t0.lower(), t1.lower()} != {a.lower(), b.lower()}:
        return None
    if liquidity <= 0:                  # zero/negative liquidity excluded
        return None

    return {
        "chain": chain,
        "dex": dex,
        "pool_address": pool,
        "factory": to_checksum_address(factory),
        "token0": t0,
        "token1": t1,
        "liquidity": liquidity,
        "resolution": "onchain_algebra_poolByPair",
    }


__all__ = ["resolve_algebra_pool", "algebra_factory_for", "EthCall"]
