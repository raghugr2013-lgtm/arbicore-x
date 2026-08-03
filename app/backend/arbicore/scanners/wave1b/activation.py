"""ScannerActivation — Wave 1B-β factory.

Builds the two shadow scanner adapters and registers them. Never
autostarts them; the operator must call
``POST /api/arbicore/scanners/{name}/start``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ...data.mid.readers import MidReader
from ...data.mid.writers import MidWriter
from .adapters import ShadowScannerAdapter
from .bridge import ScannerEvidenceBridge
from .registry import ScannerRegistry

logger = logging.getLogger(__name__)


_SCANNER_SPECS = [
    {
        "id": "dex_arbitrage",
        "description": (
            "DEX arbitrage scanner — shadow harness (Wave 1B-β). Real "
            "class ``DEXArbitrageScanner`` is present in the tree but not "
            "instantiated: it requires live quoters/aggregator sources "
            "which are forbidden by the Sprint 1B charter."
        ),
        "opportunity_type": "dex_arbitrage",
        "dependencies": [
            "scanners.dex_arbitrage.scanner.DEXArbitrageScanner (dormant)",
            "wave1b.adapters.ShadowScannerAdapter",
        ],
    },
    {
        "id": "flash_loan_arbitrage",
        "description": (
            "Flash-loan arbitrage scanner — shadow harness (Wave 1B-β). "
            "Real class ``FlashLoanArbitrageScanner`` is present in the "
            "tree but not instantiated for the same reason."
        ),
        "opportunity_type": "flash_loan_arbitrage",
        "dependencies": [
            "scanners.flash_loan_arbitrage.scanner.FlashLoanArbitrageScanner (dormant)",
            "wave1b.adapters.ShadowScannerAdapter",
        ],
    },
]


@dataclass
class ScannerActivation:
    registry: ScannerRegistry
    bridge: ScannerEvidenceBridge
    adapters: Dict[str, ShadowScannerAdapter] = field(default_factory=dict)

    def get_adapter(
        self, scanner_id: str
    ) -> Optional[ShadowScannerAdapter]:
        return self.adapters.get(scanner_id)

    def summary(self) -> Dict[str, Any]:
        s = self.registry.summary()
        s["bridge_stats"] = self.bridge.stats.to_dict()
        return s


def activate_scanners(
    writer: MidWriter, reader: MidReader
) -> ScannerActivation:
    """Instantiate + register the shadow adapters. Never autostarts."""
    registry = ScannerRegistry()
    bridge = ScannerEvidenceBridge(writer)
    result = ScannerActivation(registry=registry, bridge=bridge)

    for spec in _SCANNER_SPECS:
        try:
            adapter = ShadowScannerAdapter(
                scanner_id=spec["id"],
                description=spec["description"],
                opportunity_type=spec["opportunity_type"],
                bridge=bridge,
                mid_reader=reader,
            )
            result.adapters[spec["id"]] = adapter
            registry.register(
                scanner_id=spec["id"],
                description=spec["description"],
                adapter=adapter,
                dependencies=spec["dependencies"],
            )
            logger.info(
                "wave1b-β: registered shadow scanner id=%s (dormant)",
                spec["id"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "wave1b-β: failed to register scanner %s: %s",
                spec["id"], exc,
            )
            registry.register(
                scanner_id=spec["id"],
                description=spec["description"],
                adapter=None,
                error=f"{type(exc).__name__}: {exc}",
            )

    logger.info(
        "wave1b-β: scanner activation complete — %d/%d registered, "
        "all DORMANT",
        len([s for s in registry.all() if s.error is None]),
        len(registry.all()),
    )
    return result
