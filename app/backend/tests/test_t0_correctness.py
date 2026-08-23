"""T0 correctness acceptance matrix.

Proves the 12 required T0 guarantees with pure/in-memory fixtures — no Mongo,
no live RPC. Run:  python -m pytest tests/test_t0_correctness.py -p no:xdist
"""
import os
import pytest

# composition.py imports services.db which reads MONGO_URL at import time
# (motor client is lazy — no connection). Provide a safe default for offline
# unit tests; never used to connect.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")


# ── #6 RPC precedence deterministic ──────────────────────────────────────
def test_rpc_precedence_deterministic(monkeypatch):
    from arbicore.config.persistent import resolve_rpc_url_from_env
    for k in ("ARBICORE_RPC_URL_BASE", "ARBICORE_RPC_URL", "BASE_RPC_URL"):
        monkeypatch.delenv(k, raising=False)
    assert resolve_rpc_url_from_env("base") is None            # fail fast
    monkeypatch.setenv("BASE_RPC_URL", "legacy")
    assert resolve_rpc_url_from_env("base") == "legacy"
    monkeypatch.setenv("ARBICORE_RPC_URL", "generic")
    assert resolve_rpc_url_from_env("base") == "generic"       # beats legacy
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "chain")
    assert resolve_rpc_url_from_env("base") == "chain"         # beats generic


def test_env_sync_writes_legacy_alias(monkeypatch):
    import asyncio
    from arbicore.config.env_sync import sync_env_from_network_config
    for k in ("ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE", "BASE_RPC_URL"):
        monkeypatch.delenv(k, raising=False)

    class _Repo:
        async def get(self):
            return {"rpc_urls": {"base": ["https://x"]}, "executor_addresses": {}}

    exported = asyncio.get_event_loop().run_until_complete(
        sync_env_from_network_config(_Repo(), chain="base"))
    assert os.environ["ARBICORE_RPC_URL_BASE"] == "https://x"
    assert os.environ["BASE_RPC_URL"] == "https://x"           # legacy alias
    assert "BASE_RPC_URL" in exported


# ── #5 missing mode distinguishable from legitimate OBSERVE ───────────────
async def test_mode_resolution_missing_vs_observe():
    from arbicore.execution.pipeline import (
        OpportunityPipeline, MODE_UNRESOLVED, MODE_ERROR,
    )

    class _ModeRepo:
        def __init__(self, table): self.table = table
        async def get(self, s): return self.table.get(s)

    p = OpportunityPipeline.__new__(OpportunityPipeline)
    # seeded OBSERVE ⇒ legitimate OBSERVE (unchanged)
    p._mode = _ModeRepo({"flash_loan_arbitrage": {"mode": "OBSERVE"}})
    assert await p._resolve_mode("flash_loan_arbitrage") == "OBSERVE"
    # seeded SHADOW ⇒ real reaches analysis (proof #2)
    p._mode = _ModeRepo({"flash_loan_arbitrage": {"mode": "SHADOW"}})
    assert await p._resolve_mode("FLASH_LOAN_ARBITRAGE") == "SHADOW"  # case-norm
    # MISSING row ⇒ explicit unresolved sentinel, NOT silent OBSERVE
    p._mode = _ModeRepo({})
    assert await p._resolve_mode("flash_loan_arbitrage") == MODE_UNRESOLVED

    class _Boom:
        async def get(self, s): raise RuntimeError("db down")
    p._mode = _Boom()
    assert await p._resolve_mode("flash_loan_arbitrage") == MODE_ERROR


async def test_readiness_fault_is_explicit_not_observe():
    from arbicore.execution.pipeline import (
        OpportunityPipeline, MODE_UNRESOLVED, MODE_ERROR,
    )
    p = OpportunityPipeline.__new__(OpportunityPipeline)
    r = p._readiness_fault_result(MODE_UNRESOLVED, "flash_loan_arbitrage", "op1")
    assert r.action == "readiness_error" and r.outcome == "READINESS_ERROR"
    assert r.mode != "OBSERVE" and "config_missing" in r.reason
    r2 = p._readiness_fault_result(MODE_ERROR, "flash_loan_arbitrage", "op2")
    assert r2.action == "infra_error" and r2.outcome == "INFRA_ERROR"


# ── #1 canonical scanner cannot silently run noop ─────────────────────────
def test_scanner_noop_blocked_in_analysis_mode():
    from arbicore.runtime.composition import flash_loan_quote_readiness
    bad = flash_loan_quote_readiness(quote_provider_is_default=True, mode="SHADOW")
    assert bad["ready"] is False and bad["active"] is False
    assert bad["readiness_error"] and bad["quote_provider"] == "noop"
    # noop allowed only in OBSERVE / cold-start
    ok_obs = flash_loan_quote_readiness(quote_provider_is_default=True, mode="OBSERVE")
    assert ok_obs["ready"] is True
    live = flash_loan_quote_readiness(quote_provider_is_default=False, mode="SHADOW")
    assert live["ready"] is True and live["active"] is True and live["quote_provider"] == "live"


# ── #3 synthetic cannot enter canonical stream ────────────────────────────
def _mk_opp(prov):
    from arbicore.models.canonical import CanonicalOpportunity
    from arbicore.models.enums import (
        OpportunityType, OpportunityStatus, DataProvenance, MevRiskLevel,
    )
    return CanonicalOpportunity(
        opportunity_id="t0-x", opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id="s", asset="WETH", chain="base",
        spread_pct=0.0, expected_profit_usd=0.0, capital_required_usd=0.0,
        confidence_score=50.0, risk_score=20.0, mev_risk_level=MevRiskLevel.MEDIUM,
        source_data_quality=prov, status=OpportunityStatus.CANDIDATE,
    )


def test_canonical_write_gate_rejects_synthetic(monkeypatch):
    from arbicore.data.opportunity_repo import validate_for_upsert
    from arbicore.models.enums import DataProvenance
    monkeypatch.setenv("ARBICORE_CANONICAL_STRICT_PROVENANCE", "true")
    with pytest.raises(ValueError):
        validate_for_upsert(_mk_opp(DataProvenance.SIMULATED))
    # REAL passes the gate
    validate_for_upsert(_mk_opp(DataProvenance.REAL))
    # DEAD always rejected regardless of flag
    monkeypatch.setenv("ARBICORE_CANONICAL_STRICT_PROVENANCE", "false")
    with pytest.raises(ValueError):
        validate_for_upsert(_mk_opp(DataProvenance.DEAD))
    # non-strict: SIMULATED not rejected by the strict gate (legacy tests safe)
    validate_for_upsert(_mk_opp(DataProvenance.SIMULATED))


def test_thin_activator_quarantined_to_research_collection():
    # DiscoveryRepo default collection is the research collection, not canonical.
    import inspect
    from arbicore.execution.discovery import DiscoveryRepo
    sig = inspect.signature(DiscoveryRepo.__init__)
    assert sig.parameters["collection"].default == "arbicore_research_candidates"
    # And the canonical-upsert path is disabled (no repo.upsert(canonical)).
    src = inspect.getsource(
        __import__("arbicore.execution.discovery", fromlist=["x"]))
    assert "await repo.upsert(canonical)" not in src


# ── #4 PaperRunner does not consume synthetic ─────────────────────────────
async def test_paper_runner_filters_to_real_provenance():
    from arbicore.paper.runner import PaperValidationRunner, RunnerMetrics
    from arbicore.models.enums import LEARNING_ELIGIBLE_PROVENANCE

    seen = {}

    class _Src:
        async def find(self, *a, **kw):
            seen["provenance_filter"] = kw.get("provenance_filter")
            return []

    r = PaperValidationRunner.__new__(PaperValidationRunner)
    r._opp_source = _Src(); r._batch_limit = 10; r.metrics = RunnerMetrics()
    await r._fetch_opps()
    assert seen["provenance_filter"] == LEARNING_ELIGIBLE_PROVENANCE
    assert __import__("arbicore.models.enums", fromlist=["x"]).DataProvenance.SIMULATED \
        not in LEARNING_ELIGIBLE_PROVENANCE


# ── #7 economics agree across callers ─────────────────────────────────────
def test_economics_single_source_of_truth():
    from arbicore.scanners.economics import (
        aggregate_economics, canonical_net_profit_usd, LegCost,
    )
    from arbicore.models.enums import MevRiskLevel
    legs = [LegCost(leg_role="hop_0", venue_id="v", fee_bps=5, slippage_pct=0.0,
                    gas_estimate_usd=0.0, fee_kind="swap_fee")]
    a = aggregate_economics(legs=legs, gross_spread_pct=1.0, notional_usd=10_000.0,
                            mev_risk_level=MevRiskLevel.LOW)
    assert canonical_net_profit_usd(a) == a.expected_profit_usd


# ── #8 $25 gate unchanged ─────────────────────────────────────────────────
def test_gate7_floor_is_still_25():
    from arbicore.scanners.flash_loan_arbitrage.filter import FlashLoanGate7AtomicProfit
    g = FlashLoanGate7AtomicProfit(thresholds={})
    assert g.evaluate(atomic_profit_usd=24.99, borrow_amount_usd=1e5).passed is False
    assert g.evaluate(atomic_profit_usd=25.00, borrow_amount_usd=1e5).passed is True


# ── #9 TVL cannot fabricate a liquidity pass (fail closed) ────────────────
def test_gate8_fails_closed_on_unverifiable_tvl():
    from arbicore.scanners.flash_loan_arbitrage.filter import FlashLoanGate8LiquidityDepth
    g = FlashLoanGate8LiquidityDepth(thresholds={})
    res0 = g.evaluate(min_pool_tvl_usd_in_route=0.0)
    assert res0.passed is False and res0.metric_snapshot.get("liquidity_unverifiable")
    # real high TVL still passes
    assert g.evaluate(min_pool_tvl_usd_in_route=5_000_000.0).passed is True


def test_base_venues_sentinel_removed():
    from arbicore.discovery.base_venues import build_pool_graph
    pools, _ = build_pool_graph()
    assert pools and all(p.tvl_usd == 0.0 for p in pools)  # no $5M sentinel


async def test_unknown_tvl_provider_returns_none():
    from arbicore.scanners.flash_loan_arbitrage.tvl_provider import (
        UnknownTVLProvider, StaticTVLProvider,
    )
    assert await UnknownTVLProvider().get_pool_tvl_usd("base", "0xp") is None
    assert await StaticTVLProvider({"0xp": 42.0}).get_pool_tvl_usd("base", "0xp") == 42.0


# ── #10 certification excludes synthetic evidence ─────────────────────────
def test_certification_excludes_synthetic():
    from arbicore.certification.engine import partition_executable_by_provenance
    rows = [
        {"source_data_quality": "REAL"},
        {"source_data_quality": "VERIFIED_REAL"},
        {"source_data_quality": "SIMULATED"},
        {"source_data_quality": None},           # unknown ⇒ non-real
        {},                                       # missing ⇒ non-real
    ]
    real, synthetic = partition_executable_by_provenance(rows)
    assert len(real) == 2 and len(synthetic) == 3


# ── #11 historical evidence intact (additive, backfill never deletes) ─────
def test_evidence_field_additive_and_backfill_no_delete():
    from arbicore.paper.evidence import EvidenceBundle
    import dataclasses, inspect
    f = {x.name: x for x in dataclasses.fields(EvidenceBundle)}
    assert "source_data_quality" in f and f["source_data_quality"].default is None
    src = inspect.getsource(
        __import__("arbicore.scripts.t0_provenance_backfill", fromlist=["x"]))
    assert "delete_many" not in src and "drop(" not in src and ".delete_one" not in src


# ── #12 no automatic live promotion ───────────────────────────────────────
def test_no_auto_live_promotion():
    from arbicore.execution.mode import default_mode_map, validate_transition
    m = default_mode_map()
    assert m["flash_loan_arbitrage"] == "SHADOW"
    assert "LIMITED_LIVE" not in m.values() and "FULL_LIVE" not in m.values()
    # ladder forbids skipping straight to live
    with pytest.raises(ValueError):
        validate_transition("SHADOW", "FULL_LIVE")


# ── T0-8 minimal ChainAdapter (Base isolation) ────────────────────────────
async def test_base_chain_adapter():
    from arbicore.chains import BaseChainAdapter, ChainCapability
    a = BaseChainAdapter()
    assert a.chain == "base" and a.chain_id() == 8453 and a.native_token() == "ETH"
    assert a.flashloan_provider_registry()  # aave/balancer/uniswap
    cap = await a.capability()
    assert isinstance(cap, ChainCapability)
    assert cap.active_ready is False  # never active on assumptions alone
