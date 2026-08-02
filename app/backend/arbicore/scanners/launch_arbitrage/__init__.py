"""ArbiCore X — Phase D D-4.5 Launch Intelligence package.

Substrate established at D-4.0; the I/O layer landed at D-4.1; the wallet
intel substrate at D-4.2; the evidence engines at D-4.3; the verifier +
economics + gates at D-4.4; the scanner orchestrator (this wave, D-4.5):

  - DexScreenerFreshLaunchSource     (D-4.1 HINT)
  - PumpfunLaunchesSource            (D-4.1 HINT)
  - JupiterTrendingSource            (D-4.1 HINT)
  - HeliusWalletSource               (D-4.1 REAL; HELIUS_API_KEY)
  - BitqueryWalletSource             (D-4.1 scaffolded)
  - LaunchEconomicsAssessor          (D-4.4)
  - LaunchGate1Filter                (D-4.4)
  - LaunchGate6RugRiskFilter         (D-4.4)
  - LaunchOpportunityVerifier        (D-4.4 — sole canonical construction)
  - LaunchArbitrageScanner           (D-4.5 — sole INV-2 emit site)

D-4.5 ships scanner orchestrator + composition wiring. Scanner remains
DISABLED at boot by default; operator activates via /api/arbicore/scanners/
launch_arb/resume.
"""
from __future__ import annotations

from .economics import LaunchEconomicsAssessor, LaunchEconomicsResult
from .filter import GateResult, LaunchGate1Filter, LaunchGate6RugRiskFilter
from .helius_venue_provider import HeliusLaunchVenueProvider
from .scanner import LaunchArbitrageScanner
from .sources import (
    BitqueryWalletSource,
    DexScreenerFreshLaunchSource,
    HeliusWalletSource,
    JupiterTrendingSource,
    PumpfunLaunchesSource,
    build_all_launch_sources,
)
from .verifier import LaunchOpportunityVerifier, LaunchVenueProvider

__all__ = [
    # D-4.1 sources
    "DexScreenerFreshLaunchSource",
    "PumpfunLaunchesSource",
    "JupiterTrendingSource",
    "HeliusWalletSource",
    "BitqueryWalletSource",
    "build_all_launch_sources",
    # D-4.4
    "LaunchEconomicsAssessor", "LaunchEconomicsResult",
    "LaunchGate1Filter", "LaunchGate6RugRiskFilter", "GateResult",
    "LaunchOpportunityVerifier", "LaunchVenueProvider",
    # D-4.5
    "LaunchArbitrageScanner",
    # Operational readiness — reference Helius provider (opt-in)
    "HeliusLaunchVenueProvider",
]
