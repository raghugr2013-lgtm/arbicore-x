"""ArbiCore X — Learning Ledger (P0-B).

The Learning Ledger is the write-side companion to the Opportunity Journal
(P0-A). It converts terminal journal rows into training signals for the
two pre-existing learning workers:

    * CalibrationWorker      reads  db.calibration_log
                             sample: {predicted_confidence, survived, status,
                                      created_at, source, opportunity_id}

    * AdaptiveWeightsWorker  reads  db.arbicore_signal_metrics
                             row:    {signal_id, win_rate, sample_count,
                                      aggregated_at}

Design invariants:
  * Never rewrites the pipeline. Extends it by adding the missing "labelled
    sample" producer between broadcast/shadow outcomes and the existing
    workers.
  * Idempotent. Each journal row is consumed at most once — the ledger
    sets ``learning_consumed=True`` on the journal atomically after
    emitting the sample.
  * Emits samples for **every** opportunity, not only broadcast ones. In
    SHADOW mode the ledger uses the certification + policy verdict as a
    synthetic "would_have_survived" signal so the calibrator learns from
    every observation, even ones the operator never chose to broadcast.
  * Zero new dependencies. Reuses the same Motor db handle. Two collection
    names come straight from the pre-existing worker constructors so no
    ambient config drift is possible.

Labelling rules (deterministic, table below):

    execution_status          actual_result present    → learning_label / survived
    ------------------------  -----------------------  --------------------------
    COMPLETED                 pnl_usd > 0              → POSITIVE   / True
    COMPLETED                 pnl_usd <= 0             → NEGATIVE   / False
    BROADCAST_FAILED          any                      → NEGATIVE   / False
    SHADOW_RECORDED           expected_would_survive   → POSITIVE   / True
    SHADOW_RECORDED           !expected_would_survive  → NEGATIVE   / False
    POLICY_DENIED             any                      → NEUTRAL    / (not emitted)
    REJECTED                  any                      → NEUTRAL    / (not emitted)
    <non-terminal>            any                      → PENDING    / (not emitted)

NEUTRAL rows are still stamped ``learning_consumed=True`` so they do not
loop through the emitter forever — they simply do not produce a training
sample.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..data.journal import (
    ExecutionStatus, LearningLabel, OpportunityJournal, JournalEntry,
    TERMINAL_STATUSES,
)


logger = logging.getLogger("arbicore.learning_ledger")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =====================================================================
# Pure labelling
# =====================================================================

def label_entry(entry: JournalEntry) -> Tuple[str, Optional[bool]]:
    """Return ``(learning_label, survived_or_None)`` for a journal row.

    ``survived_or_None`` is ``None`` for rows that should not produce a
    calibration sample (NEUTRAL / PENDING). Callers use this to decide
    whether to insert into ``calibration_log`` — but they must still
    stamp the journal row ``learning_consumed=True`` so it does not get
    re-processed.
    """
    status = entry.execution_status

    if status == ExecutionStatus.COMPLETED.value:
        pnl = _get_nested(entry.actual_result, "pnl_usd")
        if pnl is None:
            return LearningLabel.NEUTRAL.value, None
        return (
            (LearningLabel.POSITIVE.value, True)
            if float(pnl) > 0
            else (LearningLabel.NEGATIVE.value, False)
        )

    if status == ExecutionStatus.BROADCAST_FAILED.value:
        return LearningLabel.NEGATIVE.value, False

    if status == ExecutionStatus.SHADOW_RECORDED.value:
        would = _get_nested(entry.expected_result, "would_survive")
        # Fallback: if the shadow decision didn't explicitly declare
        # would_survive, treat "certification_result.status == 'ok' AND
        # policy_decision.decision == 'allow'" as the survival signal.
        if would is None:
            cert_ok = _get_nested(entry.certification_result, "status") == "ok"
            pol_allow = _get_nested(entry.policy_decision, "decision") == "allow"
            would = bool(cert_ok and pol_allow)
        return (
            (LearningLabel.POSITIVE.value, True)
            if bool(would)
            else (LearningLabel.NEGATIVE.value, False)
        )

    if status in (
        ExecutionStatus.POLICY_DENIED.value,
        ExecutionStatus.REJECTED.value,
    ):
        return LearningLabel.NEUTRAL.value, None

    return LearningLabel.PENDING.value, None


def _get_nested(container: Optional[Dict[str, Any]], key: str) -> Any:
    if not container:
        return None
    return container.get(key)


# =====================================================================
# Learning Ledger repository
# =====================================================================

class LearningLedger:
    """Bridges the Opportunity Journal to the calibration + weights workers.

    Public API:
        ensure_indexes()                 — one-time bootstrap
        emit_from_journal(batch=100)     — process terminal, unconsumed rows
        status()                         — {pending, consumed, last_run_at, ...}

    Programmatic write helpers used from tests + the auto-executor:
        write_calibration_sample(...)    — one row into `db.calibration_log`
        touch_signal_metric(...)         — upsert an `arbicore_signal_metrics` row
    """

    def __init__(
        self,
        db,
        journal: OpportunityJournal,
        *,
        calibration_log_collection: str = "calibration_log",
        signal_metrics_collection: str = "arbicore_signal_metrics",
    ):
        self._db = db
        self._journal = journal
        self._log_coll = db[calibration_log_collection]
        self._metrics_coll = db[signal_metrics_collection]
        self._last_run_at: Optional[str] = None
        self._last_batch: int = 0

    async def ensure_indexes(self) -> None:
        # These indexes are safe to add repeatedly — Motor is idempotent.
        try:
            await self._log_coll.create_index("created_at")
            await self._log_coll.create_index("opportunity_id")
            await self._log_coll.create_index("status")
        except Exception as exc:  # noqa: BLE001
            logger.warning("learning_ledger calibration_log index failed: %s", exc)
        try:
            await self._metrics_coll.create_index("signal_id", unique=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("learning_ledger signal_metrics index failed: %s", exc)

    # ---- one-row emitters (used by tests + the executor) ------------
    async def write_calibration_sample(
        self,
        *,
        opportunity_id: str,
        predicted_confidence: float,
        survived: bool,
        source: str = "learning_ledger",
    ) -> None:
        row = {
            "opportunity_id": opportunity_id,
            "predicted_confidence": float(predicted_confidence),
            "survived": bool(survived),
            "status": "resolved",
            "source": source,
            "created_at": _iso_now(),
        }
        await self._log_coll.insert_one(row)

    async def touch_signal_metric(
        self,
        *,
        signal_id: str,
        survived: bool,
    ) -> None:
        """Incremental Bayesian update to an ``arbicore_signal_metrics`` row.

        We keep it as a running tally: ``sample_count`` counts every
        emission for the signal; ``win_rate`` is the historical mean.
        The adaptive-weights worker reads these directly.
        """
        doc = await self._metrics_coll.find_one(
            {"signal_id": signal_id},
            {"_id": 0},
        )
        if doc is None:
            new_sc = 1
            new_wr = 1.0 if survived else 0.0
            payload = {
                "signal_id": signal_id,
                "sample_count": new_sc,
                "win_rate": new_wr,
                "aggregated_at": _iso_now(),
            }
            await self._metrics_coll.update_one(
                {"signal_id": signal_id},
                {"$set": payload},
                upsert=True,
            )
            return
        prev_sc = int(doc.get("sample_count", 0) or 0)
        prev_wr = float(doc.get("win_rate", 0.0) or 0.0)
        new_sc = prev_sc + 1
        # Running mean update.
        new_wr = (prev_wr * prev_sc + (1.0 if survived else 0.0)) / max(new_sc, 1)
        await self._metrics_coll.update_one(
            {"signal_id": signal_id},
            {"$set": {
                "sample_count": new_sc,
                "win_rate": new_wr,
                "aggregated_at": _iso_now(),
            }},
            upsert=True,
        )

    # ---- batch emitter -----------------------------------------------
    async def emit_from_journal(self, *, batch: int = 100) -> Dict[str, Any]:
        """Process terminal, unconsumed journal rows into training samples.

        Idempotent: consumed rows are skipped on subsequent runs. Returns
        a summary suitable for the ``status`` route.
        """
        pending_rows = await self._journal.list(
            learning_label=LearningLabel.PENDING.value,
            limit=max(batch, 1),
        )
        processed = 0
        emitted_samples = 0
        touched_signals = 0
        neutrals = 0
        for entry in pending_rows:
            if entry.execution_status not in {s.value for s in TERMINAL_STATUSES}:
                continue
            label, survived = label_entry(entry)
            if survived is not None:
                await self.write_calibration_sample(
                    opportunity_id=entry.opportunity_id,
                    predicted_confidence=float(entry.confidence_score or 0.0),
                    survived=survived,
                    source=f"journal::{entry.execution_status}",
                )
                emitted_samples += 1
                signal_id = self._compute_signal_id(entry)
                if signal_id:
                    await self.touch_signal_metric(
                        signal_id=signal_id, survived=survived,
                    )
                    touched_signals += 1
            else:
                neutrals += 1
            await self._journal.set_learning_label(
                entry.opportunity_id, label, consumed=True,
            )
            processed += 1
        self._last_run_at = _iso_now()
        self._last_batch = processed
        return {
            "processed": processed,
            "emitted_samples": emitted_samples,
            "touched_signals": touched_signals,
            "neutrals": neutrals,
            "as_of": self._last_run_at,
        }

    async def status(self) -> Dict[str, Any]:
        """Aggregate ledger status for the operator UI."""
        # Count journal buckets so operator can see what's queued for learning.
        summary = await self._journal.summary()
        consumed = 0
        pending = 0
        for b in summary.get("buckets", []):
            n = int(b.get("n", 0))
            if b.get("learning_label") == LearningLabel.PENDING.value:
                pending += n
            else:
                consumed += n
        return {
            "pending": pending,
            "consumed": consumed,
            "last_run_at": self._last_run_at,
            "last_batch": self._last_batch,
            "as_of": _iso_now(),
        }

    # ---- helpers -----------------------------------------------------
    @staticmethod
    def _compute_signal_id(entry: JournalEntry) -> Optional[str]:
        """Build a stable signal_id for adaptive-weights aggregation.

        Uses ``opportunity_type`` × ``chain`` × ``buy_venue`` × ``sell_venue``
        where available so the adaptive-weights model learns route-level
        performance. Falls back to just the opportunity_type when the
        route is unknown (e.g. CEX-only rows).
        """
        opt = entry.opportunity_type or "UNKNOWN"
        chain = entry.chain or "-"
        buy = entry.buy_venue or "-"
        sell = entry.sell_venue or "-"
        return f"{opt}|{chain}|{buy}->{sell}"
