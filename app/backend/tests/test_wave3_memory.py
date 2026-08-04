"""Phase 3 — Opportunity Memory & Learning regression tests."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.asyncio


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture()
async def memory_stack():
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mid import MidWriter
    from arbicore.intelligence.wave2 import (
        OpportunityLifetimeTracker, LifetimeConfig)
    from arbicore.intelligence.wave3 import OpportunityMemory

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"wave3_test_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    writer = MidWriter(db)
    tracker = OpportunityLifetimeTracker(
        db, writer,
        LifetimeConfig(active_seconds=60, stale_seconds=3600,
                       recurrence_gap_seconds=0.05,
                       rediscovery_gap_seconds=0.02),
    )
    await tracker.ensure_indexes()
    memory = OpportunityMemory(db)
    try:
        yield tracker, memory, writer, db
    finally:
        await client.drop_database(db_name)
        client.close()


async def test_top_recurring_orders_by_recurrence(memory_stack):
    import asyncio
    tracker, memory, _, _ = memory_stack
    # opp-a: 1 recurrence, opp-b: 2 recurrences, opp-c: 0
    await tracker.observe(opp_id="opp-a",
                           opportunity_type="dex_arbitrage", chain="base")
    await asyncio.sleep(0.1)
    await tracker.observe(opp_id="opp-a",
                           opportunity_type="dex_arbitrage", chain="base")
    await tracker.observe(opp_id="opp-b",
                           opportunity_type="dex_arbitrage", chain="base")
    await asyncio.sleep(0.1)
    await tracker.observe(opp_id="opp-b",
                           opportunity_type="dex_arbitrage", chain="base")
    await asyncio.sleep(0.1)
    await tracker.observe(opp_id="opp-b",
                           opportunity_type="dex_arbitrage", chain="base")
    await tracker.observe(opp_id="opp-c",
                           opportunity_type="dex_arbitrage", chain="base")
    rows = await memory.top_recurring(limit=10)
    ids = [r["opp_id"] for r in rows]
    assert ids[0] == "opp-b"
    assert "opp-c" not in ids  # zero recurrence excluded by min_recurrence=1


async def test_most_persistent(memory_stack):
    tracker, memory, _, db = memory_stack
    await tracker.observe(opp_id="p1",
                           opportunity_type="dex_arbitrage", chain="base")
    await tracker.observe(opp_id="p1",
                           opportunity_type="dex_arbitrage", chain="base")
    # boost lifetime by manual update — simulating a long-lived opp
    await db.mid_opportunity_lifetime.update_one(
        {"opp_id": "p1"}, {"$set": {"lifetime_seconds": 999.0}})
    rows = await memory.most_persistent(limit=5, min_observations=1)
    assert rows[0]["opp_id"] == "p1"
    assert rows[0]["lifetime_seconds"] == 999.0


async def test_confidence_history_and_trend(memory_stack):
    _, memory, writer, _ = memory_stack
    for score in (0.30, 0.35, 0.40, 0.65, 0.70, 0.75):
        await writer.write_confidence(opp_id="ch-1", score=score)
    r = await memory.confidence_history("ch-1")
    assert r["stats"]["sample_count"] == 6
    assert r["stats"]["trend"] == "rising"

    for score in (0.90, 0.85, 0.60, 0.40, 0.35, 0.30):
        await writer.write_confidence(opp_id="ch-2", score=score)
    r2 = await memory.confidence_history("ch-2")
    assert r2["stats"]["trend"] == "falling"


async def test_profitability_history_from_lifetime_trend(memory_stack):
    tracker, memory, _, _ = memory_stack
    for p in (1.2, 1.4, 1.7):
        await tracker.observe(opp_id="pr-1",
                               opportunity_type="dex_arbitrage",
                               chain="base", profitability=p)
    r = await memory.profitability_history("pr-1")
    assert r["stats"]["sample_count"] == 3
    assert r["stats"]["last"] == 1.7


async def test_route_quality_sorted_by_sample_count(memory_stack):
    _, memory, writer, _ = memory_stack
    for i in range(3):
        await writer.write_route_observation(
            route_id="r-hot", fingerprint_parts={"chain": "base"})
    await writer.write_route_observation(
        route_id="r-cold", fingerprint_parts={"chain": "base"})
    rows = await memory.route_quality()
    assert rows[0]["route_id"] == "r-hot"
    assert rows[0]["sample_count"] == 3


async def test_venue_quality_aggregates_providers(memory_stack):
    _, memory, writer, _ = memory_stack
    for _ in range(3):
        await writer.write_provider_snapshot(
            provider_id="v-good", available=True,
            observed_cost_bps=5, observed_revert_count=0)
    await writer.write_provider_snapshot(
        provider_id="v-bad", available=False,
        observed_cost_bps=15, observed_revert_count=2)
    rows = await memory.venue_quality()
    good = next(r for r in rows if r["provider_id"] == "v-good")
    bad  = next(r for r in rows if r["provider_id"] == "v-bad")
    assert good["sample_count"] == 3
    assert good["available_true"] == 3
    assert bad["revert_count"] == 2


async def test_regime_history_last_hours(memory_stack):
    _, memory, writer, _ = memory_stack
    from arbicore.scanners.wave1b.bridge import ScannerEvidenceBridge  # noqa: F401
    # write a couple of regime classification events directly
    await writer.write_opportunity_event(
        opp_id="__regime__",
        event_type="intel.regime.classified",
        payload={"dominant_regime": "CALM"})
    await writer.write_opportunity_event(
        opp_id="__regime__",
        event_type="intel.regime.classified",
        payload={"dominant_regime": "VOLATILE"})
    r = await memory.regime_history(hours=1)
    assert r["count"] == 2
    assert set(r["by_regime"].keys()) == {"CALM", "VOLATILE"}


async def test_summary_hydrates_dashboard(memory_stack):
    tracker, memory, writer, _ = memory_stack
    await tracker.observe(opp_id="s1",
                           opportunity_type="dex_arbitrage", chain="base")
    await tracker.observe(opp_id="s2",
                           opportunity_type="dex_arbitrage", chain="base")
    await writer.write_confidence(opp_id="s1", score=0.5)
    s = await memory.summary()
    assert s["opportunities"]["total"] == 2
    assert s["opportunities"]["by_status"]["ACTIVE"] == 2
    assert s["evidence"]["confidence_rows"] == 1
