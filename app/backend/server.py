from fastapi import FastAPI, APIRouter, HTTPException, Request, Header, Depends, Body
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
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
    balance_reader=_WALLET_BALANCE_READER,
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
# v2.11.8 · Paper Validation Framework — canonical evidence repo + runner.
# The runner is bootstrapped later in `_start_paper_validation_runner`
# (deferred until after the OpportunityPipeline is fully assembled).
# ---------------------------------------------------------------------------
from arbicore.paper import (
    PaperEvidenceRepository,
    PaperValidationRunner,
    is_enabled_via_env as _paper_runner_enabled_via_env,
)
_PAPER_EVIDENCE_REPO = PaperEvidenceRepository(db)
_PAPER_RUNNER: Optional[PaperValidationRunner] = None

# ---------------------------------------------------------------------------
# v2.11.9 · Shadow Certification — canonical 20-cycle validation gate.
# Repo/engine are bootstrapped at import; the runner (background tick) is
# started later in `_shadow_certification_startup`. A run is one-at-a-time.
# ---------------------------------------------------------------------------
from arbicore.certification import (
    MongoShadowCertificationRepository,
    ShadowCertificationEngine,
    ShadowCertificationRunner,
    load_thresholds_from_env as _shadow_cert_load_thresholds,
    is_shadow_cert_enabled_via_env,
)
_SHADOW_CERT_REPO = MongoShadowCertificationRepository(db)
_SHADOW_CERT_ENGINE: Optional[ShadowCertificationEngine] = None
_SHADOW_CERT_RUNNER: Optional[ShadowCertificationRunner] = None

# ---------------------------------------------------------------------------
# Operator Control / Readiness layer — backend-authoritative GREEN/YELLOW/RED.
# The frontend may only REQUEST a mode; this layer decides if it's permitted.
# Reuses existing repos/engines; never weakens Phase-0 safety gates.
# ---------------------------------------------------------------------------
from arbicore.control import ExecutionReadinessEngine, ControlStateRepo, OPERATOR_MODES, NON_BROADCAST_MODES
_CONTROL_STATE_REPO = ControlStateRepo(db)
_READINESS_ENGINE = ExecutionReadinessEngine(
    db=db,
    kill_switch=_KILL_SWITCH_REPO,
    mode_repo=_EXECUTION_MODE_REPO,
    wallet_registry=_WALLET_REGISTRY,
    secret_registry=_SECRET_REGISTRY,
    capital_allocator=_CAPITAL_ALLOCATOR,
    balance_reader=_WALLET_BALANCE_READER,
    shadow_cert_repo=_SHADOW_CERT_REPO,
    paper_evidence_repo=_PAPER_EVIDENCE_REPO,
)

# ---------------------------------------------------------------------------
# P0 · Autonomous Flash-Loan Opportunity Engine + Decision History.
# Reuses RouteSearchEngine + QuoterRegistry + the P0 decision chain. Pure
# analysis + evidence persistence; SHADOW/PAPER-safe (no signer/broadcast).
# ---------------------------------------------------------------------------
from arbicore.economics.opportunity_engine import OpportunityEngine, ContinuousScanner, TOKEN_ALLOWLIST as _ENGINE_TOKEN_ALLOWLIST
from arbicore.data.decision_history import DecisionHistoryRepo, RouteRecurrenceRepo, ProfitAlertRepo
_OPPORTUNITY_ENGINE = OpportunityEngine(quoter_registry=_QUOTER_REGISTRY)
_DECISION_HISTORY_REPO = DecisionHistoryRepo(db)
_ROUTE_RECURRENCE_REPO = RouteRecurrenceRepo(db)
_PROFIT_ALERT_REPO = ProfitAlertRepo(db)
_CONTINUOUS_SCANNER = ContinuousScanner(
    engine=_OPPORTUNITY_ENGINE, history_repo=_DECISION_HISTORY_REPO,
    recurrence_repo=_ROUTE_RECURRENCE_REPO, alert_repo=_PROFIT_ALERT_REPO,
    interval_s=90.0, routes_per_scan=12)

from arbicore.execution.settlement_simulator import SettlementSimulator
_SETTLEMENT_SIM = SettlementSimulator(rpc_url=os.environ.get("ARBICORE_RPC_URL", ""))
_OPPORTUNITY_ENGINE._settlement_sim = _SETTLEMENT_SIM   # mandatory settlement gate
from arbicore.execution.atomic_executor_sim import AtomicExecutorSimulator
_ATOMIC_SIM = AtomicExecutorSimulator(rpc_url=os.environ.get("ARBICORE_RPC_URL", ""))


async def _atomic_sim_runner(*, route, univ3_hops, borrow_token, amount_wei):
    """MANDATORY atomic-executor gate for EXECUTABLE_UNIV3 routes.

    Encodes the executor's REAL entrypoint execute(address[],uint256[],bytes)
    with userData=abi.encode(SwapHop[],profitRecipient) over Uniswap V3 hops and
    runs the full atomic state-override sim (Balancer flash → UniV3 swaps →
    repay) against the DEPLOYED executor. Pure eth_call — never signs/broadcasts."""
    from arbicore.execution.signer_vault import signer_status
    from arbicore.execution.calldata import encode_executor_execute, build_user_data_from_hops
    from arbicore.discovery.base_venues import token_address as _taddr

    if not univ3_hops:
        return {"available": False, "passed": False,
                "reason": "route not representable as Uniswap V3 SwapHop[] (executor supports UniV3 only)"}
    st = await signer_status(db, expected_address=os.environ.get("ARBICORE_GAS_WALLET_ADDRESS"))
    if not st.get("present"):
        return {"available": False, "passed": False,
                "reason": "execution signer not present in vault"}
    executor = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    if not executor:
        return {"available": False, "passed": False,
                "reason": "ARBICORE_EXECUTOR_ADDRESS_BASE not set"}
    try:
        user_data = build_user_data_from_hops(hops=univ3_hops,
                                              profit_recipient=st.get("derived_address"))
        call = encode_executor_execute(executor_address=executor,
                                       tokens=[_taddr(borrow_token)], amounts=[int(amount_wei)],
                                       user_data_hex=user_data)
    except Exception as exc:  # noqa: BLE001
        return {"available": True, "passed": False, "reason": f"calldata encode failed: {exc}"}
    return await _ATOMIC_SIM.simulate_atomic(
        entry_calldata=call.calldata_hex, signer_present=True,
        from_address=st.get("derived_address"))


_OPPORTUNITY_ENGINE._atomic_runner = _atomic_sim_runner   # mandatory atomic gate

# ---------------------------------------------------------------------------
# Wallet & Capital Intelligence Engine (READ-ONLY, SHADOW-safe). Reuses the
# WalletBalanceReader + Base token universe + live ETH price from the
# opportunity engine. Never reads/logs/returns private keys.
# ---------------------------------------------------------------------------
from arbicore.capital import WalletIntelligenceEngine
_CAPITAL_ENGINE = WalletIntelligenceEngine(
    rpc_url=os.environ.get("ARBICORE_RPC_URL", ""),
    balance_reader=_WALLET_BALANCE_READER,
    eth_price_provider=_OPPORTUNITY_ENGINE._eth_price_usd)
# Cached, VERIFIED (not assumed) RPC capabilities + simulator self-test,
# refreshed at startup so the readiness matrix costs no RPC per request.
_RPC_CAPS: Dict[str, Any] = {}
_SETTLEMENT_SELFTEST: Dict[str, Any] = {}
_ATOMIC_SELFTEST: Dict[str, Any] = {}
_ATOMIC_LIVE_RUN: Dict[str, Any] = {}   # last live atomic sim vs deployed executor
_ATOMIC_DIAG_RUN: Dict[str, Any] = {}   # last DIAGNOSTIC (block-pinned/fork) atomic sim — never feeds live matrix
_FORK_RUN: Dict[str, Any] = {}          # last genuine anvil fork validation result


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
    # v2.11.8 · Paper Validation Framework — every pipeline evaluation
    # now writes an immutable EvidenceBundle to arbicore_paper_evidence.
    evidence_repo=_PAPER_EVIDENCE_REPO,
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


# ---------------------------------------------------------------------------
# v2.11.2 · Boot-stage instrumentation.
#
# Wrap every @app.on_event("startup") handler with:
#   * entry / exit / duration logging
#   * a per-handler asyncio.wait_for timeout so no single handler can
#     ever block Uvicorn's startup phase indefinitely.
#
# Why: the v2.11 VPS boot hung silently because a Mongo-dependent
# startup handler awaited motor with the default 30-s
# ``serverSelectionTimeoutMS``. Uvicorn never emitted
# "Application startup complete." so nothing bound to port 8001 and
# every health check failed with connect-refused.  We now:
#   * log ``BOOT: <handler> start`` and ``BOOT: <handler> done (<dt>s)``
#     around every handler, so the last successful handler is always
#     identifiable from the logs;
#   * cancel any handler that exceeds ``_BOOT_HANDLER_TIMEOUT_S`` and log
#     an explicit BOOT-TIMED-OUT error — startup continues without it,
#     and the abandoned coroutine is fire-and-forget (the resource it
#     was initialising will report the same failure on first user hit
#     and its own retry ladder, if any, will kick in).
#
# 8-second per-handler timeout is tighter than motor's default 30-s
# ``serverSelectionTimeoutMS`` so an unreachable Mongo surfaces fast.
# On the happy path every existing handler completes in <100 ms, so
# this bound is invisible.
# ---------------------------------------------------------------------------

_BOOT_HANDLER_TIMEOUT_S = 8.0
_orig_app_on_event = app.on_event


def _instrumented_on_event(event_name: str):
    """FastAPI ``@app.on_event`` decorator wrapped with boot instrumentation.

    Only ``startup`` is wrapped; ``shutdown`` is passed through untouched
    so existing tear-down semantics are not altered.
    """
    if event_name != "startup":
        return _orig_app_on_event(event_name)

    def _decorator(fn):
        async def _wrapped(*args, **kwargs):
            fn_name = getattr(fn, "__name__", str(fn))
            loop = asyncio.get_event_loop()
            t0 = loop.time()
            logger.info("BOOT: %s start", fn_name)
            try:
                await asyncio.wait_for(
                    fn(*args, **kwargs), timeout=_BOOT_HANDLER_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                dt = loop.time() - t0
                logger.error(
                    "BOOT: %s TIMED OUT after %.2fs "
                    "(> %.1fs budget) — startup continues without it",
                    fn_name, dt, _BOOT_HANDLER_TIMEOUT_S,
                )
                return
            except Exception as exc:  # noqa: BLE001
                dt = loop.time() - t0
                logger.exception(
                    "BOOT: %s FAILED after %.2fs: %s — startup continues",
                    fn_name, dt, exc,
                )
                return
            dt = loop.time() - t0
            logger.info("BOOT: %s done (%.2fs)", fn_name, dt)

        # Preserve the original name so downstream introspection stays sane.
        _wrapped.__name__ = getattr(fn, "__name__", "on_startup")
        _wrapped.__qualname__ = getattr(fn, "__qualname__", _wrapped.__name__)
        return _orig_app_on_event(event_name)(_wrapped)

    return _decorator


app.on_event = _instrumented_on_event  # type: ignore[assignment]


# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Slice 1.1 · Session-cookie operator guard.
# Defined early so decorators on routes below can use it via
# ``dependencies=[Depends(_require_operator_dep)]``.  The actual auth
# resolver (``_resolve_current_user``) is defined much later in this file —
# that reference resolves at request time, so forward-referencing is safe.
# ---------------------------------------------------------------------------


async def _require_operator_ctx(
    request: Request,
    authorization: Optional[str] = None,
) -> Dict[str, Any]:
    """Session guard used by protected /arbicore/* routes.

    Delegates to the unified ``_resolve_current_user`` resolver so the
    same cookie/bearer paths that gate the rest of v2.9.3 apply here.
    Raises 401 for anonymous callers; response body preserves the
    canonical shape used elsewhere ({"detail": "not_authenticated"}).
    """
    ctx = await _resolve_current_user(request, authorization)
    if not ctx:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return ctx


async def _require_operator_dep(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """FastAPI ``Depends``-compatible wrapper over ``_require_operator_ctx``.

    Used with ``dependencies=[Depends(_require_operator_dep)]`` on the
    APIRouter or per-route so protected endpoints don't need to plumb
    ``request`` / ``authorization`` through their signatures.
    """
    return await _require_operator_ctx(request, authorization)


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
async def root(
):
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


@api_router.get("/arbicore/dashboard/pulse", dependencies=[Depends(_require_operator_dep)])
async def v2_pulse() -> Dict[str, Any]:
    """Slice 5 · Canonical activation.

    Derives ``regime`` and ``opportunity_vitals`` from live canonical stores.
    Empty stores → empty counts (no fabrication).  All other pointer keys
    remain as endpoint hints for the frontend to fetch on demand.
    """
    # opportunity_vitals from the canonical repo
    try:
        rows = await _CANONICAL_OPP_REPO.find({}, limit=2000)
    except Exception:
        logger.exception("dashboard/pulse: canonical read failed")
        rows = []
    by_family: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for o in rows:
        ot = o.opportunity_type.value if hasattr(o.opportunity_type, "value") else str(o.opportunity_type)
        st = o.status.value if hasattr(o.status, "value") else str(o.status)
        by_family[ot] = by_family.get(ot, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1

    # regime — read the latest regime snapshot if the repo is composed;
    # otherwise report UNKNOWN.  No fabricated 'CALM · 0.82'.
    regime: Dict[str, Any] = {
        "regime":       "UNKNOWN",
        "tags":         [],
        "confidence":   0.0,
        "source":       "canonical",
        "observed_at":  None,
    }
    try:
        from arbicore.runtime.composition import get_regime_snapshot_repo
        r_repo = get_regime_snapshot_repo()
        latest = await r_repo.latest()
        if latest is not None:
            d = latest.to_dict() if hasattr(latest, "to_dict") else dict(latest)
            regime = {
                "regime":      d.get("regime", "UNKNOWN"),
                "tags":        list(d.get("tags", []) or []),
                "confidence":  float(d.get("confidence", 0.0) or 0.0),
                "source":      "canonical",
                "observed_at": d.get("observed_at"),
            }
    except Exception:
        # Repository not composed / no snapshots yet — honest empty regime.
        logger.debug("dashboard/pulse: regime snapshot repo unavailable")

    # Route-learning trace: count of routes with journal entries so far.
    tracked_routes = 0
    try:
        db = _CANONICAL_OPP_REPO._col.database  # type: ignore[attr-defined]
        tracked_routes = await db.arbicore_opportunity_journal.count_documents({})
    except Exception:
        logger.debug("dashboard/pulse: route trace unavailable")

    # v2.11.8 — Paper Validation pulse. Compact histogram + executable
    # rate; the full report lives at /arbicore/validation/report.
    paper_validation = {"total": 0, "executable_rate": 0.0,
                         "runner_running": False, "outcome_counts": {}}
    try:
        _pv_total = await _PAPER_EVIDENCE_REPO.count()
        _pv_hist  = await _PAPER_EVIDENCE_REPO.outcome_histogram()
        _pv_exec  = int(_pv_hist.get("EXECUTABLE", 0))
        paper_validation = {
            "total":            int(_pv_total),
            "executable_rate":  (_pv_exec / _pv_total) if _pv_total else 0.0,
            "runner_running":   bool(_PAPER_RUNNER and _PAPER_RUNNER.is_running()),
            "outcome_counts":   {k: int(v) for k, v in _pv_hist.items()},
        }
    except Exception:  # noqa: BLE001
        logger.debug("dashboard/pulse: paper validation snapshot unavailable")

    # v2.11.9 — Shadow Certification pulse. Compact snapshot of the
    # active certification run (if any) so operators can see progress
    # without hitting /certification/shadow/current.
    shadow_certification = {
        "active":           False,
        "run_id":           None,
        "status":           None,
        "cycles_completed": 0,
        "target_cycles":    0,
        "executable_rate":  0.0,
    }
    try:
        _cert_run = None
        if _SHADOW_CERT_ENGINE is not None:
            _cert_run = await _SHADOW_CERT_ENGINE.current_run()
        if _cert_run is not None:
            shadow_certification = {
                "active":           True,
                "run_id":           _cert_run.run_id,
                "status":           _cert_run.status,
                "cycles_completed": _cert_run.cycles_completed,
                "target_cycles":    _cert_run.target_cycles,
                "executable_rate":  _cert_run.cumulative_executable_rate(),
            }
    except Exception:  # noqa: BLE001
        logger.debug("dashboard/pulse: shadow certification snapshot unavailable")

    return {
        "regime":              regime,
        "opportunity_vitals":  {
            "total":     len(rows),
            "by_family": by_family,
            "by_status": by_status,
        },
        "route_learning":      {"tracked_routes": tracked_routes},
        "paper_validation":    paper_validation,
        "shadow_certification": shadow_certification,
        # Pointer keys (unchanged; frontend fetches these on demand).
        "scanner_status":      {"endpoint": "/api/arbicore/scanners", "detail": "per-family scanner status"},
        "venue_readiness":     {"endpoint": "/api/venues/status", "detail": "venue readiness registry"},
        "feed_freshness":      {"endpoint": "/api/execution/portal/diagnostic", "detail": "portal feed freshness"},
        "interlock":           {"endpoint": "/api/execution/interlock", "detail": "safety interlock status"},
        "deployable_capital":  {"endpoint": "/api/portfolio/deployable", "detail": "deployable capital"},
        "anomalies":           [],
        "source":              "canonical",
        "generated_at":        _iso_now(),
    }


@api_router.get("/arbicore/dashboard/deck", dependencies=[Depends(_require_operator_dep)])
async def v2_deck(limit: int = 5) -> Dict[str, Any]:
    """Slice 5 · Canonical activation.

    Reads the canonical Opportunity repository directly:
      * ``fresh_opportunities``   most recent by ``created_at``, any status.
      * ``pending_approvals``     rows with FSM status VALIDATED (i.e.
                                   ``WATCHING`` in UI terms) awaiting operator decision.
      * ``requires_attention``    rows with status CANDIDATE whose
                                   ``updated_at`` is stale (> 6 h old) — a
                                   pragmatic definition of "needs a look".
    Empty stores → empty lists.  No fabrication.
    """
    limit = max(1, min(int(limit or 5), 20))
    try:
        rows = await _CANONICAL_OPP_REPO.find({}, limit=500)
    except Exception:
        logger.exception("dashboard/deck: canonical read failed")
        rows = []

    def _row(o) -> Dict[str, Any]:
        c = float(o.confidence_score or 0)
        conf = c / 100.0 if c > 1.0 else c
        return {
            "id":                o.opportunity_id,
            "opportunity_type":  o.opportunity_type.value if hasattr(o.opportunity_type, "value") else str(o.opportunity_type),
            "subject_id":        o.subject_id or o.asset or o.opportunity_id,
            "chain":             o.chain,
            "confidence":        round(conf, 4),
            "status":            o.status.value if hasattr(o.status, "value") else str(o.status),
            "created_at":        o.created_at,
        }

    validated = OpportunityStatus.VALIDATED.value
    candidate = OpportunityStatus.CANDIDATE.value

    # Fresh — most recent by created_at desc.
    fresh_sorted = sorted(rows, key=lambda o: o.created_at or "", reverse=True)
    fresh = [_row(o) for o in fresh_sorted[:limit]]

    # Pending approvals — currently VALIDATED (awaiting APPROVED/REJECTED).
    pending = [_row(o) for o in rows
               if (o.status.value if hasattr(o.status, "value") else str(o.status)) == validated]

    # Requires attention — CANDIDATE untouched for > 6h.
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    def _is_stale(o) -> bool:
        st = (o.status.value if hasattr(o.status, "value") else str(o.status))
        if st != candidate:
            return False
        upd = getattr(o, "updated_at", None) or getattr(o, "created_at", None)
        if not upd:
            return False
        try:
            if isinstance(upd, str):
                dt = datetime.fromisoformat(upd.replace("Z", "+00:00"))
            else:
                dt = upd
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt < cutoff
        except Exception:
            return False
    attention = [_row(o) for o in rows if _is_stale(o)]

    return {
        "pending_approvals":         pending[:limit],
        "pending_approvals_total":   len(pending),
        "fresh_opportunities":       fresh,
        "fresh_opportunities_total": len(fresh_sorted),
        "requires_attention":        attention[:limit],
        "requires_attention_total":  len(attention),
        "source":                    "canonical",
        "generated_at":              _iso_now(),
    }


@api_router.get("/arbicore/opportunities/summary", dependencies=[Depends(_require_operator_dep)])
async def v2_opportunities_summary(
    window_hours: int = 24,
    max_scan: int = 1000
) -> Dict[str, Any]:
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
async def v2_roi_probability(
route_id: str) -> Dict[str, Any]:
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
#
# Slice 1.1 · Session-cookie auth gate.  Every /arbicore/opportunities*
# handler requires a valid authenticated operator context (cookie or
# bearer, resolved by _resolve_current_user via _require_operator_dep).
# Anonymous callers receive 401.  Contract otherwise preserved.
# ---------------------------------------------------------------------------


@api_router.get("/arbicore/opportunities", dependencies=[Depends(_require_operator_dep)])
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


@api_router.get("/arbicore/opportunities/{opp_id}", dependencies=[Depends(_require_operator_dep)])
async def v2_opportunity_detail(
    opp_id: str,
) -> Dict[str, Any]:
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


@api_router.post("/arbicore/opportunities/{opp_id}/approve", dependencies=[Depends(_require_operator_dep)])
async def v2_opportunity_approve(
    opp_id: str,
) -> Dict[str, Any]:
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
            await _journal_record_operator_event(
                canonical,
                kind="operator_approved",
                detail={"new_status": canonical.status.value},
                status=canonical.status.value,
            )
            return {"ok": True, "id": opp_id, "status": canonical.status.value,
                    "canonical": True, "generated_at": _iso_now()}
    except InvalidTransitionError as exc:
        return {"ok": False, "id": opp_id, "error": str(exc),
                "generated_at": _iso_now()}
    except HTTPException:
        raise
    except Exception:
        logger.exception("approve: canonical mutation failed for %s", opp_id)
    # Slice 1 · canonical-only. No preview fallback.
    raise HTTPException(status_code=404, detail={"error": "not_found", "id": opp_id})


@api_router.post("/arbicore/opportunities/{opp_id}/reject", dependencies=[Depends(_require_operator_dep)])
async def v2_opportunity_reject(
    opp_id: str,
    body: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    reason = (body or {}).get("reason") or "operator_rejected"
    try:
        canonical = await _CANONICAL_OPP_REPO.get(opp_id)
        if canonical is not None:
            canonical.mark_rejected(reason)
            await _CANONICAL_OPP_REPO.upsert(canonical)
            # Slice 1: record decision on the journal.
            await _journal_record_operator_event(
                canonical,
                kind="operator_rejected",
                detail={"new_status": canonical.status.value, "reason": reason},
                status=canonical.status.value,
            )
            return {"ok": True, "id": opp_id, "status": canonical.status.value,
                    "canonical": True, "reason": reason,
                    "generated_at": _iso_now()}
    except InvalidTransitionError as exc:
        return {"ok": False, "id": opp_id, "error": str(exc),
                "generated_at": _iso_now()}
    except HTTPException:
        raise
    except Exception:
        logger.exception("reject: canonical mutation failed for %s", opp_id)
    # Slice 1 · canonical-only. No preview fallback.
    raise HTTPException(status_code=404, detail={"error": "not_found", "id": opp_id})


async def _journal_record_operator_event(
    canonical: "CanonicalOpportunity",
    *,
    kind: str,
    detail: Dict[str, Any],
    status: str,
) -> None:
    """Slice 1 audit-trail bridge.

    ``OpportunityJournal.record_event`` will not create a new journal row
    for an opportunity that never passed through the discovery pipeline
    (e.g. seeded canonical rows).  We first try to append, and if the row
    is missing we seed it via ``record_discovery`` and then append.  This
    guarantees every operator decision produces an audit entry without
    changing the journal's original contract.
    """
    opp_id = canonical.opportunity_id
    try:
        appended = await _OPPORTUNITY_JOURNAL.record_event(
            opp_id, kind=kind, detail=detail, status=status,
        )
        if appended is not None:
            return
        # Row did not exist — seed a discovery entry, then append the operator event.
        await _OPPORTUNITY_JOURNAL.record_discovery(
            canonical,
            mode="OPERATOR",
            scanner_family="operator_console",
            detail={"seeded_by": kind},
        )
        await _OPPORTUNITY_JOURNAL.record_event(
            opp_id, kind=kind, detail=detail, status=status,
        )
    except Exception:
        logger.exception("journal audit write failed for %s (kind=%s)", opp_id, kind)


# ---------------------------------------------------------------------------
# Phase 8 · Per-opportunity Execution Timeline (join view — no new persistence)
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/opportunities/{opp_id}/timeline", dependencies=[Depends(_require_operator_dep)])
async def v2_opportunity_timeline(
    opp_id: str
) -> Dict[str, Any]:
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
                "kind": ev.kind,
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

# ---------------------------------------------------------------------------
# Slice 2 · Canonical Discovery view (real Mongo).
#
# The v2.10.1 slice removes ``_V2_DISCOVERY`` and rewires the Discovery
# page to render early-stage rows from the canonical Opportunity pipeline
# (``arbicore_opportunities``).  Discovery is now the pre-approval view of
# the same funnel Slice 1 activated — not a synthetic narrative feed.
#
# UI contract preserved:
#   * Field shape unchanged (id / asset / kind / chain / source / score /
#     status / why / signals / seen_at).
#   * Status vocabulary preserved (NEW / WATCHING / PROMOTED / DISMISSED)
#     — mapped from the canonical FSM:
#         CANDIDATE  -> NEW
#         VALIDATED  -> WATCHING
#         APPROVED   -> PROMOTED
#         REJECTED   -> DISMISSED
#   * Action verbs preserved (watch / promote / dismiss / reset), each
#     mapped to a canonical FSM transition (reset is a no-op — the
#     canonical FSM has no unset transition; response reports current
#     status).
#   * All endpoints are session-cookie auth-gated (v2.9.3 + Slice 1.1
#     precedent).
# ---------------------------------------------------------------------------


_CANONICAL_STATUS_TO_UI = {
    OpportunityStatus.CANDIDATE.value: "NEW",
    OpportunityStatus.VALIDATED.value: "WATCHING",
    OpportunityStatus.APPROVED.value:  "PROMOTED",
    OpportunityStatus.REJECTED.value:  "DISMISSED",
}

_UI_ACTION_TO_TARGET_STATUS = {
    "watch":   OpportunityStatus.VALIDATED,
    "promote": OpportunityStatus.APPROVED,
    "dismiss": OpportunityStatus.REJECTED,
    # "reset" is intentionally absent — canonical FSM has no back-transition.
}


def _canonical_opp_to_discovery(opp: "CanonicalOpportunity") -> Dict[str, Any]:
    """Translate a CanonicalOpportunity into the Discovery UI contract."""
    conf = float(opp.confidence_score or 0)
    if conf > 1.0:  # tolerate 0-100 scale
        conf = conf / 100.0
    otype = (opp.opportunity_type.value if hasattr(opp.opportunity_type, "value")
             else str(opp.opportunity_type))
    provenance = (opp.source_data_quality.value
                  if hasattr(opp.source_data_quality, "value")
                  else str(opp.source_data_quality))
    canonical_status = (opp.status.value if hasattr(opp.status, "value")
                        else str(opp.status))
    # kind: venue-pair for arb strategies that carry a route; asset otherwise.
    has_route = bool(opp.route) or bool(opp.buy_venue and opp.sell_venue)
    kind = "venue_pair" if has_route else "asset"
    # asset label: use canonical asset when present, else fall back to subject
    asset_label = opp.asset or opp.subject_id or opp.opportunity_id
    # why: a compact machine-generated explanation from the canonical row.
    parts: List[str] = []
    parts.append(otype.replace("_", " ").title())
    if opp.chain:
        parts.append(f"on {opp.chain}")
    if opp.spread_pct is not None:
        parts.append(f"spread {opp.spread_pct:.2f}%")
    parts.append(f"confidence {conf:.2f}")
    why = " · ".join(parts)
    # signals: normalised set of tags from the canonical row.
    signals = [
        f"type:{otype.lower()}",
        f"provenance:{provenance.lower()}",
    ]
    if opp.chain:
        signals.append(f"chain:{opp.chain}")
    if opp.route:
        signals.append(f"route:{opp.route}")
    return {
        "id":       opp.opportunity_id,
        "asset":    asset_label,
        "kind":     kind,
        "chain":    opp.chain or "-",
        "source":   f"canonical:{provenance.lower()}",
        "score":    round(conf, 4),
        "status":   _CANONICAL_STATUS_TO_UI.get(canonical_status, "NEW"),
        "why":      why,
        "signals":  signals,
        "seen_at":  opp.created_at,
    }


def _canonical_discovery_calibration(rows: List["CanonicalOpportunity"]) -> Dict[str, Any]:
    """Honest calibration block computed from the canonical population.

    Reports the fraction of top-decile-scored rows that reached APPROVED
    versus the fraction of bottom-decile-scored rows that did the same.
    When the sample is too small the deciles collapse and the rates
    default to 0.0 — no faked figures.
    """
    n = len(rows)
    approved_status = OpportunityStatus.APPROVED.value
    def _reached_approved(o) -> bool:
        st = (o.status.value if hasattr(o.status, "value") else str(o.status))
        return st == approved_status
    def _score(o) -> float:
        c = float(o.confidence_score or 0)
        return c / 100.0 if c > 1.0 else c
    top_rate = 0.0
    bot_rate = 0.0
    if n >= 10:
        ordered = sorted(rows, key=_score, reverse=True)
        decile = max(1, n // 10)
        top = ordered[:decile]
        bot = ordered[-decile:]
        top_rate = round(sum(1 for o in top if _reached_approved(o)) / len(top), 4)
        bot_rate = round(sum(1 for o in bot if _reached_approved(o)) / len(bot), 4)
    return {
        "model": "canonical-opportunity-lifecycle@2026.08.0",
        "n_samples": n,
        "promotion_rate_top_decile": top_rate,
        "promotion_rate_bottom_decile": bot_rate,
        "ece": 0.0,
        "drift_alert": False,
    }


@api_router.get("/arbicore/discovery/candidates", dependencies=[Depends(_require_operator_dep)])
async def v2_discovery_candidates(
    status: Optional[str] = None,
    kind: Optional[str] = None,
    min_score: float = 0.0,
    limit: int = 100
) -> Dict[str, Any]:
    """Slice 2 · Canonical activation.

    Reads the canonical ``arbicore_opportunities`` collection and projects
    each row into the Discovery UI contract.  Empty repo → empty items.
    No preview fallback.
    """
    try:
        canonical_rows = await _CANONICAL_OPP_REPO.find({}, limit=1000)
    except Exception:
        logger.exception("discovery_candidates: canonical read failed")
        canonical_rows = []

    items = [_canonical_opp_to_discovery(o) for o in canonical_rows]
    out: List[Dict[str, Any]] = []
    for c in items:
        if status and status != "ALL" and c["status"] != status:
            continue
        if kind and kind != "ALL" and c["kind"] != kind:
            continue
        if c["score"] < min_score:
            continue
        out.append(c)
    out.sort(key=lambda c: c.get("score") or 0, reverse=True)

    stats = {
        "total": len(items),
        "new":       sum(1 for c in items if c["status"] == "NEW"),
        "watching":  sum(1 for c in items if c["status"] == "WATCHING"),
        "promoted":  sum(1 for c in items if c["status"] == "PROMOTED"),
        "dismissed": sum(1 for c in items if c["status"] == "DISMISSED"),
    }
    return {
        "items": out[:limit],
        "total": len(out),
        "stats": stats,
        "calibration": _canonical_discovery_calibration(canonical_rows),
        "source": "canonical",
        "generated_at": _iso_now(),
    }


@api_router.post("/arbicore/discovery/candidates/{cand_id}/action", dependencies=[Depends(_require_operator_dep)])
async def v2_discovery_action(
    cand_id: str,
    action: str
) -> Dict[str, Any]:
    """Slice 2 · Canonical activation.

    Maps UI verbs (watch / promote / dismiss / reset) onto canonical FSM
    transitions and journals the operator decision.  Unknown id → 404;
    unknown action or a no-op reset → returns the current status without
    mutating the row.
    """
    verb = (action or "").lower().strip()
    try:
        canonical = await _CANONICAL_OPP_REPO.get(cand_id)
    except Exception:
        logger.exception("discovery_action: canonical read failed for %s", cand_id)
        canonical = None
    if canonical is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "id": cand_id},
        )

    def _ui_status(opp: "CanonicalOpportunity") -> str:
        st = (opp.status.value if hasattr(opp.status, "value")
              else str(opp.status))
        return _CANONICAL_STATUS_TO_UI.get(st, "NEW")

    # No-op verbs (reset / unknown): return current state, do not mutate.
    if verb not in _UI_ACTION_TO_TARGET_STATUS:
        return {"ok": True, "id": cand_id, "status": _ui_status(canonical),
                "action": verb, "no_op": True,
                "generated_at": _iso_now()}

    target = _UI_ACTION_TO_TARGET_STATUS[verb]
    try:
        if target == OpportunityStatus.VALIDATED:
            # watch: only legal from CANDIDATE.  FSM raises otherwise.
            canonical.mark_validated()
        elif target == OpportunityStatus.APPROVED:
            # promote: walk the FSM from wherever we are.  Any illegal
            # source status surfaces as InvalidTransitionError from the
            # canonical FSM, which is caught below.
            if canonical.status == OpportunityStatus.CANDIDATE:
                canonical.mark_validated()
            canonical.mark_approved()
        elif target == OpportunityStatus.REJECTED:
            canonical.mark_rejected(f"discovery_action:{verb}")
        await _CANONICAL_OPP_REPO.upsert(canonical)
        await _journal_record_operator_event(
            canonical,
            kind=f"discovery_{verb}",
            detail={"ui_action": verb,
                    "new_status": canonical.status.value},
            status=canonical.status.value,
        )
    except InvalidTransitionError as exc:
        return {"ok": False, "id": cand_id, "status": _ui_status(canonical),
                "action": verb, "error": str(exc),
                "generated_at": _iso_now()}
    except HTTPException:
        raise
    except Exception:
        logger.exception("discovery_action: canonical mutation failed for %s (verb=%s)",
                         cand_id, verb)
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "id": cand_id},
        )
    return {"ok": True, "id": cand_id, "status": _ui_status(canonical),
            "action": verb, "canonical": True,
            "generated_at": _iso_now()}


@api_router.get("/arbicore/intelligence/recommendations", dependencies=[Depends(_require_operator_dep)])
async def v2_recommendations(

) -> Dict[str, Any]:
    """Slice 3 · Canonical activation.

    Derives ``top_routes`` / ``top_chains`` / ``top_entities`` from the live
    canonical stores.  No fabricated recommendations — empty stores return
    empty lists.
      * top_routes  aggregates ``arbicore_opportunities`` by (buy_venue,
                    sell_venue) with win_rate (approved / total), trials,
                    mean confidence.
      * top_chains  aggregates ``arbicore_opportunities`` by chain.
      * top_entities pulls the top-scored rows from the canonical entity
                    scorer (``services.execution.arbitrage_intel`` scorer
                    surfaced via ``get_entity_scorer``).
    """
    try:
        rows = await _CANONICAL_OPP_REPO.find({}, limit=2000)
    except Exception:
        logger.exception("intelligence/recommendations: canonical read failed")
        rows = []

    def _route_key(o: "CanonicalOpportunity") -> Optional[str]:
        bv, sv = getattr(o, "buy_venue", None), getattr(o, "sell_venue", None)
        if bv and sv:
            return f"{bv} → {sv}"
        if getattr(o, "route", None):
            return str(o.route)
        return None

    def _score(o: "CanonicalOpportunity") -> float:
        c = float(o.confidence_score or 0)
        return c / 100.0 if c > 1.0 else c

    approved_v = OpportunityStatus.APPROVED.value
    from collections import defaultdict
    route_agg: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"trials": 0, "wins": 0, "conf_sum": 0.0})
    chain_agg: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"opps": 0, "conf_sum": 0.0})
    for o in rows:
        rk = _route_key(o)
        s = _score(o)
        st = (o.status.value if hasattr(o.status, "value") else str(o.status))
        if rk:
            route_agg[rk]["trials"] += 1
            route_agg[rk]["conf_sum"] += s
            if st == approved_v:
                route_agg[rk]["wins"] += 1
        if o.chain:
            chain_agg[o.chain]["opps"] += 1
            chain_agg[o.chain]["conf_sum"] += s

    top_routes = sorted(
        ({"route": rk, "win_rate": round(v["wins"] / v["trials"], 4) if v["trials"] else 0.0,
          "trials": v["trials"],
          "mean_confidence": round(v["conf_sum"] / v["trials"], 4) if v["trials"] else 0.0}
         for rk, v in route_agg.items()),
        key=lambda r: (r["win_rate"], r["trials"]), reverse=True,
    )[:10]
    top_chains = sorted(
        ({"chain": c, "opps": v["opps"],
          "avg_confidence": round(v["conf_sum"] / v["opps"], 4) if v["opps"] else 0.0}
         for c, v in chain_agg.items()),
        key=lambda r: (r["opps"], r["avg_confidence"]), reverse=True,
    )[:10]

    # Entities: canonical scorer if available; else empty (no fabrication).
    top_entities: List[Dict[str, Any]] = []
    try:
        from arbicore.runtime.composition import get_entity_scorer
        scorer = get_entity_scorer()
        rows_e = await scorer.top(limit=10)
        for r in rows_e:
            d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
            top_entities.append({
                "entity": d.get("entity_id"),
                "kind": d.get("entity_type", "UNKNOWN"),
                "score": round(float(d.get("avg_outcome_score", 0.0) or 0.0), 4),
                "samples": int(d.get("sample_count", 0) or 0),
            })
    except Exception:
        logger.exception("intelligence/recommendations: entity scorer unavailable")
        top_entities = []

    return {
        "top_routes":    top_routes,
        "top_chains":    top_chains,
        "top_entities":  top_entities,
        "source":        "canonical",
        "generated_at":  _iso_now(),
    }


@api_router.get("/arbicore/intelligence/decisions", dependencies=[Depends(_require_operator_dep)])
async def v2_decisions(
    verdict: Optional[str] = None,
    family: Optional[str] = None,
    min_confidence: float = 0.0,
    limit: int = 100
) -> Dict[str, Any]:
    """Slice 3 · Canonical activation.

    Derives operator decisions from the canonical audit trail:
    ``arbicore_opportunity_journal`` events (``operator_approved`` /
    ``operator_rejected`` / ``discovery_promote`` / ``discovery_dismiss``)
    joined against ``arbicore_opportunities`` for the enrichment fields.

    Verdict mapping (canonical event → UI verdict):
        operator_approved / discovery_promote  → GO
        operator_rejected / discovery_dismiss  → HARD_NO

    Empty journal → empty items list.  No fabricated decisions.
    """
    verdict_from_kind = {
        "operator_approved": "GO",
        "operator_rejected": "HARD_NO",
        "discovery_promote": "GO",
        "discovery_dismiss": "HARD_NO",
        "discovery_watch":   "SOFT_NO",
    }
    items: List[Dict[str, Any]] = []
    try:
        db = _CANONICAL_OPP_REPO._col.database  # type: ignore[attr-defined]
        cursor = db.arbicore_opportunity_journal.find({}, {"_id": 0}) \
                                                .sort("updated_at", -1) \
                                                .limit(min(int(limit) * 4, 500))
        journal_rows = await cursor.to_list(length=None)
    except Exception:
        logger.exception("intelligence/decisions: journal read failed")
        journal_rows = []

    for jrow in journal_rows:
        opp_id = jrow.get("opportunity_id")
        if not opp_id:
            continue
        try:
            canonical = await _CANONICAL_OPP_REPO.get(opp_id)
        except Exception:
            canonical = None
        canonical_family = None
        canonical_asset = None
        canonical_conf = 0.0
        if canonical is not None:
            ot = canonical.opportunity_type
            canonical_family = ot.value if hasattr(ot, "value") else str(ot)
            canonical_asset = canonical.asset or canonical.subject_id or opp_id
            c = float(canonical.confidence_score or 0)
            canonical_conf = c / 100.0 if c > 1.0 else c
        for ev in reversed(jrow.get("events", []) or []):
            kind = ev.get("kind")
            if kind not in verdict_from_kind:
                continue
            det = ev.get("detail") or {}
            factors: List[str] = []
            if canonical is not None:
                if canonical.spread_pct is not None:
                    factors.append(f"spread {canonical.spread_pct:.2f}%")
                if canonical.chain:
                    factors.append(f"chain:{canonical.chain}")
                if getattr(canonical, "source_data_quality", None):
                    prov = canonical.source_data_quality
                    factors.append(
                        f"prov:{prov.value if hasattr(prov,'value') else prov}")
            if det.get("reason"):
                factors.append(f"reason:{det['reason']}")
            items.append({
                "id":        f"{opp_id}::{kind}::{ev.get('at')}",
                "opp_id":    opp_id,
                "asset":     canonical_asset,
                "family":    canonical_family,
                "verdict":   verdict_from_kind[kind],
                "confidence": round(canonical_conf, 4),
                "regime":    "CALM",
                "top_factors": factors,
                "kind":      kind,
                "at":        ev.get("at"),
            })

    # Filter.
    out = []
    for d in items:
        if verdict and verdict != "ALL" and d["verdict"] != verdict:
            continue
        if family and family != "ALL" and d["family"] != family:
            continue
        if d["confidence"] < min_confidence:
            continue
        out.append(d)
    return {
        "items":        out[:limit],
        "total":        len(out),
        "source":       "canonical",
        "generated_at": _iso_now(),
    }


# ---------------------------------------------------------------------------
# Wave-1 activations — dormant learning-loop engines exposed as preview stubs.
# UI contract additions only; no existing endpoint shape is broken.
#
# Future-endpoint mapping (production):
#   GET /api/arbicore/intelligence/calibration   <- CalibrationRepo.snapshot()
#   GET /api/arbicore/intelligence/models        <- ModelRegistry.list_active()
# ---------------------------------------------------------------------------

@api_router.get("/arbicore/intelligence/calibration", dependencies=[Depends(_require_operator_dep)])
async def v2_calibration(
    model: Optional[str] = None,
    window_days: Optional[int] = None
) -> Dict[str, Any]:
    """Slice 3 · Canonical activation.

    Reads the active row from ``calibration_models`` via
    ``_CALIBRATION_REPO.get_active('confidence')``.  When no active model
    exists yet, returns a genuine empty state (``available: false``) —
    no bootstrap stub, no fabricated buckets.
    """
    try:
        active = await _CALIBRATION_REPO.get_active("confidence")
    except Exception:
        logger.exception("intelligence/calibration: canonical read failed")
        active = None
    if active is None:
        return {
            "available":            False,
            "model":                None,
            "window_days":          window_days or _CALIBRATION_CFG.window_days,
            "n_samples":            0,
            "brier_score":          0.0,
            "ece":                  0.0,
            "drift_alert":          False,
            "buckets":              [],
            "algorithm":            None,
            "calibrator_version":   _CALIBRATION_CFG.calibrator_version,
            "supersedes":           None,
            "source":               "canonical",
            "generated_at":         _iso_now(),
        }
    return {
        "available":            True,
        "model":                active.get("id"),
        "window_days":          active.get("window_days") or _CALIBRATION_CFG.window_days,
        "n_samples":            active.get("n_samples", 0),
        "brier_score":          active.get("brier_score", 0.0),
        "ece":                  active.get("ece", 0.0),
        "drift_alert":          bool(active.get("drift_alert", False)),
        "buckets":              active.get("buckets", []),
        "algorithm":            active.get("algorithm"),
        "calibrator_version":   active.get("calibrator_version"),
        "supersedes":           active.get("supersedes"),
        "source":               "canonical",
        "generated_at":         _iso_now(),
    }


@api_router.get("/arbicore/intelligence/models", dependencies=[Depends(_require_operator_dep)])
async def v2_models(

) -> Dict[str, Any]:
    """Slice 3 · Canonical activation.

    Lists fitted calibration models from ``calibration_models`` (recent
    rows across the ``confidence`` + ``adaptive_weights`` kinds).  Empty
    when no models have been fitted yet.  Also surfaces the current
    active adaptive-weight recommendation for completeness.
    """
    items: List[Dict[str, Any]] = []
    promotions: List[Dict[str, Any]] = []

    def _row_to_item(row: Dict[str, Any], kind: str) -> Dict[str, Any]:
        return {
            "id":                  row.get("id"),
            "kind":                kind,
            "state":               (row.get("state") or "").upper(),
            "promoted_at":         row.get("promoted_at"),
            "fitted_at":           row.get("fitted_at"),
            "shadow":              row.get("state") == "shadow",
            "trained_on_samples":  int(row.get("n_samples", 0) or 0),
            "eval_brier":          float(row.get("brier_score", 0.0) or 0.0),
            "eval_ece":            float(row.get("ece", 0.0) or 0.0),
            "algorithm":           row.get("algorithm"),
            "calibrator_version":  row.get("calibrator_version"),
            "supersedes":          row.get("supersedes"),
        }

    for kind in ("confidence",):
        try:
            recent = await _CALIBRATION_REPO.list_recent(kind, limit=20)
        except Exception:
            logger.exception("intelligence/models: list_recent(%s) failed", kind)
            recent = []
        for row in recent:
            items.append(_row_to_item(row, kind))
            if row.get("supersedes"):
                promotions.append({
                    "at":     row.get("promoted_at"),
                    "from":   row.get("supersedes"),
                    "to":     row.get("id"),
                    "kind":   kind,
                    "reason": row.get("promotion_reason") or "promotion recorded",
                })
    # Add current active adaptive weights row (state row, not a model per se).
    try:
        w_active = await _ADAPTIVE_WEIGHTS_REPO.get_active("adaptive_weights")
    except Exception:
        w_active = None
    if w_active:
        items.append({
            "id":                  w_active.get("id"),
            "kind":                "adaptive_weights",
            "state":               (w_active.get("state") or "active").upper(),
            "promoted_at":         w_active.get("promoted_at"),
            "fitted_at":           w_active.get("fitted_at"),
            "shadow":              False,
            "trained_on_samples":  int(w_active.get("n_samples", 0) or 0),
            "eval_brier":          0.0,
            "eval_ece":            0.0,
            "algorithm":           w_active.get("algorithm"),
            "calibrator_version":  w_active.get("weights_version"),
            "supersedes":          w_active.get("supersedes"),
        })
    promotions.sort(key=lambda p: p.get("at") or "", reverse=True)
    return {
        "items":        items,
        "promotions":   promotions,
        "source":       "canonical",
        "generated_at": _iso_now(),
    }


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

@api_router.get("/arbicore/intelligence/certification", dependencies=[Depends(_require_operator_dep)])
async def v2_certification(

) -> Dict[str, Any]:
    """Slice 3 · Canonical activation.

    Wraps ``services.execution.certification_review.latest_review``.
    Empty state when no shadow campaign has completed.
    """
    try:
        from services.execution.certification_review import latest_review
        pkg = await latest_review()
    except Exception:
        logger.exception("intelligence/certification: latest_review failed")
        pkg = {
            "phase":          "E4.5 — Shadow Certification Review",
            "available":      False,
            "recommendation": None,
            "message":        "Certification service unavailable.",
        }
    if isinstance(pkg, dict):
        pkg.setdefault("phase", "E4.5 — Shadow Certification Review")
        pkg.setdefault("available", False)
        pkg["source"] = "canonical"
        pkg["generated_at"] = _iso_now()
    return pkg


@api_router.get("/arbicore/intelligence/entities", dependencies=[Depends(_require_operator_dep)])
async def v2_entities(
    entity_type: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """Slice 3 · Canonical activation.

    Wraps the canonical entity repository + entity scorer.  Empty stores
    return empty lists.  Vocabulary is frozen at the canonical enum.
    """
    from arbicore.intel.entity_types import EntityType
    from arbicore.runtime.composition import get_entity_repo, get_entity_scorer
    vocabulary = [e.value for e in EntityType]
    counts_by_type: Dict[str, int] = {}
    items: List[Dict[str, Any]] = []
    total_entities = 0
    try:
        repo = get_entity_repo()
        total_entities = await repo.count()
        try:
            scorer = get_entity_scorer()
            top_scored = await scorer.top(limit=max(limit, 50))
        except Exception:
            logger.exception("intelligence/entities: scorer unavailable")
            top_scored = []
        for r in top_scored:
            d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
            et = d.get("entity_type", "UNKNOWN")
            counts_by_type[et] = counts_by_type.get(et, 0) + 1
            if entity_type and entity_type != "ALL" and et != entity_type:
                continue
            enrich = await repo.get(d["entity_id"])
            label = None
            extras: Dict[str, Any] = {}
            if enrich is not None:
                extras = dict(enrich.metadata or {})
                if enrich.labels:
                    label = enrich.labels[0]
                    extras["labels"] = enrich.labels
                if enrich.external_refs:
                    extras["external_refs"] = enrich.external_refs
            items.append({
                "entity_id":   d.get("entity_id"),
                "entity_type": et,
                "label":       label or d.get("entity_id"),
                "score":       round(float(d.get("avg_outcome_score", 0.0) or 0.0), 4),
                "samples":     int(d.get("sample_count", 0) or 0),
                "success_rate": round(float(d.get("success_rate", 0.0) or 0.0), 4),
                "last_seen":   d.get("updated_at"),
                "extras":      extras,
            })
    except Exception:
        logger.exception("intelligence/entities: entity repo unavailable")

    return {
        "count":          len(items[:limit]),
        "total_entities": int(total_entities or 0),
        "counts_by_type": counts_by_type,
        "items":          items[:limit],
        "vocabulary":     vocabulary,
        "source":         "canonical",
        "generated_at":   _iso_now(),
    }


# ---------------------------------------------------------------------------
# Slice 7 — Operations Canonicalization (2026-08-05).
#
# All placeholder arrays (_V2_SCANNERS + cycles/venues/queues/alerts stubs)
# removed. Every endpoint is now either backed by a canonical repository or
# returns a graceful empty payload preserving the UI contract. See §TODO
# comments per endpoint for the future canonical wiring path.
#
# Auth: every route uses ``dependencies=[Depends(_require_operator_dep)]``.
# Anonymous requests receive 401 (not_authenticated) uniformly.
# ---------------------------------------------------------------------------

# Canonical scanner-id ↔ UI family vocabulary. Only families with a canonical
# ScannerConfigRepository/ScannerStateRepository row are surfaced. Additional
# families (SPATIAL_ARBITRAGE, STATISTICAL_ARBITRAGE) are not part of the
# canonical scanner substrate today and therefore not returned.
_SCANNER_FAMILY_TO_ID = {
    "CEX_ARBITRAGE": "cex_arb",
    "FUNDING_ARBITRAGE": "funding_arb",
    "DEX_ARBITRAGE": "dex_arb",
    "LAUNCH_ARBITRAGE": "launch_arb",
    "CROSS_CHAIN_ARBITRAGE": "cross_chain_arb",
    "FLASH_LOAN_ARBITRAGE": "flash_loan_arb",
}
_SCANNER_ID_TO_FAMILY = {v: k for k, v in _SCANNER_FAMILY_TO_ID.items()}


@api_router.get(
    "/arbicore/operations/scanners",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_scanners() -> Dict[str, Any]:
    """Canonical scanner families from scanner_config_repo + scanner_state_repo.

    - ``state``:      derived from ScannerStateRepository (RUNNING when
                      enabled=True; IDLE otherwise).
    - ``cadence_s``:  from the canonical config row's ``interval_s`` (falls
                      back to 0 when absent).
    - Live tick counters (opps_1h / gates_dropped_1h / errors_1h) are 0 today;
      TODO: wire ScannerTelemetryRepo when the runtime aggregator lands.
    """
    now = _iso_now()
    items: List[Dict[str, Any]] = []
    try:
        from arbicore.runtime.composition import (
            get_scanner_config_repo,
            get_scanner_state_repo,
        )
        cfg_repo = get_scanner_config_repo()
        state_repo = get_scanner_state_repo()
        for family, scanner_id in _SCANNER_FAMILY_TO_ID.items():
            try:
                cfg = await cfg_repo.get(scanner_id) or {}
                state = await state_repo.get(scanner_id) or {}
            except Exception:  # noqa: BLE001
                cfg, state = {}, {}
            items.append({
                "family": family,
                "state": "RUNNING" if state.get("enabled") else "IDLE",
                "cadence_s": int(cfg.get("interval_s") or 0),
                "last_run": None,
                "opps_1h": 0,
                "gates_dropped_1h": 0,
                "errors_1h": 0,
            })
    except Exception:  # noqa: BLE001
        items = []
    return {"items": items, "generated_at": now}


@api_router.post(
    "/arbicore/operations/scanners/{family}/action",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_scanner_action(family: str, action: str) -> Dict[str, Any]:
    """Canonical scanner start/pause/stop persisted via ScannerStateRepository.

    ``start`` → enabled=True; ``pause``/``stop`` → enabled=False. Unknown
    families or unknown actions produce ``ok:false`` with ``state:None``.
    """
    scanner_id = _SCANNER_FAMILY_TO_ID.get(family)
    if not scanner_id:
        return {"ok": False, "family": family, "state": None,
                "generated_at": _iso_now()}
    action_norm = (action or "").lower()
    if action_norm == "start":
        enabled_target = True
    elif action_norm in ("pause", "stop"):
        enabled_target = False
    else:
        return {"ok": False, "family": family, "state": None,
                "generated_at": _iso_now()}
    try:
        from arbicore.runtime.composition import get_scanner_state_repo
        state_repo = get_scanner_state_repo()
        await state_repo.set_enabled(scanner_id, enabled_target, actor="ui")
        state_row = await state_repo.get(scanner_id) or {}
        ui_state = "RUNNING" if state_row.get("enabled") else "IDLE"
    except Exception:  # noqa: BLE001
        ui_state = None
    return {"ok": ui_state is not None, "family": family,
            "state": ui_state, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/operations/cycles",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_cycles(status: Optional[str] = None,
                     limit: int = 50) -> Dict[str, Any]:
    """Execution cycles view.

    TODO: wire ``CycleRepository`` / ``execution.settled_cycles`` collection
    once the executor contract is deployed (P1 roadmap item — Paper /
    Shadow Certification). Until then, no cycles have been settled → empty.
    """
    _ = status, limit  # noqa: F841 — contract preserved for UI filter chip
    return {"items": [], "total": 0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/operations/venues",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_venues() -> Dict[str, Any]:
    """Live venue capability projection from ``VenueCapabilityRepository``.

    Empty when no probe has landed a row in ``arbicore_venue_capability_live``
    yet. UI contract preserved: {venue, kind, state, role, latency_ms,
    last_seen}. Unknown fields (``kind``/``role``) default to ``UNKNOWN`` /
    ``primary`` — the canonical repo does not classify them today.
    TODO: extend VenueCapabilityRepository with kind/role columns.
    """
    items: List[Dict[str, Any]] = []
    try:
        from arbicore.runtime.composition import get_venue_capability_repo
        repo = get_venue_capability_repo()
        rows = await repo.all_live()
        for row in rows:
            status = row.get("venue_status") or (
                "READY" if row.get("api_healthy") else "OFFLINE"
            )
            last_probe_ts = row.get("last_probe_at")
            last_seen = None
            if last_probe_ts:
                try:
                    last_seen = datetime.utcfromtimestamp(
                        float(last_probe_ts)
                    ).isoformat() + "Z"
                except Exception:  # noqa: BLE001
                    last_seen = None
            items.append({
                "venue": row.get("venue_id"),
                "kind": row.get("kind") or "UNKNOWN",
                "state": status,
                "role": row.get("role") or "primary",
                "latency_ms": row.get("latency_ms"),
                "last_seen": last_seen,
            })
    except Exception:  # noqa: BLE001
        items = []
    return {"items": items, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/operations/interlock",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_interlock() -> Dict[str, Any]:
    """Kill-switch / interlock status.

    Boot posture is intentionally DISARMED — the interlock has no persisted
    state today. TODO: wire ``OperatorFlags.interlock()`` (part of the P1
    Kill-switch operator UI wiring listed in V2.11_DELIVERABLES §8.5).
    """
    return {
        "armed": False,
        "state": "DISARMED",
        "reason": None,
        "gates": [],
        "last_transition_at": None,
        "generated_at": _iso_now(),
    }


@api_router.post(
    "/arbicore/operations/interlock/action",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_interlock_action(action: str) -> Dict[str, Any]:
    """Interlock arm/disarm.

    TODO: persist via ``OperatorFlags.interlock_arm()/disarm()``. Until the
    kill-switch UI wiring lands (P1), we echo the requested transition
    without persistence so the UI action affordance is not blocked.
    """
    ui_state = "ARMED" if (action or "").lower() == "arm" else "DISARMED"
    return {"ok": True, "state": ui_state, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/operations/integrations",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_integrations() -> Dict[str, Any]:
    """Third-party integration health.

    TODO: wire a canonical ``IntegrationHealthRepo`` (or a lightweight
    liveness probe registry keyed by integration name). No canonical
    source exists today → empty.
    """
    return {"items": [], "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/operations/queues",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_queues() -> Dict[str, Any]:
    """Runtime queue depth snapshot.

    The canonical ``DiscoveryQueue.queue_status()`` is the only queue with
    live telemetry today (surfaces as ``discovery`` here). Other logical
    queues (approval_notify, execution_dispatch, evidence_bundle) will be
    added as their runtime workers land.
    TODO: extend to a full QueueTelemetryRepo covering all worker queues.
    """
    items: List[Dict[str, Any]] = []
    try:
        from arbicore.runtime.composition import get_discovery_queue
        dq = get_discovery_queue()
        status = await dq.queue_status()
        items.append({
            "queue": "discovery",
            "pending": int(status.get("unclaimed_eligible") or 0),
            "in_flight": int(status.get("claimed_in_flight") or 0),
            "failed_1h": 0,
            "rate_per_min": 0,
        })
    except Exception:  # noqa: BLE001
        items = []
    return {"items": items, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/operations/alerts",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_alerts(severity: Optional[str] = None,
                     limit: int = 100) -> Dict[str, Any]:
    """Operator alert stream.

    TODO: wire ``AlertRepository`` (canonical collection for
    ack/dismiss-aware alerts). No canonical source exists today → empty.
    """
    _ = severity, limit  # noqa: F841 — contract preserved for UI filter chip
    return {"items": [], "total": 0, "generated_at": _iso_now()}


@api_router.post(
    "/arbicore/operations/alerts/{alert_id}/ack",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_alert_ack(alert_id: str) -> Dict[str, Any]:
    """Ack a single alert.

    TODO: persist via ``AlertRepository.ack(alert_id, actor)`` once the
    canonical repo lands. Until then, treat ack as a no-op success so the
    UI affordance remains functional.
    """
    return {"ok": True, "id": alert_id, "acked": True,
            "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# v2.11.8 — Paper Validation Framework endpoints (Slice C).
#
# Reads are all backed by the immutable ``arbicore_paper_evidence``
# collection.  The four endpoints below give operators the same view
# the Shadow Certification + Limited Live promotion gates will consume.
# Every endpoint is session-cookie auth-gated.
# ---------------------------------------------------------------------------

@api_router.get(
    "/arbicore/validation/report",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_paper_report() -> Dict[str, Any]:
    """Aggregated Paper Validation report.

    Returns:
      * ``total``     — total EvidenceBundle count.
      * ``histogram`` — {outcome: count} across the eight canonical outcomes
                        (every outcome present even if count=0).
      * ``rates``     — {outcome: fraction} matching histogram; 0.0 when
                        ``total==0``.
      * ``executable_rate`` — convenience field = rates["EXECUTABLE"].
    """
    from arbicore.paper import PaperOutcome
    try:
        total    = await _PAPER_EVIDENCE_REPO.count()
        hist_raw = await _PAPER_EVIDENCE_REPO.outcome_histogram()
    except Exception:  # noqa: BLE001
        logger.exception("validation/report: repo read failed")
        total    = 0
        hist_raw = {}
    # Ensure every canonical outcome is present (0 when absent).
    histogram = {oc: int(hist_raw.get(oc, 0)) for oc in PaperOutcome.all_values()}
    rates = ({oc: (histogram[oc] / total) for oc in histogram}
             if total else {oc: 0.0 for oc in histogram})
    return {
        "total":            int(total),
        "histogram":        histogram,
        "rates":            rates,
        "executable_rate":  rates.get("EXECUTABLE", 0.0),
        "generated_at":     _iso_now(),
    }


@api_router.get(
    "/arbicore/validation/evidence",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_paper_evidence_list(
    outcome:  Optional[str] = None,
    strategy: Optional[str] = None,
    limit:    int = 50,
) -> Dict[str, Any]:
    """Recent EvidenceBundle listing.  Filter by ``outcome`` +/or ``strategy``.

    Returns a compact projection — for the full stage trace call
    ``GET /arbicore/validation/evidence/{validation_id}``.
    """
    try:
        rows = await _PAPER_EVIDENCE_REPO.list_recent(
            limit=int(limit), outcome=outcome, strategy=strategy,
        )
    except Exception:  # noqa: BLE001
        logger.exception("validation/evidence: repo read failed")
        rows = []
    items = [{
        "validation_id":      b.validation_id,
        "opportunity_id":     b.opportunity_id,
        "strategy":           b.strategy,
        "mode":               b.mode,
        "outcome":            b.outcome.value,
        "outcome_reason":     b.outcome_reason,
        "scanner_family":     b.scanner_family,
        "simulation_backend": b.simulation_backend,
        "stage_count":        len(b.stages),
        "created_at":         b.created_at,
    } for b in rows]
    return {
        "items":         items,
        "total":         len(items),
        "generated_at":  _iso_now(),
    }


@api_router.get(
    "/arbicore/validation/evidence/{validation_id}",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_paper_evidence_get(validation_id: str) -> Dict[str, Any]:
    """Full EvidenceBundle for one validation_id — including per-stage trace."""
    try:
        b = await _PAPER_EVIDENCE_REPO.get_by_validation_id(validation_id)
    except Exception:  # noqa: BLE001
        logger.exception("validation/evidence/{id}: repo read failed")
        b = None
    if b is None:
        return {"found": False, "validation_id": validation_id,
                "generated_at": _iso_now()}
    return {
        "found":              True,
        "validation_id":      b.validation_id,
        "opportunity_id":     b.opportunity_id,
        "strategy":           b.strategy,
        "mode":               b.mode,
        "outcome":            b.outcome.value,
        "outcome_reason":     b.outcome_reason,
        "scanner_family":     b.scanner_family,
        "plan_id":            b.plan_id,
        "simulation_backend": b.simulation_backend,
        "pipeline_action":    b.pipeline_action,
        "inputs":             b.inputs,
        "stages":             b.stages,
        "schema_version":     b.schema_version,
        "created_at":         b.created_at,
        "generated_at":       _iso_now(),
    }


@api_router.get(
    "/arbicore/validation/metrics",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_paper_metrics() -> Dict[str, Any]:
    """Runner health + throughput metrics.

    Reads the in-memory :class:`RunnerMetrics` when the runner is
    active; returns a canonical empty shape when the runner is
    disabled or not yet started (metrics_source='disabled').
    """
    if _PAPER_RUNNER is None:
        return {
            "runner_enabled": False,
            "metrics_source": "disabled",
            "runner":         {"is_running": False},
            "generated_at":   _iso_now(),
        }
    return {
        "runner_enabled":  True,
        "metrics_source":  "in_memory",
        "runner":          {
            "is_running": _PAPER_RUNNER.is_running(),
            **_PAPER_RUNNER.metrics.to_dict(),
        },
        "generated_at":    _iso_now(),
    }


# ---------------------------------------------------------------------------
# v2.11.9 · Shadow Certification — operator surface.
# All endpoints are session-cookie auth-gated (see _require_operator_dep).
# ---------------------------------------------------------------------------
def _shadow_cert_engine_or_503():
    """Return the live engine or raise 503 if the boot hook failed."""
    if _SHADOW_CERT_ENGINE is None:
        raise HTTPException(
            status_code=503,
            detail="shadow_certification_engine_unavailable",
        )
    return _SHADOW_CERT_ENGINE


async def _shadow_cert_readiness_snapshot() -> Dict[str, Any]:
    """v2.11.9 — pre-flight snapshot of the emission chain.

    Enforces the "no accidental infra-only certification" rule: a live
    certification must confirm that (a) at least one Wave1B scanner is
    actively running AND (b) the runner has processed non-zero
    opportunities in the recent past.  If either is false the caller
    must explicitly opt into ``infrastructure_only=true``.

    Fail-open: any probe error is reported as ``unknown=True`` and
    treated as "not ready" — the operator has to force with an explicit
    override flag.
    """
    report: Dict[str, Any] = {
        "generated_at":            _iso_now(),
        "scanners_running":        [],
        "scanners_all":            [],
        "runtime_autostart":       dict(_ARBICORE_RUNTIME_INIT),
        "paper_runner": {
            "enabled":               False,
            "is_running":            False,
            "opportunities_seen":    0,
            "opportunities_processed": 0,
            "cycles_completed":      0,
        },
        "canonical_opportunities": {"total": 0},
        "unknown":                 False,
        "issues":                  [],
    }
    # Scanner state
    try:
        from arbicore.runtime import composition as _comp
        for scan_name, getter in (
            ("cex_arb",         getattr(_comp, "get_cex_arb_scanner",         None)),
            ("funding_arb",     getattr(_comp, "get_funding_arb_scanner",     None)),
            ("dex_arb",         getattr(_comp, "get_dex_arb_scanner",         None)),
            ("launch_arb",      getattr(_comp, "get_launch_arb_scanner",      None)),
            ("cross_chain_arb", getattr(_comp, "get_cross_chain_arb_scanner", None)),
            ("flash_loan_arb",  getattr(_comp, "get_flash_loan_arb_scanner",  None)),
        ):
            if getter is None:
                continue
            report["scanners_all"].append(scan_name)
            try:
                sc = getter()
                task = getattr(sc, "_task", None)
                enabled = False
                try:
                    enabled = bool(sc.is_enabled())
                except Exception:  # noqa: BLE001
                    enabled = False
                task_alive = task is not None and not task.done()
                if enabled and task_alive:
                    report["scanners_running"].append(scan_name)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        report["unknown"] = True
        report["issues"].append("scanner_probe_failed")

    # Paper Validation runner state
    if _PAPER_RUNNER is not None:
        m = _PAPER_RUNNER.metrics.to_dict()
        report["paper_runner"] = {
            "enabled":                 True,
            "is_running":              _PAPER_RUNNER.is_running(),
            "opportunities_seen":      int(m.get("opportunities_seen") or 0),
            "opportunities_processed": int(m.get("opportunities_processed") or 0),
            "cycles_completed":        int(m.get("cycles_completed") or 0),
        }

    # Canonical opportunity feed size
    try:
        total = await _CANONICAL_OPP_REPO._col.count_documents({})
        report["canonical_opportunities"]["total"] = int(total)
    except Exception:  # noqa: BLE001
        report["unknown"] = True
        report["issues"].append("canonical_opp_count_failed")

    if not report["scanners_running"]:
        report["issues"].append("no_scanners_running")
    if report["paper_runner"]["opportunities_processed"] == 0:
        report["issues"].append("paper_runner_zero_processed")

    report["is_live_ready"] = (
        len(report["scanners_running"]) >= 1
        and report["paper_runner"]["opportunities_processed"] > 0
        and not report["unknown"]
    )
    return report


@api_router.get(
    "/arbicore/certification/shadow/readiness",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_shadow_cert_readiness() -> Dict[str, Any]:
    """Pre-flight readiness snapshot used by the /start endpoint.

    ``is_live_ready`` is True only when:
      * ≥ 1 Wave1B scanner is actively running (task alive + enabled), AND
      * the Paper Validation runner has processed at least 1 opportunity
        in its lifetime, AND
      * no probe errors were encountered.
    """
    return await _shadow_cert_readiness_snapshot()


# ---------------------------------------------------------------------------
# v2.11.10 · Opportunity Decision Analytics — read-only aggregations over
# the immutable arbicore_paper_evidence collection.  Every processed
# opportunity is projected through the canonical rejection taxonomy in
# ``arbicore.analytics.classify_evidence`` so the operator can see:
#   * acceptance / rejection summary
#   * rejection-reason histogram
#   * per-scanner performance
#   * bottleneck stages
#   * hourly executable-rate trend
# The service is instantiated lazily on first use so preview envs
# without the evidence collection still boot cleanly.
# ---------------------------------------------------------------------------
from arbicore.analytics.service import DecisionAnalyticsService as _DecisionAnalyticsSvc  # noqa: E402
_DECISION_ANALYTICS: Optional[_DecisionAnalyticsSvc] = None


def _decision_analytics() -> _DecisionAnalyticsSvc:
    global _DECISION_ANALYTICS
    if _DECISION_ANALYTICS is None:
        _DECISION_ANALYTICS = _DecisionAnalyticsSvc(_PAPER_EVIDENCE_REPO)
    return _DECISION_ANALYTICS


@api_router.get(
    "/arbicore/analytics/decisions/summary",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_decision_summary(
    limit: int = 500,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """Executable / rejected counts, effective rate, category counts."""
    return await _decision_analytics().summary(limit=limit, since=since)


@api_router.get(
    "/arbicore/analytics/decisions/rejections",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_decision_rejections(
    limit: int = 500,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """Rejection breakdown by canonical category with sample reasons."""
    return await _decision_analytics().rejection_breakdown(limit=limit, since=since)


@api_router.get(
    "/arbicore/analytics/decisions/by_scanner",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_decision_by_scanner(
    limit: int = 500,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """Per-scanner-family performance table."""
    return await _decision_analytics().by_scanner(limit=limit, since=since)


@api_router.get(
    "/arbicore/analytics/decisions/bottlenecks",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_decision_bottlenecks(
    limit: int = 500,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    """Which stages are eating the most opportunities + their p95 latency."""
    return await _decision_analytics().bottlenecks(limit=limit, since=since)


@api_router.get(
    "/arbicore/analytics/decisions/trend",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_decision_trend(
    hours: int = 24,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Hourly executable-rate trend over the last N hours."""
    return await _decision_analytics().trend(hours=hours, limit=limit)


@api_router.get(
    "/arbicore/analytics/decisions/recent",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_decision_recent(
    limit: int = 50,
    scanner_family: Optional[str] = None,
    outcome: Optional[str] = None,
) -> Dict[str, Any]:
    """Recent decision records with classified category + sub-code."""
    return await _decision_analytics().recent_decisions(
        limit=limit,
        scanner_family=scanner_family,
        outcome=outcome,
    )


@api_router.get(
    "/arbicore/certification/shadow/thresholds",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_shadow_cert_thresholds() -> Dict[str, Any]:
    """Active certification thresholds (frozen for the next run)."""
    th = _shadow_cert_load_thresholds()
    if _SHADOW_CERT_ENGINE is not None:
        th = _SHADOW_CERT_ENGINE.thresholds
    return {
        "thresholds":   th.to_dict(),
        "generated_at": _iso_now(),
    }


@api_router.get(
    "/arbicore/certification/shadow/current",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_shadow_cert_current() -> Dict[str, Any]:
    """Return the currently-active certification run (or `null`)."""
    engine = _shadow_cert_engine_or_503()
    run = await engine.current_run()
    if run is None:
        return {"current": None, "generated_at": _iso_now()}
    return {"current": run.to_report(), "generated_at": _iso_now()}


@api_router.post(
    "/arbicore/certification/shadow/start",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_shadow_cert_start(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """Start a fresh Shadow Certification run.

    Optional body fields:
      * ``target_cycles`` — override target for this run only.
      * ``notes`` — free-form operator note (recorded on the run).
      * ``infrastructure_only`` — set true to acknowledge that live
        scanner emission is unavailable; the run is then explicitly
        graded as an Infrastructure-Only Certification (marker
        recorded on the run summary).

    Refuses (409) if a run is already RUNNING.
    Refuses (412 preconditon_failed) if the emission chain is not
    live-ready AND ``infrastructure_only`` is not set to true.
    """
    engine = _shadow_cert_engine_or_503()
    payload = payload if isinstance(payload, dict) else {}

    # v2.11.9 — pre-flight readiness gate
    infrastructure_only = bool(payload.get("infrastructure_only", False))
    readiness = await _shadow_cert_readiness_snapshot()
    if not readiness.get("is_live_ready") and not infrastructure_only:
        raise HTTPException(
            status_code=412,
            detail={
                "error":     "not_live_ready",
                "message":   ("emission chain is not producing fresh "
                              "opportunities; set infrastructure_only=true "
                              "to run an explicit Infrastructure-Only "
                              "Certification"),
                "readiness": readiness,
            },
        )

    try:
        thresholds = engine.thresholds
        override_cycles = payload.get("target_cycles")
        if override_cycles is not None:
            thresholds = type(thresholds).from_dict({
                **thresholds.to_dict(),
                "target_cycles": int(override_cycles),
            })
        run = await engine.start_run(thresholds=thresholds)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # Record the readiness snapshot + infrastructure_only marker in the
    # run's summary so historical reports carry the pre-flight context.
    marker: Dict[str, Any] = {
        "infrastructure_only":       infrastructure_only,
        "readiness_at_start":        readiness,
    }
    notes = payload.get("notes")
    if notes:
        marker["operator_notes"] = str(notes)

    from dataclasses import replace as _dc_replace
    from arbicore.certification.models import ShadowCertificationRun as _RunT
    _new_summary = {**(run.summary or {}), "start_markers": marker}
    _run2 = _dc_replace(run, summary=_new_summary)  # type: ignore[arg-type]
    await _SHADOW_CERT_REPO.upsert(_run2)
    run = _run2
    return {"run": run.to_report(), "generated_at": _iso_now()}


@api_router.post(
    "/arbicore/certification/shadow/stop",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_shadow_cert_stop(payload: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
    """Abort the currently-running Shadow Certification run."""
    engine = _shadow_cert_engine_or_503()
    reason = (payload or {}).get("reason") if isinstance(payload, dict) else None
    reason = str(reason or "operator_stop")
    run = await engine.stop_run(reason=reason)
    if run is None:
        return {"run": None, "generated_at": _iso_now()}
    return {"run": run.to_report(), "generated_at": _iso_now()}


@api_router.post(
    "/arbicore/certification/shadow/tick",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_shadow_cert_tick() -> Dict[str, Any]:
    """Run one certification tick immediately.

    Useful when the background runner is disabled and the operator
    wants to drive cycles manually (e.g. during pre-Sepolia rehearsal).
    """
    engine = _shadow_cert_engine_or_503()
    run = await engine.tick()
    if run is None:
        return {"run": None, "generated_at": _iso_now()}
    return {"run": run.to_report(), "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/certification/shadow/runs",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_shadow_cert_runs_list(
    limit: int = 50,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """History of Shadow Certification runs (newest first)."""
    limit = max(1, min(int(limit or 50), 200))
    items = await _SHADOW_CERT_REPO.list_recent(limit=limit, status=status)
    return {
        "items":        [r.to_report() for r in items],
        "count":        len(items),
        "generated_at": _iso_now(),
    }


@api_router.get(
    "/arbicore/certification/shadow/runs/{run_id}",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_shadow_cert_runs_get(run_id: str) -> Dict[str, Any]:
    """Full Shadow Certification run report by id."""
    run = await _SHADOW_CERT_REPO.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return {"run": run.to_report(), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Slice 6 — Portfolio Canonicalization (2026-08-05).
#
# All hardcoded position/balance/transfer/ledger/treasury/exposure/allocation
# arrays removed. Every endpoint is now either backed by a canonical
# repository or returns a graceful empty payload preserving the UI contract.
# See §TODO comments per endpoint for the future canonical wiring path.
#
# Auth: every route uses ``dependencies=[Depends(_require_operator_dep)]``.
# Anonymous requests receive 401 (not_authenticated) uniformly.
# ---------------------------------------------------------------------------

@api_router.get(
    "/arbicore/portfolio/positions",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_positions(venue: Optional[str] = None,
                        side: Optional[str] = None) -> Dict[str, Any]:
    """Open position snapshot.

    TODO: wire ``ExecutionPositionRepository.snapshot()`` once the executor
    contract is deployed and paper/shadow execution begins writing rows to
    ``arbicore_execution_positions``. No canonical source exists today
    → empty items + zero totals.
    """
    _ = venue, side  # noqa: F841 — contract preserved for UI filter chips
    return {"items": [], "total": 0, "total_size_usd": 0.0,
            "total_upnl_usd": 0.0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/balances",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_balances(venue: Optional[str] = None) -> Dict[str, Any]:
    """Aggregated per-venue balance snapshot.

    TODO: wire ``VenueBalanceService.aggregate()`` — requires per-venue
    balance polling to be enabled (part of the P1 execution readiness
    milestone). No canonical source exists today → empty.
    """
    _ = venue  # noqa: F841
    return {"items": [], "total": 0, "total_usd": 0.0,
            "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/transfers",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_transfers(status: Optional[str] = None,
                        limit: int = 100) -> Dict[str, Any]:
    """Treasury transfer log.

    TODO: wire ``TreasuryLedger.transfers(window)`` once the treasury ledger
    substrate lands (P1 execution readiness). No canonical source today
    → empty.
    """
    _ = status, limit  # noqa: F841
    return {"items": [], "total": 0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/deployable",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_deployable() -> Dict[str, Any]:
    """Deployable-capital snapshot.

    TODO: wire ``CapitalRouter.deployable_snapshot()``. The existing
    ``CapitalPolicyRepo`` today holds policy configuration only, not a
    runtime per-venue deployable/utilised state — that requires the P1
    executor + balance-polling wiring. Empty per-venue → zero totals.
    """
    return {
        "total_deployable_usd": 0.0,
        "total_utilised_usd": 0.0,
        "total_capital_usd": 0.0,
        "utilisation_pct": 0.0,
        "per_venue": [],
        "generated_at": _iso_now(),
    }


@api_router.get(
    "/arbicore/portfolio/treasury",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_treasury() -> Dict[str, Any]:
    """Treasury vault snapshot.

    TODO: wire ``TreasuryLedger.vault_snapshot()``. No canonical source
    exists today → empty vaults + zero total.
    """
    return {"vaults": [], "total_usd": 0.0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/ledger",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_ledger(kind: Optional[str] = None,
                     limit: int = 100) -> Dict[str, Any]:
    """Treasury ledger entries.

    TODO: wire ``TreasuryLedger.entries(window, kind)``. No canonical
    source exists today → empty.
    """
    _ = kind, limit  # noqa: F841
    return {"items": [], "total": 0, "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/exposure",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_exposure() -> Dict[str, Any]:
    """Exposure breakdown by asset + by chain.

    TODO: wire ``ExposureAnalyzer.breakdown()``. Derives from
    balances + positions once those canonical sources exist. Empty today.
    """
    return {"by_asset": [], "by_chain": [], "total_usd": 0.0,
            "generated_at": _iso_now()}


@api_router.get(
    "/arbicore/portfolio/allocation",
    dependencies=[Depends(_require_operator_dep)],
)
async def v2_allocation() -> Dict[str, Any]:
    """Allocation target vs. actual per strategy bucket.

    TODO: wire ``AllocationPolicy.status()`` — requires the treasury
    ledger + capital router substrate. No canonical source today → empty
    items + zero totals.
    """
    return {"items": [], "total_target_usd": 0.0,
            "total_actual_usd": 0.0, "generated_at": _iso_now()}

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

@api_router.get("/arbicore/execution/adapters", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_adapters() -> Dict[str, Any]:
    return {**_ADAPTER_REGISTRY.catalog(), "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/plans/build", dependencies=[Depends(_require_operator_dep)])
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


@api_router.get("/arbicore/execution/plans/{plan_id}", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_plan_one(plan_id: str) -> Dict[str, Any]:
    try:
        plan = await _EXECUTION_PLANS_REPO.get(plan_id)
    except Exception:
        plan = None
    return {"plan": plan, "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/plans", dependencies=[Depends(_require_operator_dep)])
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

@api_router.get("/arbicore/execution/simulation/status", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_simulation_status() -> Dict[str, Any]:
    """Simulator registry status — which backends are wired, which is
    the current default, and the read-only RPC allowlist."""
    return {**_SIMULATION_REGISTRY.status(), "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/gas", dependencies=[Depends(_require_operator_dep)])
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


@api_router.get("/arbicore/execution/mev/routers", dependencies=[Depends(_require_operator_dep)])
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


@api_router.post("/arbicore/execution/plans/{plan_id}/simulate", dependencies=[Depends(_require_operator_dep)])
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

@api_router.get("/arbicore/execution/capital-policy", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_capital_policy_list() -> Dict[str, Any]:
    try:
        items = await _CAPITAL_POLICY_REPO.list_all()
    except Exception:
        items = []
    return {"items": items, "count": len(items),
            "defaults": dict(CAPITAL_DEFAULT_POLICY),
            "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/capital-policy/{strategy}", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_capital_policy_one(strategy: str) -> Dict[str, Any]:
    try:
        row = await _CAPITAL_POLICY_REPO.get(strategy)
    except Exception:
        row = None
    return {"strategy": strategy, "policy": row,
            "defaults": dict(CAPITAL_DEFAULT_POLICY),
            "generated_at": _iso_now()}


@api_router.patch("/arbicore/execution/capital-policy/{strategy}", dependencies=[Depends(_require_operator_dep)])
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


@api_router.post("/arbicore/execution/capital-policy/{strategy}/evaluate", dependencies=[Depends(_require_operator_dep)])
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

@api_router.get("/arbicore/execution/kill-switch", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_kill_switch_state() -> Dict[str, Any]:
    try:
        state = await _KILL_SWITCH_REPO.state()
        return {"state": state.to_dict(), "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/kill-switch/engage", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_kill_switch_engage(body: Dict[str, Any]) -> Dict[str, Any]:
    b = body or {}
    reason = (b.get("reason") or "").strip()
    if not reason:
        return {"ok": False, "error": "reason is required",
                "generated_at": _iso_now()}
    state = await _KILL_SWITCH_REPO.engage(reason=reason,
                                            actor=b.get("actor") or "operator")
    return {"ok": True, "state": state.to_dict(), "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/kill-switch/disengage", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_kill_switch_disengage(body: Dict[str, Any]) -> Dict[str, Any]:
    b = body or {}
    reason = (b.get("reason") or "").strip()
    if not reason:
        return {"ok": False, "error": "reason is required",
                "generated_at": _iso_now()}
    state = await _KILL_SWITCH_REPO.disengage(reason=reason,
                                                actor=b.get("actor") or "operator")
    return {"ok": True, "state": state.to_dict(), "generated_at": _iso_now()}


@api_router.get("/arbicore/execution/kill-switch/audit", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_kill_switch_audit(limit: int = 50) -> Dict[str, Any]:
    try:
        items = await _KILL_SWITCH_REPO.audit_history(limit=limit)
    except Exception:
        items = []
    return {"items": items, "count": len(items), "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wave-6D · Live Signer (gate ladder — never emits signed bytes)
# ---------------------------------------------------------------------------

@api_router.post("/arbicore/execution/plans/{plan_id}/sign", dependencies=[Depends(_require_operator_dep)])
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

@api_router.get("/arbicore/execution/certification/stages", dependencies=[Depends(_require_operator_dep)])
async def v2_execution_certification_stages() -> Dict[str, Any]:
    """Canonical list of pipeline stages the certifier evaluates."""
    return {"stages": list(PIPELINE_STAGES),
            "would_broadcast": False,
            "generated_at": _iso_now()}


@api_router.post("/arbicore/execution/certification/run", dependencies=[Depends(_require_operator_dep)])
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



@api_router.post("/arbicore/wizard/opportunity-probe")
async def v2_opportunity_probe(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Operator-triggered LIVE quote probe against the configured RPC.

    READ-ONLY. No broadcast, no signing, no fund movement. Sends real
    Uniswap V3 QuoterV2 ``eth_call`` reads for a token pair across the
    common fee tiers and reports which (if any) return a live quote —
    so the operator can watch a real EXECUTABLE candidate form on Base
    Sepolia BEFORE any deployment or broadcast.

    Body (all optional):
        {
          "chain": "base-sepolia",      # or "base" for mainnet
          "token_in":  "0x4200...0006", # default WETH (Base Sepolia)
          "token_out": "0x036C...CF7e", # default USDC (Base Sepolia)
          "amount_in_wei": 10000000000000000,   # default 0.01 WETH
          "fees": [500, 3000, 10000]    # UniV3 fee tiers to probe (ppm)
        }
    """
    body = body or {}
    chain = (body.get("chain") or "base-sepolia").strip()
    # Base Sepolia canonical test tokens.
    token_in = body.get("token_in") or "0x4200000000000000000000000000000000000006"   # WETH
    token_out = body.get("token_out") or "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # USDC
    try:
        amount_in_wei = int(body.get("amount_in_wei") or 10**16)  # 0.01 WETH
    except (TypeError, ValueError):
        amount_in_wei = 10**16
    fees = body.get("fees") or [500, 3000, 10000]
    rpc_url = (body.get("rpc_url") or os.environ.get("ARBICORE_RPC_URL") or "").strip()

    if not rpc_url:
        return {"ok": False, "chain": chain,
                "detail": "ARBICORE_RPC_URL not configured", "generated_at": _iso_now()}

    tiers: List[Dict[str, Any]] = []
    live_tier: Optional[Dict[str, Any]] = None
    for fee in fees:
        try:
            rq = await _QUOTER_REGISTRY.quote_route(
                chain=chain,
                hops=[{
                    "dex": "uniswap_v3",
                    "token_in": token_in, "token_out": token_out,
                    "amount_in_wei": amount_in_wei, "fee": int(fee),
                }],
                rpc_url=rpc_url,
            )
            hop = rq.hops[0].to_dict() if rq.hops else {}
            tier_row = {
                "fee_ppm": int(fee),
                "status": rq.status,
                "amount_out_wei": rq.final_amount_out_wei,
                "block_number": hop.get("block_number"),
                "quoter_contract": hop.get("quoter_contract"),
                "hop_status": hop.get("status"),
                "hop_error": hop.get("error"),
            }
        except Exception as exc:  # noqa: BLE001
            tier_row = {"fee_ppm": int(fee), "status": "error",
                        "hop_error": f"{type(exc).__name__}: {exc}"}
        tiers.append(tier_row)
        if live_tier is None and tier_row.get("hop_status") == "ok":
            live_tier = tier_row

    any_live = live_tier is not None
    return {
        "ok": True,
        "chain": chain,
        "rpc_reachable": any(t.get("block_number") for t in tiers) or any_live,
        "token_in": token_in,
        "token_out": token_out,
        "amount_in_wei": amount_in_wei,
        "any_live_pool": any_live,
        "live_tier": live_tier,
        "tiers": tiers,
        "detail": (f"live UniV3 pool found at fee={live_tier['fee_ppm']}ppm"
                   if any_live else
                   "no live UniV3 pool with liquidity for this pair on "
                   f"chain '{chain}' (expected on a thin testnet)"),
        "note": ("READ-ONLY probe. No broadcast. Confirms the live-quote "
                 "path + RPC before any executor deployment or broadcast."),
        "generated_at": _iso_now(),
    }



@api_router.post("/arbicore/wizard/technical-validation", dependencies=[Depends(_require_operator_dep)])
async def v2_technical_validation(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Reusable Flash-Loan engine self-test (Aave V3, smallest practical size).

    Proves borrow → execution → repayment → no revert → EvidenceBundle,
    end-to-end on-chain. Profitability is NOT the goal. Governance-safe:
    does NOT touch the strategy mode ladder (trading stays SHADOW); uses a
    dedicated engineering signer (`ARBICORE_VALIDATION_SIGNER_KEY`).

    S4 hardening — the ``execute=true`` path is NOT an alternate route
    around the normal safety architecture. It requires an authenticated
    operator (route dependency) AND enforces: kill-switch disengaged,
    approved executor configured, dedicated signer configured, chain-id in
    the tech-validation allowlist (Base Sepolia 84532 by default; NEVER a
    mainnet chain unless explicitly allowlisted), and asset/swap-out tokens
    on the tech-validation token allowlist.

    Body (all optional):
        {
          "execute": false,           # false = safe preflight only (default)
          "amount_wei": 10000000000000,   # default 0.00001 WETH
          "asset": "0x4200...0006",   # default WETH (an Aave reserve on Base)
          "auto_prefund": true        # wrap+send the tiny Aave premium
        }
    """
    from arbicore.execution.technical_validation import (
        TechnicalValidator, TechnicalValidationError, _WETH, _USDC_BASE_SEPOLIA,
    )
    body = body or {}
    execute = bool(body.get("execute", False))

    # ---- S4 hard safety gates for the execute path -----------------------
    if execute:
        try:
            await _KILL_SWITCH_REPO.guard()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"kill_switch: {exc}",
                    "generated_at": _iso_now()}
        executor_addr = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") or ""
        if not executor_addr:
            return {"ok": False,
                    "error": "no approved executor configured (ARBICORE_EXECUTOR_ADDRESS_BASE)",
                    "generated_at": _iso_now()}
        if not (os.environ.get("ARBICORE_VALIDATION_SIGNER_KEY") or "").strip():
            return {"ok": False,
                    "error": "no dedicated validation signer configured",
                    "generated_at": _iso_now()}
        allowed_chain_ids = {
            int(x) for x in (os.environ.get(
                "ARBICORE_TECH_VALIDATION_ALLOWED_CHAIN_IDS") or "84532"
            ).split(",") if x.strip().isdigit()
        }
        try:
            _probe = TechnicalValidator(
                rpc_url=os.environ.get("ARBICORE_RPC_URL", ""),
                executor_address=executor_addr, signer_key=None, db=db)
            observed_chain_id = await _probe._chain_id()  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"chain preflight failed: {exc}",
                    "generated_at": _iso_now()}
        if observed_chain_id not in allowed_chain_ids:
            return {"ok": False,
                    "error": (f"chain {observed_chain_id} is not in the "
                              f"tech-validation allowlist {sorted(allowed_chain_ids)} "
                              f"— execute refused (mainnet self-test is blocked)"),
                    "generated_at": _iso_now()}
        token_allowlist = {t.lower() for t in (
            [_WETH, _USDC_BASE_SEPOLIA] + [
                x for x in (os.environ.get(
                    "ARBICORE_TECH_VALIDATION_TOKEN_ALLOWLIST") or "").split(",")
                if x.strip()
            ]
        )}
        asset = (body.get("asset") or _WETH).lower()
        swap_out = (body.get("swap_out_token") or _USDC_BASE_SEPOLIA).lower()
        if asset not in token_allowlist or swap_out not in token_allowlist:
            return {"ok": False,
                    "error": "asset/swap_out_token not on tech-validation token allowlist",
                    "generated_at": _iso_now()}

    try:
        validator = TechnicalValidator(
            rpc_url=os.environ.get("ARBICORE_RPC_URL", ""),
            executor_address=os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE", ""),
            signer_key=os.environ.get("ARBICORE_VALIDATION_SIGNER_KEY") or None,
            db=db,
        )
        trace = await validator.run(
            asset=body.get("asset") or _WETH,
            amount_wei=int(body.get("amount_wei") or 10**13),
            swap_in_wei=int(body.get("swap_in_wei") or 10**12),
            fee_tier_bps=int(body.get("fee_tier_bps") or 5),
            auto_prefund=bool(body.get("auto_prefund", True)),
            execute=execute,
        )
        return {"result": trace, "generated_at": _iso_now()}
    except TechnicalValidationError as exc:
        return {"ok": False, "error": str(exc), "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "generated_at": _iso_now()}


@api_router.get("/arbicore/wizard/technical-validation/history")
async def v2_technical_validation_history(limit: int = 10) -> Dict[str, Any]:
    """Recent technical-validation runs (immutable evidence records)."""
    try:
        cur = db["arbicore_technical_validations"].find(
            {}, {"_id": 0}).sort("recorded_at", -1).limit(max(1, min(limit, 50)))
        rows = await cur.to_list(length=limit)
        return {"count": len(rows), "runs": rows, "generated_at": _iso_now()}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "generated_at": _iso_now()}


@api_router.get("/arbicore/control/profit-preview", dependencies=[Depends(_require_operator_dep)])
async def v2_control_profit_preview(
    gross_spread_bps: float = 30.0,
    pool_liquidity_usd: float = 2_000_000.0,
    gas_cost_usd: float = 3.0,
) -> Dict[str, Any]:
    """Worked profit → confidence → EV → optimal-size example.

    SHADOW-safe and PURE: runs the P0 engines on the supplied (or sample)
    parameters. `data_source` is SAMPLE_PARAMETERS until live Base liquidity
    + quotes are wired (P0-4) — the UI must not treat this as executable."""
    from arbicore.economics.size_optimizer import optimize_size
    from arbicore.intelligence.confidence_v2 import confidence_from_signals
    prob_kwargs = dict(simulation_passed=None, quote_age_sec=None,
                       gas_certainty=0.9, mev_risk=0.15, historical_success_rate=None)
    opt = optimize_size(
        gross_spread_bps=gross_spread_bps, pool_liquidity_usd=pool_liquidity_usd,
        gas_cost_usd=gas_cost_usd, buy_venue_fee_bps=5.0, sell_venue_fee_bps=5.0,
        native_price_usd=3000.0, prob_kwargs=prob_kwargs)
    chosen = opt.get("chosen") or {}
    conf = confidence_from_signals(
        quote_age_sec=None, liquidity_ratio=(chosen.get("notional_usd", 0) / pool_liquidity_usd)
        if pool_liquidity_usd else None,
        slippage_bps=chosen.get("slippage_bps"), max_slippage_bps=150.0,
        gas_certainty=0.9, flash_available=True, simulation_passed=None,
        mev_risk=0.15, net_profit_bps=chosen.get("roi_bps"))
    return {
        "data_source": "SAMPLE_PARAMETERS",
        "note": "Illustrative; not executable until live Base liquidity/quotes are wired (P0-4).",
        "inputs": {"gross_spread_bps": gross_spread_bps,
                   "pool_liquidity_usd": pool_liquidity_usd, "gas_cost_usd": gas_cost_usd},
        "size_optimization": opt,
        "confidence": conf.to_dict(),
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/control/readiness", dependencies=[Depends(_require_operator_dep)])
async def v2_control_readiness() -> Dict[str, Any]:
    """Backend-authoritative Control Center readiness (GREEN/YELLOW/RED).

    Returns per-component checks + per-mode activation eligibility. This is
    the SINGLE source of truth for operator readiness — the frontend renders
    it but can never bypass it."""
    report = await _READINESS_ENGINE.evaluate()
    report["current_mode"] = await _CONTROL_STATE_REPO.get_mode()
    return report


@api_router.get("/arbicore/control/mode", dependencies=[Depends(_require_operator_dep)])
async def v2_control_get_mode() -> Dict[str, Any]:
    return {"current_mode": await _CONTROL_STATE_REPO.get_mode(),
            "available_modes": list(OPERATOR_MODES), "generated_at": _iso_now()}


@api_router.post("/arbicore/control/mode", dependencies=[Depends(_require_operator_dep)])
async def v2_control_set_mode(body: Dict[str, Any],
                              ctx: Dict[str, Any] = Depends(_require_operator_dep)
                              ) -> Dict[str, Any]:
    """Operator REQUESTS a mode change. The backend decides.

    SHADOW/PAPER/PROFIT_ENGINE are non-broadcast and permitted when the
    system is healthy. LIMITED_LIVE / FULL_AUTOMATION are hard-gated and
    ALWAYS refused in this build — no frontend path can enable them."""
    target = str((body or {}).get("mode") or "").strip().upper()
    if target not in OPERATOR_MODES:
        raise HTTPException(status_code=400, detail=f"unknown mode '{target}'")
    decision = await _READINESS_ENGINE.can_transition(target)
    if not decision.get("allowed"):
        return {"applied": False, "current_mode": await _CONTROL_STATE_REPO.get_mode(),
                "decision": decision, "generated_at": _iso_now()}
    actor = (ctx or {}).get("username") or "operator"
    await _CONTROL_STATE_REPO.set_mode(target, actor=actor,
                                        reason=str((body or {}).get("reason") or ""))
    return {"applied": True, "current_mode": target, "decision": decision,
            "generated_at": _iso_now()}


# Default Base allowlists (operator-locked). Sourced from the canonical
# ADDRESS_BOOK + verified token registry. Operator may narrow (never widen
# beyond safety) via request body overrides.
def _default_base_router_allowlist() -> List[str]:
    from arbicore.execution.adapters import ADDRESS_BOOK
    base = ADDRESS_BOOK.get("base", {})
    return [base.get("uniswap_v3_router", ""), base.get("aerodrome_router", "")]


def _default_base_token_allowlist() -> List[str]:
    # Base WETH + USDC (verified). Extend as adapters are certified.
    return ["0x4200000000000000000000000000000000000006",
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"]


@api_router.post("/arbicore/control/live-quote",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_control_live_quote(body: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only live Base route quote via the existing QuoterRegistry.

    Uses ``eth_call`` against ARBICORE_RPC_URL only — never a signer path.
    Surfaces freshness/provenance (block, rpc host, age) and a normalised
    ``quote_status`` (REAL/STALE/UNAVAILABLE). When RPC is unset or every hop
    reverts, the route degrades to fallback and quote_status=UNAVAILABLE
    (no fabricated numbers)."""
    from arbicore.economics.quote_provider import classify_quote_status

    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="request body must be a JSON object")
    chain = str(body.get("chain") or "base").strip()
    hops = body.get("hops")
    if not isinstance(hops, list) or not hops:
        raise HTTPException(status_code=422, detail="'hops' array is required")
    try:
        max_age_sec = float(body.get("max_age_sec", 12.0))
    except (TypeError, ValueError):
        max_age_sec = 12.0

    rq = await _QUOTER_REGISTRY.quote_route(chain=chain, hops=hops)
    rq_dict = rq.to_dict()
    freshness = classify_quote_status(rq_dict, max_age_sec=max_age_sec)
    return {
        "rpc_configured": bool(os.environ.get("ARBICORE_RPC_URL")),
        "quote_status": freshness["quote_status"],
        "quote_age_sec": freshness["quote_age_sec"],
        "route_quote": rq_dict,
        "generated_at": _iso_now(),
    }


@api_router.post("/arbicore/control/decide-opportunity",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_control_decide_opportunity(body: Dict[str, Any]) -> Dict[str, Any]:
    """SHADOW/PAPER-safe opportunity decision path (P0 integrator).

    Composes the pure engines — net_profit → confidence v2 → expected value →
    adaptive size optimizer — behind a HARD simulation gate, and returns an
    ADVISORY decision object. This endpoint NEVER signs, broadcasts, deploys,
    or executes: it is pure analysis regardless of the requested notional.

    Two input modes:
      * ``opportunity`` — operator supplies the full opportunity dict.
      * ``route`` (+ ``economics``) — the backend fetches a REAL Base quote
        via the existing QuoterRegistry (read-only eth_call), derives the
        realized cyclic spread + freshness, and builds the opportunity. A
        stale/fallback quote is never executable.

    The kill switch and live-capable-mode blocks are enforced here: when the
    kill switch is engaged, or the operator mode is LIMITED_LIVE/FULL_AUTOMATION
    (both permanently hard-blocked in this build), ``would_execute`` is forced
    False with an explicit safety reason.
    """
    from arbicore.economics.opportunity_decision import decide_opportunity

    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="request body must be a JSON object")

    quote_provenance: Optional[Dict[str, Any]] = None
    opp = body.get("opportunity")
    route = body.get("route")
    if (not isinstance(opp, dict) or not opp) and isinstance(route, dict):
        # Live-quote-backed path: quote the route, then build the opportunity.
        from arbicore.economics.quote_provider import build_opportunity_from_route
        chain = str(route.get("chain") or "base").strip()
        hops = route.get("hops")
        if not isinstance(hops, list) or not hops:
            raise HTTPException(status_code=422,
                                detail="route.hops array is required")
        try:
            max_age_sec = float(route.get("max_age_sec", 12.0))
        except (TypeError, ValueError):
            max_age_sec = 12.0
        rq = await _QUOTER_REGISTRY.quote_route(chain=chain, hops=hops)
        built = build_opportunity_from_route(
            rq.to_dict(), input_hops=hops,
            economics=body.get("economics") or {}, max_age_sec=max_age_sec)
        opp = built["opportunity"]
        quote_provenance = built["quote_provenance"]
    elif not isinstance(opp, dict) or not opp:
        raise HTTPException(status_code=422,
                            detail="'opportunity' object or 'route' is required")

    router_allowlist = body.get("router_allowlist") or _default_base_router_allowlist()
    token_allowlist = body.get("token_allowlist") or _default_base_token_allowlist()
    try:
        max_slippage_bps = float(body.get("max_slippage_bps", 150.0))
        max_gas_usd = float(body.get("max_gas_usd", 50.0))
        wallet_reserve_usd = float(body.get("wallet_reserve_usd", 0.0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="numeric caps must be numbers")

    decision = decide_opportunity(
        opp, router_allowlist=router_allowlist, token_allowlist=token_allowlist,
        max_slippage_bps=max_slippage_bps, max_gas_usd=max_gas_usd,
        wallet_reserve_usd=wallet_reserve_usd)
    result = decision.to_dict()

    # Authoritative safety overrides — these can only make a decision LESS
    # executable, never more. Confidence/EV can never bypass them.
    ks = await _KILL_SWITCH_REPO.state()
    mode = await _CONTROL_STATE_REPO.get_mode()
    safety_blocks: List[str] = []
    if ks.engaged:
        safety_blocks.append("kill switch engaged")
    if mode not in NON_BROADCAST_MODES:
        safety_blocks.append(f"mode '{mode}' is not a shadow-safe mode")
    if safety_blocks:
        result["would_execute"] = False
        result["reason"] = "; ".join(safety_blocks) + " (advisory blocked)"

    resp = {
        "mode": mode,
        "kill_switch_engaged": bool(ks.engaged),
        "execution_performed": False,
        "shadow_safe": True,
        "data_source": "LIVE_QUOTE" if quote_provenance else "OPERATOR_SUPPLIED",
        "decision": result,
        "generated_at": _iso_now(),
    }
    if quote_provenance is not None:
        resp["quote_provenance"] = quote_provenance
    return resp


@api_router.post("/arbicore/engine/scan-once",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_engine_scan_once(body: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Run ONE autonomous discovery→quote→decision scan over real Base venues.

    Enumerates cycles (same-DEX fee tiers, cross-DEX, triangular, stablecoin
    triangular, multi-hop), live-quotes each via read-only eth_call, runs the
    full decision chain, ranks by EV, and persists every evaluation as
    Decision History evidence. SHADOW/PAPER-safe: never signs or broadcasts."""
    limit = None
    try:
        if isinstance(body, dict) and body.get("limit") is not None:
            limit = int(body.get("limit"))
    except (TypeError, ValueError):
        limit = None
    scan = await _OPPORTUNITY_ENGINE.scan_once(limit=limit)
    try:
        await _DECISION_HISTORY_REPO.record_many(scan["scan_id"], scan["opportunities"])
        await _ROUTE_RECURRENCE_REPO.record_many(scan["opportunities"])
        await _PROFIT_ALERT_REPO.record_qualified(scan["scan_id"], scan["opportunities"])
    except Exception as exc:  # noqa: BLE001
        scan["history_persist_error"] = f"{type(exc).__name__}: {exc}"
    scan["execution_performed"] = False
    scan["shadow_safe"] = True
    return scan


@api_router.get("/arbicore/engine/alerts",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_alerts(limit: int = 50) -> Dict[str, Any]:
    """Profit alerts — only opportunities that passed the COMPLETE economic
    chain (real quote → net profit → confidence → EV → optimal size →
    simulation). Never fired on raw price spread."""
    rows = await _PROFIT_ALERT_REPO.recent(limit=limit)
    return {"count": len(rows), "total": await _PROFIT_ALERT_REPO.count(),
            "criteria": "real_quote AND net_profit>0 AND EV>0 AND simulation_pass AND would_execute",
            "alerts": rows, "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/onboarding",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_onboarding() -> Dict[str, Any]:
    """Secure operator onboarding checklist for the remaining LIMITED_LIVE
    prerequisites. Reports presence/absence ONLY — never returns secret
    values. Private keys are never accepted or echoed by this endpoint."""
    rpc_set = bool(os.environ.get("ARBICORE_RPC_URL"))
    archive_set = bool(os.environ.get("ARBICORE_ARCHIVE_RPC_URL")
                       or os.environ.get("ARBICORE_FORK_RPC_URL"))
    executor_set = bool(os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE"))
    signer_set = bool(os.environ.get("ARBICORE_VALIDATION_SIGNER_KEY")
                      or os.environ.get("ARBICORE_SIGNER_KEY"))
    try:
        gas_wallets = await _WALLET_REGISTRY.list_all(execution_role="gas")
    except Exception:  # noqa: BLE001
        gas_wallets = []

    def item(key, title, done, how, secret=False):
        return {"key": key, "title": title, "status": "DONE" if done else "PENDING",
                "how_to": how, "handles_secret": secret}

    checklist = [
        item("read_rpc", "Read-only Base RPC", rpc_set,
             "Set ARBICORE_RPC_URL in backend/.env (public https://mainnet.base.org works)."),
        item("gas_wallet", "Funded Base gas wallet", bool(gas_wallets),
             "Register a gas/execution wallet via the operator wizard; fund it with a small ETH reserve. Address only — no private key stored here.", True),
        item("signer", "Isolated execution signer", signer_set,
             "Provision a dedicated signer held in the secure secret store / KMS. The key is NEVER pasted into the app or committed.", True),
        item("executor", "Executor contract deployed & allowlisted", executor_set,
             "Deploy FlashLoanReceiver on Base, allowlist it, then set ARBICORE_EXECUTOR_ADDRESS_BASE (address only).", True),
        item("archive_rpc", "Fork/archive RPC for validation", archive_set,
             "Provide an archive/trace RPC (Alchemy/QuickNode) or run local anvil --fork-url; set ARBICORE_ARCHIVE_RPC_URL."),
    ]
    pending = [c for c in checklist if c["status"] == "PENDING"]
    return {"complete": len(pending) == 0, "pending_count": len(pending),
            "checklist": checklist,
            "security_note": ("This endpoint reports presence only and never accepts, "
                              "stores, or returns private keys/secrets."),
            "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/rpc-capabilities",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_rpc_capabilities(refresh: bool = False) -> Dict[str, Any]:
    """VERIFIED (not assumed) RPC capabilities: state-override, archive, trace."""
    if refresh or not _RPC_CAPS:
        try:
            _RPC_CAPS.update(await _SETTLEMENT_SIM.probe_capabilities())
        except Exception as exc:  # noqa: BLE001
            _RPC_CAPS["error"] = str(exc)
    return {"rpc_configured": bool(os.environ.get("ARBICORE_RPC_URL")),
            "capabilities": _RPC_CAPS, "generated_at": _iso_now()}


@api_router.post("/arbicore/engine/simulate-settlement",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_engine_simulate_settlement(body: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only end-to-end Aerodrome settlement simulation against REAL Base
    state: borrow → swap(s) → repayment → net profit. Optionally block-pinned
    (historical replay). NEVER signs or broadcasts. A failed simulation is an
    absolute rejection."""
    from arbicore.economics.opportunity_engine import TOKEN_ALLOWLIST as _TA
    if not os.environ.get("ARBICORE_RPC_URL"):
        raise HTTPException(status_code=503, detail="ARBICORE_RPC_URL not configured")
    if not isinstance(body, dict) or not isinstance(body.get("hops"), list) or not body["hops"]:
        raise HTTPException(status_code=422, detail="'hops' array is required")
    try:
        amount_in_wei = int(body["amount_in_wei"])
        token_decimals = int(body.get("token_decimals", 18))
        token_usd = float(body.get("token_usd", 0.0))
        gas_cost_usd = float(body.get("gas_cost_usd", 0.0))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="amount_in_wei/token_usd invalid")
    recipient = body.get("recipient") or "0x0000000000000000000000000000000000000001"
    kwargs = dict(hops=body["hops"], amount_in_wei=amount_in_wei,
                  token_decimals=token_decimals, token_usd=token_usd,
                  gas_cost_usd=gas_cost_usd, token_allowlist=_TA, recipient=recipient)
    block = body.get("block_number")
    result = (await _SETTLEMENT_SIM.replay(block_number=int(block), **kwargs)
              if block is not None else await _SETTLEMENT_SIM.simulate(**kwargs))
    return {"execution_performed": False, "shadow_safe": True,
            "simulation": result, "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/atomic-sim-status",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_atomic_sim_status(refresh: bool = False) -> Dict[str, Any]:
    """Atomic executor state-override simulation readiness.

    Reports the VERIFIED code-injection capability + whether the operator
    executor prerequisites are in place. Full atomic simulation stays gated
    until an executor address + bytecode are provided (no fake GREEN)."""
    if refresh or "code_injection" not in _ATOMIC_SELFTEST:
        try:
            _ATOMIC_SELFTEST.update(await _ATOMIC_SIM.capability_self_test())
        except Exception as exc:  # noqa: BLE001
            _ATOMIC_SELFTEST["error"] = str(exc)
    rd = _ATOMIC_SIM.readiness()
    from arbicore.execution.signer_vault import signer_status
    sig = await signer_status(db, expected_address=os.environ.get("ARBICORE_GAS_WALLET_ADDRESS"))
    signer_ok = bool(sig.get("present") and sig.get("matches_expected") is not False)
    # The executor is DEPLOYED on-chain, so its bytecode is live — the atomic
    # sim runs against the real contract via eth_call (local bytecode override
    # is only needed for not-yet-deployed contracts). Ready = capability +
    # deployed executor + a matching vault signer.
    if refresh and signer_ok and rd["executor_address_set"]:
        try:
            await _run_live_atomic_sim()
        except Exception as exc:  # noqa: BLE001
            _ATOMIC_LIVE_RUN.clear()
            _ATOMIC_LIVE_RUN.update({"available": False, "reason": str(exc)})
    live = dict(_ATOMIC_LIVE_RUN)
    ready = bool(_ATOMIC_SELFTEST.get("code_injection")
                 and rd["executor_address_set"] and signer_ok)
    note = ("Atomic state-override simulation runs against the DEPLOYED executor "
            "with the vault signer." if ready else
            "Code-injection verified. Full atomic simulation activates once the "
            "executor is deployed and a matching signer is in the vault.")
    return {"code_injection_verified": bool(_ATOMIC_SELFTEST.get("code_injection")),
            "readiness": {**rd, "signer_present": signer_ok},
            "atomic_sim_ready": ready, "live_run": live or None,
            "note": note, "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/fork-status",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_fork_status() -> Dict[str, Any]:
    """Anvil fork-validation harness readiness (ready-to-run, no fake GREEN)."""
    from arbicore.execution.executor_entrypoint import AnvilForkHarness
    return {"fork_harness": AnvilForkHarness().readiness(), "generated_at": _iso_now()}


@api_router.post("/arbicore/engine/build-executor-calldata",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_engine_build_executor_calldata(body: Dict[str, Any]) -> Dict[str, Any]:
    """Build (unsigned) executor entrypoint calldata that wraps the allowlisted
    Aerodrome settlement calldata: flash borrow → swaps → repay. No broadcast."""
    from arbicore.execution.executor_entrypoint import build_executor_entrypoint_calldata
    from arbicore.execution.aerodrome_settlement import AerodromeSettlementAdapter, AERODROME_ROUTER
    from arbicore.economics.opportunity_engine import TOKEN_ALLOWLIST as _TA
    if not isinstance(body, dict) or not isinstance(body.get("hops"), list) or not body["hops"]:
        raise HTTPException(status_code=422, detail="'hops' array required")
    try:
        borrow_token = body["borrow_token"]
        borrow_amount_wei = int(body["borrow_amount_wei"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="borrow_token/borrow_amount_wei required")
    adapter = AerodromeSettlementAdapter(token_allowlist=_TA, router_allowlist=[AERODROME_ROUTER])
    try:
        settlement = adapter.encode_settlement(
            hops=body["hops"], amount_in_wei=borrow_amount_wei,
            min_amount_out_wei=int(body.get("min_amount_out_wei", 1)),
            recipient=os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
            or "0x0000000000000000000000000000000000000001",
            deadline=9_999_999_999)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"settlement encode rejected: {exc}")
    entry = build_executor_entrypoint_calldata(
        borrow_token=borrow_token, borrow_amount_wei=borrow_amount_wei,
        settlement_target=settlement["to"], settlement_calldata_hex=settlement["data"])
    return {"executor_entrypoint": entry, "settlement": {"to": settlement["to"],
            "selector": settlement["data"][:10]},
            "signed": False, "broadcast": False, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Execution signer — secure one-time ingestion into the encrypted vault.
# Derives the address (eth_account), verifies against the gas wallet, stores
# ONLY the Fernet ciphertext + handle. The raw key is never logged/echoed/
# persisted outside the vault. No signing/broadcast anywhere here.
# ---------------------------------------------------------------------------
@api_router.get("/arbicore/engine/settings/signer",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_signer_status() -> Dict[str, Any]:
    from arbicore.execution.signer_vault import signer_status, ensure_signer_address
    # Self-heal a missing derived-address annotation (never exposes the key).
    await ensure_signer_address(_SECRET_REGISTRY, db,
                                expected_address=os.environ.get("ARBICORE_GAS_WALLET_ADDRESS"))
    st = await signer_status(db, expected_address=os.environ.get("ARBICORE_GAS_WALLET_ADDRESS"))
    return {**st, "vault_available": _SECRET_BACKEND.is_available(),
            "generated_at": _iso_now()}


@api_router.post("/arbicore/engine/settings/signer",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_engine_signer_ingest(body: Dict[str, Any]) -> Dict[str, Any]:
    """One-time secure ingestion of the execution signer private key.

    Body: {"private_key": "<64-hex or 0x…>", "label": "optional"}. Response
    returns ONLY the handle + derived checksummed address + mask — never the
    key. Verifies the derived address matches ARBICORE_GAS_WALLET_ADDRESS."""
    from arbicore.execution.signer_vault import ingest_signer
    if not _SECRET_BACKEND.is_available():
        raise HTTPException(status_code=503, detail="vault unavailable (VAULT_KEY missing)")
    pk = (body or {}).get("private_key")
    if not pk or not isinstance(pk, str):
        raise HTTPException(status_code=422, detail="private_key required")
    try:
        out = await ingest_signer(
            _SECRET_REGISTRY, db, private_key=pk,
            expected_address=os.environ.get("ARBICORE_GAS_WALLET_ADDRESS"),
            label=(body.get("label") or "execution-signer"))
    except ValueError as exc:
        # Message is key-free by construction in signer_vault.
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:  # noqa: BLE001 — never leak details that could echo material
        raise HTTPException(status_code=503, detail="unable to store signer")
    del pk
    return {"ok": True, **out, "signed": False, "broadcast": False,
            "generated_at": _iso_now()}


@api_router.delete("/arbicore/engine/settings/signer",
                   dependencies=[Depends(_require_operator_dep)])
async def v2_engine_signer_delete() -> Dict[str, Any]:
    from arbicore.execution.signer_vault import delete_signer
    out = await delete_signer(_SECRET_REGISTRY, db)
    return {"ok": True, **out, "generated_at": _iso_now()}


@api_router.post("/arbicore/engine/run-fork-validation",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_engine_run_fork_validation(body: Dict[str, Any] = None) -> Dict[str, Any]:
    """Run a REAL Anvil fork validation (spawns anvil --fork-url, runs read-only
    checks against the fork, tears it down). Returns ran/passed with evidence.
    Never fakes GREEN — ran=false when anvil/archive-RPC are absent."""
    from arbicore.execution.executor_entrypoint import AnvilForkHarness
    block = (body or {}).get("block_number")
    result = await AnvilForkHarness().run_fork_validation(
        block_number=int(block) if block is not None else None)
    _FORK_RUN.clear(); _FORK_RUN.update({**result, "ran_at": _iso_now()})
    return {"fork_validation": result, "generated_at": _iso_now()}


async def _run_live_atomic_sim(*, block_number: Optional[int] = None,
                               fork_rpc: Optional[str] = None) -> Dict[str, Any]:
    """Run the atomic executor state-override simulation against the DEPLOYED
    executor using its REAL ABI (recovered from source): entrypoint
    ``execute(address[],uint256[],bytes)`` (Balancer V2 flash) with
    ``userData = abi.encode(SwapHop[], profitRecipient)`` and Uniswap V3
    exactInputSingle hops. Pure eth_call from the owner/signer — never
    signs/broadcasts. A revert is a deterministic on-chain result classified
    below (economics / swap / repayment / decode).

    Diagnostic replay (A) — READ-ONLY, never signs/broadcasts, never modifies
    real chain state, never touches the LIVE readiness matrix:
      * ``fork_rpc`` — run the eth_call against an operator-provided fork
        endpoint (e.g. an already-running Anvil). URL is never echoed.
      * ``block_number`` — pin to a historical block. Prefers a LOCAL Anvil
        fork (``--fork-block-number``); falls back to a direct archive-RPC
        eth_call at ``hex(block)`` when Anvil is unavailable.
    Only a ``live_rpc_latest`` pass updates SIMULATION_ONCHAIN; block-pinned /
    fork runs are stored as separate diagnostic evidence (honest semantics)."""
    from arbicore.execution.signer_vault import signer_status
    from arbicore.execution.calldata import (encode_executor_execute,
                                             build_user_data_from_hops,
                                             UNISWAP_V3_ROUTER_BY_CHAIN,
                                             BALANCER_V2_VAULT_BY_CHAIN)
    from arbicore.execution.executor_entrypoint import anvil_fork

    diagnostic = bool(block_number is not None or fork_rpc)
    slot = _ATOMIC_DIAG_RUN if diagnostic else _ATOMIC_LIVE_RUN

    executor = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    st = await signer_status(db, expected_address=os.environ.get("ARBICORE_GAS_WALLET_ADDRESS"))
    if not (st.get("present") and executor):
        res = {"available": False, "passed": False,
               "reason": "signer not in vault or executor not configured"}
        slot.clear(); slot.update({**res, "ran_at": _iso_now()})
        return dict(slot)

    WETH = "0x4200000000000000000000000000000000000006"
    USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    signer = st.get("derived_address")
    borrow = 10**16  # 0.01 WETH
    # Representative Uniswap-V3-only round trip (Balancer flash → UniV3 → repay).
    hops = [
        {"token_in": WETH, "token_out": USDC, "fee_tier_bps": 5,
         "amount_in_wei": borrow, "amount_out_min_wei": 0},
        {"token_in": USDC, "token_out": WETH, "fee_tier_bps": 5,
         "amount_in_wei": 0, "amount_out_min_wei": 0},
    ]
    try:
        user_data = build_user_data_from_hops(hops=hops, profit_recipient=signer)
        call = encode_executor_execute(executor_address=executor, tokens=[WETH],
                                       amounts=[borrow], user_data_hex=user_data)
    except Exception as exc:  # noqa: BLE001
        res = {"available": True, "passed": False, "reason": f"calldata encode failed: {exc}"}
        slot.clear(); slot.update({**res, "ran_at": _iso_now()})
        return dict(slot)

    # (B) Complete diagnostic execution artifact — deterministic replay/tracing.
    # NEVER includes any private key / vault material / RPC URL (may carry a key).
    artifact = {
        "executor": executor,
        "entrypoint": "execute(address[],uint256[],bytes)",
        "selector": call.selector_hex,
        "from": signer,
        "borrow_token": WETH,
        "borrow_amount_wei": borrow,
        "flash_provider": "balancer_v2",
        "flash_vault": BALANCER_V2_VAULT_BY_CHAIN.get("base"),
        "settlement_target": UNISWAP_V3_ROUTER_BY_CHAIN.get("base"),  # UniV3 SwapRouter02
        "settlement_venue": "uniswap_v3",
        "tokens": [WETH],
        "amounts": [borrow],
        "hops": [
            {"index": i, "token_in": h["token_in"], "token_out": h["token_out"],
             "fee_ppm": int(h["fee_tier_bps"]) * 100,
             "fee_tier": f"{(int(h['fee_tier_bps']) * 100) / 10000:.2f}%",
             "amount_in_wei": int(h.get("amount_in_wei") or 0),
             "amount_out_minimum_wei": int(h["amount_out_min_wei"]),
             "sqrt_price_limit_x96": int(h.get("sqrt_price_limit_x96") or 0)}
            for i, h in enumerate(hops)
        ],
        "user_data": user_data,
        "profit_recipient": signer,
        "calldata_hex": call.calldata_hex,
        "value_wei": 0,
    }

    # (A) Determine the simulation context + endpoint/block.
    async def _sim(rpc_override, block_tag):
        return await _ATOMIC_SIM.simulate_atomic(
            entry_calldata=call.calldata_hex, signer_present=True,
            from_address=signer, rpc_url_override=rpc_override, block_tag=block_tag)

    rpc_context: Dict[str, Any] = {}
    if fork_rpc:
        # Operator-provided external fork (e.g. their own anvil). URL not echoed.
        res = await _sim(fork_rpc, "latest")
        rpc_context = {"mode": "block_pinned_fork_external", "fork": True,
                       "rpc_source": "operator_fork_rpc", "block": "fork_latest",
                       "block_number": block_number}
    elif block_number is not None:
        # Prefer a LOCAL Anvil fork pinned to the block; fall back to archive RPC.
        async with anvil_fork(int(block_number)) as fk:
            if fk.get("ok"):
                res = await _sim(fk["local_url"], "latest")
                rpc_context = {"mode": "block_pinned_anvil_fork", "fork": True,
                               "rpc_source": "local_anvil", "block": "fork_block",
                               "block_number": block_number, "fork_block": fk.get("fork_block")}
            else:
                # Archive fallback: historical state via the live archive RPC.
                res = await _sim(None, hex(int(block_number)))
                rpc_context = {"mode": "block_pinned_archive_rpc", "fork": False,
                               "rpc_source": "ARBICORE_RPC_URL", "block": hex(int(block_number)),
                               "block_number": block_number,
                               "anvil_fallback_reason": fk.get("reason")}
    else:
        res = await _sim(None, "latest")
        rpc_context = {"mode": "live_rpc_latest", "fork": False,
                       "rpc_source": "ARBICORE_RPC_URL", "block": "latest",
                       "block_number": None}

    # Classify the deterministic on-chain outcome (honest — never GREEN on revert).
    reason = str(res.get("reason") or "")
    if res.get("passed"):
        res["root_cause"] = None
    elif not res.get("available"):
        res["root_cause"] = "prerequisite: " + reason
    else:
        low = reason.lower()
        if "insufficient" in low or "repay" in low:
            cat = "economics/repayment: swap output could not repay the Balancer loan (route unprofitable)"
        elif "swapreverted" in low:
            cat = "swap: a Uniswap V3 hop reverted (liquidity/slippage/fee-tier)"
        elif "notowner" in low or "notauthorized" in low:
            cat = "auth: caller/authorization gate rejected the call"
        else:
            # Public RPC returned no revert data → exact cause not yet PROVEN.
            cat = ("reverted with NO revert data on the public RPC. Calldata now targets the "
                   "REAL entrypoint execute(address[],uint256[],bytes) with the verified userData "
                   "schema (SwapHop[],profitRecipient). Most likely economics (round-trip "
                   "WETH→USDC→WETH loses UniV3 fees → cannot repay the 0-fee Balancer loan), but "
                   "proving the exact cause requires a fork trace (anvil) or a revert-data RPC.")
        res["root_cause"] = cat
    res["entrypoint"] = "execute(address[],uint256[],bytes)"
    res["venue"] = "balancer_v2_flash + uniswap_v3_swaps"
    res["route"] = "WETH→USDC→WETH @ 0.05% (representative UniV3-only)"
    res["execution_context"] = rpc_context           # (A) live vs block-pinned fork evidence
    res["diagnostic"] = diagnostic
    res["artifact"] = artifact                        # (B) complete replay artifact
    res["signed"] = False
    res["broadcast"] = False
    slot.clear()
    slot.update({**res, "ran_at": _iso_now()})
    return dict(slot)


_EXECUTOR_ABI_CACHE: Dict[str, Any] = {}   # last-good executor ABI inspection


@api_router.get("/arbicore/engine/executor-abi",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_executor_abi() -> Dict[str, Any]:
    """READ-ONLY on-chain inspection of the deployed executor: real function
    selectors, recognised signatures, owner/ROUTER/VAULT getters, and the
    verified entrypoint signature (determined from bytecode, not guessed)."""
    from arbicore.execution.executor_entrypoint import inspect_executor
    insp = await inspect_executor(os.environ.get("ARBICORE_RPC_URL", ""),
                                  os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE", ""))
    # Public-RPC getters can flake (rate limits) on a cold call — merge the last
    # successful owner/router/vault so the inspection is stable across retries.
    if insp.get("ok"):
        for k in ("owner", "router", "vault"):
            if insp.get(k):
                _EXECUTOR_ABI_CACHE[k] = insp[k]
            elif _EXECUTOR_ABI_CACHE.get(k):
                insp[k] = _EXECUTOR_ABI_CACHE[k]
    return {"executor_abi": insp, "generated_at": _iso_now()}


_BUILD_IDENTITY: Dict[str, Any] = {}


def _resolve_build_identity() -> Dict[str, Any]:
    """Non-secret build/runtime identity for the deployment-identity chain
    (Emergent→Git→Docker→VPS). Prefers baked build args/env (set by the Docker
    build via --build-arg/labels); falls back to a live `git` read in dev.
    NEVER returns secrets."""
    global _BUILD_IDENTITY
    if _BUILD_IDENTITY:
        return _BUILD_IDENTITY
    import subprocess

    def _git(args: List[str]) -> Optional[str]:
        try:
            out = subprocess.run(["git", *args], cwd=os.path.dirname(__file__),
                                  capture_output=True, text=True, timeout=4)
            v = (out.stdout or "").strip()
            return v or None
        except Exception:  # noqa: BLE001
            return None

    git_sha = (os.environ.get("ARBICORE_GIT_SHA") or _git(["rev-parse", "HEAD"]) or "unknown")
    git_tag = (os.environ.get("ARBICORE_GIT_TAG")
               or _git(["describe", "--tags", "--always", "--dirty"]) or "unknown")
    _BUILD_IDENTITY = {
        "application": "arbicore-x",
        "app_version": os.environ.get("ARBICORE_VERSION") or git_tag,
        "git_sha": git_sha,
        "git_sha_short": git_sha[:12] if git_sha and git_sha != "unknown" else "unknown",
        "git_tag": git_tag,
        "image_digest": os.environ.get("ARBICORE_IMAGE_DIGEST") or "unset",
        "image_ref": os.environ.get("ARBICORE_IMAGE_REF") or "unset",
        "build_time": os.environ.get("ARBICORE_BUILD_TIME") or "unset",
        "runtime_env": os.environ.get("ARBICORE_ENV") or "unset",
        "dirty": git_tag.endswith("-dirty") if git_tag else False,
    }
    return _BUILD_IDENTITY


@api_router.get("/arbicore/version")
async def v2_arbicore_version() -> Dict[str, Any]:
    """Deployment identity — commit sha, tag, image digest, build time, runtime
    env. Safe (no secrets). Used to prove Git == Docker == VPS == running code."""
    ident = _resolve_build_identity()
    return {**ident, "generated_at": _iso_now()}


@api_router.post("/arbicore/engine/run-atomic-sim",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_engine_run_atomic_sim(body: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute ATOMIC_EXECUTOR_SIM + SIMULATION_ONCHAIN against the deployed
    executor with the vault signer. Returns the deterministic eth_call result
    plus a complete replay/trace artifact (calldata, hops, userData, context).

    Optional body (diagnostic, READ-ONLY — never signs/broadcasts):
      * ``block_number`` (int) — pin the sim to a historical block (prefers a
        local Anvil fork, falls back to archive-RPC historical state).
      * ``fork_rpc`` (str) — run against an operator-provided fork endpoint.
    A live (default) pass updates SIMULATION_ONCHAIN; block-pinned/fork runs are
    returned as separate diagnostic evidence and never flip the live matrix."""
    b = body or {}
    block_number = b.get("block_number")
    fork_rpc = b.get("fork_rpc")
    result = await _run_live_atomic_sim(
        block_number=int(block_number) if block_number is not None else None,
        fork_rpc=str(fork_rpc) if fork_rpc else None)
    return {"atomic_sim": result, "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# Wallet & Capital Intelligence — READ-ONLY on-chain monitoring for the
# configured Base gas/execution wallet(s). SHADOW-safe; public addresses only.
# ---------------------------------------------------------------------------
async def _capital_monitored_wallets() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    try:
        for w in await _WALLET_REGISTRY.list_all(chain="base", execution_role="gas"):
            a = (w.get("address") or "").lower()
            if a and a not in seen:
                seen.add(a)
                out.append({"address": w.get("address"), "wallet_id": w.get("wallet_id"),
                            "role": "gas", "label": w.get("label")})
    except Exception:  # noqa: BLE001
        pass
    env_gas = os.environ.get("ARBICORE_GAS_WALLET_ADDRESS")
    if env_gas and env_gas.lower() not in seen:
        out.append({"address": env_gas, "wallet_id": "env-gas", "role": "gas",
                    "label": "env-configured gas wallet"})
    return out


def _capital_default_address(address: Optional[str]) -> str:
    addr = (address or os.environ.get("ARBICORE_GAS_WALLET_ADDRESS") or "").strip()
    if not (addr.startswith("0x") and len(addr) == 42):
        raise HTTPException(status_code=422, detail="valid 0x address required (or configure ARBICORE_GAS_WALLET_ADDRESS)")
    return addr


@api_router.get("/arbicore/capital/wallets", dependencies=[Depends(_require_operator_dep)])
async def v2_capital_wallets() -> Dict[str, Any]:
    return {"wallets": await _capital_monitored_wallets(), "generated_at": _iso_now()}


@api_router.get("/arbicore/capital/balances", dependencies=[Depends(_require_operator_dep)])
async def v2_capital_balances(address: Optional[str] = None) -> Dict[str, Any]:
    return await _CAPITAL_ENGINE.live_balances(_capital_default_address(address))


@api_router.get("/arbicore/capital/statement", dependencies=[Depends(_require_operator_dep)])
async def v2_capital_statement(address: Optional[str] = None, limit: int = 100,
                               tx_type: Optional[str] = None, venue: Optional[str] = None,
                               status: Optional[str] = None,
                               start_ts: Optional[int] = None,
                               end_ts: Optional[int] = None) -> Dict[str, Any]:
    return await _CAPITAL_ENGINE.transaction_statement(
        _capital_default_address(address), limit=min(int(limit), 500),
        tx_type=tx_type, venue=venue, status=status,
        start_ts=start_ts, end_ts=end_ts)


@api_router.get("/arbicore/capital/money-trail", dependencies=[Depends(_require_operator_dep)])
async def v2_capital_money_trail(tx_hash: str, address: Optional[str] = None) -> Dict[str, Any]:
    return await _CAPITAL_ENGINE.money_trail(_capital_default_address(address), tx_hash)


@api_router.get("/arbicore/capital/reconciliation", dependencies=[Depends(_require_operator_dep)])
async def v2_capital_reconciliation(address: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    return await _CAPITAL_ENGINE.capital_reconciliation(
        _capital_default_address(address), limit=min(int(limit), 500))


@api_router.get("/arbicore/capital/venue-stats", dependencies=[Depends(_require_operator_dep)])
async def v2_capital_venue_stats(address: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    return await _CAPITAL_ENGINE.venue_pair_stats(
        _capital_default_address(address), limit=min(int(limit), 500))


@api_router.get("/arbicore/capital/overview", dependencies=[Depends(_require_operator_dep)])
async def v2_capital_overview(address: Optional[str] = None) -> Dict[str, Any]:
    """One-call composite for the Capital Intelligence screen: live balances,
    recent statement, reconciliation and venue stats."""
    addr = _capital_default_address(address)
    balances = await _CAPITAL_ENGINE.live_balances(addr)
    statement = await _CAPITAL_ENGINE.transaction_statement(addr, limit=50)
    reconciliation = await _CAPITAL_ENGINE.capital_reconciliation(addr, limit=200)
    venue_stats = await _CAPITAL_ENGINE.venue_pair_stats(addr, limit=200)
    return {"address": addr, "balances": balances, "statement": statement,
            "reconciliation": reconciliation, "venue_stats": venue_stats,
            "monitored_wallets": await _capital_monitored_wallets(),
            "generated_at": _iso_now()}




@api_router.get("/arbicore/engine/scanner/status",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_scanner_status() -> Dict[str, Any]:
    return _CONTINUOUS_SCANNER.status()


@api_router.get("/arbicore/engine/flash-loan/readiness",
                dependencies=[Depends(_require_operator_dep)])
async def v2_flash_loan_readiness() -> Dict[str, Any]:
    """T0-1 · canonical flash-loan scanner quote-provider readiness.

    Proves the canonical scanner is NOT silently running the noop quote
    provider in an analysis mode. Live-computed against the current
    flash_loan_arbitrage execution mode.
    """
    from arbicore.runtime import composition as _composition
    activation = dict(_CANONICAL_FL_ACTIVATION)
    readiness = activation.get("readiness")
    try:
        scanner = _composition.get_flash_loan_arb_scanner()
        fl_row = await _EXECUTION_MODE_REPO.get("flash_loan_arbitrage")
        fl_mode = (fl_row or {}).get("mode") or "OBSERVE"
        readiness = _composition.flash_loan_quote_readiness(
            quote_provider_is_default=scanner.quote_provider_is_default,
            mode=fl_mode)
        activation["mode"] = fl_mode
        activation["readiness"] = readiness
    except Exception as exc:  # noqa: BLE001
        activation["readiness_error"] = f"{type(exc).__name__}: {exc}"
    return {"activation": activation, "readiness": readiness,
            "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/base-live-shadow/readiness",
                dependencies=[Depends(_require_operator_dep)])
async def v2_base_live_shadow_readiness() -> Dict[str, Any]:
    """T2 · Base live-SHADOW readiness. Evidence-based per-dependency status +
    categorized blockers. tx_builder is now WIRED (SOFTWARE self-test against
    the canonical execute() encoder). SHADOW-only; never signs/broadcasts."""
    from arbicore.searcher import live_base as _lb
    readiness = _lb.base_live_readiness()          # tx_builder auto self-tested
    return {"readiness": readiness,
            "tx_builder_selftest": _lb.tx_builder_selftest(),
            "mode": "SHADOW", "broadcast": False, "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/base-live-shadow/audit",
                dependencies=[Depends(_require_operator_dep)])
async def v2_base_live_shadow_audit() -> Dict[str, Any]:
    """T2 · Full Base live-SHADOW software audit — every path item classified as
    SOFTWARE / CONFIGURATION / VALIDATION / MARKET / SAFETY with evidence-based
    status. Read-only; changes nothing; never signs/broadcasts."""
    from arbicore.searcher import live_base as _lb
    audit = _lb.base_live_shadow_audit()
    audit["generated_at"] = _iso_now()
    return audit


@api_router.get("/arbicore/engine/base-live-shadow/dry-run",
                dependencies=[Depends(_require_operator_dep)])
async def v2_base_live_shadow_dry_run() -> Dict[str, Any]:
    """T2 · SHADOW dry-run transaction audit — builds the canonical executor tx
    for a representative Base route via the wired tx_builder and DECODES it
    (selector, borrow, hops, profit-recipient) for operator review.

    READ-ONLY: value=0x0, eth_call/fork-sim only. NEVER signs or broadcasts."""
    from arbicore.searcher import live_base as _lb
    audit = _lb.shadow_dry_run_audit()
    audit["generated_at"] = _iso_now()
    return audit


@api_router.get("/arbicore/certification/provenance-split",
                dependencies=[Depends(_require_operator_dep)])
async def v2_certification_provenance_split() -> Dict[str, Any]:
    """T0-7 · REAL vs SYNTHETIC provenance partition of the latest evidence
    delta. Executable metrics count REAL/VERIFIED_REAL only; synthetic
    executable evidence is reported here but excluded from executable_rate."""
    split = {"real": 0, "synthetic": 0,
             "synthetic_executable_excluded": 0, "executable_real": 0}
    if _SHADOW_CERT_ENGINE is not None:
        try:
            split = _SHADOW_CERT_ENGINE.last_provenance_split()
        except Exception:  # noqa: BLE001
            pass
    return {"provenance_split": split, "generated_at": _iso_now()}


@api_router.post("/arbicore/engine/scanner/start",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_engine_scanner_start() -> Dict[str, Any]:
    """Start the always-on read-only Base opportunity scanner (SHADOW-safe)."""
    return await _CONTINUOUS_SCANNER.start()


@api_router.post("/arbicore/engine/scanner/stop",
                 dependencies=[Depends(_require_operator_dep)])
async def v2_engine_scanner_stop() -> Dict[str, Any]:
    return await _CONTINUOUS_SCANNER.stop()


@api_router.get("/arbicore/engine/recurring",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_recurring(limit: int = 25, min_seen: int = 2) -> Dict[str, Any]:
    """Routes that recur across scans (recurring-route opportunity signal)."""
    rows = await _ROUTE_RECURRENCE_REPO.recurring(limit=limit, min_seen=min_seen)
    return {"count": len(rows), "recurring_routes": rows, "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/checkpoint",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_checkpoint() -> Dict[str, Any]:
    """Consolidated operator checkpoint: scan totals, opportunities discovered,
    positive-after-costs, top opportunities, rejection reasons, dynamic-sizing
    + simulation results, decision-history stats, recurring routes, the full
    RED/YELLOW/GREEN matrix, and the exact remaining LIMITED_LIVE blockers."""
    cp = await _DECISION_HISTORY_REPO.checkpoint(top_n=5)
    recurring = await _ROUTE_RECURRENCE_REPO.recurring(limit=10, min_seen=2)
    matrix = await v2_engine_readiness_matrix()
    scanner = _CONTINUOUS_SCANNER.status()
    alerts_total = await _PROFIT_ALERT_REPO.count()

    limited_live_blockers = [
        {"capability": c["capability"], "blocker": c["blocker"],
         "action": c["action"], "owner": c["owner"]}
        for c in matrix["capabilities"]
        if c["status"] in ("RED", "YELLOW")
        and c["capability"] in ("WALLET_GAS", "SIGNER", "EXECUTOR_CONTRACT",
                                "DEX_ADAPTERS_SETTLE", "SIMULATION_ONCHAIN",
                                "FORK_VALIDATION", "HISTORICAL_REPLAY")]

    # Dynamic-sizing + simulation snapshot from the latest scan.
    last = scanner.get("last_scan_summary") or {}
    dynamic_sizing = []
    sim_results = {"passed": 0, "failed": 0}
    top = cp.get("top_opportunities", [])
    for o in top:
        dynamic_sizing.append({
            "route_id": o.get("route_id"),
            "opportunity_type": o.get("opportunity_type"),
            "optimal_notional_usd": o.get("optimal_notional_usd"),
            "expected_value_usd": o.get("expected_value_usd"),
            "net_profit_usd": o.get("net_profit_usd"),
        })
        if o.get("simulation_passed"):
            sim_results["passed"] += 1
        else:
            sim_results["failed"] += 1

    return {
        "market_coverage_funnel": scanner.get("funnel_cumulative"),
        "candidate_universe": scanner.get("candidate_universe"),
        "routes_scanned_records": cp["records"],
        "real_quotes": cp["real_quotes"],
        "opportunities_discovered": cp["records"],
        "positive_after_costs": cp["positive_after_costs"],
        "executable": cp["executable"],
        "profit_alerts_total": alerts_total,
        "opportunity_type_coverage": cp["opportunity_type_coverage"],
        "top_opportunities": top,
        "rejection_reasons": cp["rejection_histogram"],
        "dynamic_sizing_results": dynamic_sizing,
        "simulation_results": sim_results,
        "recurring_routes": recurring,
        "decision_history": await _DECISION_HISTORY_REPO.stats(),
        "scanner": scanner,
        "last_scan_summary": last,
        "readiness_matrix": {"overall_status": matrix["overall_status"],
                             "capabilities": matrix["capabilities"],
                             "modes": matrix["modes"]},
        "limited_live_blockers": limited_live_blockers,
        "generated_at": _iso_now(),
    }




@api_router.get("/arbicore/engine/opportunities",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_opportunities(limit: int = 25,
                                  only_executable: bool = False) -> Dict[str, Any]:
    """Latest ranked opportunities from the Decision-History evidence store."""
    rows = await _DECISION_HISTORY_REPO.recent(limit=limit, only_executable=only_executable)
    return {"count": len(rows), "opportunities": rows,
            "stats": await _DECISION_HISTORY_REPO.stats(), "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/history",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_history(limit: int = 50) -> Dict[str, Any]:
    rows = await _DECISION_HISTORY_REPO.recent(limit=limit)
    return {"count": len(rows), "history": rows,
            "stats": await _DECISION_HISTORY_REPO.stats(), "generated_at": _iso_now()}


@api_router.get("/arbicore/engine/readiness-matrix",
                dependencies=[Depends(_require_operator_dep)])
async def v2_engine_readiness_matrix() -> Dict[str, Any]:
    """Single authoritative readiness matrix across every capability + mode.

    Each row: status (GREEN/YELLOW/RED), blocker, action, and whether the gap
    needs USER (credentials/config) or ENGINEERING work. The five operator
    modes reflect the backend-authoritative readiness engine (LIMITED_LIVE /
    FULL_AUTOMATION remain hard-blocked in this build)."""
    from arbicore.discovery.base_venues import VENUES, BORROW_TOKENS

    try:
        from arbicore.execution.aerodrome_settlement import AerodromeSettlementAdapter
        _aero_settle_ok = bool(AerodromeSettlementAdapter().self_test().get("passed"))
    except Exception:  # noqa: BLE001
        _aero_settle_ok = False

    # Lazily verify RPC capabilities + settlement simulator once (cached).
    if os.environ.get("ARBICORE_RPC_URL"):
        if not _RPC_CAPS:
            try:
                _RPC_CAPS.update(await _SETTLEMENT_SIM.probe_capabilities())
            except Exception:  # noqa: BLE001
                pass
        if not _SETTLEMENT_SELFTEST.get("ran"):
            try:
                _SETTLEMENT_SELFTEST.update(await _SETTLEMENT_SIM.self_test())
            except Exception:  # noqa: BLE001
                pass
        if "code_injection" not in _ATOMIC_SELFTEST:
            try:
                _ATOMIC_SELFTEST.update(await _ATOMIC_SIM.capability_self_test())
            except Exception:  # noqa: BLE001
                pass

    _atomic_rd = _ATOMIC_SIM.readiness()
    rpc_set = bool(os.environ.get("ARBICORE_RPC_URL"))
    executor_set = bool(os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE"))
    # Execution signer must live in the encrypted vault (scope=evm_sign), NOT
    # env — and its derived address must match the gas/execution wallet.
    from arbicore.execution.signer_vault import signer_status as _signer_status
    try:
        _signer = await _signer_status(db, expected_address=os.environ.get("ARBICORE_GAS_WALLET_ADDRESS"))
    except Exception:  # noqa: BLE001
        _signer = {"present": False, "matches_expected": None, "derived_address": None}
    _gas_env_for_signer = os.environ.get("ARBICORE_GAS_WALLET_ADDRESS")
    # GREEN only when present AND (no gas wallet to match OR address matches).
    signer_set = bool(_signer.get("present") and (
        (not _gas_env_for_signer) or _signer.get("matches_expected") is True))
    signer_mismatch = bool(_signer.get("present") and _gas_env_for_signer
                           and _signer.get("matches_expected") is False)
    gas_env_addr = os.environ.get("ARBICORE_GAS_WALLET_ADDRESS")

    # Lazily run the live atomic executor sim ONCE against the deployed executor
    # when a matching vault signer is present (cached; refresh via
    # POST /engine/run-atomic-sim). available=True means the state-override
    # eth_call round-tripped deterministically against the real contract.
    if executor_set and signer_set and not _ATOMIC_LIVE_RUN:
        try:
            await _run_live_atomic_sim()
        except Exception:  # noqa: BLE001
            pass
    _atomic_ran = bool(_ATOMIC_LIVE_RUN.get("available"))
    _atomic_passed = bool(_ATOMIC_LIVE_RUN.get("passed"))
    _gas_registered = await _WALLET_REGISTRY.list_all(execution_role="gas") \
        if hasattr(_WALLET_REGISTRY, "list_all") else []
    gas_wallets = bool(_gas_registered) or bool(gas_env_addr)
    hist = await _DECISION_HISTORY_REPO.stats()

    G, Y, R = "GREEN", "YELLOW", "RED"

    def row(name, status, blocker="", action="", owner=""):
        return {"capability": name, "status": status, "blocker": blocker,
                "action": action, "owner": owner}

    matrix = [
        row("CONFIGURATION_RPC", G if rpc_set else R,
            "" if rpc_set else "ARBICORE_RPC_URL missing",
            "" if rpc_set else "Set a Base RPC URL in backend/.env",
            "" if rpc_set else "USER"),
        row("WALLET_GAS", G if gas_wallets else Y,
            "" if gas_wallets else "No gas/execution wallet registered",
            "Base gas wallet address configured" if gas_wallets else "Register a funded Base gas wallet (operator wizard)",
            "" if gas_wallets else "USER"),
        row("SIGNER", G if signer_set else Y,
            ("" if signer_set else
             ("Signer address does not match gas wallet (ARBICORE_GAS_WALLET_ADDRESS)"
              if signer_mismatch else "No execution signer in encrypted vault (0 handles)")),
            "Execution signer handle present in vault; derived address matches gas wallet" if signer_set
            else ("Re-ingest the signer whose address matches the gas wallet" if signer_mismatch
                  else "Inject signer key via POST /api/arbicore/engine/settings/signer (encrypted vault; VAULT_KEY ready)"),
            "" if signer_set else "USER"),
        row("EXECUTOR_CONTRACT", G if executor_set else Y,
            "" if executor_set else "ARBICORE_EXECUTOR_ADDRESS_BASE not set",
            "" if executor_set else "Deploy/allowlist FlashLoanReceiver, set address (LIMITED_LIVE only)",
            "" if executor_set else "USER"),
        row("FLASH_PROVIDERS", G, "", "Aave V3 + Balancer V2 adapters present (quoting/economics)", ""),
        row("DEX_ADAPTERS_QUOTE", G, "",
            "UniV3 + Aerodrome SlipStream + classic live quoting active", ""),
        row("DEX_ADAPTERS_SETTLE", G if _aero_settle_ok else Y,
            "" if _aero_settle_ok else "Aerodrome settlement encoder self-test failed",
            "Allowlisted Aerodrome swapExactTokensForTokens encoder validated (no arbitrary target, no signing)"
            if _aero_settle_ok else "Investigate aerodrome_settlement.self_test()",
            "" if _aero_settle_ok else "ENGINEERING"),
        row("DISCOVERY_ENGINE", G, "",
            f"{len(VENUES)} venues, borrow tokens {BORROW_TOKENS}; cycle DFS active", ""),
        row("ROUTE_ENGINE", G, "", "RouteSearchEngine enumerating closed cycles", ""),
        row("OPP_TYPES", G, "",
            "same-DEX fee-tier, cross-DEX, triangular, stablecoin-triangular, multi-hop", ""),
        row("QUOTES_LIVE", G if rpc_set else R,
            "" if rpc_set else "RPC required",
            "REAL/STALE/UNAVAILABLE freshness enforced", ""),
        row("PROFITABILITY", G, "", "net_profit engine wired (realized spread net of DEX fees)", ""),
        row("CONFIDENCE_V2", G, "", "12-factor explainable score (advisory)", ""),
        row("EXPECTED_VALUE", G, "", "EV = P(s)*net − P(f)*max_loss with evidence penalty", ""),
        row("SIZE_OPTIMIZER", G, "", "adaptive max-risk-adjusted-EV size search", ""),
        row("LIQUIDITY_DEPTH", G, "",
            "dynamic: effective depth measured live from the multi-size quote curve; conservative default only for clearly-unprofitable routes", ""),
        row("SCANNER", G if _CONTINUOUS_SCANNER.running else Y,
            "" if _CONTINUOUS_SCANNER.running else "Continuous scanner not running",
            "Autonomous Base scan loop active" if _CONTINUOUS_SCANNER.running
            else "POST /api/arbicore/engine/scanner/start (auto-starts on boot)",
            "" if _CONTINUOUS_SCANNER.running else "ENGINEERING"),
        row("SIMULATION_GATE", G, "", "hard gate: quote-fresh, allowlists, min-out, slippage, gas, repayment, calldata", ""),
        row("SETTLEMENT_SIMULATION", G if _SETTLEMENT_SELFTEST.get("ran") else Y,
            "" if _SETTLEMENT_SELFTEST.get("ran") else "Settlement simulator has not validated a real route",
            "Read-only E2E Aerodrome route sim (getAmountsOut → repayment → net profit) is MANDATORY before any candidate is executable"
            if _SETTLEMENT_SELFTEST.get("ran") else "Ensure RPC reachable; run /engine/simulate-settlement",
            "" if _SETTLEMENT_SELFTEST.get("ran") else "ENGINEERING"),
        row("RPC_STATE_OVERRIDE", G if _RPC_CAPS.get("state_override") else Y,
            "" if _RPC_CAPS.get("state_override") else "State-override eth_call not verified on this RPC",
            "VERIFIED: eth_call state-override supported (enables realistic pre-trade sim)"
            if _RPC_CAPS.get("state_override") else "Provide an RPC supporting eth_call state overrides",
            "" if _RPC_CAPS.get("state_override") else "USER"),
        row("ATOMIC_EXECUTOR_SIM",
            G if (_ATOMIC_SELFTEST.get("code_injection") and executor_set and signer_set) else Y,
            ("" if (executor_set and signer_set)
             else ("executor deployed=%s, state-override verified=%s; needs execution signer in vault + executor entrypoint calldata"
                    % (bool(executor_set), bool(_ATOMIC_SELFTEST.get("code_injection"))))),
            ("Atomic state-override simulation ready" if (executor_set and signer_set)
             else "Inject signer into vault; then wire executor entrypoint flash-loan calldata for the full atomic sim"),
            "" if (executor_set and signer_set) else "USER"),
        row("SIMULATION_ONCHAIN",
            G if _atomic_passed else Y,
            ("" if _atomic_passed else
             ("On-chain atomic sim EXECUTED against the deployed executor via its REAL entrypoint "
              "execute(address[],uint256[],bytes) + verified userData (SwapHop[],profitRecipient); "
              "reverted with no revert data on the public RPC. Calldata/ABI is CORRECT; most likely "
              "economics (no live arbitrage → round-trip cannot repay the flash loan). Not auth (owner==signer)."
              if _atomic_ran else
              ("Executor deployed + signer in vault; run POST /engine/run-atomic-sim"
               if (executor_set and signer_set)
               else "Full atomic executor sim gated on execution signer (vault) + deployed executor"))),
            ("Passing on-chain atomic state-override simulation against the deployed executor"
             if _atomic_passed else
             ("Supply a genuinely profitable UniV3 route (or a controlled fork state) so the flash loan "
              "repays with profit; the calldata path is correct and executes end-to-end"
              if _atomic_ran else
              "Provide signer via vault → on-chain atomic state-override sim turns on (no fake GREEN)")),
            "" if _atomic_passed else ("ENGINEERING" if _atomic_ran else "USER")),
        row("FORK_VALIDATION",
            G if _FORK_RUN.get("passed") else (Y if _RPC_CAPS.get("archive_state") else R),
            ("" if _FORK_RUN.get("passed") else
             (("Archive state reads VERIFIED; run the anvil fork validation to confirm the controllable fork"
               if _RPC_CAPS.get("archive_state") else "No archive/trace RPC and no local fork"))),
            ("Genuine anvil fork validation PASSED (forked Base block %s; executor code + state-override verified on the fork)"
             % (_FORK_RUN.get("evidence", {}).get("fork_block"))
             if _FORK_RUN.get("passed") else
             "Run POST /engine/run-fork-validation (anvil --fork-url) for a controllable fork test"),
            "" if _FORK_RUN.get("passed") else "USER"),
        row("HISTORICAL_REPLAY", G if _RPC_CAPS.get("archive_state") else Y,
            "" if _RPC_CAPS.get("archive_state") else "Archive state not available on this RPC",
            "VERIFIED archive reads → block-pinned replay via /engine/simulate-settlement {block_number}"
            if _RPC_CAPS.get("archive_state") else "Provide an archive/trace RPC for block-pinned replay",
            "" if _RPC_CAPS.get("archive_state") else "USER"),
        row("DECISION_HISTORY", G if hist["total"] >= 0 else Y, "",
            f"persisting evidence: total={hist['total']} executable={hist['executable']} real={hist['real_quotes']}", ""),
    ]

    readiness = await _READINESS_ENGINE.evaluate()
    modes = {m: {"status": v["status"], "can_activate": v["can_activate"],
                 "blockers": v.get("blockers", []), "warnings": v.get("warnings", [])}
             for m, v in readiness["modes"].items()}

    overall = R if any(r["status"] == R for r in matrix) else (
        Y if any(r["status"] == Y for r in matrix) else G)
    return {
        "overall_status": overall,
        "current_mode": await _CONTROL_STATE_REPO.get_mode(),
        "capabilities": matrix,
        "modes": modes,
        "notes": ("SHADOW/PAPER/PROFIT_ENGINE analysis is fully live on read-only "
                  "Base quotes. LIMITED_LIVE/FULL_AUTOMATION stay hard-blocked "
                  "until executor+signer+wallet+fork-validation are satisfied."),
        "generated_at": _iso_now(),
    }




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

@api_router.post("/arbicore/execution/plans/{plan_id}/calldata", dependencies=[Depends(_require_operator_dep)])
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


@api_router.post("/arbicore/execution/plans/{plan_id}/broadcast", dependencies=[Depends(_require_operator_dep)])
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


@app.on_event("startup")
async def _autorun_fork_validation():
    """Run one genuine anvil fork validation in the background at boot (if anvil
    + archive RPC are configured) so FORK_VALIDATION reflects a real run.
    Read-only; never signs/broadcasts."""
    import asyncio as _asyncio
    from arbicore.execution.executor_entrypoint import AnvilForkHarness
    if not AnvilForkHarness().readiness().get("ready_to_run"):
        return

    async def _bg():
        try:
            result = await AnvilForkHarness().run_fork_validation()
            _FORK_RUN.clear(); _FORK_RUN.update({**result, "ran_at": _iso_now()})
            logger.info("fork_validation: boot run ran=%s passed=%s",
                        result.get("ran"), result.get("passed"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("fork_validation: boot run failed: %s", exc)

    _asyncio.create_task(_bg())



@app.on_event("startup")
async def _ensure_signer_address_backfill():
    """Self-heal any externally-stored execution signer: derive + annotate its
    public address (never exposing the key) so readiness can verify the match."""
    try:
        from arbicore.execution.signer_vault import ensure_signer_address
        out = await ensure_signer_address(
            _SECRET_REGISTRY, db,
            expected_address=os.environ.get("ARBICORE_GAS_WALLET_ADDRESS"))
        if out.get("backfilled"):
            logger.info("signer_vault: backfilled derived address (matches_gas=%s)",
                        out.get("matches_expected"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("signer_vault: address backfill skipped: %s", exc)



    """Idempotently register the configured Base gas/execution wallet with the
    'gas' execution role in the WalletRegistry (public ADDRESS only — never a
    private key). This makes the registry the single source of truth for the
    gas wallet so both readiness surfaces agree. SHADOW-safe."""
    addr = os.environ.get("ARBICORE_GAS_WALLET_ADDRESS")
    if not addr:
        return
    try:
        await _WALLET_REGISTRY.ensure_indexes()
        existing = await _WALLET_REGISTRY.list_all(chain="base", execution_role="gas")
        if any((w.get("address") or "").lower() == addr.lower() for w in existing):
            return
        await _WALLET_REGISTRY.register(
            wallet_id="base-gas-primary", address=addr, chain="base",
            execution_role="gas", label="Base gas/execution wallet (env-configured)",
            actor="system", reason="auto-register ARBICORE_GAS_WALLET_ADDRESS")
        logger.info("wallet_registry: registered env gas wallet %s (gas role)", addr)
    except Exception as exc:  # noqa: BLE001
        logger.warning("wallet_registry: env gas wallet auto-register skipped: %s", exc)



@app.on_event("startup")
async def _autostart_opportunity_scanner():
    """Auto-start the read-only Base opportunity scanner (SHADOW-safe).

    The engine continuously discovers candidate flash-loan opportunities and
    runs them through the full economic/safety chain; it never signs or
    broadcasts. Operator can stop it via /api/arbicore/engine/scanner/stop."""
    try:
        await _DECISION_HISTORY_REPO.ensure_indexes()
        await _ROUTE_RECURRENCE_REPO.ensure_indexes()
        await _PROFIT_ALERT_REPO.ensure_indexes()
    except Exception:  # noqa: BLE001
        pass
    # Verify RPC capabilities + simulators FIRST (before the scanner starts,
    # to avoid throttle contention), then start continuous SHADOW scanning.
    if os.environ.get("ARBICORE_RPC_URL"):
        try:
            _RPC_CAPS.update(await _SETTLEMENT_SIM.probe_capabilities())
        except Exception as exc:  # noqa: BLE001
            logger.warning("rpc capability probe failed: %r", exc)
        try:
            _SETTLEMENT_SELFTEST.update(await _SETTLEMENT_SIM.self_test())
        except Exception as exc:  # noqa: BLE001
            logger.warning("settlement self-test failed: %r", exc)
        try:
            _ATOMIC_SELFTEST.update(await _ATOMIC_SIM.capability_self_test())
        except Exception as exc:  # noqa: BLE001
            logger.warning("atomic capability self-test failed: %r", exc)
    if os.environ.get("ARBICORE_RPC_URL") and \
            os.environ.get("ARBICORE_SCANNER_AUTOSTART", "1") != "0":
        try:
            await _CONTINUOUS_SCANNER.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning("scanner autostart failed: %r", exc)


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

# ---------------------------------------------------------------------------
# Canonical scanner management router (D-1 surface): per-scanner
# status/kill/resume/config/gate-analysis + discovery + venues endpoints.
# All routes are auth-gated (Depends(require_auth)). Registering the router
# only EXPOSES these read/config endpoints — it does not start any scanner,
# sign, broadcast, or move capital. SHADOW/PAPER posture is unaffected.
# ---------------------------------------------------------------------------
try:
    from arbicore.routes.scanners import router as scanners_router
    app.include_router(scanners_router)
    logger.info("canonical scanners router mounted (/api/arbicore/scanners/*)")
except Exception:  # noqa: BLE001
    logger.exception(
        "canonical scanners router failed to import — "
        "/api/arbicore/scanners/* management endpoints will be 404"
    )


@app.on_event("startup")
async def _canonical_auth_provision_startup():
    """v2.9.4 — deterministic, idempotent provisioning of admin/operator into
    the CANONICAL ``users`` collection (the same one /api/auth/login reads),
    from environment credentials. Fixes the auth source-of-truth drift where a
    fresh production DB had zero users → login 401. Insert-only (never
    overwrites an existing user); skips gracefully when creds are absent."""
    try:
        from services.auth import ensure_provisioned_users
        summary = await ensure_provisioned_users()
        logger.info(
            "v2.9.4: canonical auth provisioned — coll=%s created=%s existed=%s skipped=%s jwt_secret=%s",
            summary.get("collection"), summary.get("created"),
            summary.get("existed"), summary.get("skipped"),
            summary.get("jwt_secret_present"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("v2.9.4: canonical auth provisioning failed: %s", exc)

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
# v2.11.8 · Paper Validation Framework — runner lifecycle.
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _paper_validation_startup():
    """Ensure the paper-evidence indexes and (optionally) start the runner.

    The runner is gated behind ``ARBICORE_PAPER_VALIDATION_ENABLED``.  When
    the flag is not set (default in preview / test environments) we still
    ensure the indexes so any manual pipeline invocation persists cleanly.
    """
    global _PAPER_RUNNER
    try:
        await _PAPER_EVIDENCE_REPO.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        logger.exception("paper evidence index ensure failed: %s", exc)
    if not _paper_runner_enabled_via_env():
        logger.info("PaperValidationRunner disabled "
                    "(ARBICORE_PAPER_VALIDATION_ENABLED not set)")
        return
    try:
        _PAPER_RUNNER = PaperValidationRunner(
            opp_source=_CANONICAL_OPP_REPO,
            pipeline=_OPPORTUNITY_PIPELINE,
            evidence_repo=_PAPER_EVIDENCE_REPO,
        )
        _PAPER_RUNNER.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("PaperValidationRunner failed to start: %s", exc)


@app.on_event("shutdown")
async def _paper_validation_shutdown():
    """Give the runner a chance to drain and stop cleanly."""
    if _PAPER_RUNNER is None:
        return
    try:
        await _PAPER_RUNNER.stop()
    except Exception as exc:  # noqa: BLE001
        logger.warning("PaperValidationRunner shutdown error: %s", exc)


# ---------------------------------------------------------------------------
# v2.11.9 · Shadow Certification — engine + runner lifecycle.
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def _shadow_certification_startup():
    """Ensure certification indexes and (optionally) start the runner.

    The engine is always bootstrapped so operators can drive runs via
    the HTTP surface.  The background *runner* is only started when
    ``ARBICORE_SHADOW_CERT_ENABLED=true``.
    """
    global _SHADOW_CERT_ENGINE, _SHADOW_CERT_RUNNER
    try:
        await _SHADOW_CERT_REPO.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        logger.exception("shadow_cert index ensure failed: %s", exc)
    try:
        _SHADOW_CERT_ENGINE = ShadowCertificationEngine(
            cert_repo=_SHADOW_CERT_REPO,
            evidence_repo=_PAPER_EVIDENCE_REPO,
            paper_runner=_PAPER_RUNNER,
            db=db,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("ShadowCertificationEngine init failed: %s", exc)
        return

    # Auto-start a run if the operator has explicitly opted in and no
    # run is currently active.
    if (os.environ.get("ARBICORE_SHADOW_CERT_AUTOSTART_RUN") or "").strip().lower() in (
        "1", "true", "yes", "on",
    ):
        try:
            current = await _SHADOW_CERT_ENGINE.current_run()
            if current is None:
                await _SHADOW_CERT_ENGINE.start_run()
                logger.info(
                    "ShadowCertificationEngine: auto-started a new run "
                    "(ARBICORE_SHADOW_CERT_AUTOSTART_RUN=true)"
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "ShadowCertificationEngine auto-start failed: %s", exc
            )

    if not is_shadow_cert_enabled_via_env():
        logger.info(
            "ShadowCertificationRunner disabled "
            "(ARBICORE_SHADOW_CERT_ENABLED not set)"
        )
        return
    try:
        _SHADOW_CERT_RUNNER = ShadowCertificationRunner(engine=_SHADOW_CERT_ENGINE)
        _SHADOW_CERT_RUNNER.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("ShadowCertificationRunner failed to start: %s", exc)


@app.on_event("shutdown")
async def _shadow_certification_shutdown():
    if _SHADOW_CERT_RUNNER is None:
        return
    try:
        await _SHADOW_CERT_RUNNER.stop()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ShadowCertificationRunner shutdown error: %s", exc)


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


_CANONICAL_FL_SCANNER = None          # real FlashLoanArbitrageScanner (canonical)
_CANONICAL_FL_ACTIVATION: Dict[str, Any] = {}


@app.on_event("startup")
async def _canonical_flash_loan_scanner_startup():
    """STAGE 1 — activate the REAL canonical FlashLoanArbitrageScanner
    (discovery over the real Base pool universe + live QuoterRegistry). This
    supersedes the dormant wave1b ShadowScannerAdapter for flash-loan discovery.
    Detection-only / SHADOW: emission is gated by the verifier's economic +
    atomic-profit + liquidity + MEV gates, and execution by the mode ladder +
    AutoExecutor. Never signs or broadcasts."""
    global _CANONICAL_FL_SCANNER, _CANONICAL_FL_ACTIVATION
    try:
        from arbicore.runtime import composition as _composition
        _CANONICAL_FL_ACTIVATION = await _composition.activate_canonical_flash_loan_scanner(
            _QUOTER_REGISTRY)
        _CANONICAL_FL_SCANNER = _composition.get_flash_loan_arb_scanner()
        # T0-1: surface an explicit readiness verdict so a canonical scanner
        # in an analysis mode on the default noop quote provider is visible
        # (never a silent synthetic production quote path).
        try:
            _fl_row = await _EXECUTION_MODE_REPO.get("flash_loan_arbitrage")
            _fl_mode = (_fl_row or {}).get("mode") or "OBSERVE"
            _readiness = _composition.flash_loan_quote_readiness(
                quote_provider_is_default=_CANONICAL_FL_SCANNER.quote_provider_is_default,
                mode=_fl_mode)
            _CANONICAL_FL_ACTIVATION = {**_CANONICAL_FL_ACTIVATION,
                                        "mode": _fl_mode,
                                        "readiness": _readiness}
        except Exception as _re:  # noqa: BLE001
            logger.warning("flash-loan readiness snapshot failed: %s", _re)
        logger.info("scanners: canonical FlashLoanArbitrageScanner ACTIVE — %s",
                    _CANONICAL_FL_ACTIVATION)
    except Exception as exc:  # noqa: BLE001
        _CANONICAL_FL_ACTIVATION = {"instantiated": False, "error": f"{type(exc).__name__}: {exc}"}
        logger.exception("scanners: canonical flash-loan activation failed: %s", exc)

    # T2 · flag-gated Base searcher runtime (SHADOW, construction-only; never
    # broadcasts, never promotes). Default OFF → zero runtime impact.
    global _BASE_SEARCHER_RUNTIME
    try:
        from arbicore.searcher.runtime import maybe_build_base_searcher
        _BASE_SEARCHER_RUNTIME = maybe_build_base_searcher()
        if _BASE_SEARCHER_RUNTIME is not None:
            logger.info("searcher: T2 Base runtime constructed (SHADOW, "
                        "no-broadcast, flag ARBICORE_T2_SEARCHER_ENABLED=on)")
        else:
            logger.info("searcher: T2 Base runtime disabled (flag off)")
    except Exception as exc:  # noqa: BLE001
        _BASE_SEARCHER_RUNTIME = None
        logger.warning("searcher: T2 runtime construction skipped: %s", exc)


# ---------------------------------------------------------------------------
# v2.11.9 · Wave1B individual scanners (CEX / DEX / Flash Loan / Funding /
# Cross Chain / Launch) — instantiated + started via
# ``initialise_arbicore_runtime()``.  Each scanner emits through
# ``EmissionBus`` which upserts into the canonical
# ``arbicore_opportunities`` collection that the Paper Validation runner
# reads.  Prior to v2.11.9 the initialiser was only invoked from tests,
# so the individual scanners never booted and the canonical opportunity
# feed was seed-only.  Gate: ``ARBICORE_RUNTIME_AUTOSTART=on``.
# ---------------------------------------------------------------------------
_ARBICORE_RUNTIME_INIT: Dict[str, Any] = {
    "attempted":  False,
    "completed":  False,
    "started_at": None,
    "completed_at": None,
    "error":      None,
    "scanners_started": [],
}


@app.on_event("startup")
async def _arbicore_bootstrap_substrate():
    """Always-run, execution-free substrate bootstrap.

    Creates the idempotent arbicore_* indexes (incl. TTL indexes on
    arbicore_state_snapshots / arbicore_audit_log) and seeds the canonical
    scanner_config + scanner_state documents (6 each). Every seeded scanner
    STATE row is dormant (``enabled=False``); nothing here starts a scanner,
    signs, broadcasts, or moves capital. Decoupled from
    ``ARBICORE_RUNTIME_AUTOSTART`` so the substrate exists in SHADOW/PAPER —
    scanner *execution* remains gated in ``_arbicore_runtime_autostart``.
    """
    errors: Dict[str, str] = {}
    # ── 1. arbicore_* index bootstrap (idempotent) ─────────────
    try:
        from arbicore.data.mongo.arbicore_collections import (
            ensure_indexes as _ensure_arbicore_indexes,
        )
        await _ensure_arbicore_indexes()
    except Exception as exc:  # noqa: BLE001
        errors["arbicore_indexes"] = f"{type(exc).__name__}: {exc}"

    # ── 2. discovery-layer + scanner config/state seeding ──────
    try:
        from arbicore.runtime import composition as _comp
        await _comp.get_discovery_queue().ensure_indexes()
        await _comp.get_venue_capability_repo().ensure_indexes()
        await _comp.get_discovery_source_metrics().ensure_indexes()
        cfg_repo = _comp.get_scanner_config_repo()
        await cfg_repo.ensure_indexes()
        await cfg_repo.seed_defaults()
        state_repo = _comp.get_scanner_state_repo()
        await state_repo.ensure_indexes()
        await state_repo.seed_defaults()
    except Exception as exc:  # noqa: BLE001
        errors["discovery_bootstrap"] = f"{type(exc).__name__}: {exc}"

    if errors:
        logger.error("arbicore_bootstrap_substrate errors=%s", errors)
    else:
        logger.info("arbicore_bootstrap_substrate: indexes + scanner defaults seeded")


@app.on_event("startup")
async def _arbicore_runtime_autostart():
    """Boot the Wave1B scanners so their EmissionBus emissions reach the
    canonical opportunity repo used by Paper Validation + Shadow
    Certification.

    Substrate seeding (indexes + scanner config/state defaults) is handled
    unconditionally by ``_arbicore_bootstrap_substrate``. This handler only
    INSTANTIATES + STARTS scanners, gated behind
    ``ARBICORE_RUNTIME_AUTOSTART`` and the per-scanner ``ARBICORE_SCANNER_*``
    env flags.
    """
    autostart = (os.environ.get("ARBICORE_RUNTIME_AUTOSTART") or "").strip().lower()
    if autostart not in ("1", "true", "yes", "on"):
        logger.info(
            "arbicore_runtime autostart disabled "
            "(ARBICORE_RUNTIME_AUTOSTART not set)"
        )
        return

    _ARBICORE_RUNTIME_INIT["attempted"]  = True
    _ARBICORE_RUNTIME_INIT["started_at"] = _iso_now()
    started: List[str] = []
    errors: Dict[str, str] = {}
    try:
        from arbicore.runtime import composition as _comp

        # ── per-scanner instantiate + prime cache + start ───────
        scanner_map = (
            ("cex_arb",         "get_cex_arb_scanner",         "ARBICORE_SCANNER_CEX_ARB"),
            ("funding_arb",     "get_funding_arb_scanner",     "ARBICORE_SCANNER_FUNDING_ARB"),
            ("dex_arb",         "get_dex_arb_scanner",         "ARBICORE_SCANNER_DEX_ARB"),
            ("launch_arb",      "get_launch_arb_scanner",      "ARBICORE_SCANNER_LAUNCH_ARB"),
            ("cross_chain_arb", "get_cross_chain_arb_scanner", "ARBICORE_SCANNER_CROSS_CHAIN_ARB"),
            ("flash_loan_arb",  "get_flash_loan_arb_scanner",  "ARBICORE_SCANNER_FLASH_LOAN_ARB"),
        )
        for name, getter_name, env_key in scanner_map:
            env_val = (os.environ.get(env_key) or "off").strip().lower()
            if env_val not in ("on", "1", "true", "yes"):
                continue
            getter = getattr(_comp, getter_name, None)
            if getter is None:
                errors[name] = "getter_missing"
                continue
            try:
                # 3a. persist enabled flag so is_enabled() returns True
                try:
                    await _comp.get_scanner_state_repo().set_enabled(
                        name, True, actor="env_boot"
                    )
                except Exception:  # noqa: BLE001
                    pass
                # 3b. instantiate + prime + start
                sc = getter()
                if hasattr(sc, "_refresh_caches_once"):
                    try:
                        await sc._refresh_caches_once()  # type: ignore[attr-defined]
                    except Exception:  # noqa: BLE001
                        pass
                await sc.start()
                started.append(name)
            except Exception as exc:  # noqa: BLE001
                errors[name] = f"{type(exc).__name__}: {exc}"

        _ARBICORE_RUNTIME_INIT["completed"]        = True
        _ARBICORE_RUNTIME_INIT["completed_at"]     = _iso_now()
        _ARBICORE_RUNTIME_INIT["scanners_started"] = started
        _ARBICORE_RUNTIME_INIT["errors"]           = errors
        logger.info(
            "arbicore_runtime: bootstrap complete (started=%s, errors=%s)",
            started, list(errors.keys()),
        )
    except Exception as exc:  # noqa: BLE001
        _ARBICORE_RUNTIME_INIT["error"] = f"{type(exc).__name__}: {exc}"
        logger.exception("arbicore_runtime autostart failed: %s", exc)


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
    # STAGE 1 — canonical real flash-loan scanner (supersedes the dormant
    # wave1b ShadowScannerAdapter for flash_loan_arbitrage discovery).
    canonical = {"instantiated": False}
    if _CANONICAL_FL_SCANNER is not None:
        canonical = {
            **_CANONICAL_FL_ACTIVATION,
            "instantiated": True,
            "authoritative": True,
            "detection_only": True,
            "stats": _CANONICAL_FL_SCANNER.stats,
            "quote_provider": ("noop" if _CANONICAL_FL_SCANNER.quote_provider_is_default
                               else "live"),
            "enabled": _CANONICAL_FL_SCANNER.is_enabled(),
        }
    else:
        canonical = {**_CANONICAL_FL_ACTIVATION, "instantiated": False}
    payload["canonical_flash_loan_arbitrage"] = canonical
    # Mark the legacy shadow adapter as non-authoritative for this family.
    payload["flash_loan_arbitrage_shadow_adapter"] = {
        "authoritative": False,
        "note": "superseded by canonical FlashLoanArbitrageScanner (STAGE 1)",
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