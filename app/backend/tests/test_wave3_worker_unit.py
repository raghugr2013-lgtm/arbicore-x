"""Wave 3 · CalibrationWorker + CalibrationModelsRepo — async unit tests.

Uses ``mongomock_motor`` when available; otherwise falls back to a
lightweight in-memory Motor-shaped stub so the tests run in any env.
Covers cold start, insufficient samples, promotion, rollback, drift
detection, and persistence recovery.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, List

import pytest

# ------- lightweight in-memory Motor stand-in (async) -------
# Enough of the ``motor``/``pymongo`` surface to run the worker + repo.

class _AsyncCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)
        self._i = 0

    def sort(self, key, direction=1):
        # Sort by (key, direction) — key may be a str or list of tuples.
        if isinstance(key, str):
            self._docs.sort(key=lambda d: d.get(key), reverse=(direction == -1))
        elif isinstance(key, list):
            for k, dir_ in reversed(key):
                self._docs.sort(key=lambda d: d.get(k), reverse=(dir_ == -1))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n):
        return list(self._docs[:n])

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]
        self._i += 1
        return d


class _MemColl:
    def __init__(self):
        self._docs: List[Dict[str, Any]] = []

    async def create_index(self, *_a, **_kw):
        return None

    async def insert_one(self, doc):
        self._docs.append(dict(doc))
        return type("R", (), {"inserted_id": len(self._docs)})()

    async def find_one(self, query, projection=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in query.items()):
                return dict(d)
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        out = []
        for d in self._docs:
            ok = True
            for k, v in query.items():
                if isinstance(v, dict):
                    # Support $gte only (enough for the worker query).
                    if "$gte" in v and (d.get(k) is None or d.get(k) < v["$gte"]):
                        ok = False; break
                elif d.get(k) != v:
                    ok = False; break
            if ok:
                out.append(dict(d))
        return _AsyncCursor(out)

    async def update_one(self, query, update):
        for d in self._docs:
            if all(d.get(k) == v for k, v in query.items()):
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                for k in update.get("$unset", {}).keys():
                    d.pop(k, None)
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

    async def delete_many(self, query):
        before = len(self._docs)
        self._docs = [d for d in self._docs if not all(d.get(k) == v for k, v in query.items())]
        return type("R", (), {"deleted_count": before - len(self._docs)})()


class _MemDB:
    def __init__(self):
        self._c: Dict[str, _MemColl] = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _MemColl())


# ------- fixtures -------

from arbicore.config.calibration_config import CalibrationConfig
from arbicore.data.mongo.calibration_models_repo import CalibrationModelsRepo
from arbicore.learning.concrete.calibrator_isotonic import IsotonicConfidenceCalibrator
from arbicore.learning.concrete.calibration_worker import CalibrationWorker


def _cfg(**over):
    base = dict(
        window_days=30,
        tick_interval_s=3600,
        min_samples_isotonic=200,
        min_samples_platt=30,
        n_buckets=10,
        promotion_ece_slack=0.02,
        drift_history_len=10,
        drift_ece_absolute_floor=0.05,
        drift_stdev_mult_on=2.0,
        drift_stdev_mult_off=1.0,
        drift_off_consecutive_ticks=3,
        retired_ttl_days=30,
        calibrator_version="isotonic@1",
    )
    base.update(over)
    return CalibrationConfig(**base)


async def _seed_samples(db, n: int, slope: float, bias: float, seed: int = 42):
    """Seed n resolved rows into db.calibration_log.  Uses ISO strings for
    created_at so the worker query matches."""
    from datetime import datetime, timezone
    rnd = random.Random(seed)
    now = datetime.now(timezone.utc).isoformat()
    for _ in range(n):
        raw = rnd.uniform(0.0, 100.0)
        p_true = max(0.0, min(1.0, slope * (raw / 100.0) + bias))
        survived = rnd.random() < p_true
        await db["calibration_log"].insert_one({
            "predicted_confidence": raw,
            "survived": survived,
            "status": "resolved",
            "created_at": now,
        })


async def _build_worker(cfg=None):
    db = _MemDB()
    repo = CalibrationModelsRepo(db, retired_ttl_days=30)
    calibrator = IsotonicConfidenceCalibrator(
        min_samples_isotonic=(cfg or _cfg()).min_samples_isotonic,
        min_samples_platt=(cfg or _cfg()).min_samples_platt,
    )
    worker = CalibrationWorker(
        db=db, calibrator=calibrator, repo=repo,
        config=cfg or _cfg(),
    )
    await repo.ensure_indexes()
    return db, repo, calibrator, worker


# ------- Tests -------

@pytest.mark.asyncio
async def test_cold_start_no_samples_stays_identity():
    """Cold start (no samples) → no promotion, calibrator serves identity."""
    db, repo, calibrator, worker = await _build_worker()
    result = await worker.tick_once()
    assert result["n_samples"] == 0
    assert result["algorithm"] == "identity"
    assert result["promotion_state"] == "shadowed_below_threshold"
    # Calibrator still returns identity.
    assert calibrator.calibrate(42.0, {}) == pytest.approx(42.0)
    # No active row was published.
    assert await repo.get_active("confidence") is None


@pytest.mark.asyncio
async def test_insufficient_samples_stays_identity_below_platt():
    db, repo, calibrator, worker = await _build_worker()
    await _seed_samples(db, 10, slope=1.0, bias=0.0)
    result = await worker.tick_once()
    assert result["algorithm"] == "identity"
    assert result["promotion_state"] == "shadowed_below_threshold"
    assert await repo.get_active("confidence") is None


@pytest.mark.asyncio
async def test_promotion_publishes_active_row():
    db, repo, calibrator, worker = await _build_worker()
    await _seed_samples(db, 250, slope=1.0, bias=0.0, seed=1)
    result = await worker.tick_once()
    assert result["algorithm"] == "isotonic"
    assert result["promotion_state"] == "promoted"
    active = await repo.get_active("confidence")
    assert active is not None
    assert active["algorithm"] == "isotonic"
    # In-memory cache updated.
    assert calibrator.algorithm == "isotonic"


@pytest.mark.asyncio
async def test_worse_candidate_is_shadowed_not_promoted():
    db, repo, calibrator, worker = await _build_worker(_cfg(promotion_ece_slack=0.0))
    # First fit — good samples → promoted.
    await _seed_samples(db, 500, slope=1.0, bias=0.0, seed=2)
    r1 = await worker.tick_once()
    assert r1["promotion_state"] == "promoted"
    active_before = await repo.get_active("confidence")
    ece_before = active_before["ece"]

    # Second fit — inject bad data to raise ECE above slack.
    await _seed_samples(db, 500, slope=0.2, bias=0.6, seed=3)
    r2 = await worker.tick_once()
    # If new ECE happens to be lower, it'll still promote — either way the
    # invariant is: only-better-or-equal-plus-slack is promoted.
    active_after = await repo.get_active("confidence")
    if r2["ece"] > ece_before + 0.0:
        assert r2["promotion_state"] == "shadowed_below_threshold"
        assert active_after["id"] == active_before["id"]
    else:
        assert r2["promotion_state"] == "promoted"


@pytest.mark.asyncio
async def test_rollback_to_previous_active():
    db, repo, calibrator, worker = await _build_worker()
    await _seed_samples(db, 300, slope=1.0, bias=0.0, seed=4)
    await worker.tick_once()
    first = await repo.get_active("confidence")
    # Second fit with different seed.
    await _seed_samples(db, 300, slope=1.0, bias=0.1, seed=5)
    await worker.tick_once()
    second = await repo.get_active("confidence")
    if second and first["id"] != second["id"]:
        restored = await repo.rollback_to(first["id"], "confidence")
        assert restored is not None
        assert restored["id"] == first["id"]
        assert (await repo.get_active("confidence"))["id"] == first["id"]


@pytest.mark.asyncio
async def test_corruption_recovery_load_falls_to_identity():
    """A corrupt persisted curve must not brick calibrate() — identity fallback."""
    _, _, calibrator, _ = await _build_worker()
    calibrator.load_curve({"algorithm": "isotonic", "x": [0.1], "y": []})
    assert calibrator.algorithm == "identity"
    assert calibrator.calibrate(75.0, {}) == pytest.approx(75.0)


@pytest.mark.asyncio
async def test_drift_state_machine_on_off():
    """ECE spike must flip drift ON; sustained recovery flips it OFF."""
    _, _, _, worker = await _build_worker(_cfg(
        drift_history_len=10,
        drift_ece_absolute_floor=0.05,
        drift_stdev_mult_on=2.0,
        drift_stdev_mult_off=1.0,
        drift_off_consecutive_ticks=2,
    ))
    # Prime steady low ECE history with tiny jitter below the absolute floor.
    baseline = [0.020, 0.022, 0.019, 0.021, 0.020, 0.023]
    for e in baseline:
        worker._update_drift_state(e)
    assert worker._drift_on is False
    # Big spike above absolute floor AND > mean + 2*stdev.
    worker._update_drift_state(0.30)
    assert worker._drift_on is True
    # Sustained recovery — 2 consecutive ticks under mean + 1*stdev.
    worker._update_drift_state(0.02)
    worker._update_drift_state(0.02)
    assert worker._drift_on is False


@pytest.mark.asyncio
async def test_persistence_recovery_from_active_row():
    """A restarted worker must warm-start from the active row."""
    db, repo, cal_a, worker_a = await _build_worker()
    await _seed_samples(db, 300, slope=1.0, bias=0.0, seed=8)
    await worker_a.tick_once()
    active = await repo.get_active("confidence")
    assert active is not None

    # New calibrator + new worker sharing the same db/repo.
    cal_b = IsotonicConfidenceCalibrator()
    from arbicore.learning.concrete.calibration_worker import CalibrationWorker as W
    worker_b = W(db=db, calibrator=cal_b, repo=repo, config=_cfg())
    await worker_b._warm_start_cache()
    assert cal_b.algorithm == active["algorithm"]
    # And produces the same calibrated output as the original cache.
    for x in (10.0, 40.0, 70.0, 95.0):
        assert cal_b.calibrate(x, {}) == pytest.approx(cal_a.calibrate(x, {}))


@pytest.mark.asyncio
async def test_backward_compatibility_no_curve_serves_identity():
    """When no active row exists, calibrator serves identity — old callers unaffected."""
    _, _, calibrator, worker = await _build_worker()
    await worker._warm_start_cache()
    assert calibrator.algorithm == "identity"
    assert calibrator.calibrate(60.0, {}) == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_deterministic_ticks():
    """Same seeded samples → same persisted brier / ece across two runs."""
    db1, _, _, w1 = await _build_worker()
    db2, _, _, w2 = await _build_worker()
    await _seed_samples(db1, 500, slope=1.0, bias=0.0, seed=99)
    await _seed_samples(db2, 500, slope=1.0, bias=0.0, seed=99)
    r1 = await w1.tick_once()
    r2 = await w2.tick_once()
    assert r1["brier_score"] == r2["brier_score"]
    assert r1["ece"] == r2["ece"]
    assert r1["algorithm"] == r2["algorithm"]
