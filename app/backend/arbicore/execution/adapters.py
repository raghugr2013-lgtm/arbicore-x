"""Wave 6B · Provider adapters — flash-loan providers + DEX routers.

Adapter protocols keep provider-specific logic isolated:

    FlashLoanAdapter — knows the ``flashLoan(...)`` ABI, borrow-fee
                        schedule, and the borrow / repay leg pair for
                        a single provider.
    DexAdapter       — knows the ``exactInputSingle(...)`` /
                        ``swap(...)`` ABI for a single DEX family.

Every adapter exposes a ``version`` (semantic tag) so persisted plans
record which adapter revision produced them — future adapter upgrades
can bump the version without touching business logic.

Wave 6B ships:
    * Flash-loan: Aave V3, Balancer V2, Uniswap V3 (per canonical
      ``FLASH_LOAN_PROVIDERS`` catalog).
    * DEX: Uniswap V3, Aerodrome (Base-native).

Base-chain contract addresses:  Uniswap V3 Router 02 and Aerodrome
Router 02 constants are inlined here as the operator-locked defaults;
they may be overridden via env for staging.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Protocol


# ---------------------------------------------------------------------------
# Address book (Base first; other chains added incrementally)
# ---------------------------------------------------------------------------

ADDRESS_BOOK: Dict[str, Dict[str, str]] = {
    "base": {
        # Flash-loan pool addresses (operator-locked defaults).
        "aave_v3_pool":     os.environ.get("BASE_AAVE_V3_POOL",     "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"),
        "balancer_v2_vault":os.environ.get("BASE_BALANCER_V2_VAULT","0xBA12222222228d8Ba445958a75a0704d566BF2C8"),
        # DEX routers.
        "uniswap_v3_router":os.environ.get("BASE_UNIV3_ROUTER",     "0x2626664c2603336E57B271c5C0b26F421741e481"),
        "aerodrome_router": os.environ.get("BASE_AERODROME_ROUTER", "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"),
    },
}


def _addr(chain: str, key: str) -> Optional[str]:
    return ADDRESS_BOOK.get(chain, {}).get(key)


# ---------------------------------------------------------------------------
# Adapter protocols
# ---------------------------------------------------------------------------

class FlashLoanAdapter(Protocol):
    provider: str
    version: str
    fee_bps_default: int

    def supports(self, chain: str) -> bool: ...

    def borrow_step(self, *, chain: str, asset: str, amount_wei: int,
                    step_index: int, callback_receiver: str,
                    callback_data: bytes = b"") -> Dict[str, Any]: ...

    def repay_step(self, *, chain: str, asset: str, amount_wei: int,
                   fee_bps: Optional[int], step_index: int,
                   depends_on: List[int]) -> Dict[str, Any]: ...


class DexAdapter(Protocol):
    dex: str
    version: str

    def supports(self, chain: str) -> bool: ...

    def swap_step(self, *, chain: str, token_in: str, token_out: str,
                  amount_in_wei: int, min_amount_out_wei: int,
                  step_index: int, depends_on: List[int],
                  fee_tier_bps: Optional[int] = None) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Flash-loan adapters
# ---------------------------------------------------------------------------

class AaveV3FlashLoanAdapter:
    provider = "aave_v3"
    version = "aave_v3_flashloan@1"
    fee_bps_default = 5
    supports_chains = ("ethereum", "arbitrum", "base", "optimism", "polygon")

    def supports(self, chain: str) -> bool:
        return chain in self.supports_chains

    def borrow_step(self, *, chain: str, asset: str, amount_wei: int,
                    step_index: int, callback_receiver: str,
                    callback_data: bytes = b"") -> Dict[str, Any]:
        return {
            "step_index": step_index,
            "kind": "borrow",
            "provider": self.provider,
            "chain": chain,
            "contract_address": _addr(chain, "aave_v3_pool"),
            "function_signature": "flashLoanSimple(address,address,uint256,bytes,uint16)",
            "args": [callback_receiver, asset, amount_wei,
                     callback_data.hex() if callback_data else "0x", 0],
            "value_wei": 0,
            "depends_on": [],
            "notes": "Aave V3 flashLoanSimple — 5 bps premium",
        }

    def repay_step(self, *, chain: str, asset: str, amount_wei: int,
                   fee_bps: Optional[int], step_index: int,
                   depends_on: List[int]) -> Dict[str, Any]:
        premium_bps = int(fee_bps if fee_bps is not None else self.fee_bps_default)
        premium_wei = (amount_wei * premium_bps) // 10_000
        return {
            "step_index": step_index,
            "kind": "repay",
            "provider": self.provider,
            "chain": chain,
            "contract_address": _addr(chain, "aave_v3_pool"),
            "function_signature": "__aave_v3_repay_within_flashloan_callback",
            "args": [asset, amount_wei, premium_wei],
            "value_wei": 0,
            "depends_on": list(depends_on),
            "notes": f"Aave V3 repay = principal + {premium_bps} bps premium",
        }


class BalancerV2FlashLoanAdapter:
    provider = "balancer_v2"
    version = "balancer_v2_flashloan@1"
    fee_bps_default = 0
    supports_chains = ("ethereum", "arbitrum", "base", "optimism", "polygon")

    def supports(self, chain: str) -> bool:
        return chain in self.supports_chains

    def borrow_step(self, *, chain: str, asset: str, amount_wei: int,
                    step_index: int, callback_receiver: str,
                    callback_data: bytes = b"") -> Dict[str, Any]:
        return {
            "step_index": step_index,
            "kind": "borrow",
            "provider": self.provider,
            "chain": chain,
            "contract_address": _addr(chain, "balancer_v2_vault"),
            "function_signature": "flashLoan(address,address[],uint256[],bytes)",
            "args": [callback_receiver, [asset], [amount_wei],
                     callback_data.hex() if callback_data else "0x"],
            "value_wei": 0,
            "depends_on": [],
            "notes": "Balancer V2 vault flashLoan — 0 bps premium",
        }

    def repay_step(self, *, chain: str, asset: str, amount_wei: int,
                   fee_bps: Optional[int], step_index: int,
                   depends_on: List[int]) -> Dict[str, Any]:
        return {
            "step_index": step_index,
            "kind": "repay",
            "provider": self.provider,
            "chain": chain,
            "contract_address": _addr(chain, "balancer_v2_vault"),
            "function_signature": "__balancer_v2_repay_within_flashloan_callback",
            "args": [asset, amount_wei, 0],
            "value_wei": 0,
            "depends_on": list(depends_on),
            "notes": "Balancer V2 repay = principal exactly (0 bps premium)",
        }


class UniswapV3FlashLoanAdapter:
    """Uniswap V3 flash-loan repayment fee = pool swap-fee tier (5 / 30 / 100 bps)."""
    provider = "uniswap_v3"
    version = "uniswap_v3_flashloan@1"
    fee_bps_default = 30
    supports_chains = ("ethereum", "arbitrum", "base", "optimism", "polygon")

    def supports(self, chain: str) -> bool:
        return chain in self.supports_chains

    def borrow_step(self, *, chain: str, asset: str, amount_wei: int,
                    step_index: int, callback_receiver: str,
                    callback_data: bytes = b"") -> Dict[str, Any]:
        return {
            "step_index": step_index,
            "kind": "borrow",
            "provider": self.provider,
            "chain": chain,
            # UniV3 flash is invoked on the pool itself; address is resolved
            # by the caller from the actual borrow-pool address.
            "contract_address": None,
            "function_signature": "flash(address,uint256,uint256,bytes)",
            "args": [callback_receiver, amount_wei, 0,
                     callback_data.hex() if callback_data else "0x"],
            "value_wei": 0,
            "depends_on": [],
            "notes": "Uniswap V3 flash — fee = pool tier (caller resolves)",
        }

    def repay_step(self, *, chain: str, asset: str, amount_wei: int,
                   fee_bps: Optional[int], step_index: int,
                   depends_on: List[int]) -> Dict[str, Any]:
        premium_bps = int(fee_bps if fee_bps is not None else self.fee_bps_default)
        premium_wei = (amount_wei * premium_bps) // 10_000
        return {
            "step_index": step_index,
            "kind": "repay",
            "provider": self.provider,
            "chain": chain,
            "contract_address": None,
            "function_signature": "__uniswap_v3_repay_within_flashloan_callback",
            "args": [asset, amount_wei, premium_wei],
            "value_wei": 0,
            "depends_on": list(depends_on),
            "notes": f"Uniswap V3 repay = principal + {premium_bps} bps pool-tier premium",
        }


# ---------------------------------------------------------------------------
# DEX adapters
# ---------------------------------------------------------------------------

class UniswapV3SwapAdapter:
    dex = "uniswap_v3"
    version = "uniswap_v3_swap@1"
    supports_chains = ("ethereum", "arbitrum", "base", "optimism", "polygon")

    def supports(self, chain: str) -> bool:
        return chain in self.supports_chains

    def swap_step(self, *, chain: str, token_in: str, token_out: str,
                  amount_in_wei: int, min_amount_out_wei: int,
                  step_index: int, depends_on: List[int],
                  fee_tier_bps: Optional[int] = None) -> Dict[str, Any]:
        tier = int(fee_tier_bps if fee_tier_bps is not None else 30)
        return {
            "step_index": step_index,
            "kind": "swap",
            "provider": self.dex,
            "chain": chain,
            "contract_address": _addr(chain, "uniswap_v3_router"),
            "function_signature": (
                "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))"
            ),
            "args": [{
                "tokenIn": token_in,
                "tokenOut": token_out,
                "fee": tier * 100,   # UniV3 fee tier is expressed in hundredths of a bps
                "recipient": "__signer_wallet__",   # resolved by Wave-6D signer
                "amountIn": amount_in_wei,
                "amountOutMinimum": min_amount_out_wei,
                "sqrtPriceLimitX96": 0,
            }],
            "value_wei": 0,
            "depends_on": list(depends_on),
            "notes": f"Uniswap V3 exactInputSingle (fee tier {tier} bps)",
        }


class AerodromeSwapAdapter:
    dex = "aerodrome"
    version = "aerodrome_swap@1"
    supports_chains = ("base",)  # Base-native

    def supports(self, chain: str) -> bool:
        return chain in self.supports_chains

    def swap_step(self, *, chain: str, token_in: str, token_out: str,
                  amount_in_wei: int, min_amount_out_wei: int,
                  step_index: int, depends_on: List[int],
                  fee_tier_bps: Optional[int] = None) -> Dict[str, Any]:
        return {
            "step_index": step_index,
            "kind": "swap",
            "provider": self.dex,
            "chain": chain,
            "contract_address": _addr(chain, "aerodrome_router"),
            "function_signature": (
                "swapExactTokensForTokens(uint256,uint256,(address,address,bool,address)[],address,uint256)"
            ),
            "args": [
                amount_in_wei, min_amount_out_wei,
                [(token_in, token_out, False, "__factory__")],   # stable=False; caller can override
                "__signer_wallet__",
                # deadline = block.timestamp + 300 (resolved at broadcast; symbolic here).
                "__deadline_plus_5m__",
            ],
            "value_wei": 0,
            "depends_on": list(depends_on),
            "notes": "Aerodrome swapExactTokensForTokens (single hop, volatile)",
        }


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

_DEFAULT_FLASH: Dict[str, Any] = {
    "aave_v3": AaveV3FlashLoanAdapter(),
    "balancer_v2": BalancerV2FlashLoanAdapter(),
    "uniswap_v3": UniswapV3FlashLoanAdapter(),
}
_DEFAULT_DEX: Dict[str, Any] = {
    "uniswap_v3": UniswapV3SwapAdapter(),
    "aerodrome": AerodromeSwapAdapter(),
}


class AdapterRegistry:
    def __init__(self,
                 flash_adapters: Optional[Dict[str, FlashLoanAdapter]] = None,
                 dex_adapters: Optional[Dict[str, DexAdapter]] = None):
        self._flash: Dict[str, FlashLoanAdapter] = dict(flash_adapters or _DEFAULT_FLASH)
        self._dex: Dict[str, DexAdapter] = dict(dex_adapters or _DEFAULT_DEX)

    def flash(self, provider: str) -> FlashLoanAdapter:
        try:
            return self._flash[provider]
        except KeyError:
            raise ValueError(
                f"unknown flash-loan provider '{provider}'; "
                f"available: {sorted(self._flash.keys())}"
            )

    def dex(self, provider: str) -> DexAdapter:
        try:
            return self._dex[provider]
        except KeyError:
            raise ValueError(
                f"unknown DEX provider '{provider}'; "
                f"available: {sorted(self._dex.keys())}"
            )

    def register_flash(self, adapter: FlashLoanAdapter) -> None:
        self._flash[adapter.provider] = adapter

    def register_dex(self, adapter: DexAdapter) -> None:
        self._dex[adapter.dex] = adapter

    def catalog(self) -> Dict[str, Any]:
        return {
            "flash_loan_providers": [
                {"provider": a.provider, "version": a.version,
                 "fee_bps_default": a.fee_bps_default,
                 "supports_chains": list(getattr(a, "supports_chains", ()))}
                for a in self._flash.values()
            ],
            "dex_providers": [
                {"dex": a.dex, "version": a.version,
                 "supports_chains": list(getattr(a, "supports_chains", ()))}
                for a in self._dex.values()
            ],
            "address_book": {chain: dict(book) for chain, book in ADDRESS_BOOK.items()},
        }
