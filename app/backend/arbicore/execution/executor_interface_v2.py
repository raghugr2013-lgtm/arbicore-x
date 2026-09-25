"""Executor V2 canonical ABI — SINGLE SOURCE OF TRUTH (backend side).

Mirrors ``contracts/contracts/interfaces/IExecutorV2.sol`` + ``IV2Routers.sol``
(Interface Freeze v1.1). This module is ADDITIVE — it does NOT modify or import
the V1 ``executor_interface.py``; the V1 surface stays byte-for-byte intact.

It is pure metadata + deterministic selectors. It performs NO network I/O, NEVER
signs or broadcasts, and grants NO execution authority. A capability listed here
becomes executable only after a verified V2 receiver is DEPLOYED and reconciled
(see ``receiver_capability`` + ``settlement_dispatcher``).
"""
from __future__ import annotations

import enum
from typing import Dict

from eth_utils import keccak


def selector(sig: str) -> str:
    return "0x" + keccak(text=sig)[:4].hex()


# --- Version tag ------------------------------------------------------------ #
RECEIVER_VERSION_V2 = "v2"

# --- Flash-head entrypoint selectors --------------------------------------- #
# execute/executeAave are PRESERVED identical to V1; executeMorpho is new.
ENTRY_BALANCER_SIG = "execute(address[],uint256[],bytes)"          # 0x64ba4bc1
ENTRY_AAVE_SIG     = "executeAave(address,uint256,bytes)"          # 0x4343d8b2
ENTRY_MORPHO_SIG   = "executeMorpho(address,uint256,bytes)"        # new

SEL_ENTRY_BALANCER = selector(ENTRY_BALANCER_SIG)
SEL_ENTRY_AAVE     = selector(ENTRY_AAVE_SIG)
SEL_ENTRY_MORPHO   = selector(ENTRY_MORPHO_SIG)

# --- Provider-pinned callback selectors ------------------------------------ #
SEL_CB_BALANCER = selector("receiveFlashLoan(address[],uint256[],uint256[],bytes)")
SEL_CB_AAVE     = selector("executeOperation(address,uint256,uint256,address,bytes)")
SEL_CB_MORPHO   = selector("onMorphoFlashLoan(uint256,bytes)")     # 0x31f57072 (canonical)

SEL_RECEIVER_VERSION = selector("receiverVersion()")


class VenueV2(enum.IntEnum):
    """On-chain ABI-family discriminator — MUST match the Solidity enum order."""
    UNISWAP_V3 = 0
    UNISWAP_V2 = 1
    AERODROME_CLASSIC = 2
    AERODROME_SLIPSTREAM = 3
    ALGEBRA_V3 = 4


# Backend venue identifier -> on-chain ABI family (Freeze v1.1 §A.2).
BACKEND_VENUE_TO_FAMILY: Dict[str, VenueV2] = {
    "uniswap_v3": VenueV2.UNISWAP_V3,
    "sushiswap_v3": VenueV2.UNISWAP_V3,        # UniV3-compatible fork
    "pancakeswap_v3": VenueV2.UNISWAP_V3,      # UniV3-compatible fork (OUT OF SCOPE)
    "uniswap_v2": VenueV2.UNISWAP_V2,
    "sushiswap_v2": VenueV2.UNISWAP_V2,
    "aerodrome": VenueV2.AERODROME_CLASSIC,
    "aerodrome_slipstream": VenueV2.AERODROME_SLIPSTREAM,
    "camelot_v3": VenueV2.ALGEBRA_V3,          # OUT OF SCOPE
    "quickswap_v3": VenueV2.ALGEBRA_V3,        # OUT OF SCOPE
}

# V2 flash heads the deployed receiver exposes.
V2_FLASH_HEADS = frozenset({"balancer_v2", "aave_v3", "morpho_blue"})

# --- Initial certified scope (Freeze v1.1 §B) ------------------------------ #
# Chain id -> (flash providers, swap venues) the INITIAL certified V2 deployment
# is authorised to claim. Anything outside this is fail-closed (out of scope),
# regardless of adapter presence in the backend.
V2_INITIAL_SCOPE: Dict[int, Dict[str, frozenset]] = {
    8453: {  # Base mainnet
        "providers": frozenset({"balancer_v2", "aave_v3", "morpho_blue"}),
        "venues": frozenset({"uniswap_v3", "aerodrome", "aerodrome_slipstream"}),
    },
    1: {  # Ethereum mainnet
        "providers": frozenset({"balancer_v2", "aave_v3", "morpho_blue"}),
        "venues": frozenset({"uniswap_v3", "sushiswap_v2", "sushiswap_v3"}),
    },
    84532: {  # Base Sepolia — staging/pre-flight only
        "providers": frozenset({"aave_v3", "morpho_blue"}),
        "venues": frozenset({"uniswap_v3"}),
    },
}

# Chains explicitly OUT OF SCOPE for the initial V2 deployment (fail-closed).
V2_OUT_OF_SCOPE_CHAINS = frozenset({42161, 10, 137, 56})  # Arbitrum, Optimism, Polygon, BNB

# userData schema tag (all three heads):
#   abi.encode(SwapHopV2[] hops, address profitRecipient, uint256 minProfit, uint256 deadline)
USERDATA_SCHEMA_V2 = (
    "abi.encode(SwapHopV2[] hops, address profitRecipient, uint256 minProfit, "
    "uint256 deadline) where SwapHopV2=(uint8 venue,address router,address tokenIn,"
    "address tokenOut,uint24 feeOrTickSpacing,bool stable,address factory,"
    "uint256 amountIn,uint256 amountOutMinimum,uint160 sqrtPriceLimitX96,uint256 deadline)"
)


def family_for_backend_venue(venue: str) -> VenueV2:
    """Map a backend venue id to its on-chain ABI family (fail-closed)."""
    v = (venue or "").strip().lower()
    if v not in BACKEND_VENUE_TO_FAMILY:
        raise ValueError(f"no V2 ABI family for backend venue '{venue}'")
    return BACKEND_VENUE_TO_FAMILY[v]


def in_initial_scope(chain_id: int, *, provider: str = None, venue: str = None) -> bool:
    """True only when (chain, provider/venue) is in the INITIAL certified V2
    scope. Fail-closed for out-of-scope chains and unlisted providers/venues."""
    scope = V2_INITIAL_SCOPE.get(int(chain_id))
    if scope is None:
        return False
    if provider is not None and provider.strip().lower() not in scope["providers"]:
        return False
    if venue is not None and venue.strip().lower() not in scope["venues"]:
        return False
    return True


__all__ = [
    "selector", "RECEIVER_VERSION_V2",
    "SEL_ENTRY_BALANCER", "SEL_ENTRY_AAVE", "SEL_ENTRY_MORPHO",
    "SEL_CB_BALANCER", "SEL_CB_AAVE", "SEL_CB_MORPHO", "SEL_RECEIVER_VERSION",
    "ENTRY_BALANCER_SIG", "ENTRY_AAVE_SIG", "ENTRY_MORPHO_SIG",
    "VenueV2", "BACKEND_VENUE_TO_FAMILY", "V2_FLASH_HEADS",
    "V2_INITIAL_SCOPE", "V2_OUT_OF_SCOPE_CHAINS", "USERDATA_SCHEMA_V2",
    "family_for_backend_venue", "in_initial_scope",
]
