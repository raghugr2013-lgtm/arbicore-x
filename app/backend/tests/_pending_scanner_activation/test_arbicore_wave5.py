"""Phase C Wave 5 — Shadow Binding tests.

Coverage:
  - Mapper purity & determinism
  - Lifecycle status projection
  - Provenance projection
  - Observer end-to-end (in-process, real Mongo)
  - Approval proposer post_run_hook contract
  - Wave 5 endpoint contract
"""
import asyncio
import os
import time

import pytest
import requests

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.enums import (
    DataProvenance,
    MarketRegime,
    MevRiskLevel,
    OpportunityStatus,
    OpportunityType,
    RouteHealth,
)
from arbicore.shadow.mapper import (
    LegacyProposalMapper,
    LEGACY_ASSET,
    LEGACY_BUY_VENUE,
    LEGACY_OPPORTUNITY_TYPE,
    LEGACY_SELL_VENUE,
    LEGACY_SUBJECT_ID,
    SHADOW_OPP_ID_PREFIX,
    map_proposal_to_canonical,
    opportunity_id_for,
)


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://exec-readiness-x.preview.emergentagent.com",
).rstrip("/")


@pytest.fixture(scope="module")
def event_loop():
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import db as _db_mod
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _db_mod.client = AsyncIOMotorClient(os.environ['MONGO_URL'], io_loop=loop)
    _db_mod.db = _db_mod.client[os.environ['DB_NAME']]
    yield loop
    loop.close()


def _run(loop, coro):
    return loop.run_until_complete(coro)


def _make_proposal(**overrides):
    """Realistic shape of one element of build_proposals().secondary."""
    base = {
        "proposal_id":              "prop_batch_abc_500",
        "batch_id":                 "batch_abc",
        "size_usd":                 500.0,
        "buy_price":                0.0410,
        "buy_price_source":         "userscript_v2_batch",
        "sell_price":               0.0420,
        "gross_spread_pct":         2.4390,
        "net_roi_pct":              2.1390,
        "fee_drag_pct":             0.3000,
        "expected_profit_usd":      10.695,
        "expected_cycle_s":         600,
        "combined_survival_prob":   0.74,
        "regime":                   "Volatile",
        "risk_label":               "MEDIUM",
        "risk_score":               42,
        "liquidity_feasible":       True,
        "profitable_buyer_depth_usd": 1500.0,
        "quality_score":            3.123,
        "quote_age_s":              4.0,
        "bdag_expected":            12195.12,
        "stale":                    False,
        "actionable":               True,
    }
    base.update(overrides)
    return base


# ============================================================================
# Mapper — pure determinism
# ============================================================================

def test_opportunity_id_is_deterministic():
    a = opportunity_id_for("prop_batch_abc_500")
    b = opportunity_id_for("prop_batch_abc_500")
    c = opportunity_id_for("prop_batch_abc_400")
    assert a == b
    assert a != c
    assert a.startswith(SHADOW_OPP_ID_PREFIX)


def test_map_proposal_returns_canonical():
    opp = map_proposal_to_canonical(_make_proposal(), tier="primary")
    assert isinstance(opp, CanonicalOpportunity)
    assert opp.opportunity_id == opportunity_id_for("prop_batch_abc_500")
    assert opp.opportunity_type is LEGACY_OPPORTUNITY_TYPE
    assert opp.opportunity_type is OpportunityType.CEX_ARBITRAGE
    assert opp.asset == LEGACY_ASSET
    assert opp.subject_id == LEGACY_SUBJECT_ID
    assert opp.buy_venue == LEGACY_BUY_VENUE
    assert opp.sell_venue == LEGACY_SELL_VENUE
    assert opp.buy_price == 0.0410
    assert opp.sell_price == 0.0420
    assert opp.spread_pct == 2.4390
    assert opp.expected_profit_usd == 10.695
    assert opp.capital_required_usd == 500.0


def test_map_proposal_provenance_is_real_for_userscript():
    opp = map_proposal_to_canonical(_make_proposal(), tier="primary")
    assert opp.source_data_quality is DataProvenance.REAL
    assert opp.is_learning_eligible is True


def test_map_proposal_provenance_simulated_for_test_mode():
    p = _make_proposal(buy_price_source="userscript_test_mode_batch")
    opp = map_proposal_to_canonical(p, tier="primary")
    assert opp.source_data_quality is DataProvenance.SIMULATED
    assert opp.is_learning_eligible is False


def test_map_proposal_status_actionable_is_validated():
    opp_actionable = map_proposal_to_canonical(_make_proposal(actionable=True))
    assert opp_actionable.status is OpportunityStatus.VALIDATED
    opp_not = map_proposal_to_canonical(_make_proposal(actionable=False))
    assert opp_not.status is OpportunityStatus.CANDIDATE


def test_map_proposal_regime_projection():
    assert map_proposal_to_canonical(_make_proposal(regime="Stable")).market_regime is MarketRegime.CALM
    assert map_proposal_to_canonical(_make_proposal(regime="Volatile")).market_regime is MarketRegime.VOLATILE
    assert map_proposal_to_canonical(_make_proposal(regime="Extremely Volatile")).market_regime is MarketRegime.VOLATILE
    assert map_proposal_to_canonical(_make_proposal(regime=None)).market_regime is MarketRegime.UNKNOWN


def test_map_proposal_mev_proxy():
    assert map_proposal_to_canonical(_make_proposal(risk_label="LOW")).mev_risk_level is MevRiskLevel.LOW
    assert map_proposal_to_canonical(_make_proposal(risk_label="HIGH")).mev_risk_level is MevRiskLevel.HIGH
    assert map_proposal_to_canonical(_make_proposal(risk_label="VERY_HIGH")).mev_risk_level is MevRiskLevel.HIGH


def test_map_proposal_route_health():
    fresh = map_proposal_to_canonical(_make_proposal(quote_age_s=2, liquidity_feasible=True))
    assert fresh.route_health is RouteHealth.PERSISTENT
    stale = map_proposal_to_canonical(_make_proposal(quote_age_s=20, liquidity_feasible=True))
    assert stale.route_health is RouteHealth.NEW
    illiq = map_proposal_to_canonical(_make_proposal(liquidity_feasible=False))
    assert illiq.route_health is RouteHealth.SHORT_LIVED


def test_map_proposal_returns_none_for_missing_id():
    assert map_proposal_to_canonical({"buy_price": 1.0}) is None


def test_map_proposal_returns_none_for_missing_prices():
    assert map_proposal_to_canonical({"proposal_id": "x"}) is None


def test_map_proposal_metadata_tagged_for_audit():
    opp = map_proposal_to_canonical(_make_proposal(), tier="secondary")
    assert opp.metadata.get("shadow_binding") is True
    assert opp.metadata.get("tier") == "secondary"
    assert opp.metadata.get("legacy_proposal_id") == "prop_batch_abc_500"
    assert opp.metadata.get("legacy_batch_id") == "batch_abc"
    assert opp.metadata.get("legacy_category") == "legacy_bdag"


def test_map_proposal_category_metadata_uses_known_vocabulary():
    """Soft-typed vocabulary check — no unknown keys."""
    from arbicore.models.category_metadata import KNOWN_CATEGORY_METADATA_KEYS
    known = KNOWN_CATEGORY_METADATA_KEYS[OpportunityType.CEX_ARBITRAGE]
    opp = map_proposal_to_canonical(_make_proposal(), tier="primary")
    for k in (opp.category_metadata or {}).keys():
        assert k in known, f"Unknown category_metadata key emitted: {k}"


def test_snapshot_mapper_orders_primary_then_secondary():
    primary = _make_proposal(proposal_id="prop_X_1000", size_usd=1000)
    sec_a = _make_proposal(proposal_id="prop_X_500", size_usd=500)
    sec_b = _make_proposal(proposal_id="prop_X_250", size_usd=250)
    snapshot = {
        "primary": primary,
        "secondary": [sec_a, sec_b],
        "ranked_count": 3, "actionable_count": 3,
        "blockers": [], "now": "2026-06-19T00:00:00Z",
    }
    opps = LegacyProposalMapper.map_snapshot(snapshot)
    assert len(opps) == 3
    assert opps[0].metadata["tier"] == "primary"
    assert opps[0].opportunity_id == opportunity_id_for("prop_X_1000")
    assert opps[1].metadata["tier"] == "secondary"
    assert opps[1].opportunity_id == opportunity_id_for("prop_X_500")
    assert opps[2].metadata["tier"] == "secondary"


def test_snapshot_mapper_empty_when_no_primary_and_no_secondary():
    assert LegacyProposalMapper.map_snapshot({"primary": None, "secondary": []}) == []
    assert LegacyProposalMapper.map_snapshot({}) == []


def test_snapshot_mapper_drops_bad_items_silently():
    snapshot = {
        "primary": _make_proposal(),
        "secondary": [
            {"proposal_id": None},          # dropped
            {"buy_price": 1.0},              # dropped (no id)
            _make_proposal(proposal_id="prop_ok_100"),
        ],
    }
    opps = LegacyProposalMapper.map_snapshot(snapshot)
    assert len(opps) == 2


# ============================================================================
# Observer — end-to-end against Mongo
# ============================================================================

def test_observer_persists_canonical_opportunity_and_outcome_rows(event_loop):
    from arbicore.runtime.composition import (
        get_opportunity_repo,
        get_outcome_repo,
        get_shadow_binder,
        initialise_arbicore_runtime,
    )
    _run(event_loop, initialise_arbicore_runtime())
    binder = get_shadow_binder()
    pid = f"prop_test_e2e_{int(time.time())}"
    snapshot = {
        "primary": _make_proposal(proposal_id=pid, size_usd=300),
        "secondary": [],
        "ranked_count": 1, "actionable_count": 1, "blockers": [],
    }
    report = _run(event_loop, binder.observe(snapshot))
    assert report["mapped"] == 1
    assert report["upserted"] == 1
    assert report["emissions"] == 1
    # Verify canonical row landed
    opp_id = opportunity_id_for(pid)
    opp = _run(event_loop, get_opportunity_repo().get(opp_id))
    assert opp is not None
    assert opp.opportunity_id == opp_id
    assert opp.opportunity_type is OpportunityType.CEX_ARBITRAGE
    # Verify outcome rows seeded for default 5 horizons
    rows = _run(event_loop, get_outcome_repo().list_for_subject(opp.subject_id))
    horizon_labels = {r.horizon_label for r in rows
                      if r.opportunity_id == opp_id}
    assert {"5m", "15m", "1h", "6h", "24h"}.issubset(horizon_labels)


def test_observer_idempotent_for_same_proposal_id(event_loop):
    from arbicore.runtime.composition import (
        get_opportunity_repo,
        get_outcome_repo,
        get_shadow_binder,
        initialise_arbicore_runtime,
    )
    _run(event_loop, initialise_arbicore_runtime())
    binder = get_shadow_binder()
    pid = f"prop_test_idem_{int(time.time())}"
    snapshot = {
        "primary": _make_proposal(proposal_id=pid, size_usd=300),
        "secondary": [],
    }
    _run(event_loop, binder.observe(snapshot))
    _run(event_loop, binder.observe(snapshot))
    _run(event_loop, binder.observe(snapshot))
    rows = _run(event_loop, get_outcome_repo().list_for_subject(LEGACY_SUBJECT_ID))
    # Idempotent — each (opportunity_id, horizon_label) appears once.
    opp_id = opportunity_id_for(pid)
    horizons = [r.horizon_label for r in rows if r.opportunity_id == opp_id]
    assert sorted(horizons) == sorted(set(horizons))


def test_observer_skips_simulated_provenance_for_learning(event_loop):
    from arbicore.runtime.composition import (
        get_shadow_binder,
        initialise_arbicore_runtime,
    )
    _run(event_loop, initialise_arbicore_runtime())
    binder = get_shadow_binder()
    before = binder.stats["skipped_non_learning"]
    pid = f"prop_test_sim_{int(time.time())}"
    snapshot = {
        "primary": _make_proposal(
            proposal_id=pid,
            buy_price_source="userscript_test_mode_batch",
        ),
        "secondary": [],
    }
    report = _run(event_loop, binder.observe(snapshot))
    # mapping still succeeds and we still upsert the canonical row
    # (provenance gate is for the learning subsystem, not persistence).
    assert report["mapped"] == 1
    assert report["upserted"] == 1
    # learning emission was skipped
    assert binder.stats["skipped_non_learning"] >= before + 1
    assert report["emissions"] == 0


def test_observer_swallows_persistence_errors(event_loop):
    """Faulty repo must not break observe(); errors land in stats."""
    from arbicore.shadow.observer import ShadowBindingObserver

    class _BoomRepo:
        async def upsert(self, opp):
            raise RuntimeError("simulated outage")

    class _Noop:
        async def aggregate_by_subject_horizon(self, *a, **kw):
            return []
        async def record_emission(self, opp):
            return 0
        async def append_state_snapshot(self, st):
            return None
        async def resolve_or_create(self, **kw):
            return None
        async def write(self, **kw):
            return None

    binder = ShadowBindingObserver(
        opportunity_repo=_BoomRepo(),
        outcome_repo=_Noop(),
        outcome_tracker=_Noop(),
        metrics_aggregator=_Noop(),
        entity_resolver=_Noop(),
        audit_log=_Noop(),
    )
    snapshot = {"primary": _make_proposal(proposal_id="prop_boom_1"), "secondary": []}
    rep = _run(event_loop, binder.observe(snapshot))
    assert rep["mapped"] == 1
    assert rep["upserted"] == 0
    assert binder.stats["errors_persistence"] >= 1
    assert binder.stats["last_error"] is not None


# ============================================================================
# Approval Proposer hook contract
# ============================================================================

def test_approval_proposer_has_post_run_hook_attached(event_loop):
    from arbicore.runtime.composition import initialise_arbicore_runtime
    _run(event_loop, initialise_arbicore_runtime())
    from services.execution.approval_proposer import approval_proposer
    assert hasattr(approval_proposer, "post_run_hook")
    assert approval_proposer.post_run_hook is not None


def test_approval_proposer_hook_swallows_errors(event_loop):
    """Even if the hook raises, _run_once must continue + set last_run_status=ok."""
    from services.execution.approval_proposer import ApprovalProposer

    async def _boom(_snap):
        raise RuntimeError("hook intentionally broken")

    proposer = ApprovalProposer()
    proposer.post_run_hook = _boom

    async def _go():
        await proposer.ensure_indexes()
        await proposer._run_once()

    _run(event_loop, _go())
    # Last run is still OK despite hook failure — the legacy loop is insulated.
    assert proposer.last_run_status == "ok"


# ============================================================================
# Wave 5 endpoint
# ============================================================================

def test_shadow_status_endpoint_requires_auth():
    r = requests.get(f"{BASE_URL}/api/arbicore/shadow/status", timeout=10)
    assert r.status_code in (401, 403)


def _login():
    s = requests.Session()
    s.post(
        f"{BASE_URL}/api/auth/login", timeout=10,
        json={"username": "admin", "password": "ArbiCore2026!"},
    )
    return s


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login", timeout=10,
        json={"username": "admin", "password": "ArbiCore2026!"},
    )
    if r.status_code != 200:
        pytest.skip(f"admin login unavailable ({r.status_code})")
    return s


def test_shadow_status_endpoint_returns_wave_5_payload(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/shadow/status", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wave"] == "C-5"
    assert body["mode"] == "SHADOW"
    assert body["hook_attached"] is True
    assert "binder" in body
    assert "snapshots_observed" in body["binder"]


def test_learning_status_includes_wave5_shadow_binder(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/learning-status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["wave"] == "C-5"
    assert "shadow_binder" in body
    assert body["shadow_binder"]["hook_attached"] is True


def test_health_endpoint_still_works_after_wave5_wire(auth_session):
    """Regression: health endpoint must remain functional."""
    r = auth_session.get(f"{BASE_URL}/api/arbicore/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
