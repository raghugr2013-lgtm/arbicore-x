"""ArbiCore X — Phase C Wave 5: ShadowBindingObserver.

Subscribes (logically — wired via a non-invasive post-run hook on
``ApprovalProposer``) to legacy proposal snapshots and emits canonical
opportunities into the learning loop.

End-to-end side effects per snapshot:
  1. ``OpportunityRepository.upsert(opp)`` — canonical row persisted.
  2. ``OutcomeTracker.record_emission(opp)`` — per-horizon outcome rows seeded.
  3. ``OutcomeRepository.append_state_snapshot(state)`` — rolling state for
     the BDAG subject keyed off the legacy proposal's best-bid mid-price.
  4. ``EntityResolver.resolve_or_create()`` — buy/sell venues recorded as
     ``CEX_ACCOUNT`` entities so the Wave-4 Entity Intelligence layer has
     real subjects to score / cluster against.
  5. ``MetricsAggregator.aggregate_by_subject_horizon()`` — invoked on a
     low cadence (every ``METRICS_AGG_EVERY_N`` snapshots) to keep the
     ``arbicore_signal_metrics`` collection fresh for the
     AdaptiveConfidenceEngine.

All steps are wrapped in a per-step try/except: shadow-binding errors must
never propagate back to the legacy ``ApprovalProposer`` loop.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ..data.outcome_repo import OutcomeRepository, StateRow
from ..data.provenance import is_learning_eligible
from ..intel.entity_types import EntityType
from ..intel.resolver import EntityResolver
from ..learning.concrete.audit_log import MongoAuditLog
from ..learning.concrete.metrics_aggregator import MetricsAggregator
from ..learning.concrete.outcome_tracker import OutcomeTracker
from ..models.canonical import CanonicalOpportunity
from ..models.enums import DataProvenance
from .mapper import LEGACY_OPPORTUNITY_TYPE, LegacyProposalMapper

logger = logging.getLogger("arbicore.shadow")

METRICS_AGG_EVERY_N = 4  # ~1 per minute given ApprovalProposer's 15s cadence


class ShadowBindingObserver:
    """Stateless-ish singleton: holds per-process counters for the
    /api/arbicore/shadow/status endpoint and rate-limits the metrics
    aggregator. Persisted state lives entirely in Mongo."""

    def __init__(self,
                 opportunity_repo,
                 outcome_repo: OutcomeRepository,
                 outcome_tracker: OutcomeTracker,
                 metrics_aggregator: MetricsAggregator,
                 entity_resolver: EntityResolver,
                 audit_log: Optional[MongoAuditLog] = None,
                 ) -> None:
        self._opps = opportunity_repo
        self._outcomes = outcome_repo
        self._tracker = outcome_tracker
        self._metrics = metrics_aggregator
        self._resolver = entity_resolver
        self._audit = audit_log
        self._mapper = LegacyProposalMapper()
        self._stats: Dict[str, Any] = {
            "snapshots_observed":         0,
            "snapshots_with_proposals":   0,
            "opportunities_mapped":       0,
            "opportunities_upserted":     0,
            "emissions_recorded":         0,
            "state_snapshots_written":    0,
            "entities_resolved":          0,
            "metrics_aggregations":       0,
            "errors_mapping":             0,
            "errors_persistence":         0,
            "errors_learning":            0,
            "skipped_non_learning":       0,
            "last_snapshot_at":           None,
            "last_error":                 None,
        }

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    async def observe(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Process one ``build_proposals()`` snapshot end-to-end.

        Returns a small per-call report so callers (and tests) can verify
        observation took place. Never raises — internal errors are
        captured into ``self._stats``.
        """
        self._stats["snapshots_observed"] += 1
        self._stats["last_snapshot_at"] = time.time()
        report: Dict[str, Any] = {
            "mapped": 0, "upserted": 0, "emissions": 0,
            "state_snapshots": 0, "entities": 0,
        }
        try:
            opps = self._mapper.map_snapshot(snapshot)
        except Exception as exc:  # noqa: BLE001
            self._stats["errors_mapping"] += 1
            self._stats["last_error"] = f"map_snapshot: {exc!r}"
            logger.exception("shadow.map_snapshot failed: %s", exc)
            return report
        if not opps:
            return report
        self._stats["snapshots_with_proposals"] += 1
        self._stats["opportunities_mapped"] += len(opps)
        report["mapped"] = len(opps)

        # ---- 1. Upsert canonical opportunities --------------------------
        upserted = 0
        for opp in opps:
            try:
                await self._opps.upsert(opp)
                upserted += 1
            except Exception as exc:  # noqa: BLE001
                self._stats["errors_persistence"] += 1
                self._stats["last_error"] = f"opp.upsert: {exc!r}"
                logger.exception("shadow.opportunity_repo.upsert failed: %s", exc)
        self._stats["opportunities_upserted"] += upserted
        report["upserted"] = upserted

        # ---- 2. Outcome emission seeding --------------------------------
        emissions = 0
        for opp in opps:
            if not is_learning_eligible(opp.source_data_quality):
                self._stats["skipped_non_learning"] += 1
                continue
            try:
                seeded = await self._tracker.record_emission(opp)
                if seeded:
                    emissions += 1
            except Exception as exc:  # noqa: BLE001
                self._stats["errors_learning"] += 1
                self._stats["last_error"] = f"tracker.record_emission: {exc!r}"
                logger.exception("shadow.outcome_tracker failed: %s", exc)
        self._stats["emissions_recorded"] += emissions
        report["emissions"] = emissions

        # ---- 3. State snapshot for the subject --------------------------
        # Pick the best (primary tier) opp's mid-price as the canonical
        # "state" of the BDAG subject at this tick. Falls back gracefully
        # if buy_price is the only thing available.
        state_n = await self._write_state_snapshot(opps[0])
        report["state_snapshots"] = state_n
        self._stats["state_snapshots_written"] += state_n

        # ---- 4. Entity resolution (venues) ------------------------------
        entity_ids = await self._resolve_entities(opps[0])
        report["entities"] = len(entity_ids)
        self._stats["entities_resolved"] += len(entity_ids)

        # ---- 5. Low-cadence metrics aggregation -------------------------
        if (self._stats["snapshots_observed"] % METRICS_AGG_EVERY_N) == 0:
            try:
                await self._metrics.aggregate_by_subject_horizon()
                self._stats["metrics_aggregations"] += 1
            except Exception as exc:  # noqa: BLE001
                self._stats["errors_learning"] += 1
                self._stats["last_error"] = f"metrics.aggregate: {exc!r}"

        # ---- 6. Audit ---------------------------------------------------
        if self._audit:
            try:
                await self._audit.write(
                    actor="shadow_binder",
                    event="snapshot_observed",
                    subject_id=opps[0].subject_id,
                    payload={
                        "mapped": report["mapped"],
                        "upserted": report["upserted"],
                        "emissions": report["emissions"],
                        "state_snapshots": report["state_snapshots"],
                        # ``entities`` MUST be a list of entity_ids — the
                        # Wave 4 EntityClusterDetector relies on this exact
                        # shape (see arbicore/intel/cluster_detector.py).
                        "entities": entity_ids,
                    },
                )
            except Exception:  # noqa: BLE001
                pass

        return report

    # ---------------------------------------------------------------- helpers

    async def _write_state_snapshot(self, opp: CanonicalOpportunity) -> int:
        # Choose primary_metric: prefer sell_price (best_bid) since that's
        # the realized exit price. Fallback to buy_price.
        primary = opp.sell_price if opp.sell_price is not None else opp.buy_price
        if primary is None:
            return 0
        provenance = (opp.source_data_quality.value
                      if isinstance(opp.source_data_quality, DataProvenance)
                      else str(opp.source_data_quality))
        state = StateRow(
            subject_id=opp.subject_id or "BDAG",
            opportunity_type=LEGACY_OPPORTUNITY_TYPE.value,
            captured_at_ts=time.time(),
            primary_metric=float(primary),
            secondary_metrics={
                "buy_price":  opp.buy_price,
                "sell_price": opp.sell_price,
                "spread_pct": opp.spread_pct,
                "expected_profit_usd": opp.expected_profit_usd,
                "capital_required_usd": opp.capital_required_usd,
                "regime": opp.market_regime.value if hasattr(opp.market_regime, "value") else None,
            },
            source="shadow_binder",
            provenance=provenance,
        )
        try:
            await self._outcomes.append_state_snapshot(state)
            return 1
        except Exception as exc:  # noqa: BLE001
            self._stats["errors_persistence"] += 1
            self._stats["last_error"] = f"state_snapshot: {exc!r}"
            return 0

    async def _resolve_entities(self, opp: CanonicalOpportunity) -> List[str]:
        """Resolve venue refs into entity_ids. Returns the list of resolved
        entity_ids — used both for stats AND as the canonical co-occurrence
        payload consumed by the Wave-4 EntityClusterDetector."""
        resolved: List[str] = []
        provenance = opp.source_data_quality
        if isinstance(provenance, str):
            try:
                provenance = DataProvenance(provenance)
            except ValueError:
                return resolved
        for ref_type, external_ref in self._venue_refs(opp):
            try:
                eid = await self._resolver.resolve_or_create(
                    ref_type=ref_type,
                    external_ref=external_ref,
                    entity_type=EntityType.CEX_ACCOUNT,
                    provenance=provenance,
                )
                if eid:
                    resolved.append(eid)
            except Exception as exc:  # noqa: BLE001
                self._stats["errors_persistence"] += 1
                self._stats["last_error"] = f"entity.resolve: {exc!r}"
        return resolved

    @staticmethod
    def _venue_refs(opp: CanonicalOpportunity) -> List[tuple]:
        out: List[tuple] = []
        if opp.buy_venue:
            out.append(("buy_venue", opp.buy_venue))
        if opp.sell_venue:
            out.append(("sell_venue", opp.sell_venue))
        return out
