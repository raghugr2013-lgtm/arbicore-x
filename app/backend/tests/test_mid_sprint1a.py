"""Sprint 1A — MID façade regression tests.

Covers:
    * schema round-trip (dataclass -> doc)
    * enum registry open/closed semantics + warnings
    * writers happy path (all 11 write methods)
    * reader query with metadata filters
    * ensure_indexes idempotency
    * REST endpoints /mid/status, /mid/query/{domain}, /mid/enums

Tests use motor's mongomock is not available in this environment; instead we
target the same MongoDB the running server uses (test_database via
MONGO_URL).  Every test writes into a per-test namespace-scoped collection
by using a unique strategy_type value; teardown deletes those rows.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

from arbicore.data.mid import (
    MidWriter, MidReader, MidMetadata, ReplayContext,
    ensure_indexes, DOMAINS, MID_COLLECTION_MAP,
    make_meta, new_mid_id, route_id_for, market_snapshot_id_for,
    get_registry, EnumRegistry,
    STRATEGY_TYPE, EXECUTION_MODE, MARKET_REGIME,
)
from arbicore.data.mid.enums import reset_registry_for_tests

BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
API = f"{BACKEND_URL}/api"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def isolate_tag():
    """Unique tag isolating every test's writes."""
    return f"pytest_mid_{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    yield client[os.environ.get("DB_NAME", "test_database")]
    client.close()


@pytest.fixture
async def writer(db):
    return MidWriter(db)


@pytest.fixture
async def reader(db):
    return MidReader(db)


@pytest.fixture(autouse=True)
async def _cleanup(db, isolate_tag):
    yield
    for domain in DOMAINS:
        try:
            await db[MID_COLLECTION_MAP[domain]].delete_many({"meta.tags": isolate_tag})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Schema round-trip
# ---------------------------------------------------------------------------


def test_metadata_defaults():
    m = MidMetadata()
    d = m.to_doc()
    assert d["strategy_type"] == "flash_loan_arbitrage"
    assert d["opportunity_type"] == "unknown"
    assert d["capital_source"] is None
    assert d["chain"] == "unknown"
    assert d["protocol"] is None
    assert d["execution_mode"] == "shadow"
    assert d["market_regime"] == "UNKNOWN"
    assert d["tags"] == []


def test_replay_context_defaults():
    r = ReplayContext()
    d = r.to_doc()
    for k in ("block_number", "block_timestamp",
              "quote_snapshot_id", "liquidity_snapshot_id", "gas_snapshot_id",
              "route_snapshot_id", "decision_snapshot_id", "market_snapshot_id"):
        assert k in d
        assert d[k] is None


def test_route_id_stable_across_calls():
    a = route_id_for("base", "flash_loan_arbitrage", "WETH", "USDC", ["uniswap_v3", "aerodrome"])
    b = route_id_for("base", "flash_loan_arbitrage", "WETH", "USDC", ["uniswap_v3", "aerodrome"])
    assert a == b
    c = route_id_for("base", "flash_loan_arbitrage", "WETH", "USDC", ["aerodrome", "uniswap_v3"])
    assert a != c  # dex_path order matters


def test_market_snapshot_id_stable():
    a = market_snapshot_id_for("base", "uniswap_v3", "WETH/USDC", "2026-08-02T09:00:00")
    b = market_snapshot_id_for("base", "uniswap_v3", "WETH/USDC", "2026-08-02T09:00:00")
    assert a == b


# ---------------------------------------------------------------------------
# Enum registry
# ---------------------------------------------------------------------------


def test_enum_registry_seeded():
    reset_registry_for_tests()
    reg = get_registry()
    assert reg.contains(STRATEGY_TYPE, "flash_loan_arbitrage")
    assert reg.contains(EXECUTION_MODE, "shadow")
    assert reg.contains(MARKET_REGIME, "UNKNOWN")
    assert reg.is_closed(EXECUTION_MODE)
    assert not reg.is_closed(STRATEGY_TYPE)


def test_enum_registry_register_open():
    reset_registry_for_tests()
    reg = get_registry()
    assert not reg.contains(STRATEGY_TYPE, "cex_dex_arbitrage")
    reg.register(STRATEGY_TYPE, "cex_dex_arbitrage")
    assert reg.contains(STRATEGY_TYPE, "cex_dex_arbitrage")


def test_enum_registry_snapshot_shape():
    reset_registry_for_tests()
    snap = get_registry().snapshot()
    assert STRATEGY_TYPE in snap
    assert MARKET_REGIME in snap
    assert isinstance(snap[STRATEGY_TYPE], list)


# ---------------------------------------------------------------------------
# ensure_indexes idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_indexes_idempotent(db):
    s1 = await ensure_indexes(db)
    s2 = await ensure_indexes(db)  # second call must not raise
    for domain in DOMAINS:
        assert MID_COLLECTION_MAP[domain] in s1
        assert MID_COLLECTION_MAP[domain] in s2


# ---------------------------------------------------------------------------
# Writers happy path (all 11)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_market_state(writer, db, isolate_tag):
    meta = make_meta(chain="base", protocol="uniswap_v3", tags=[isolate_tag])
    mid_id = await writer.write_market_state(
        chain="base", dex="uniswap_v3", pair="WETH/USDC",
        mid_price=2500.0, meta=meta,
        replay_context=ReplayContext(block_number=12345, block_timestamp="2026-08-02T09:00:00Z"),
    )
    doc = await db["mid_market_state"].find_one({"mid_id": mid_id})
    assert doc is not None
    assert doc["dex"] == "uniswap_v3"
    assert doc["mid_price"] == 2500.0
    assert doc["market_snapshot_id"].startswith("ms:base:uniswap_v3:WETH/USDC:")
    assert doc["replay_context"]["block_number"] == 12345
    assert doc["meta"]["market_regime"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_write_quote(writer, db, isolate_tag):
    rid = route_id_for("base", "flash_loan_arbitrage", "WETH", "USDC", ["uniswap_v3"])
    meta = make_meta(chain="base", tags=[isolate_tag])
    mid_id = await writer.write_quote(
        route_id=rid, dex="uniswap_v3",
        hops=[{"token_in": "WETH", "token_out": "USDC"}],
        quote_out=2500.0, meta=meta,
    )
    doc = await db["mid_quotes"].find_one({"mid_id": mid_id})
    assert doc["route_id"] == rid
    assert doc["meta"]["strategy_type"] == "flash_loan_arbitrage"


@pytest.mark.asyncio
async def test_write_liquidity_snapshot(writer, db, isolate_tag):
    meta = make_meta(chain="base", protocol="uniswap_v3", tags=[isolate_tag])
    mid_id = await writer.write_liquidity_snapshot(
        dex="uniswap_v3", pool="0xdeadbeef",
        reserves={"WETH": "1000000000000000000", "USDC": "2500000000"},
        meta=meta,
    )
    doc = await db["mid_liquidity"].find_one({"mid_id": mid_id})
    assert doc["pool"] == "0xdeadbeef"


@pytest.mark.asyncio
async def test_write_gas_snapshot(writer, db, isolate_tag):
    meta = make_meta(chain="base", tags=[isolate_tag])
    mid_id = await writer.write_gas_snapshot(
        meta=meta, gas_price_wei="30000000000", priority_fee_wei="1000000000",
    )
    doc = await db["mid_gas"].find_one({"mid_id": mid_id})
    assert doc["gas_price_wei"] == "30000000000"


@pytest.mark.asyncio
async def test_write_provider_snapshot(writer, db, isolate_tag):
    meta = make_meta(chain="base", capital_source="flash_loan_aave_v3", tags=[isolate_tag])
    mid_id = await writer.write_provider_snapshot(
        provider_id="aave_v3:base", meta=meta,
        available=True, observed_cost_bps=5.0,
    )
    doc = await db["mid_providers"].find_one({"mid_id": mid_id})
    assert doc["provider_id"] == "aave_v3:base"
    assert doc["observed_cost_bps"] == 5.0


@pytest.mark.asyncio
async def test_write_route_observation_upserts(writer, db, isolate_tag):
    rid = f"base:flash_loan_arbitrage:WETH->USDC:{uuid.uuid4().hex[:12]}"
    meta = make_meta(chain="base", tags=[isolate_tag])
    fp = {"chain": "base", "family": "flash_loan_arbitrage",
          "in_token": "WETH", "out_token": "USDC", "dex_path": ["uniswap_v3"]}
    id1 = await writer.write_route_observation(route_id=rid, fingerprint_parts=fp, meta=meta)
    id2 = await writer.write_route_observation(route_id=rid, fingerprint_parts=fp, meta=meta)
    # upsert semantics: same mid_id returned
    assert id1 == id2
    doc = await db["mid_routes"].find_one({"route_id": rid})
    assert doc["sample_count"] == 2


@pytest.mark.asyncio
async def test_write_opportunity_event_ordinal(writer, db, isolate_tag):
    opp = f"opp_{uuid.uuid4().hex[:8]}"
    meta = make_meta(chain="base", tags=[isolate_tag])
    m1 = await writer.write_opportunity_event(opp_id=opp, event_type="discovered", meta=meta)
    m2 = await writer.write_opportunity_event(opp_id=opp, event_type="quoted", meta=meta)
    d1 = await db["mid_opportunities"].find_one({"mid_id": m1})
    d2 = await db["mid_opportunities"].find_one({"mid_id": m2})
    assert d1["event_ordinal"] == 0
    assert d2["event_ordinal"] == 1
    assert d1["event_id"] == f"{opp}:0000"
    assert d2["event_id"] == f"{opp}:0001"


@pytest.mark.asyncio
async def test_write_confidence(writer, db, isolate_tag):
    meta = make_meta(chain="base", tags=[isolate_tag])
    mid_id = await writer.write_confidence(
        opp_id="opp_xx", score=0.83, inputs={"regime": "UNKNOWN"}, meta=meta,
    )
    doc = await db["mid_confidence"].find_one({"mid_id": mid_id})
    assert doc["score"] == 0.83


@pytest.mark.asyncio
async def test_write_decision(writer, db, isolate_tag):
    meta = make_meta(chain="base", tags=[isolate_tag])
    mid_id = await writer.write_decision(
        opp_id="opp_xx", gate="preflight", verdict="allow", meta=meta,
    )
    doc = await db["mid_decisions"].find_one({"mid_id": mid_id})
    assert doc["gate"] == "preflight"
    assert doc["verdict"] == "allow"


@pytest.mark.asyncio
async def test_write_outcome(writer, db, isolate_tag):
    meta = make_meta(chain="base", execution_mode="shadow", tags=[isolate_tag])
    mid_id = await writer.write_outcome(
        opp_id="opp_xx", terminal="shadow", pnl_usd=1.23, meta=meta,
    )
    doc = await db["mid_outcomes"].find_one({"mid_id": mid_id})
    assert doc["terminal"] == "shadow"
    assert doc["pnl_usd"] == 1.23


@pytest.mark.asyncio
async def test_write_replay(writer, db, isolate_tag):
    meta = make_meta(chain="base", tags=[isolate_tag])
    mid_id = await writer.write_replay(
        opp_id="opp_xx", variant_id="alt_provider_balancer",
        counter_factual_outcome={"pnl_usd_delta": 0.42}, meta=meta,
    )
    doc = await db["mid_replay"].find_one({"mid_id": mid_id})
    assert doc["variant_id"] == "alt_provider_balancer"


# ---------------------------------------------------------------------------
# Enum warning path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_enum_writes_audit_row(writer, db, isolate_tag):
    reset_registry_for_tests()
    meta = make_meta(strategy_type="cex_dex_arbitrage", chain="base", tags=[isolate_tag])
    await writer.write_gas_snapshot(meta=meta, gas_price_wei="1")
    # audit row exists
    audit = await db["mid_enum_warnings"].find_one({"value": "cex_dex_arbitrage"})
    assert audit is not None


# ---------------------------------------------------------------------------
# Reader query + filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reader_filters(writer, reader, isolate_tag):
    m_shadow = make_meta(chain="base", execution_mode="shadow", tags=[isolate_tag])
    m_paper = make_meta(chain="base", execution_mode="paper", tags=[isolate_tag])
    await writer.write_gas_snapshot(meta=m_shadow, gas_price_wei="1")
    await writer.write_gas_snapshot(meta=m_paper, gas_price_wei="2")
    rows = await reader.query("gas", execution_mode="shadow", limit=10)
    tagged = [r for r in rows if isolate_tag in (r.get("meta", {}).get("tags") or [])]
    assert len(tagged) == 1
    assert tagged[0]["meta"]["execution_mode"] == "shadow"


@pytest.mark.asyncio
async def test_reader_status(reader):
    st = await reader.status()
    assert "domains" in st
    for d in DOMAINS:
        assert d in st["domains"]
        assert "collection" in st["domains"][d]


# ---------------------------------------------------------------------------
# REST endpoints (against running server)
# ---------------------------------------------------------------------------


def test_endpoint_mid_status():
    r = requests.get(f"{API}/arbicore/mid/status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is True
    assert "domains" in body
    for d in DOMAINS:
        assert d in body["domains"]


def test_endpoint_mid_query_valid_domain():
    r = requests.get(f"{API}/arbicore/mid/query/gas", params={"limit": 5}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["domain"] == "gas"
    assert "rows" in body
    assert isinstance(body["rows"], list)


def test_endpoint_mid_query_unknown_domain():
    r = requests.get(f"{API}/arbicore/mid/query/not_a_domain", timeout=10)
    assert r.status_code == 404


def test_endpoint_mid_query_metadata_filter():
    r = requests.get(
        f"{API}/arbicore/mid/query/opportunities",
        params={"strategy_type": "flash_loan_arbitrage", "chain": "base", "limit": 5},
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filters"]["strategy_type"] == "flash_loan_arbitrage"
    assert body["filters"]["chain"] == "base"


def test_endpoint_mid_enums():
    r = requests.get(f"{API}/arbicore/mid/enums", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "enums" in body
    assert STRATEGY_TYPE in body["enums"]
    assert EXECUTION_MODE in body["enums"]
    assert MARKET_REGIME in body["enums"]
    assert body["closed"][EXECUTION_MODE] is True
    assert body["closed"][STRATEGY_TYPE] is False
