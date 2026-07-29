"""ArbiCore X — OutcomeTracker concrete (Phase C Wave 1).

Category-agnostic outcome tracker. Listens (optionally via EventBus) for
opportunity emissions, schedules per-horizon outcome rows, and periodically
evaluates due rows by querying the registered ``StateObserver`` for each
opportunity type.

Hard rules (governance):
  - No exchange/asset/category-specific code.
  - Only ``LEARNING_ELIGIBLE_PROVENANCE`` opportunities seed outcome rows.
  - ``NullStateObserver`` (default for unregistered types) returns None →
    the evaluator marks the row evaluated with ``realized_metric=None`` and
    ``succeeded=False``; this is the safe no-op that keeps the loop running.
  - No execution, no signing, no fund movement.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from ...data.outcome_repo import (
    OutcomeRepository,
    OutcomeRow,
    StateRow,
    make_outcome_rows_for,
)
from ...data.provenance import is_learning_eligible
from ...data.state_observer import StateObserverRegistry
from ...models.canonical import CanonicalOpportunity
from ...models.enums import DataProvenance, LEARNING_ELIGIBLE_PROVENANCE
from .audit_log import MongoAuditLog
from .models import OpportunityOutcome
from .route_success_tracker import MongoRouteSuccessTracker, route_key_for

logger = logging.getLogger("arbicore.outcome_tracker")


class OutcomeTracker:
    """Wave-1 concrete tracker.

    Wiring contract (composition root):
      - constructor receives concrete OutcomeRepository, StateObserverRegistry,
        RouteSuccessTracker, AuditLog
      - ``record_emission(opp)`` is invoked when a CanonicalOpportunity reaches
        APPROVED status (or any other downstream commit decision)
      - ``evaluate_due(now_ts)`` is invoked on a periodic cadence by the worker
    """

    def __init__(self,
                 outcome_repo: OutcomeRepository,
                 observer_registry: StateObserverRegistry,
                 route_tracker: Optional[MongoRouteSuccessTracker] = None,
                 audit_log: Optional[MongoAuditLog] = None,
                 ):
        self._outcomes = outcome_repo
        self._observers = observer_registry
        self._routes = route_tracker
        self._audit = audit_log
        self._stats: Dict[str, int] = {
            "emissions_recorded": 0,
            "rows_seeded": 0,
            "rows_evaluated": 0,
            "rows_skipped_provenance": 0,
            "rows_skipped_null_observer": 0,
            "route_outcomes_written": 0,
        }

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    # ---------------------------------------------------------------- emission

    async def record_emission(self, opp: CanonicalOpportunity) -> int:
        """Schedule per-horizon outcome rows for a newly-emitted opportunity.

        Returns the number of rows seeded. Returns 0 when provenance is not
        learning-eligible (no scheduling for SIMULATED / CONTAMINATED / DEAD).
        """
        if not is_learning_eligible(opp.source_data_quality):
            self._stats["rows_skipped_provenance"] += 1
            if self._audit:
                await self._audit.write(
                    actor="outcome_tracker",
                    event="emission_skipped_non_learning_provenance",
                    opportunity_id=opp.opportunity_id,
                    subject_id=opp.subject_id,
                    payload={"provenance": str(opp.source_data_quality)},
                )
            return 0
        emission_ts = time.time()
        rows = make_outcome_rows_for(
            opportunity_id=opp.opportunity_id,
            subject_id=opp.subject_id,
            emission_ts=emission_ts,
            provenance=opp.source_data_quality.value
            if isinstance(opp.source_data_quality, DataProvenance)
            else str(opp.source_data_quality),
        )
        seeded = 0
        for row in rows:
            # only_insert=True — guard against replay corruption per Phase B contract.
            wrote = await self._outcomes.upsert_outcome(row, only_insert=True)
            if wrote:
                seeded += 1
        self._stats["emissions_recorded"] += 1
        self._stats["rows_seeded"] += seeded
        if self._audit:
            await self._audit.write(
                actor="outcome_tracker",
                event="emission_recorded",
                opportunity_id=opp.opportunity_id,
                subject_id=opp.subject_id,
                payload={
                    "rows_seeded": seeded,
                    "opportunity_type": opp.opportunity_type.value,
                    "provenance": opp.source_data_quality.value,
                    "buy_venue": opp.buy_venue,
                    "sell_venue": opp.sell_venue,
                },
            )
        return seeded

    # -------------------------------------------------------------- evaluation

    async def evaluate_due(self, now_ts: Optional[float] = None,
                           limit: int = 200) -> Dict[str, Any]:
        """Evaluate all outcome rows whose due_at <= now_ts. Returns stats."""
        if now_ts is None:
            now_ts = time.time()
        due_rows = await self._outcomes.list_due(now_ts=now_ts, limit=limit)
        evaluated_count = 0
        null_observer_count = 0
        for row in due_rows:
            outcome = await self._evaluate_row(row, now_ts)
            if outcome is None:
                null_observer_count += 1
                continue
            evaluated_count += 1
        self._stats["rows_evaluated"] += evaluated_count
        self._stats["rows_skipped_null_observer"] += null_observer_count
        return {
            "evaluated_at": now_ts,
            "due_count": len(due_rows),
            "evaluated": evaluated_count,
            "null_observer": null_observer_count,
        }

    async def _evaluate_row(self, row: OutcomeRow, now_ts: float
                            ) -> Optional[OpportunityOutcome]:
        """Evaluate a single OutcomeRow by querying state from observer."""
        # Determine the opportunity context (subject_id + opportunity_type).
        # Without an opportunity-aware lookup, we need the row's subject + type.
        # OutcomeRow stores subject_id; opportunity_type must be derived from
        # the latest state snapshot (or marked null). For Wave 1 we look up
        # the latest state snapshot per subject; if absent → null observer path.
        if not row.subject_id:
            # Cannot evaluate without a subject — mark evaluated with no metric.
            await self._mark_no_data(row, now_ts, reason="missing_subject_id")
            return None
        latest_state = await self._outcomes.latest_state(row.subject_id)
        if latest_state is None:
            # No state snapshots exist for this subject → null-observer path.
            await self._mark_no_data(row, now_ts, reason="no_state_snapshots")
            return None
        # Compute realized metric and delta vs emission baseline (the first
        # state snapshot at or before the emission timestamp).
        emission_state = await self._earliest_state_at_or_before(
            row.subject_id, row.created_at,
        )
        baseline = emission_state.primary_metric if emission_state else latest_state.primary_metric
        realized = latest_state.primary_metric
        delta = realized - baseline
        succeeded = delta > 0
        outcome = OpportunityOutcome(
            opportunity_id=row.opportunity_id,
            subject_id=row.subject_id,
            opportunity_type=latest_state.opportunity_type,
            horizon_label=row.horizon_label,
            horizon_s=row.horizon_s,
            emission_ts=row.created_at,
            evaluated_at_ts=now_ts,
            realized_metric=realized,
            realized_metric_delta=delta,
            succeeded=succeeded,
            provenance=row.provenance or "",
            note="evaluated_via_state_observer",
        )
        # Persist the evaluated row.
        row.evaluated = True
        row.realized_metric = realized
        row.realized_outcome = outcome.to_dict()
        row.note = outcome.note
        await self._outcomes.upsert_outcome(row, only_insert=False)
        # Feed RouteSuccessTracker if route_key resolvable.
        if self._routes and outcome.route_key:
            await self._routes.record_outcome(
                outcome.route_key,
                succeeded=succeeded,
                realized_outcome=delta,
                provenance=DataProvenance(row.provenance) if row.provenance else DataProvenance.SIMULATED,
            )
            self._stats["route_outcomes_written"] += 1
        if self._audit:
            await self._audit.write(
                actor="outcome_tracker",
                event="outcome_evaluated",
                opportunity_id=row.opportunity_id,
                subject_id=row.subject_id,
                payload={
                    "horizon_label": row.horizon_label,
                    "succeeded": succeeded,
                    "delta": delta,
                },
            )
        return outcome

    async def _mark_no_data(self, row: OutcomeRow, now_ts: float, reason: str) -> None:
        row.evaluated = True
        row.realized_metric = None
        row.realized_outcome = {"succeeded": False, "reason": reason}
        row.note = f"evaluated_no_data:{reason}"
        await self._outcomes.upsert_outcome(row, only_insert=False)
        if self._audit:
            await self._audit.write(
                actor="outcome_tracker",
                event="outcome_no_data",
                opportunity_id=row.opportunity_id,
                subject_id=row.subject_id,
                payload={"horizon_label": row.horizon_label, "reason": reason},
            )

    async def _earliest_state_at_or_before(self,
                                           subject_id: str,
                                           t: float) -> Optional[StateRow]:
        # list_states returns oldest-first within [t0, t1]. Pull a small window
        # before t and pick the latest entry.
        states = await self._outcomes.list_states(
            subject_id=subject_id, t0=t - 24 * 3600, t1=t, limit=50,
        )
        return states[-1] if states else None


__all__ = ["OutcomeTracker", "LEARNING_ELIGIBLE_PROVENANCE", "route_key_for"]
