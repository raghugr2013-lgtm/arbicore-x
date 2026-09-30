"""P0 — Balancer V2 read-only pool discovery + ``queryBatchSwap`` single-swap
quote (fail-closed).

Scope
-----
Given an EXPLICIT pool identity (``pool_id`` bytes32 or ``pool_address``) this
module:

* derives / validates the exact ``pool_id`` (Balancer encodes the pool contract
  address in the first 20 bytes of the id — we verify that invariant),
* reads the pool token set + balances + last-change block from the Vault
  (``getPoolTokens``),
* reads the pool swap fee (``getSwapFeePercentage``) and each token's
  ``decimals()``,
* validates token membership, ordering and liquidity,
* prices a single ``tokenIn -> tokenOut`` swap through the Vault's read-only
  ``queryBatchSwap`` simulation and decodes the signed asset deltas.

Fail-closed contract
--------------------
Every unknown / stale / malformed / illiquid / unsupported / reverting input
yields a DENY result with an explicit status + reason and ``amount_out_wei=0``.
Nothing is ever fabricated or substituted. UNKNOWN NEVER BECOMES ZERO PROFIT:
an unknown quote/liquidity/fee/decimals is a DENY, not a silent 0.

The ``eth_call`` dependency is INJECTED
(``eth_call_fn(to, data) -> (result_hex, block_number, error_dict)``) so this
module is fully unit-testable offline and shares the exact fail-closed JSON-RPC
helper the live quoter already uses. READ-ONLY: no signing, no broadcast, no
state mutation.

NOTE (known P0 limitation): this resolves + prices a pool GIVEN its identity.
Full pool ENUMERATION (discovering every Balancer pool for a token pair) needs
the PoolRegistered event log / subgraph and is intentionally out of P0 scope —
that remains VALIDATION_REQUIRED and must be wired with real evidence later.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Tuple

from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import function_signature_to_4byte_selector, to_checksum_address


# --------------------------------------------------------------------------- #
# Contract catalog                                                            #
# --------------------------------------------------------------------------- #

# Balancer V2 Vault — SAME address on every chain Balancer V2 is deployed on.
# Sourced from (single source of truth) ``execution.calldata`` — a regression
# test asserts these stay identical so the two never drift. BNB Chain is
# intentionally ABSENT (Balancer V2 is not deployed there) → fail closed.
BALANCER_V2_VAULT_BY_CHAIN = {
    "ethereum": to_checksum_address("0xBA12222222228d8Ba445958a75a0704d566BF2C8"),
    "base":     to_checksum_address("0xBA12222222228d8Ba445958a75a0704d566BF2C8"),
    "arbitrum": to_checksum_address("0xBA12222222228d8Ba445958a75a0704d566BF2C8"),
    "optimism": to_checksum_address("0xBA12222222228d8Ba445958a75a0704d566BF2C8"),
    "polygon":  to_checksum_address("0xBA12222222228d8Ba445958a75a0704d566BF2C8"),
}

_ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
GIVEN_IN = 0  # Balancer V2 SwapKind.GIVEN_IN

# Selectors computed once at import.
SEL_GET_POOL_ID       = "0x" + function_signature_to_4byte_selector("getPoolId()").hex()
SEL_GET_POOL_TOKENS   = "0x" + function_signature_to_4byte_selector("getPoolTokens(bytes32)").hex()
SEL_GET_SWAP_FEE      = "0x" + function_signature_to_4byte_selector("getSwapFeePercentage()").hex()
SEL_DECIMALS          = "0x" + function_signature_to_4byte_selector("decimals()").hex()
SEL_QUERY_BATCH_SWAP  = "0x" + function_signature_to_4byte_selector(
    "queryBatchSwap(uint8,(bytes32,uint256,uint256,uint256,bytes)[],address[],(address,bool,address,bool))"
).hex()


# --------------------------------------------------------------------------- #
# Status vocabulary (explicit, auditable)                                     #
# --------------------------------------------------------------------------- #

OK = "ok"
UNSUPPORTED_CHAIN = "unsupported_chain"
MISSING_POOL_IDENTITY = "missing_pool_identity"
RPC_ERROR = "rpc_error"
POOL_REVERT = "pool_revert"
MALFORMED = "malformed"
UNKNOWN_POOL = "unknown_pool"
POOL_ID_MISMATCH = "pool_id_mismatch"
TOKEN_NOT_IN_POOL = "token_not_in_pool"
UNKNOWN_LIQUIDITY = "unknown_liquidity"
INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
UNKNOWN_FEE = "unknown_fee"
UNKNOWN_DECIMALS = "unknown_decimals"
STALE_POOL = "stale_pool"
QUOTE_REVERT = "quote_revert"
NO_OUTPUT = "no_output"

_NO_ADAPTER_STATUSES = {UNSUPPORTED_CHAIN, MISSING_POOL_IDENTITY}
_RPC_STATUSES = {RPC_ERROR}


def hop_status_for(status: str) -> str:
    """Map a discovery/quote DENY status onto the ``HopQuote`` fallback status
    the QuoterRegistry understands."""
    if status in _NO_ADAPTER_STATUSES:
        return "fallback:no_adapter"
    if status in _RPC_STATUSES:
        return "fallback:rpc_error"
    return "fallback:revert"


# --------------------------------------------------------------------------- #
# Data model                                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class BalancerV2Token:
    address: str
    decimals: int
    balance: int


@dataclass(frozen=True)
class BalancerV2PoolMeta:
    chain: str
    vault: str
    pool_id: str            # 0x-prefixed 66-char bytes32
    pool_address: str
    specialization: int
    tokens: List[BalancerV2Token]   # order preserved as returned by getPoolTokens
    swap_fee_1e18: int
    swap_fee_bps: float
    last_change_block: int
    query_block_number: Optional[int]
    resolved_at: str

    def token_index(self, addr: str) -> Optional[int]:
        a = (addr or "").lower()
        for i, t in enumerate(self.tokens):
            if t.address.lower() == a:
                return i
        return None

    def is_stale(self, current_block: Optional[int],
                 max_age_blocks: Optional[int]) -> bool:
        if not current_block or not max_age_blocks:
            return False
        ref = self.query_block_number or self.last_change_block
        if not ref:
            return False
        return (int(current_block) - int(ref)) > int(max_age_blocks)


@dataclass(frozen=True)
class BalancerV2Discovery:
    status: str
    meta: Optional[BalancerV2PoolMeta] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class BalancerV2Quote:
    status: str
    amount_out_wei: int = 0
    deltas: Optional[List[int]] = None
    block_number: Optional[int] = None
    meta: Optional[BalancerV2PoolMeta] = None
    error: Optional[str] = None


EthCallFn = Callable[[str, str], Any]  # async (to, data) -> (result_hex, block, err)


# --------------------------------------------------------------------------- #
# Low-level helpers                                                           #
# --------------------------------------------------------------------------- #

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hexbytes(result_hex: Optional[str]) -> Optional[bytes]:
    if not isinstance(result_hex, str) or not result_hex.startswith("0x"):
        return None
    body = result_hex[2:]
    if len(body) == 0 or len(body) % 2 != 0:
        return None
    try:
        return bytes.fromhex(body)
    except ValueError:
        return None


def _err_kind(err: Optional[dict]) -> Optional[str]:
    """Classify an eth_call error into 'rpc' (transport/rate-limit/node) vs
    'revert' (genuine contract revert)."""
    if not err:
        return None
    if err.get("_transport"):
        return "rpc"
    msg = str(err.get("message", "")).lower()
    code = err.get("code")
    if code == -32016 or "rate limit" in msg or "too many requests" in msg or "429" in msg:
        return "rpc"
    if "revert" in msg or code == 3:
        return "revert"
    return "rpc"


async def _read(eth_call_fn: EthCallFn, to: str,
                data: str) -> Tuple[Optional[str], Optional[int], Optional[dict]]:
    """Invoke the injected eth_call, converting transport exceptions into a
    tagged error dict (never raises)."""
    try:
        res, blk, err = await eth_call_fn(to, data)
        return res, blk, err
    except Exception as exc:  # noqa: BLE001 — fail closed on transport/HTTP errors
        return None, None, {"_transport": True, "message": f"{type(exc).__name__}: {exc}"}


def _normalize_pool_id(pool_id: Any) -> Optional[bytes]:
    if isinstance(pool_id, (bytes, bytearray)):
        b = bytes(pool_id)
    elif isinstance(pool_id, str) and pool_id.startswith("0x"):
        try:
            b = bytes.fromhex(pool_id[2:])
        except ValueError:
            return None
    else:
        return None
    return b if len(b) == 32 else None


def _pool_addr_from_id(pool_id_bytes: bytes) -> str:
    return to_checksum_address(pool_id_bytes[:20])


def _specialization_from_id(pool_id_bytes: bytes) -> int:
    return int.from_bytes(pool_id_bytes[20:22], "big")


# --------------------------------------------------------------------------- #
# Pool discovery                                                              #
# --------------------------------------------------------------------------- #

async def discover_pool(eth_call_fn: EthCallFn, chain: str, *,
                        pool_id: Any = None,
                        pool_address: Optional[str] = None) -> BalancerV2Discovery:
    """Resolve + validate a Balancer V2 pool entirely on-chain, fail-closed."""
    c = (chain or "").strip().lower()
    vault = BALANCER_V2_VAULT_BY_CHAIN.get(c)
    if not vault:
        return BalancerV2Discovery(UNSUPPORTED_CHAIN,
                                   error=f"Balancer V2 not deployed on chain '{chain}'")

    # ---- 1) resolve the exact pool_id + pool_address (no fabrication) -------
    pid_bytes = _normalize_pool_id(pool_id) if pool_id is not None else None
    if pool_id is not None and pid_bytes is None:
        return BalancerV2Discovery(MALFORMED, error="pool_id is not a valid bytes32")

    if pid_bytes is not None:
        derived_addr = _pool_addr_from_id(pid_bytes)
        if pool_address and to_checksum_address(pool_address) != derived_addr:
            return BalancerV2Discovery(
                POOL_ID_MISMATCH,
                error="pool_address does not match the address embedded in pool_id")
        resolved_addr = derived_addr
    elif pool_address:
        try:
            resolved_addr = to_checksum_address(pool_address)
        except Exception:  # noqa: BLE001
            return BalancerV2Discovery(MALFORMED, error="pool_address is not a valid address")
        res, _blk, err = await _read(eth_call_fn, resolved_addr, SEL_GET_POOL_ID)
        kind = _err_kind(err)
        if kind == "rpc":
            return BalancerV2Discovery(RPC_ERROR, error=str(err.get("message")))
        if kind == "revert":
            return BalancerV2Discovery(UNKNOWN_POOL,
                                       error=f"getPoolId reverted: {err.get('message')}")
        raw = _hexbytes(res)
        if raw is None or len(raw) < 32:
            return BalancerV2Discovery(MALFORMED, error="getPoolId returned malformed data")
        try:
            (pid_b,) = abi_decode(["bytes32"], raw)
        except Exception as exc:  # noqa: BLE001
            return BalancerV2Discovery(MALFORMED, error=f"getPoolId decode error: {exc}")
        pid_bytes = pid_b
        if _pool_addr_from_id(pid_bytes) != resolved_addr:
            return BalancerV2Discovery(
                POOL_ID_MISMATCH,
                error="pool_id from getPoolId does not embed the queried pool_address")
    else:
        return BalancerV2Discovery(MISSING_POOL_IDENTITY,
                                   error="either pool_id or pool_address is required")

    pool_id_hex = "0x" + pid_bytes.hex()
    specialization = _specialization_from_id(pid_bytes)

    # ---- 2) Vault.getPoolTokens(pool_id) -> tokens, balances, lastChangeBlk -
    data = SEL_GET_POOL_TOKENS + abi_encode(["bytes32"], [pid_bytes]).hex()
    res, block_number, err = await _read(eth_call_fn, vault, data)
    kind = _err_kind(err)
    if kind == "rpc":
        return BalancerV2Discovery(RPC_ERROR, error=str(err.get("message")))
    if kind == "revert":
        return BalancerV2Discovery(UNKNOWN_POOL,
                                   error=f"getPoolTokens reverted: {err.get('message')}")
    raw = _hexbytes(res)
    if raw is None:
        return BalancerV2Discovery(MALFORMED, error="getPoolTokens returned malformed data")
    try:
        token_addrs, balances, last_change_block = abi_decode(
            ["address[]", "uint256[]", "uint256"], raw)
    except Exception as exc:  # noqa: BLE001
        return BalancerV2Discovery(MALFORMED, error=f"getPoolTokens decode error: {exc}")
    if not token_addrs or len(token_addrs) != len(balances):
        return BalancerV2Discovery(UNKNOWN_POOL,
                                   error="getPoolTokens returned empty / mismatched arrays")

    # ---- 3) pool swap fee (getSwapFeePercentage) ---------------------------
    res, _blk, err = await _read(eth_call_fn, resolved_addr, SEL_GET_SWAP_FEE)
    kind = _err_kind(err)
    if kind == "rpc":
        return BalancerV2Discovery(RPC_ERROR, error=str(err.get("message")))
    if kind == "revert":
        return BalancerV2Discovery(UNKNOWN_FEE,
                                   error=f"getSwapFeePercentage reverted: {err.get('message')}")
    raw = _hexbytes(res)
    if raw is None:
        return BalancerV2Discovery(UNKNOWN_FEE, error="getSwapFeePercentage malformed")
    try:
        (swap_fee_1e18,) = abi_decode(["uint256"], raw)
    except Exception as exc:  # noqa: BLE001
        return BalancerV2Discovery(UNKNOWN_FEE, error=f"swap fee decode error: {exc}")
    if swap_fee_1e18 < 0 or swap_fee_1e18 >= 10 ** 18:
        return BalancerV2Discovery(UNKNOWN_FEE,
                                   error=f"swap fee out of range: {swap_fee_1e18}")
    swap_fee_bps = swap_fee_1e18 / 1e14

    # ---- 4) token decimals for every pool token ----------------------------
    tokens: List[BalancerV2Token] = []
    for addr_raw, bal in zip(token_addrs, balances):
        try:
            addr_cs = to_checksum_address(addr_raw)
        except Exception:  # noqa: BLE001
            return BalancerV2Discovery(MALFORMED, error="pool token is not a valid address")
        res, _blk, err = await _read(eth_call_fn, addr_cs, SEL_DECIMALS)
        kind = _err_kind(err)
        if kind == "rpc":
            return BalancerV2Discovery(RPC_ERROR, error=str(err.get("message")))
        if kind == "revert":
            return BalancerV2Discovery(UNKNOWN_DECIMALS,
                                       error=f"decimals() reverted for {addr_cs}")
        raw = _hexbytes(res)
        if raw is None:
            return BalancerV2Discovery(UNKNOWN_DECIMALS,
                                       error=f"decimals() malformed for {addr_cs}")
        try:
            (dec,) = abi_decode(["uint256"], raw)
        except Exception as exc:  # noqa: BLE001
            return BalancerV2Discovery(UNKNOWN_DECIMALS,
                                       error=f"decimals decode error for {addr_cs}: {exc}")
        if dec <= 0 or dec > 36:
            return BalancerV2Discovery(UNKNOWN_DECIMALS,
                                       error=f"decimals out of range for {addr_cs}: {dec}")
        tokens.append(BalancerV2Token(address=addr_cs, decimals=int(dec), balance=int(bal)))

    meta = BalancerV2PoolMeta(
        chain=c, vault=vault, pool_id=pool_id_hex, pool_address=resolved_addr,
        specialization=specialization, tokens=tokens,
        swap_fee_1e18=int(swap_fee_1e18), swap_fee_bps=swap_fee_bps,
        last_change_block=int(last_change_block),
        query_block_number=block_number, resolved_at=_now_iso(),
    )
    return BalancerV2Discovery(OK, meta=meta)


# --------------------------------------------------------------------------- #
# Single-swap quote via Vault.queryBatchSwap                                  #
# --------------------------------------------------------------------------- #

async def quote_single_swap(eth_call_fn: EthCallFn, meta: BalancerV2PoolMeta,
                            token_in: str, token_out: str, amount_in_wei: int, *,
                            current_block: Optional[int] = None,
                            max_age_blocks: Optional[int] = None) -> BalancerV2Quote:
    """Price a single ``tokenIn -> tokenOut`` swap through the resolved pool,
    fail-closed. The returned amount ALREADY nets the pool swap fee (Balancer's
    ``queryBatchSwap`` applies it); ``meta.swap_fee_bps`` is provenance only and
    must NOT be subtracted again by callers."""
    if int(amount_in_wei) <= 0:
        return BalancerV2Quote(NO_OUTPUT, meta=meta, error="amount_in must be > 0")

    idx_in = meta.token_index(token_in)
    idx_out = meta.token_index(token_out)
    if idx_in is None or idx_out is None or idx_in == idx_out:
        return BalancerV2Quote(TOKEN_NOT_IN_POOL, meta=meta,
                               error="token_in/token_out not both present in pool")

    bal_in = meta.tokens[idx_in].balance
    bal_out = meta.tokens[idx_out].balance
    if bal_in <= 0 or bal_out <= 0:
        return BalancerV2Quote(INSUFFICIENT_LIQUIDITY, meta=meta,
                               error=f"zero pool balance (in={bal_in}, out={bal_out})")

    if meta.is_stale(current_block, max_age_blocks):
        return BalancerV2Quote(STALE_POOL, meta=meta,
                               error="pool state older than max_age_blocks")

    pid_bytes = bytes.fromhex(meta.pool_id[2:])
    ti = to_checksum_address(token_in)
    to_ = to_checksum_address(token_out)
    swaps = [(pid_bytes, 0, 1, int(amount_in_wei), b"")]
    assets = [ti, to_]
    funds = (_ZERO_ADDRESS, False, _ZERO_ADDRESS, False)
    encoded = abi_encode(
        ["uint8", "(bytes32,uint256,uint256,uint256,bytes)[]", "address[]",
         "(address,bool,address,bool)"],
        [GIVEN_IN, swaps, assets, funds],
    )
    data = SEL_QUERY_BATCH_SWAP + encoded.hex()

    res, block_number, err = await _read(eth_call_fn, meta.vault, data)
    kind = _err_kind(err)
    if kind == "rpc":
        return BalancerV2Quote(RPC_ERROR, meta=meta, error=str(err.get("message")))
    if kind == "revert":
        return BalancerV2Quote(QUOTE_REVERT, meta=meta,
                               error=f"queryBatchSwap reverted: {err.get('message')}")
    raw = _hexbytes(res)
    if raw is None:
        return BalancerV2Quote(MALFORMED, meta=meta, error="queryBatchSwap malformed data")
    try:
        (deltas,) = abi_decode(["int256[]"], raw)
    except Exception as exc:  # noqa: BLE001
        return BalancerV2Quote(MALFORMED, meta=meta, error=f"deltas decode error: {exc}")
    if not deltas or len(deltas) < 2:
        return BalancerV2Quote(MALFORMED, meta=meta, error="queryBatchSwap returned < 2 deltas")

    # assets = [tokenIn, tokenOut] → deltas[0] = +amountIn, deltas[1] = -amountOut
    amount_out = -int(deltas[1])
    if amount_out <= 0:
        return BalancerV2Quote(NO_OUTPUT, deltas=[int(d) for d in deltas], meta=meta,
                               block_number=block_number, error="non-positive amount_out")
    if amount_out >= bal_out:
        return BalancerV2Quote(INSUFFICIENT_LIQUIDITY, deltas=[int(d) for d in deltas],
                               meta=meta, block_number=block_number,
                               error=f"amount_out {amount_out} >= pool balance {bal_out}")

    return BalancerV2Quote(OK, amount_out_wei=amount_out,
                           deltas=[int(d) for d in deltas], meta=meta,
                           block_number=block_number)


async def discover_and_quote(eth_call_fn: EthCallFn, chain: str,
                             token_in: str, token_out: str, amount_in_wei: int, *,
                             pool_id: Any = None, pool_address: Optional[str] = None,
                             current_block: Optional[int] = None,
                             max_age_blocks: Optional[int] = None) -> BalancerV2Quote:
    """Convenience: discover the pool then price the swap. On discovery failure
    the discovery status is surfaced verbatim (fail-closed)."""
    disc = await discover_pool(eth_call_fn, chain, pool_id=pool_id,
                               pool_address=pool_address)
    if disc.status != OK or disc.meta is None:
        return BalancerV2Quote(disc.status, meta=disc.meta, error=disc.error)
    return await quote_single_swap(eth_call_fn, disc.meta, token_in, token_out,
                                   int(amount_in_wei), current_block=current_block,
                                   max_age_blocks=max_age_blocks)
