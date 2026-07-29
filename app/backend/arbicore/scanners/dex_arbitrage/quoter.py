"""ArbiCore X — Phase D D-3.1 DEX quoter abstractions.

Defines the contract every D-3 on-chain quoter must satisfy. Quoters are
PURE VALUE-OBJECT PRODUCERS — they return DEXQuoteResult instances, never
CanonicalOpportunity, never DiscoveryCandidate. INV-2 is preserved by
construction (no EmissionBus reachable from this module — no scanner
orchestrator imports the quoter to drive an emit call).

Two reference implementations are included:

  - EVMV3Quoter — Uniswap V3 / PancakeSwap V3 / Aerodrome share the V3
                  QuoterV2 ABI surface (`quoteExactInputSingle` /
                  `quoteExactInput`). One class parameterised by
                  (chain, dex, rpc_env_var, quoter_address) handles all
                  three DEX families across all target EVM chains.
  - RaydiumQuoter — Solana / Raydium AMM pool-state reads via Helius RPC,
                    off-chain quote math.

Both implementations are **graceful-disable**: if the required RPC env var is
absent the quoter returns DEXQuoteResult(ok=False, reason="credentials_missing")
without raising, so the rest of the system continues to work during D-3
shadow rollout when only some providers are provisioned.

Live HTTP is intentionally NOT exercised in D-3.1 unit tests — credentials
land at D-3.6. The quoter contract + graceful-disable + provenance attribution
are the surface tested at this wave.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ============================================================================
# Result value object
# ============================================================================

@dataclass
class DEXQuoteResult:
    """Single-leg quote outcome. Pure value object — never persisted."""

    ok: bool
    chain: str
    dex: str
    pool_address: Optional[str] = None
    token_in: Optional[str] = None
    token_out: Optional[str] = None
    size_in_usd: Optional[float] = None
    amount_in: Optional[float] = None
    amount_out: Optional[float] = None
    effective_price: Optional[float] = None      # amount_out / amount_in
    mid_price: Optional[float] = None             # mid at the pool (no size impact)
    slippage_pct: Optional[float] = None
    fee_tier_bps: Optional[int] = None
    pool_liquidity_usd: Optional[float] = None
    gas_estimate_usd: Optional[float] = None
    quoted_at_ts: float = field(default_factory=lambda: time.time())
    age_ms: Optional[int] = None
    reason: Optional[str] = None                  # "" on ok; explanation otherwise
    source_id: Optional[str] = None               # SOURCE_REGISTRY id (INV-3 attribution)
    raw: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Quoter ABC
# ============================================================================

class BaseDEXQuoter(ABC):
    """Contract every D-3 on-chain quoter satisfies.

    Subclasses MUST set:
      - chain, dex            (str identifiers)
      - source_id             (key in arbicore.data.provenance.SOURCE_REGISTRY)
      - rpc_env_var           (e.g. "ALCHEMY_API_KEY"); None ⇒ no creds required
    Subclasses MUST implement:
      - _quote_impl(...)      (live integration; only invoked when credentials present)
    """

    chain: str = ""
    dex: str = ""
    source_id: str = ""
    rpc_env_var: Optional[str] = None

    def __init__(self) -> None:
        if not self.chain or not self.dex or not self.source_id:
            raise TypeError(
                f"{type(self).__name__} must set chain, dex, source_id at class scope"
            )

    # ----- public API -------------------------------------------------------

    @property
    def credentials_available(self) -> bool:
        if not self.rpc_env_var:
            return True
        return bool(os.environ.get(self.rpc_env_var, "").strip())

    async def quote(self, *, pair_canonical: str, size_in_usd: float,
                    direction: str = "buy") -> DEXQuoteResult:
        """Return a DEXQuoteResult. NEVER raises.

        Graceful disable: if rpc_env_var is set but absent from os.environ,
        returns ok=False with reason='credentials_missing'. Live-integration
        errors are also caught and returned as ok=False results.
        """
        if not self.credentials_available:
            return DEXQuoteResult(
                ok=False, chain=self.chain, dex=self.dex,
                source_id=self.source_id,
                reason=f"credentials_missing:{self.rpc_env_var}",
            )
        if direction not in ("buy", "sell"):
            return DEXQuoteResult(
                ok=False, chain=self.chain, dex=self.dex,
                source_id=self.source_id, reason="invalid_direction",
            )
        try:
            return await self._quote_impl(
                pair_canonical=pair_canonical,
                size_in_usd=size_in_usd,
                direction=direction,
            )
        except Exception as exc:  # noqa: BLE001
            return DEXQuoteResult(
                ok=False, chain=self.chain, dex=self.dex,
                source_id=self.source_id,
                reason=f"quoter_error:{type(exc).__name__}:{exc}",
            )

    # ----- subclass contract -----------------------------------------------

    @abstractmethod
    async def _quote_impl(self, *, pair_canonical: str,
                          size_in_usd: float, direction: str) -> DEXQuoteResult:
        """Live integration. Invoked only when credentials_available is True."""


# ============================================================================
# EVM V3 quoter (Uniswap V3 / PancakeSwap V3 / Aerodrome share ABI surface)
# ============================================================================

# QuoterV2 contract addresses per (dex, chain). Used by _quote_impl when wired
# in D-3.6; D-3.1 tests do not exercise these.
EVM_V3_QUOTER_CONTRACTS: Dict[tuple, str] = {
    ("uniswap_v3", "ethereum"): "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    ("uniswap_v3", "arbitrum"): "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    ("uniswap_v3", "base"):     "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
    ("pancake_v3", "bnb"):       "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
    ("pancake_v3", "arbitrum"):  "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
    ("pancake_v3", "base"):      "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",
    ("aerodrome",  "base"):      "0xA8AAd9a89CD8AD68BcE5A4eaF5CB75f4Fb15D89F",
}


class EVMV3Quoter(BaseDEXQuoter):
    """Uniswap V3 / PancakeSwap V3 / Aerodrome quoter (shared ABI).

    rpc_env_var defaults to ALCHEMY_API_KEY. When live integration lands in
    D-3.6 the implementation will issue eth_call against
    EVM_V3_QUOTER_CONTRACTS[(dex, chain)].quoteExactInputSingle for the
    fee-tier candidate set, picking the best output. Until then _quote_impl
    returns ok=False with reason='not_yet_wired' — discoverable, tested,
    documented; no surprises.
    """

    rpc_env_var = "ALCHEMY_API_KEY"

    def __init__(self, *, chain: str, dex: str, source_id: str) -> None:
        self.chain = chain
        self.dex = dex
        self.source_id = source_id
        super().__init__()
        if (dex, chain) not in EVM_V3_QUOTER_CONTRACTS:
            raise ValueError(
                f"EVMV3Quoter has no QuoterV2 address for ({dex}, {chain})"
            )
        self.quoter_address = EVM_V3_QUOTER_CONTRACTS[(dex, chain)]

    async def _quote_impl(self, *, pair_canonical: str,
                          size_in_usd: float, direction: str) -> DEXQuoteResult:
        # D-3.6 will replace this stub with httpx + eth_call wiring. Returning
        # an explicit ok=False keeps the discovery/scanner layers exercisable
        # and the contract testable today.
        return DEXQuoteResult(
            ok=False, chain=self.chain, dex=self.dex,
            source_id=self.source_id, token_in=pair_canonical.split("/")[0],
            token_out=pair_canonical.split("/")[1] if "/" in pair_canonical else None,
            size_in_usd=size_in_usd,
            reason="not_yet_wired:D-3.6_will_wire_eth_call",
        )


# ============================================================================
# Solana / Raydium quoter
# ============================================================================

class RaydiumQuoter(BaseDEXQuoter):
    """Solana / Raydium AMM quoter (off-chain math against on-chain pool state).

    rpc_env_var = HELIUS_API_KEY. _quote_impl is stubbed for D-3.1 like the
    EVM quoter — wiring lands at D-3.6.
    """

    chain = "solana"
    dex = "raydium"
    source_id = "raydium_quoter_solana"
    rpc_env_var = "HELIUS_API_KEY"

    async def _quote_impl(self, *, pair_canonical: str,
                          size_in_usd: float, direction: str) -> DEXQuoteResult:
        return DEXQuoteResult(
            ok=False, chain=self.chain, dex=self.dex,
            source_id=self.source_id,
            token_in=pair_canonical.split("/")[0],
            token_out=pair_canonical.split("/")[1] if "/" in pair_canonical else None,
            size_in_usd=size_in_usd,
            reason="not_yet_wired:D-3.6_will_wire_helius_pool_reads",
        )


# ============================================================================
# Factory
# ============================================================================

def build_default_quoters() -> List[BaseDEXQuoter]:
    """Instantiate one quoter per (dex, chain) in the D-3 universe.

    Total 8 quoters: 7 EVM V3 (uniswap_v3 × 3, pancake_v3 × 3, aerodrome × 1)
    + 1 Solana Raydium. Each instance is independently graceful-disabled if
    its rpc_env_var is missing.
    """
    out: List[BaseDEXQuoter] = []
    for (dex, chain), _addr in EVM_V3_QUOTER_CONTRACTS.items():
        source_id = f"{dex}_quoter_{chain}"
        out.append(EVMV3Quoter(chain=chain, dex=dex, source_id=source_id))
    out.append(RaydiumQuoter())
    return out
