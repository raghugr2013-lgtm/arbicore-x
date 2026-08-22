"""Canonical deployed-executor interface — SINGLE SOURCE OF TRUTH.

The deployed FlashLoanReceiver on Base (Balancer V2 flash loan + Uniswap V3
swaps) exposes exactly these public getters and entrypoint. Every executor
verification path — the operator wizard, fork validation, execution-capability
checks and atomic simulation — MUST read this module instead of hard-coding its
own selectors. This prevents the historical drift where the wizard probed
``balancerVault()/uniRouter()/aavePool()`` while the contract actually exposes
``VAULT()/ROUTER()`` (and no aavePool()), which BLOCKED executor_verified
despite a correctly deployed contract.

Verified against the recovered bytecode selector map in
``executor_entrypoint._KNOWN_SELECTORS`` and ``contracts/.../FlashLoanReceiver.sol``.
"""
from __future__ import annotations

from eth_utils import keccak


def selector(sig: str) -> str:
    """0x-prefixed 4-byte function selector for a Solidity signature."""
    return "0x" + keccak(text=sig)[:4].hex()


# --- Public getters actually present on the deployed executor -------------- #
GETTER_VAULT_SIG = "VAULT()"      # 0x411557d1  → Balancer V2 Vault
GETTER_ROUTER_SIG = "ROUTER()"    # 0x32fe7b26  → Uniswap V3 SwapRouter02
GETTER_OWNER_SIG = "owner()"      # 0x8da5cb5b

SEL_VAULT = selector(GETTER_VAULT_SIG)
SEL_ROUTER = selector(GETTER_ROUTER_SIG)
SEL_OWNER = selector(GETTER_OWNER_SIG)

# --- Entrypoint ------------------------------------------------------------ #
ENTRYPOINT_SIG = "execute(address[],uint256[],bytes)"   # 0x64ba4bc1
ENTRYPOINT_SELECTOR = selector(ENTRYPOINT_SIG)
USERDATA_SCHEMA = (
    "abi.encode(SwapHop[] hops, address profitRecipient) where "
    "SwapHop=(address tokenIn,address tokenOut,uint24 feePpm,uint256 amountIn,"
    "uint256 amountOutMinimum,uint160 sqrtPriceLimitX96)"
)

# --- Chain ids ------------------------------------------------------------- #
BASE_MAINNET_ID = 8453
BASE_SEPOLIA_ID = 84532

# --- Expected venue addresses the executor's getters must return ----------- #
EXPECTED_VAULT_BY_ID = {
    BASE_MAINNET_ID: "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    BASE_SEPOLIA_ID: "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
}
EXPECTED_ROUTER_BY_ID = {
    BASE_MAINNET_ID: "0x2626664c2603336E57B271c5C0b26F421741e481",
    BASE_SEPOLIA_ID: "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4",
}

# The deployed head is Balancer V2 + Uniswap V3. Aave is NOT part of this head;
# aavePool() is intentionally NOT a verification requirement.
FLASH_PROVIDER = "balancer_v2"
SWAP_VENUE = "uniswap_v3"

__all__ = [
    "selector", "SEL_VAULT", "SEL_ROUTER", "SEL_OWNER",
    "GETTER_VAULT_SIG", "GETTER_ROUTER_SIG", "GETTER_OWNER_SIG",
    "ENTRYPOINT_SIG", "ENTRYPOINT_SELECTOR", "USERDATA_SCHEMA",
    "BASE_MAINNET_ID", "BASE_SEPOLIA_ID",
    "EXPECTED_VAULT_BY_ID", "EXPECTED_ROUTER_BY_ID",
    "FLASH_PROVIDER", "SWAP_VENUE",
]
