"""Phase-2 Step 2 · Real on-chain flash-loan provider liquidity + feasibility.

Reads ACTUAL on-chain liquidity for supported flash-loan providers so the
optimizer stops assuming capacity just because a provider is configured.

Providers:
  * Balancer V2 — flash loans are served from the singleton Vault
    (0xBA12222222228d8Ba445958a75a0704d566BF2C8, same address on ETH/Arb/OP/
    Polygon; NOT deployed on BNB). Available token liquidity ≈ ERC20.balanceOf
    (Vault). Balancer V2 flash fee is a genuine, config-VERIFIED 0 bps.
  * Aave V3 — flash-loanable liquidity of a reserve ≈ underlying ERC20.balanceOf
    (aToken). The aToken address is read from Pool.getReserveData(asset). Fee is
    a real, on-chain-readable premium (default ~5 bps).

Status ladder (never assume capacity):
    CONFIGURED          provider is in the catalog for this chain
    AVAILABLE           the provider contract exists on-chain (has code)
    ON_CHAIN_CONFIRMED  a real token balance was read AND ≥ the borrow amount
    UNAVAILABLE         contract missing, or confirmed liquidity < borrow
    UNKNOWN             read failed / no RPC ⇒ FAIL-CLOSED (never treated feasible)

Pure decoding helpers are offline-testable; live reads use ``EthJsonRpcProvider``.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from eth_utils import function_signature_to_4byte_selector


class ProviderStatus(str, enum.Enum):
    CONFIGURED = "CONFIGURED"
    AVAILABLE = "AVAILABLE"
    ON_CHAIN_CONFIRMED = "ON_CHAIN_CONFIRMED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


# Balancer V2 Vault — identical address on every EVM deployment (not on BNB).
BALANCER_V2_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"

# Aave V3 Pool per chain (public, verifiable).
AAVE_V3_POOL: Dict[str, str] = {
    "ethereum": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    "arbitrum": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "optimism": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "polygon": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "base": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    "bnb": "0x6807dc923806fE8Fd134338EABCA509979a7e0cB",
}


def _sel(sig: str) -> str:
    return "0x" + function_signature_to_4byte_selector(sig).hex()


SEL_BALANCE_OF = _sel("balanceOf(address)")
SEL_DECIMALS = _sel("decimals()")
SEL_GET_RESERVE_DATA = _sel("getReserveData(address)")


def _addr_arg(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


def _to_int(raw: Optional[str]) -> Optional[int]:
    if not raw or raw in ("0x", "0x0"):
        return None if raw in (None, "0x") else 0
    try:
        return int(raw, 16)
    except (TypeError, ValueError):
        return None


def decode_atoken_from_reserve_data(raw: str) -> Optional[str]:
    """Extract the aTokenAddress (9th 32-byte word) from Aave V3 getReserveData.

    Aave V3 ReserveData ABI order: configuration, liquidityIndex,
    currentLiquidityRate, variableBorrowIndex, currentVariableBorrowRate,
    currentStableBorrowRate, lastUpdateTimestamp, id, **aTokenAddress**, ...
    ⇒ word index 8 (0-based). Returns a 0x address or None (fail-closed).
    """
    if not raw or not raw.startswith("0x"):
        return None
    body = raw[2:]
    word = body[8 * 64:9 * 64]
    if len(word) < 64:
        return None
    addr = "0x" + word[-40:]
    if int(addr, 16) == 0:
        return None
    return addr


@dataclass
class ProviderLiquidity:
    provider: str
    chain: str
    status: ProviderStatus
    fee_bps: Optional[int] = None
    liquidity_tokens: Optional[float] = None       # underlying token units
    liquidity_usd: Optional[float] = None
    source_address: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider, "chain": self.chain,
            "status": self.status.value, "fee_bps": self.fee_bps,
            "liquidity_tokens": self.liquidity_tokens,
            "liquidity_usd": self.liquidity_usd,
            "source_address": self.source_address, "reason": self.reason,
        }

    @property
    def feasible_usd(self) -> Optional[float]:
        """USD liquidity ONLY when on-chain confirmed; else None (fail-closed)."""
        return (self.liquidity_usd
                if self.status == ProviderStatus.ON_CHAIN_CONFIRMED else None)


async def _has_code(provider, address: str) -> Optional[bool]:
    try:
        code = await provider._call("eth_getCode", [address, "latest"])
    except Exception:  # noqa: BLE001
        return None
    if code is None:
        return None
    return len(code.replace("0x", "")) > 0


async def _erc20_balance(provider, token: str, holder: str) -> Optional[int]:
    try:
        raw = await provider.eth_call(
            {"to": token, "data": SEL_BALANCE_OF + _addr_arg(holder)})
    except Exception:  # noqa: BLE001
        return None
    return _to_int(raw)


async def read_balancer_liquidity(
    provider, *, chain: str, token_address: str, token_decimals: int,
    token_price_usd: Optional[float], borrow_amount_usd: Optional[float],
    fee_bps: int = 0,
) -> ProviderLiquidity:
    r = ProviderLiquidity(provider="balancer_v2", chain=chain,
                          status=ProviderStatus.CONFIGURED, fee_bps=fee_bps,
                          source_address=BALANCER_V2_VAULT)
    has = await _has_code(provider, BALANCER_V2_VAULT)
    if has is None:
        r.status = ProviderStatus.UNKNOWN
        r.reason = "vault_code_read_failed"
        return r
    if not has:
        r.status = ProviderStatus.UNAVAILABLE
        r.reason = "vault_not_deployed_on_chain"
        return r
    r.status = ProviderStatus.AVAILABLE
    bal = await _erc20_balance(provider, token_address, BALANCER_V2_VAULT)
    if bal is None:
        r.status = ProviderStatus.UNKNOWN
        r.reason = "balance_read_failed"
        return r
    r.liquidity_tokens = bal / (10 ** token_decimals)
    if token_price_usd is not None and token_price_usd > 0:
        r.liquidity_usd = r.liquidity_tokens * token_price_usd
    _finalise(r, borrow_amount_usd)
    return r


async def read_aave_liquidity(
    provider, *, chain: str, token_address: str, token_decimals: int,
    token_price_usd: Optional[float], borrow_amount_usd: Optional[float],
    fee_bps: int = 5,
) -> ProviderLiquidity:
    pool = AAVE_V3_POOL.get(chain)
    r = ProviderLiquidity(provider="aave_v3", chain=chain,
                          status=ProviderStatus.CONFIGURED, fee_bps=fee_bps,
                          source_address=pool)
    if not pool:
        r.status = ProviderStatus.UNAVAILABLE
        r.reason = "no_aave_pool_for_chain"
        return r
    has = await _has_code(provider, pool)
    if has is None:
        r.status = ProviderStatus.UNKNOWN
        r.reason = "pool_code_read_failed"
        return r
    if not has:
        r.status = ProviderStatus.UNAVAILABLE
        r.reason = "pool_not_deployed_on_chain"
        return r
    r.status = ProviderStatus.AVAILABLE
    try:
        raw = await provider.eth_call(
            {"to": pool, "data": SEL_GET_RESERVE_DATA + _addr_arg(token_address)})
    except Exception:  # noqa: BLE001
        r.status = ProviderStatus.UNKNOWN
        r.reason = "get_reserve_data_failed"
        return r
    atoken = decode_atoken_from_reserve_data(raw or "")
    if not atoken:
        r.status = ProviderStatus.UNAVAILABLE
        r.reason = "reserve_not_listed"
        return r
    r.source_address = atoken
    bal = await _erc20_balance(provider, token_address, atoken)
    if bal is None:
        r.status = ProviderStatus.UNKNOWN
        r.reason = "atoken_balance_read_failed"
        return r
    r.liquidity_tokens = bal / (10 ** token_decimals)
    if token_price_usd is not None and token_price_usd > 0:
        r.liquidity_usd = r.liquidity_tokens * token_price_usd
    _finalise(r, borrow_amount_usd)
    return r


def _finalise(r: ProviderLiquidity, borrow_amount_usd: Optional[float]) -> None:
    if r.liquidity_usd is None:
        # We have a token balance but no USD price to contextualise it.
        r.status = ProviderStatus.UNKNOWN
        r.reason = "token_price_unavailable"
        return
    if borrow_amount_usd is not None and r.liquidity_usd < float(borrow_amount_usd):
        r.status = ProviderStatus.UNAVAILABLE
        r.reason = "insufficient_liquidity"
    else:
        r.status = ProviderStatus.ON_CHAIN_CONFIRMED
        r.reason = "confirmed"


__all__ = [
    "ProviderStatus", "ProviderLiquidity",
    "BALANCER_V2_VAULT", "AAVE_V3_POOL",
    "read_balancer_liquidity", "read_aave_liquidity",
    "decode_atoken_from_reserve_data",
    "SEL_BALANCE_OF", "SEL_GET_RESERVE_DATA",
]
