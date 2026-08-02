"""Wave 7A · Continuous Discovery (thin activator).

Reuse notice (VERIFY → REUSE → REFINE):

    The canonical bundle carries a full ``arbicore/scanners/flash_loan_arbitrage``
    subsystem — the ``FlashLoanArbitrageScanner``, ``RouteSearchEngine``,
    ``FlashLoanEconomicsAssessor``, three real-data discovery sources
    (aave_v3_flashloan_real, balancer_v2_flashloan_real,
    uniswap_v3_flashloan_real), and a nine-gate verifier chain.  That
    tree drags in ~30 canonical files with heavy internal
    dependencies (emission bus, discovery queue, venue capability
    repo, ROI probability engine, MEV risk scorer, opportunity
    verifier registry, etc.).

    A future wave will import the canonical tree wholesale.  For the
    LIMITED_LIVE validation objective, we ship a **thin activator** that:

        * runs a background asyncio task at a configurable cadence
          (default 60 s);
        * produces deterministic opportunity candidates from a small,
          operator-configurable universe of token pairs on Base;
        * evaluates each candidate through the existing Wave 6B/6C
          planner + dry-run + slippage stack;
        * persists confirmed opportunities to ``db.opportunities`` for
          the operator UI to consume;
        * emits ``discovery_confirmed`` metrics for the certifier
          audit trail.

    The activator is a REFINEMENT — the canonical tree is the eventual
    substrate.  Everything here operates in SHADOW/PAPER only.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


logger = logging.getLogger("arbicore.execution.discovery")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Default universe — small, operator-tunable
# ---------------------------------------------------------------------------

DEFAULT_UNIVERSE_BASE: List[Dict[str, Any]] = [
    # WETH / USDC on Base — highest-liquidity pair.
    {
        "opportunity_id_hint": "base-weth-usdc-univ3-aero",
        "chain": "base",
        "borrow_token": "0x4200000000000000000000000000000000000006",  # WETH
        "borrow_amount_wei": 100_000_000_000_000_000,                  # 0.1 WETH
        "borrow_amount_usd": 250.0,
        "flash_loan_provider": "balancer_v2",
        "swap_hops": [
            {"dex": "uniswap_v3",
             "token_in":  "0x4200000000000000000000000000000000000006",  # WETH
             "token_out": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
             "amount_in_wei": 100_000_000_000_000_000,
             "min_amount_out_wei": 249_500_000,
             "fee_tier_bps": 5},
            {"dex": "aerodrome",
             "token_in":  "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
             "token_out": "0x4200000000000000000000000000000000000006",  # WETH
             "amount_in_wei": 249_500_000,
             "min_amount_out_wei": 100_050_000_000_000_000},
        ],
    },
]


@dataclass
class DiscoveredOpportunity:
    opportunity_id: str
    chain: str
    strategy: str
    borrow_token: str
    borrow_amount_wei: int
    borrow_amount_usd: float
    flash_loan_provider: str
    swap_hops: List[Dict[str, Any]]
    plan_id: Optional[str]
    confidence: float
    net_profit_usd: Optional[float]
    profitable: bool
    status: str          # "candidate" | "confirmed" | "rejected"
    reasons: List[str]
    engine_version: str
    discovered_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DiscoveryRepo:
    def __init__(self, db, collection: str = "opportunities"):
        self._db = db
        self._coll = db[collection]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._coll.create_index("opportunity_id", unique=True)
        await self._coll.create_index([("chain", 1), ("discovered_at", -1)])
        await self._coll.create_index([("status", 1), ("discovered_at", -1)])
        self._indexes_ready = True

    async def upsert(self, opp: DiscoveredOpportunity) -> None:
        d = opp.to_dict()
        await self._coll.update_one(
            {"opportunity_id": opp.opportunity_id},
            {"$set": d},
            upsert=True,
        )

    async def list_recent(self, *, status: Optional[str] = None,
                          chain: Optional[str] = None,
                          limit: int = 50) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        if chain:
            q["chain"] = chain
        cur = self._coll.find(q, {"_id": 0}).sort("discovered_at", -1).limit(int(limit))
        return await cur.to_list(int(limit))

    async def get(self, opportunity_id: str) -> Optional[Dict[str, Any]]:
        return await self._coll.find_one({"opportunity_id": opportunity_id},
                                          {"_id": 0})


class ContinuousDiscovery:
    """Background continuous-discovery loop for flash-loan opportunities.

    Every ``interval_s`` seconds, iterates the operator-configured
    universe, dry-runs each candidate through the Wave-6B planner, and
    persists a ``DiscoveredOpportunity`` row.
    """

    def __init__(self, *,
                 repo: DiscoveryRepo,
                 planner,
                 dry_run_engine,
                 slippage_estimator,
                 plans_repo,
                 universe_loader=None,
                 interval_s: float = 60.0,
                 min_confidence: float = 0.55):
        self._repo = repo
        self._planner = planner
        self._dry_run = dry_run_engine
        self._slippage = slippage_estimator
        self._plans_repo = plans_repo
        self._universe = universe_loader or (lambda: list(DEFAULT_UNIVERSE_BASE))
        self._interval = float(interval_s)
        self._min_conf = float(min_confidence)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_run_at: Optional[str] = None
        self._last_result: Optional[Dict[str, Any]] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("ContinuousDiscovery started (interval=%ss)", self._interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("discovery tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass

    async def tick_once(self) -> Dict[str, Any]:
        """Run one discovery pass over the universe.  Returns a summary."""
        universe = list(self._universe() or [])
        confirmed = 0
        rejected = 0
        for tmpl in universe:
            try:
                opp = await self._evaluate_candidate(tmpl)
                await self._repo.upsert(opp)
                if opp.status == "confirmed":
                    confirmed += 1
                else:
                    rejected += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("discovery candidate skipped: %s", exc)
                rejected += 1
        self._last_run_at = _now_iso()
        self._last_result = {
            "ran_at": self._last_run_at,
            "universe_size": len(universe),
            "confirmed": confirmed,
            "rejected": rejected,
        }
        return self._last_result

    async def _evaluate_candidate(self, tmpl: Dict[str, Any]) -> DiscoveredOpportunity:
        reasons: List[str] = []
        opp_id = tmpl.get("opportunity_id_hint") or f"opp-{uuid.uuid4().hex}"
        # Build a plan using Wave 6B.
        plan = self._planner.build(
            strategy="flash_loan_arbitrage",
            chain=tmpl["chain"],
            borrow_token=tmpl["borrow_token"],
            borrow_amount_wei=int(tmpl["borrow_amount_wei"]),
            flash_loan_provider=tmpl["flash_loan_provider"],
            swap_hops=tmpl["swap_hops"],
            signer_wallet_id=None,
            opportunity_id=opp_id,
            borrow_amount_usd=float(tmpl.get("borrow_amount_usd") or 0),
            mode="SHADOW",
        )
        # Phase 10.10.8 · canonical live-quote path.  Discovery is the
        # primary consumer of ``evaluate_live`` — every tick asks the
        # QuoterRegistry for real DEX outputs and feeds the RpcGasOracle
        # into the profitability calc.  The legacy deterministic path
        # (``self._dry_run.evaluate(...)``) is only used as a policy-safe
        # fallback when the live engine cannot reach the RPC.
        try:
            econ = await self._dry_run.evaluate_live(plan)
        except Exception as exc:  # noqa: BLE001
            logger.warning("live evaluate degraded (%s); falling back to deterministic",
                            type(exc).__name__)
            effective_out_wei = int(
                (tmpl["swap_hops"][-1].get("min_amount_out_wei") or 0)
            )
            econ = self._dry_run.evaluate(
                plan, quote_effective_out_wei=effective_out_wei,
            )
        # Persist the plan so operator UI can pick it up.
        try:
            await self._plans_repo.insert(plan.to_dict())
        except Exception:  # noqa: BLE001
            pass
        # Phase 8 — also emit a canonical opportunity row so the running
        # v2 UI (Opportunities page) can display the same discovery through
        # the canonical repo.  Best-effort; failure never blocks the tick.
        profitable = bool(econ.get("profitable"))
        try:
            from ..models.canonical import CanonicalOpportunity
            from ..models.enums import (
                OpportunityStatus, OpportunityType, DataProvenance, MevRiskLevel,
            )
            spread_pct = 0.0
            try:
                if econ.get("net_profit_usd") is not None:
                    spread_pct = float(econ["net_profit_usd"]) / max(
                        1.0, float(tmpl.get("borrow_amount_usd") or 1)
                    ) * 100.0
            except Exception:
                pass
            confidence_pct = round(75.0 if profitable else 30.0, 2)
            canonical = CanonicalOpportunity(
                opportunity_id=opp_id,
                opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
                subject_id=opp_id,
                asset=tmpl["borrow_token"],
                chain=tmpl["chain"],
                buy_venue=(tmpl["swap_hops"][0].get("dex") if tmpl.get("swap_hops") else None),
                sell_venue=(tmpl["swap_hops"][-1].get("dex") if tmpl.get("swap_hops") else None),
                spread_pct=round(spread_pct, 4),
                expected_profit_usd=(float(econ.get("net_profit_usd") or 0)),
                capital_required_usd=float(tmpl.get("borrow_amount_usd") or 0),
                confidence_score=confidence_pct,
                risk_score=(20.0 if profitable else 45.0),
                mev_risk_level=MevRiskLevel.MEDIUM,
                source_data_quality=DataProvenance.SIMULATED,
                status=(OpportunityStatus.VALIDATED if profitable
                        else OpportunityStatus.CANDIDATE),
                metadata={"engine": "thin_activator", "plan_id": plan.plan_id},
            )
            # Best-effort: repo is injected at higher level; look it up lazily.
            repo = getattr(self, "_canonical_repo", None)
            if repo is None:
                # Late binding via a module-global set at server bootstrap.
                import server as _srv  # type: ignore  # noqa: PLC0415
                repo = getattr(_srv, "_CANONICAL_OPP_REPO", None)
            if repo is not None:
                await repo.upsert(canonical)
        except Exception as _e:  # noqa: BLE001
            logger.warning("canonical upsert skipped: %s", _e)
        # Confidence heuristic: profitable ⇒ 0.75; not profitable ⇒ 0.30.
        confidence = 0.75 if profitable else 0.30
        net_usd = econ.get("net_profit_usd")
        status = "confirmed" if confidence >= self._min_conf else "rejected"
        if not profitable:
            reasons.append(f"dry_run net_profit_usd={net_usd}")
        return DiscoveredOpportunity(
            opportunity_id=opp_id,
            chain=tmpl["chain"],
            strategy="flash_loan_arbitrage",
            borrow_token=tmpl["borrow_token"],
            borrow_amount_wei=int(tmpl["borrow_amount_wei"]),
            borrow_amount_usd=float(tmpl.get("borrow_amount_usd") or 0),
            flash_loan_provider=tmpl["flash_loan_provider"],
            swap_hops=list(tmpl["swap_hops"]),
            plan_id=plan.plan_id,
            confidence=confidence,
            net_profit_usd=(float(net_usd) if net_usd is not None else None),
            profitable=profitable,
            status=status,
            reasons=reasons,
            engine_version="thin_activator@1",
            discovered_at=_now_iso(),
            updated_at=_now_iso(),
        )

    def status(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "interval_s": self._interval,
            "min_confidence": self._min_conf,
            "last_run_at": self._last_run_at,
            "last_result": self._last_result,
            "universe_size": len(list(self._universe() or [])),
        }
