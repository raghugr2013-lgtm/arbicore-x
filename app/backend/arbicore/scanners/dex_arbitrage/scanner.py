"""ArbiCore X — Phase D D-3.4 DEX Arbitrage scanner orchestrator.

Mirrors `funding_arbitrage/scanner.py` structurally. **The SINGLE place in
the DEX subsystem that drives the EmissionBus emit method** — i.e., the
third emission call site across the entire scanner tree (the first being
`cex_arbitrage/scanner.py`, the second `funding_arbitrage/scanner.py`).

INV-1: only DiscoveryCandidate produced by sources → claimed → verified.
INV-2: this orchestrator owns the only DEX emit call site.
INV-3: provenance is set by the verifier from per-leg quoter SOURCE_REGISTRY
       — never from any aggregator HINT candidate.

D-3.4 ships the orchestrator + factory + composition wiring + routes,
but keeps both scanner state AND every discovery source DISABLED at boot.
Operator-graduated enablement happens in D-3.6 shadow rollout.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from ...data.discovery_queue import DiscoveryQueue
from ...models.discovery import VerifiedOutcome
from ..discovery_source import DiscoverySource, DiscoverySourceRegistry
from ..opportunity_verifier import OpportunityVerifierRegistry
from ..discovery.dexscreener_hint import DexScreenerHintSource
from .economics import DEXEconomicsAssessor
from .quote_cache import DEXQuoteCache
from .quoter import BaseDEXQuoter, build_default_quoters
from .sources import build_all_dex_sources
from .verifier import DEXQuoteVerifier

logger = logging.getLogger("arbicore.scanners.dex_arb")


class DEXArbitrageScanner:
    """Single INV-2 emit caller for OpportunityType.DEX_ARBITRAGE."""

    def __init__(self, *,
                 emission_bus,
                 discovery_queue: DiscoveryQueue,
                 venue_capability_repo,
                 config_loader: Callable[[], Dict[str, Any]],
                 state_loader: Callable[[], Dict[str, Any]],
                 quoters: Optional[List[BaseDEXQuoter]] = None,
                 confidence_engine=None,
                 ) -> None:
        self._bus   = emission_bus
        self._queue = discovery_queue
        self._caps  = venue_capability_repo
        self._cfg   = config_loader
        self._state = state_loader

        # Discovery sources — venue tier + DexScreener HINT (INV-3 telemetry only)
        self._quote_cache = DEXQuoteCache()
        venue_sources = build_all_dex_sources(
            quote_cache=self._quote_cache, config_loader=config_loader,
        )
        hint_source = DexScreenerHintSource(config_loader=config_loader)
        self._sources: List[DiscoverySource] = [*venue_sources, hint_source]
        self._source_registry = DiscoverySourceRegistry()
        for s in self._sources:
            self._source_registry.register(s)

        # Quoters + economics + verifier
        self._quoters = quoters or build_default_quoters()
        self._econ = DEXEconomicsAssessor(config_loader=config_loader)
        self._verifier = DEXQuoteVerifier(
            quoters=self._quoters,
            venue_caps=venue_capability_repo,
            confidence_engine=confidence_engine,
            config_loader=config_loader,
            economics_assessor=self._econ,
        )
        self._verifier_registry = OpportunityVerifierRegistry()
        self._verifier_registry.register(self._verifier)

        self._worker_id = f"dex_arb:{uuid.uuid4().hex[:8]}"
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
                "economics": 0, "liquidity": 0,
                "venue_capability": 0, "confidence": 0, "provenance": 0,
            },
            "last_run_at":        None,
            "last_error":         None,
        }

    # ----- accessors -------------------------------------------------------

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
    def quote_cache(self) -> DEXQuoteCache:
        return self._quote_cache

    def is_enabled(self) -> bool:
        st = self._state() or {}
        return bool(st.get("enabled", False))

    # ----- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("DEXArbitrageScanner started: worker=%s", self._worker_id)

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
                logger.exception("dex scanner tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass

    # ----- main loop -------------------------------------------------------

    async def _tick(self) -> None:
        if not self.is_enabled():
            return
        self._stats["iterations"] += 1
        self._stats["last_run_at"] = time.time()

        # 1. Discover candidates from all enabled sources
        all_candidates = []
        for source in self._sources:
            try:
                cands = await source.discover()
                all_candidates.extend(cands)
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"discover[{source.source_id}]: {exc!r}"
        if all_candidates:
            await self._queue.upsert_many(all_candidates)

        # 2. Claim a batch from the universal queue
        batch = await self._queue.claim_batch(self._worker_id, batch_size=32)
        self._stats["candidates_claimed"] += len(batch)

        # 3. Verify + emit one row at a time
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
                    # ─── The SINGLE call site for DEX emission (INV-2) ───
                    await self._bus.emit(
                        opp, venue_ids=[opp.buy_venue, opp.sell_venue],
                        actor="dex_arb_scanner",
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


__all__ = ["DEXArbitrageScanner"]
