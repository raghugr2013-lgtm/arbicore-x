"""Authoritative diagnostic-run evidence attribution — isolate the evidence
belonging to EXACTLY one audit execution (observability only).

Proves (mission requirements 1-10):
  1. correct audit_run_id is selected;
  2. wrong audit_run_id is rejected;
  3. missing scanner_tick_id is rejected;
  4. missing candidate_id is rejected;
  5. concurrent audit records are not mixed;
  6. candidate_id ALONE cannot select evidence;
  7. timestamp ALONE cannot select evidence;
  8. provenance survives scanner -> verifier -> evidence persistence;
  9/10 are covered by the existing partial-quote + Gate 7/8/9 suites.

Layers: pure selector functions (offline), a verifier provenance-flow check
(offline), and an end-to-end scanner-tick -> Mongo -> find_for_audit isolation
(real DiscoveryQueue + EvidenceBundlesRepo). No signing, no broadcast.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid

from unittest.mock import MagicMock

from motor.motor_asyncio import AsyncIOMotorClient

from arbicore.data.discovery_queue import DiscoveryQueue
from arbicore.data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
from arbicore.evidence.audit_provenance import (
    AuditProvenanceError, build_audit_evidence_query, evidence_matches_audit,
    filter_evidence_for_audit,
)
from arbicore.models.discovery import (
    DiscoveryCandidate, VerifiedOutcome, make_candidate_id,
)
from arbicore.models.enums import OpportunityType
from arbicore.scanners.flash_loan_arbitrage.scanner import (
    FlashLoanArbitrageScanner,
)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _bundle(*, run_id, tick, cand, worker="w1", status="CONFIRMED",
            created_at="2026-06-01T00:00:00+00:00", extra_diag=None):
    diag = {"audit_run_id": run_id, "scanner_tick_id": tick,
            "worker_id": worker, "candidate_id": cand}
    if extra_diag is not None:
        diag.update(extra_diag)
    return {"bundle_id": f"b:{run_id}:{tick}:{cand}",
            "source_component": "flash_loan_arb_verifier",
            "verification_status": status, "created_at": created_at,
            "diagnostics": diag}


# ---------------------------------------------------------------------------
# 1-7 — pure authoritative selector (offline, deterministic)
# ---------------------------------------------------------------------------

def test_correct_audit_run_id_is_selected():
    b = _bundle(run_id="RUN-A", tick=3, cand="cand-1")
    out = filter_evidence_for_audit(
        [b], audit_run_id="RUN-A", scanner_tick_id=3, candidate_id="cand-1")
    assert out == [b]


def test_wrong_audit_run_id_is_rejected():
    foreign = _bundle(run_id="RUN-B", tick=3, cand="cand-1")
    out = filter_evidence_for_audit(
        [foreign], audit_run_id="RUN-A", scanner_tick_id=3,
        candidate_id="cand-1")
    assert out == []
    assert evidence_matches_audit(
        foreign, audit_run_id="RUN-A", scanner_tick_id=3,
        candidate_id="cand-1") is False


def test_request_missing_scanner_tick_id_raises():
    b = _bundle(run_id="RUN-A", tick=3, cand="cand-1")
    for bad in (None, ""):
        try:
            filter_evidence_for_audit([b], audit_run_id="RUN-A",
                                      scanner_tick_id=bad, candidate_id="cand-1")
            assert False, "expected AuditProvenanceError"
        except AuditProvenanceError:
            pass


def test_bundle_missing_scanner_tick_id_is_rejected():
    b = _bundle(run_id="RUN-A", tick=3, cand="cand-1")
    b["diagnostics"].pop("scanner_tick_id")
    assert evidence_matches_audit(
        b, audit_run_id="RUN-A", scanner_tick_id=3, candidate_id="cand-1") \
        is False


def test_request_missing_candidate_id_raises():
    b = _bundle(run_id="RUN-A", tick=3, cand="cand-1")
    for bad in (None, "", "   "):
        try:
            filter_evidence_for_audit([b], audit_run_id="RUN-A",
                                      scanner_tick_id=3, candidate_id=bad)
            assert False, "expected AuditProvenanceError"
        except AuditProvenanceError:
            pass


def test_bundle_missing_candidate_id_is_rejected():
    b = _bundle(run_id="RUN-A", tick=3, cand="cand-1")
    b["diagnostics"].pop("candidate_id")
    assert evidence_matches_audit(
        b, audit_run_id="RUN-A", scanner_tick_id=3, candidate_id="cand-1") \
        is False


def test_bundle_missing_diagnostics_is_rejected():
    b = _bundle(run_id="RUN-A", tick=3, cand="cand-1")
    b.pop("diagnostics")
    assert evidence_matches_audit(
        b, audit_run_id="RUN-A", scanner_tick_id=3, candidate_id="cand-1") \
        is False


def test_concurrent_audit_records_are_not_mixed():
    # Two workers, two runs, overlapping candidate ids and ticks.
    a1 = _bundle(run_id="RUN-A", tick=1, cand="cand-1", worker="wA")
    a2 = _bundle(run_id="RUN-A", tick=2, cand="cand-2", worker="wA")
    b1 = _bundle(run_id="RUN-B", tick=1, cand="cand-1", worker="wB")
    pool = [a1, b1, a2]
    out = filter_evidence_for_audit(
        pool, audit_run_id="RUN-A", scanner_tick_id=1, candidate_id="cand-1")
    assert out == [a1]                      # only RUN-A tick 1 cand-1
    # worker tie-breaker further narrows without mixing
    assert filter_evidence_for_audit(
        pool, audit_run_id="RUN-B", scanner_tick_id=1, candidate_id="cand-1",
        worker_id="wA") == []


def test_candidate_id_alone_cannot_select_evidence():
    # Same candidate id under two different runs — candidate id is NOT enough.
    a = _bundle(run_id="RUN-A", tick=1, cand="cand-x")
    b = _bundle(run_id="RUN-B", tick=1, cand="cand-x")
    out = filter_evidence_for_audit(
        [a, b], audit_run_id="RUN-A", scanner_tick_id=1, candidate_id="cand-x")
    assert out == [a]                       # run id disambiguates, not cand id
    # And the query object never keys off candidate id alone.
    q = build_audit_evidence_query(
        audit_run_id="RUN-A", scanner_tick_id=1, candidate_id="cand-x")
    assert q["diagnostics.audit_run_id"] == "RUN-A"
    assert q["diagnostics.scanner_tick_id"] == 1
    assert q["diagnostics.candidate_id"] == "cand-x"


def test_timestamp_alone_cannot_select_evidence():
    q = build_audit_evidence_query(
        audit_run_id="RUN-A", scanner_tick_id=1, candidate_id="cand-1")
    # No timestamp / created_at / persisted_at may appear as a selector.
    assert not any("created_at" in k or "persisted_at" in k or "ts" == k
                   for k in q)
    # A newer foreign record must not be preferred over the pinned run.
    older = _bundle(run_id="RUN-A", tick=1, cand="cand-1",
                    created_at="2020-01-01T00:00:00+00:00")
    newer_foreign = _bundle(run_id="RUN-B", tick=1, cand="cand-1",
                            created_at="2999-01-01T00:00:00+00:00")
    out = filter_evidence_for_audit(
        [newer_foreign, older], audit_run_id="RUN-A", scanner_tick_id=1,
        candidate_id="cand-1")
    assert out == [older]


def test_tick_zero_is_a_valid_identifier():
    b = _bundle(run_id="RUN-A", tick=0, cand="cand-1")
    assert evidence_matches_audit(
        b, audit_run_id="RUN-A", scanner_tick_id=0, candidate_id="cand-1")


def test_operator_document_selectors_are_rejected():
    # NoSQL-injection guard: a Mongo operator doc must never widen selection.
    a = _bundle(run_id="RUN-A", tick=1, cand="cand-1")
    b = _bundle(run_id="RUN-B", tick=1, cand="cand-1")
    for bad in ({"$ne": "nope"}, {"$exists": True}, ["RUN-A"]):
        try:
            filter_evidence_for_audit([a, b], audit_run_id=bad,
                                      scanner_tick_id=1, candidate_id="cand-1")
            assert False, f"expected AuditProvenanceError for {bad!r}"
        except AuditProvenanceError:
            pass
    # build_audit_evidence_query must also reject them (query never widened).
    try:
        build_audit_evidence_query(audit_run_id="RUN-A", scanner_tick_id={"$gt": 0},
                                   candidate_id="cand-1")
        assert False, "expected AuditProvenanceError for operator tick"
    except AuditProvenanceError:
        pass


def test_bool_tick_is_rejected():
    try:
        build_audit_evidence_query(audit_run_id="RUN-A", scanner_tick_id=True,
                                   candidate_id="cand-1")
        assert False, "expected AuditProvenanceError for bool tick"
    except AuditProvenanceError:
        pass


def test_query_and_inmemory_defaults_are_aligned():
    # A foreign source_component is rejected by BOTH the Mongo query and the
    # in-memory mirror (default source_component parity).
    q = build_audit_evidence_query(
        audit_run_id="RUN-A", scanner_tick_id=1, candidate_id="cand-1")
    assert q["source_component"] == "flash_loan_arb_verifier"
    foreign_component = _bundle(run_id="RUN-A", tick=1, cand="cand-1")
    foreign_component["source_component"] = "some_other_component"
    assert filter_evidence_for_audit(
        [foreign_component], audit_run_id="RUN-A", scanner_tick_id=1,
        candidate_id="cand-1") == []


# ---------------------------------------------------------------------------
# 8 — provenance survives scanner -> verifier -> evidence persistence (Mongo)
# ---------------------------------------------------------------------------

_GATES = {"min_atomic_profit_usd": 25.0,
          "min_pool_tvl_usd_in_route": 100_000.0,
          "max_flash_loan_mev_risk_class": "MEDIUM"}


def _cfg():
    return {
        "interval_s": 60, "default_notional_usd": 10_000.0,
        "providers": {"aave_v3": {"enabled": False, "fee_bps": 5}},
        "chains": {c: {"enabled": False, "gas_token": "ETH",
                       "tx_gas_units": 800_000}
                   for c in ("ethereum", "base")},
        "route_search": {"max_hops": 4, "wall_clock_cap_s": 5.0,
                         "candidate_cap": 64, "min_pool_tvl_usd": 100_000},
        "gate_thresholds": {"default": _GATES},
        "roi_probability": {"min_sample_size": 2},
    }


async def _confirmed_provider(hm, amt):
    return {
        "flash_loan_pool_address": "0xpool", "flash_loan_fee_bps_override": 5,
        "hop_legs": [
            {"venue_id": "p1", "fee_bps": 30, "slippage_pct": 0.05,
             "source_id": "uniswap_v3_quoter_ethereum", "depth_usd": 500_000,
             "dex_protocol": "uniswap_v3", "status": "ok"},
            {"venue_id": "p2", "fee_bps": 30, "slippage_pct": 0.05,
             "source_id": "uniswap_v3_quoter_ethereum", "depth_usd": 500_000,
             "dex_protocol": "uniswap_v3", "status": "ok"},
        ],
        "gross_profit_pct": 2.0, "verified_at_ts": 1.0,
        "route_quote_status": "ok",
        "min_pool_tvl_usd_in_route": 500_000.0,
    }


def _fresh_candidate():
    observed = time.time()
    hm = {"chain": "ethereum", "provider": "aave_v3", "borrow_token": "USDC",
          "hop_count": 2, "min_tvl_usd": 500_000.0,
          "route_pools": ["p1", "p2"],
          "route_dex_protocols": ["uniswap_v3", "sushiswap"],
          "cycle_token_path": ["USDC", "WETH", "USDC"]}
    subject = f"flash_loan:aave_v3:ethereum:USDC:{uuid.uuid4().hex[:6]}"
    cid = make_candidate_id(
        hint_source="flash_loan_route_search",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id=subject, asset="USDC",
        candidate_venues=["p1", "p2"], hint_observed_at=observed)
    return DiscoveryCandidate(
        candidate_id=cid, opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="flash_loan_route_search", hint_observed_at=observed,
        subject_id=subject, asset="USDC", candidate_venues=["p1", "p2"],
        hint_metric=hm, reason="audit-provenance-regression")


def _make_scanner(queue):
    class _Bus:
        async def emit(self, opp, *, venue_ids=None, actor=None):
            return None

    scanner = FlashLoanArbitrageScanner(
        emission_bus=_Bus(), discovery_queue=queue,
        venue_capability_repo=MagicMock(), config_loader=_cfg,
        state_loader=lambda: {"enabled": True}, pool_loader=lambda c: [],
        quote_provider=_confirmed_provider)
    return scanner


def test_provenance_survives_scanner_verifier_persistence_and_isolation():
    async def body():
        client = AsyncIOMotorClient(MONGO_URL)
        dbname = f"arbicore_x_audit_prov_test_{uuid.uuid4().hex[:8]}"
        db = client[dbname]
        try:
            queue = DiscoveryQueue(db)
            await queue.ensure_indexes()
            repo = EvidenceBundlesRepo(db)
            await repo.ensure_indexes()

            cand = _fresh_candidate()
            await queue.upsert_many([cand])
            scanner = _make_scanner(queue)
            scanner.set_evidence_sink(repo.insert)
            await scanner._tick()

            run_id = scanner._audit_run_id
            tick_id = scanner._tick_id
            worker_id = scanner._worker_id

            # 8: the persisted bundle carries full provenance and is isolable.
            found = await repo.find_for_audit(
                audit_run_id=run_id, scanner_tick_id=tick_id,
                candidate_id=cand.candidate_id, worker_id=worker_id)
            assert len(found) == 1
            b = found[0]
            assert b["verification_status"] == "CONFIRMED"
            d = b["diagnostics"]
            assert d["audit_run_id"] == run_id
            assert d["scanner_tick_id"] == tick_id
            assert d["worker_id"] == worker_id
            assert d["candidate_id"] == cand.candidate_id

            # 2: a foreign audit_run_id retrieves nothing.
            assert await repo.find_for_audit(
                audit_run_id="RUN-DOES-NOT-EXIST", scanner_tick_id=tick_id,
                candidate_id=cand.candidate_id) == []

            # 6: candidate id under the wrong run retrieves nothing (no
            #    candidate-only fallback).
            assert await repo.find_for_audit(
                audit_run_id=run_id, scanner_tick_id=tick_id + 999,
                candidate_id=cand.candidate_id) == []
        finally:
            await client.drop_database(dbname)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# m3_0_vps_validate isolation: pinned-but-no-match must FAIL CLOSED (HIGH fix)
# ---------------------------------------------------------------------------

def test_m3_script_pinned_no_match_fails_closed_no_foreign_fallback(monkeypatch):
    import scripts.m3_0_vps_validate as m

    async def body():
        client = AsyncIOMotorClient(MONGO_URL)
        dbname = f"arbicore_x_audit_script_test_{uuid.uuid4().hex[:8]}"
        db = client[dbname]
        try:
            # Seed a FOREIGN confirmed bundle (different audit run).
            await db.evidence_bundles.insert_one(
                _bundle(run_id="FOREIGN-RUN", tick=9, cand="foreign-cand"))

            # (a) NOT pinned → caller keeps its normal path.
            for k in ("ARBICORE_AUDIT_RUN_ID", "ARBICORE_AUDIT_SCANNER_TICK_ID",
                      "ARBICORE_AUDIT_CANDIDATE_ID"):
                monkeypatch.delenv(k, raising=False)
            audit = {"opportunity": {}}
            pinned, doc = await m._select_audit_isolated_bundle(db, audit)
            assert pinned is False and doc is None

            # (b) PINNED to a run that matches nothing → (True, None), and the
            #     report records fail-closed (no fallback to the FOREIGN bundle).
            monkeypatch.setenv("ARBICORE_AUDIT_RUN_ID", "PINNED-RUN")
            monkeypatch.setenv("ARBICORE_AUDIT_SCANNER_TICK_ID", "1")
            monkeypatch.setenv("ARBICORE_AUDIT_CANDIDATE_ID", "cand-1")
            audit = {"opportunity": {}}
            pinned, doc = await m._select_audit_isolated_bundle(db, audit)
            assert pinned is True
            assert doc is None, "pinned run must NOT borrow foreign evidence"
            iso = audit["opportunity"]["audit_isolation"]
            assert iso["matched"] is False
            assert iso["fail_closed_no_fallback"] is True

            # (c) PINNED to a run that DOES match → returns exactly that bundle.
            await db.evidence_bundles.insert_one(
                _bundle(run_id="PINNED-RUN", tick=1, cand="cand-1"))
            audit = {"opportunity": {}}
            pinned, doc = await m._select_audit_isolated_bundle(db, audit)
            assert pinned is True and doc is not None
            assert doc["diagnostics"]["audit_run_id"] == "PINNED-RUN"
        finally:
            await client.drop_database(dbname)
            client.close()

    _run(body())
