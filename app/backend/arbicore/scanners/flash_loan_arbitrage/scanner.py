"""ArbiCore X — Phase D D-6.1 Flash-Loan Arbitrage scanner orchestrator.

SIXTH and FINAL authorised EmissionBus call site across the scanner
tree. INV-1/2/3 preserved. Detection only.

Boot posture: DORMANT.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ...data.discovery_queue import DiscoveryQueue
from ...intelligence.roi_probability import ROIProbabilityEngine
from ...models.discovery import DiscoveryCandidate, VerifiedOutcome
from ...models.enums import OpportunityType
from ..cross_chain_arbitrage.bridge_intelligence import MevRiskScorer
from ..discovery_source import DiscoverySourceRegistry
from ..opportunity_verifier import OpportunityVerifierRegistry
from .economics import FlashLoanEconomicsAssessor
from .filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)
from .route_search import RouteSearchEngine
from .sources import build_all_flash_loan_sources
from .verifier import (
    FlashLoanOpportunityVerifier, QuoteProvider, noop_quote_provider,
)

logger = logging.getLogger("arbicore.scanners.flash_loan_arb")


class FlashLoanArbitrageScanner:
    """Orchestrator for ``OpportunityType.FLASH_LOAN_ARBITRAGE``.

    Discovery → cooperative queue → claim → verify → (gate) → emit.
    The sole emission call site lives inside ``_tick``.
    """

    def __init__(
        self,
        *,
        emission_bus,
        discovery_queue: DiscoveryQueue,
        venue_capability_repo,
        config_loader: Callable[[], Dict[str, Any]],
        state_loader: Callable[[], Dict[str, Any]],
        pool_loader: Callable[[str], List[Any]],
        quote_provider: Optional[QuoteProvider] = None,
        chain_liveness_loader: Optional[
            Callable[[str], Dict[str, float]]] = None,
        confidence_engine=None,
    ) -> None:
        self._bus = emission_bus
        self._queue = discovery_queue
        self._caps = venue_capability_repo
        self._cfg = config_loader
        self._state = state_loader
        self._confidence_engine = confidence_engine

        cfg0 = config_loader() or {}
        rs_cfg = cfg0.get("route_search") or {}
        gate_cfg = cfg0.get("gate_thresholds") or {}
        roi_cfg = cfg0.get("roi_probability") or {}
        borrow_amount = float(cfg0.get("default_notional_usd") or 10_000.0)

        # ── Route search engine (the genuinely novel substrate) ─────────
        self._route_engine = RouteSearchEngine(
            pool_loader=pool_loader,
            max_hops=int(rs_cfg.get("max_hops", 4)),
            wall_clock_cap_s=float(rs_cfg.get("wall_clock_cap_s", 5.0)),
            candidate_cap=int(rs_cfg.get("candidate_cap", 64)),
            min_pool_tvl_usd=float(rs_cfg.get("min_pool_tvl_usd", 100_000)),
        )

        # ── Discovery sources ───────────────────────────────────────────
        self._sources = build_all_flash_loan_sources(
            route_engine=self._route_engine, config_loader=config_loader)
        self._source_registry = DiscoverySourceRegistry()
        for s in self._sources:
            self._source_registry.register(s)

        # ── Gates ───────────────────────────────────────────────────────
        gate_defaults = dict(gate_cfg.get("default", {}))
        self._gate_7 = FlashLoanGate7AtomicProfit(thresholds=gate_defaults)
        self._gate_8 = FlashLoanGate8LiquidityDepth(thresholds=gate_defaults)
        self._gate_9 = FlashLoanGate9FlashLoanMev(thresholds=gate_defaults)

        # ── MEV scorer (reused from D-5 — lightweight, ~95 LOC) ─────────
        self._mev = MevRiskScorer()

        # ── Verifier composition ────────────────────────────────────────
        self._quote_provider: QuoteProvider = (
            quote_provider or noop_quote_provider)
        self._verifier = FlashLoanOpportunityVerifier(
            quote_provider=self._quote_provider,
            economics_assessor=FlashLoanEconomicsAssessor(
                roi_engine=ROIProbabilityEngine(
                    min_sample=int(roi_cfg.get("min_sample_size", 8)),
                    winsorize_pct=float(roi_cfg.get("winsor_low_pct", 5.0))
                                    / 100.0,
                ),
                default_borrow_amount_usd=borrow_amount,
            ),
            mev_scorer=self._mev,
            chain_liveness_loader=chain_liveness_loader,
            gate_7=self._gate_7,
            gate_8=self._gate_8,
            gate_9=self._gate_9,
            default_borrow_amount_usd=borrow_amount,
        )
        self._verifier_registry = OpportunityVerifierRegistry()
        self._verifier_registry.register(self._verifier)

        self._worker_id = f"flash_loan_arb:{uuid.uuid4().hex[:8]}"
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._stats: Dict[str, Any] = {
            "iterations": 0, "rows_emitted": 0,
            "verifier_confirmed": 0, "verifier_denied": 0,
            "verifier_errors": 0, "candidates_claimed": 0,
            "gate_rejections": {
                "gate_7_atomic_profit": 0,
                "gate_8_liquidity_depth": 0,
                "gate_9_flash_loan_mev": 0,
            },
            "denied_venue_unreadable": 0,
            "last_run_at": None,
            "last_error": None,
        }

    # -- accessors --------------------------------------------------------

    @property
    def opportunity_type(self) -> OpportunityType:
        return OpportunityType.FLASH_LOAN_ARBITRAGE

    @property
    def scanner_id(self) -> str:
        return "flash_loan_arb"

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    @property
    def source_registry(self) -> DiscoverySourceRegistry:
        return self._source_registry

    @property
    def verifier_registry(self) -> OpportunityVerifierRegistry:
        return self._verifier_registry

    @property
    def route_engine(self) -> RouteSearchEngine:
        return self._route_engine

    @property
    def quote_provider_is_default(self) -> bool:
        return self._quote_provider is noop_quote_provider

    @property
    def config_loader(self) -> Callable[[], Dict[str, Any]]:
        return self._cfg

    def is_enabled(self) -> bool:
        st = self._state() or {}
        return bool(st.get("enabled", False))

    # -- operator hooks ---------------------------------------------------

    def set_quote_provider(self, provider: QuoteProvider) -> None:
        """Operator-controlled wiring of a live quote provider."""
        self._quote_provider = provider
        self._verifier.quote_provider = provider

    # -- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        logger.info(
            "FlashLoanArbitrageScanner started: worker=%s quote_provider=%s",
            self._worker_id,
            "default-noop" if self.quote_provider_is_default
            else "operator-provided",
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        for s in self._sources:
            try:
                await s.close()
            except Exception:  # noqa: BLE001
                pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"tick: {exc!r}"
                logger.exception("flash_loan scanner tick failed: %s", exc)
            cfg = self._cfg() or {}
            interval = float(cfg.get("interval_s") or 60.0)
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        """Single discover → claim → verify → emit cycle.

        This method is the ONLY place in the flash-loan subsystem that
        invokes the EmissionBus for FLASH_LOAN_ARBITRAGE (INV-2).
        """
        if not self.is_enabled():
            return
        self._stats["iterations"] += 1
        self._stats["last_run_at"] = time.time()

        # ---- 1. Discover --------------------------------------------------
        all_candidates: List[DiscoveryCandidate] = []
        for source in self._sources:
            try:
                cands = await source.discover()
                all_candidates.extend(cands)
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = (
                    f"discover[{source.source_id}]: {exc!r}")
        if all_candidates:
            try:
                await self._queue.upsert_many(all_candidates)
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"queue_upsert: {exc!r}"

        # ---- 2. Claim ------------------------------------------------------
        try:
            batch = await self._queue.claim_batch(
                self._worker_id, batch_size=32)
        except Exception as exc:  # noqa: BLE001
            self._stats["last_error"] = f"queue_claim: {exc!r}"
            return
        self._stats["candidates_claimed"] += len(batch)

        # ---- 3. Verify each candidate -------------------------------------
        for c in batch:
            if c.opportunity_type != OpportunityType.FLASH_LOAN_ARBITRAGE:
                await self._queue.mark_processed(
                    c.candidate_id, VerifiedOutcome.DENIED_NO_VERIFIER,
                    observed_at=c.hint_observed_at,
                )
                continue
            verifier = self._verifier_registry.get(c.opportunity_type)
            if verifier is None:
                await self._queue.mark_processed(
                    c.candidate_id, VerifiedOutcome.DENIED_NO_VERIFIER,
                    observed_at=c.hint_observed_at,
                )
                continue
            try:
                opp, outcome = await verifier.verify(c)
            except Exception as exc:  # noqa: BLE001
                self._stats["verifier_errors"] += 1
                self._stats["last_error"] = f"verify: {exc!r}"
                await self._queue.mark_processed(
                    c.candidate_id,
                    f"{VerifiedOutcome.ERROR_PREFIX}{type(exc).__name__}",
                    observed_at=c.hint_observed_at,
                )
                continue

            # ---- 4. Emit (sole FLASH_LOAN_ARBITRAGE emit site) ──────────
            if opp is not None and outcome.startswith(
                    VerifiedOutcome.CONFIRMED_PREFIX):
                try:
                    # ── _TICK_EMIT: SOLE FLASH_LOAN_ARBITRAGE emit site ──
                    await self._bus.emit(
                        opp,
                        venue_ids=[v for v in
                                    (opp.buy_venue, opp.sell_venue) if v],
                        actor="flash_loan_arb_scanner",
                    )
                    self._stats["rows_emitted"] += 1
                except Exception as exc:  # noqa: BLE001
                    self._stats["last_error"] = f"bus_publish: {exc!r}"

            # ---- 5. Stats roll-up ---------------------------------------
            if outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX):
                self._stats["verifier_confirmed"] += 1
            else:
                self._stats["verifier_denied"] += 1
                if outcome == VerifiedOutcome.DENIED_VENUE_UNREADABLE or \
                        outcome.startswith(
                            VerifiedOutcome.DENIED_VENUE_UNREADABLE + ":"):
                    self._stats["denied_venue_unreadable"] += 1
                elif outcome.startswith(VerifiedOutcome.DENIED_GATE_PREFIX):
                    tail = outcome[len(VerifiedOutcome.DENIED_GATE_PREFIX):]
                    gate_name = tail.split(":", 1)[0]
                    key = {
                        "gate_7": "gate_7_atomic_profit",
                        "gate_8": "gate_8_liquidity_depth",
                        "gate_9": "gate_9_flash_loan_mev",
                    }.get(gate_name)
                    if key:
                        self._stats["gate_rejections"][key] += 1

            # ---- 6. Mark processed --------------------------------------
            try:
                await self._queue.mark_processed(
                    c.candidate_id, outcome,
                    opportunity_id=(opp.opportunity_id if opp else None),
                    observed_at=c.hint_observed_at,
                )
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"queue_mark: {exc!r}"
