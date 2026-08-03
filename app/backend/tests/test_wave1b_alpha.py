"""Sprint 1B-α — Intelligence Activation regression tests.

These tests validate:
  * Every engine constructs without error via ``activate_all``.
  * :class:`MidEvidenceBridge` writes valid rows into MID for every
    engine and records the write in ``BridgeStats``.
  * The mirror ``opportunity_event`` is written alongside each engine's
    domain-specific row.
  * ``IntelligenceRegistry`` exposes truthful status + snapshots.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
async def mid_writer_and_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mid import MidWriter

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"wave1b_alpha_test_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    writer = MidWriter(db)
    try:
        yield writer, db
    finally:
        await client.drop_database(db_name)
        client.close()


async def test_activate_all_engines_active(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all

    writer, _ = mid_writer_and_db
    result = activate_all(writer)
    summary = result.registry.summary()
    assert summary["engine_count"] == 6
    assert summary["active_count"] == 6
    assert summary["errored"] == []
    assert set(summary["active"]) == {
        "confidence", "roi", "route_ranking",
        "economics", "entity_scoring", "regime",
    }


async def test_confidence_bridge_writes_to_mid(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all
    writer, db = mid_writer_and_db
    result = activate_all(writer)

    opp_id = f"opp-{uuid.uuid4().hex[:8]}"
    mid_id = await result.bridge.publish_confidence(
        opp_id=opp_id, score=87.5, inputs={"route": "uniswap->sushi"},
    )
    assert mid_id is not None

    # confidence row landed
    row = await db["mid_confidence"].find_one({"opp_id": opp_id})
    assert row is not None
    assert row["score"] == 87.5

    # mirror event landed
    ev = await db["mid_opportunities"].find_one({
        "opp_id": opp_id,
        "event_type": "intel.confidence.score_written",
    })
    assert ev is not None

    stats = result.bridge.stats
    assert stats.total_writes >= 1
    assert stats.by_engine.get("confidence", 0) >= 1


async def test_route_ranking_bridge_writes_to_mid(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all
    from arbicore.intelligence.scoring import ChainProfile

    writer, db = mid_writer_and_db
    result = activate_all(writer)
    profile = ChainProfile(
        name="base",
        min_spread_percent=0.5,
        gas_score=1.0,
        mev_risk_score=1.2,
        min_chain_score=5.0,
    )
    breakdown = result.route_ranking.score(
        spread_percent=1.5, duration_seconds=45,
        available_liquidity=1_000_000, trade_amount=10_000,
        profile=profile,
    )
    route_id = f"base:dex:USDC->WETH:{uuid.uuid4().hex[:12]}"
    opp_id = f"opp-{uuid.uuid4().hex[:8]}"
    await result.bridge.publish_route_score(
        route_id=route_id,
        fingerprint_parts={"chain": "base", "in_token": "USDC",
                           "out_token": "WETH", "path": ["uniswap"]},
        score=breakdown.as_dict(),
        opp_id=opp_id,
    )
    row = await db["mid_routes"].find_one({"route_id": route_id})
    assert row is not None
    assert row["fingerprint_parts"]["chain_score"] == breakdown.chain_score
    assert row["sample_count"] == 1


async def test_economics_bridge_writes_decision(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all
    writer, db = mid_writer_and_db
    result = activate_all(writer)
    sizing = result.economics.size(
        available_liquidity=500_000, reference_capital_usd=40_000,
    )
    opp_id = f"opp-{uuid.uuid4().hex[:8]}"
    await result.bridge.publish_capital_sizing(
        opp_id=opp_id,
        sizing={
            "suggested_trade_size_usd": sizing.suggested_trade_size_usd,
            "binding_constraint": sizing.binding_constraint,
            "pool_limit_usd": sizing.pool_limit_usd,
            "wallet_limit_usd": sizing.wallet_limit_usd,
        },
    )
    decision = await db["mid_decisions"].find_one(
        {"opp_id": opp_id, "gate": "capital_sizing"})
    assert decision is not None
    assert "binding=" in decision["reason"]


async def test_regime_bridge_writes_provider_snapshot(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all
    writer, db = mid_writer_and_db
    result = activate_all(writer)
    await result.bridge.publish_regime(
        dominant_regime="CALM",
        tags=["deep_liquidity"],
        confidence=0.8, source="test",
    )
    prov = await db["mid_providers"].find_one({"provider_id": "regime:test"})
    assert prov is not None
    ev = await db["mid_opportunities"].find_one({
        "opp_id": "__regime__",
        "event_type": "intel.regime.classified",
    })
    assert ev is not None


async def test_entity_scoring_bridge_writes_event(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all
    writer, db = mid_writer_and_db
    result = activate_all(writer)
    await result.bridge.publish_entity_score(
        entity_id="0xabc", entity_type="wallet",
        outcome_score=0.72, succeeded=True,
    )
    ev = await db["mid_opportunities"].find_one({
        "opp_id": "ent:0xabc",
        "event_type": "intel.entity_scoring.outcome_recorded",
    })
    assert ev is not None


async def test_roi_bridge_writes_event(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all
    writer, db = mid_writer_and_db
    result = activate_all(writer)

    opp_id = f"opp-{uuid.uuid4().hex[:8]}"
    roi = {
        "sample_size": 10, "median_roi": 3.4,
        "breakout_probability": 0.12,
        "data_basis": "real",
    }
    await result.bridge.publish_roi_probability(opp_id=opp_id, roi=roi)
    ev = await db["mid_opportunities"].find_one({
        "opp_id": opp_id,
        "event_type": "intel.roi.probability",
    })
    assert ev is not None
    assert ev["payload"]["median_roi"] == 3.4


async def test_bridge_stats_track_all_engines(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all
    writer, _ = mid_writer_and_db
    result = activate_all(writer)

    opp = "opp-cover"
    await result.bridge.publish_confidence(opp_id=opp, score=50.0)
    await result.bridge.publish_capital_sizing(
        opp_id=opp,
        sizing={"suggested_trade_size_usd": 1000.0,
                "binding_constraint": "wallet"},
    )
    await result.bridge.publish_regime(
        dominant_regime="CALM", tags=[], confidence=0.5, source="cov")
    await result.bridge.publish_entity_score(
        entity_id="0x1", entity_type="wallet",
        outcome_score=1.0, succeeded=True)
    await result.bridge.publish_roi_probability(
        opp_id=opp, roi={"median_roi": 1.0})

    stats = result.bridge.stats.to_dict()
    assert stats["total_writes"] >= 5
    assert set(stats["by_engine"].keys()) >= {
        "confidence", "economics", "regime", "entity_scoring", "roi",
    }


async def test_registry_snapshot_for_each_engine(mid_writer_and_db):
    from arbicore.intelligence.wave1b import activate_all
    writer, _ = mid_writer_and_db
    result = activate_all(writer)
    for engine_id in ("confidence", "roi", "route_ranking",
                       "economics", "entity_scoring", "regime"):
        status = result.registry.get(engine_id)
        assert status is not None
        assert status.active is True
        snap = status.snapshot()
        assert snap["snapshot_available"] is True
