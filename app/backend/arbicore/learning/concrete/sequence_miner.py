"""ArbiCore X — Sequence Miner (Phase C Wave 3).

Discovers recurring temporal patterns of regime states preceding successful
or unsuccessful outcomes. The miner is category-agnostic — it operates only
on (regime_snapshot, outcome) sequences pulled from the universal
collections.

Algorithm (intentionally simple, deterministic, replay-safe):

  1. Pull recent regime snapshots ordered by captured_at.
  2. Pull recent evaluated outcomes ordered by evaluated_at_ts.
  3. For each evaluated outcome, build a "preceding context" = the last K
     regime snapshots whose captured_at <= outcome.evaluated_at_ts.
  4. Encode the context as a tuple of dominant_regime values (lengths 2 and 3).
  5. Increment counters per (context, succeeded?) into in-memory maps.
  6. Convert counts into ``SequencePattern`` rows with support + confidence.
  7. Persist patterns to ``arbicore_sequence_patterns`` (replace-by-pattern_id).

No exchange / asset / category strings appear in this module.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ...data.mongo.arbicore_collections import get_collection
from ...data.regime_snapshot_repo import RegimeSnapshotRepository


CONTEXT_LENGTHS = (2, 3)
MIN_SUPPORT = 2   # minimum occurrences before a pattern is recorded


@dataclass
class SequencePattern:
    pattern_id: str
    sequence: List[str]
    occurrences: int
    succeeded_count: int
    failed_count: int
    support: int
    confidence: float        # succeeded / total (smoothed)
    last_seen_at: float
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _pattern_id(sequence: List[str]) -> str:
    raw = "→".join(sequence)
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"seq:{h}"


def _smoothed_confidence(succeeded: int, total: int) -> float:
    """Laplace-smoothed proportion (prior = 1 success + 1 failure)."""
    if total <= 0:
        return 0.5
    return (succeeded + 1) / (total + 2)


class SequenceMiner:

    def __init__(self,
                 regime_repo: RegimeSnapshotRepository,
                 max_outcomes: int = 1000,
                 max_regime_snapshots: int = 2000):
        self._regimes = regime_repo
        self._max_outcomes = int(max_outcomes)
        self._max_regimes = int(max_regime_snapshots)

    @property
    def _outcomes_col(self):
        return get_collection("outcomes")

    @property
    def _sequences_col(self):
        return get_collection("temporal_sequences")

    @property
    def _patterns_col(self):
        return get_collection("sequence_patterns")

    async def mine(self) -> Dict[str, Any]:
        """Run one pass. Idempotent; pattern rows are upserted by pattern_id."""
        # 1. Pull regime snapshots (oldest first to make windowing easy)
        regime_rows = await self._regimes.list_since(t0=0.0, limit=self._max_regimes)
        regime_rows = sorted(regime_rows, key=lambda r: r.captured_at)

        # 2. Pull evaluated outcomes
        cursor = self._outcomes_col.find(
            {"evaluated": True,
             "realized_outcome.succeeded": {"$exists": True}},
            {"_id": 0, "evaluated_at_ts": 1, "realized_outcome": 1},
        ).sort([("updated_at", -1)]).limit(self._max_outcomes)
        outcomes = [d async for d in cursor]

        if not regime_rows or not outcomes:
            return {"regime_count": len(regime_rows),
                    "outcome_count": len(outcomes),
                    "patterns_written": 0,
                    "patterns_seen": 0}

        # 3. Build per-pattern counters
        counters: Dict[Tuple[str, ...], Dict[str, int]] = {}
        now = time.time()

        regime_ts = [r.captured_at for r in regime_rows]
        regime_seq = [r.dominant_regime for r in regime_rows]

        from bisect import bisect_right

        for out in outcomes:
            ts = out.get("updated_at") or out.get("evaluated_at_ts") or now
            ts = float(ts)
            cut = bisect_right(regime_ts, ts)
            for length in CONTEXT_LENGTHS:
                if cut < length:
                    continue
                ctx = tuple(regime_seq[cut - length:cut])
                bucket = counters.setdefault(ctx, {"succeeded": 0, "failed": 0})
                if bool(out["realized_outcome"].get("succeeded")):
                    bucket["succeeded"] += 1
                else:
                    bucket["failed"] += 1

        # 4. Materialize SequencePattern + persist
        written = 0
        seen = 0
        for ctx, bucket in counters.items():
            seen += 1
            total = bucket["succeeded"] + bucket["failed"]
            if total < MIN_SUPPORT:
                continue
            pid = _pattern_id(list(ctx))
            pattern = SequencePattern(
                pattern_id=pid,
                sequence=list(ctx),
                occurrences=total,
                succeeded_count=bucket["succeeded"],
                failed_count=bucket["failed"],
                support=total,
                confidence=_smoothed_confidence(bucket["succeeded"], total),
                last_seen_at=now,
            )
            await self._patterns_col.update_one(
                {"pattern_id": pid},
                {"$set": pattern.to_dict()},
                upsert=True,
            )
            written += 1

        return {
            "regime_count": len(regime_rows),
            "outcome_count": len(outcomes),
            "patterns_seen": seen,
            "patterns_written": written,
        }

    async def list_patterns(self,
                            limit: int = 100,
                            min_support: int = MIN_SUPPORT,
                            ) -> List[SequencePattern]:
        cursor = self._patterns_col.find(
            {"support": {"$gte": int(min_support)}},
            {"_id": 0},
        ).sort([("support", -1), ("confidence", -1)]).limit(limit)
        return [SequencePattern(**d) async for d in cursor]

    async def count(self) -> int:
        return await self._patterns_col.count_documents({})
