"""ScannerEvidenceBridge — the single scanner → MID write path.

Every emission a scanner produces (in Wave 1B-β: a synthetic shadow
emission; in Sprint 2: a real verified opportunity) flows through this
bridge into MID. This preserves the Sprint 1B invariant that
intelligence engines consume scanner outputs ONLY via MID rather than
via direct in-process coupling.

For each emission the bridge writes:

  * one ``mid_opportunities`` row with ``event_type =
    "scanner.<scanner_id>.emit"`` — the timeline of every scanner tick,
  * one ``mid_routes`` row when a route fingerprint is supplied — so
    the route-ranking engine has a first-class ``mid_routes`` sample
    to learn from,
  * bumps :class:`ScannerBridgeStats` counters used by
    ``/api/arbicore/scanners/status``.

The bridge never raises — errors are recorded on the stats block.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...data.mid.writers import MidWriter, make_meta
from ...data.mid.schemas import MidMetadata

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ScannerBridgeStats:
    total_emissions: int = 0
    by_scanner: Dict[str, int] = field(default_factory=dict)
    by_event_type: Dict[str, int] = field(default_factory=dict)
    routes_observed: int = 0
    last_emit_at: Optional[str] = None
    last_scanner: Optional[str] = None
    last_error: Optional[str] = None

    def record(self, scanner: str, event_type: str,
               route_written: bool) -> None:
        self.total_emissions += 1
        self.by_scanner[scanner] = self.by_scanner.get(scanner, 0) + 1
        self.by_event_type[event_type] = (
            self.by_event_type.get(event_type, 0) + 1
        )
        if route_written:
            self.routes_observed += 1
        self.last_emit_at = _now_iso()
        self.last_scanner = scanner

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_emissions": self.total_emissions,
            "by_scanner": dict(self.by_scanner),
            "by_event_type": dict(self.by_event_type),
            "routes_observed": self.routes_observed,
            "last_emit_at": self.last_emit_at,
            "last_scanner": self.last_scanner,
            "last_error": self.last_error,
        }


class ScannerEvidenceBridge:
    def __init__(self, writer: MidWriter) -> None:
        self._writer = writer
        self.stats = ScannerBridgeStats()

    async def publish_emission(
        self,
        *,
        scanner_id: str,
        opp_id: str,
        payload: Dict[str, Any],
        route: Optional[Dict[str, Any]] = None,
        meta: Optional[MidMetadata] = None,
    ) -> Dict[str, Optional[str]]:
        """Persist one scanner emission into MID.

        Returns ``{"opportunity_event_id": ..., "route_observation_id": ...}``
        (either value may be ``None`` if that write failed or was not
        applicable).
        """
        meta = meta or make_meta(
            opportunity_type=payload.get("opportunity_type", "unknown"),
            chain=payload.get("chain", "unknown"),
            protocol=payload.get("protocol"),
            execution_mode="shadow",
            market_regime=payload.get("market_regime", "UNKNOWN"),
            tags=payload.get("tags"),
        )
        event_type = f"scanner.{scanner_id}.emit"
        result: Dict[str, Optional[str]] = {
            "opportunity_event_id": None,
            "route_observation_id": None,
        }
        route_written = False

        # 1. mirror opportunity event
        try:
            result["opportunity_event_id"] = (
                await self._writer.write_opportunity_event(
                    opp_id=opp_id,
                    event_type=event_type,
                    payload=payload,
                    meta=meta,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "ScannerEvidenceBridge opportunity_event failed: %s", exc)
            self.stats.last_error = f"opp_event[{scanner_id}]: {exc!r}"

        # 2. optional route observation (Sprint 1B contract: routes flow
        #    into MID so the route_ranking engine can learn from them).
        if route:
            try:
                result["route_observation_id"] = (
                    await self._writer.write_route_observation(
                        route_id=route["route_id"],
                        fingerprint_parts=route.get(
                            "fingerprint_parts", {}),
                        meta=meta,
                    )
                )
                route_written = True
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "ScannerEvidenceBridge route_observation failed: %s",
                    exc,
                )
                self.stats.last_error = (
                    f"route[{scanner_id}]: {exc!r}")

        self.stats.record(scanner_id, event_type, route_written)
        return result
