"""Scanner bootstrap decoupling + validator-contract correction.

Guards the fix for the post-deploy validation failure:
  * scanner_config + scanner_state seeding (6 docs each) must NOT be gated
    behind ARBICORE_RUNTIME_AUTOSTART — it now runs in the always-run
    `_arbicore_bootstrap_substrate` startup handler.
  * every seeded scanner STATE row must be dormant (enabled=False) — SHADOW/
    PAPER posture; nothing here starts a scanner / signs / broadcasts.
  * `04_validate.js` must NOT demand cex_arb/funding_arb enabled===true nor a
    positive recent-verifications count (both violate the dormant posture).
"""
from __future__ import annotations

import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from arbicore.data.scanner_config_repo import (
    ScannerConfigRepository, ScannerStateRepository,
)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

REPO = "/app"
SERVER_PY = f"{REPO}/app/backend/server.py"
VALIDATE_JS = f"{REPO}/deployment/upgrade/mongo/04_validate.js"

SCANNER_IDS = {"cex_arb", "funding_arb", "dex_arb",
               "launch_arb", "cross_chain_arb", "flash_loan_arb"}


def _read(path):
    with open(path) as f:
        return f.read()


@pytest.mark.asyncio
async def test_seed_defaults_creates_six_dormant_docs():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[f"arbicore_bootstrap_test_{uuid.uuid4().hex[:8]}"]
    try:
        cfg = ScannerConfigRepository(db)
        state = ScannerStateRepository(db)
        # idempotent: run twice, still 6 each
        for _ in range(2):
            await cfg.seed_defaults()
            await state.seed_defaults()

        assert await db.arbicore_scanner_config.count_documents({}) == 6
        assert await db.arbicore_scanner_state.count_documents({}) == 6

        cfg_ids = {d["_id"] async for d in db.arbicore_scanner_config.find({}, {"_id": 1})}
        st_ids = {d["_id"] async for d in db.arbicore_scanner_state.find({}, {"_id": 1})}
        assert cfg_ids == SCANNER_IDS
        assert st_ids == SCANNER_IDS

        # SHADOW/PAPER posture: EVERY state row dormant.
        async for d in db.arbicore_scanner_state.find({}):
            assert d.get("enabled") is False, f"{d['_id']} must seed dormant"
    finally:
        await client.drop_database(db.name)
        client.close()


def test_bootstrap_decoupled_from_autostart_in_server():
    src = _read(SERVER_PY)
    # The always-run substrate handler exists and seeds defaults.
    assert "async def _arbicore_bootstrap_substrate" in src
    seg = src.split("async def _arbicore_bootstrap_substrate", 1)[1]
    seg = seg.split("async def _arbicore_runtime_autostart", 1)[0]
    assert "seed_defaults()" in seg
    assert "ensure_indexes" in seg
    # The substrate handler must NOT be gated by the autostart env flag
    # (docstring may mention it; the CODE must not read it).
    assert 'os.environ.get("ARBICORE_RUNTIME_AUTOSTART")' not in seg
    # Scanner START remains gated in the autostart handler.
    autoseg = src.split("async def _arbicore_runtime_autostart", 1)[1]
    assert "ARBICORE_RUNTIME_AUTOSTART" in autoseg
    assert "sc.start()" in autoseg


def test_scanners_router_registered_in_server():
    src = _read(SERVER_PY)
    assert "from arbicore.routes.scanners import router as scanners_router" in src
    assert "app.include_router(scanners_router)" in src


def test_validator_no_longer_demands_enabled_or_production():
    js = _read(VALIDATE_JS)
    # Must not FAIL on scanners being enabled (dormant is correct).
    assert 'ok(enabled("cex_arb"))' not in js
    assert 'ok(enabled("funding_arb"))' not in js
    # Recent-verifications must be informational, not a PASS/FAIL gate.
    assert "ok(recent > 0)" not in js
    # Still asserts the 6+6 doc counts and TTL indexes.
    assert "cfg === 6" in js
    assert "st  === 6" in js
    assert 'hasIdx("arbicore_state_snapshots","ttl_30d")' in js
    assert 'hasIdx("arbicore_audit_log","ttl_90d")' in js
