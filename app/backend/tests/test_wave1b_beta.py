"""Sprint 1B-β — Scanner Activation (SHADOW) regression tests.

Validates:
  * Scanners register but boot DORMANT (never autostart).
  * ``ShadowScannerAdapter.start`` sets running/enabled true, publishes
    exactly one MID opportunity_event + route_observation per tick.
  * ``stop`` fully drains and idempotency (start on running is a no-op).
  * ``ScannerEvidenceBridge`` counters attribute writes correctly.
  * Auth v2.0.7: legacy documents (missing ``active`` field) can log in;
    documents with ``active: false`` cannot.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def mid_stack():
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mid import MidWriter, MidReader

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"wave1b_beta_test_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    writer = MidWriter(db)
    reader = MidReader(db)
    try:
        yield writer, reader, db
    finally:
        await client.drop_database(db_name)
        client.close()


# ---------------------------------------------------------------------------
# Scanner activation + lifecycle
# ---------------------------------------------------------------------------


async def test_activate_scanners_boots_dormant(mid_stack):
    from arbicore.scanners.wave1b import activate_scanners

    writer, reader, _ = mid_stack
    result = activate_scanners(writer, reader)

    summary = result.registry.summary()
    assert summary["scanner_count"] == 2
    assert summary["running"] == []
    assert summary["errored"] == []
    for sc in summary["scanners"]:
        assert sc["mode"] == "shadow"
        assert sc["running"] is False
        assert sc["enabled"] is False


async def test_shadow_scanner_start_stop_lifecycle(mid_stack):
    from arbicore.scanners.wave1b import activate_scanners
    from arbicore.scanners.wave1b.adapters import ShadowScannerConfig

    writer, reader, db = mid_stack
    result = activate_scanners(writer, reader)
    adapter = result.get_adapter("dex_arbitrage")
    assert adapter is not None
    # tight tick for the test
    adapter._cfg = ShadowScannerConfig(tick_interval_seconds=0.1)

    r = await adapter.start()
    assert r.get("started") is True
    assert adapter.is_running() is True

    # let a few ticks land
    await asyncio.sleep(0.5)

    r = await adapter.stop()
    assert r.get("stopped") is True
    assert adapter.is_running() is False
    assert adapter.is_enabled() is False

    assert adapter.stats["iterations"] >= 3
    assert adapter.stats["rows_emitted"] >= 3

    count = await db["mid_opportunities"].count_documents({
        "event_type": "scanner.dex_arbitrage.emit"})
    assert count >= 3
    routes = await db["mid_routes"].count_documents({})
    assert routes >= 3


async def test_start_is_idempotent(mid_stack):
    from arbicore.scanners.wave1b import activate_scanners
    from arbicore.scanners.wave1b.adapters import ShadowScannerConfig

    writer, reader, _ = mid_stack
    result = activate_scanners(writer, reader)
    adapter = result.get_adapter("flash_loan_arbitrage")
    adapter._cfg = ShadowScannerConfig(tick_interval_seconds=0.1)
    r1 = await adapter.start()
    r2 = await adapter.start()
    assert r1.get("started") is True
    assert r2.get("already_running") is True
    await adapter.stop()


async def test_stop_before_start_is_safe(mid_stack):
    from arbicore.scanners.wave1b import activate_scanners
    writer, reader, _ = mid_stack
    result = activate_scanners(writer, reader)
    adapter = result.get_adapter("dex_arbitrage")
    r = await adapter.stop()
    assert r.get("already_stopped") is True


# ---------------------------------------------------------------------------
# Bridge attribution
# ---------------------------------------------------------------------------


async def test_bridge_stats_attribute_writes(mid_stack):
    from arbicore.scanners.wave1b import activate_scanners
    from arbicore.scanners.wave1b.adapters import ShadowScannerConfig

    writer, reader, _ = mid_stack
    result = activate_scanners(writer, reader)
    for sid in ("dex_arbitrage", "flash_loan_arbitrage"):
        adapter = result.get_adapter(sid)
        adapter._cfg = ShadowScannerConfig(tick_interval_seconds=0.1)
        await adapter.start()

    await asyncio.sleep(0.6)

    for sid in ("dex_arbitrage", "flash_loan_arbitrage"):
        await result.get_adapter(sid).stop()

    stats = result.bridge.stats.to_dict()
    assert stats["total_emissions"] >= 6
    assert set(stats["by_scanner"].keys()) == {
        "dex_arbitrage", "flash_loan_arbitrage"}
    assert set(stats["by_event_type"].keys()) == {
        "scanner.dex_arbitrage.emit",
        "scanner.flash_loan_arbitrage.emit",
    }
    assert stats["routes_observed"] >= 6


async def test_bridge_publish_direct_with_route(mid_stack):
    from arbicore.scanners.wave1b.bridge import ScannerEvidenceBridge
    writer, _, db = mid_stack
    bridge = ScannerEvidenceBridge(writer)
    r = await bridge.publish_emission(
        scanner_id="dex_arbitrage",
        opp_id="opp-xyz",
        payload={"opportunity_type": "dex_arbitrage",
                 "chain": "base", "shadow": True},
        route={"route_id": "route-xyz",
                "fingerprint_parts": {"chain": "base"}},
    )
    assert r["opportunity_event_id"]
    assert r["route_observation_id"]
    row = await db["mid_routes"].find_one({"route_id": "route-xyz"})
    assert row is not None


# ---------------------------------------------------------------------------
# Auth v2.0.7 — tolerant `active` filter
# ---------------------------------------------------------------------------


async def test_auth_legacy_document_without_active_can_login():
    """VPS regression: a user doc lacking ``active`` still authenticates."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.auth import _hash_password, authenticate

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"auth_legacy_test_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    try:
        await db["auth_users"].insert_one({
            "user_id": "legacy-1",
            "username": "legacyadmin",
            "role": "admin",
            "password_hash": _hash_password("s3cret"),
            "created_at": "2026-08-03T00:00:00Z",
            # NOTE: intentionally NO 'active' field
        })
        user = await authenticate(db, "legacyadmin", "s3cret")
        assert user is not None
        assert user["username"] == "legacyadmin"
    finally:
        await client.drop_database(db_name)
        client.close()


async def test_auth_active_false_denies_login():
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.auth import _hash_password, authenticate

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"auth_deactivated_test_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    try:
        await db["auth_users"].insert_one({
            "user_id": "u2", "username": "banned",
            "role": "operator",
            "password_hash": _hash_password("s3cret"),
            "created_at": "2026-08-03T00:00:00Z",
            "active": False,
        })
        user = await authenticate(db, "banned", "s3cret")
        assert user is None
    finally:
        await client.drop_database(db_name)
        client.close()


async def test_ensure_seed_users_verifies_legacy_admin_ok():
    """v2.0.7 — the seed routine's post-seed verification must treat a
    legacy admin (no ``active`` field) as present."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.auth import _hash_password, ensure_seed_users

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"auth_seed_test_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    try:
        # pre-seed a legacy admin without the ``active`` field
        await db["auth_users"].insert_one({
            "user_id": "legacy-admin",
            "username": "admin",
            "role": "admin",
            "password_hash": _hash_password("legacy-pw"),
            "created_at": "2026-08-03T00:00:00Z",
        })
        summary = await ensure_seed_users(db)
        assert summary["ok"] is True
        assert "admin" in summary["existed_before"]
        assert "operator" in summary["inserted"]
        assert summary["verified"]["admin"] is True
        assert summary["verified"]["operator"] is True
    finally:
        await client.drop_database(db_name)
        client.close()
