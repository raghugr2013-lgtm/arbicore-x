"""Canonical VPS audit runner + single-tick workflow.

Proves the fix for the audit-tooling blocker: an audit runner that starts with
ONLY an audit_run_id can now (a) execute exactly one canonical scanner tick,
(b) capture the ACTUAL scanner_tick_id, (c) retrieve every candidate of that
exact run+tick from the evidence store (candidate_id optional), and (d) enforce
candidate-level exact matching — with strict fail-closed isolation throughout.

Offline/deterministic where possible; the end-to-end tick uses a real
DiscoveryQueue + EvidenceBundlesRepo (Mongo) with an injected confirmed quote
provider. No RPC, no signing, no broadcast.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid

# composition -> services.db reads MONGO_URL/DB_NAME at import; provide safe
# local defaults for the test process (the fail-closed test uses monkeypatch).
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_test")

from unittest.mock import MagicMock

from motor.motor_asyncio import AsyncIOMotorClient

from arbicore.data.discovery_queue import DiscoveryQueue
from arbicore.data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
from arbicore.evidence.audit_provenance import evidence_matches_audit
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


# ---------------------------------------------------------------------------
# Composition API surface (no regression to activation; new helpers present)
# ---------------------------------------------------------------------------

def test_composition_exposes_single_tick_and_activation():
    import inspect
    from arbicore.runtime import composition as c
    assert inspect.iscoroutinefunction(c.activate_canonical_flash_loan_scanner)
    assert inspect.iscoroutinefunction(
        c.run_single_canonical_flash_loan_audit_tick)
    assert inspect.iscoroutinefunction(c._wire_canonical_flash_loan_scanner)


def test_runner_module_imports():
    import scripts.vps_canonical_audit as r
    assert hasattr(r, "main") and callable(r.main)


def test_runner_fails_closed_without_mongo_env(monkeypatch):
    import scripts.vps_canonical_audit as r
    monkeypatch.delenv("MONGO_URL", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    rc = _run(r._amain())
    assert rc == 2  # fail closed: refuses to run without Mongo config


# ---------------------------------------------------------------------------
# End-to-end tick -> capture actual ids -> retrieve run+tick -> isolate (Mongo)
# ---------------------------------------------------------------------------

_GATES = {"min_atomic_profit_usd": 25.0,
          "min_pool_tvl_usd_in_route": 100_000.0,
          "max_flash_loan_mev_risk_class": "MEDIUM"}


def _cfg():
    return {
        "interval_s": 60, "default_notional_usd": 10_000.0,
        "providers": {"aave_v3": {"enabled": False, "fee_bps": 5}},
        "chains": {c: {"enabled": False, "gas_token": "ETH",
                       "tx_gas_units": 800_000} for c in ("ethereum", "base")},
        "route_search": {"max_hops": 4, "wall_clock_cap_s": 5.0,
                         "candidate_cap": 64, "min_pool_tvl_usd": 100_000},
        "gate_thresholds": {"default": _GATES},
        "roi_probability": {"min_sample_size": 2},
    }


async def _confirmed_provider(hm, amt):
    leg = {"venue_id": "p", "fee_bps": 30, "slippage_pct": 0.05,
           "source_id": "uniswap_v3_quoter_ethereum", "depth_usd": 500_000,
           "dex_protocol": "uniswap_v3", "status": "ok"}
    return {"flash_loan_pool_address": "0xpool", "flash_loan_fee_bps_override": 5,
            "hop_legs": [dict(leg), dict(leg)], "gross_profit_pct": 2.0,
            "verified_at_ts": 1.0, "route_quote_status": "ok",
            "min_pool_tvl_usd_in_route": 500_000.0}


def _fresh_candidate():
    observed = time.time()
    hm = {"chain": "ethereum", "provider": "aave_v3", "borrow_token": "USDC",
          "hop_count": 2, "min_tvl_usd": 500_000.0, "route_pools": ["p1", "p2"],
          "route_dex_protocols": ["uniswap_v3", "sushiswap"],
          "cycle_token_path": ["USDC", "WETH", "USDC"]}
    subject = f"flash_loan:aave_v3:ethereum:USDC:{uuid.uuid4().hex[:6]}"
    cid = make_candidate_id(
        hint_source="flash_loan_route_search",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id=subject, asset="USDC", candidate_venues=["p1", "p2"],
        hint_observed_at=observed)
    return DiscoveryCandidate(
        candidate_id=cid, opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="flash_loan_route_search", hint_observed_at=observed,
        subject_id=subject, asset="USDC", candidate_venues=["p1", "p2"],
        hint_metric=hm, reason="canonical-audit-runner-regression")


def _make_scanner(queue):
    class _Bus:
        async def emit(self, opp, *, venue_ids=None, actor=None):
            return None
    return FlashLoanArbitrageScanner(
        emission_bus=_Bus(), discovery_queue=queue,
        venue_capability_repo=MagicMock(), config_loader=_cfg,
        state_loader=lambda: {"enabled": True}, pool_loader=lambda c: [],
        quote_provider=_confirmed_provider)


def test_single_tick_capture_ids_then_retrieve_and_isolate():
    async def body():
        client = AsyncIOMotorClient(MONGO_URL)
        dbname = f"arbicore_x_runner_test_{uuid.uuid4().hex[:8]}"
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

            # Runner starts with ONLY the audit_run_id (read from the scanner);
            # it must run one tick and then discover the tick id + candidates.
            run_id = scanner._audit_run_id
            await scanner._tick()                         # exactly one tick
            tick_id = scanner._tick_id                    # ACTUAL, not guessed

            # Retrieve EVERY candidate of this exact run+tick (candidate omitted).
            bundles = await repo.find_for_audit(
                audit_run_id=run_id, scanner_tick_id=tick_id)
            assert len(bundles) == 1
            ledger_cands = [b["diagnostics"]["candidate_id"] for b in bundles]
            assert cand.candidate_id in ledger_cands

            # Candidate-level exact isolation (defense in depth).
            assert all(evidence_matches_audit(
                b, audit_run_id=run_id, scanner_tick_id=tick_id,
                candidate_id=b["diagnostics"]["candidate_id"]) for b in bundles)
            confirmed = [b for b in bundles
                         if b["verification_status"] == "CONFIRMED"]
            assert len(confirmed) == 1
            assert confirmed[0]["outcome_tag"].startswith(
                VerifiedOutcome.CONFIRMED_PREFIX)

            # Wrong run / wrong tick / wrong candidate all isolate to nothing.
            assert await repo.find_for_audit(
                audit_run_id="FOREIGN", scanner_tick_id=tick_id) == []
            assert await repo.find_for_audit(
                audit_run_id=run_id, scanner_tick_id=tick_id + 999) == []
            assert await repo.find_for_audit(
                audit_run_id=run_id, scanner_tick_id=tick_id,
                candidate_id="not-a-real-candidate") == []
        finally:
            await client.drop_database(dbname)
            client.close()

    _run(body())


def test_concurrent_runs_do_not_contaminate_ledger():
    async def body():
        client = AsyncIOMotorClient(MONGO_URL)
        dbname = f"arbicore_x_runner_conc_{uuid.uuid4().hex[:8]}"
        db = client[dbname]
        try:
            queue = DiscoveryQueue(db)
            await queue.ensure_indexes()
            repo = EvidenceBundlesRepo(db)
            await repo.ensure_indexes()

            # Two independent scanner instances = two audit runs.
            c1, c2 = _fresh_candidate(), _fresh_candidate()
            await queue.upsert_many([c1, c2])
            s1 = _make_scanner(queue)
            s1.set_evidence_sink(repo.insert)
            await s1._tick()   # claims and verifies whatever is available

            # Second run against fresh candidates.
            c3 = _fresh_candidate()
            await queue.upsert_many([c3])
            s2 = _make_scanner(queue)
            s2.set_evidence_sink(repo.insert)
            await s2._tick()

            r1 = await repo.find_for_audit(
                audit_run_id=s1._audit_run_id, scanner_tick_id=s1._tick_id)
            r2 = await repo.find_for_audit(
                audit_run_id=s2._audit_run_id, scanner_tick_id=s2._tick_id)
            runs1 = {b["diagnostics"]["audit_run_id"] for b in r1}
            runs2 = {b["diagnostics"]["audit_run_id"] for b in r2}
            assert runs1 <= {s1._audit_run_id}
            assert runs2 <= {s2._audit_run_id}
            assert s1._audit_run_id != s2._audit_run_id
            # No record from run 2 leaks into run 1's ledger.
            assert all(b["diagnostics"]["audit_run_id"] == s1._audit_run_id
                       for b in r1)
        finally:
            await client.drop_database(dbname)
            client.close()

    _run(body())
