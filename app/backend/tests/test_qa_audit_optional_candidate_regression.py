"""QA (T1) independent adversarial regression for the audit-tooling blocker fix.

Covers, against a REAL Mongo instance where relevant:
  * EvidenceBundlesRepo.find_for_audit with candidate_id OMITTED (the exact
    blocker: caller has only audit_run_id + scanner_tick_id -> no TypeError)
  * run+tick remain MANDATORY at every layer (query / in-memory / repo)
  * NoSQL-operator selectors rejected at the repo layer too
  * Mongo _id never leaks into audit results
  * bundles with missing candidate provenance rejected even when candidate_id
    is omitted (fail closed)
  * vps_canonical_audit.py fails closed (rc=2 + audit_error) without env
  * run_single_canonical_flash_loan_audit_tick exposes the id keys and runs at
    most one tick (no background loop left running)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_test")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from arbicore.data.mongo.evidence_bundles_repo import EvidenceBundlesRepo  # noqa: E402
from arbicore.evidence.audit_provenance import (  # noqa: E402
    AuditProvenanceError, build_audit_evidence_query, evidence_matches_audit,
    filter_evidence_for_audit,
)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _bundle(run_id, tick, cand, status="CONFIRMED", worker="w-1"):
    return {
        "bundle_id": f"TEST_{uuid.uuid4().hex[:8]}",
        "source_component": "flash_loan_arb_verifier",
        "verification_status": status,
        "outcome_tag": "ok",
        "created_at": "2026-07-01T00:00:00Z",
        "diagnostics": {
            "audit_run_id": run_id, "scanner_tick_id": tick,
            "candidate_id": cand, "worker_id": worker,
        },
    }


# ---------------------------------------------------------------------------
# Repo layer against real Mongo — the blocker path
# ---------------------------------------------------------------------------

class TestRepoFindForAudit:
    def test_omitted_candidate_returns_all_candidates_of_run_tick(self):
        run = f"TEST_run_{uuid.uuid4().hex[:8]}"
        other_run = f"TEST_run_{uuid.uuid4().hex[:8]}"
        docs = [
            _bundle(run, 7, "cand-a"),
            _bundle(run, 7, "cand-b", status="REJECTED"),
            _bundle(run, 8, "cand-c"),            # other tick
            _bundle(other_run, 7, "cand-d"),      # foreign run
        ]

        async def go():
            db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
            repo = EvidenceBundlesRepo(db)
            await db["evidence_bundles"].insert_many([dict(d) for d in docs])
            try:
                # BLOCKER: only run + tick known
                all_c = await repo.find_for_audit(
                    audit_run_id=run, scanner_tick_id=7)
                pinned = await repo.find_for_audit(
                    audit_run_id=run, scanner_tick_id=7, candidate_id="cand-a")
                unknown = await repo.find_for_audit(
                    audit_run_id=run, scanner_tick_id=7,
                    candidate_id="cand-zzz")
                foreign_tick = await repo.find_for_audit(
                    audit_run_id=run, scanner_tick_id=99)
                foreign_run = await repo.find_for_audit(
                    audit_run_id=f"{run}-x", scanner_tick_id=7)
                confirmed = await repo.find_for_audit(
                    audit_run_id=run, scanner_tick_id=7,
                    verification_status="CONFIRMED")
                return all_c, pinned, unknown, foreign_tick, foreign_run, confirmed
            finally:
                await db["evidence_bundles"].delete_many(
                    {"bundle_id": {"$in": [d["bundle_id"] for d in docs]}})

        all_c, pinned, unknown, ftick, frun, confirmed = _run(go())
        assert {b["diagnostics"]["candidate_id"] for b in all_c} == {
            "cand-a", "cand-b"}
        assert len(pinned) == 1 and pinned[0]["diagnostics"]["candidate_id"] == "cand-a"
        assert unknown == [] and ftick == [] and frun == []
        assert {b["diagnostics"]["candidate_id"] for b in confirmed} == {"cand-a"}
        # no Mongo _id leakage
        assert all("_id" not in b for b in all_c)

    def test_repo_rejects_missing_run_tick_and_operator_selectors(self):
        async def go(**kw):
            db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
            return await EvidenceBundlesRepo(db).find_for_audit(**kw)

        for kw in (
            {"audit_run_id": "", "scanner_tick_id": 1},
            {"audit_run_id": None, "scanner_tick_id": 1},
            {"audit_run_id": "r", "scanner_tick_id": None},
            {"audit_run_id": "r", "scanner_tick_id": "  "},
            {"audit_run_id": {"$ne": None}, "scanner_tick_id": 1},
            {"audit_run_id": "r", "scanner_tick_id": {"$gte": 0}},
            {"audit_run_id": "r", "scanner_tick_id": 1,
             "candidate_id": {"$ne": None}},
            {"audit_run_id": "r", "scanner_tick_id": 1, "candidate_id": "  "},
            {"audit_run_id": "r", "scanner_tick_id": True},
            {"audit_run_id": "r", "scanner_tick_id": 1.5},
        ):
            with pytest.raises(AuditProvenanceError):
                _run(go(**kw))


# ---------------------------------------------------------------------------
# Pure function semantics
# ---------------------------------------------------------------------------

class TestOptionalCandidateSemantics:
    def test_query_omits_candidate_key_when_none(self):
        q = build_audit_evidence_query(audit_run_id="r1", scanner_tick_id=0)
        assert "diagnostics.candidate_id" not in q
        assert q["diagnostics.audit_run_id"] == "r1"
        assert q["diagnostics.scanner_tick_id"] == 0
        assert q["source_component"] == "flash_loan_arb_verifier"

    def test_missing_candidate_provenance_rejected_without_candidate_selector(self):
        b = _bundle("r1", 3, "cand-a")
        b["diagnostics"].pop("candidate_id")
        assert filter_evidence_for_audit(
            [b], audit_run_id="r1", scanner_tick_id=3) == []
        b2 = _bundle("r1", 3, "   ")
        assert filter_evidence_for_audit(
            [b2], audit_run_id="r1", scanner_tick_id=3) == []

    def test_candidate_alone_still_insufficient(self):
        b = _bundle("r1", 3, "cand-a")
        with pytest.raises(AuditProvenanceError):
            filter_evidence_for_audit([b], audit_run_id="", scanner_tick_id=3,
                                      candidate_id="cand-a")
        with pytest.raises(AuditProvenanceError):
            evidence_matches_audit(b, audit_run_id="r1", scanner_tick_id=None,
                                   candidate_id="cand-a")

    def test_worker_id_tiebreaker_isolates_concurrent_workers(self):
        a = _bundle("r1", 3, "cand-a", worker="w-1")
        b = _bundle("r1", 3, "cand-b", worker="w-2")
        got = filter_evidence_for_audit([a, b], audit_run_id="r1",
                                        scanner_tick_id=3, worker_id="w-2")
        assert [x["diagnostics"]["candidate_id"] for x in got] == ["cand-b"]

    def test_string_tick_not_equal_int_tick(self):
        b = _bundle("r1", 3, "cand-a")
        assert filter_evidence_for_audit(
            [b], audit_run_id="r1", scanner_tick_id="3") == []
        assert len(filter_evidence_for_audit(
            [b], audit_run_id="r1", scanner_tick_id=3)) == 1


# ---------------------------------------------------------------------------
# Runner script + composition surface
# ---------------------------------------------------------------------------

class TestRunnerFailClosed:
    def test_runner_rc2_without_mongo_env(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("MONGO_URL", "DB_NAME")}
        env["PYTHONPATH"] = BACKEND_DIR
        p = subprocess.run([sys.executable, "-m", "scripts.vps_canonical_audit"],
                           cwd=BACKEND_DIR, env=env, capture_output=True,
                           text=True, timeout=180)
        assert p.returncode == 2, p.stdout + p.stderr
        assert "audit_error" in p.stdout
        # never leaks a secret-looking key
        assert "PRIVATE" not in p.stdout.upper()

    def test_runner_source_never_signs_or_broadcasts(self):
        src = open(os.path.join(BACKEND_DIR, "scripts",
                                "vps_canonical_audit.py")).read()
        for forbidden in ("sign_transaction", "send_raw_transaction",
                          "broadcast(", "FULL_LIVE", "LIMITED_LIVE"):
            assert forbidden not in src, forbidden

    def test_single_tick_helper_exposes_actual_ids_and_no_loop(self):
        from arbicore.runtime import composition as c
        from arbicore.execution.quoter import QuoterRegistry
        meta = _run(c.run_single_canonical_flash_loan_audit_tick(
            QuoterRegistry()))
        for k in ("audit_run_id", "scanner_tick_id", "worker_id",
                  "tick_executed", "mode", "detection_only"):
            assert k in meta, k
        assert meta["mode"] == "single_audit_tick"
        assert meta["detection_only"] is True
        scanner = c.get_flash_loan_arb_scanner()
        # no background loop task was started by the single-tick helper
        task = getattr(scanner, "_task", None)
        assert task is None or task.done(), "background loop left running"
