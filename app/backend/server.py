from fastapi import FastAPI, APIRouter, HTTPException, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

from arbicore.config.calibration_config import CalibrationConfig
from arbicore.config.adaptive_weights_config import AdaptiveWeightsConfig
from arbicore.config.signing_config import SigningConfig
from arbicore.data.mongo.calibration_models_repo import CalibrationModelsRepo
from arbicore.data.mongo.adaptive_weights_repo import AdaptiveWeightsRepo
from arbicore.data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
from arbicore.evidence.signer import EvidenceSigner, EvidenceVerifier
from arbicore.execution.mode import (
    ExecutionModeRepo, MODES, TRADING_STRATEGIES,
    default_mode_map, is_broadcast_allowed, validate_transition,
)
from arbicore.execution.pipeline import OpportunityPipeline, BROADCAST_MODES
from arbicore.execution.auto_executor import AutoExecutor
from arbicore.execution.wallet_registry import (
    EXECUTION_ROLES, SUPPORTED_CHAINS, WalletRegistryRepo,
)
from arbicore.data.mongo.opportunity_repo_mongo import MongoOpportunityRepository
from arbicore.data.journal import (
    OpportunityJournal, JournalEntry, ExecutionStatus, LearningLabel,
)
from arbicore.data.provenance import is_learning_eligible
from arbicore.models.canonical import CanonicalOpportunity, InvalidTransitionError
from arbicore.models.enums import (
    DataProvenance, OpportunityStatus, OpportunityType,
)
from arbicore.execution.adapters import AdapterRegistry
from arbicore.execution.broadcast import LimitedLiveBroadcaster
from arbicore.execution.calldata import encode_plan_head_call
from arbicore.execution.capital_policy import (
    CapitalAllocator, CapitalPolicyRepo, DEFAULT_POLICY as CAPITAL_DEFAULT_POLICY,
)
from arbicore.execution.certification import ExecutionCertifier, PIPELINE_STAGES
from arbicore.execution.discovery import (
    ContinuousDiscovery, DiscoveryRepo, DEFAULT_UNIVERSE_BASE,
)
from arbicore.execution.operator_wizard import (
    build_wizard_state, verify_executor, check_rpc,
    latest_broadcast_receipts, check_flash_loan_prereqs,
)
from arbicore.execution.operator_journey import build_journey
from arbicore.config.persistent import (
    ConfigRepo, NetworkConfigRepo, NETWORK_KIND,
)
from arbicore.config.env_sync import sync_env_from_network_config
from arbicore.config.stubs_migration import (
    OperatorAccountRepo, ExecutionSettingsRepo, OperationalFlagsRepo,
    ACCOUNT_KIND, EXECUTION_KIND, OPERATIONAL_KIND, NOTIFICATIONS_KIND,
)
from arbicore.config.scanner_config import (
    ScannerConfigRepo, SCANNER_GLOBAL_KIND, MARKET_FAMILIES,
)
from arbicore.data.scanner_config_defaults import CANONICAL_FAMILIES
from arbicore.notifications import TelegramAlertService, TELEGRAM_KIND
from arbicore.execution.gas import RpcGasOracle, StaticGasOracle
from arbicore.execution.quoter import QuoterRegistry
from arbicore.execution.kill_switch import KillSwitchEngagedError, KillSwitchRepo
from arbicore.execution.live_signer import LiveSigner
from arbicore.execution.mev import MevRouterRegistry
from arbicore.execution.planner import (
    DryRunEngine, ExecutionPlanner, ExecutionPlansRepo,
)
from arbicore.execution.simulation import SimulationRegistry
from arbicore.execution.slippage import SlippageEstimator
from arbicore.execution.wallet_balance import WalletBalanceReader
from arbicore.execution.wallet_health import WalletHealthCard
from arbicore.secrets.backends import FernetSecretBackend
from arbicore.secrets.registry import SecretRegistry
from arbicore.learning.concrete.calibrator_isotonic import IsotonicConfidenceCalibrator
from arbicore.learning.concrete.calibration_worker import CalibrationWorker
from arbicore.learning.concrete.adaptive_weights_observer import AdaptiveWeightsObserver
from arbicore.learning.concrete.adaptive_weights_worker import AdaptiveWeightsWorker
from arbicore.learning.concrete.evidence_signing_worker import EvidenceSigningWorker
from arbicore.learning.ledger import LearningLedger


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ---------------------------------------------------------------------------
# Wave-3 Confidence Calibration pipeline (initialised at import; started/
# stopped on FastAPI lifecycle events at the bottom of this file).
# ---------------------------------------------------------------------------
_CALIBRATION_CFG = CalibrationConfig.from_env()
_CALIBRATION_REPO = CalibrationModelsRepo(
    db, retired_ttl_days=_CALIBRATION_CFG.retired_ttl_days
)
_CALIBRATOR = IsotonicConfidenceCalibrator(
    min_samples_isotonic=_CALIBRATION_CFG.min_samples_isotonic,
    min_samples_platt=_CALIBRATION_CFG.min_samples_platt,
)
_CALIBRATION_WORKER = CalibrationWorker(
    db=db,
    calibrator=_CALIBRATOR,
    repo=_CALIBRATION_REPO,
    config=_CALIBRATION_CFG,
)

# ---------------------------------------------------------------------------
# Wave-4 Adaptive Weights (OBSERVE mode) pipeline — recommendation-only.
# Live scoring is NEVER touched.  Startup / shutdown wired at bottom of file.
# ---------------------------------------------------------------------------
_ADAPTIVE_WEIGHTS_CFG = AdaptiveWeightsConfig.from_env()
_ADAPTIVE_WEIGHTS_REPO = AdaptiveWeightsRepo(
    db, retired_ttl_days=_ADAPTIVE_WEIGHTS_CFG.retired_ttl_days
)
_ADAPTIVE_WEIGHTS_OBSERVER = AdaptiveWeightsObserver(_ADAPTIVE_WEIGHTS_CFG)
_ADAPTIVE_WEIGHTS_WORKER = AdaptiveWeightsWorker(
    db=db,
    observer=_ADAPTIVE_WEIGHTS_OBSERVER,
    repo=_ADAPTIVE_WEIGHTS_REPO,
    config=_ADAPTIVE_WEIGHTS_CFG,
)

# ---------------------------------------------------------------------------
# Wave-5 Evidence Bundle Signing (Ed25519) — signing is fully independent
# from learning + scoring.  Bootstrap policy = UNSIGNED unless key material
# is supplied via environment (see arbicore.config.signing_config).
# ---------------------------------------------------------------------------
_SIGNING_CFG = SigningConfig.from_env()
_EVIDENCE_SIGNER = EvidenceSigner(_SIGNING_CFG)
_EVIDENCE_VERIFIER = EvidenceVerifier(_SIGNING_CFG)
_EVIDENCE_REPO = EvidenceBundlesRepo(db)
_EVIDENCE_WORKER = EvidenceSigningWorker(
    db=db,
    signer=_EVIDENCE_SIGNER,
    repo=_EVIDENCE_REPO,
    calibration_repo=_CALIBRATION_REPO,
    adaptive_weights_repo=_ADAPTIVE_WEIGHTS_REPO,
    config=_SIGNING_CFG,
)

# ---------------------------------------------------------------------------
# Wave-6A · Execution Substrate (mode ladder, wallet registry, secret registry)
# READ-ONLY at REST surface; no live signing or fund movement.
# ---------------------------------------------------------------------------
_EXECUTION_MODE_REPO = ExecutionModeRepo(db)
_WALLET_REGISTRY = WalletRegistryRepo(db)
_SECRET_BACKEND = FernetSecretBackend(db)
_SECRET_REGISTRY = SecretRegistry(_SECRET_BACKEND)

# ---------------------------------------------------------------------------
# Wave-6B · Adapter framework + Planner + Dry-run + Plan repo.  SHADOW ONLY.
# Wave-6C additive: Gas Oracle, Slippage Estimator, Simulator Registry,
# MEV Router Registry.  All additive & backward-compatible.
# ---------------------------------------------------------------------------
_ADAPTER_REGISTRY = AdapterRegistry()
# Phase 10.10.8 · production-grade live oracle (RPC first, static fallback).
# The RpcGasOracle transparently degrades to StaticGasOracle when the RPC
# is unreachable, so downstream code never sees a hard outage.
_GAS_ORACLE = RpcGasOracle(fallback=StaticGasOracle())
_SLIPPAGE_ESTIMATOR = SlippageEstimator()
_SIMULATION_REGISTRY = SimulationRegistry()
_MEV_REGISTRY = MevRouterRegistry()
# Phase 10.10.8 · canonical live-quote engine (UniV3 + Aerodrome CL + classic).
_QUOTER_REGISTRY = QuoterRegistry()
_EXECUTION_PLANNER = ExecutionPlanner(_ADAPTER_REGISTRY)
_DRY_RUN_ENGINE = DryRunEngine(
    _ADAPTER_REGISTRY,
    gas_oracle=_GAS_ORACLE,
    slippage=_SLIPPAGE_ESTIMATOR,
    simulator_registry=_SIMULATION_REGISTRY,
    mev_registry=_MEV_REGISTRY,
    quoter=_QUOTER_REGISTRY,
)
_EXECUTION_PLANS_REPO = ExecutionPlansRepo(db)

# ---------------------------------------------------------------------------
# Wave-6D · Capital Policy + Kill Switch + Live Signer (gate ladder only).
# SHADOW-safe: Live Signer never emits signed bytes at this wave — the ladder
# is fully wired so end-to-end pipeline is testable.
# ---------------------------------------------------------------------------
_CAPITAL_POLICY_REPO = CapitalPolicyRepo(db)
_CAPITAL_ALLOCATOR = CapitalAllocator(_CAPITAL_POLICY_REPO, _EXECUTION_PLANS_REPO)
_KILL_SWITCH_REPO = KillSwitchRepo(db)
_LIVE_SIGNER = LiveSigner(
    kill_switch=_KILL_SWITCH_REPO,
    mode_repo=_EXECUTION_MODE_REPO,
    wallet_registry=_WALLET_REGISTRY,
    secret_registry=_SECRET_REGISTRY,
    capital_allocator=_CAPITAL_ALLOCATOR,
)

# ---------------------------------------------------------------------------
# Wave-6E · Execution Certifier — composes Wave 6A/6B/6C/6D into a single
# end-to-end pipeline audit.  READ-ONLY.  SHADOW-safe.
# ---------------------------------------------------------------------------
_EXECUTION_CERTIFIER = ExecutionCertifier(
    mode_repo=_EXECUTION_MODE_REPO,
    planner=_EXECUTION_PLANNER,
    dry_run_engine=_DRY_RUN_ENGINE,
    simulator_registry=_SIMULATION_REGISTRY,
    gas_oracle=_GAS_ORACLE,
    mev_registry=_MEV_REGISTRY,
    slippage_estimator=_SLIPPAGE_ESTIMATOR,
    capital_allocator=_CAPITAL_ALLOCATOR,
    kill_switch=_KILL_SWITCH_REPO,
    live_signer=_LIVE_SIGNER,
    wallet_registry=_WALLET_REGISTRY,
    secret_registry=_SECRET_REGISTRY,
    evidence_signer=_EVIDENCE_SIGNER,
)

# ---------------------------------------------------------------------------
# Wave-7A · Wallet balance reader + health card + Continuous Discovery.
# Wave-7C · LIMITED_LIVE broadcaster (bytes-level, 6-gate ladder).
# ---------------------------------------------------------------------------
_WALLET_BALANCE_READER = WalletBalanceReader()
_WALLET_HEALTH_CARD = WalletHealthCard(
    wallet_registry=_WALLET_REGISTRY,
    secret_registry=_SECRET_REGISTRY,
    balance_reader=_WALLET_BALANCE_READER,
    mode_repo=_EXECUTION_MODE_REPO,
    capital_allocator=_CAPITAL_ALLOCATOR,
    kill_switch=_KILL_SWITCH_REPO,
)
_DISCOVERY_REPO = DiscoveryRepo(db)
_CONTINUOUS_DISCOVERY = ContinuousDiscovery(
    repo=_DISCOVERY_REPO,
    planner=_EXECUTION_PLANNER,
    dry_run_engine=_DRY_RUN_ENGINE,
    slippage_estimator=_SLIPPAGE_ESTIMATOR,
    plans_repo=_EXECUTION_PLANS_REPO,
    interval_s=60.0,
)
_LIMITED_LIVE_BROADCASTER = LimitedLiveBroadcaster(
    kill_switch=_KILL_SWITCH_REPO,
    mode_repo=_EXECUTION_MODE_REPO,
    wallet_registry=_WALLET_REGISTRY,
    secret_registry=_SECRET_REGISTRY,
    capital_allocator=_CAPITAL_ALLOCATOR,
    evidence_signer=_EVIDENCE_SIGNER,
)

# ---------------------------------------------------------------------------
# Phase 8 · Canonical Opportunity Intelligence Activation.
# The MongoOpportunityRepository is the single source of truth for canonical
# opportunities.  Every preview stub below is now a *thin translator* that
# emits the frontend contract shape from canonical rows when they exist and
# falls back to the deterministic preview universe when they don't.
# ---------------------------------------------------------------------------
_CANONICAL_OPP_REPO = MongoOpportunityRepository(db)
# Phase 8 — inject canonical repo into continuous discovery so every tick
# writes a CanonicalOpportunity row to arbicore_opportunities.
_CONTINUOUS_DISCOVERY._canonical_repo = _CANONICAL_OPP_REPO

# ---------------------------------------------------------------------------
# P0-A · Opportunity Journal — append-only historical intelligence store.
# Reuses the same Motor `db`. Aggregated one-row-per-opportunity model with
# an events[] trail captures the full lifecycle without discarding rejects.
# Bootstrapped in the startup hook further below (`_seed_execution_substrate`).
# ---------------------------------------------------------------------------
_OPPORTUNITY_JOURNAL = OpportunityJournal(db)

# ---------------------------------------------------------------------------
# P0-B · Learning Ledger — bridges Opportunity Journal into the existing
# CalibrationWorker + AdaptiveWeightsWorker. Writes to `db.calibration_log`
# and `db.arbicore_signal_metrics` which the two workers already consume.
# No new workers, no new collections beyond those the workers already read.
# ---------------------------------------------------------------------------
_LEARNING_LEDGER = LearningLedger(db, _OPPORTUNITY_JOURNAL)

# ---------------------------------------------------------------------------
# P0-C · Unified Opportunity Pipeline — orchestrates
#   Discovery → Quote → Gas → Profit → Policy → Certification →
#   (SHADOW terminal) or (LIMITED_LIVE broadcast) → Journal → Learning.
# Reuses ExecutionModeRepo, KillSwitchRepo, CapitalAllocator, Certifier,
# LimitedLiveBroadcaster, ExecutionPlansRepo — no new subsystems, no
# duplicate policies. Broadcast is authorised ONLY when the strategy has
# been explicitly promoted to LIMITED_LIVE / FULL_LIVE by an operator.
# ---------------------------------------------------------------------------
_OPPORTUNITY_PIPELINE = OpportunityPipeline(
    journal=_OPPORTUNITY_JOURNAL,
    mode_repo=_EXECUTION_MODE_REPO,
    kill_switch=_KILL_SWITCH_REPO,
    capital_allocator=_CAPITAL_ALLOCATOR,
    certifier=_EXECUTION_CERTIFIER,
    broadcaster=_LIMITED_LIVE_BROADCASTER,
    plans_repo=_EXECUTION_PLANS_REPO,
)

# ---------------------------------------------------------------------------
# P0-D · Autonomous Executor — background worker that continuously drains
# the DiscoveryRepo through the OpportunityPipeline (P0-C), journals every
# stage, and periodically triggers the LearningLedger (P0-B) to convert
# terminals into calibration samples.
#
# By construction it CANNOT broadcast unless the strategy's mode has been
# explicitly promoted by the operator via
# POST /api/arbicore/execution/mode/{strategy}. Default deployment starts
# in SHADOW/PAPER — every stage is journaled but no chain writes occur.
# ---------------------------------------------------------------------------
_AUTO_EXECUTOR = AutoExecutor(
    pipeline=_OPPORTUNITY_PIPELINE,
    discovery_repo=_DISCOVERY_REPO,
    journal=_OPPORTUNITY_JOURNAL,
    learning_ledger=_LEARNING_LEDGER,
    interval_s=float(os.environ.get("ARBICORE_AUTOEXEC_INTERVAL_S", "30")),
    batch_size=int(os.environ.get("ARBICORE_AUTOEXEC_BATCH", "25")),
    min_confidence=float(os.environ.get("ARBICORE_AUTOEXEC_MIN_CONF", "0.0")),
    learning_every_n_ticks=int(os.environ.get("ARBICORE_AUTOEXEC_LEARN_EVERY", "4")),
)

# ---------------------------------------------------------------------------
# Phase 10.1 · Persistent operator configuration substrate.
# Phase 10.2 · Stub-migration repos.
# Phase 10.3 · Telegram alerts.
# ---------------------------------------------------------------------------
_CONFIG_REPO         = ConfigRepo(db)
_NETWORK_CONFIG      = NetworkConfigRepo(_CONFIG_REPO)
_ACCOUNT_REPO        = OperatorAccountRepo(_CONFIG_REPO)
_EXECUTION_SETTINGS  = ExecutionSettingsRepo(_CONFIG_REPO)
_OPERATIONAL_FLAGS   = OperationalFlagsRepo(_CONFIG_REPO)
_TELEGRAM            = TelegramAlertService(
    db, config_repo=_CONFIG_REPO, secret_registry=_SECRET_REGISTRY,
)
_SCANNER_CONFIG      = ScannerConfigRepo(
    _CONFIG_REPO, network_repo=_NETWORK_CONFIG,
)

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


# ---------------------------------------------------------------------------
# UI v2 · Slice 0 preview endpoints (pod-local stubs that mirror the canonical
# shapes in app/backend/arbicore/routes/dashboard.py). Real implementation
# lives in the canonical repo; these stubs exist only so the Emergent preview
# renders the /v2 Home cards with realistic sample data.
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@api_router.get("/arbicore/dashboard/pulse")
async def v2_pulse() -> Dict[str, Any]:
    return {
        "regime": {
            "regime": "CALM",
            "tags": ["low_volatility"],
            "confidence": 0.82,
            "source": "preview-stub",
            "observed_at": _iso_now(),
        },
        "opportunity_vitals": {
            "total": 14,
            "by_family": {"CEX_ARBITRAGE": 6, "DEX_ARBITRAGE": 4, "FUNDING_ARBITRAGE": 3, "LAUNCH_ARBITRAGE": 1},
            "by_status": {"CANDIDATE": 12, "APPROVED": 2},
        },
        "route_learning": {"tracked_routes": 47},
        "scanner_status": {"endpoint": "/api/arbicore/scanners", "detail": "per-family scanner status"},
        "venue_readiness": {"endpoint": "/api/venues/status", "detail": "venue readiness registry"},
        "feed_freshness": {"endpoint": "/api/execution/portal/diagnostic", "detail": "portal feed freshness"},
        "interlock": {"endpoint": "/api/execution/interlock", "detail": "safety interlock status"},
        "deployable_capital": {"endpoint": "/api/portfolio/deployable", "detail": "deployable capital"},
        "anomalies": [],
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/dashboard/deck")
async def v2_deck(limit: int = 5) -> Dict[str, Any]:
    fresh = [
        {"id": "opp-001", "opportunity_type": "CEX_ARBITRAGE", "subject_id": "ETH-USDT",
         "chain": "ethereum", "confidence": 0.87, "status": "CANDIDATE", "created_at": _iso_now()},
        {"id": "opp-002", "opportunity_type": "DEX_ARBITRAGE", "subject_id": "WETH/USDC",
         "chain": "arbitrum", "confidence": 0.79, "status": "CANDIDATE", "created_at": _iso_now()},
        {"id": "opp-003", "opportunity_type": "FUNDING_ARBITRAGE", "subject_id": "SOL-PERP",
         "chain": "solana", "confidence": 0.71, "status": "CANDIDATE", "created_at": _iso_now()},
        {"id": "opp-004", "opportunity_type": "CEX_ARBITRAGE", "subject_id": "BTC-USDT",
         "chain": "bitcoin", "confidence": 0.65, "status": "CANDIDATE", "created_at": _iso_now()},
        {"id": "opp-005", "opportunity_type": "LAUNCH_ARBITRAGE", "subject_id": "NEW-TOKEN",
         "chain": "solana", "confidence": 0.58, "status": "CANDIDATE", "created_at": _iso_now()},
    ][:max(1, min(limit, 20))]
    return {
        "pending_approvals": [],
        "pending_approvals_total": 0,
        "fresh_opportunities": fresh,
        "fresh_opportunities_total": len(fresh),
        "requires_attention": [],
        "requires_attention_total": 0,
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/opportunities/summary")
async def v2_opportunities_summary(window_hours: int = 24, max_scan: int = 1000) -> Dict[str, Any]:
    """Slice 1 · Canonical activation.

    Aggregate the ``arbicore_opportunities`` collection grouped by
    opportunity_type / chain / status.  Returns empty counts when the
    canonical store is empty — never falls back to placeholder totals.
    """
    by_family: Dict[str, int] = {}
    by_chain: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    total = 0
    try:
        rows = await _CANONICAL_OPP_REPO.find({}, limit=int(max_scan))
        for opp in rows:
            total += 1
            fam = (opp.opportunity_type.value
                    if hasattr(opp.opportunity_type, "value")
                    else str(opp.opportunity_type))
            ch = opp.chain or "-"
            st = (opp.status.value if hasattr(opp.status, "value")
                    else str(opp.status))
            by_family[fam] = by_family.get(fam, 0) + 1
            by_chain[ch] = by_chain.get(ch, 0) + 1
            by_status[st] = by_status.get(st, 0) + 1
    except Exception:
        logger.exception("opportunities_summary: canonical aggregate failed")
    return {
        "total": total,
        "by_family": by_family,
        "by_chain": by_chain,
        "by_status": by_status,
        "source": "canonical",
        "window_hours": int(window_hours),
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/roi-probability")
async def v2_roi_probability(route_id: str) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "sample_size": 42,
        "win_rate": 0.643,
        "realized_outcome_mean": 0.012,
        "realized_outcome_sum": 0.517,
        "last_outcome_at": _iso_now(),
        "generated_at": _iso_now(),
    }


@api_router.get("/system/status")
async def v2_system_status() -> Dict[str, Any]:
    return {
        "features": {"ui_v2": True},
        "preview": True,
        "generated_at": _iso_now(),
    }


# ---------------------------------------------------------------------------
# UI v2 · Slice 1 preview endpoints — universal opportunity feed + detail.
# Pod-local stubs; canonical implementation lives in arbicore/routes/*.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Slice 1 · Canonical Opportunity endpoints (real Mongo, real journal).
# The v2.10 hotfix removed the ``_V2_OPPS`` preview universe and every
# canonical-first / preview-fallback merge branch.  The handlers below now
# read exclusively from ``_CANONICAL_OPP_REPO`` and mutate exclusively via
# ``_OPPORTUNITY_JOURNAL``.  Empty repository → empty response, never a
# hardcoded placeholder.
# ---------------------------------------------------------------------------


@api_router.get("/arbicore/opportunities")
async def v2_opportunities_list(
    family: Optional[str] = None,
    chain: Optional[str] = None,
    verdict: Optional[str] = None,
    min_confidence: float = 0.0,
    sort_by: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Slice 1 · Canonical activation.

    Reads the canonical ``arbicore_opportunities`` collection and translates
    each row into the frontend v2 contract.  Never falls back to preview.
    """
    try:
        canonical_rows = await _CANONICAL_OPP_REPO.find({}, limit=int(limit) * 2)
        items = [_canonical_opp_to_contract(opp) for opp in canonical_rows]
    except Exception:
        logger.exception("opportunities_list: canonical read failed")
        items = []

    out: List[Dict[str, Any]] = []
    for o in items:
        if family and family != "ALL" and o["opportunity_type"] != family:
            continue
        if chain and chain != "ALL" and o["chain"] != chain:
            continue
        if verdict and verdict != "ALL" and o["verdict"] != verdict:
            continue
        if o["confidence"] < min_confidence:
            continue
        out.append(o)

    if sort_by == "confidence":
        out.sort(key=lambda x: x.get("confidence") or 0, reverse=True)
    elif sort_by == "spread":
        out.sort(key=lambda x: x.get("spread_bps") or 0, reverse=True)
    elif sort_by == "depth":
        out.sort(key=lambda x: x.get("depth_usd") or 0, reverse=True)
    else:
        out.sort(key=lambda x: x.get("age_s") or 0)

    return {
        "items": out[:limit],
        "total": len(out),
        "source": "canonical",
        "generated_at": _iso_now(),
    }


def _canonical_opp_to_contract(opp: "CanonicalOpportunity") -> Dict[str, Any]:
    """Translate a CanonicalOpportunity into the frontend v2 contract."""
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)
    try:
        created = _dt.fromisoformat(opp.created_at.replace("Z", "+00:00"))
        age_s = max(0, int((now - created).total_seconds()))
    except Exception:
        age_s = 0
    conf = float(opp.confidence_score or 0)
    if conf > 1.0:  # tolerate 0-100 scale
        conf = conf / 100.0
    verdict = "GO" if opp.status in (OpportunityStatus.APPROVED,
                                       OpportunityStatus.VALIDATED) \
        else ("HARD_NO" if opp.status == OpportunityStatus.REJECTED else "SOFT_NO")
    return {
        "id": opp.opportunity_id,
        "subject_id": opp.subject_id or opp.asset,
        "opportunity_type": (opp.opportunity_type.value
                              if hasattr(opp.opportunity_type, "value")
                              else str(opp.opportunity_type)),
        "chain": opp.chain or "-",
        "verdict": verdict,
        "confidence": round(conf, 4),
        "safety": round(1.0 - min(1.0, float(opp.risk_score or 0) / 100.0), 4),
        "spread_bps": int(round((opp.spread_pct or 0) * 100)),
        "depth_usd": int(round(opp.capital_required_usd or 0)),
        "return_low": round((opp.expected_profit_usd or 0) * 0.9, 2),
        "return_high": round((opp.expected_profit_usd or 0) * 1.1, 2),
        "age_s": age_s,
        "route": opp.route,
        "status": (opp.status.value if hasattr(opp.status, "value") else str(opp.status)),
        "source_data_quality": (opp.source_data_quality.value
                                 if hasattr(opp.source_data_quality, "value")
                                 else str(opp.source_data_quality)),
        "canonical": True,
    }


@api_router.get("/arbicore/opportunities/{opp_id}")
async def v2_opportunity_detail(opp_id: str) -> Dict[str, Any]:
    # Phase 8: canonical-first.
    try:
        canonical = await _CANONICAL_OPP_REPO.get(opp_id)
    except Exception:
        canonical = None
    if canonical is not None:
        base = _canonical_opp_to_contract(canonical)
        base["reasoning"] = {
            "confidence_breakdown": [
                {"factor": "Route confidence", "delta": int(base["confidence"] * 10),
                 "notes": f"Canonical score {base['confidence']:.2%}"},
            ],
            "gates_passed": ["provenance", "lifecycle"],
            "gates_dropped": [],
        }
        base["verification"] = {
            "quote_source": "canonical_opp_repo",
            "last_verified_at": canonical.updated_at,
            "fresh_window_s": 60,
            "stale": base["age_s"] > 60,
        }
        base["evidence"] = {"cycle_id": None,
                              "download_endpoint": f"/api/arbicore/opportunities/{opp_id}/evidence",
                              "attachments": []}
        return base
    # Slice 1: canonical-only. When the opportunity is not in the canonical
    # store, respond with a 404 rather than a placeholder payload.
    raise HTTPException(status_code=404, detail={"error": "not_found", "id": opp_id})


@api_router.post("/arbicore/opportunities/{opp_id}/approve")
async def v2_opportunity_approve(opp_id: str) -> Dict[str, Any]:
    # Phase 8: route through canonical FSM.
    try:
        canonical = await _CANONICAL_OPP_REPO.get(opp_id)
        if canonical is not None:
            # CANDIDATE → VALIDATED → APPROVED (single call may need chaining).
            if canonical.status == OpportunityStatus.CANDIDATE:
                canonical.mark_validated()
            if canonical.status == OpportunityStatus.VALIDATED:
                canonical.mark_approved()
            await _CANONICAL_OPP_REPO.upsert(canonical)
            # Slice 1: record decision on the journal (audit trail).
            try:
                await _OPPORTUNITY_JOURNAL.record_event(
                    opp_id, kind="operator_approved",
                    detail={"new_status": canonical.status.value},
                    status=canonical.status.value,
                )
            except Exception:
                logger.exception("approve: journal.record_event failed for %s", opp_id)
            return {"ok": True, "id": opp_id, "status": canonical.status.value,
                    "canonical": True, "generated_at": _iso_now()}
    except InvalidTransitionError as exc:
        return {"ok": False, "id": opp_id, "error": str(exc),
                "generated_at": _iso_now()}
    except Exception:
        pass
    # Slice 1 · canonical-only. No preview fallback.
    raise HTTPException(status_code=404, detail={"error": "not_found", "id": opp_id})


@api_router.post("/arbicore/opportunities/{opp_id}/reject")
async def v2_opportunity_reject(opp_id: str,
                                  body: Optional[Dict[str, Any]] = None
                                  ) -> Dict[str, Any]:
    reason = (body or {}).get("reason") or "operator_rejected"
    try:
        canonical = await _CANONICAL_OPP_REPO.get(opp_id)
        if canonical is not None:
            canonical.mark_rejected(reason)
            await _CANONICAL_OPP_REPO.upsert(canonical)
            # Slice 1: record decision on the journal.
            try:
                await _OPPORTUNITY_JOURNAL.record_event(
                    opp_id, kind="operator_rejected",
                    detail={"new_status": canonical.status.value, "reason": reason},
                    status=canonical.status.value,
                )
            except Exception:
                logger.exception("reject: journal.record_event failed for %s", opp_id)
            return {"ok": True, "id": opp_id, "status": canonical.status.value,
                    "canonical": True, "reason": reason,
                    "generated_at": _iso_now()}
    except InvalidTransitionError as exc:
        return {"ok": False, "id": opp_id, "error": str(exc),
                "generated_at": _iso_now()}
    except Exception:
        pass
    # Slice 1 · canonical-only. No preview fallback.
    raise HTTPException(status_code=404, detail={"error": "not_found", "id": opp_id})


# ---------------------------------------------------------------------------
# Phase 8 · Per-opportunity Execution Timeline (join view — no new persistence)
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/opportunities/{opp_id}/timeline")
async def v2_opportunity_timeline(opp_id: str) -> Dict[str, Any]:
    """Join view across every existing audit collection.  Read-only.

    Phase 8 institutional trail — orders events chronologically (descending)
    across:
      * ``arbicore_opportunities`` (canonical lifecycle / FSM)
      * ``opportunities`` (Wave-7A discovery cadence)
      * ``execution_plans`` (planner output)
      * ``evidence_bundles`` (Wave-5 signed evidence)
      * ``execution_mode_audit`` (mode ladder)
      * ``capital_policy_audit`` (capital allocation)
      * ``kill_switch_audit`` (safety interlock)
      * ``calibration_models`` (learning: confidence calibration)
      * ``adaptive_weight_recommendations`` (learning: adaptive weights)
      * ``wallet_registry_audit`` (operator wallet changes)

    Global (non-opportunity-scoped) audits are capped at ``global_cap`` rows
    each so a single per-opportunity view is not overwhelmed by ambient
    system activity.  The scoped collections are unbounded (small tables).
    """
    events: List[Dict[str, Any]] = []
    GLOBAL_CAP = 8

    async def _tap(collection_name: str, query: Dict[str, Any],
                    ts_field: str, kind: str, limit: int = 50):
        try:
            coll = db[collection_name]
            cur = coll.find(query, {"_id": 0}).sort(ts_field, -1).limit(limit)
            async for row in cur:
                events.append({
                    "kind": kind,
                    "at": row.get(ts_field) or row.get("created_at") or row.get("updated_at"),
                    "collection": collection_name,
                    "payload": row,
                })
        except Exception:
            pass

    # 1. Canonical opportunity trail (FSM lifecycle)
    canonical = None
    try:
        canonical = await _CANONICAL_OPP_REPO.get(opp_id)
    except Exception:
        pass
    if canonical:
        events.append({
            "kind": "opportunity_state",
            "at": canonical.updated_at,
            "collection": "arbicore_opportunities",
            "payload": {"status": canonical.status.value,
                         "opportunity_type": canonical.opportunity_type.value,
                         "asset": canonical.asset,
                         "chain": canonical.chain,
                         "confidence_score": canonical.confidence_score,
                         "risk_score": canonical.risk_score,
                         "source_data_quality": canonical.source_data_quality.value,
                         "created_at": canonical.created_at,
                         "updated_at": canonical.updated_at},
        })
    # 2. Wave 7A opportunity + discovery cadence (per-opp scoped)
    await _tap("opportunities", {"opportunity_id": opp_id},
                "updated_at", "discovery")
    # Slice 1: opportunity_journal per-opp trail (operator decisions).
    try:
        journal_entry = await _OPPORTUNITY_JOURNAL.get(opp_id)
    except Exception:
        journal_entry = None
    if journal_entry is not None:
        for ev in getattr(journal_entry, "events", []) or []:
            events.append({
                "kind": f"journal:{ev.kind}",
                "at": getattr(ev, "at", None),
                "collection": "opportunity_journal",
                "payload": {"kind": ev.kind, "detail": ev.detail},
            })
    # 3. Execution plans built for this opportunity (per-opp scoped)
    await _tap("execution_plans", {"opportunity_id": opp_id},
                "created_at", "execution_plan")
    # 4. Evidence bundles for this opportunity (per-opp scoped)
    await _tap("evidence_bundles", {"opportunity_id": opp_id},
                "signed_at", "evidence")
    # 5. Global — mode ladder audit (ambient state at decision time)
    await _tap("execution_mode_audit", {}, "at", "mode_transition", limit=GLOBAL_CAP)
    # 6. Global — capital policy audit
    await _tap("capital_policy_audit", {}, "at", "capital_policy", limit=GLOBAL_CAP)
    # 7. Global — kill-switch audit
    await _tap("kill_switch_audit", {}, "at", "kill_switch", limit=GLOBAL_CAP)
    # 8. Global — wallet registry audit
    await _tap("wallet_registry_audit", {}, "at", "wallet_registry", limit=GLOBAL_CAP)
    # 9. Global — calibration models (learning update history)
    await _tap("calibration_models", {},
                "fitted_at", "calibration", limit=GLOBAL_CAP)
    # 10. Global — adaptive weight recommendations (learning: weights)
    await _tap("adaptive_weight_recommendations", {},
                "recommended_at", "adaptive_weights", limit=GLOBAL_CAP)
    # Sort chronologically (descending) — tolerate mixed timestamp formats.
    events.sort(key=lambda e: str(e.get("at") or ""), reverse=True)
    return {"opportunity_id": opp_id, "count": len(events),
            "events": events[:200], "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# UI v2 · Slice 2 preview endpoints — Discovery + Intelligence.
# Pod-local stubs; canonical implementations added in
# app/backend/arbicore/routes/dashboard.py alongside Slice 1.
# ---------------------------------------------------------------------------

_V2_DISCOVERY = [
    {"id": "cand-001", "asset": "PENDLE", "kind": "asset", "chain": "ethereum",
     "source": "twitter:@messaricrypto", "score": 0.82, "status": "NEW",
     "why": "Repeated mention across 4 curated sources in last 48h.",
     "signals": ["mention_burst", "unusual_volume", "narrative:LRT"], "seen_at": None},
    {"id": "cand-002", "asset": "TIA", "kind": "asset", "chain": "celestia",
     "source": "coingecko:trending", "score": 0.71, "status": "NEW",
     "why": "Trending +38% pageviews, whale accumulation on Osmosis.",
     "signals": ["trending", "whale_accumulation"], "seen_at": None},
    {"id": "cand-003", "asset": "kucoin:MOODENG-USDT", "kind": "venue_pair", "chain": "kucoin",
     "source": "listings:new", "score": 0.64, "status": "WATCHING",
     "why": "New CEX listing pair, high early spread.",
     "signals": ["new_listing", "spread_open"], "seen_at": None},
    {"id": "cand-004", "asset": "berachain", "kind": "chain", "chain": "berachain",
     "source": "github:activity", "score": 0.58, "status": "NEW",
     "why": "Mainnet imminent; RPC endpoints reachable.",
     "signals": ["mainnet_soon", "rpc_up"], "seen_at": None},
    {"id": "cand-005", "asset": "ORDI", "kind": "asset", "chain": "bitcoin",
     "source": "twitter:@onchainedge", "score": 0.44, "status": "DISMISSED",
     "why": "Dismissed 6d ago — low liquidity across venues.",
     "signals": ["low_liquidity"], "seen_at": None},
    {"id": "cand-006", "asset": "sushiswap:WETH-USDT (base)", "kind": "venue_pair", "chain": "base",
     "source": "onchain:pool_scan", "score": 0.69, "status": "NEW",
     "why": "New Sushi pool with $3.2M TVL on Base.",
     "signals": ["new_pool", "tvl_ok"], "seen_at": None},
    {"id": "cand-007", "asset": "hyperliquid:BTC-PERP", "kind": "venue_pair", "chain": "hyperliquid",
     "source": "funding:screener", "score": 0.77, "status": "PROMOTED",
     "why": "Extreme funding rate divergence vs Binance funding.",
     "signals": ["funding_divergence"], "seen_at": None},
]


def _hydrate_discovery():
    now = _iso_now()
    for c in _V2_DISCOVERY:
        if c["seen_at"] is None:
            c["seen_at"] = now
    return _V2_DISCOVERY


@api_router.get("/arbicore/discovery/candidates")
async def v2_discovery_candidates(status: Optional[str] = None, kind: Optional[str] = None,
                                   min_score: float = 0.0, limit: int = 100) -> Dict[str, Any]:
    items = _hydrate_discovery()
    out = []
    for c in items:
        if status and status != "ALL" and c["status"] != status:
            continue
        if kind and kind != "ALL" and c["kind"] != kind:
            continue
        if c["score"] < min_score:
            continue
        out.append(c)
    stats = {
        "total": len(items),
        "new": sum(1 for c in items if c["status"] == "NEW"),
        "watching": sum(1 for c in items if c["status"] == "WATCHING"),
        "promoted": sum(1 for c in items if c["status"] == "PROMOTED"),
        "dismissed": sum(1 for c in items if c["status"] == "DISMISSED"),
    }
    # Wave-1 refinement: expose DiscoveryScorer calibration so operators can see
    # whether the signal weights track realised promotions. Additive block; UI
    # ignores unknown fields. Future prod source: DiscoveryScorer.calibration().
    promoted = max(1, stats["promoted"] + stats["dismissed"])
    calibration = {
        "model": "discovery-scorer@2026.07.0",
        "n_samples": 214,
        "promotion_rate_top_decile": 0.62,   # fraction of top-score candidates that end PROMOTED
        "promotion_rate_bottom_decile": 0.04,
        "ece": 0.037,
        "drift_alert": False,
    }
    return {"items": out[:limit], "total": len(out), "stats": stats,
            "calibration": calibration, "generated_at": _iso_now()}


@api_router.post("/arbicore/discovery/candidates/{cand_id}/action")
async def v2_discovery_action(cand_id: str, action: str) -> Dict[str, Any]:
    items = _hydrate_discovery()
    match = next((c for c in items if c["id"] == cand_id), None)
    if match:
        mapping = {"watch": "WATCHING", "promote": "PROMOTED", "dismiss": "DISMISSED", "reset": "NEW"}
        match["status"] = mapping.get(action.lower(), match["status"])
    return {"ok": True, "id": cand_id, "status": match["status"] if match else None, "generated_at": _iso_now()}


@api_router.get("/arbicore/intelligence/recommendations")
async def v2_recommendations() -> Dict[str, Any]:
    return {
        "top_routes": [
            {"route": "binance:ETH-USDT → kucoin:ETH-USDT", "win_rate": 0.68, "trials": 128, "mean_roi": 0.0031},
            {"route": "uniswap-v3:WETH/USDC → sushiswap:WETH/USDC", "win_rate": 0.61, "trials": 89, "mean_roi": 0.0022},
            {"route": "binance:BTC-USDT → okx:BTC-USDT", "win_rate": 0.72, "trials": 214, "mean_roi": 0.0018},
            {"route": "bybit:SOL-PERP short + spot long", "win_rate": 0.54, "trials": 46, "mean_roi": 0.0014},
            {"route": "aave-flash → quickswap → sushiswap (MATIC)", "win_rate": 0.49, "trials": 22, "mean_roi": 0.0026},
        ],
        "top_chains": [
            {"chain": "ethereum", "opps_24h": 41, "avg_confidence": 0.73, "avg_safety": 0.86},
            {"chain": "arbitrum", "opps_24h": 32, "avg_confidence": 0.68, "avg_safety": 0.82},
            {"chain": "solana", "opps_24h": 27, "avg_confidence": 0.61, "avg_safety": 0.71},
            {"chain": "base", "opps_24h": 18, "avg_confidence": 0.65, "avg_safety": 0.79},
        ],
        "top_entities": [
            {"entity": "binance", "kind": "venue", "score": 0.91},
            {"entity": "uniswap-v3", "kind": "venue", "score": 0.87},
            {"entity": "ETH-USDT", "kind": "market", "score": 0.83},
            {"entity": "WETH/USDC", "kind": "market", "score": 0.78},
        ],
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/intelligence/decisions")
async def v2_decisions(verdict: Optional[str] = None, family: Optional[str] = None,
                        min_confidence: float = 0.0, limit: int = 100) -> Dict[str, Any]:
    # Wave-1 refinement: every decision now carries model_version + policy_version
    # so operators + auditors can trace which classifier + policy produced the
    # verdict. Additive to the Slice-2 shape (existing UI ignores unknown fields).
    log = [
        {"id": "dec-001", "opp_id": "opp-001", "asset": "ETH-USDT", "family": "CEX_ARBITRAGE",
         "verdict": "GO", "confidence": 0.87, "regime": "CALM",
         "top_factors": ["+6 route history", "+4 regime CALM", "+3 depth"],
         "model_version": "conf-scorer@2026.07.2", "policy_version": "exec-policy@v1.4.0",
         "at": _iso_now()},
        {"id": "dec-002", "opp_id": "opp-002", "asset": "WETH/USDC", "family": "DEX_ARBITRAGE",
         "verdict": "GO", "confidence": 0.79, "regime": "CALM",
         "top_factors": ["+5 route history", "+3 regime CALM", "-1 gas volatility"],
         "model_version": "conf-scorer@2026.07.2", "policy_version": "exec-policy@v1.4.0",
         "at": _iso_now()},
        {"id": "dec-003", "opp_id": "opp-003", "asset": "SOL-PERP", "family": "FUNDING_ARBITRAGE",
         "verdict": "SOFT_NO", "confidence": 0.71, "regime": "CALM",
         "top_factors": ["-3 safety (venue drift)", "+2 spread", "-1 funding vol"],
         "model_version": "conf-scorer@2026.07.2", "policy_version": "exec-policy@v1.4.0",
         "at": _iso_now()},
        {"id": "dec-004", "opp_id": "opp-008", "asset": "WETH/USDT (base)", "family": "DEX_ARBITRAGE",
         "verdict": "HARD_NO", "confidence": 0.42, "regime": "CALM",
         "top_factors": ["-6 safety_min gate", "-3 depth_min gate"],
         "model_version": "conf-scorer@2026.07.2", "policy_version": "exec-policy@v1.4.0",
         "at": _iso_now()},
        {"id": "dec-005", "opp_id": "opp-004", "asset": "BTC-USDT", "family": "CEX_ARBITRAGE",
         "verdict": "GO", "confidence": 0.65, "regime": "CALM",
         "top_factors": ["+4 route history", "+2 depth", "-2 fresh window"],
         "model_version": "conf-scorer@2026.07.2", "policy_version": "exec-policy@v1.4.0",
         "at": _iso_now()},
        {"id": "dec-006", "opp_id": "opp-007", "asset": "MATIC/USDC", "family": "FLASH_LOAN_ARBITRAGE",
         "verdict": "GO", "confidence": 0.61, "regime": "CALM",
         "top_factors": ["+3 flash-fee coverage", "+2 route history"],
         "model_version": "conf-scorer@2026.07.2-shadow", "policy_version": "exec-policy@v1.4.0",
         "at": _iso_now()},
    ]
    out = []
    for d in log:
        if verdict and verdict != "ALL" and d["verdict"] != verdict:
            continue
        if family and family != "ALL" and d["family"] != family:
            continue
        if d["confidence"] < min_confidence:
            continue
        # Wave-3 refinement — every decision carries the calibrator version
        # so audits can trace which calibration curve produced the confidence.
        d.setdefault("calibrator_version", _CALIBRATION_CFG.calibrator_version)
        out.append(d)
    return {"items": out[:limit], "total": len(out), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-1 activations — dormant learning-loop engines exposed as preview stubs.
# UI contract additions only; no existing endpoint shape is broken.
#
# Future-endpoint mapping (production):
#   GET /api/arbicore/intelligence/calibration   <- CalibrationRepo.snapshot()
#   GET /api/arbicore/intelligence/models        <- ModelRegistry.list_active()
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/intelligence/calibration")
async def v2_calibration(model: Optional[str] = None, window_days: Optional[int] = None) -> Dict[str, Any]:
    # Wave-3: prefer the currently-active row from db.calibration_models.
    # Fallback path — no active row yet (bootstrap) — returns an identity
    # baseline with a stable 10-bucket demo shape so the UI keeps rendering.
    # Both paths emit the frozen Wave-1 contract keys.
    active = None
    try:
        active = await _CALIBRATION_REPO.get_active("confidence")
    except Exception:
        active = None
    if active is not None:
        return {
            "model": active.get("id"),
            "window_days": active.get("window_days") or _CALIBRATION_CFG.window_days,
            "n_samples": active.get("n_samples", 0),
            "brier_score": active.get("brier_score", 0.0),
            "ece": active.get("ece", 0.0),
            "drift_alert": bool(active.get("drift_alert", False)),
            "buckets": active.get("buckets", []),
            "algorithm": active.get("algorithm"),
            "calibrator_version": active.get("calibrator_version"),
            "supersedes": active.get("supersedes"),
            "generated_at": _iso_now(),
        }
    # Bootstrap fallback (identity mapping) — Wave-1 stub shape retained.
    win = window_days if window_days is not None else _CALIBRATION_CFG.window_days
    buckets = [
        {"bucket": "0.0-0.1", "predicted": 0.05, "realised": 0.06, "n": 12},
        {"bucket": "0.1-0.2", "predicted": 0.15, "realised": 0.11, "n": 24},
        {"bucket": "0.2-0.3", "predicted": 0.25, "realised": 0.22, "n": 38},
        {"bucket": "0.3-0.4", "predicted": 0.35, "realised": 0.31, "n": 51},
        {"bucket": "0.4-0.5", "predicted": 0.45, "realised": 0.43, "n": 72},
        {"bucket": "0.5-0.6", "predicted": 0.55, "realised": 0.52, "n": 96},
        {"bucket": "0.6-0.7", "predicted": 0.65, "realised": 0.66, "n": 148},
        {"bucket": "0.7-0.8", "predicted": 0.75, "realised": 0.73, "n": 214},
        {"bucket": "0.8-0.9", "predicted": 0.85, "realised": 0.81, "n": 189},
        {"bucket": "0.9-1.0", "predicted": 0.95, "realised": 0.92, "n": 87},
    ]
    n_total = sum(b["n"] for b in buckets)
    brier = sum(((b["predicted"] - b["realised"]) ** 2) * b["n"] for b in buckets) / n_total
    ece = sum(abs(b["predicted"] - b["realised"]) * b["n"] for b in buckets) / n_total
    return {
        "model": model or "conf-scorer@2026.07.2",
        "window_days": win,
        "n_samples": n_total,
        "brier_score": round(brier, 4),
        "ece": round(ece, 4),
        "drift_alert": ece > 0.05,
        "buckets": buckets,
        "algorithm": "identity",
        "calibrator_version": _CALIBRATION_CFG.calibrator_version,
        "supersedes": None,
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/intelligence/models")
async def v2_models() -> Dict[str, Any]:
    active = [
        {"id": "conf-scorer@2026.07.2", "kind": "confidence", "state": "ACTIVE",
         "promoted_at": "2026-07-14T09:00:00+00:00", "shadow": False,
         "trained_on_samples": 42_180, "eval_brier": 0.078, "eval_ece": 0.021},
        {"id": "safety-scorer@2026.06.1", "kind": "safety", "state": "ACTIVE",
         "promoted_at": "2026-06-02T09:00:00+00:00", "shadow": False,
         "trained_on_samples": 28_400, "eval_brier": 0.093, "eval_ece": 0.028},
        {"id": "regime-detector@2026.07.0", "kind": "regime", "state": "ACTIVE",
         "promoted_at": "2026-07-01T09:00:00+00:00", "shadow": False,
         "trained_on_samples": 60_120, "eval_brier": 0.051, "eval_ece": 0.017},
        {"id": "conf-scorer@2026.07.2-shadow", "kind": "confidence", "state": "SHADOW",
         "promoted_at": None, "shadow": True,
         "trained_on_samples": 45_012, "eval_brier": 0.071, "eval_ece": 0.019},
    ]
    promotions = [
        {"at": "2026-07-14T09:00:00+00:00", "from": "conf-scorer@2026.06.1",
         "to": "conf-scorer@2026.07.2", "reason": "Brier +12% on holdout"},
        {"at": "2026-07-01T09:00:00+00:00", "from": "regime-detector@2026.06.1",
         "to": "regime-detector@2026.07.0", "reason": "Regime accuracy +4pp"},
        {"at": "2026-06-02T09:00:00+00:00", "from": "safety-scorer@2026.05.0",
         "to": "safety-scorer@2026.06.1", "reason": "False-safe rate halved"},
    ]
    return {"items": active, "promotions": promotions, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-2 exposures — read-only surfacing of engines that were previously
# hidden but are VERIFIED active in canonical v1.0.2. Shapes below mirror
# the real canonical implementations so lift is a straight port.
#
# Future-endpoint mapping (production):
#   GET /api/arbicore/intelligence/certification
#       <- services/execution/certification_review.latest_review()
#   GET /api/arbicore/intelligence/entities
#       <- composed over /entities + /entities/scores/top
#          (arbicore/routes/arbicore.py list_entities + top_entity_scores)
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/intelligence/certification")
async def v2_certification() -> Dict[str, Any]:
    # Shape mirrors services/execution/certification_review.latest_review()
    # exactly so the future lift is only a handler swap.
    return {
        "phase": "E4.5 — Shadow Certification Review",
        "available": True,
        "generated_at": _iso_now(),
        "recommendation": "NEEDS_MORE_DATA",
        "headline": "12 completed shadow cycles · 8 more needed for micro-capital review.",
        "campaign": {
            "id": "cmp-2026-07-31-a",
            "status": "COMPLETED",
            "target_completed": 20,
            "start_at": "2026-07-24T09:00:00+00:00",
            "ended_at": "2026-07-31T04:12:00+00:00",
            "breach_reason": None,
            "breach_thresholds": {"max_stuck_pct": 40.0, "max_variance_pct": 35.0, "min_recovery_pct": 70.0},
            "final_verdict_report": "NEEDS_MORE_DATA",
        },
        "summary": {
            "total_cycles": 12, "completed": 11, "aborted": 1,
            "completion_rate_pct": 91.67,
            "ever_stuck": 2, "stuck_rate_pct": 16.67,
            "recovery_success_rate_pct": 100.0,
            "recovery_failures": 0,
            "expected_total_quote": 4823.4,
            "realized_total_quote": 4712.9,
            "variance_pct": 2.29,
            "profitable_rate_pct": 90.9,
            "avg_realized_per_cycle": 428.4,
            "recommended_safe_cycle_usd": 350.0,
            "criteria_passed": 5, "criteria_failed": 2, "criteria_na": 0,
        },
        "readiness_criteria": {
            "min_completed_cycles": 20,
            "require_positive_avg_realized": True,
            "min_completion_rate_pct": 90.0,
            "min_recovery_success_rate_pct": 95.0,
            "max_stuck_rate_pct": 10.0,
            "max_variance_pct": 15.0,
            "min_profitable_rate_pct": 80.0,
        },
        "sections": [
            {"title": "Sample size", "verdict": "FAIL",
             "evidence": [{"metric": "completed_cycles", "value": 11, "threshold": 20, "status": "FAIL"}]},
            {"title": "Profitability", "verdict": "PASS",
             "evidence": [{"metric": "profitable_rate_pct", "value": 90.9, "threshold": 80.0, "status": "PASS"},
                          {"metric": "avg_realized_per_cycle", "value": 428.4, "threshold": 0.0, "status": "PASS"}]},
            {"title": "Completion", "verdict": "PASS",
             "evidence": [{"metric": "completion_rate_pct", "value": 91.67, "threshold": 90.0, "status": "PASS"}]},
            {"title": "Stuck rate", "verdict": "FAIL",
             "evidence": [{"metric": "stuck_rate_pct", "value": 16.67, "threshold": 10.0, "status": "FAIL"}]},
            {"title": "Recovery", "verdict": "PASS",
             "evidence": [{"metric": "recovery_success_rate_pct", "value": 100.0, "threshold": 95.0, "status": "PASS"}]},
            {"title": "Variance", "verdict": "PASS",
             "evidence": [{"metric": "variance_pct", "value": 2.29, "threshold": 15.0, "status": "PASS"}]},
            {"title": "Recommended safe cycle size", "verdict": "INFO",
             "evidence": [{"metric": "recommended_safe_cycle_usd", "value": 350.0, "threshold": None, "status": "INFO"}]},
        ],
        "next_steps": [
            "Run additional shadow cycles until completed_cycles ≥ 20",
            "Investigate the 2 stuck events (both STUCK_WAITING_FOR_BDAG)",
            "Recheck stuck_rate_pct after next campaign",
        ],
        "note": ("Read-only evidence package from recorded shadow cycles only. Does NOT authorize "
                 "execution. No trading, no wallet, no withdrawals, no fund movement."),
    }


@api_router.get("/arbicore/intelligence/entities")
async def v2_entities(entity_type: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    # Composed shape: mirrors `/entities` (list) + `/entities/scores/top` (score).
    # Real canonical vocabulary (frozen): WALLET, SMART_MONEY, EXCHANGE_WALLET,
    # MARKET_MAKER, LIQUIDITY_PROVIDER, LAUNCH_PARTICIPANT, CEX_ACCOUNT, DEX_POOL, UNKNOWN.
    all_items = [
        {"entity_id": "ent-w-001", "entity_type": "SMART_MONEY", "label": "0x7Aa9…3F1c",
         "score": 0.94, "samples": 412, "last_seen": _iso_now(),
         "extras": {"chains": ["ethereum", "arbitrum"], "notable": "3× launch alpha last 30d"}},
        {"entity_id": "ent-w-002", "entity_type": "MARKET_MAKER", "label": "0x1F31…C09b",
         "score": 0.88, "samples": 1_248, "last_seen": _iso_now(),
         "extras": {"chains": ["ethereum"], "notable": "Wintermute cluster"}},
        {"entity_id": "ent-w-003", "entity_type": "EXCHANGE_WALLET", "label": "binance-hot-01",
         "score": 0.82, "samples": 9_812, "last_seen": _iso_now(),
         "extras": {"venue": "binance", "notable": "primary hot wallet"}},
        {"entity_id": "ent-p-004", "entity_type": "DEX_POOL", "label": "uniswap-v3 · WETH/USDC 0.05%",
         "score": 0.79, "samples": 3_412, "last_seen": _iso_now(),
         "extras": {"chain": "ethereum", "tvl_usd": 348_000_000}},
        {"entity_id": "ent-w-005", "entity_type": "LIQUIDITY_PROVIDER", "label": "0x9C4b…AB12",
         "score": 0.76, "samples": 289, "last_seen": _iso_now(),
         "extras": {"chains": ["ethereum", "base"]}},
        {"entity_id": "ent-w-006", "entity_type": "LAUNCH_PARTICIPANT", "label": "sol:9r7X…qP2",
         "score": 0.71, "samples": 44, "last_seen": _iso_now(),
         "extras": {"chain": "solana", "notable": "top-10 pump.fun launch buyer"}},
        {"entity_id": "ent-a-007", "entity_type": "CEX_ACCOUNT", "label": "okx-sub-042",
         "score": 0.68, "samples": 2_140, "last_seen": _iso_now(),
         "extras": {"venue": "okx"}},
        {"entity_id": "ent-w-008", "entity_type": "SMART_MONEY", "label": "0x2C8e…9D1f",
         "score": 0.66, "samples": 189, "last_seen": _iso_now(),
         "extras": {"chains": ["ethereum"], "notable": "2× correct pre-listing entries"}},
        {"entity_id": "ent-p-009", "entity_type": "DEX_POOL", "label": "curve · 3pool",
         "score": 0.63, "samples": 4_902, "last_seen": _iso_now(),
         "extras": {"chain": "ethereum", "tvl_usd": 82_000_000}},
        {"entity_id": "ent-w-010", "entity_type": "WALLET", "label": "0x8B72…4E0a",
         "score": 0.61, "samples": 74, "last_seen": _iso_now(),
         "extras": {"chains": ["arbitrum"]}},
    ]
    filtered = [e for e in all_items
                if (not entity_type or entity_type == "ALL" or e["entity_type"] == entity_type)]
    counts_by_type: Dict[str, int] = {}
    for e in all_items:
        counts_by_type[e["entity_type"]] = counts_by_type.get(e["entity_type"], 0) + 1
    return {
        "count": len(filtered),
        "total_entities": len(all_items),
        "counts_by_type": counts_by_type,
        "items": filtered[:limit],
        "vocabulary": ["WALLET", "SMART_MONEY", "EXCHANGE_WALLET", "MARKET_MAKER",
                       "LIQUIDITY_PROVIDER", "LAUNCH_PARTICIPANT", "CEX_ACCOUNT",
                       "DEX_POOL", "UNKNOWN"],
        "generated_at": _iso_now(),
    }


# ---------------------------------------------------------------------------
# UI v2 · Slice 3 preview endpoints — Operations (scanners, cycles, venues,
# interlock, integrations, queues, alerts). Pod-local stubs.
# ---------------------------------------------------------------------------

_V2_SCANNERS = [
    {"family": "CEX_ARBITRAGE", "state": "RUNNING", "cadence_s": 5, "last_run": None, "opps_1h": 43, "gates_dropped_1h": 128, "errors_1h": 0},
    {"family": "DEX_ARBITRAGE", "state": "RUNNING", "cadence_s": 8, "last_run": None, "opps_1h": 27, "gates_dropped_1h": 91, "errors_1h": 1},
    {"family": "FUNDING_ARBITRAGE", "state": "RUNNING", "cadence_s": 30, "last_run": None, "opps_1h": 12, "gates_dropped_1h": 18, "errors_1h": 0},
    {"family": "CROSS_CHAIN_ARBITRAGE", "state": "RUNNING", "cadence_s": 20, "last_run": None, "opps_1h": 9, "gates_dropped_1h": 41, "errors_1h": 0},
    {"family": "FLASH_LOAN_ARBITRAGE", "state": "PAUSED", "cadence_s": 10, "last_run": None, "opps_1h": 0, "gates_dropped_1h": 0, "errors_1h": 0},
    {"family": "LAUNCH_ARBITRAGE", "state": "RUNNING", "cadence_s": 60, "last_run": None, "opps_1h": 3, "gates_dropped_1h": 12, "errors_1h": 0},
    {"family": "SPATIAL_ARBITRAGE", "state": "IDLE", "cadence_s": 15, "last_run": None, "opps_1h": 0, "gates_dropped_1h": 0, "errors_1h": 0},
    {"family": "STATISTICAL_ARBITRAGE", "state": "RUNNING", "cadence_s": 45, "last_run": None, "opps_1h": 6, "gates_dropped_1h": 22, "errors_1h": 0},
]


@api_router.get("/arbicore/operations/scanners")
async def v2_scanners() -> Dict[str, Any]:
    now = _iso_now()
    for s in _V2_SCANNERS:
        if s["last_run"] is None:
            s["last_run"] = now
    return {"items": _V2_SCANNERS, "generated_at": now}


@api_router.post("/arbicore/operations/scanners/{family}/action")
async def v2_scanner_action(family: str, action: str) -> Dict[str, Any]:
    match = next((s for s in _V2_SCANNERS if s["family"] == family), None)
    if match:
        mapping = {"start": "RUNNING", "pause": "PAUSED", "stop": "IDLE"}
        match["state"] = mapping.get(action.lower(), match["state"])
    return {"ok": True, "family": family, "state": match["state"] if match else None, "generated_at": _iso_now()}


@api_router.get("/arbicore/operations/cycles")
async def v2_cycles(status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    cycles = [
        {"id": "cyc-101", "family": "CEX_ARBITRAGE", "route": "binance:ETH-USDT → kucoin:ETH-USDT",
         "status": "SETTLED", "realized_bps": 21.4, "started_at": _iso_now(), "ended_at": _iso_now(),
         "size_usd": 24_800},
        {"id": "cyc-100", "family": "DEX_ARBITRAGE", "route": "uni-v3:WETH/USDC → sushi:WETH/USDC",
         "status": "SETTLED", "realized_bps": 14.2, "started_at": _iso_now(), "ended_at": _iso_now(),
         "size_usd": 18_400},
        {"id": "cyc-099", "family": "FLASH_LOAN_ARBITRAGE", "route": "aave-flash → quickswap → sushiswap",
         "status": "REVERTED", "realized_bps": 0.0, "started_at": _iso_now(), "ended_at": _iso_now(),
         "size_usd": 12_000},
        {"id": "cyc-098", "family": "CEX_ARBITRAGE", "route": "binance:BTC-USDT → okx:BTC-USDT",
         "status": "RUNNING", "realized_bps": None, "started_at": _iso_now(), "ended_at": None,
         "size_usd": 50_000},
        {"id": "cyc-097", "family": "FUNDING_ARBITRAGE", "route": "bybit:SOL-PERP short + spot long",
         "status": "SETTLED", "realized_bps": 11.7, "started_at": _iso_now(), "ended_at": _iso_now(),
         "size_usd": 8_500},
        {"id": "cyc-096", "family": "CROSS_CHAIN_ARBITRAGE", "route": "eth:USDC → arb:USDC (stargate)",
         "status": "SETTLED", "realized_bps": 4.1, "started_at": _iso_now(), "ended_at": _iso_now(),
         "size_usd": 30_000},
    ]
    out = [c for c in cycles if (not status or status == "ALL" or c["status"] == status)][:limit]
    return {"items": out, "total": len(out), "generated_at": _iso_now()}


@api_router.get("/arbicore/operations/venues")
async def v2_venues() -> Dict[str, Any]:
    venues = [
        {"venue": "binance", "kind": "CEX", "state": "READY", "role": "primary", "latency_ms": 42, "last_seen": _iso_now()},
        {"venue": "kucoin", "kind": "CEX", "state": "READY", "role": "primary", "latency_ms": 58, "last_seen": _iso_now()},
        {"venue": "okx", "kind": "CEX", "state": "READY", "role": "primary", "latency_ms": 61, "last_seen": _iso_now()},
        {"venue": "bybit", "kind": "CEX", "state": "READY", "role": "primary", "latency_ms": 66, "last_seen": _iso_now()},
        {"venue": "uniswap-v3", "kind": "DEX", "state": "READY", "role": "primary", "latency_ms": 190, "last_seen": _iso_now()},
        {"venue": "sushiswap", "kind": "DEX", "state": "READY", "role": "secondary", "latency_ms": 210, "last_seen": _iso_now()},
        {"venue": "raydium", "kind": "DEX", "state": "DEGRADED", "role": "secondary", "latency_ms": 480, "last_seen": _iso_now()},
        {"venue": "hyperliquid", "kind": "PERP", "state": "READY", "role": "primary", "latency_ms": 88, "last_seen": _iso_now()},
        {"venue": "gate-io", "kind": "CEX", "state": "OFFLINE", "role": "excluded", "latency_ms": None, "last_seen": _iso_now()},
    ]
    return {"items": venues, "generated_at": _iso_now()}


@api_router.get("/arbicore/operations/interlock")
async def v2_interlock() -> Dict[str, Any]:
    return {
        "armed": True,
        "state": "ARMED",
        "reason": None,
        "gates": [
            {"gate": "safety_min", "state": "PASS", "value": 0.70, "threshold": 0.60},
            {"gate": "freshness_max", "state": "PASS", "value": 12, "threshold": 15},
            {"gate": "depth_min", "state": "PASS", "value": 240_000, "threshold": 100_000},
            {"gate": "regime_ok", "state": "PASS", "value": "CALM", "threshold": "not HOSTILE"},
            {"gate": "capital_deployable", "state": "PASS", "value": 380_000, "threshold": 50_000},
        ],
        "last_transition_at": _iso_now(),
        "generated_at": _iso_now(),
    }


@api_router.post("/arbicore/operations/interlock/action")
async def v2_interlock_action(action: str) -> Dict[str, Any]:
    return {"ok": True, "state": "ARMED" if action == "arm" else "DISARMED", "generated_at": _iso_now()}


@api_router.get("/arbicore/operations/integrations")
async def v2_integrations() -> Dict[str, Any]:
    return {
        "items": [
            {"key": "userscript_v2", "label": "Userscript v2 quote portal", "state": "CONNECTED", "detail": "3 tabs live"},
            {"key": "portal_ws", "label": "Portal WS", "state": "CONNECTED", "detail": "42ms latency"},
            {"key": "coingecko", "label": "CoinGecko", "state": "CONNECTED", "detail": "OK"},
            {"key": "telegram", "label": "Telegram alerts", "state": "CONNECTED", "detail": "chat #ops"},
            {"key": "alchemy", "label": "Alchemy RPC", "state": "DEGRADED", "detail": "ETH mainnet slow"},
            {"key": "chainlink", "label": "Chainlink price feeds", "state": "CONNECTED", "detail": "5 pairs"},
        ],
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/operations/queues")
async def v2_queues() -> Dict[str, Any]:
    return {
        "items": [
            {"queue": "scanner_ingest", "pending": 12, "in_flight": 3, "failed_1h": 0, "rate_per_min": 41},
            {"queue": "confidence_scoring", "pending": 4, "in_flight": 2, "failed_1h": 0, "rate_per_min": 39},
            {"queue": "approval_notify", "pending": 0, "in_flight": 0, "failed_1h": 0, "rate_per_min": 0.5},
            {"queue": "execution_dispatch", "pending": 1, "in_flight": 1, "failed_1h": 0, "rate_per_min": 0.8},
            {"queue": "evidence_bundle", "pending": 6, "in_flight": 1, "failed_1h": 2, "rate_per_min": 3.2},
        ],
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/operations/alerts")
async def v2_alerts(severity: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    alerts = [
        {"id": "alr-9", "severity": "warn", "source": "venue:raydium", "message": "Raydium RPC latency > 400ms for 6m.", "at": _iso_now(), "acked": False},
        {"id": "alr-8", "severity": "info", "source": "scanner:LAUNCH_ARBITRAGE", "message": "New listing detected on kucoin: MOODENG-USDT.", "at": _iso_now(), "acked": False},
        {"id": "alr-7", "severity": "warn", "source": "integration:alchemy", "message": "Alchemy ETH mainnet degraded — freshness stretched.", "at": _iso_now(), "acked": False},
        {"id": "alr-6", "severity": "info", "source": "cycle:cyc-099", "message": "Flash-loan cycle reverted safely; capital returned.", "at": _iso_now(), "acked": True},
        {"id": "alr-5", "severity": "warn", "source": "venue:gate-io", "message": "gate-io session lost; venue set OFFLINE.", "at": _iso_now(), "acked": True},
    ]
    out = [a for a in alerts if (not severity or severity == "ALL" or a["severity"] == severity)][:limit]
    return {"items": out, "total": len(out), "generated_at": _iso_now()}


@api_router.post("/arbicore/operations/alerts/{alert_id}/ack")
async def v2_alert_ack(alert_id: str) -> Dict[str, Any]:
    return {"ok": True, "id": alert_id, "acked": True, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# UI v2 · Slice 4 preview endpoints — Portfolio (positions, balances, transfers,
# deployable capital, treasury, ledger, exposure, allocation).
#
# All shapes below are pod-local stubs that mirror the canonical endpoints
# planned for `app/backend/arbicore/routes/portfolio.py`. UI contract is
# stable; when the real backend lands, only the handlers below get swapped.
#
# Future-endpoint mapping (production):
#   GET  /api/portfolio/positions           <- ExecutionPositionRepo.snapshot()
#   GET  /api/portfolio/balances            <- VenueBalanceService.aggregate()
#   GET  /api/portfolio/transfers           <- TreasuryLedger.transfers(window)
#   GET  /api/portfolio/deployable          <- CapitalRouter.deployable_snapshot()
#   GET  /api/portfolio/treasury            <- TreasuryLedger.vault_snapshot()
#   GET  /api/portfolio/ledger              <- TreasuryLedger.entries(window, kind)
#   GET  /api/portfolio/exposure            <- ExposureAnalyzer.breakdown()
#   GET  /api/portfolio/allocation          <- AllocationPolicy.status()
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/portfolio/positions")
async def v2_positions(venue: Optional[str] = None, side: Optional[str] = None) -> Dict[str, Any]:
    items = [
        {"id": "pos-01", "venue": "binance", "market": "ETH-USDT", "side": "LONG",
         "size_usd": 25_000, "entry_price": 3421.5, "mark_price": 3428.1,
         "upnl_bps": 19.3, "upnl_usd": 48.3, "opened_at": _iso_now()},
        {"id": "pos-02", "venue": "kucoin", "market": "ETH-USDT", "side": "SHORT",
         "size_usd": 25_000, "entry_price": 3430.2, "mark_price": 3428.1,
         "upnl_bps": 6.1, "upnl_usd": 15.2, "opened_at": _iso_now()},
        {"id": "pos-03", "venue": "uniswap-v3", "market": "WETH/USDC", "side": "LP",
         "size_usd": 18_400, "entry_price": 3400.0, "mark_price": 3428.1,
         "upnl_bps": 82.6, "upnl_usd": 151.9, "opened_at": _iso_now()},
        {"id": "pos-04", "venue": "bybit", "market": "SOL-PERP", "side": "SHORT",
         "size_usd": 8_500, "entry_price": 192.4, "mark_price": 189.1,
         "upnl_bps": 171.5, "upnl_usd": 145.7, "opened_at": _iso_now()},
        {"id": "pos-05", "venue": "okx", "market": "BTC-USDT", "side": "LONG",
         "size_usd": 50_000, "entry_price": 68_000.0, "mark_price": 68_180.0,
         "upnl_bps": 26.5, "upnl_usd": 132.4, "opened_at": _iso_now()},
        {"id": "pos-06", "venue": "hyperliquid", "market": "BTC-PERP", "side": "SHORT",
         "size_usd": 12_000, "entry_price": 68_120.0, "mark_price": 68_180.0,
         "upnl_bps": -8.8, "upnl_usd": -10.6, "opened_at": _iso_now()},
    ]
    out = [p for p in items
           if (not venue or venue == "ALL" or p["venue"] == venue)
           and (not side or side == "ALL" or p["side"] == side)]
    total_size = sum(p["size_usd"] for p in out)
    total_upnl = sum(p["upnl_usd"] for p in out)
    return {"items": out, "total": len(out), "total_size_usd": total_size,
            "total_upnl_usd": total_upnl, "generated_at": _iso_now()}


@api_router.get("/arbicore/portfolio/balances")
async def v2_balances(venue: Optional[str] = None) -> Dict[str, Any]:
    items = [
        {"venue": "binance", "asset": "USDT", "total": 82_400.0, "available": 62_400.0, "in_orders": 20_000.0, "usd_value": 82_400.0},
        {"venue": "binance", "asset": "ETH", "total": 7.3, "available": 7.3, "in_orders": 0.0, "usd_value": 25_025.13},
        {"venue": "kucoin", "asset": "USDT", "total": 41_800.0, "available": 16_800.0, "in_orders": 25_000.0, "usd_value": 41_800.0},
        {"venue": "kucoin", "asset": "ETH", "total": 7.3, "available": 0.0, "in_orders": 7.3, "usd_value": 25_025.13},
        {"venue": "okx", "asset": "USDT", "total": 118_000.0, "available": 68_000.0, "in_orders": 50_000.0, "usd_value": 118_000.0},
        {"venue": "okx", "asset": "BTC", "total": 0.734, "available": 0.0, "in_orders": 0.734, "usd_value": 50_044.12},
        {"venue": "bybit", "asset": "USDT", "total": 24_600.0, "available": 16_100.0, "in_orders": 8_500.0, "usd_value": 24_600.0},
        {"venue": "hyperliquid", "asset": "USDC", "total": 18_400.0, "available": 6_400.0, "in_orders": 12_000.0, "usd_value": 18_400.0},
        {"venue": "uniswap-v3", "asset": "WETH/USDC LP", "total": 1.0, "available": 1.0, "in_orders": 0.0, "usd_value": 18_400.0},
        {"venue": "cold_wallet", "asset": "BTC", "total": 2.5, "available": 2.5, "in_orders": 0.0, "usd_value": 170_450.0},
        {"venue": "cold_wallet", "asset": "ETH", "total": 40.0, "available": 40.0, "in_orders": 0.0, "usd_value": 137_124.0},
    ]
    out = [b for b in items if (not venue or venue == "ALL" or b["venue"] == venue)]
    total_usd = sum(b["usd_value"] for b in out)
    return {"items": out, "total": len(out), "total_usd": total_usd, "generated_at": _iso_now()}


@api_router.get("/arbicore/portfolio/transfers")
async def v2_transfers(status: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    items = [
        {"id": "tr-014", "kind": "cex_to_cex", "from": "binance", "to": "okx",
         "asset": "USDT", "amount": 25_000.0, "usd_value": 25_000.0,
         "status": "SETTLED", "started_at": _iso_now(), "settled_at": _iso_now(), "tx": "0xabc…def1"},
        {"id": "tr-013", "kind": "vault_to_cex", "from": "cold_wallet", "to": "binance",
         "asset": "BTC", "amount": 0.5, "usd_value": 34_090.0,
         "status": "SETTLED", "started_at": _iso_now(), "settled_at": _iso_now(), "tx": "0xabc…def2"},
        {"id": "tr-012", "kind": "bridge", "from": "ethereum", "to": "arbitrum",
         "asset": "USDC", "amount": 50_000.0, "usd_value": 50_000.0,
         "status": "SETTLED", "started_at": _iso_now(), "settled_at": _iso_now(), "tx": "stargate:0x…a1"},
        {"id": "tr-011", "kind": "cex_to_vault", "from": "okx", "to": "cold_wallet",
         "asset": "USDT", "amount": 10_000.0, "usd_value": 10_000.0,
         "status": "PENDING", "started_at": _iso_now(), "settled_at": None, "tx": "0xabc…def3"},
        {"id": "tr-010", "kind": "cex_to_vault", "from": "coinbase", "to": "cold_wallet",
         "asset": "USDT", "amount": 20_000.0, "usd_value": 20_000.0,
         "status": "SETTLED", "started_at": _iso_now(), "settled_at": _iso_now(), "tx": "0xabc…def4"},
        {"id": "tr-009", "kind": "bridge", "from": "arbitrum", "to": "base",
         "asset": "WETH", "amount": 3.2, "usd_value": 10_970.0,
         "status": "FAILED", "started_at": _iso_now(), "settled_at": _iso_now(), "tx": "stargate:0x…b2"},
    ]
    out = [t for t in items if (not status or status == "ALL" or t["status"] == status)][:limit]
    return {"items": out, "total": len(out), "generated_at": _iso_now()}


@api_router.get("/arbicore/portfolio/deployable")
async def v2_deployable() -> Dict[str, Any]:
    per_venue = [
        {"venue": "binance", "deployable_usd": 62_400.0, "utilised_usd": 45_000.0, "utilisation_pct": 0.419},
        {"venue": "kucoin", "deployable_usd": 16_800.0, "utilisation_pct": 0.598, "utilised_usd": 25_000.0},
        {"venue": "okx", "deployable_usd": 68_000.0, "utilised_usd": 100_044.0, "utilisation_pct": 0.595},
        {"venue": "bybit", "deployable_usd": 16_100.0, "utilised_usd": 8_500.0, "utilisation_pct": 0.345},
        {"venue": "hyperliquid", "deployable_usd": 6_400.0, "utilised_usd": 12_000.0, "utilisation_pct": 0.652},
        {"venue": "uniswap-v3", "deployable_usd": 4_200.0, "utilised_usd": 18_400.0, "utilisation_pct": 0.814},
    ]
    total_deployable = sum(v["deployable_usd"] for v in per_venue)
    total_utilised = sum(v["utilised_usd"] for v in per_venue)
    total_capital = total_deployable + total_utilised
    return {
        "total_deployable_usd": total_deployable,
        "total_utilised_usd": total_utilised,
        "total_capital_usd": total_capital,
        "utilisation_pct": total_utilised / total_capital if total_capital else 0.0,
        "per_venue": per_venue,
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/portfolio/treasury")
async def v2_treasury() -> Dict[str, Any]:
    vaults = [
        {"vault": "cold_wallet", "kind": "COLD", "custody": "self", "assets": 2, "usd_value": 307_574.0, "last_reconciled_at": _iso_now()},
        {"vault": "hot_wallet", "kind": "HOT", "custody": "self", "assets": 3, "usd_value": 32_100.0, "last_reconciled_at": _iso_now()},
        {"vault": "safe_multisig", "kind": "MULTISIG", "custody": "self", "assets": 4, "usd_value": 148_200.0, "last_reconciled_at": _iso_now()},
        {"vault": "cex_pool", "kind": "EXCHANGE", "custody": "venue", "assets": 8, "usd_value": 385_869.0, "last_reconciled_at": _iso_now()},
    ]
    total = sum(v["usd_value"] for v in vaults)
    return {"vaults": vaults, "total_usd": total, "generated_at": _iso_now()}


@api_router.get("/arbicore/portfolio/ledger")
async def v2_ledger(kind: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    items = [
        {"id": "led-042", "kind": "PNL", "ref": "cyc-101", "delta_usd": +530.7, "balance_usd": 873_743.0, "at": _iso_now(), "note": "CEX arbitrage settled"},
        {"id": "led-041", "kind": "PNL", "ref": "cyc-100", "delta_usd": +261.3, "balance_usd": 873_212.3, "at": _iso_now(), "note": "DEX arbitrage settled"},
        {"id": "led-040", "kind": "FEE",  "ref": "cyc-100", "delta_usd": -18.2, "balance_usd": 872_951.0, "at": _iso_now(), "note": "gas + venue fees"},
        {"id": "led-039", "kind": "TRANSFER", "ref": "tr-014", "delta_usd": 0.0, "balance_usd": 872_969.2, "at": _iso_now(), "note": "internal (netting)"},
        {"id": "led-038", "kind": "PNL", "ref": "cyc-099", "delta_usd": -12.4, "balance_usd": 872_969.2, "at": _iso_now(), "note": "flash-loan reverted, fee only"},
        {"id": "led-037", "kind": "PNL", "ref": "cyc-097", "delta_usd": +99.5, "balance_usd": 872_981.6, "at": _iso_now(), "note": "funding arbitrage settled"},
        {"id": "led-036", "kind": "DEPOSIT", "ref": "tr-010", "delta_usd": +20_000.0, "balance_usd": 872_882.1, "at": _iso_now(), "note": "cold-wallet top-up"},
        {"id": "led-035", "kind": "PNL", "ref": "cyc-096", "delta_usd": +123.0, "balance_usd": 852_882.1, "at": _iso_now(), "note": "cross-chain settled"},
    ]
    out = [x for x in items if (not kind or kind == "ALL" or x["kind"] == kind)][:limit]
    return {"items": out, "total": len(out), "generated_at": _iso_now()}


@api_router.get("/arbicore/portfolio/exposure")
async def v2_exposure() -> Dict[str, Any]:
    by_asset = [
        {"asset": "BTC", "usd_value": 220_494.0, "pct": 0.259, "delta_24h_pct": 0.008},
        {"asset": "ETH", "usd_value": 205_574.0, "pct": 0.241, "delta_24h_pct": 0.012},
        {"asset": "USDT", "usd_value": 266_800.0, "pct": 0.313, "delta_24h_pct": 0.0},
        {"asset": "USDC", "usd_value": 68_400.0, "pct": 0.080, "delta_24h_pct": 0.0},
        {"asset": "SOL", "usd_value": 42_180.0, "pct": 0.049, "delta_24h_pct": -0.024},
        {"asset": "OTHER", "usd_value": 49_295.0, "pct": 0.058, "delta_24h_pct": 0.004},
    ]
    by_chain = [
        {"chain": "cex", "usd_value": 385_869.0, "pct": 0.454},
        {"chain": "ethereum", "usd_value": 226_000.0, "pct": 0.266},
        {"chain": "arbitrum", "usd_value": 92_400.0, "pct": 0.109},
        {"chain": "solana", "usd_value": 42_180.0, "pct": 0.049},
        {"chain": "base", "usd_value": 18_400.0, "pct": 0.022},
        {"chain": "cold", "usd_value": 87_894.0, "pct": 0.103},
    ]
    return {"by_asset": by_asset, "by_chain": by_chain, "total_usd": sum(a["usd_value"] for a in by_asset), "generated_at": _iso_now()}


@api_router.get("/arbicore/portfolio/allocation")
async def v2_allocation() -> Dict[str, Any]:
    items = [
        {"bucket": "CEX_ARBITRAGE", "target_pct": 0.35, "actual_pct": 0.31, "target_usd": 297_500.0, "actual_usd": 263_400.0, "delta_usd": -34_100.0, "status": "UNDER"},
        {"bucket": "DEX_ARBITRAGE", "target_pct": 0.20, "actual_pct": 0.22, "target_usd": 170_000.0, "actual_usd": 187_000.0, "delta_usd": +17_000.0, "status": "OVER"},
        {"bucket": "FUNDING_ARBITRAGE", "target_pct": 0.15, "actual_pct": 0.11, "target_usd": 127_500.0, "actual_usd": 93_500.0, "delta_usd": -34_000.0, "status": "UNDER"},
        {"bucket": "FLASH_LOAN_ARBITRAGE", "target_pct": 0.05, "actual_pct": 0.02, "target_usd": 42_500.0, "actual_usd": 17_000.0, "delta_usd": -25_500.0, "status": "UNDER"},
        {"bucket": "TREASURY_RESERVE", "target_pct": 0.25, "actual_pct": 0.34, "target_usd": 212_500.0, "actual_usd": 288_874.0, "delta_usd": +76_374.0, "status": "OVER"},
    ]
    return {"items": items, "total_target_usd": sum(x["target_usd"] for x in items), "total_actual_usd": sum(x["actual_usd"] for x in items), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# UI v2 · Slice 5 preview endpoints — Settings (account, vault, execution,
# exchanges, notifications, documentation, operational).
#
# All shapes below are pod-local stubs that mirror the canonical endpoints
# planned for `app/backend/arbicore/routes/settings.py` (and existing legacy
# routes noted per section). UI contract is stable; when the real backend
# lands, only the handlers below get swapped.
#
# Future-endpoint mapping (production):
#   GET/PATCH  /api/settings/account          <- UserService.profile()
#   GET        /api/settings/vaults           <- TreasuryLedger.list_vaults()
#   POST       /api/settings/vaults/{v}/reconcile <- TreasuryLedger.reconcile()
#   GET/PATCH  /api/settings/execution        <- ExecutionPolicy.config()
#   GET        /api/settings/exchanges        <- VenueRegistry.list_configured()
#   POST       /api/settings/exchanges/{k}/test <- VenueRegistry.test_connectivity()
#   GET/PATCH  /api/settings/notifications    <- NotificationConfig.load()/save()
#   GET        /api/settings/documentation    <- static registry (docs index)
#   GET/PATCH  /api/settings/operational      <- OperatorFlags.snapshot()/set()
# ---------------------------------------------------------------------------

_V2_ACCOUNT = {
    "username": "operator",
    "display_name": "Ops Desk 01",
    "email": "ops@arbicore.internal",
    "role": "operator",
    "mfa_enabled": True,
    "session_ttl_min": 60,
    "last_login_at": None,
    "created_at": "2025-11-04T09:12:00+00:00",
}

_V2_EXECUTION = {
    "max_position_usd": 100_000,
    "max_daily_notional_usd": 2_500_000,
    "slippage_bps": 8,
    "min_confidence": 0.60,
    "min_safety": 0.65,
    "freshness_max_s": 15,
    "auto_execute_enabled": False,
    "auto_execute_verdict": "GO",
    "kill_switch_wired": True,
}

_V2_NOTIFICATIONS = {
    "telegram_enabled": True,
    "telegram_chat": "#ops",
    "email_enabled": True,
    "email_to": ["ops@arbicore.internal"],
    "webhook_enabled": False,
    "webhook_url": "",
    "severities": {"info": False, "warn": True, "error": True},
    "events": {
        "opportunity_go": True,
        "cycle_settled": True,
        "cycle_reverted": True,
        "venue_offline": True,
        "interlock_transition": True,
    },
}

_V2_OPERATIONAL = {
    "maintenance_mode": False,
    "trading_paused": False,
    "read_only": False,
    "dev_mode": False,
    "verbose_logging": False,
    "feature_flags": {
        "ui_v2": True,
        "auto_execute": False,
        "cross_chain_scanner": True,
        "flash_loan_scanner": True,
    },
}


@api_router.get("/arbicore/settings/account")
async def v2_settings_account() -> Dict[str, Any]:
    acct = await _ACCOUNT_REPO.get()
    if not acct.get("last_login_at"):
        acct = {**acct, "last_login_at": _iso_now()}
    return {"account": acct, "generated_at": _iso_now()}


@api_router.patch("/arbicore/settings/account")
async def v2_settings_account_update(patch: Dict[str, Any]) -> Dict[str, Any]:
    try:
        updated = await _ACCOUNT_REPO.patch(patch or {}, actor="operator")
        return {"ok": True, "account": updated, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.get("/arbicore/settings/vaults")
async def v2_settings_vaults() -> Dict[str, Any]:
    items = [
        {"vault": "cold_wallet", "kind": "COLD", "custody": "self", "address": "bc1q…7fx3", "signers_required": 2, "signers_total": 3, "reconciled_at": _iso_now(), "state": "READY"},
        {"vault": "hot_wallet", "kind": "HOT", "custody": "self", "address": "0xA1…9F", "signers_required": 1, "signers_total": 1, "reconciled_at": _iso_now(), "state": "READY"},
        {"vault": "safe_multisig", "kind": "MULTISIG", "custody": "self", "address": "0x8C…C2", "signers_required": 3, "signers_total": 5, "reconciled_at": _iso_now(), "state": "READY"},
        {"vault": "cex_pool", "kind": "EXCHANGE", "custody": "venue", "address": "-", "signers_required": 0, "signers_total": 0, "reconciled_at": _iso_now(), "state": "READY"},
    ]
    return {"items": items, "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/vaults/{vault}/reconcile")
async def v2_settings_vault_reconcile(vault: str) -> Dict[str, Any]:
    return {"ok": True, "vault": vault, "reconciled_at": _iso_now(), "generated_at": _iso_now()}


@api_router.get("/arbicore/settings/execution")
async def v2_settings_execution() -> Dict[str, Any]:
    cfg = await _EXECUTION_SETTINGS.get()
    return {"config": cfg, "generated_at": _iso_now()}


@api_router.patch("/arbicore/settings/execution")
async def v2_settings_execution_update(patch: Dict[str, Any]) -> Dict[str, Any]:
    try:
        updated = await _EXECUTION_SETTINGS.patch(patch or {}, actor="operator")
        return {"ok": True, "config": updated, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.get("/arbicore/settings/exchanges")
async def v2_settings_exchanges() -> Dict[str, Any]:
    items = [
        {"key": "binance", "label": "Binance", "kind": "CEX", "role": "primary", "api_key_masked": "AKb••••••••u3q", "state": "CONNECTED", "read_only": False, "last_tested_at": _iso_now()},
        {"key": "kucoin", "label": "KuCoin", "kind": "CEX", "role": "primary", "api_key_masked": "AKk••••••••j4p", "state": "CONNECTED", "read_only": False, "last_tested_at": _iso_now()},
        {"key": "okx", "label": "OKX", "kind": "CEX", "role": "primary", "api_key_masked": "AKo••••••••x9m", "state": "CONNECTED", "read_only": False, "last_tested_at": _iso_now()},
        {"key": "bybit", "label": "Bybit", "kind": "CEX", "role": "primary", "api_key_masked": "AKy••••••••t2v", "state": "CONNECTED", "read_only": False, "last_tested_at": _iso_now()},
        {"key": "hyperliquid", "label": "Hyperliquid", "kind": "PERP", "role": "primary", "api_key_masked": "AKh••••••••q6w", "state": "CONNECTED", "read_only": False, "last_tested_at": _iso_now()},
        {"key": "gate-io", "label": "Gate.io", "kind": "CEX", "role": "excluded", "api_key_masked": "AKg••••••••e1z", "state": "DISCONNECTED", "read_only": True, "last_tested_at": _iso_now()},
        {"key": "coinbase", "label": "Coinbase", "kind": "CEX", "role": "secondary", "api_key_masked": "AKc••••••••p8b", "state": "CONNECTED", "read_only": True, "last_tested_at": _iso_now()},
    ]
    return {"items": items, "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/exchanges/{key}/test")
async def v2_settings_exchange_test(key: str) -> Dict[str, Any]:
    ok = key != "gate-io"
    return {"ok": ok, "key": key, "state": "CONNECTED" if ok else "DISCONNECTED",
            "latency_ms": 62 if ok else None, "tested_at": _iso_now()}


@api_router.get("/arbicore/settings/notifications")
async def v2_settings_notifications() -> Dict[str, Any]:
    """Legacy shape kept for backward compat. The primary Telegram surface
    is now `/api/arbicore/settings/telegram`.  This endpoint returns a
    superset: legacy fields (email/webhook stubs) alongside the real
    Telegram config."""
    telegram = await _TELEGRAM.get_settings()
    return {
        "config": {
            "telegram_enabled": telegram["enabled"],
            "telegram_chat": telegram["chat_id"],
            "telegram_token_set": telegram["token_set"],
            "telegram_token_mask": telegram["token_mask"],
            "email_enabled": False,
            "email_to": [],
            "webhook_enabled": False,
            "webhook_url": "",
            "severities": {"info": False, "warn": True, "error": True},
            "events": telegram["rules"],
        },
        "generated_at": _iso_now(),
    }


@api_router.patch("/arbicore/settings/notifications")
async def v2_settings_notifications_update(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy PATCH — maps the small legacy schema onto the Telegram service."""
    p = patch or {}
    save_args: Dict[str, Any] = {}
    if "telegram_enabled" in p:
        save_args["enabled"] = bool(p["telegram_enabled"])
    if "telegram_chat" in p:
        save_args["chat_id"] = str(p["telegram_chat"])
    if "events" in p and isinstance(p["events"], dict):
        save_args["rules"] = p["events"]
    if save_args:
        await _TELEGRAM.save_settings(**save_args, actor="operator",
                                        reason="legacy notifications PATCH")
    return await v2_settings_notifications()


@api_router.get("/arbicore/settings/documentation")
async def v2_settings_documentation() -> Dict[str, Any]:
    items = [
        {"title": "Architecture", "path": "docs/ARCHITECTURE.md", "category": "guide"},
        {"title": "Install & Deploy", "path": "docs/INSTALL.md", "category": "guide"},
        {"title": "Roadmap", "path": "docs/ROADMAP.md", "category": "guide"},
        {"title": "UI v2 Master Spec", "path": "docs/ui_v2/04_UI_V2_MASTER_SPEC.md", "category": "reference"},
        {"title": "UI v2 Design Language", "path": "docs/ui_v2/design_language.md", "category": "reference"},
        {"title": "Backend Capability Audit", "path": "docs/ui_v2/01_BACKEND_CAPABILITY_AUDIT.md", "category": "reference"},
        {"title": "UI Exposure Matrix", "path": "docs/ui_v2/02_UI_EXPOSURE_MATRIX.md", "category": "reference"},
        {"title": "Information Architecture", "path": "docs/ui_v2/03_INFORMATION_ARCHITECTURE.md", "category": "reference"},
        {"title": "User Journeys", "path": "docs/ui_v2/appendix/USER_JOURNEYS.md", "category": "reference"},
        {"title": "Wireframes", "path": "docs/ui_v2/appendix/wireframes.md", "category": "reference"},
        {"title": "Release v1.0.2", "path": "docs/releases/v1.0.2.md", "category": "release"},
    ]
    return {"items": items, "generated_at": _iso_now()}


@api_router.get("/arbicore/settings/operational")
async def v2_settings_operational() -> Dict[str, Any]:
    cfg = await _OPERATIONAL_FLAGS.get()
    return {"config": cfg, "generated_at": _iso_now()}


@api_router.patch("/arbicore/settings/operational")
async def v2_settings_operational_update(patch: Dict[str, Any]) -> Dict[str, Any]:
    try:
        updated = await _OPERATIONAL_FLAGS.patch(patch or {}, actor="operator")
        return {"ok": True, "config": updated, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.get("/arbicore/intelligence/calibration/status")
async def v2_calibration_status() -> Dict[str, Any]:
    """Wave-3 pipeline status — worker liveness, config, last tick result."""
    return {"worker": _CALIBRATION_WORKER.status, "generated_at": _iso_now()}


@api_router.get("/arbicore/intelligence/calibration/history")
async def v2_calibration_history(limit: int = 20) -> Dict[str, Any]:
    """Wave-3 — historical calibration models (audit trail)."""
    try:
        items = await _CALIBRATION_REPO.list_recent("confidence", limit=limit)
    except Exception:
        items = []
    return {"items": items, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-4 exposures — Adaptive Weights (OBSERVE mode).  Read-only surface.
# Live scoring is NEVER modified by these endpoints — they return the
# currently-persisted recommendation snapshot for operator review only.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/intelligence/weights/current")
async def v2_weights_current() -> Dict[str, Any]:
    """Canonical ``/weights/current`` shape enriched with recommendation
    deltas.  Returned in OBSERVE mode — informational only."""
    active = None
    try:
        active = await _ADAPTIVE_WEIGHTS_REPO.get_active("adaptive_weights")
    except Exception:
        active = None
    if active is None:
        return {
            "mode": _ADAPTIVE_WEIGHTS_CFG.mode,
            "provider_version": _ADAPTIVE_WEIGHTS_CFG.provider_version,
            "count": 0,
            "weights": {},
            "cache_age_s": None,
            "neutral_default": _ADAPTIVE_WEIGHTS_CFG.neutral_weight,
            "min": _ADAPTIVE_WEIGHTS_CFG.min_weight,
            "max": _ADAPTIVE_WEIGHTS_CFG.max_weight,
            "note": "awaiting sufficient real observations",
            "generated_at": _iso_now(),
        }
    weights = {
        r["signal_id"]: r.get("recommended_weight", _ADAPTIVE_WEIGHTS_CFG.neutral_weight)
        for r in active.get("recommendations", [])
    }
    return {
        "mode": active.get("mode", _ADAPTIVE_WEIGHTS_CFG.mode),
        "provider_version": active.get("provider_version"),
        "model_id": active.get("id"),
        "count": len(weights),
        "weights": weights,
        "aggregate_confidence": active.get("aggregate_confidence", 0.0),
        "neutral_default": _ADAPTIVE_WEIGHTS_CFG.neutral_weight,
        "min": _ADAPTIVE_WEIGHTS_CFG.min_weight,
        "max": _ADAPTIVE_WEIGHTS_CFG.max_weight,
        "note": active.get("note", ""),
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/intelligence/weights/recommendations")
async def v2_weights_recommendations(min_confidence: float = 0.0) -> Dict[str, Any]:
    """Full recommendation set with baseline / recommended / delta /
    confidence / expected_score_impact / evidence per signal."""
    active = None
    try:
        active = await _ADAPTIVE_WEIGHTS_REPO.get_active("adaptive_weights")
    except Exception:
        active = None
    if active is None:
        return {
            "mode": _ADAPTIVE_WEIGHTS_CFG.mode,
            "provider_version": _ADAPTIVE_WEIGHTS_CFG.provider_version,
            "model_id": None,
            "n_signals": 0,
            "aggregate_confidence": 0.0,
            "recommendations": [],
            "note": "awaiting sufficient real observations",
            "generated_at": _iso_now(),
        }
    items = [r for r in active.get("recommendations", [])
             if float(r.get("confidence", 0.0)) >= float(min_confidence)]
    return {
        "mode": active.get("mode", _ADAPTIVE_WEIGHTS_CFG.mode),
        "provider_version": active.get("provider_version"),
        "model_id": active.get("id"),
        "n_signals": len(items),
        "aggregate_confidence": active.get("aggregate_confidence", 0.0),
        "recommendations": items,
        "note": active.get("note", ""),
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/intelligence/weights/status")
async def v2_weights_status() -> Dict[str, Any]:
    """Worker liveness + config for operator observability."""
    return {"worker": _ADAPTIVE_WEIGHTS_WORKER.status, "generated_at": _iso_now()}


@api_router.get("/arbicore/intelligence/weights/history")
async def v2_weights_history(limit: int = 20) -> Dict[str, Any]:
    """Historical adaptive-weight recommendation snapshots (audit trail)."""
    try:
        items = await _ADAPTIVE_WEIGHTS_REPO.list_recent("adaptive_weights", limit=limit)
    except Exception:
        items = []
    return {"items": items, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-5 exposures — Evidence Bundle Signing (Ed25519).  Read-only surface
# plus a stateless verification endpoint.  Never mutates learning state.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/intelligence/evidence/current")
async def v2_evidence_current(source: str = "calibration") -> Dict[str, Any]:
    """Latest signed evidence bundle for a given source component."""
    try:
        bundle = await _EVIDENCE_REPO.get_latest(source)
    except Exception:
        bundle = None
    return {
        "bundle": bundle,
        "source": source,
        "signer_enabled": _SIGNING_CFG.has_signing_material(),
        "unsigned_reason": _SIGNING_CFG.unsigned_reason(),
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/intelligence/evidence/history")
async def v2_evidence_history(source: Optional[str] = None,
                              limit: int = 20) -> Dict[str, Any]:
    """Audit trail across all sources (or filtered to one)."""
    try:
        items = await _EVIDENCE_REPO.list_recent(source, limit=limit)
    except Exception:
        items = []
    return {
        "items": items,
        "source": source,
        "count": len(items),
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/intelligence/evidence/status")
async def v2_evidence_status() -> Dict[str, Any]:
    """Signer + worker observability — key version, failure counts, last
    successful signing, unsigned-reason (if applicable)."""
    return {"worker": _EVIDENCE_WORKER.status, "generated_at": _iso_now()}


@api_router.get("/arbicore/intelligence/evidence/keys")
async def v2_evidence_keys() -> Dict[str, Any]:
    """Registered signing keys (public halves + versions) for external
    verifiers.  Never returns secret material."""
    keys = [
        {
            "version": k.version,
            "algorithm": k.algorithm,
            "public_key_b64": k.public_b64,
            "signing_enabled": bool(k.secret_b64),
            "is_active": (k.version == _SIGNING_CFG.active_key_version),
        }
        for k in _SIGNING_CFG.keys.values()
    ]
    return {
        "active_key_version": _SIGNING_CFG.active_key_version,
        "keys": keys,
        "generated_at": _iso_now(),
    }


@api_router.post("/arbicore/intelligence/evidence/verify")
async def v2_evidence_verify(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Verify a supplied bundle.  Deterministic — no wall-clock inputs.
    Works for historical bundles as long as the referenced
    ``signing_key_version`` is still registered (public half only)."""
    result = _EVIDENCE_VERIFIER.verify(bundle or {})
    return {**result, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-6A exposures — Execution Substrate.  Read-only surface + audited
# mode-ladder transitions.  No live signing or fund movement.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/execution/mode")
async def v2_execution_mode() -> Dict[str, Any]:
    """Per-strategy execution mode map with deployment defaults + ladder."""
    try:
        items = await _EXECUTION_MODE_REPO.list_all()
    except Exception:
        items = []
    defaults = default_mode_map()
    # Fill in any missing rows with defaults (bootstrap surface).
    known = {row["strategy"] for row in items}
    for strategy, mode in defaults.items():
        if strategy not in known:
            items.append({"strategy": strategy, "mode": mode,
                          "seeded": True, "bootstrap_only": True})
    return {
        "items": items,
        "ladder": list(MODES),
        "trading_strategies": list(TRADING_STRATEGIES),
        "defaults": defaults,
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/execution/mode/{strategy}")
async def v2_execution_mode_one(strategy: str) -> Dict[str, Any]:
    try:
        row = await _EXECUTION_MODE_REPO.get(strategy)
    except Exception:
        row = None
    if row is None:
        # Fall back to default posture — surface it as bootstrap-only so
        # operators know the row hasn't been persisted yet.
        default_mode = default_mode_map().get(strategy)
        if default_mode is None:
            return {"strategy": strategy, "mode": None,
                    "error": "unknown strategy",
                    "generated_at": _iso_now()}
        row = {"strategy": strategy, "mode": default_mode,
               "seeded": True, "bootstrap_only": True}
    return {"item": row, "broadcast_allowed": is_broadcast_allowed(row["mode"]),
            "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/mode/{strategy}")
async def v2_execution_mode_transition(strategy: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Apply an audit-logged mode transition.  Enforces the 5-step ladder
    (forward = one step at a time, backward = any distance is allowed)."""
    to_mode = (body or {}).get("to_mode")
    reason = (body or {}).get("reason", "")
    actor = (body or {}).get("actor", "operator")
    if not to_mode:
        return {"error": "to_mode is required",
                "ladder": list(MODES),
                "generated_at": _iso_now()}
    try:
        row = await _EXECUTION_MODE_REPO.transition(
            strategy, to_mode, reason=reason, actor=actor
        )
    except ValueError as e:
        return {"error": str(e), "ladder": list(MODES),
                "generated_at": _iso_now()}
    return {"item": row,
            "broadcast_allowed": is_broadcast_allowed(row["mode"]),
            "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/mode/audit/history")
async def v2_execution_mode_audit(strategy: Optional[str] = None,
                                  limit: int = 50) -> Dict[str, Any]:
    try:
        items = await _EXECUTION_MODE_REPO.audit_history(strategy, limit=limit)
    except Exception:
        items = []
    return {"items": items, "count": len(items),
            "strategy": strategy, "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/wallets")
async def v2_execution_wallets(chain: Optional[str] = None,
                               execution_role: Optional[str] = None) -> Dict[str, Any]:
    try:
        items = await _WALLET_REGISTRY.list_all(chain, execution_role)
    except Exception:
        items = []
    return {"items": items, "count": len(items),
            "supported_chains": list(SUPPORTED_CHAINS),
            "execution_roles": list(EXECUTION_ROLES),
            "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/wallets/{wallet_id}")
async def v2_execution_wallet_one(wallet_id: str) -> Dict[str, Any]:
    try:
        row = await _WALLET_REGISTRY.get(wallet_id)
    except Exception:
        row = None
    if row is None:
        return {"item": None, "error": "wallet not found",
                "generated_at": _iso_now()}
    return {"item": row, "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/wallets")
async def v2_execution_wallet_register(body: Dict[str, Any]) -> Dict[str, Any]:
    """Register a wallet with an execution role.  Never accepts private
    key material — only a reference to a secret handle (see
    ``/api/arbicore/execution/secrets``)."""
    b = body or {}
    try:
        row = await _WALLET_REGISTRY.register(
            wallet_id=b.get("wallet_id") or "",
            address=b.get("address") or "",
            chain=b.get("chain", "base"),
            execution_role=b.get("execution_role", "watch_only"),
            label=b.get("label"),
            whitelisted_venues=b.get("whitelisted_venues") or [],
            secret_handle_id=b.get("secret_handle_id"),
            actor=b.get("actor", "operator"),
            reason=b.get("reason", ""),
        )
    except ValueError as e:
        return {"error": str(e), "generated_at": _iso_now()}
    except Exception as e:  # noqa: BLE001
        return {"error": f"registration failed: {type(e).__name__}",
                "generated_at": _iso_now()}
    return {"item": row, "generated_at": _iso_now()}


@api_router.patch("/arbicore/execution/wallets/{wallet_id}/role")
async def v2_execution_wallet_role(wallet_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    b = body or {}
    try:
        row = await _WALLET_REGISTRY.update_role(
            wallet_id=wallet_id,
            execution_role=b.get("execution_role") or "",
            actor=b.get("actor", "operator"),
            reason=b.get("reason", ""),
        )
    except ValueError as e:
        return {"error": str(e), "generated_at": _iso_now()}
    if row is None:
        return {"item": None, "error": "wallet not found",
                "generated_at": _iso_now()}
    return {"item": row, "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/wallets/audit/history")
async def v2_execution_wallet_audit(wallet_id: Optional[str] = None,
                                    limit: int = 50) -> Dict[str, Any]:
    try:
        items = await _WALLET_REGISTRY.audit_history(wallet_id, limit=limit)
    except Exception:
        items = []
    return {"items": items, "count": len(items),
            "wallet_id": wallet_id, "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/secrets")
async def v2_execution_secrets() -> Dict[str, Any]:
    """List registered secret handles.  Metadata only — never plaintext
    or cipher material."""
    try:
        handles = await _SECRET_REGISTRY.list_handles()
    except Exception:
        handles = []
    # Defensive strip — belt-and-braces even though the backend already
    # scrubs cipher.
    safe = []
    for h in handles:
        safe.append({k: v for k, v in h.items() if k not in ("cipher", "plaintext")})
    return {"items": safe, "count": len(safe),
            "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/secrets/status")
async def v2_execution_secrets_status() -> Dict[str, Any]:
    """Backend availability + default provider — never leaks material."""
    return {"registry": _SECRET_REGISTRY.status,
            "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 10.5 · Secrets Management — write REST
# ---------------------------------------------------------------------------

_ALLOWED_SECRET_SCOPES = {
    "cex_read", "cex_trade", "cex_withdraw", "evm_sign", "custom",
}
_ALLOWED_SECRET_ALGOS = {
    "eth_privkey", "cex_api_secret", "telegram_bot_token",
    "generic_bytes", "generic_utf8",
}


def _mask_plaintext(plaintext: str) -> str:
    if not plaintext:
        return ""
    if len(plaintext) <= 8:
        return plaintext[:2] + "…"
    return plaintext[:4] + "…" + plaintext[-4:]


@api_router.post("/arbicore/execution/secrets")
async def v2_execution_secrets_put(body: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap and store an operator-supplied secret.

    Body:
        plaintext:  str        (required — the secret material)
        scope:      str        (broadcast|signing|notifications|exchange_api|custom)
        algorithm:  str        (eth_privkey|cex_api_secret|telegram_bot_token|...)
        label:      str        (optional — displayed in the UI, e.g. "burner-01")
    The REST response NEVER echoes the plaintext or the cipher.
    """
    b = body or {}
    plaintext = (b.get("plaintext") or "").strip()
    scope = (b.get("scope") or "").strip()
    algo  = (b.get("algorithm") or "").strip()
    label = (b.get("label") or "").strip()
    if not plaintext:
        return {"ok": False, "error": "plaintext required",
                 "generated_at": _iso_now()}
    if scope not in _ALLOWED_SECRET_SCOPES:
        return {"ok": False,
                 "error": f"scope must be one of {sorted(_ALLOWED_SECRET_SCOPES)}",
                 "generated_at": _iso_now()}
    if algo not in _ALLOWED_SECRET_ALGOS:
        return {"ok": False,
                 "error": f"algorithm must be one of {sorted(_ALLOWED_SECRET_ALGOS)}",
                 "generated_at": _iso_now()}
    # eth_privkey sanity — 64 hex chars, no 0x
    if algo == "eth_privkey":
        h = plaintext.removeprefix("0x").strip()
        if len(h) != 64 or not all(c in "0123456789abcdefABCDEF" for c in h):
            return {"ok": False,
                     "error": "eth_privkey must be 64 hex chars",
                     "generated_at": _iso_now()}
        plaintext = h  # store canonical (no 0x)
    try:
        handle = await _SECRET_REGISTRY.put(
            plaintext.encode("utf-8"),
            scope=scope, algorithm=algo, label=label,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                 "error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}
    return {"ok": True,
             "handle": {
                 "handle_id": handle.handle_id,
                 "scope": handle.scope,
                 "algorithm": handle.algorithm,
                 "label": handle.label,
                 "provider": handle.provider,
                 "mask": _mask_plaintext(plaintext),
             },
             "generated_at": _iso_now()}


@api_router.delete("/arbicore/execution/secrets/{handle_id}")
async def v2_execution_secrets_delete(handle_id: str) -> Dict[str, Any]:
    try:
        ok = await _SECRET_REGISTRY.delete(handle_id)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}
    return {"ok": bool(ok), "handle_id": handle_id,
             "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/secrets/{handle_id}/rotate")
async def v2_execution_secrets_rotate(handle_id: str,
                                        body: Dict[str, Any]) -> Dict[str, Any]:
    """Atomically rotate a secret.

    Creates a new handle with the supplied plaintext (reusing the old
    handle's scope + algorithm + label), then deletes the old one.
    Existing pointers to the old handle (e.g. wallet.secret_handle_id)
    are NOT automatically updated — the caller must PATCH them (the UI
    does this).
    """
    b = body or {}
    plaintext = (b.get("plaintext") or "").strip()
    if not plaintext:
        return {"ok": False, "error": "plaintext required",
                 "generated_at": _iso_now()}
    handles = await _SECRET_REGISTRY.list_handles()
    old = next((h for h in handles if h.get("handle_id") == handle_id), None)
    if not old:
        return {"ok": False, "error": "handle not found",
                 "generated_at": _iso_now()}
    algo = old.get("algorithm") or "generic_bytes"
    if algo == "eth_privkey":
        h = plaintext.removeprefix("0x").strip()
        if len(h) != 64 or not all(c in "0123456789abcdefABCDEF" for c in h):
            return {"ok": False, "error": "eth_privkey must be 64 hex chars",
                     "generated_at": _iso_now()}
        plaintext = h
    try:
        new_handle = await _SECRET_REGISTRY.put(
            plaintext.encode("utf-8"),
            scope=old.get("scope") or "custom",
            algorithm=algo,
            label=old.get("label") or "",
        )
        await _SECRET_REGISTRY.delete(handle_id)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                 "error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}
    return {"ok": True,
             "old_handle_id": handle_id,
             "new_handle": {
                 "handle_id": new_handle.handle_id,
                 "scope": new_handle.scope,
                 "algorithm": new_handle.algorithm,
                 "label": new_handle.label,
                 "provider": new_handle.provider,
                 "mask": _mask_plaintext(plaintext),
             },
             "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/secrets/{handle_id}/test")
async def v2_execution_secrets_test(handle_id: str) -> Dict[str, Any]:
    """Structural test — resolve the handle from the backend, confirm
    the plaintext decrypts (mask the first few bytes), verify algorithm-
    specific sanity.  Never returns plaintext."""
    try:
        plaintext = await _SECRET_REGISTRY.resolve(handle_id)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}
    if plaintext is None:
        return {"ok": False, "error": "handle not found or decrypt failed",
                 "generated_at": _iso_now()}
    handles = await _SECRET_REGISTRY.list_handles()
    meta = next((h for h in handles if h.get("handle_id") == handle_id), {})
    algo = meta.get("algorithm") or "generic_bytes"
    checks: Dict[str, Any] = {"decrypt": True, "algorithm": algo}
    if algo == "eth_privkey":
        s = plaintext.decode("utf-8", errors="ignore").removeprefix("0x").strip()
        checks["hex_length_64"] = len(s) == 64
        checks["hex_only"] = all(c in "0123456789abcdefABCDEF" for c in s)
    return {"ok": all(v is True for v in checks.values() if isinstance(v, bool)),
             "handle_id": handle_id,
             "checks": checks,
             "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-6B exposures — Adapter catalogue, plan build, dry-run, history.
# SHADOW ONLY.  No signing, no broadcasting anywhere below.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/execution/adapters")
async def v2_execution_adapters() -> Dict[str, Any]:
    return {**_ADAPTER_REGISTRY.catalog(), "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/plans/build")
async def v2_execution_plan_build(body: Dict[str, Any]) -> Dict[str, Any]:
    """Build (and dry-run) an execution plan.  The result is persisted
    to ``db.execution_plans`` but never signed or broadcast."""
    b = body or {}
    # Wave-6B constraint — historical: build was blocked in LIMITED_LIVE to
    # prevent accidental live plans during Wave 6 rollout.  Wave 7C shipped
    # the LIMITED_LIVE broadcaster which enforces the mode gate at broadcast
    # time (broadcast.py Gate 2), so the build-time guard is redundant.
    # Phase 10.10.1 lifts LIMITED_LIVE from the block-list; FULL_LIVE remains
    # blocked pending a future review.
    strategy = b.get("strategy") or "flash_loan_arbitrage"
    mode_row = await _EXECUTION_MODE_REPO.get(strategy)
    current_mode = (mode_row or {}).get("mode") or default_mode_map().get(strategy)
    if current_mode not in ("OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE"):
        return {"error": f"strategy '{strategy}' is in mode '{current_mode}' — "
                         "plan build accepts OBSERVE/PAPER/SHADOW/LIMITED_LIVE only",
                "generated_at": _iso_now()}
    try:
        plan = _EXECUTION_PLANNER.build(
            strategy=strategy,
            chain=b.get("chain", "base"),
            borrow_token=b.get("borrow_token") or "",
            borrow_amount_wei=int(b.get("borrow_amount_wei") or 0),
            flash_loan_provider=b.get("flash_loan_provider") or "",
            swap_hops=b.get("swap_hops") or [],
            signer_wallet_id=b.get("signer_wallet_id"),
            opportunity_id=b.get("opportunity_id"),
            borrow_amount_usd=b.get("borrow_amount_usd"),
            flash_fee_bps_override=b.get("flash_fee_bps_override"),
            mode=current_mode,
        )
    except ValueError as e:
        return {"error": str(e), "generated_at": _iso_now()}
    # Phase 10.10.8 · Manual Plan Composer now also runs the canonical
    # live-quote pipeline by default.  A caller can still override the
    # quote/gas explicitly (e.g. Tenderly counterfactual, historical
    # backtest); anything else routes through ``evaluate_live``.
    if (b.get("quote_effective_out_wei") is None and
            b.get("gas_estimate_usd") is None):
        try:
            await _DRY_RUN_ENGINE.evaluate_live(plan)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Manual Composer live evaluate failed (%s); "
                            "falling back to deterministic", type(exc).__name__)
            _DRY_RUN_ENGINE.evaluate(plan)
    else:
        _DRY_RUN_ENGINE.evaluate(
            plan,
            quote_effective_out_wei=b.get("quote_effective_out_wei"),
            gas_estimate_usd=b.get("gas_estimate_usd"),
        )
    try:
        await _EXECUTION_PLANS_REPO.ensure_indexes()
        stored = await _EXECUTION_PLANS_REPO.insert(plan)
        logger.info("plans/build persisted plan_id=%s mode=%s strategy=%s",
                     (stored or {}).get("plan_id") if isinstance(stored, dict) else getattr(stored, "plan_id", "?"),
                     current_mode, strategy)
        return {"plan": stored, "generated_at": _iso_now()}
    except Exception as exc:
        # Phase 10.10.5 — DO NOT silently swallow the persist error and hand
        # back a fake plan_id.  Callers (broadcast, evidence, receipts) rely
        # on the plan actually being in Mongo.  Surface the real error so
        # the operator can see WHY persistence failed.
        logger.error("plans/build persist FAILED: %s: %s",
                      type(exc).__name__, exc, exc_info=True)
        return {
            "error": f"persist failed: {type(exc).__name__}: {exc}",
            "attempted_plan_id": getattr(plan, "plan_id", None),
            "generated_at": _iso_now(),
        }


@api_router.get("/arbicore/execution/plans/{plan_id}")
async def v2_execution_plan_one(plan_id: str) -> Dict[str, Any]:
    try:
        plan = await _EXECUTION_PLANS_REPO.get(plan_id)
    except Exception:
        plan = None
    return {"plan": plan, "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/plans")
async def v2_execution_plans(strategy: Optional[str] = None,
                             chain: Optional[str] = None,
                             limit: int = 20) -> Dict[str, Any]:
    try:
        items = await _EXECUTION_PLANS_REPO.list_recent(strategy, chain, limit=limit)
    except Exception:
        items = []
    return {"items": items, "count": len(items),
            "strategy": strategy, "chain": chain,
            "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-6C · On-chain Simulation / Gas Oracle / MEV Router
# SHADOW-only.  Every endpoint below is READ-ONLY.  None broadcasts.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/execution/simulation/status")
async def v2_execution_simulation_status() -> Dict[str, Any]:
    """Simulator registry status — which backends are wired, which is
    the current default, and the read-only RPC allowlist."""
    return {**_SIMULATION_REGISTRY.status(), "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/gas")
async def v2_execution_gas(chain: str = "base",
                           steps: Optional[str] = None) -> Dict[str, Any]:
    """Live gas estimate for a canonical Borrow → Swap → Repay → Profit
    plan (or an operator-supplied step-kind sequence)."""
    if steps:
        step_kinds = [s.strip() for s in steps.split(",") if s.strip()]
    else:
        step_kinds = ["borrow", "swap", "repay", "profit"]
    try:
        est = await _GAS_ORACLE.estimate(chain=chain, step_kinds=step_kinds)
        return {"estimate": est.to_dict(), "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/mev/routers")
async def v2_execution_mev_routers(chain: str = "base",
                                    router: Optional[str] = None,
                                    protected: bool = True) -> Dict[str, Any]:
    """MEV router catalog + a routing decision for the requested chain.
    The decision is *shadow*-only (``would_broadcast=False`` invariant)."""
    catalog = _MEV_REGISTRY.catalog()
    try:
        decision = await _MEV_REGISTRY.route(router=router, chain=chain,
                                              protected=protected)
        catalog["current_decision"] = decision.to_dict()
    except Exception as exc:  # noqa: BLE001
        catalog["current_decision"] = None
        catalog["current_decision_error"] = f"{type(exc).__name__}: {exc}"
    catalog["generated_at"] = _iso_now()
    return catalog


@api_router.post("/arbicore/execution/plans/{plan_id}/simulate")
async def v2_execution_plan_simulate(plan_id: str,
                                      body: Optional[Dict[str, Any]] = None
                                      ) -> Dict[str, Any]:
    """Simulate a stored plan under a chosen simulator + gas oracle + MEV
    router.  All calls are READ-ONLY.  SHADOW invariant enforced.

    Body (all optional)::

        {
          "simulator": "noop" | "eth_call",
          "mev_router": "public_rpc" | "flashbots_protect" | ...,
          "protected": true
        }
    """
    b = body or {}
    plan_doc = await _EXECUTION_PLANS_REPO.get(plan_id)
    if not plan_doc:
        return {"error": f"plan '{plan_id}' not found",
                "generated_at": _iso_now()}
    # Mode gate — must be OBSERVE/PAPER/SHADOW (i.e. broadcast NOT allowed).
    strategy = plan_doc.get("strategy") or "flash_loan_arbitrage"
    mode_row = await _EXECUTION_MODE_REPO.get(strategy)
    current_mode = (mode_row or {}).get("mode") or default_mode_map().get(strategy) or "OBSERVE"
    if is_broadcast_allowed(current_mode):
        # Live modes go through the (Wave-6E) execution pipeline, NOT here.
        return {"error": f"strategy '{strategy}' is in mode '{current_mode}' — "
                          "simulation endpoint refuses live modes; use Wave 6E flow",
                "generated_at": _iso_now()}
    simulator_name = b.get("simulator")
    router_name = b.get("mev_router")
    protected = bool(b.get("protected", True))
    try:
        sim_result = await _SIMULATION_REGISTRY.simulate(plan_doc,
                                                          simulator=simulator_name)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"simulation failed: {type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}
    try:
        gas_est = await _GAS_ORACLE.estimate(
            chain=plan_doc.get("chain") or "base",
            step_kinds=[s.get("kind") or "" for s in plan_doc.get("steps") or []],
        )
        gas_est_d = gas_est.to_dict()
    except Exception:  # noqa: BLE001
        gas_est_d = None
    try:
        mev_decision = await _MEV_REGISTRY.route(
            router=router_name, chain=plan_doc.get("chain") or "base",
            protected=protected,
        )
        mev_d = mev_decision.to_dict()
    except Exception as exc:  # noqa: BLE001
        mev_d = {"error": f"{type(exc).__name__}: {exc}"}

    # Slippage recomputed deterministically from the persisted economics.
    hops = sum(1 for s in (plan_doc.get("steps") or []) if s.get("kind") == "swap")
    quoted_out = int((plan_doc.get("economics") or {}).get("effective_out_wei") or 0)
    slip_d = None
    if quoted_out > 0:
        slip_d = _SLIPPAGE_ESTIMATOR.estimate(
            quoted_output_wei=quoted_out, hops=max(1, hops)
        ).to_dict()

    return {
        "plan_id": plan_id,
        "mode": current_mode,
        "would_broadcast": False,
        "simulation": sim_result.to_dict(),
        "gas_estimate": gas_est_d,
        "mev_routing": mev_d,
        "slippage": slip_d,
        "generated_at": _iso_now(),
    }


# ---------------------------------------------------------------------------
# Wave-6D · Capital Allocation Policy
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/execution/capital-policy")
async def v2_execution_capital_policy_list() -> Dict[str, Any]:
    try:
        items = await _CAPITAL_POLICY_REPO.list_all()
    except Exception:
        items = []
    return {"items": items, "count": len(items),
            "defaults": dict(CAPITAL_DEFAULT_POLICY),
            "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/capital-policy/{strategy}")
async def v2_execution_capital_policy_one(strategy: str) -> Dict[str, Any]:
    try:
        row = await _CAPITAL_POLICY_REPO.get(strategy)
    except Exception:
        row = None
    return {"strategy": strategy, "policy": row,
            "defaults": dict(CAPITAL_DEFAULT_POLICY),
            "generated_at": _iso_now()}


@api_router.patch("/arbicore/execution/capital-policy/{strategy}")
async def v2_execution_capital_policy_update(strategy: str,
                                              body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        updated = await _CAPITAL_POLICY_REPO.update(
            strategy, body or {},
            actor=(body or {}).get("actor") or "operator",
            reason=(body or {}).get("reason") or "",
        )
        return {"ok": True, "strategy": strategy, "policy": updated,
                "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/capital-policy/{strategy}/evaluate")
async def v2_execution_capital_policy_evaluate(strategy: str,
                                                 body: Dict[str, Any]) -> Dict[str, Any]:
    """Preview a sizing decision for a proposed plan.  Read-only."""
    b = body or {}
    try:
        decision = await _CAPITAL_ALLOCATOR.evaluate(
            strategy=strategy,
            proposed_usd=float(b.get("proposed_usd") or 0),
            available_liquidity_usd=float(b.get("available_liquidity_usd") or 1_000_000.0),
            reference_capital_usd=float(b.get("reference_capital_usd") or 5_000.0),
            expected_net_profit_usd=(float(b["expected_net_profit_usd"])
                                     if "expected_net_profit_usd" in b else None),
        )
        return {"decision": decision.to_dict(), "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-6D · Kill Switch
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/execution/kill-switch")
async def v2_execution_kill_switch_state() -> Dict[str, Any]:
    try:
        state = await _KILL_SWITCH_REPO.state()
        return {"state": state.to_dict(), "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/kill-switch/engage")
async def v2_execution_kill_switch_engage(body: Dict[str, Any]) -> Dict[str, Any]:
    b = body or {}
    reason = (b.get("reason") or "").strip()
    if not reason:
        return {"ok": False, "error": "reason is required",
                "generated_at": _iso_now()}
    state = await _KILL_SWITCH_REPO.engage(reason=reason,
                                            actor=b.get("actor") or "operator")
    return {"ok": True, "state": state.to_dict(), "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/kill-switch/disengage")
async def v2_execution_kill_switch_disengage(body: Dict[str, Any]) -> Dict[str, Any]:
    b = body or {}
    reason = (b.get("reason") or "").strip()
    if not reason:
        return {"ok": False, "error": "reason is required",
                "generated_at": _iso_now()}
    state = await _KILL_SWITCH_REPO.disengage(reason=reason,
                                                actor=b.get("actor") or "operator")
    return {"ok": True, "state": state.to_dict(), "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/kill-switch/audit")
async def v2_execution_kill_switch_audit(limit: int = 50) -> Dict[str, Any]:
    try:
        items = await _KILL_SWITCH_REPO.audit_history(limit=limit)
    except Exception:
        items = []
    return {"items": items, "count": len(items), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-6D · Live Signer (gate ladder — never emits signed bytes)
# ---------------------------------------------------------------------------

@api_router.post("/arbicore/execution/plans/{plan_id}/sign")
async def v2_execution_plan_sign(plan_id: str,
                                   body: Optional[Dict[str, Any]] = None
                                   ) -> Dict[str, Any]:
    """Run the Wave-6D live-signer gate ladder against a stored plan.

    The receipt is the authoritative record of which gates would allow
    a broadcast — but **no signed bytes are ever emitted at this wave**,
    even when every gate passes.  Bytes-level encoding lands in Wave 6E."""
    b = body or {}
    plan_doc = await _EXECUTION_PLANS_REPO.get(plan_id)
    if not plan_doc:
        return {"error": f"plan '{plan_id}' not found",
                "generated_at": _iso_now()}
    try:
        receipt = await _LIVE_SIGNER.sign_plan(
            plan_doc,
            actor=b.get("actor") or "operator",
            available_liquidity_usd=float(b.get("available_liquidity_usd") or 1_000_000.0),
            reference_capital_usd=float(b.get("reference_capital_usd") or 5_000.0),
            expected_net_profit_usd=(float(b["expected_net_profit_usd"])
                                     if "expected_net_profit_usd" in b else None),
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}
    return {"receipt": receipt.to_dict(), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-6E · End-to-end Execution Certification
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/execution/certification/stages")
async def v2_execution_certification_stages() -> Dict[str, Any]:
    """Canonical list of pipeline stages the certifier evaluates."""
    return {"stages": list(PIPELINE_STAGES),
            "would_broadcast": False,
            "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/certification/run")
async def v2_execution_certification_run(body: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full Discovery → Planning → Simulation → Evidence
    pipeline for a proposed plan and return a certification report.

    The pipeline never broadcasts.  ``would_broadcast=False`` invariant
    is asserted at every stage."""
    b = body or {}
    try:
        report = await _EXECUTION_CERTIFIER.certify(
            strategy=b.get("strategy") or "flash_loan_arbitrage",
            chain=b.get("chain") or "base",
            borrow_token=b.get("borrow_token") or "",
            borrow_amount_wei=int(b.get("borrow_amount_wei") or 0),
            borrow_amount_usd=float(b.get("borrow_amount_usd") or 0),
            flash_loan_provider=b.get("flash_loan_provider") or "aave_v3",
            swap_hops=b.get("swap_hops") or [],
            signer_wallet_id=b.get("signer_wallet_id"),
            opportunity_id=b.get("opportunity_id"),
            expected_net_profit_usd=(float(b["expected_net_profit_usd"])
                                     if "expected_net_profit_usd" in b else None),
            quote_effective_out_wei=b.get("quote_effective_out_wei"),
            simulator=b.get("simulator"),
            mev_router=b.get("mev_router"),
        )
        r = report.to_dict()
        logger.info("certification/run returned plan_id=%s verdict=%s "
                     "(ephemeral — NOT persisted; use /plans/build for broadcast)",
                     r.get("plan_id"), r.get("verdict"))
        return {"report": r, "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-7A · Wallet Balance + Health
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/execution/wallets/{wallet_id}/balance")
async def v2_wallet_balance(wallet_id: str) -> Dict[str, Any]:
    wallet = await _WALLET_REGISTRY.get(wallet_id)
    if not wallet:
        return {"error": f"wallet '{wallet_id}' not found",
                "generated_at": _iso_now()}
    reading = await _WALLET_BALANCE_READER.read(
        chain=wallet.get("chain") or "base",
        address=wallet.get("address") or "",
    )
    return {"wallet_id": wallet_id, "reading": reading.to_dict(),
            "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/wallets/{wallet_id}/health")
async def v2_wallet_health(wallet_id: str,
                            strategy: str = "flash_loan_arbitrage",
                            min_gas_native: float = 0.001) -> Dict[str, Any]:
    report = await _WALLET_HEALTH_CARD.evaluate(
        wallet_id, strategy=strategy, min_gas_native=min_gas_native,
    )
    return {"report": report.to_dict(), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-7A · Continuous Discovery
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/execution/discovery/status")
async def v2_discovery_status() -> Dict[str, Any]:
    return {**_CONTINUOUS_DISCOVERY.status(),
            "default_universe_base": DEFAULT_UNIVERSE_BASE,
            "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/discovery/tick")
async def v2_discovery_tick() -> Dict[str, Any]:
    try:
        result = await _CONTINUOUS_DISCOVERY.tick_once()
        return {"ok": True, "result": result, "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/discovery/start")
async def v2_discovery_start() -> Dict[str, Any]:
    await _CONTINUOUS_DISCOVERY.start()
    return {"ok": True, "status": _CONTINUOUS_DISCOVERY.status(),
            "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/discovery/stop")
async def v2_discovery_stop() -> Dict[str, Any]:
    await _CONTINUOUS_DISCOVERY.stop()
    return {"ok": True, "status": _CONTINUOUS_DISCOVERY.status(),
            "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/opportunities")
async def v2_execution_opportunities_list(status: Optional[str] = None,
                                            chain: Optional[str] = None,
                                            limit: int = 50) -> Dict[str, Any]:
    try:
        items = await _DISCOVERY_REPO.list_recent(
            status=status, chain=chain, limit=limit,
        )
    except Exception:
        items = []
    return {"items": items, "count": len(items),
            "status_filter": status, "chain_filter": chain,
            "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/opportunities/{opportunity_id}")
async def v2_execution_opportunity_one(opportunity_id: str) -> Dict[str, Any]:
    row = await _DISCOVERY_REPO.get(opportunity_id)
    return {"opportunity": row, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Flash Loan LIMITED_LIVE · Operator Readiness Wizard (read-only aggregator).
# Composes existing repos + on-chain RPC checks into a single, tap-and-go
# view of every step the operator must clear before the first controlled
# broadcast.  ZERO new collections, ZERO mutating behaviour.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/wizard/state")
async def v2_wizard_state(strategy: str = "flash_loan_arbitrage",
                          chain: str = "base") -> Dict[str, Any]:
    try:
        return await build_wizard_state(
            kill_switch_repo=_KILL_SWITCH_REPO,
            mode_repo=_EXECUTION_MODE_REPO,
            wallet_registry=_WALLET_REGISTRY,
            secret_registry=_SECRET_REGISTRY,
            wallet_balance_reader=_WALLET_BALANCE_READER,
            certifier=_EXECUTION_CERTIFIER,
            strategy=strategy,
            chain=chain,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.get("/arbicore/executor/verify")
async def v2_executor_verify(address: Optional[str] = None,
                              chain: str = "base",
                              expected_owner: Optional[str] = None
                              ) -> Dict[str, Any]:
    try:
        return await verify_executor(address=address, chain=chain,
                                      expected_owner=expected_owner)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.get("/arbicore/rpc/check")
async def v2_rpc_check() -> Dict[str, Any]:
    try:
        return await check_rpc()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.get("/arbicore/post-trade/latest")
async def v2_post_trade_latest(limit: int = 5) -> Dict[str, Any]:
    try:
        return await latest_broadcast_receipts(
            plans_repo=_EXECUTION_PLANS_REPO,
            limit=max(1, min(int(limit), 25)),
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 10.6 · Flash Loan family prerequisite check
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/wizard/flash-loan-prereqs")
async def v2_flash_loan_prereqs(chain: str = "base") -> Dict[str, Any]:
    try:
        return await check_flash_loan_prereqs(
            kill_switch_repo=_KILL_SWITCH_REPO,
            mode_repo=_EXECUTION_MODE_REPO,
            wallet_registry=_WALLET_REGISTRY,
            secret_registry=_SECRET_REGISTRY,
            wallet_balance_reader=_WALLET_BALANCE_READER,
            scanner_repo=_SCANNER_CONFIG,
            network_repo=_NETWORK_CONFIG,
            chain=chain,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}


@api_router.get("/arbicore/wizard/journey")
async def v2_wizard_journey() -> Dict[str, Any]:
    """14-stage guided operator journey (composed from existing signals)."""
    try:
        ws = await build_wizard_state(
            kill_switch_repo=_KILL_SWITCH_REPO, mode_repo=_EXECUTION_MODE_REPO,
            wallet_registry=_WALLET_REGISTRY, secret_registry=_SECRET_REGISTRY,
            wallet_balance_reader=_WALLET_BALANCE_READER,
            certifier=_EXECUTION_CERTIFIER,
        )
        pr = await check_flash_loan_prereqs(
            kill_switch_repo=_KILL_SWITCH_REPO, mode_repo=_EXECUTION_MODE_REPO,
            wallet_registry=_WALLET_REGISTRY, secret_registry=_SECRET_REGISTRY,
            wallet_balance_reader=_WALLET_BALANCE_READER,
            scanner_repo=_SCANNER_CONFIG, network_repo=_NETWORK_CONFIG,
        )
        pt = await latest_broadcast_receipts(plans_repo=_EXECUTION_PLANS_REPO, limit=25)
        fl_family = await _SCANNER_CONFIG.get_family("flash_loan_arb")
        op_flags = await _OPERATIONAL_FLAGS.get()
        return await build_journey(
            wizard_state=ws, prereqs=pr, post_trade=pt,
            scanner_family_enabled=bool(fl_family.get("enabled")),
            operational_flags=op_flags,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}


@api_router.post("/arbicore/wizard/journey/mark-vps-ready")
async def v2_mark_vps_ready(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Operator affirms the system is validated and ready for VPS deploy."""
    b = body or {}
    try:
        cfg = await _OPERATIONAL_FLAGS.patch(
            {"feature_flags": {"vps_ready": True}},
            actor=b.get("actor") or "operator",
            reason=(b.get("reason") or "operator marked VPS-ready").strip(),
        )
        # Store both at root and feature_flags level for compat.
        await _CONFIG_REPO.apply(
            "operational_flags",
            patch={"vps_ready": True, "vps_ready_at": _iso_now()},
            actor=b.get("actor") or "operator",
            reason="mark VPS-ready",
        )
        return {"ok": True, "config": cfg, "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 10.1 · Network Configuration — persistent, UI-editable
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/settings/network")
async def v2_settings_network() -> Dict[str, Any]:
    try:
        cfg = await _NETWORK_CONFIG.get()
        draft = await _NETWORK_CONFIG.get_draft()
        return {"config": cfg, "draft": draft, "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/network/validate")
async def v2_settings_network_validate(patch: Dict[str, Any]) -> Dict[str, Any]:
    return {**_NETWORK_CONFIG.validate(patch or {}),
             "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/network/draft")
async def v2_settings_network_draft(patch: Dict[str, Any]) -> Dict[str, Any]:
    try:
        d = await _NETWORK_CONFIG.save_draft(patch or {}, actor="operator")
        return {"ok": True, "draft": d, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/network/apply")
async def v2_settings_network_apply(body: Optional[Dict[str, Any]] = None
                                     ) -> Dict[str, Any]:
    b = body or {}
    reason = (b.get("reason") or "").strip()
    try:
        cfg = await _NETWORK_CONFIG.apply(
            patch=b.get("patch"),
            actor=b.get("actor") or "operator",
            reason=reason,
        )
        # Phase 10.10 — hot-load the newly applied config into os.environ
        # so subsequent RPC health checks, gas queries, wallet balance
        # reads, executor verifications and broadcasts pick it up without
        # a backend restart.
        exported = await sync_env_from_network_config(_NETWORK_CONFIG)
        return {"ok": True, "config": cfg, "env_synced": sorted(exported.keys()),
                "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/network/rollback")
async def v2_settings_network_rollback(body: Optional[Dict[str, Any]] = None
                                        ) -> Dict[str, Any]:
    b = body or {}
    try:
        cfg = await _NETWORK_CONFIG.rollback(
            revision_id=b.get("revision_id"),
            actor=b.get("actor") or "operator",
            reason=(b.get("reason") or "").strip(),
        )
        # Phase 10.10 — same hot-load on rollback so runtime env tracks
        # whichever revision is now current.
        exported = await sync_env_from_network_config(_NETWORK_CONFIG)
        return {"ok": True, "config": cfg, "env_synced": sorted(exported.keys()),
                "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.get("/arbicore/settings/network/history")
async def v2_settings_network_history(limit: int = 50) -> Dict[str, Any]:
    items = await _NETWORK_CONFIG.history(limit=max(1, min(int(limit), 200)))
    return {"items": items, "count": len(items), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 10.2 · Generic config history across kinds
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/settings/config/history")
async def v2_config_history(kind: Optional[str] = None,
                             limit: int = 100) -> Dict[str, Any]:
    if kind:
        items = await _CONFIG_REPO.history(kind, limit=max(1, min(int(limit), 500)))
    else:
        items = await _CONFIG_REPO.all_history(limit=max(1, min(int(limit), 500)))
    return {"items": items, "count": len(items),
             "kind_filter": kind, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 10.3 · Telegram alerts
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/settings/telegram")
async def v2_settings_telegram() -> Dict[str, Any]:
    settings = await _TELEGRAM.get_settings()
    return {"config": settings, "generated_at": _iso_now()}


@api_router.put("/arbicore/settings/telegram")
async def v2_settings_telegram_update(body: Dict[str, Any]) -> Dict[str, Any]:
    b = body or {}
    try:
        settings = await _TELEGRAM.save_settings(
            enabled=b.get("enabled"),
            chat_id=b.get("chat_id"),
            rules=b.get("rules"),
            bot_token=b.get("bot_token"),
            actor=b.get("actor") or "operator",
            reason=(b.get("reason") or "").strip(),
        )
        return {"ok": True, "config": settings, "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                 "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/telegram/test")
async def v2_settings_telegram_test() -> Dict[str, Any]:
    result = await _TELEGRAM.send_test(actor="operator")
    return {**result, "generated_at": _iso_now()}


@api_router.get("/arbicore/settings/telegram/log")
async def v2_settings_telegram_log(limit: int = 50,
                                     kind: Optional[str] = None) -> Dict[str, Any]:
    items = await _TELEGRAM.history(limit=max(1, min(int(limit), 500)),
                                      kind=kind)
    return {"items": items, "count": len(items),
             "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/telegram/emit")
async def v2_settings_telegram_emit(body: Dict[str, Any]) -> Dict[str, Any]:
    """Manually emit an alert of the given ``kind`` — used by tests +
    integrations that want to notify without going through a live event
    (e.g. an operator-triggered heartbeat)."""
    b = body or {}
    kind = (b.get("kind") or "").strip()
    text = (b.get("text") or "").strip()
    if not kind or not text:
        return {"ok": False, "error": "kind and text are required",
                 "generated_at": _iso_now()}
    r = await _TELEGRAM.emit(kind=kind, text=text,
                              payload=b.get("payload"),
                              actor=b.get("actor") or "operator")
    return {**r, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 10.4 · Scanner Configuration (multi-family)
# Reuses the Phase-10 ConfigRepo substrate; defaults ported from the
# canonical arbicore/data/scanner_config_repo.py (v1.0.2 bundle).
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/settings/scanner")
async def v2_settings_scanner() -> Dict[str, Any]:
    snap = await _SCANNER_CONFIG.snapshot()
    # Attach drafts for the initial-load path.
    global_draft = await _SCANNER_CONFIG.get_global_draft()
    family_drafts: Dict[str, Any] = {}
    for fid in CANONICAL_FAMILIES:
        d = await _SCANNER_CONFIG.get_family_draft(fid)
        if d:
            family_drafts[fid] = d
    return {**snap,
             "global_draft": global_draft,
             "family_drafts": family_drafts}


@api_router.post("/arbicore/settings/scanner/global/validate")
async def v2_settings_scanner_global_validate(patch: Dict[str, Any]) -> Dict[str, Any]:
    r = await _SCANNER_CONFIG.validate_global_live(patch or {})
    return {**r, "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/global/draft")
async def v2_settings_scanner_global_draft(patch: Dict[str, Any]) -> Dict[str, Any]:
    try:
        d = await _SCANNER_CONFIG.save_global_draft(patch or {}, actor="operator")
        return {"ok": True, "draft": d, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/global/apply")
async def v2_settings_scanner_global_apply(body: Optional[Dict[str, Any]] = None
                                            ) -> Dict[str, Any]:
    b = body or {}
    try:
        cfg = await _SCANNER_CONFIG.apply_global(
            patch=b.get("patch"),
            actor=b.get("actor") or "operator",
            reason=(b.get("reason") or "").strip(),
        )
        return {"ok": True, "config": cfg, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/global/rollback")
async def v2_settings_scanner_global_rollback(body: Optional[Dict[str, Any]] = None
                                               ) -> Dict[str, Any]:
    b = body or {}
    try:
        cfg = await _SCANNER_CONFIG.rollback_global(
            revision_id=b.get("revision_id"),
            actor=b.get("actor") or "operator",
            reason=(b.get("reason") or "").strip(),
        )
        return {"ok": True, "config": cfg, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.get("/arbicore/settings/scanner/global/history")
async def v2_settings_scanner_global_history(limit: int = 50) -> Dict[str, Any]:
    items = await _SCANNER_CONFIG.global_history(limit=max(1, min(int(limit), 200)))
    return {"items": items, "count": len(items), "generated_at": _iso_now()}


# ----- Per-family endpoints -----

@api_router.get("/arbicore/settings/scanner/family/{family_id}")
async def v2_settings_scanner_family_get(family_id: str) -> Dict[str, Any]:
    if family_id not in CANONICAL_FAMILIES:
        return {"error": f"unknown family '{family_id}'",
                 "supported": list(CANONICAL_FAMILIES),
                 "generated_at": _iso_now()}
    cfg = await _SCANNER_CONFIG.get_family(family_id)
    draft = await _SCANNER_CONFIG.get_family_draft(family_id)
    return {"family": family_id, "config": cfg, "draft": draft,
             "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/family/{family_id}/validate")
async def v2_settings_scanner_family_validate(family_id: str,
                                                patch: Dict[str, Any]) -> Dict[str, Any]:
    r = _SCANNER_CONFIG.validate_family(family_id, patch or {})
    return {**r, "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/family/{family_id}/draft")
async def v2_settings_scanner_family_draft(family_id: str,
                                             patch: Dict[str, Any]) -> Dict[str, Any]:
    try:
        d = await _SCANNER_CONFIG.save_family_draft(family_id, patch or {},
                                                       actor="operator")
        return {"ok": True, "draft": d, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/family/{family_id}/apply")
async def v2_settings_scanner_family_apply(family_id: str,
                                             body: Optional[Dict[str, Any]] = None
                                             ) -> Dict[str, Any]:
    b = body or {}
    try:
        cfg = await _SCANNER_CONFIG.apply_family(
            family_id,
            patch=b.get("patch"),
            actor=b.get("actor") or "operator",
            reason=(b.get("reason") or "").strip(),
        )
        return {"ok": True, "config": cfg, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/family/{family_id}/rollback")
async def v2_settings_scanner_family_rollback(family_id: str,
                                                body: Optional[Dict[str, Any]] = None
                                                ) -> Dict[str, Any]:
    b = body or {}
    try:
        cfg = await _SCANNER_CONFIG.rollback_family(
            family_id,
            revision_id=b.get("revision_id"),
            actor=b.get("actor") or "operator",
            reason=(b.get("reason") or "").strip(),
        )
        return {"ok": True, "config": cfg, "generated_at": _iso_now()}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}


@api_router.get("/arbicore/settings/scanner/family/{family_id}/history")
async def v2_settings_scanner_family_history(family_id: str,
                                                limit: int = 50) -> Dict[str, Any]:
    items = await _SCANNER_CONFIG.family_history(
        family_id, limit=max(1, min(int(limit), 200)),
    )
    return {"items": items, "count": len(items), "generated_at": _iso_now()}


# ----- Runtime controls (map to global) -----

@api_router.post("/arbicore/settings/scanner/pause")
async def v2_settings_scanner_pause(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    b = body or {}
    cfg = await _SCANNER_CONFIG.pause(
        actor=b.get("actor") or "operator",
        reason=(b.get("reason") or "").strip(),
    )
    return {"ok": True, "config": cfg, "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/resume")
async def v2_settings_scanner_resume(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    b = body or {}
    cfg = await _SCANNER_CONFIG.resume(
        actor=b.get("actor") or "operator",
        reason=(b.get("reason") or "").strip(),
    )
    return {"ok": True, "config": cfg, "generated_at": _iso_now()}


@api_router.post("/arbicore/settings/scanner/reload")
async def v2_settings_scanner_reload(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    b = body or {}
    cfg = await _SCANNER_CONFIG.reload(
        actor=b.get("actor") or "operator",
        reason=(b.get("reason") or "").strip(),
    )
    return {"ok": True, "config": cfg, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-7C · Bytes-level calldata + LIMITED_LIVE broadcaster (6-gate)
# ---------------------------------------------------------------------------

@api_router.post("/arbicore/execution/plans/{plan_id}/calldata")
async def v2_plan_calldata(plan_id: str) -> Dict[str, Any]:
    """Encode the bytes-level calldata for a stored plan's borrow head.
    Read-only — no signing, no broadcast."""
    plan_doc = await _EXECUTION_PLANS_REPO.get(plan_id)
    if not plan_doc:
        return {"error": f"plan '{plan_id}' not found",
                "generated_at": _iso_now()}
    try:
        encoded = encode_plan_head_call(plan_doc)
        return {"plan_id": plan_id, "encoded_call": encoded.to_dict(),
                "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"plan_id": plan_id,
                "error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/plans/{plan_id}/broadcast")
async def v2_plan_broadcast(plan_id: str,
                              body: Optional[Dict[str, Any]] = None
                              ) -> Dict[str, Any]:
    """Run the 6-gate LIMITED_LIVE broadcast pipeline against a stored
    plan.  Every request goes through the full ladder + preflight; a
    real ``eth_sendRawTransaction`` fires ONLY when the body contains
    ``{"confirm": true}`` AND every gate passes.

    Body::

        {
          "confirm": bool,                       # required to submit
          "actor": "operator@handle",
          "expected_net_profit_usd": float       # optional; enables min-profit gate
        }
    """
    b = body or {}
    plan_doc = await _EXECUTION_PLANS_REPO.get(plan_id)
    if not plan_doc:
        return {"error": f"plan '{plan_id}' not found",
                "generated_at": _iso_now()}
    try:
        receipt = await _LIMITED_LIVE_BROADCASTER.broadcast_plan(
            plan_doc,
            actor=b.get("actor") or "operator",
            confirm=bool(b.get("confirm", False)),
            expected_net_profit_usd=(float(b["expected_net_profit_usd"])
                                     if "expected_net_profit_usd" in b else None),
        )
        return {"receipt": receipt.to_dict(), "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}

    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# P0-A · Opportunity Journal — read-side routes.
# The journal is written by the auto-executor and pipeline glue (P0-C / P0-D).
# These routes expose it to the operator UI and to the Learning Ledger tests.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/journal")
async def v2_journal_list(
    execution_status: Optional[str] = None,
    opportunity_type: Optional[str] = None,
    mode: Optional[str] = None,
    learning_label: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """List journal rows, newest-observed first. All filters optional."""
    try:
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        limit = 100
    entries = await _OPPORTUNITY_JOURNAL.list(
        execution_status=execution_status,
        opportunity_type=opportunity_type,
        mode=mode,
        learning_label=learning_label,
        limit=limit,
    )
    return {
        "items": [e.model_dump(mode="json") for e in entries],
        "count": len(entries),
        "as_of": _iso_now(),
    }


@api_router.get("/arbicore/journal/summary")
async def v2_journal_summary() -> Dict[str, Any]:
    """Aggregate counts + averages across the whole journal."""
    return await _OPPORTUNITY_JOURNAL.summary()


@api_router.get("/arbicore/journal/{opportunity_id}")
async def v2_journal_get(opportunity_id: str) -> Dict[str, Any]:
    """Return one journal row with its full event trail."""
    entry = await _OPPORTUNITY_JOURNAL.get(opportunity_id)
    if not entry:
        return {"error": f"journal entry '{opportunity_id}' not found",
                "generated_at": _iso_now()}
    return {"entry": entry.model_dump(mode="json"), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# P0-B · Learning Ledger routes.
# The ledger is the write-side bridge from the Journal into the existing
# CalibrationWorker + AdaptiveWeightsWorker. Emissions are idempotent —
# each journal row is consumed at most once.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/learning/ledger/status")
async def v2_ledger_status() -> Dict[str, Any]:
    """Ledger status — pending / consumed counts and last batch metrics."""
    return await _LEARNING_LEDGER.status()


@api_router.post("/arbicore/learning/ledger/emit")
async def v2_ledger_emit(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Consume pending terminal journal rows into training samples.

    Body (all optional):
        {"batch": int}   # default 100, max 500
    """
    body = body or {}
    try:
        batch = int(body.get("batch", 100))
    except (TypeError, ValueError):
        batch = 100
    batch = max(1, min(batch, 500))
    return await _LEARNING_LEDGER.emit_from_journal(batch=batch)


# ---------------------------------------------------------------------------
# P0-C · Pipeline route — evaluate one opportunity through the unified loop.
# This is the same coordinator the Autonomous Executor (P0-D) will call on
# every tick. Exposed as an HTTP route so operators + tests can invoke it
# directly on a single opportunity (useful for debugging discovery output).
# ---------------------------------------------------------------------------

@api_router.post("/arbicore/pipeline/evaluate")
async def v2_pipeline_evaluate(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Walk one opportunity through Discovery→Quote→Gas→Profit→Policy→
    Certification→(Shadow|Broadcast) and journal every stage.

    Body:
        {
            "opportunity": { ...DiscoveredOpportunity dict... },
            "strategy":       "flash_loan_arbitrage" (optional),
            "scanner_family": "flash_loan_arb" (optional)
        }
    """
    body = body or {}
    opp = body.get("opportunity") or {}
    if not isinstance(opp, dict) or not opp.get("opportunity_id"):
        return {"error": "opportunity.opportunity_id is required",
                "generated_at": _iso_now()}
    strategy = body.get("strategy")
    scanner_family = body.get("scanner_family")
    result = await _OPPORTUNITY_PIPELINE.evaluate(
        opp, strategy=strategy, scanner_family=scanner_family,
    )
    return {"result": result.to_dict(), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# P0-D · Autonomous Executor routes.
# The executor NEVER auto-promotes mode and NEVER broadcasts unless the
# operator has already promoted the strategy to LIMITED_LIVE / FULL_LIVE.
# Default deployment starts in SHADOW — every opportunity is discovered,
# quoted, gas-estimated, profit-evaluated, policy-checked, certified, and
# journaled with a complete historical audit trail. No chain writes occur.
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/auto-executor/status")
async def v2_autoexec_status() -> Dict[str, Any]:
    return _AUTO_EXECUTOR.status()


@api_router.post("/arbicore/auto-executor/start")
async def v2_autoexec_start() -> Dict[str, Any]:
    await _AUTO_EXECUTOR.start()
    return {"started": True, **_AUTO_EXECUTOR.status()}


@api_router.post("/arbicore/auto-executor/stop")
async def v2_autoexec_stop() -> Dict[str, Any]:
    await _AUTO_EXECUTOR.stop()
    return {"stopped": True, **_AUTO_EXECUTOR.status()}


@api_router.post("/arbicore/auto-executor/tick")
async def v2_autoexec_tick() -> Dict[str, Any]:
    """Force a single tick — useful for tests, debugging, and cron."""
    summary = await _AUTO_EXECUTOR.tick_once()
    return {"summary": summary, "generated_at": _iso_now()}




# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# v2.9.3 — Canonical authentication router (single-admin, cookie-based JWT).
#
# Historical context: `routes/auth.py`, `services/auth.py`, and `services/db.py`
# were introduced as the canonical auth surface in v1.0.0 but were left
# dormant in the v2.0.0 consolidation (see docs/RELEASE_NOTES_v2.9.3.md §2).
# This wire-up completes the activation without altering any other route.
#
# Provides:  /api/auth/{status,setup,login,logout,logout-all,me,refresh,
#            change-password}
# ---------------------------------------------------------------------------
try:
    from routes.auth import router as _canonical_auth_router
    app.include_router(_canonical_auth_router)
    logger.info("v2.9.3: canonical auth router mounted (/api/auth/*)")
except Exception:  # noqa: BLE001
    logger.exception(
        "v2.9.3: canonical auth router failed to import — "
        "/api/auth/{status,setup,change-password,logout-all,refresh} will be 404"
    )

@app.on_event("startup")
async def _start_calibration_worker():
    try:
        await _CALIBRATION_WORKER.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to start calibration worker: %s", exc)


# ---------------------------------------------------------------------------
# Sprint 1A — Market Intelligence Database (MID)
# ---------------------------------------------------------------------------
# Platform-wide persistent intelligence foundation.  Every MID row carries
# strategy-agnostic metadata (see docs/V2_PLATFORM_ROADMAP.md §P1-α).
# Producers wire through the façade in Sprint 1A; downstream sprints extend
# what each producer records.  Boot posture: writers ready, indexes ensured.
try:
    from arbicore.data.mid import (
        MidWriter, MidReader, ensure_indexes as _mid_ensure_indexes, DOMAINS as _MID_DOMAINS,
        make_meta as _mid_make_meta, get_registry as _mid_get_registry,
    )
    _MID_WRITER: Optional[MidWriter] = MidWriter(db)
    _MID_READER: Optional[MidReader] = MidReader(db)
except Exception:  # noqa: BLE001
    _MID_WRITER = None
    _MID_READER = None
    logger.exception("failed to construct MID writer/reader — endpoints will report unavailable")


@app.on_event("startup")
async def _mid_ensure_indexes_startup():
    """Sprint 1A — ensure MID indexes + TTL policies at every boot (idempotent)."""
    if _MID_WRITER is None:
        return
    try:
        summary = await _mid_ensure_indexes(db)
        logger.info("MID indexes ensured across %d collections", len(summary))
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to ensure MID indexes: %s", exc)


# ---------------------------------------------------------------------------
# v2.0.3 — Backend authentication (JWT · roles · seeded users)
# ---------------------------------------------------------------------------
try:
    from arbicore.auth import (
        ensure_seed_users as _auth_ensure_seed,
        authenticate as _auth_authenticate,
        issue_token as _auth_issue_token,
        decode_token as _auth_decode_token,
        record_session as _auth_record_session,
        revoke_session as _auth_revoke_session,
        is_session_revoked as _auth_is_revoked,
    )
    from fastapi import Header
    from jwt import ExpiredSignatureError, InvalidTokenError
    _AUTH_AVAILABLE = True
except Exception:  # noqa: BLE001
    _AUTH_AVAILABLE = False
    logger.exception("auth module unavailable — /api/auth/* will report 503")


@app.on_event("startup")
async def _auth_seed_startup():
    """v2.0.6 — surface the truthful seed summary at boot.

    Historical bug: the previous implementation always logged
    "seeded 2 default users" even when nothing was inserted.  We now
    call the refactored ``ensure_seed_users`` which returns a summary
    dict, and we log that summary verbatim so operators can see
    exactly what happened in Mongo.

    v2.9.3 — Gated OFF by default. The canonical auth router
    (``routes/auth.py``) uses the ``users`` collection with a first-run
    setup flow. Silently reseeding the legacy ``auth_users`` collection
    on every boot would mask reset flows on hosts that have migrated
    to the canonical store. Operators who still depend on the legacy
    admin/operator seed can opt in explicitly by setting the env var
    ``ARBICORE_LEGACY_AUTH_SEED=1``.
    """
    if not _AUTH_AVAILABLE:
        return
    if os.environ.get("ARBICORE_LEGACY_AUTH_SEED", "0").strip() != "1":
        logger.info(
            "v2.9.3: legacy auth seed skipped "
            "(ARBICORE_LEGACY_AUTH_SEED != '1'). "
            "Canonical auth (users collection) is authoritative."
        )
        return
    try:
        summary = await _auth_ensure_seed(db)
        # summary is guaranteed to be a dict; older stub versions
        # returned None, so we tolerate that shape for safety.
        if isinstance(summary, dict):
            logger.info(
                "auth: startup seed summary — db=%s coll=%s inserted=%s "
                "existed_before=%s skipped_existing=%s verified=%s ok=%s",
                summary.get("database"),
                summary.get("collection"),
                summary.get("inserted"),
                summary.get("existed_before"),
                summary.get("skipped_existing"),
                summary.get("verified"),
                summary.get("ok"),
            )
            if not summary.get("ok"):
                logger.error(
                    "auth: startup seed verification FAILED — "
                    "default users missing after seed routine"
                )
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to seed auth users: %s", exc)


async def _resolve_current_user(
    request: Optional[Request] = None,
    authorization: Optional[str] = None,
):
    """v2.9.3 — Unified auth resolver.

    Preferred path: the canonical cookie/bearer flow from ``services/auth.py``
    (single-admin, session_version-versioned, brute-force lockout).  This
    accepts either the ``access_token`` httpOnly cookie or an
    ``Authorization: Bearer <access_token>`` header — both are handled by
    ``services.auth.get_current_user``.

    Fallback path: the legacy bearer flow via ``arbicore.auth`` for anyone
    who still holds a token issued before v2.9.3.  Kept read-only; no new
    tokens are issued from this codepath because the Tree-B login endpoint
    was removed in v2.9.3.

    Returns ``None`` when neither path authenticates.  The returned dict
    shape is preserved from v2.0.3 so downstream call sites do not change:
    ``{"user_id", "username", "role", "jti"}``.
    """
    # ---- canonical path (cookie or bearer via services.auth) ----
    if request is not None:
        try:
            from services import auth as _canonical_auth  # local import to avoid boot cycles
            user = await _canonical_auth.get_current_user(request)
            return {
                "user_id":  user.get("id"),
                "username": user.get("username"),
                "role":     user.get("role"),
                "jti":      None,   # canonical uses session_version, not JTI
            }
        except HTTPException:
            pass
        except Exception:  # noqa: BLE001
            logger.exception("v2.9.3: canonical auth resolver crashed — falling back to legacy")
        if authorization is None:
            authorization = request.headers.get("Authorization")

    # ---- legacy bearer fallback (arbicore.auth) ----
    if not _AUTH_AVAILABLE or not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = _auth_decode_token(token)
    except ExpiredSignatureError:
        return None
    except InvalidTokenError:
        return None
    jti = payload.get("jti")
    if jti and await _auth_is_revoked(db, jti):
        return None
    return {
        "user_id": payload.get("sub"),
        "username": payload.get("username"),
        "role": payload.get("role"),
        "jti": jti,
    }


# ---------------------------------------------------------------------------
# v2.9.3 — Legacy Tree-B `/api/auth/*` endpoints removed.
#
# The four handlers that previously lived here (`auth_login`, `auth_logout`,
# `auth_me`, `auth_diagnostics`) were replaced by the canonical router
# `routes/auth.py`, mounted in the app-wiring block above.  Removing them is
# what unblocks `/api/auth/status` and `/api/auth/setup` because FastAPI
# keeps the first-registered handler for a given (method, path), and these
# would have collided on `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`.
#
# `_resolve_current_user` above still supports legacy bearer tokens for
# administrative endpoints elsewhere in this file (see call sites below),
# preserving read-only backward compatibility for tokens issued before v2.9.3.
# ---------------------------------------------------------------------------

@app.get("/api/arbicore/mid/status")
async def mid_status() -> Dict[str, Any]:
    """Sprint 1A — MID health + per-domain counts + last-write timestamps."""
    if _MID_READER is None:
        return {"available": False, "reason": "mid_reader_unavailable", "generated_at": _iso_now()}
    payload = await _MID_READER.status()
    payload.update({"available": True, "generated_at": _iso_now()})
    return payload


@app.get("/api/arbicore/mid/query/{domain}")
async def mid_query(domain: str,
                     strategy_type: Optional[str] = None,
                     opportunity_type: Optional[str] = None,
                     capital_source: Optional[str] = None,
                     chain: Optional[str] = None,
                     protocol: Optional[str] = None,
                     execution_mode: Optional[str] = None,
                     market_regime: Optional[str] = None,
                     ts_gte: Optional[str] = None,
                     ts_lte: Optional[str] = None,
                     limit: int = 100) -> Dict[str, Any]:
    """Sprint 1A — parameterised MID query surface with strategy-agnostic filters."""
    if _MID_READER is None:
        raise HTTPException(status_code=503, detail="mid_reader_unavailable")
    if domain not in _MID_DOMAINS:
        raise HTTPException(status_code=404, detail=f"unknown MID domain: {domain}")
    try:
        rows = await _MID_READER.query(
            domain, limit=limit,
            strategy_type=strategy_type, opportunity_type=opportunity_type,
            capital_source=capital_source, chain=chain, protocol=protocol,
            execution_mode=execution_mode, market_regime=market_regime,
            ts_gte=ts_gte, ts_lte=ts_lte,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "domain": domain,
        "count": len(rows),
        "filters": {
            "strategy_type": strategy_type, "opportunity_type": opportunity_type,
            "capital_source": capital_source, "chain": chain, "protocol": protocol,
            "execution_mode": execution_mode, "market_regime": market_regime,
            "ts_gte": ts_gte, "ts_lte": ts_lte, "limit": limit,
        },
        "rows": rows,
        "generated_at": _iso_now(),
    }


@app.get("/api/arbicore/mid/enums")
async def mid_enums() -> Dict[str, Any]:
    """Sprint 1A — enum registry snapshot + closed-enum flags."""
    reg = _mid_get_registry()
    snap = reg.snapshot()
    closed = {name: reg.is_closed(name) for name in snap}
    return {
        "enums": snap,
        "closed": closed,
        "generated_at": _iso_now(),
    }


# ---------------------------------------------------------------------------
# Sprint 1B-α — Intelligence Activation
# ---------------------------------------------------------------------------
# Wires the six previously-dormant intelligence engines through the MID
# evidence bridge.  Boot posture: engines instantiated at startup, each
# activation surfaced in ``/api/arbicore/intelligence/status``.  No scanner
# is activated in this wave; that ships in Sprint 1B-β.
try:
    from arbicore.intelligence.wave1b import activate_all as _intel_activate_all
    _INTEL_ACTIVATION = None  # populated by startup event below
    _INTEL_AVAILABLE = True
except Exception:  # noqa: BLE001
    _INTEL_ACTIVATION = None
    _INTEL_AVAILABLE = False
    logger.exception(
        "intelligence Wave 1B-α unavailable — /api/arbicore/intelligence/* "
        "will report 503"
    )


@app.on_event("startup")
async def _intelligence_activate_startup():
    """Sprint 1B-α — activate all six intelligence engines through MID."""
    global _INTEL_ACTIVATION
    if not _INTEL_AVAILABLE or _MID_WRITER is None:
        logger.warning(
            "intelligence: activation SKIPPED "
            "(available=%s, writer_ready=%s)",
            _INTEL_AVAILABLE, _MID_WRITER is not None,
        )
        return
    try:
        _INTEL_ACTIVATION = _intel_activate_all(_MID_WRITER)
        summary = _INTEL_ACTIVATION.registry.summary()
        logger.info(
            "intelligence: Wave 1B-α activation summary — "
            "active=%s errored=%s",
            summary.get("active"), summary.get("errored"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("intelligence: activation failed: %s", exc)


@app.get("/api/arbicore/intelligence/status")
async def intelligence_status() -> Dict[str, Any]:
    """Sprint 1B-α — per-engine activation state + MidEvidenceBridge stats."""
    if _INTEL_ACTIVATION is None:
        return {
            "available": False,
            "reason": "intelligence_not_activated",
            "generated_at": _iso_now(),
        }
    return {
        "available": True,
        "wave": "1B-α",
        **_INTEL_ACTIVATION.summary(),
        "generated_at": _iso_now(),
    }


@app.get("/api/arbicore/intelligence/{engine_id}/snapshot")
async def intelligence_snapshot(engine_id: str) -> Dict[str, Any]:
    """Sprint 1B-α — return the current public state of one engine."""
    if _INTEL_ACTIVATION is None:
        raise HTTPException(
            status_code=503, detail="intelligence_not_activated")
    status = _INTEL_ACTIVATION.registry.get(engine_id)
    if status is None:
        raise HTTPException(
            status_code=404, detail=f"unknown engine: {engine_id}")
    return {
        "engine": status.to_dict(),
        **status.snapshot(),
        "generated_at": _iso_now(),
    }


# ---------------------------------------------------------------------------
# Sprint 1B-β — Scanner Activation (SHADOW MODE)
# ---------------------------------------------------------------------------
try:
    from arbicore.scanners.wave1b import activate_scanners as _scanner_activate
    _SCANNER_ACTIVATION = None  # populated by startup event below
    _SCANNER_AVAILABLE = True
except Exception:  # noqa: BLE001
    _SCANNER_ACTIVATION = None
    _SCANNER_AVAILABLE = False
    logger.exception(
        "scanners Wave 1B-β unavailable — /api/arbicore/scanners/* "
        "will report 503"
    )


@app.on_event("startup")
async def _scanners_activate_startup():
    """Sprint 1B-β — register shadow scanners (DORMANT boot)."""
    global _SCANNER_ACTIVATION
    if (not _SCANNER_AVAILABLE
            or _MID_WRITER is None or _MID_READER is None):
        logger.warning(
            "scanners: activation SKIPPED "
            "(available=%s, writer=%s, reader=%s)",
            _SCANNER_AVAILABLE,
            _MID_WRITER is not None,
            _MID_READER is not None,
        )
        return
    try:
        _SCANNER_ACTIVATION = _scanner_activate(_MID_WRITER, _MID_READER)
        summary = _SCANNER_ACTIVATION.registry.summary()
        logger.info(
            "scanners: Wave 1B-β activation summary — count=%d "
            "running=%s errored=%s (all boot DORMANT)",
            summary.get("scanner_count"),
            summary.get("running"),
            summary.get("errored"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("scanners: activation failed: %s", exc)


@app.get("/api/arbicore/scanners/status")
async def scanners_status() -> Dict[str, Any]:
    """Sprint 1B-β — per-scanner activation + runtime state + bridge stats.

    Also includes the intelligence pipeline totals so operators can see the
    full ``scanners → MidEvidenceBridge → engines`` throughput in one call.
    """
    if _SCANNER_ACTIVATION is None:
        return {
            "available": False,
            "reason": "scanners_not_activated",
            "generated_at": _iso_now(),
        }
    payload = {
        "available": True,
        "wave": "1B-β",
        "mode": "shadow",
        **_SCANNER_ACTIVATION.summary(),
        "generated_at": _iso_now(),
    }
    if _INTEL_ACTIVATION is not None:
        payload["intelligence_bridge_stats"] = (
            _INTEL_ACTIVATION.bridge.stats.to_dict())
    return payload


@app.post("/api/arbicore/scanners/{scanner_id}/start")
async def scanner_start(
    scanner_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """Sprint 1B-β — operator-controlled start (admin OR operator)."""
    if _SCANNER_ACTIVATION is None:
        raise HTTPException(
            status_code=503, detail="scanners_not_activated")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx:
        raise HTTPException(status_code=401, detail="not_authenticated")
    if ctx.get("role") not in ("admin", "operator"):
        raise HTTPException(
            status_code=403, detail="admin_or_operator_only")
    adapter = _SCANNER_ACTIVATION.get_adapter(scanner_id)
    if adapter is None:
        raise HTTPException(
            status_code=404, detail=f"unknown scanner: {scanner_id}")
    result = await adapter.start()
    logger.info(
        "scanners: START scanner_id=%s by=%s result=%s",
        scanner_id, ctx.get("username"), result,
    )
    return {"scanner_id": scanner_id, "mode": "shadow", **result,
            "generated_at": _iso_now()}


@app.post("/api/arbicore/scanners/{scanner_id}/stop")
async def scanner_stop(
    scanner_id: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    if _SCANNER_ACTIVATION is None:
        raise HTTPException(
            status_code=503, detail="scanners_not_activated")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx:
        raise HTTPException(status_code=401, detail="not_authenticated")
    if ctx.get("role") not in ("admin", "operator"):
        raise HTTPException(
            status_code=403, detail="admin_or_operator_only")
    adapter = _SCANNER_ACTIVATION.get_adapter(scanner_id)
    if adapter is None:
        raise HTTPException(
            status_code=404, detail=f"unknown scanner: {scanner_id}")
    result = await adapter.stop()
    logger.info(
        "scanners: STOP scanner_id=%s by=%s result=%s",
        scanner_id, ctx.get("username"), result,
    )
    return {"scanner_id": scanner_id, **result,
            "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 2 — Opportunity Lifetime Intelligence (v2.2.0)
# ---------------------------------------------------------------------------
try:
    from arbicore.intelligence.wave2 import (
        OpportunityLifetimeTracker as _LifetimeTracker,
        LifetimeSweeper as _LifetimeSweeper,
        load_config_from_env as _load_lifetime_cfg,
    )
    _LIFETIME_AVAILABLE = True
except Exception:  # noqa: BLE001
    _LIFETIME_AVAILABLE = False
    logger.exception(
        "Phase 2 lifetime tracker unavailable — /api/arbicore/lifetime/* "
        "will report 503"
    )

_LIFETIME_TRACKER: Optional[Any] = None
_LIFETIME_SWEEPER: Optional[Any] = None


@app.on_event("startup")
async def _lifetime_activate_startup():
    """Phase 2 — construct the lifetime tracker, wire it into the
    scanner bridge, and start the background sweeper."""
    global _LIFETIME_TRACKER, _LIFETIME_SWEEPER
    if (not _LIFETIME_AVAILABLE or _MID_WRITER is None
            or _SCANNER_ACTIVATION is None):
        logger.warning(
            "lifetime: activation SKIPPED "
            "(available=%s, writer=%s, scanner_activation=%s)",
            _LIFETIME_AVAILABLE, _MID_WRITER is not None,
            _SCANNER_ACTIVATION is not None,
        )
        return
    try:
        cfg = _load_lifetime_cfg()
        _LIFETIME_TRACKER = _LifetimeTracker(db=db, writer=_MID_WRITER,
                                              config=cfg)
        await _LIFETIME_TRACKER.ensure_indexes()
        _SCANNER_ACTIVATION.bridge.set_lifetime_tracker(_LIFETIME_TRACKER)

        _LIFETIME_SWEEPER = _LifetimeSweeper(_LIFETIME_TRACKER, cfg)
        await _LIFETIME_SWEEPER.start()   # boots ACTIVE — status decay
                                          # must happen even if no
                                          # scanner is running.
        logger.info(
            "lifetime: Phase 2 activated — tracker wired into scanner "
            "bridge, sweeper started (interval=%.1fs, active=%.0fs, "
            "stale=%.0fs)",
            cfg.sweeper_interval_seconds, cfg.active_seconds,
            cfg.stale_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("lifetime: activation failed: %s", exc)


@app.on_event("shutdown")
async def _lifetime_shutdown():
    if _LIFETIME_SWEEPER is not None:
        try:
            await _LIFETIME_SWEEPER.stop()
        except Exception:  # noqa: BLE001
            logger.exception("lifetime sweeper shutdown failed")


@app.get("/api/arbicore/lifetime/status")
async def lifetime_status() -> Dict[str, Any]:
    """Phase 2 — aggregate status counts + tracker + sweeper stats."""
    if _LIFETIME_TRACKER is None:
        return {"available": False,
                "reason": "lifetime_not_activated",
                "generated_at": _iso_now()}
    payload = await _LIFETIME_TRACKER.status_summary()
    payload.update({
        "available": True,
        "tracker_stats": _LIFETIME_TRACKER.stats.to_dict(),
        "sweeper_stats": (_LIFETIME_SWEEPER.stats
                           if _LIFETIME_SWEEPER is not None else None),
        "sweeper_running": (_LIFETIME_SWEEPER.is_running()
                             if _LIFETIME_SWEEPER is not None else False),
        "generated_at": _iso_now(),
    })
    return payload


@app.get("/api/arbicore/lifetime/recent")
async def lifetime_recent(
    limit: int = 50,
    status: Optional[str] = None,
    opportunity_type: Optional[str] = None,
) -> Dict[str, Any]:
    if _LIFETIME_TRACKER is None:
        raise HTTPException(status_code=503,
                             detail="lifetime_not_activated")
    limit = max(1, min(int(limit), 500))
    rows = await _LIFETIME_TRACKER.list_recent(
        limit=limit, status=status, opportunity_type=opportunity_type)
    return {"count": len(rows), "rows": rows,
            "generated_at": _iso_now()}


@app.get("/api/arbicore/lifetime/{opp_id}")
async def lifetime_by_opp(opp_id: str) -> Dict[str, Any]:
    if _LIFETIME_TRACKER is None:
        raise HTTPException(status_code=503,
                             detail="lifetime_not_activated")
    row = await _LIFETIME_TRACKER.get(opp_id)
    if row is None:
        raise HTTPException(status_code=404,
                             detail=f"unknown opp_id: {opp_id}")
    return {"row": row, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 3 — Opportunity Memory & Learning (v2.3.0)
# ---------------------------------------------------------------------------
try:
    from arbicore.intelligence.wave3 import OpportunityMemory as _Memory
    _MEMORY: Optional[Any] = _Memory(db)
    _MEMORY_AVAILABLE = True
    logger.info("memory: Phase 3 activated — read-side aggregator ready")
except Exception:  # noqa: BLE001
    _MEMORY = None
    _MEMORY_AVAILABLE = False
    logger.exception("Phase 3 memory unavailable")


@app.get("/api/arbicore/memory/summary")
async def memory_summary() -> Dict[str, Any]:
    if _MEMORY is None:
        raise HTTPException(status_code=503, detail="memory_not_activated")
    return {**await _MEMORY.summary(), "generated_at": _iso_now()}


@app.get("/api/arbicore/memory/recurring")
async def memory_recurring(
    limit: int = 20, min_recurrence: int = 1,
    opportunity_type: Optional[str] = None,
) -> Dict[str, Any]:
    if _MEMORY is None:
        raise HTTPException(status_code=503, detail="memory_not_activated")
    rows = await _MEMORY.top_recurring(
        limit=max(1, min(int(limit), 200)),
        min_recurrence=max(0, int(min_recurrence)),
        opportunity_type=opportunity_type,
    )
    return {"count": len(rows), "rows": rows,
            "generated_at": _iso_now()}


@app.get("/api/arbicore/memory/persistent")
async def memory_persistent(limit: int = 20,
                             min_observations: int = 2) -> Dict[str, Any]:
    if _MEMORY is None:
        raise HTTPException(status_code=503, detail="memory_not_activated")
    rows = await _MEMORY.most_persistent(
        limit=max(1, min(int(limit), 200)),
        min_observations=max(1, int(min_observations)))
    return {"count": len(rows), "rows": rows,
            "generated_at": _iso_now()}


@app.get("/api/arbicore/memory/confidence/{opp_id}")
async def memory_confidence(opp_id: str, limit: int = 100) -> Dict[str, Any]:
    if _MEMORY is None:
        raise HTTPException(status_code=503, detail="memory_not_activated")
    return {**await _MEMORY.confidence_history(
        opp_id, limit=max(1, min(int(limit), 500))),
        "generated_at": _iso_now()}


@app.get("/api/arbicore/memory/profitability/{opp_id}")
async def memory_profitability(opp_id: str,
                                limit: int = 100) -> Dict[str, Any]:
    if _MEMORY is None:
        raise HTTPException(status_code=503, detail="memory_not_activated")
    return {**await _MEMORY.profitability_history(
        opp_id, limit=max(1, min(int(limit), 500))),
        "generated_at": _iso_now()}


@app.get("/api/arbicore/memory/routes")
async def memory_routes(limit: int = 20,
                         chain: Optional[str] = None) -> Dict[str, Any]:
    if _MEMORY is None:
        raise HTTPException(status_code=503, detail="memory_not_activated")
    rows = await _MEMORY.route_quality(
        limit=max(1, min(int(limit), 200)), chain=chain)
    return {"count": len(rows), "rows": rows,
            "generated_at": _iso_now()}


@app.get("/api/arbicore/memory/venues")
async def memory_venues(limit: int = 50) -> Dict[str, Any]:
    if _MEMORY is None:
        raise HTTPException(status_code=503, detail="memory_not_activated")
    rows = await _MEMORY.venue_quality(
        limit=max(1, min(int(limit), 200)))
    return {"count": len(rows), "rows": rows,
            "generated_at": _iso_now()}


@app.get("/api/arbicore/memory/regime")
async def memory_regime(hours: float = 24.0,
                         limit: int = 200) -> Dict[str, Any]:
    if _MEMORY is None:
        raise HTTPException(status_code=503, detail="memory_not_activated")
    return {**await _MEMORY.regime_history(
        hours=float(hours), limit=max(1, min(int(limit), 500))),
        "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 5 — Provider Registry (vendor-independent abstraction layer)
# ---------------------------------------------------------------------------
try:
    from arbicore.providers import ProviderRegistry as _ProviderRegistry
    from arbicore.providers.bootstrap import bootstrap as _bootstrap_providers
    from arbicore.wallets import NoOpWalletProvider, EnvSecretProvider
    _PROVIDER_REGISTRY = _ProviderRegistry()
    _PROVIDER_REGISTRY.register(NoOpWalletProvider(), priority=1000)
    _PROVIDER_REGISTRY.register(EnvSecretProvider(),  priority=1000)
    _PROVIDER_BOOTSTRAP_SUMMARY = _bootstrap_providers(_PROVIDER_REGISTRY)
    _PROVIDERS_AVAILABLE = True
    logger.info(
        "providers: Phase 5 registry activated (%d providers total)",
        len(_PROVIDER_REGISTRY.list(include_tripped=True)))
except Exception:  # noqa: BLE001
    _PROVIDER_REGISTRY = None
    _PROVIDER_BOOTSTRAP_SUMMARY = None
    _PROVIDERS_AVAILABLE = False
    logger.exception("Phase 5 provider registry unavailable")


@app.get("/api/arbicore/providers/status")
async def providers_status() -> Dict[str, Any]:
    if _PROVIDER_REGISTRY is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True, **_PROVIDER_REGISTRY.snapshot(),
            "bootstrap": _PROVIDER_BOOTSTRAP_SUMMARY,
            "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 8 — Safety infrastructure (kill switch / capital / audit)
# ---------------------------------------------------------------------------
try:
    from arbicore.safety import (
        load_policy_from_env as _load_policy,
        KillSwitch as _KillSwitch,
        CapitalAllocationPolicy as _CapPolicy,
        ApprovalGate as _ApprovalGate,
        AuditLog as _AuditLog,
    )
    _POLICY = _load_policy()
    _KILL = _KillSwitch(_POLICY)
    _CAPITAL = _CapPolicy(_POLICY)
    _APPROVAL = _ApprovalGate(_POLICY, _KILL)
    _AUDIT = None                     # bound after MID writer boots
    _SAFETY_AVAILABLE = True
    logger.info(
        "safety: Phase 8 activated — kill.engaged=%s live_exec=%s "
        "max_per_trade_usd=%.2f",
        _KILL.is_engaged(), _POLICY.live_execution_enabled,
        _POLICY.max_per_trade_usd)
except Exception:  # noqa: BLE001
    _POLICY = _KILL = _CAPITAL = _APPROVAL = _AUDIT = None
    _SAFETY_AVAILABLE = False
    logger.exception("Phase 8 safety infrastructure unavailable")


# ---------------------------------------------------------------------------
# Phase 6 — Paper Opportunity Engine
# ---------------------------------------------------------------------------
try:
    from arbicore.paper import PaperEngine as _PaperEngine
    _PAPER_ENGINE = None
    _PAPER_AVAILABLE = True
except Exception:  # noqa: BLE001
    _PAPER_ENGINE = None
    _PAPER_AVAILABLE = False
    logger.exception("Phase 6 paper engine unavailable")


@app.on_event("startup")
async def _phase6_8_activate_startup():
    """Bind the audit log + paper engine to the running MidWriter."""
    global _AUDIT, _PAPER_ENGINE
    if _MID_WRITER is None:
        return
    if _SAFETY_AVAILABLE and _AUDIT is None:
        _AUDIT = _AuditLog(_MID_WRITER)
        await _AUDIT.log(event="boot", by="server",
                          payload={"live_execution_enabled":
                                   _POLICY.live_execution_enabled,
                                   "kill_engaged": _KILL.is_engaged()})
    if _PAPER_AVAILABLE and _PAPER_ENGINE is None:
        _PAPER_ENGINE = _PaperEngine(
            _MID_WRITER, kill_switch=_KILL, capital_policy=_CAPITAL)
        logger.info("paper: Phase 6 engine bound to MidWriter")


# ---------------------------------------------------------------------------
# Stage 2 (v2.5.0) — Live Market Intelligence scanner
# ---------------------------------------------------------------------------
try:
    from arbicore.scanners.live import LiveMarketScanner as _LiveScanner
    _LIVE_SCANNER: Optional[Any] = None
    _LIVE_AVAILABLE = True
except Exception:  # noqa: BLE001
    _LIVE_SCANNER = None
    _LIVE_AVAILABLE = False
    logger.exception("live_market scanner unavailable")


@app.on_event("startup")
async def _live_market_startup():
    """Bind the Live Market Scanner once MID + registry + paper are ready.

    Autostart is controlled by ``LIVE_MARKET_AUTOSTART`` (default: '1').
    The scanner runs in OBSERVE mode — no signing, no trading. Safety
    gates (kill switch + capital caps) still apply to the paper engine
    downstream.
    """
    global _LIVE_SCANNER
    if not _LIVE_AVAILABLE:
        return
    if (_MID_WRITER is None or _MID_READER is None
            or _SCANNER_ACTIVATION is None
            or _PROVIDER_REGISTRY is None):
        return
    if _LIVE_SCANNER is not None:
        return
    _LIVE_SCANNER = _LiveScanner(
        registry=_PROVIDER_REGISTRY,
        bridge=_SCANNER_ACTIVATION.bridge,
        mid_reader=_MID_READER,
        paper_engine=_PAPER_ENGINE,
        tick_interval_s=float(os.environ.get(
            "LIVE_TICK_INTERVAL_SECONDS", "15") or 15),
        min_spread_bps=float(os.environ.get(
            "LIVE_MIN_SPREAD_BPS", "5") or 5),
        notional_usd=float(os.environ.get(
            "LIVE_QUOTE_NOTIONAL_USD", "10000") or 10000),
    )
    if os.environ.get("LIVE_MARKET_AUTOSTART", "1") == "1":
        await _LIVE_SCANNER.start()
        logger.info("live_market: autostarted")


@app.on_event("shutdown")
async def _live_market_shutdown():
    if _LIVE_SCANNER is not None and _LIVE_SCANNER.is_running():
        await _LIVE_SCANNER.stop()


@app.get("/api/arbicore/live/status")
async def live_status() -> Dict[str, Any]:
    if _LIVE_SCANNER is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True,
            "running": _LIVE_SCANNER.is_running(),
            "stats": _LIVE_SCANNER.stats,
            "generated_at": _iso_now()}


@app.post("/api/arbicore/live/start")
async def live_start(request: Request, authorization: Optional[str] = Header(default=None)):
    if _LIVE_SCANNER is None:
        raise HTTPException(status_code=503, detail="live_market_unavailable")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx or ctx.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403,
                             detail="admin_or_operator_only")
    return await _LIVE_SCANNER.start()


@app.post("/api/arbicore/live/stop")
async def live_stop(request: Request, authorization: Optional[str] = Header(default=None)):
    if _LIVE_SCANNER is None:
        raise HTTPException(status_code=503, detail="live_market_unavailable")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx or ctx.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403,
                             detail="admin_or_operator_only")
    return await _LIVE_SCANNER.stop()


@app.get("/api/arbicore/live/prices")
async def live_prices() -> Dict[str, Any]:
    """Latest cross-venue price snapshot for every scanned symbol."""
    if _LIVE_SCANNER is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True,
            "prices": _LIVE_SCANNER.last_prices,
            "generated_at": _iso_now()}


@app.get("/api/arbicore/live/opportunities")
async def live_opportunities(limit: int = 25) -> Dict[str, Any]:
    """Recent live opportunities from MID (cex_spot_arbitrage & friends)."""
    if _MID_READER is None:
        return {"available": False, "generated_at": _iso_now()}
    try:
        rows = await _MID_READER.query("opportunities", limit=int(limit))
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc),
                "generated_at": _iso_now()}
    return {"available": True, "count": len(rows), "opportunities": rows,
            "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Stage 3 (v2.6.0) — Cross-venue scanners (CEX↔DEX + DEX↔DEX)
# ---------------------------------------------------------------------------
try:
    from arbicore.scanners.live.cross import CexDexScanner, DexDexScanner
    _CROSS_AVAILABLE = True
except Exception:  # noqa: BLE001
    _CROSS_AVAILABLE = False
    CexDexScanner = DexDexScanner = None  # type: ignore
    logger.exception("cross scanner import failed")

_CEX_DEX_SCANNER: Optional[Any] = None
_DEX_DEX_SCANNER: Optional[Any] = None


@app.on_event("startup")
async def _cross_scanner_startup():
    global _CEX_DEX_SCANNER, _DEX_DEX_SCANNER
    if not _CROSS_AVAILABLE:
        return
    if (_MID_WRITER is None or _MID_READER is None
            or _SCANNER_ACTIVATION is None
            or _PROVIDER_REGISTRY is None):
        return

    common = dict(
        registry=_PROVIDER_REGISTRY,
        bridge=_SCANNER_ACTIVATION.bridge,
        mid_reader=_MID_READER,
        paper_engine=_PAPER_ENGINE,
        tick_interval_s=float(os.environ.get(
            "CROSS_TICK_INTERVAL_SECONDS", "25") or 25),
        min_net_bps=float(os.environ.get(
            "CROSS_MIN_NET_BPS", "8") or 8),
        notional_usd=float(os.environ.get(
            "CROSS_NOTIONAL_USD", "10000") or 10000),
    )
    if _CEX_DEX_SCANNER is None:
        _CEX_DEX_SCANNER = CexDexScanner(**common)
        if os.environ.get("CROSS_AUTOSTART", "1") == "1":
            await _CEX_DEX_SCANNER.start()
            logger.info("live_cex_dex: autostarted")
    if _DEX_DEX_SCANNER is None:
        _DEX_DEX_SCANNER = DexDexScanner(**common)
        if os.environ.get("CROSS_AUTOSTART", "1") == "1":
            await _DEX_DEX_SCANNER.start()
            logger.info("live_dex_dex: autostarted")


@app.on_event("shutdown")
async def _cross_scanner_shutdown():
    for s in (_CEX_DEX_SCANNER, _DEX_DEX_SCANNER):
        if s is not None and s.is_running():
            await s.stop()


@app.get("/api/arbicore/scanners/cross/status")
async def cross_scanners_status() -> Dict[str, Any]:
    def _s(sc):
        if sc is None:
            return {"available": False}
        return {"available": True, "running": sc.is_running(),
                 "stats": sc.stats,
                 "scanner_id": sc.scanner_id}
    return {"cex_dex": _s(_CEX_DEX_SCANNER),
             "dex_dex": _s(_DEX_DEX_SCANNER),
             "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Stage 3 (v2.6.0) — Validation framework
# ---------------------------------------------------------------------------
try:
    from arbicore.validation import ValidationReporter
    _VALIDATION_AVAILABLE = True
except Exception:  # noqa: BLE001
    _VALIDATION_AVAILABLE = False
    ValidationReporter = None  # type: ignore

_VALIDATION_REPORTER: Optional[Any] = None


def _all_live_scanners():
    return [s for s in (_LIVE_SCANNER, _CEX_DEX_SCANNER, _DEX_DEX_SCANNER)
             if s is not None]


@app.on_event("startup")
async def _validation_startup():
    global _VALIDATION_REPORTER
    if _VALIDATION_AVAILABLE and _MID_READER is not None:
        _VALIDATION_REPORTER = ValidationReporter(_MID_READER)


@app.get("/api/arbicore/validation/summary")
async def validation_summary() -> Dict[str, Any]:
    if _VALIDATION_REPORTER is None or _PROVIDER_REGISTRY is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True,
             **(await _VALIDATION_REPORTER.summary(
                 scanners=_all_live_scanners(),
                 registry=_PROVIDER_REGISTRY)),
             }


@app.get("/api/arbicore/validation/recurrence")
async def validation_recurrence(limit: int = 500) -> Dict[str, Any]:
    if _VALIDATION_REPORTER is None:
        return {"available": False}
    return {"available": True,
             **(await _VALIDATION_REPORTER.opportunity_recurrence(limit=limit))}


@app.get("/api/arbicore/validation/calibration")
async def validation_calibration(limit: int = 500) -> Dict[str, Any]:
    if _VALIDATION_REPORTER is None:
        return {"available": False}
    return {"available": True,
             **(await _VALIDATION_REPORTER.confidence_calibration(limit=limit))}


@app.get("/api/arbicore/validation/venue_ranking")
async def validation_venue_ranking(limit: int = 500) -> Dict[str, Any]:
    if _VALIDATION_REPORTER is None:
        return {"available": False}
    return {"available": True,
             **(await _VALIDATION_REPORTER.venue_ranking(limit=limit))}


@app.get("/api/arbicore/validation/regime")
async def validation_regime(limit: int = 500) -> Dict[str, Any]:
    if _VALIDATION_REPORTER is None:
        return {"available": False}
    return {"available": True,
             **(await _VALIDATION_REPORTER.regime_analysis(limit=limit))}


# ---------------------------------------------------------------------------
# Stage 4 (v2.6.0) — Flash-Loan Operator Journey (dry-run only)
# ---------------------------------------------------------------------------
try:
    from arbicore.flashloan import FlashLoanOperatorJourney
    _FLJ_AVAILABLE = True
except Exception:  # noqa: BLE001
    _FLJ_AVAILABLE = False
    FlashLoanOperatorJourney = None  # type: ignore

_FL_JOURNEY: Optional[Any] = None


@app.on_event("startup")
async def _flj_startup():
    global _FL_JOURNEY
    if not _FLJ_AVAILABLE:
        return
    if (_PROVIDER_REGISTRY is None or _KILL is None
            or _CAPITAL is None or _MID_WRITER is None):
        return
    _FL_JOURNEY = FlashLoanOperatorJourney(
        registry=_PROVIDER_REGISTRY,
        kill_switch=_KILL,
        capital_policy=_CAPITAL,
        approval_gate=_APPROVAL,
        mid_writer=_MID_WRITER,
    )
    logger.info("flashloan.operator_journey: initialised (dry-run only)")


@app.post("/api/arbicore/flashloan/journey/run")
async def flj_run(opp: Dict[str, Any],
                    request: Request,
                    authorization: Optional[str] = Header(default=None)):
    if _FL_JOURNEY is None:
        raise HTTPException(status_code=503,
                             detail="flashloan_journey_unavailable")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx or ctx.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403,
                             detail="admin_or_operator_only")
    return await _FL_JOURNEY.run(opp)


@app.get("/api/arbicore/flashloan/journey/status")
async def flj_status() -> Dict[str, Any]:
    return {"available": _FL_JOURNEY is not None,
             "ready_for_signing": False,
             "ready_for_broadcast": False,
             "safety_note": "v2.6.0 — kill switch engaged, dry-run only",
             "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Phase 6/7/8/9 — Runtime config + Preflight + Daily Summary Writer
# ---------------------------------------------------------------------------
try:
    from arbicore.config.runtime import get_runtime_config as _get_rc
    from arbicore.validation.operations import (
        PreflightRunner as _PreflightRunner,
        DailySummaryWriter as _DailyWriter,
    )
    _RUNTIME_CFG = _get_rc()
    _OPS_AVAILABLE = True
    logger.info(
        "runtime_config activated (chains=%d, autostart_daily=%s)",
        len(_RUNTIME_CFG.rpc.urls_by_chain),
        _RUNTIME_CFG.validation.autostart_daily_writer)
except Exception:  # noqa: BLE001
    _RUNTIME_CFG = None
    _PreflightRunner = None    # type: ignore
    _DailyWriter = None        # type: ignore
    _OPS_AVAILABLE = False
    logger.exception("runtime_config/operations import failed")


_DAILY_WRITER: Optional[Any] = None


@app.get("/api/arbicore/config/runtime")
async def config_runtime() -> Dict[str, Any]:
    if _RUNTIME_CFG is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True,
             "config": _RUNTIME_CFG.to_dict(),
             "generated_at": _iso_now()}


@app.get("/api/arbicore/preflight")
async def preflight() -> Dict[str, Any]:
    if not _OPS_AVAILABLE or _RUNTIME_CFG is None:
        return {"available": False, "generated_at": _iso_now()}
    runner = _PreflightRunner(
        mongo_client=client,
        mid_reader=_MID_READER,
        mid_writer=_MID_WRITER,
        provider_registry=_PROVIDER_REGISTRY,
        live_scanners=_all_live_scanners(),
        paper_engine=_PAPER_ENGINE,
        kill_switch=_KILL,
        runtime_config=_RUNTIME_CFG,
    )
    return await runner.run()


@app.on_event("startup")
async def _daily_summary_startup():
    global _DAILY_WRITER
    if not _OPS_AVAILABLE or _RUNTIME_CFG is None:
        return
    if (_VALIDATION_REPORTER is None or _MID_WRITER is None
            or _PROVIDER_REGISTRY is None):
        return
    _DAILY_WRITER = _DailyWriter(
        validation_reporter=_VALIDATION_REPORTER,
        mid_writer=_MID_WRITER,
        registry=_PROVIDER_REGISTRY,
        live_scanners=_all_live_scanners(),
        runtime_config=_RUNTIME_CFG,
    )
    if _RUNTIME_CFG.validation.autostart_daily_writer:
        await _DAILY_WRITER.start()
        logger.info("daily_summary_writer: autostarted run_id=%s",
                    _DAILY_WRITER.run_id)


@app.on_event("shutdown")
async def _daily_summary_shutdown():
    if _DAILY_WRITER is not None and _DAILY_WRITER.is_running():
        await _DAILY_WRITER.stop()


@app.get("/api/arbicore/validation/daily_status")
async def validation_daily_status() -> Dict[str, Any]:
    if _DAILY_WRITER is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True,
             "run_id": _DAILY_WRITER.run_id,
             "running": _DAILY_WRITER.is_running(),
             "last_summary_at": (_DAILY_WRITER.last_summary or {}).get("at"),
             "last_anomalies": _DAILY_WRITER.last_anomalies,
             "generated_at": _iso_now()}


@app.post("/api/arbicore/validation/daily_run_now")
async def validation_daily_run_now(
        request: Request,
        authorization: Optional[str] = Header(default=None)):
    if _DAILY_WRITER is None:
        raise HTTPException(status_code=503, detail="daily_writer_unavailable")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx or ctx.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403,
                             detail="admin_or_operator_only")
    return await _DAILY_WRITER.run_once()


@app.get("/api/arbicore/validation/last_daily")
async def validation_last_daily() -> Dict[str, Any]:
    if _DAILY_WRITER is None or _DAILY_WRITER.last_summary is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True,
             "summary": _DAILY_WRITER.last_summary,
             "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Post-Validation Review & Calibration (v2.8.0 — read-only)
# ---------------------------------------------------------------------------
try:
    from arbicore.postvalidation import PostValidationReviewer as _PVR
    _POSTVAL_AVAILABLE = True
except Exception:  # noqa: BLE001
    _POSTVAL_AVAILABLE = False
    _PVR = None  # type: ignore
    logger.exception("post-validation import failed")


def _pv_reviewer():
    if not _POSTVAL_AVAILABLE or _RUNTIME_CFG is None:
        return None
    return _PVR(
        mid_reader=_MID_READER,
        registry=_PROVIDER_REGISTRY,
        live_scanners=_all_live_scanners(),
        runtime_config=_RUNTIME_CFG,
        paper_engine=_PAPER_ENGINE,
        kill_switch=_KILL,
        validation_reporter=_VALIDATION_REPORTER,
        daily_writer=_DAILY_WRITER,
    )


@app.get("/api/arbicore/postvalidation/report")
async def postval_report(sample_limit: int = 2000) -> Dict[str, Any]:
    r = _pv_reviewer()
    if r is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True, **(await r.calibration_report(
        sample_limit=int(sample_limit)))}


@app.get("/api/arbicore/postvalidation/recommendations")
async def postval_recommendations(sample_limit: int = 2000) -> Dict[str, Any]:
    r = _pv_reviewer()
    if r is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True, **(await r.recommendations(
        sample_limit=int(sample_limit)))}


@app.get("/api/arbicore/postvalidation/readiness_score")
async def postval_readiness(sample_limit: int = 2000) -> Dict[str, Any]:
    r = _pv_reviewer()
    if r is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True, **(await r.readiness_score(
        sample_limit=int(sample_limit)))}


@app.get("/api/arbicore/postvalidation/executive_summary")
async def postval_exec_summary(sample_limit: int = 2000) -> Dict[str, Any]:
    r = _pv_reviewer()
    if r is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True, **(await r.executive_summary(
        sample_limit=int(sample_limit)))}


# ---------- safety endpoints ----------

@app.get("/api/arbicore/safety/status")
async def safety_status() -> Dict[str, Any]:
    if not _SAFETY_AVAILABLE:
        return {"available": False, "generated_at": _iso_now()}
    return {
        "available":                True,
        "live_execution_enabled":   _POLICY.live_execution_enabled,
        "require_approval_gate":    _POLICY.require_approval_gate,
        "require_paper_validation": _POLICY.require_paper_validation,
        "kill":                     _KILL.to_dict(),
        "capital_policy":           _CAPITAL.to_dict(),
        "generated_at":             _iso_now(),
    }


@app.post("/api/arbicore/safety/kill/engage")
async def kill_engage(
    request: Request,
    reason: str = "operator_request",
    authorization: Optional[str] = Header(default=None),
):
    if not _SAFETY_AVAILABLE:
        raise HTTPException(status_code=503, detail="safety_unavailable")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx or ctx.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="admin_or_operator_only")
    entry = _KILL.engage(by=ctx.get("username"), reason=reason)
    if _AUDIT is not None:
        await _AUDIT.log(event="kill.engage",
                          by=ctx.get("username"),
                          payload={"reason": reason})
    return {**entry, "current": _KILL.to_dict()}


@app.post("/api/arbicore/safety/kill/disengage")
async def kill_disengage(
    request: Request,
    reason: str = "operator_request",
    authorization: Optional[str] = Header(default=None),
):
    if not _SAFETY_AVAILABLE:
        raise HTTPException(status_code=503, detail="safety_unavailable")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx or ctx.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin_only")
    entry = _KILL.disengage(by=ctx.get("username"), reason=reason)
    if _AUDIT is not None:
        await _AUDIT.log(event="kill.disengage",
                          by=ctx.get("username"),
                          payload={"reason": reason})
    return {**entry, "current": _KILL.to_dict()}


# ---------- paper engine endpoints ----------

@app.post("/api/arbicore/paper/analyse")
async def paper_analyse(
    body: Dict[str, Any],
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    if _PAPER_ENGINE is None:
        raise HTTPException(status_code=503, detail="paper_engine_unavailable")
    ctx = await _resolve_current_user(request, authorization)
    if not ctx or ctx.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="admin_or_operator_only")
    try:
        analysis = await _PAPER_ENGINE.analyse(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"opp_id": analysis.opp_id, **analysis.to_payload(),
            "generated_at": _iso_now()}


@app.get("/api/arbicore/paper/stats")
async def paper_stats() -> Dict[str, Any]:
    if _PAPER_ENGINE is None:
        return {"available": False, "generated_at": _iso_now()}
    return {"available": True, **_PAPER_ENGINE.stats.to_dict(),
            "generated_at": _iso_now()}


@app.get("/api/arbicore/observability")
async def observability() -> Dict[str, Any]:
    """Sprint 1B-β — one-shot operational observability endpoint.

    Aggregates health for the entire intelligence pipeline:
      * MID health + per-domain counts
      * Intelligence engine activation state + bridge throughput
      * Scanner activation state + shadow bridge throughput + backlog
      * Last-execution timestamps + error counters
    """
    payload: Dict[str, Any] = {"generated_at": _iso_now()}

    # MID
    if _MID_READER is not None:
        try:
            payload["mid"] = await _MID_READER.status()
            payload["mid"]["available"] = True
        except Exception as exc:  # noqa: BLE001
            payload["mid"] = {"available": False, "error": str(exc)}
    else:
        payload["mid"] = {"available": False}

    # Intelligence engines
    if _INTEL_ACTIVATION is not None:
        payload["intelligence"] = _INTEL_ACTIVATION.summary()
        payload["intelligence"]["available"] = True
    else:
        payload["intelligence"] = {"available": False}

    # Scanners
    if _SCANNER_ACTIVATION is not None:
        payload["scanners"] = _SCANNER_ACTIVATION.summary()
        payload["scanners"]["available"] = True
    else:
        payload["scanners"] = {"available": False}

    # Auth
    payload["auth"] = {"available": _AUTH_AVAILABLE}

    # Phase 2 — Opportunity Lifetime Intelligence
    if _LIFETIME_TRACKER is not None:
        try:
            summary = await _LIFETIME_TRACKER.status_summary()
            payload["lifetime"] = {
                "available":         True,
                "total":             summary.get("total"),
                "by_status":         summary.get("by_status"),
                "tracker_stats":     _LIFETIME_TRACKER.stats.to_dict(),
                "sweeper_running":   (_LIFETIME_SWEEPER.is_running()
                                       if _LIFETIME_SWEEPER else False),
                "sweeper_stats":     (_LIFETIME_SWEEPER.stats
                                       if _LIFETIME_SWEEPER else None),
                "config":            summary.get("config"),
            }
        except Exception as exc:  # noqa: BLE001
            payload["lifetime"] = {"available": True, "error": str(exc)}
    else:
        payload["lifetime"] = {"available": False}

    # Phase 5 — providers
    payload["providers"] = (
        {"available": True, **_PROVIDER_REGISTRY.snapshot()}
        if _PROVIDER_REGISTRY else {"available": False})

    # Phase 8 — safety
    payload["safety"] = (
        {"available": True,
         "live_execution_enabled": _POLICY.live_execution_enabled,
         "kill": _KILL.to_dict(),
         "capital_policy": _CAPITAL.to_dict()}
        if _SAFETY_AVAILABLE else {"available": False})

    # Phase 6 — paper engine
    payload["paper"] = (
        {"available": True, **_PAPER_ENGINE.stats.to_dict()}
        if _PAPER_ENGINE else {"available": False})

    return payload


@app.on_event("startup")
async def _start_adaptive_weights_worker():
    try:
        await _ADAPTIVE_WEIGHTS_WORKER.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to start adaptive weights worker: %s", exc)


@app.on_event("startup")
async def _start_evidence_signing_worker():
    try:
        await _EVIDENCE_WORKER.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to start evidence signing worker: %s", exc)


@app.on_event("startup")
async def _seed_execution_substrate():
    """Wave 6A — ensure indexes on mode / wallet / secret collections,
    and seed the approved deployment defaults for the mode ladder.
    Wave 6B — plan repo indexes.
    Wave 6D — capital policy defaults + kill switch default state."""
    try:
        await _EXECUTION_MODE_REPO.ensure_indexes()
        await _EXECUTION_MODE_REPO.ensure_defaults()
        await _WALLET_REGISTRY.ensure_indexes()
        await _SECRET_BACKEND.ensure_indexes()
        # Wave 6B — plan repo indexes.
        await _EXECUTION_PLANS_REPO.ensure_indexes()
        # Wave 6D — capital policy + kill switch bootstrap.
        await _CAPITAL_POLICY_REPO.ensure_indexes()
        await _CAPITAL_POLICY_REPO.ensure_defaults(list(TRADING_STRATEGIES))
        await _KILL_SWITCH_REPO.ensure_indexes()
        await _KILL_SWITCH_REPO.ensure_default()
        # Wave 7A — continuous discovery bootstrap.
        await _DISCOVERY_REPO.ensure_indexes()
        # Phase 8 — canonical opportunity repo bootstrap.
        await _CANONICAL_OPP_REPO.ensure_indexes()
        # P0-A — Opportunity Journal bootstrap.
        await _OPPORTUNITY_JOURNAL.ensure_indexes()
        # P0-B — Learning Ledger bootstrap.
        await _LEARNING_LEDGER.ensure_indexes()
        # Phase 10 — persistent configuration substrate bootstrap.
        await _CONFIG_REPO.ensure_indexes()
        await _NETWORK_CONFIG.ensure_seed_from_env()
        # Phase 10.10 — reverse-direction sync so persistent Network config
        # drives the runtime env (broadcast, gas, MEV, wallet balance,
        # executor verify, RPC health all consume os.environ).  Idempotent.
        exported = await sync_env_from_network_config(_NETWORK_CONFIG)
        if exported:
            logger.info("phase-10.10 env sync exported: %s",
                         sorted(exported.keys()))
        await _ACCOUNT_REPO.ensure_seeded()
        await _EXECUTION_SETTINGS.ensure_seeded()
        await _OPERATIONAL_FLAGS.ensure_seeded()
        await _TELEGRAM.ensure_indexes()
        await _TELEGRAM.ensure_seeded()
        await _SCANNER_CONFIG.ensure_seeded()
        if (os.environ.get("ARBICORE_DISCOVERY_AUTOSTART") or "true").lower() in ("1", "true", "yes"):
            await _CONTINUOUS_DISCOVERY.start()
        # P0-D — Autonomous Executor autostart.  Defaults to enabled so the
        # deployed VPS starts learning from opportunities immediately in
        # SHADOW mode (no chain writes until the operator promotes a
        # strategy to LIMITED_LIVE / FULL_LIVE).
        if (os.environ.get("ARBICORE_AUTOEXEC_AUTOSTART") or "true").lower() in ("1", "true", "yes"):
            await _AUTO_EXECUTOR.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("failed to seed execution substrate: %s", exc)


@app.on_event("shutdown")
async def _stop_calibration_worker():
    try:
        await _CALIBRATION_WORKER.stop()
    except Exception:  # noqa: BLE001
        pass


@app.on_event("shutdown")
async def _stop_adaptive_weights_worker():
    try:
        await _ADAPTIVE_WEIGHTS_WORKER.stop()
    except Exception:  # noqa: BLE001
        pass


@app.on_event("shutdown")
async def _stop_evidence_signing_worker():
    try:
        await _EVIDENCE_WORKER.stop()
    except Exception:  # noqa: BLE001
        pass


@app.on_event("shutdown")
async def _stop_auto_executor():
    try:
        await _AUTO_EXECUTOR.stop()
    except Exception:  # noqa: BLE001
        pass


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()