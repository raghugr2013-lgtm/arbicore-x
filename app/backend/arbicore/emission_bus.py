"""ArbiCore X — Phase D D-1: shared EmissionBus.

Extracted from the Wave 5 ShadowBindingObserver fan-out logic so every
Phase D scanner can use the exact same downstream pipeline:
  - opportunity_repo.upsert  (idempotent canonical persistence)
  - outcome_tracker.record_emission (provenance-gated 5-horizon seeding)
  - state_snapshot append (subject state observation)
  - entity_resolver.resolve_or_create (universal entity layer)
  - audit_log.write (forensic trail)

INV-2: The ONLY signature this bus accepts is CanonicalOpportunity.
       Discovery candidates cannot reach this code path. The verifier
       contract returning Optional[CanonicalOpportunity] is the sole
       gateway.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .data.outcome_repo import OutcomeRepository, StateRow
from .data.provenance import is_learning_eligible
from .intel.entity_types import EntityType
from .intel.resolver import EntityResolver
from .learning.concrete.audit_log import MongoAuditLog
from .learning.concrete.outcome_tracker import OutcomeTracker
from .models.canonical import CanonicalOpportunity
from .models.enums import DataProvenance

logger = logging.getLogger("arbicore.emission_bus")


class EmissionBus:
    """Shared downstream pipeline for canonical opportunity emission.

    Every Phase D scanner emits through this bus. The bus is category-
    agnostic — it never branches on opportunity_type. New scanners plug
    in for free.
    """

    def __init__(self,
                 opportunity_repo,
                 outcome_repo: OutcomeRepository,
                 outcome_tracker: OutcomeTracker,
                 entity_resolver: EntityResolver,
                 audit_log: Optional[MongoAuditLog] = None,
                 ) -> None:
        self._opps = opportunity_repo
        self._outcomes = outcome_repo
        self._tracker = outcome_tracker
        self._resolver = entity_resolver
        self._audit = audit_log
        self._stats: Dict[str, Any] = {
            "opportunities_upserted":  0,
            "emissions_recorded":      0,
            "state_snapshots_written": 0,
            "entities_resolved":       0,
            "skipped_non_learning":    0,
            "errors_persistence":      0,
            "errors_learning":         0,
            "last_emit_at":            None,
            "last_error":              None,
        }

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    async def emit(self, opp: CanonicalOpportunity,
                   *, venue_ids: Optional[List[str]] = None,
                   actor: str = "emission_bus",
                   ) -> Dict[str, Any]:
        """Persist + seed learning for a single CanonicalOpportunity.

        INV-2 enforced by signature: only CanonicalOpportunity allowed.
        Never raises — errors are counted in self._stats.
        """
        report: Dict[str, Any] = {
            "upserted": 0, "emission": 0,
            "state_snapshot": 0, "entities": 0,
        }
        self._stats["last_emit_at"] = time.time()

        # 1. Canonical upsert
        try:
            await self._opps.upsert(opp)
            self._stats["opportunities_upserted"] += 1
            report["upserted"] = 1
        except Exception as exc:  # noqa: BLE001
            self._stats["errors_persistence"] += 1
            self._stats["last_error"] = f"opp.upsert: {exc!r}"
            logger.exception("emission_bus.upsert failed: %s", exc)

        # 2. Outcome emission (provenance-gated)
        if is_learning_eligible(opp.source_data_quality):
            try:
                seeded = await self._tracker.record_emission(opp)
                if seeded:
                    self._stats["emissions_recorded"] += 1
                    report["emission"] = 1
            except Exception as exc:  # noqa: BLE001
                self._stats["errors_learning"] += 1
                self._stats["last_error"] = f"tracker.record_emission: {exc!r}"
        else:
            self._stats["skipped_non_learning"] += 1

        # 3. State snapshot
        report["state_snapshot"] = await self._write_state_snapshot(opp)

        # 4. Entity resolution for venues
        entity_ids = await self._resolve_entities(opp, venue_ids or [])
        report["entities"] = len(entity_ids)

        # 5. Audit
        if self._audit:
            try:
                await self._audit.write(
                    actor=actor,
                    event="opportunity_emitted",
                    subject_id=opp.subject_id,
                    payload={
                        "opportunity_id": opp.opportunity_id,
                        "opportunity_type": opp.opportunity_type.value,
                        "status": opp.status.value,
                        "entities": entity_ids,
                    },
                )
            except Exception:  # noqa: BLE001
                pass

        return report

    async def emit_batch(self, opps: List[CanonicalOpportunity],
                         *, venue_ids: Optional[List[str]] = None,
                         actor: str = "emission_bus",
                         ) -> Dict[str, int]:
        """Convenience for batch emission (used by Wave 5 binder)."""
        agg = {"upserted": 0, "emissions": 0,
               "state_snapshots": 0, "entities": 0, "count": 0}
        for opp in opps:
            r = await self.emit(opp, venue_ids=venue_ids, actor=actor)
            agg["count"] += 1
            agg["upserted"] += r.get("upserted", 0)
            agg["emissions"] += r.get("emission", 0)
            agg["state_snapshots"] += r.get("state_snapshot", 0)
            agg["entities"] += r.get("entities", 0)
        return agg

    # -------------------------------------------------------------- helpers

    async def _write_state_snapshot(self, opp: CanonicalOpportunity) -> int:
        primary = opp.sell_price if opp.sell_price is not None else opp.buy_price
        if primary is None:
            return 0
        provenance = (opp.source_data_quality.value
                      if isinstance(opp.source_data_quality, DataProvenance)
                      else str(opp.source_data_quality))
        state = StateRow(
            subject_id=opp.subject_id or "UNKNOWN",
            opportunity_type=opp.opportunity_type.value,
            captured_at_ts=time.time(),
            primary_metric=float(primary),
            secondary_metrics={
                "buy_price": opp.buy_price,
                "sell_price": opp.sell_price,
                "spread_pct": opp.spread_pct,
                "expected_profit_usd": opp.expected_profit_usd,
                "capital_required_usd": opp.capital_required_usd,
            },
            source="emission_bus",
            provenance=provenance,
        )
        try:
            await self._outcomes.append_state_snapshot(state)
            self._stats["state_snapshots_written"] += 1
            return 1
        except Exception as exc:  # noqa: BLE001
            self._stats["errors_persistence"] += 1
            self._stats["last_error"] = f"state_snapshot: {exc!r}"
            return 0

    async def _resolve_entities(self, opp: CanonicalOpportunity,
                                venue_ids: List[str]) -> List[str]:
        resolved: List[str] = []
        provenance = opp.source_data_quality
        if isinstance(provenance, str):
            try:
                provenance = DataProvenance(provenance)
            except ValueError:
                return resolved
        # Default: use opp's own buy/sell venues if no venue_ids passed
        refs: List[tuple] = []
        if venue_ids:
            for v in venue_ids:
                refs.append(("venue", v))
        else:
            if opp.buy_venue:
                refs.append(("buy_venue", opp.buy_venue))
            if opp.sell_venue:
                refs.append(("sell_venue", opp.sell_venue))
        for ref_type, external_ref in refs:
            try:
                eid = await self._resolver.resolve_or_create(
                    ref_type=ref_type,
                    external_ref=external_ref,
                    entity_type=EntityType.CEX_ACCOUNT,
                    provenance=provenance,
                )
                if eid:
                    resolved.append(eid)
                    self._stats["entities_resolved"] += 1
            except Exception as exc:  # noqa: BLE001
                self._stats["errors_persistence"] += 1
                self._stats["last_error"] = f"entity.resolve: {exc!r}"
        return resolved
