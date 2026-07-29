"""ArbiCore X — Phase D D-5.1 Cross-Chain Arbitrage package.

Substrate established at D-5.0 (category_metadata vocab, SOURCE_REGISTRY
entries, scanner_config defaults, scanner_state seed). D-5.1 ships the
operational layer:

  - LiFiAggregatorSource              (D-5.1 HINT-aware DiscoverySource)
  - StargateSource                    (D-5.1 HINT-aware DiscoverySource)
  - ChainLivenessRegistry             (per-chain finality/congestion)
  - BridgeRouteCatalog                (per-bridge corridor metadata)
  - MevRiskScorer                     (lightweight runtime MEV scorer)
  - TransferModelProvider / LiFi...   (read-only bridge quote provider)
  - BridgeEconomicsAssessor           (D-3 economics consumer)
  - CrossChainGate7BridgeLiveness     (D-5.1 family-specific Gate 7)
  - CrossChainGate8ChainLiveness      (D-5.1 family-specific Gate 8)
  - CrossChainGate9CrossChainMev      (D-5.1 family-specific Gate 9)
  - CrossChainOpportunityVerifier     (D-5.1 — sole canonical construction)
  - CrossChainArbitrageScanner        (D-5.1 — sole INV-2 emit site;
                                       5th and final authorised emit site
                                       in the ArbiCore X scanner tree)

Boot posture: scanner ships DISABLED. Every per-bridge and per-chain
enable flag in ``scanner_config.cross_chain_arb`` ships False. Operator
graduates each surface via the D-5.1 HTTP routes.
"""
from __future__ import annotations

from .bridge_intelligence import (
    BridgeRouteCatalog, BridgeRouteMetadata,
    MevRiskScorer,
)
from .chain_liveness import (
    ChainLivenessRegistry, ChainLivenessSnapshot,
    RpcChainLivenessLoader,
)
from .economics import BridgeEconomicsAssessor, BridgeEconomicsResult
from .filter import (
    CrossChainGate7BridgeLiveness,
    CrossChainGate8ChainLiveness,
    CrossChainGate9CrossChainMev,
    GateResult,
)
from .scanner import CrossChainArbitrageScanner
from .sources import (
    LiFiAggregatorSource, StargateSource, build_all_cross_chain_sources,
)
from .transfer_provider import (
    LiFiTransferProvider, StargateTransferProvider, TransferModelProvider,
)
from .verifier import CrossChainOpportunityVerifier

__all__ = [
    # Sources
    "LiFiAggregatorSource", "StargateSource", "build_all_cross_chain_sources",
    # Intelligence
    "ChainLivenessRegistry", "ChainLivenessSnapshot",
    "RpcChainLivenessLoader",
    "BridgeRouteCatalog", "BridgeRouteMetadata", "MevRiskScorer",
    # Transfer modelling
    "TransferModelProvider", "LiFiTransferProvider",
    "StargateTransferProvider",
    # Economics + Gates
    "BridgeEconomicsAssessor", "BridgeEconomicsResult",
    "CrossChainGate7BridgeLiveness", "CrossChainGate8ChainLiveness",
    "CrossChainGate9CrossChainMev", "GateResult",
    # Verifier + Scanner
    "CrossChainOpportunityVerifier",
    "CrossChainArbitrageScanner",
]
