"""Regression: flash-loan discovery candidates must progress A→B→C.

Root cause (fixed): DiscoveryCandidate lifetime was hardcoded to 60s, shorter
than a production _tick discover()+upsert_many() latency, so fresh candidates
expired before DiscoveryQueue.claim_batch() could claim them → verification
never ran (verified_outcome/verified_at stayed None).

This suite proves:
  * candidate TTL is configurable (ARBICORE_DISCOVERY_CANDIDATE_TTL_S, def 900s)
  * a fresh candidate survives long enough to be claimed by the REAL queue
  * a real _tick drives claim → verify → deterministic outcome, with verified_at
    populated, for BOTH a confirmed canonical and a Gate-7 rejection
  * no transaction is broadcast (detection-only emission), execution disabled

Uses the real DiscoveryQueue against a throwaway Mongo DB. Reuses the D-6.1
verifier/economics/gate fixture shapes.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid

from unittest.mock import MagicMock

from motor.motor_asyncio import AsyncIOMotorClient

from arbicore.data.discovery_queue import DiscoveryQueue
from arbicore.models.discovery import (
    DiscoveryCandidate, VerifiedOutcome, make_candidate_id,
    _discovery_candidate_ttl_s,
)
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.enums import OpportunityType
from arbicore.scanners.flash_loan_arbitrage.scanner import (
    FlashLoanArbitrageScanner,
)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

_GATES = {
    "min_atomic_profit_usd": 25.0,
    "min_pool_tvl_usd_in_route": 100_000.0,
    "max_flash_loan_mev_risk_class": "MEDIUM",
}


def _cfg() -> dict:
    # Sources kept DISABLED so discover() emits nothing → the test isolates the
    # pre-seeded candidate through the real claim/verify path.
    return {
        "interval_s": 60,
        "default_notional_usd": 10_000.0,
        "providers": {
            "aave_v3": {"enabled": False, "fee_bps": 5},
            "balancer_v2": {"enabled": False, "fee_bps": 0},
            "uniswap_v3": {"enabled": False, "fee_bps_default": 30},
        },
        "chains": {c: {"enabled": False, "gas_token": "ETH",
                       "tx_gas_units": 800_000}
                   for c in ("ethereum", "arbitrum", "base",
                             "optimism", "polygon")},
        "route_search": {"max_hops": 4, "wall_clock_cap_s": 5.0,
                         "candidate_cap": 64, "min_pool_tvl_usd": 100_000},
        "gate_thresholds": {"default": _GATES},
        "roi_probability": {"min_sample_size": 2},
    }


def _fresh_candidate(observed: float | None = None) -> DiscoveryCandidate:
    observed = observed if observed is not None else time.time()
    hm = {
        "chain": "ethereum", "provider": "aave_v3",
        "borrow_token": "USDC", "hop_count": 2, "min_tvl_usd": 500_000.0,
        "estimated_total_fee_pct": 0.6,
        "route_pools": ["p1", "p2"],
        "route_dex_protocols": ["uniswap_v3", "sushiswap"],
        "cycle_token_path": ["USDC", "WETH", "USDC"],
        "route_search_wall_ms": 12, "route_search_candidates_explored": 4,
    }
    subject = f"flash_loan:aave_v3:ethereum:USDC:{uuid.uuid4().hex[:6]}"
    cid = make_candidate_id(
        hint_source="flash_loan_route_search",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id=subject, asset="USDC",
        candidate_venues=["p1", "p2"], hint_observed_at=observed)
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="flash_loan_route_search", hint_observed_at=observed,
        subject_id=subject, asset="USDC", candidate_venues=["p1", "p2"],
        hint_metric=hm, reason="regression")


async def _confirmed_provider(hm, amt):
    return {
        "flash_loan_pool_address": "0xpool",
        "flash_loan_fee_bps_override": 5,
        "hop_legs": [
            {"venue_id": "p1", "fee_bps": 30, "slippage_pct": 0.05,
             "source_id": "uniswap_v3_quoter_ethereum",
             "depth_usd": 500_000, "dex_protocol": "uniswap_v3"},
            {"venue_id": "p2", "fee_bps": 30, "slippage_pct": 0.05,
             "source_id": "uniswap_v3_quoter_ethereum",
             "depth_usd": 500_000, "dex_protocol": "sushiswap"},
        ],
        "gross_profit_pct": 2.0, "verified_at_ts": 1.0,
        "min_pool_tvl_usd_in_route": 500_000.0,
    }


async def _gate7_reject_provider(hm, amt):
    return {
        "hop_legs": [{"venue_id": "p1", "fee_bps": 30, "slippage_pct": 5.0,
                      "source_id": "uniswap_v3_quoter_ethereum"}],
        "gross_profit_pct": 0.0,           # no profit → Gate 7 rejects
        "min_pool_tvl_usd_in_route": 500_000.0,
    }


class _SpyBus:
    """Records emissions (detection). NEVER broadcasts a transaction."""

    def __init__(self):
        self.emits = []

    async def emit(self, opp, *, venue_ids=None, actor=None):
        self.emits.append({"opp": opp, "venue_ids": venue_ids, "actor": actor})


def _make_scanner(queue, *, quote_provider):
    cfg = _cfg()
    bus = _SpyBus()
    scanner = FlashLoanArbitrageScanner(
        emission_bus=bus,
        discovery_queue=queue,
        venue_capability_repo=MagicMock(),
        config_loader=lambda: cfg,
        state_loader=lambda: {"enabled": True},
        pool_loader=lambda c: [],
        quote_provider=quote_provider,
    )
    return scanner, bus


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _with_queue(fn):
    client = AsyncIOMotorClient(MONGO_URL)
    dbname = f"arbicore_x_pipeline_test_{uuid.uuid4().hex[:8]}"
    db = client[dbname]
    queue = DiscoveryQueue(db)
    try:
        await queue.ensure_indexes()
        return await fn(queue)
    finally:
        await client.drop_database(dbname)
        client.close()


# ── TTL configuration (unit; no Mongo) ─────────────────────────────────────
def test_ttl_default_is_900(monkeypatch):
    monkeypatch.delenv("ARBICORE_DISCOVERY_CANDIDATE_TTL_S", raising=False)
    assert _discovery_candidate_ttl_s() == 900.0
    now = time.time()
    c = _fresh_candidate(observed=now)
    assert abs(c.expires_at - (now + 900.0)) < 1.0


def test_ttl_env_override(monkeypatch):
    monkeypatch.setenv("ARBICORE_DISCOVERY_CANDIDATE_TTL_S", "300")
    assert _discovery_candidate_ttl_s() == 300.0
    now = time.time()
    c = _fresh_candidate(observed=now)
    assert abs(c.expires_at - (now + 300.0)) < 1.0


def test_ttl_bad_values_fall_back_to_default(monkeypatch):
    for bad in ("abc", "-5", "0", ""):
        monkeypatch.setenv("ARBICORE_DISCOVERY_CANDIDATE_TTL_S", bad)
        assert _discovery_candidate_ttl_s() == 900.0


def test_regression_old_60s_window_would_have_starved_claim(monkeypatch):
    """A candidate observed ~120s ago is EXPIRED under the old 60s window but
    still LIVE (claimable) under the new default — the exact starvation fixed."""
    monkeypatch.delenv("ARBICORE_DISCOVERY_CANDIDATE_TTL_S", raising=False)
    now = time.time()
    c = _fresh_candidate(observed=now - 120.0)
    assert (now - 120.0) + 60.0 < now      # old 60s → already expired
    assert c.expires_at > now              # new default → still claimable


# ── Real DiscoveryQueue eligibility (A, B) ──────────────────────────────────
def test_claim_batch_returns_fresh_and_skips_expired():
    async def body(queue: DiscoveryQueue):
        fresh = _fresh_candidate()
        expired = _fresh_candidate()
        await queue.upsert_many([fresh, expired])
        # Force the second row to be already-expired (simulate old-window row).
        await queue._col.update_one(
            {"candidate_id": expired.candidate_id},
            {"$set": {"expires_at": time.time() - 1.0}})
        claimed = await queue.claim_batch("test_worker", batch_size=32)
        ids = {c.candidate_id for c in claimed}
        assert fresh.candidate_id in ids            # B: eligible fresh claimed
        assert expired.candidate_id not in ids      # expired excluded
        # Claim lock recorded on the fresh row.
        doc = await queue.get_candidate(fresh.candidate_id)
        assert doc["claimed_by"] == "test_worker"
        assert doc["claimed_until"] is not None
    _run(_with_queue(body))


# ── Real _tick path: claim → verify → deterministic outcome (C–H) ───────────
def test_full_tick_confirmed_outcome():
    async def body(queue: DiscoveryQueue):
        cand = _fresh_candidate()
        await queue.upsert_many([cand])
        scanner, bus = _make_scanner(queue, quote_provider=_confirmed_provider)
        await scanner._tick()
        doc = await queue.get_candidate(cand.candidate_id)
        # C+D+E: reached verifier, verified_at populated, confirmed outcome.
        assert doc["verified_at"] is not None
        assert doc["verified_outcome"].startswith(
            VerifiedOutcome.CONFIRMED_PREFIX)
        assert doc["emitted_opportunity_id"]
        # F: stats non-zero.
        assert scanner.stats["candidates_claimed"] >= 1
        assert scanner.stats["verifier_confirmed"] >= 1
        # C: emission is detection-only (opportunity), G/H: no broadcast/exec.
        assert len(bus.emits) == 1
        assert isinstance(bus.emits[0]["opp"], CanonicalOpportunity)
        assert bus.emits[0]["actor"] == "flash_loan_arb_scanner"
    _run(_with_queue(body))


def test_full_tick_gate7_rejection_is_deterministic():
    async def body(queue: DiscoveryQueue):
        cand = _fresh_candidate()
        await queue.upsert_many([cand])
        scanner, bus = _make_scanner(
            queue, quote_provider=_gate7_reject_provider)
        await scanner._tick()
        doc = await queue.get_candidate(cand.candidate_id)
        # D+E: verified_at populated, deterministic gate rejection recorded.
        assert doc["verified_at"] is not None
        assert doc["verified_outcome"].startswith(
            VerifiedOutcome.DENIED_GATE_PREFIX + "gate_7")
        assert doc["emitted_opportunity_id"] is None
        # F: denial stats non-zero.
        assert scanner.stats["candidates_claimed"] >= 1
        assert scanner.stats["verifier_denied"] >= 1
        assert scanner.stats["gate_rejections"]["gate_7_atomic_profit"] >= 1
        # G/H: nothing emitted, no broadcast.
        assert bus.emits == []
    _run(_with_queue(body))
