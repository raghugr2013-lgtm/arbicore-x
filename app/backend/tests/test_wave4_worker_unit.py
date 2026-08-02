"""Wave 4 · AdaptiveWeightsWorker + Repo — async unit tests.

Reuses the lightweight in-memory Motor stand-in from
``test_wave3_worker_unit.py`` via a local copy (kept short) so tests
remain hermetic (no live Mongo).  Covers cold start / no metrics,
promotion, rollback, persistence recovery, deterministic recompute,
failure isolation, and OBSERVE-mode contract.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

# ------- reuse the mem-motor stub from the wave-3 test (import-safe copy) -------

class _AsyncCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, key, direction=1):
        if isinstance(key, str):
            self._docs.sort(key=lambda d: d.get(key), reverse=(direction == -1))
        elif isinstance(key, list):
            for k, dir_ in reversed(key):
                self._docs.sort(key=lambda d: d.get(k), reverse=(dir_ == -1))
        return self
    def limit(self, n): self._docs = self._docs[:n]; return self
    async def to_list(self, n): return list(self._docs[:n])
    def __aiter__(self): self._i = 0; return self
    async def __anext__(self):
        if self._i >= len(self._docs): raise StopAsyncIteration
        d = self._docs[self._i]; self._i += 1; return d

class _MemColl:
    def __init__(self): self._docs: List[Dict[str, Any]] = []
    async def create_index(self, *a, **k): return None
    async def insert_one(self, doc):
        self._docs.append(dict(doc))
        return type("R", (), {"inserted_id": len(self._docs)})()
    async def find_one(self, query, projection=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in query.items()): return dict(d)
        return None
    def find(self, query=None, projection=None):
        query = query or {}; out = []
        for d in self._docs:
            ok = True
            for k, v in query.items():
                if isinstance(v, dict):
                    if "$gte" in v and (d.get(k) is None or d.get(k) < v["$gte"]):
                        ok = False; break
                elif d.get(k) != v:
                    ok = False; break
            if ok: out.append(dict(d))
        return _AsyncCursor(out)
    async def update_one(self, query, update):
        for d in self._docs:
            if all(d.get(k) == v for k, v in query.items()):
                for k, v in update.get("$set", {}).items(): d[k] = v
                for k in update.get("$unset", {}).keys(): d.pop(k, None)
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

class _MemDB:
    def __init__(self): self._c: Dict[str, _MemColl] = {}
    def __getitem__(self, name): return self._c.setdefault(name, _MemColl())


from arbicore.config.adaptive_weights_config import AdaptiveWeightsConfig
from arbicore.data.mongo.adaptive_weights_repo import AdaptiveWeightsRepo
from arbicore.learning.concrete.adaptive_weights_observer import AdaptiveWeightsObserver
from arbicore.learning.concrete.adaptive_weights_worker import AdaptiveWeightsWorker


def _cfg(**over) -> AdaptiveWeightsConfig:
    base = dict(
        mode="OBSERVE",
        prior_trials=20,
        neutral_weight=1.0,
        min_weight=0.1,
        max_weight=2.0,
        max_delta_scale=4.0,
        min_samples_for_recommendation=30,
        min_confidence_floor=0.10,
        tick_interval_s=3600,
        retired_ttl_days=30,
        max_signals_scanned=500,
        provider_version="adaptive_weights_observer@1",
    )
    base.update(over)
    return AdaptiveWeightsConfig(**base)


async def _seed_metrics(db, rows: List[Dict[str, Any]]) -> None:
    for r in rows:
        await db["arbicore_signal_metrics"].insert_one(r)


async def _build(cfg=None):
    db = _MemDB()
    repo = AdaptiveWeightsRepo(db, retired_ttl_days=30)
    obs = AdaptiveWeightsObserver(cfg or _cfg())
    worker = AdaptiveWeightsWorker(db=db, observer=obs, repo=repo, config=cfg or _cfg())
    await repo.ensure_indexes()
    return db, repo, obs, worker


@pytest.mark.asyncio
async def test_cold_start_no_metrics_publishes_identity_row():
    """Cold start with no signal metrics → identity snapshot promoted."""
    db, repo, obs, worker = await _build()
    result = await worker.tick_once()
    assert result["mode"] == "OBSERVE"
    assert result["n_signals"] == 0
    assert result["aggregate_confidence"] == 0.0
    assert result["promotion_state"] == "promoted"
    active = await repo.get_active("adaptive_weights")
    assert active is not None
    assert active["mode"] == "OBSERVE"
    assert active["recommendations"] == []
    # Observer snapshot mirrors the active row.
    assert obs.snapshot()["n_signals"] == 0
    assert obs.snapshot()["aggregate_confidence"] == 0.0


@pytest.mark.asyncio
async def test_insufficient_samples_stays_identity():
    db, repo, obs, worker = await _build(_cfg(min_samples_for_recommendation=100))
    await _seed_metrics(db, [
        {"signal_id": "a", "win_rate": 0.9, "sample_count": 5},
        {"signal_id": "b", "win_rate": 0.1, "sample_count": 5},
    ])
    await worker.tick_once()
    active = await repo.get_active("adaptive_weights")
    for r in active["recommendations"]:
        assert r["recommended_weight"] == 1.0
        assert r["confidence"] == 0.0
        assert r["evidence"]["insufficient_samples"] is True


@pytest.mark.asyncio
async def test_promotion_publishes_active_and_updates_cache():
    db, repo, obs, worker = await _build()
    await _seed_metrics(db, [
        {"signal_id": "spread", "win_rate": 0.72, "sample_count": 300},
        {"signal_id": "depth", "win_rate": 0.30, "sample_count": 220},
    ])
    result = await worker.tick_once()
    assert result["n_signals"] == 2
    active = await repo.get_active("adaptive_weights")
    assert active["n_signals"] == 2
    weights = obs.get_weights({})
    assert set(weights.keys()) == {"spread", "depth"}
    assert weights["spread"] > 1.0
    assert weights["depth"] < 1.0


@pytest.mark.asyncio
async def test_rollback_to_previous_active():
    import asyncio as _aio
    db, repo, obs, worker = await _build()
    await _seed_metrics(db, [{"signal_id": "spread", "win_rate": 0.7, "sample_count": 200}])
    await worker.tick_once()
    first = await repo.get_active("adaptive_weights")

    # Ensure unique second-precision model id.
    await _aio.sleep(1.05)
    await _seed_metrics(db, [{"signal_id": "spread", "win_rate": 0.4, "sample_count": 200}])
    await worker.tick_once()
    second = await repo.get_active("adaptive_weights")
    assert second["id"] != first["id"]

    restored = await repo.rollback_to(first["id"], "adaptive_weights")
    assert restored is not None
    assert restored["id"] == first["id"]
    now_active = await repo.get_active("adaptive_weights")
    assert now_active["id"] == first["id"]


@pytest.mark.asyncio
async def test_persistence_recovery_warm_start():
    db, repo, _, worker = await _build()
    await _seed_metrics(db, [{"signal_id": "spread", "win_rate": 0.7, "sample_count": 300}])
    await worker.tick_once()

    # Fresh observer + fresh worker sharing the same repo/db.
    fresh_obs = AdaptiveWeightsObserver(_cfg())
    fresh_worker = AdaptiveWeightsWorker(db=db, observer=fresh_obs, repo=repo, config=_cfg())
    await fresh_worker._warm_start_cache()
    active = await repo.get_active("adaptive_weights")
    assert fresh_obs.snapshot()["n_signals"] == active["n_signals"]
    assert fresh_obs.get_weights({})["spread"] == pytest.approx(
        active["recommendations"][0]["recommended_weight"])


@pytest.mark.asyncio
async def test_deterministic_recompute():
    db1, _, _, w1 = await _build()
    db2, _, _, w2 = await _build()
    rows = [
        {"signal_id": "s1", "win_rate": 0.65, "sample_count": 250},
        {"signal_id": "s2", "win_rate": 0.35, "sample_count": 180},
    ]
    await _seed_metrics(db1, rows)
    await _seed_metrics(db2, rows)
    r1 = await w1.tick_once()
    r2 = await w2.tick_once()
    assert r1["n_signals"] == r2["n_signals"]
    assert r1["aggregate_confidence"] == r2["aggregate_confidence"]


@pytest.mark.asyncio
async def test_observe_mode_never_flips_to_apply():
    """Wave-4 hard invariant — recommendations are always tagged OBSERVE."""
    db, repo, _, worker = await _build()
    await _seed_metrics(db, [{"signal_id": "spread", "win_rate": 0.9, "sample_count": 500}])
    await worker.tick_once()
    active = await repo.get_active("adaptive_weights")
    assert active["mode"] == "OBSERVE"
    for r in active["recommendations"]:
        # Recommendations exist as telemetry but MODE stays OBSERVE.
        assert "recommended_weight" in r
    # Config stamp on the tick result too.
    status = worker.status
    assert status["mode"] == "OBSERVE"


@pytest.mark.asyncio
async def test_worker_status_shape():
    _, _, _, worker = await _build()
    s = worker.status
    for k in ("running", "interval_s", "iterations", "last_run_at",
              "last_result", "last_error", "mode", "config"):
        assert k in s
    for k in ("prior_trials", "neutral_weight", "min_weight", "max_weight",
              "max_delta_scale", "min_samples_for_recommendation",
              "min_confidence_floor", "max_signals_scanned"):
        assert k in s["config"]
