"""ArbiCore X — Phase D D-3 DEX Arbitrage package.

D-3.1 ships the source + quoter abstractions only:
  - BaseDEXQuoter ABC + DEXQuoteResult dataclass (quoter.py)
  - DEXQuoteCache (quote_cache.py)
  - BaseDEXPoolSource ABC + concrete venue × chain sources (sources.py)

NO scanner orchestrator (D-3.4). NO verifier (D-3.2). NO emit path. INV-1/2/3
preserved by construction — sources return DiscoveryCandidate ONLY, quoters
return DEXQuoteResult (a value object, not a CanonicalOpportunity), and there
is no code path in this package that drives the EmissionBus emit method.
"""
from .quote_cache import DEXQuoteCache
from .quoter import (
    BaseDEXQuoter, DEXQuoteResult, EVMV3Quoter, RaydiumQuoter,
    build_default_quoters,
)
from .sources import (
    BaseDEXPoolSource, UniswapV3PoolSource, PancakeV3PoolSource,
    AerodromePoolSource, RaydiumPoolSource, build_all_dex_sources,
)
from .verifier import DEXQuoteVerifier
from .filter import run_dex_gates, DEXGateContext
from .economics import DEXEconomicsAssessor
from .scanner import DEXArbitrageScanner

__all__ = [
    "BaseDEXQuoter", "DEXQuoteResult", "EVMV3Quoter", "RaydiumQuoter",
    "build_default_quoters",
    "DEXQuoteCache",
    "BaseDEXPoolSource", "UniswapV3PoolSource", "PancakeV3PoolSource",
    "AerodromePoolSource", "RaydiumPoolSource", "build_all_dex_sources",
    "DEXQuoteVerifier", "run_dex_gates", "DEXGateContext",
    "DEXEconomicsAssessor",
    "DEXArbitrageScanner",
]
