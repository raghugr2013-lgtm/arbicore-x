"""ArbiCore X — Phase D D-2.0 Funding Arbitrage scanner orchestrator.

Mirrors `cex_arbitrage/scanner.py` structurally. The SINGLE place in
the funding subsystem that calls the EmissionBus emit method — i.e., the
second emission call site across the entire scanner tree (the first
being `cex_arbitrage/scanner.py:165`).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, Optional

from ...data.discovery_queue import DiscoveryQueue
from ...models.discovery import VerifiedOutcome
from ..discovery_source import DiscoverySourceRegistry
from ..opportunity_verifier import OpportunityVerifierRegistry
from .economics import FundingEconomicsAssessor
from .opportunity_verifier import FundingOpportunityVerifier
from .sources import build_all_funding_sources
from .verifier import FundingDifferentialVerifier

logger = logging.getLogger("arbicore.scanners.funding_arb")


class FundingArbitrageScanner:
    def __init__(self, *,
                 emission_bus,
                 discovery_queue: DiscoveryQueue,
                 venue_capability_repo,
                 config_loader: Callable[[], Dict[str, Any]],
                 state_loader: Callable[[], Dict[str, Any]],
                 confidence_engine=None,
                 depth_fetcher=None,
                 ) -> None:
        self._bus   = emission_bus
        self._queue = discovery_queue
        self._caps  = venue_capability_repo
        self._cfg   = config_loader
        self._state = state_loader
        self._sources = build_all_funding_sources(config_loader=config_loader)
        self._source_registry = DiscoverySourceRegistry()
        for s in self._sources:
            self._source_registry.register(s)
        # Verifier composition — math + economics + universal gates.
        self._diff_engine = FundingDifferentialVerifier(
            sources=self._sources, config_loader=config_loader)
        self._econ = FundingEconomicsAssessor(config_loader=config_loader)
        self._verifier = FundingOpportunityVerifier(
            differential_engine=self._diff_engine,
            economics_assessor=self._econ,
            venue_capability_repo=venue_capability_repo,
            config_loader=config_loader,
            confidence_engine=confidence_engine,
            depth_fetcher=depth_fetcher,
        )
        self._verifier_registry = OpportunityVerifierRegistry()
        self._verifier_registry.register(self._verifier)
        self._worker_id = f"funding_arb:{uuid.uuid4().hex[:8]}"
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._stats: Dict[str, Any] = {
            "iterations":         0,
            "rows_emitted":       0,
            "verifier_confirmed": 0,
            "verifier_denied":    0,
            "verifier_errors":    0,
            "candidates_claimed": 0,
            "gate_rejections":    {
                "funding_diff": 0, "economics": 0,
                "liquidity": 0, "venue_capability": 0,
                "confidence": 0, "provenance": 0,
            },
            "last_run_at":        None,
            "last_error":         None,
        }

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    @property
    def source_registry(self) -> DiscoverySourceRegistry:
        return self._source_registry

    @property
    def verifier_registry(self) -> OpportunityVerifierRegistry:
        return self._verifier_registry

    def is_enabled(self) -> bool:
        st = self._state() or {}
        return bool(st.get("enabled", False))

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("FundingArbitrageScanner started: worker=%s", self._worker_id)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        for s in self._sources:
            await s.close()

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"tick: {exc!r}"
                logger.exception("funding scanner tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        if not self.is_enabled():
            return
        self._stats["iterations"] += 1
        self._stats["last_run_at"] = time.time()

        all_candidates = []
        for source in self._sources:
            try:
                cands = await source.discover()
                all_candidates.extend(cands)
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"discover[{source.source_id}]: {exc!r}"
        if all_candidates:
            await self._queue.upsert_many(all_candidates)

        batch = await self._queue.claim_batch(self._worker_id, batch_size=32)
        self._stats["candidates_claimed"] += len(batch)
        for c in batch:
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
            if opp is not None and outcome.startswith("confirmed_canonical:"):
                try:
                    # ── The SINGLE call site for funding emission (INV-2) ──
                    await self._bus.emit(
                        opp, venue_ids=[opp.buy_venue, opp.sell_venue],
                        actor="funding_arb_scanner",
                    )
                    self._stats["rows_emitted"] += 1
                except Exception as exc:  # noqa: BLE001
                    self._stats["last_error"] = f"bus_publish: {exc!r}"
            if outcome.startswith("confirmed_canonical:"):
                self._stats["verifier_confirmed"] += 1
            else:
                self._stats["verifier_denied"] += 1
                if outcome.startswith(VerifiedOutcome.DENIED_GATE_PREFIX):
                    tail = outcome[len(VerifiedOutcome.DENIED_GATE_PREFIX):]
                    gate_name = tail.split(":", 1)[0]
                    if gate_name in self._stats["gate_rejections"]:
                        self._stats["gate_rejections"][gate_name] += 1
            await self._queue.mark_processed(
                c.candidate_id, outcome,
                opportunity_id=(opp.opportunity_id if opp else None),
                observed_at=c.hint_observed_at,
            )
