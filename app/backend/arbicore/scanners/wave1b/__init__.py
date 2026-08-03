"""Sprint 1B-β — Scanner Activation (SHADOW MODE ONLY).

This package wires the two previously-dormant scanners
(``DEXArbitrageScanner`` and ``FlashLoanArbitrageScanner``) into the
runtime **without** any live network I/O. Concretely:

  * Neither scanner is autostarted; both boot DORMANT.
  * Neither instantiates the real production DEX/FlashLoan class (those
    classes drag in live HTTP quoters and DEX aggregator sources).
  * Instead we build a **ShadowScannerAdapter** for each scanner that
    implements the exact lifecycle contract (``start``, ``stop``,
    ``is_enabled``, ``status``, ``stats``) but consumes only MID data
    and only writes back to MID via :class:`ScannerEvidenceBridge`.
  * Every scanner emission is a validated MID row
    (``opportunity_event``) plus a ``route_observation`` — the exact
    contract Sprint 1B-β specifies.

Wave 1B-γ (integration + regression) will layer end-to-end tests over
this harness, then Sprint 2 will replace the shadow tick with the real
production discover→verify→emit pipeline once live providers are wired
in a later ticket.
"""
from .bridge import ScannerEvidenceBridge
from .registry import ScannerRegistry, ScannerStatus
from .adapters import ShadowScannerAdapter
from .activation import ScannerActivation, activate_scanners

__all__ = [
    "ScannerEvidenceBridge",
    "ScannerRegistry",
    "ScannerStatus",
    "ShadowScannerAdapter",
    "ScannerActivation",
    "activate_scanners",
]
