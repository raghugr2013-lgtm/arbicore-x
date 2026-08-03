"""Sprint 1B-γ — end-to-end pipeline validation.

These tests exercise the full canonical pipeline that Sprint 1B assembled:

    Intelligence engines (Wave 1B-α)
       ↓ MidEvidenceBridge
    MID (durable evidence)
       ↑ MidReader
    Scanners (Wave 1B-β, shadow)
       ↓ ScannerEvidenceBridge
    MID again  (opportunity_events + route_observations)
       ↑ MidReader
    Intelligence engines re-consume scanner emissions via MID  ← the loop closes

The tests only exercise in-process code; no live network I/O is used.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def full_pipeline():
    """Wire the entire Sprint 1B pipeline against a scratch Mongo DB."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mid import MidReader, MidWriter
    from arbicore.intelligence.wave1b import activate_all as _intel_activate
    from arbicore.scanners.wave1b import (
        activate_scanners as _scanner_activate,
    )
    from arbicore.scanners.wave1b.adapters import ShadowScannerConfig

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"wave1b_gamma_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    writer, reader = MidWriter(db), MidReader(db)
    intel = _intel_activate(writer)
    scan = _scanner_activate(writer, reader)
    for sid in ("dex_arbitrage", "flash_loan_arbitrage"):
        scan.get_adapter(sid)._cfg = ShadowScannerConfig(
            tick_interval_seconds=0.05,
        )
    try:
        yield intel, scan, reader, writer, db
    finally:
        for sid in ("dex_arbitrage", "flash_loan_arbitrage"):
            adapter = scan.get_adapter(sid)
            if adapter and adapter.is_running():
                await adapter.stop()
        await client.drop_database(db_name)
        client.close()


# ---------------------------------------------------------------------------
# 1. Composite activation: both waves boot in a single process
# ---------------------------------------------------------------------------


async def test_both_waves_activate_cleanly(full_pipeline):
    intel, scan, _, _, _ = full_pipeline
    ints = intel.registry.summary()
    scns = scan.registry.summary()
    assert ints["active_count"] == 6
    assert scns["scanner_count"] == 2
    assert scns["running"] == []            # DORMANT boot
    assert not ints["errored"]
    assert not scns["errored"]


# ---------------------------------------------------------------------------
# 2. Engine → MID → scanner-visible via MID reader (Wave 1B-α → 1B-β loop)
# ---------------------------------------------------------------------------


async def test_engine_evidence_visible_to_scanners_via_mid(full_pipeline):
    intel, scan, reader, _, db = full_pipeline
    opp = f"opp-{uuid.uuid4().hex[:8]}"
    await intel.bridge.publish_confidence(
        opp_id=opp, score=91.4, inputs={"seed": "gamma-1"})

    # ScannerAdapter._tick reads MID confidence — start dex and let it tick.
    adapter = scan.get_adapter("dex_arbitrage")
    await adapter.start()
    await asyncio.sleep(0.25)
    await adapter.stop()

    # Every emission should reference the same confidence row we wrote.
    rows = await db["mid_opportunities"].find({
        "event_type": "scanner.dex_arbitrage.emit",
    }).to_list(length=50)
    assert rows, "shadow scanner did not emit any rows"
    assert any(r["payload"].get("upstream_opp_id") == opp for r in rows)


# ---------------------------------------------------------------------------
# 3. Scanner emissions readable by intelligence engines via MID
# ---------------------------------------------------------------------------


async def test_scanner_emissions_visible_via_mid_reader(full_pipeline):
    _, scan, reader, _, _ = full_pipeline
    adapter = scan.get_adapter("flash_loan_arbitrage")
    await adapter.start()
    await asyncio.sleep(0.25)
    await adapter.stop()

    # Engines discover scanner traffic through the SAME MID reader they
    # use for regular intelligence rows — proving the decoupled contract.
    events = await reader.query("opportunities", limit=50)
    scanner_events = [e for e in events
                       if e.get("event_type", "").startswith(
                           "scanner.flash_loan_arbitrage.")]
    assert scanner_events, (
        "flash-loan scanner emissions not visible via MidReader"
    )
    routes = await reader.query("routes", limit=50)
    assert any(r["fingerprint_parts"].get("scanner")
                == "flash_loan_arbitrage" for r in routes)


# ---------------------------------------------------------------------------
# 4. Bridge attribution is independent per wave
# ---------------------------------------------------------------------------


async def test_bridges_are_independent(full_pipeline):
    intel, scan, _, _, _ = full_pipeline
    opp = "opp-cross"
    await intel.bridge.publish_confidence(opp_id=opp, score=50.0)
    adapter = scan.get_adapter("dex_arbitrage")
    await adapter.start()
    await asyncio.sleep(0.2)
    await adapter.stop()

    # intelligence bridge should show exactly one write (confidence);
    # scanner bridge should show >= 1 emission but attributed only to
    # scanners, never to intelligence engines.
    ib = intel.bridge.stats.to_dict()
    sb = scan.bridge.stats.to_dict()
    assert ib["total_writes"] == 1
    assert "confidence" in ib["by_engine"]
    assert sb["total_emissions"] >= 1
    assert set(sb["by_scanner"].keys()) <= {
        "dex_arbitrage", "flash_loan_arbitrage",
    }
    # scanner bridge must never bleed into intelligence engines
    assert "confidence" not in sb["by_scanner"]


# ---------------------------------------------------------------------------
# 5. Backlog & throughput counters increment under sustained load
# ---------------------------------------------------------------------------


async def test_backlog_and_throughput_counters(full_pipeline):
    _, scan, _, _, _ = full_pipeline
    adapter = scan.get_adapter("dex_arbitrage")
    await adapter.start()
    await asyncio.sleep(0.5)
    await adapter.stop()

    s = adapter.stats
    assert s["iterations"] >= 5
    assert s["rows_emitted"] >= 5
    assert s["last_run_at"] is not None
    assert s["started_at"] is not None
    assert s["stopped_at"] is not None


# ---------------------------------------------------------------------------
# 6. Observability composition: full snapshot self-consistent
# ---------------------------------------------------------------------------


async def test_observability_composition(full_pipeline):
    intel, scan, _, _, _ = full_pipeline

    # emulate the /api/arbicore/observability payload assembly
    obs = {
        "mid": {"available": True},
        "intelligence": intel.summary(),
        "scanners": scan.summary(),
    }
    assert obs["intelligence"]["active_count"] == 6
    assert obs["scanners"]["scanner_count"] == 2
    # bridge_stats always present
    assert "bridge_stats" in obs["intelligence"]
    assert "bridge_stats" in obs["scanners"]


# ---------------------------------------------------------------------------
# 7. Auth v2.0.7 — end-to-end regression sanity (unit-level)
# ---------------------------------------------------------------------------


async def test_auth_lookup_is_tolerant_and_strict(full_pipeline):
    """Wave 1B-γ smoke on the v2.0.7 auth fix — a single test that
    validates the whole ``active`` contract in one place."""
    from arbicore.auth import _hash_password, authenticate

    _, _, _, _, db = full_pipeline
    await db["auth_users"].insert_many([
        # legacy — no ``active`` field
        {"user_id": "u-legacy", "username": "legacy",
         "role": "operator",
         "password_hash": _hash_password("p1"),
         "created_at": "2026-08-03T00:00:00Z"},
        # explicitly deactivated — must be rejected
        {"user_id": "u-banned", "username": "banned",
         "role": "operator", "active": False,
         "password_hash": _hash_password("p2"),
         "created_at": "2026-08-03T00:00:00Z"},
        # normal active
        {"user_id": "u-ok", "username": "ok",
         "role": "admin", "active": True,
         "password_hash": _hash_password("p3"),
         "created_at": "2026-08-03T00:00:00Z"},
    ])
    assert (await authenticate(db, "legacy", "p1")) is not None
    assert (await authenticate(db, "banned", "p2")) is None
    assert (await authenticate(db, "ok", "p3")) is not None
    assert (await authenticate(db, "legacy", "wrong")) is None
