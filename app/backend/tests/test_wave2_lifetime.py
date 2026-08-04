"""Phase 2 — Opportunity Lifetime Intelligence regression tests."""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.asyncio


def _iso_offset(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds))\
        .isoformat().replace("+00:00", "Z")


@pytest.fixture()
async def tracker_and_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mid import MidWriter
    from arbicore.intelligence.wave2 import (
        OpportunityLifetimeTracker, LifetimeConfig)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"wave2_test_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    writer = MidWriter(db)
    # tight thresholds so tests can trigger transitions quickly
    cfg = LifetimeConfig(
        active_seconds=0.5, stale_seconds=2.0, expired_seconds=60.0,
        trend_ring_buffer=5, rediscovery_gap_seconds=0.3,
        recurrence_gap_seconds=0.8, sweeper_interval_seconds=0.2,
    )
    tracker = OpportunityLifetimeTracker(db, writer, cfg)
    await tracker.ensure_indexes()
    try:
        yield tracker, db, cfg
    finally:
        await client.drop_database(db_name)
        client.close()


async def test_first_observation_inserts_active_doc(tracker_and_db):
    tracker, db, _ = tracker_and_db
    r = await tracker.observe(
        opp_id="opp-1", opportunity_type="dex_arbitrage", chain="base",
        confidence=0.72, profitability=1.5)
    assert r["inserted"] is True
    assert r["opportunity_status"] == "ACTIVE"

    doc = await db.mid_opportunity_lifetime.find_one({"opp_id": "opp-1"})
    assert doc["observation_count"] == 1
    assert doc["opportunity_status"] == "ACTIVE"
    assert doc["last_confidence"] == 0.72
    assert doc["last_profitability"] == 1.5
    assert len(doc["confidence_trend"]) == 1
    assert doc["mid_id"]  # unique id assigned


async def test_second_observation_updates_counters_and_trends(
        tracker_and_db):
    tracker, db, _ = tracker_and_db
    await tracker.observe(
        opp_id="opp-2", opportunity_type="dex_arbitrage", chain="base",
        confidence=0.60, profitability=1.0)
    r = await tracker.observe(
        opp_id="opp-2", opportunity_type="dex_arbitrage", chain="base",
        confidence=0.90, profitability=2.5)
    assert r["inserted"] is False
    assert r["observation_count"] == 2

    doc = await db.mid_opportunity_lifetime.find_one({"opp_id": "opp-2"})
    assert doc["observation_count"] == 2
    assert doc["last_confidence"] == 0.90
    assert len(doc["confidence_trend"]) == 2


async def test_rediscovery_but_not_recurrence(tracker_and_db):
    tracker, db, cfg = tracker_and_db
    await tracker.observe(opp_id="opp-3",
                           opportunity_type="dex_arbitrage", chain="base")
    # gap > rediscovery (0.3s) but < recurrence (0.8s)
    await asyncio.sleep(cfg.rediscovery_gap_seconds + 0.15)
    r = await tracker.observe(opp_id="opp-3",
                               opportunity_type="dex_arbitrage",
                               chain="base")
    assert r["rediscovered"] is True
    assert r["recurred"] is False

    doc = await db.mid_opportunity_lifetime.find_one({"opp_id": "opp-3"})
    assert doc["rediscovery_count"] == 1
    assert doc["recurrence_count"] == 0


async def test_recurrence_increment(tracker_and_db):
    tracker, db, cfg = tracker_and_db
    await tracker.observe(opp_id="opp-4",
                           opportunity_type="dex_arbitrage", chain="base")
    await asyncio.sleep(cfg.recurrence_gap_seconds + 0.15)
    r = await tracker.observe(opp_id="opp-4",
                               opportunity_type="dex_arbitrage",
                               chain="base")
    assert r["rediscovered"] is True
    assert r["recurred"] is True

    doc = await db.mid_opportunity_lifetime.find_one({"opp_id": "opp-4"})
    assert doc["rediscovery_count"] == 1
    assert doc["recurrence_count"] == 1


async def test_trend_ring_buffer_bounds(tracker_and_db):
    tracker, db, cfg = tracker_and_db
    for i in range(cfg.trend_ring_buffer + 3):
        await tracker.observe(
            opp_id="opp-ring", opportunity_type="dex_arbitrage",
            chain="base", confidence=float(i))
    doc = await db.mid_opportunity_lifetime.find_one(
        {"opp_id": "opp-ring"})
    assert len(doc["confidence_trend"]) == cfg.trend_ring_buffer
    # last entry is the most recent
    assert doc["confidence_trend"][-1]["value"] == (
        cfg.trend_ring_buffer + 3 - 1)


async def test_status_transitions_via_sweeper(tracker_and_db):
    tracker, db, cfg = tracker_and_db
    await tracker.observe(opp_id="opp-s",
                           opportunity_type="dex_arbitrage", chain="base")
    # wait past ACTIVE window (0.5s) but before EXPIRED
    await asyncio.sleep(cfg.active_seconds + 0.2)
    moved = await tracker.sweep_status_transitions()
    assert moved["active_to_stale"] == 1
    doc = await db.mid_opportunity_lifetime.find_one({"opp_id": "opp-s"})
    assert doc["opportunity_status"] == "STALE"

    # wait past STALE window to trigger EXPIRED
    await asyncio.sleep(cfg.stale_seconds + 0.2)
    moved = await tracker.sweep_status_transitions()
    assert moved["stale_to_expired"] == 1
    doc = await db.mid_opportunity_lifetime.find_one({"opp_id": "opp-s"})
    assert doc["opportunity_status"] == "EXPIRED"


async def test_reactivation_on_new_observation(tracker_and_db):
    tracker, db, cfg = tracker_and_db
    await tracker.observe(opp_id="opp-r",
                           opportunity_type="dex_arbitrage", chain="base")
    await asyncio.sleep(cfg.active_seconds + 0.2)
    await tracker.sweep_status_transitions()   # → STALE
    doc = await db.mid_opportunity_lifetime.find_one({"opp_id": "opp-r"})
    assert doc["opportunity_status"] == "STALE"

    r = await tracker.observe(opp_id="opp-r",
                               opportunity_type="dex_arbitrage",
                               chain="base")
    assert r["opportunity_status"] == "ACTIVE"


async def test_status_summary(tracker_and_db):
    tracker, _, _ = tracker_and_db
    for i in range(4):
        await tracker.observe(opp_id=f"opp-{i}",
                               opportunity_type="dex_arbitrage",
                               chain="base")
    summary = await tracker.status_summary()
    assert summary["total"] == 4
    assert summary["by_status"]["ACTIVE"] == 4
    assert summary["config"]["trend_ring_buffer"] == 5


async def test_list_recent_filters(tracker_and_db):
    tracker, _, _ = tracker_and_db
    await tracker.observe(opp_id="d1",
                           opportunity_type="dex_arbitrage", chain="base")
    await tracker.observe(opp_id="f1",
                           opportunity_type="flash_loan_arbitrage",
                           chain="ethereum")
    dex_rows = await tracker.list_recent(
        opportunity_type="dex_arbitrage")
    fl_rows = await tracker.list_recent(
        opportunity_type="flash_loan_arbitrage")
    assert len(dex_rows) == 1 and dex_rows[0]["opp_id"] == "d1"
    assert len(fl_rows) == 1 and fl_rows[0]["opp_id"] == "f1"


async def test_bridge_wires_tracker_into_emission():
    """Prove the ScannerEvidenceBridge invokes the lifetime tracker on
    every publish_emission."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mid import MidWriter
    from arbicore.scanners.wave1b.bridge import ScannerEvidenceBridge
    from arbicore.intelligence.wave2 import (
        OpportunityLifetimeTracker, LifetimeConfig)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"wave2_bridge_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    writer = MidWriter(db)
    tracker = OpportunityLifetimeTracker(db, writer, LifetimeConfig())
    await tracker.ensure_indexes()
    bridge = ScannerEvidenceBridge(writer, tracker=tracker)
    try:
        await bridge.publish_emission(
            scanner_id="dex_arbitrage", opp_id="opp-bridge",
            payload={"opportunity_type": "dex_arbitrage",
                     "chain": "base", "confidence": 0.5},
            route={"route_id": "rt-1", "fingerprint_parts": {}})
        # tracker doc must exist
        doc = await db.mid_opportunity_lifetime.find_one(
            {"opp_id": "opp-bridge"})
        assert doc is not None
        assert doc["observation_count"] == 1
        assert doc["opportunity_status"] == "ACTIVE"
    finally:
        await client.drop_database(db_name)
        client.close()


async def test_no_writes_on_missing_tracker():
    """Backward-compat: bridge without a tracker must still work."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mid import MidWriter
    from arbicore.scanners.wave1b.bridge import ScannerEvidenceBridge

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"wave2_notrack_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    writer = MidWriter(db)
    bridge = ScannerEvidenceBridge(writer)      # tracker=None
    try:
        r = await bridge.publish_emission(
            scanner_id="dex_arbitrage", opp_id="opp-lonely",
            payload={"opportunity_type": "dex_arbitrage",
                     "chain": "base"},
            route={"route_id": "rt-x", "fingerprint_parts": {}})
        assert r["opportunity_event_id"]
        # tracker collection must be empty (or non-existent)
        assert (await db.mid_opportunity_lifetime.count_documents({})) == 0
    finally:
        await client.drop_database(db_name)
        client.close()
