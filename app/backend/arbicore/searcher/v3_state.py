"""M2 — Uniswap-V3 on-chain state ingestion (the one genuinely-absent layer).

Reuses the EXISTING primitives and adds ONLY what the audit proved missing:
  * ``sqrtPriceX96 → sqrt_p`` conversion (matches ``amm_math`` raw convention).
  * V3 event decoding (Initialize / Swap / Mint / Burn) → ``PoolStateCache`` log dicts.
  * V3 initial-state bootstrap via real ``slot0()`` / ``liquidity()`` eth_call.
  * V3 on-chain reserves fn (ERC-20 ``balanceOf(pool)``) for the EXISTING
    ``OnChainReserveTVLProvider`` — NOT V2 ``getReserves`` (wrong for V3 pools).

Everything is injectable (eth_call is ``async (to, data) -> hex`` — the same
convention as ``live_base.make_base_reserves_fn``) so it is deterministically
testable offline. Fail-closed: any malformed/absent data → None (never fabricated).
Chain-agnostic: no hardcoded network — the Base composition supplies the pools.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from eth_abi import decode as _abi_decode

from .pool_cache import PoolState

# ── sqrtPriceX96 representation (critical correctness) ──────────────────────
_Q96 = float(2 ** 96)


def sqrtx96_to_sqrt_p(sqrt_price_x96: int) -> float:
    """Convert on-chain Q64.96 ``sqrtPriceX96`` → the float ``sqrt_p`` used by
    ``amm_math.v3_amount_out`` (= sqrt of the RAW token1/token0 price, i.e.
    sqrt(reserve1_wei / reserve0_wei)).

    ``sqrtPriceX96 = sqrt(token1_wei/token0_wei) * 2**96`` ⇒ ``sqrt_p = X96 / 2**96``.
    Token DECIMALS deliberately stay embedded (raw units) because the AMM math
    and route ratios are decimals-consistent and cancel around a closed cycle;
    human/USD pricing applies decimals separately (see ``human_price_token1_per_token0``).
    """
    x = int(sqrt_price_x96)
    if x <= 0:
        return 0.0
    return x / _Q96


def human_price_token1_per_token0(sqrt_price_x96: int, dec0: int, dec1: int) -> float:
    """Human-readable price = token1 per 1 token0 (for inspection/tests).
    price_raw = sqrt_p**2 = token1_wei/token0_wei; human = price_raw * 10**(dec0-dec1)."""
    sp = sqrtx96_to_sqrt_p(sqrt_price_x96)
    return (sp * sp) * (10 ** (int(dec0) - int(dec1)))


# ── V3 event topic0 (keccak of the canonical event signatures) ─────────────
V3_SWAP_TOPIC0 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
V3_MINT_TOPIC0 = "0x7a53080ba414158be7ec69b987b5fb7d07dee101fe85488f0853ae16239d0bde"
V3_BURN_TOPIC0 = "0x0c396cd989a39f4459b5fa1aed6a9a8dcdbc45908acfd67e028cd568da98982c"
V3_INIT_TOPIC0 = "0x98636036cb66a9c19a37435efc1e90142190214e8abeb821bdba3f2990dd4c95"

V3_LOG_TOPIC0S = [V3_SWAP_TOPIC0, V3_MINT_TOPIC0, V3_BURN_TOPIC0, V3_INIT_TOPIC0]

# eth_call selectors.
SLOT0_SELECTOR = "0x3850c7bd"       # slot0()
LIQUIDITY_SELECTOR = "0x1a686502"   # liquidity()
BALANCEOF_SELECTOR = "0x70a08231"   # balanceOf(address)


def _bytes(data_hex: str) -> bytes:
    if not data_hex:
        return b""
    return bytes.fromhex(data_hex[2:] if data_hex.startswith("0x") else data_hex)


def _signed_from_topic(topic_hex: str) -> int:
    """Decode an indexed signed integer (int24 sign-extended to 32 bytes)."""
    v = int(topic_hex, 16)
    return v - 2 ** 256 if v >= 2 ** 255 else v


# ── V3 event decoder (dispatch on topic0) ──────────────────────────────────
def decode_v3_log(raw_log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Decode a UniV3-family (Swap/Mint/Burn/Initialize) log → cache log dict.

    Returns None for non-V3 logs (caller falls back to the V2 Sync decoder).
    Never fabricates: malformed data → None.
    """
    topics = raw_log.get("topics") or []
    if not topics:
        return None
    t0 = (topics[0] or "").lower()
    pool = (raw_log.get("address") or "").lower()
    try:
        block = int(raw_log.get("blockNumber", "0x0"), 16)
    except (ValueError, TypeError):
        block = 0
    b = _bytes(raw_log.get("data", "0x"))
    try:
        if t0 == V3_SWAP_TOPIC0:
            # data: int256 amount0, int256 amount1, uint160 sqrtPriceX96,
            #       uint128 liquidity, int24 tick
            _a0, _a1, sqrtp, liq, tick = _abi_decode(
                ["int256", "int256", "uint160", "uint128", "int24"], b)
            return {"pool": pool, "event": "Swap",
                    "sqrt_p": sqrtx96_to_sqrt_p(sqrtp),
                    "liquidity": float(liq), "tick": int(tick), "block": block}
        if t0 == V3_MINT_TOPIC0:
            # indexed: owner, tickLower, tickUpper ; data: address sender,
            #   uint128 amount, uint256 amount0, uint256 amount1
            _sender, amount, _d0, _d1 = _abi_decode(
                ["address", "uint128", "uint256", "uint256"], b)
            return {"pool": pool, "event": "Mint",
                    "liquidity_delta": float(amount),
                    "tick_lower": _signed_from_topic(topics[2]),
                    "tick_upper": _signed_from_topic(topics[3]), "block": block}
        if t0 == V3_BURN_TOPIC0:
            # indexed: owner, tickLower, tickUpper ; data: uint128 amount,
            #   uint256 amount0, uint256 amount1
            amount, _d0, _d1 = _abi_decode(
                ["uint128", "uint256", "uint256"], b)
            return {"pool": pool, "event": "Burn",
                    "liquidity_delta": -float(amount),
                    "tick_lower": _signed_from_topic(topics[2]),
                    "tick_upper": _signed_from_topic(topics[3]), "block": block}
        if t0 == V3_INIT_TOPIC0:
            sqrtp, tick = _abi_decode(["uint160", "int24"], b)
            return {"pool": pool, "event": "Initialize",
                    "sqrt_p": sqrtx96_to_sqrt_p(sqrtp), "tick": int(tick),
                    "block": block}
    except Exception:  # noqa: BLE001 — decoder never fabricates a value
        return None
    return None


EthCall = Callable[[str, str], Awaitable[Optional[str]]]  # (to, data) -> hex


# ── V3 initial-state bootstrap (real slot0()/liquidity()) ───────────────────
def make_v3_state_initializer(
    eth_call: EthCall,
    *, get_block: Optional[Callable[[], Awaitable[int]]] = None,
):
    """Return ``async init_pool(...) -> PoolState|None`` that reads real V3 state
    from ``slot0()`` + ``liquidity()``. Fail-closed on any malformed/absent read.
    """
    async def init_pool(*, pool_address: str, token0: str, token1: str,
                        fee_bps: int, block: Optional[int] = None,
                        kind: str = "v3") -> Optional[PoolState]:
        s = await eth_call(pool_address, SLOT0_SELECTOR)
        liq_raw = await eth_call(pool_address, LIQUIDITY_SELECTOR)
        if not s or not liq_raw:
            return None
        try:
            decoded = _abi_decode(
                ["uint160", "int24", "uint16", "uint16", "uint16", "uint8",
                 "bool"], _bytes(s))
            sqrtp, tick = int(decoded[0]), int(decoded[1])
            (liq,) = _abi_decode(["uint128"], _bytes(liq_raw))
        except Exception:  # noqa: BLE001
            return None
        if sqrtp <= 0:
            return None
        blk = block
        if blk is None and get_block is not None:
            try:
                blk = await get_block()
            except Exception:  # noqa: BLE001
                blk = 0
        return PoolState(
            pool=pool_address.lower(), kind=kind, token0=token0, token1=token1,
            fee_bps=int(fee_bps), sqrt_p=sqrtx96_to_sqrt_p(sqrtp),
            liquidity=float(liq), tick=tick, block=int(blk or 0))
    return init_pool


# ── V3 on-chain reserves fn (balanceOf) for OnChainReserveTVLProvider ────────
def _balanceof_data(holder: str) -> str:
    return BALANCEOF_SELECTOR + holder.lower().replace("0x", "").rjust(64, "0")


def make_base_v3_reserves_fn(
    eth_call: EthCall,
    pool_meta: Dict[str, tuple],
):
    """Return ``reserves_fn(chain, pool) -> (t0, r0, t1, r1) | None`` that reads
    the pool's REAL token balances via ERC-20 ``balanceOf(pool)`` — the correct
    liquidity basis for a V3 pool (tokens actually locked in the contract).

    ``pool_meta`` maps pool_address(lower) -> (t0_id, t0_addr, dec0, t1_id, t1_addr, dec1),
    where ``t0_id``/``t1_id`` are the identifiers the price_fn expects (symbols).
    Fail-closed on missing meta or malformed reads.
    """
    async def reserves_fn(chain: str, pool: str):
        meta = pool_meta.get((pool or "").lower())
        if meta is None:
            # Runtime-resolved pools (Aerodrome/Slipstream) are written into the
            # canonical registry AFTER this provider was built, so pool_meta —
            # snapshotted at construction — does not know their address. Resolve
            # the token metadata dynamically from the ONE canonical registry so
            # the TVL/reserves path aligns with the runtime-resolved address
            # (single source of truth). Still fail-closed if truly unknown.
            try:
                from ..discovery.base_pool_registry import (
                    canonical_pool_by_address)
                cp = canonical_pool_by_address(pool)
            except Exception:  # noqa: BLE001
                cp = None
            if cp is None:
                return None
            meta = (cp.token0_symbol, cp.token0_address, cp.token0_decimals,
                    cp.token1_symbol, cp.token1_address, cp.token1_decimals)
        t0_id, t0_addr, d0, t1_id, t1_addr, d1 = meta
        raw0 = await eth_call(t0_addr, _balanceof_data(pool))
        raw1 = await eth_call(t1_addr, _balanceof_data(pool))
        if not raw0 or not raw1:
            return None
        try:
            r0 = int(raw0, 16) / (10 ** int(d0))
            r1 = int(raw1, 16) / (10 ** int(d1))
        except (ValueError, TypeError):
            return None
        if r0 <= 0 or r1 <= 0:
            return None
        return (t0_id, r0, t1_id, r1)
    return reserves_fn


def build_pool_meta_for_reserves(pools) -> Dict[str, tuple]:
    """Build the ``pool_meta`` map for ``make_base_v3_reserves_fn`` from canonical
    registry pools that have a resolved address."""
    meta: Dict[str, tuple] = {}
    for p in pools:
        if not p.address:
            continue
        meta[p.address.lower()] = (
            p.token0_symbol, p.token0_address, p.token0_decimals,
            p.token1_symbol, p.token1_address, p.token1_decimals)
    return meta


# ── VPS-only: verify a deterministic UniV3 address via factory getPool ──────
def make_univ3_getpool_verifier(eth_call: EthCall, factory: str):
    """Return ``async verify(token0_addr, token1_addr, fee_ppm) -> address|None``
    that calls the UniV3 factory ``getPool`` (0x1698ee82) — used on the VPS to
    cross-check the CREATE2 addresses against the real chain. Read-only."""
    async def verify(token0_addr: str, token1_addr: str, fee_ppm: int):
        a = token0_addr.lower().replace("0x", "").rjust(64, "0")
        b = token1_addr.lower().replace("0x", "").rjust(64, "0")
        fee = ("%x" % int(fee_ppm)).rjust(64, "0")
        data = "0x1698ee82" + a + b + fee
        raw = await eth_call(factory, data)
        if not raw or len(raw) < 66:
            return None
        addr = "0x" + raw[-40:]
        return addr if int(addr, 16) != 0 else None
    return verify


__all__ = [
    "sqrtx96_to_sqrt_p", "human_price_token1_per_token0",
    "V3_SWAP_TOPIC0", "V3_MINT_TOPIC0", "V3_BURN_TOPIC0", "V3_INIT_TOPIC0",
    "V3_LOG_TOPIC0S", "SLOT0_SELECTOR", "LIQUIDITY_SELECTOR", "BALANCEOF_SELECTOR",
    "decode_v3_log", "make_v3_state_initializer", "make_base_v3_reserves_fn",
    "build_pool_meta_for_reserves", "make_univ3_getpool_verifier",
]
