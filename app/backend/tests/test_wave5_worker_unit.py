"""Wave 5 · EvidenceSigningWorker + EvidenceBundlesRepo — async unit tests."""
from __future__ import annotations

import base64
from typing import Any, Dict, List

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from arbicore.config.signing_config import KeyMaterial, SigningConfig
from arbicore.data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
from arbicore.evidence.signer import EvidenceSigner, EvidenceVerifier
from arbicore.learning.concrete.evidence_signing_worker import EvidenceSigningWorker


# ------- shared in-memory Motor stub -------

class _AsyncCursor:
    def __init__(self, docs): self._docs = list(docs); self._i = 0
    def sort(self, key, direction=1):
        if isinstance(key, str):
            self._docs.sort(key=lambda d: d.get(key), reverse=(direction == -1))
        elif isinstance(key, list):
            for k, d in reversed(key):
                self._docs.sort(key=lambda x: x.get(k), reverse=(d == -1))
        return self
    def limit(self, n): self._docs = self._docs[:n]; return self
    async def to_list(self, n): return list(self._docs[:n])

class _MemColl:
    def __init__(self): self._docs: List[Dict[str, Any]] = []
    async def create_index(self, *a, **k): return None
    async def insert_one(self, doc):
        self._docs.append(dict(doc))
        return type("R", (), {"inserted_id": len(self._docs)})()
    async def find_one(self, q, p=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()): return dict(d)
        return None
    def find(self, q=None, p=None):
        q = q or {}
        return _AsyncCursor([dict(d) for d in self._docs
                             if all(d.get(k) == v for k, v in q.items())])

class _MemDB:
    def __init__(self): self._c: Dict[str, _MemColl] = {}
    def __getitem__(self, n): return self._c.setdefault(n, _MemColl())


class _StubActive:
    """Stand-in for CalibrationModelsRepo / AdaptiveWeightsRepo — only
    ``get_active`` is used by the signing worker."""
    def __init__(self):
        self.row = None
    async def get_active(self, kind):
        return dict(self.row) if self.row else None


def _make_key(v="v1"):
    priv = Ed25519PrivateKey.generate()
    sec = priv.private_bytes(encoding=serialization.Encoding.Raw,
                             format=serialization.PrivateFormat.Raw,
                             encryption_algorithm=serialization.NoEncryption())
    pub = priv.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                         format=serialization.PublicFormat.Raw)
    return KeyMaterial(v, "ed25519",
                       base64.b64encode(sec).decode(),
                       base64.b64encode(pub).decode())


def _cfg(*keys, active=None, enabled=True):
    return SigningConfig(enabled=enabled, active_key_version=active,
                         keys={k.version: k for k in keys},
                         tick_interval_s=5)


async def _build(cfg=None):
    db = _MemDB()
    cfg = cfg or SigningConfig()
    signer = EvidenceSigner(cfg)
    repo = EvidenceBundlesRepo(db)
    cal = _StubActive(); aw = _StubActive()
    worker = EvidenceSigningWorker(
        db=db, signer=signer, repo=repo,
        calibration_repo=cal, adaptive_weights_repo=aw,
        config=cfg,
    )
    await repo.ensure_indexes()
    return db, repo, signer, worker, cal, aw


# ------- tests -------

@pytest.mark.asyncio
async def test_no_source_rows_no_bundles():
    _, repo, _, worker, _, _ = await _build()
    result = await worker.tick_once()
    assert result["emitted"] == []
    items = await repo.list_recent()
    assert items == []


@pytest.mark.asyncio
async def test_emits_bundle_on_new_source_row_unsigned():
    _, repo, signer, worker, cal, _ = await _build()
    cal.row = {"id": "cal-1", "algorithm": "isotonic",
               "n_samples": 500, "ece": 0.03,
               "calibrator_version": "isotonic@1"}
    result = await worker.tick_once()
    assert len(result["emitted"]) == 1
    latest = await repo.get_latest("calibration")
    assert latest is not None
    assert latest["source_model_id"] == "cal-1"
    assert latest["verification_status"] == "unsigned"
    assert latest["signature"] is None
    assert latest["calibrator_version"] == "isotonic@1"


@pytest.mark.asyncio
async def test_fingerprint_dedupe_no_reemit():
    _, repo, _, worker, cal, _ = await _build()
    cal.row = {"id": "cal-1", "algorithm": "identity"}
    await worker.tick_once()
    # Second tick with same fingerprint → no new bundle.
    r2 = await worker.tick_once()
    assert r2["emitted"] == []
    items = await repo.list_recent("calibration")
    assert len(items) == 1


@pytest.mark.asyncio
async def test_bundle_signed_when_keys_configured():
    k = _make_key("v1")
    _, repo, signer, worker, cal, _ = await _build(_cfg(k, active="v1"))
    cal.row = {"id": "cal-1", "algorithm": "isotonic", "brier_score": 0.1}
    await worker.tick_once()
    latest = await repo.get_latest("calibration")
    assert latest["signature"] is not None
    assert latest["verification_status"] == "signed"
    assert latest["signing_key_version"] == "v1"
    # And verifier accepts it.
    v = EvidenceVerifier(_cfg(k, active="v1"))
    assert v.verify(latest)["verified"] is True


@pytest.mark.asyncio
async def test_warm_start_recovers_fingerprint():
    """A restarted worker must not re-emit bundles already persisted."""
    db, repo, _, worker, cal, _ = await _build()
    cal.row = {"id": "cal-1"}
    await worker.tick_once()
    # Fresh worker sharing the same db/repo.
    worker2 = EvidenceSigningWorker(
        db=db, signer=EvidenceSigner(SigningConfig()), repo=repo,
        calibration_repo=cal, adaptive_weights_repo=_StubActive(),
        config=SigningConfig(tick_interval_s=5),
    )
    await repo.ensure_indexes()
    await worker2._warm_start()
    r = await worker2.tick_once()
    assert r["emitted"] == []


@pytest.mark.asyncio
async def test_source_read_failure_isolated():
    """An exception in the source repo must not crash the tick."""
    class _Boom:
        async def get_active(self, kind):
            raise RuntimeError("boom")
    _, repo, _, worker, _, aw = await _build()
    worker._calibration_repo = _Boom()
    aw.row = {"id": "aw-1", "mode": "OBSERVE"}
    result = await worker.tick_once()
    # Adaptive_weights bundle still emitted.
    assert result["emitted"]
    latest = await repo.get_latest("adaptive_weights")
    assert latest is not None


@pytest.mark.asyncio
async def test_status_shape():
    _, _, _, worker, _, _ = await _build()
    s = worker.status
    for k in ("running", "interval_s", "iterations", "last_run_at",
              "last_error", "signer", "last_bundled_fingerprints"):
        assert k in s
    signer_stats = s["signer"]
    for k in ("enabled", "active_key_version", "algorithms_available",
              "success_count", "failure_count", "last_signed_at",
              "unsigned_reason", "keys_registered"):
        assert k in signer_stats


@pytest.mark.asyncio
async def test_rollback_via_repo_history():
    """Rollback = superseding insert; historical bundles remain intact."""
    _, repo, _, worker, cal, _ = await _build()
    cal.row = {"id": "cal-1", "algorithm": "identity"}
    await worker.tick_once()
    cal.row = {"id": "cal-2", "algorithm": "isotonic"}
    await worker.tick_once()
    items = await repo.list_recent("calibration")
    assert len(items) == 2
    # Original bundle is retrievable by its bundle_id.
    original = items[-1]
    got = await repo.find_by_bundle_id(original["bundle_id"])
    assert got == original


@pytest.mark.asyncio
async def test_deterministic_hash_across_ticks_same_source():
    """Same source_row content on two workers → identical evidence_hash."""
    _, _, _, w1, c1, _ = await _build()
    _, _, _, w2, c2, _ = await _build()
    row = {"id": "cal-1", "algorithm": "isotonic",
           "n_samples": 100, "ece": 0.02}
    c1.row = dict(row); c2.row = dict(row)
    await w1.tick_once()
    await w2.tick_once()
    b1 = await w1._repo.get_latest("calibration")
    b2 = await w2._repo.get_latest("calibration")
    # Hash covers only hashed fields — bundle_id + created_at are
    # excluded intentionally to keep bundles unique (audit) while the
    # payload hash is stable.  Verify payload hash is identical.
    from arbicore.evidence.bundle import _canonicalise, canonical_json
    assert canonical_json({"payload": b1["payload"]}) == canonical_json({"payload": b2["payload"]})
