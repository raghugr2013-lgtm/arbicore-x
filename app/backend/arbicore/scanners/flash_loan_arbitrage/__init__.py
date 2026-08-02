"""ArbiCore X — Phase D D-6.1 Flash-Loan Detection Framework.

Atomic multi-hop arbitrage opportunities funded by single-block flash
loans. Detection only — no execution, no bundle submission, no relays.

Operator-scoped at D-6.0:
  - Providers: Aave V3, Balancer V2, Uniswap V3 (single-sided flash)
  - Chains:    Ethereum, Arbitrum, Base, Optimism, Polygon (no Solana)
  - Hop budget: max_hops = 4
  - Route search: wall_clock_cap = 5 s, candidate_cap = 64
  - Atomic-profit floor: 25 USD (Gate 7 default)

INV-1: sources emit DiscoveryCandidate only. ``RouteSearchEngine``
produces ordered route tuples that become DiscoveryCandidates.
INV-2: ``FlashLoanArbitrageScanner._tick()`` is the SIXTH and FINAL
authorised EmissionBus call site across the entire scanner tree.
INV-3: ``derive_provenance(legs)`` over the per-leg ``source_id``
chooses ``source_data_quality`` — never the aggregator hint.

Boot posture: DORMANT. Every per-provider and per-chain enable flag
ships ``False``; scanner state ships ``enabled=False``.
"""
from __future__ import annotations

from .economics import (
    FlashLoanEconomicsAssessor, FlashLoanEconomicsResult,
    FLASH_LOAN_PROVIDERS,
)
from .filter import (
    FlashLoanGate7AtomicProfit,
    FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
    GateResult,
)
from .route_search import (
    PoolNode, RouteSearchEngine, RouteCycle,
)
from .scanner import FlashLoanArbitrageScanner
from .sources import (
    RouteSearchDiscoverySource, FlashLoanProviderHealthSource,
    build_all_flash_loan_sources,
)
from .verifier import FlashLoanOpportunityVerifier

__all__ = [
    # Route search (the one novel substrate)
    "PoolNode", "RouteSearchEngine", "RouteCycle",
    # Sources
    "RouteSearchDiscoverySource", "FlashLoanProviderHealthSource",
    "build_all_flash_loan_sources",
    # Economics
    "FlashLoanEconomicsAssessor", "FlashLoanEconomicsResult",
    "FLASH_LOAN_PROVIDERS",
    # Gates
    "FlashLoanGate7AtomicProfit", "FlashLoanGate8LiquidityDepth",
    "FlashLoanGate9FlashLoanMev", "GateResult",
    # Verifier + scanner
    "FlashLoanOpportunityVerifier", "FlashLoanArbitrageScanner",
]
