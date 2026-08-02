"""ArbiCore X — Phase D D-5.1 Cross-Chain Arbitrage scanner orchestrator.

Mirrors ``launch_arbitrage/scanner.py`` structurally. This is the FIFTH
and FINAL authorised emission call site across the scanner tree (after
``cex_arbitrage``, ``funding_arbitrage``, ``dex_arbitrage`` and
``launch_arbitrage``).

INV-1 — sources emit ``DiscoveryCandidate`` only; the verifier produces
``CanonicalOpportunity`` via the universal substrate.

INV-2 — EmissionBus is invoked ONLY here (``_tick``).

INV-3 — the verifier sets ``source_data_quality`` from the per-leg
``source_id`` (``lifi_quote_real`` or ``stargate_quote_real``) via the
universal ``derive_provenance`` substrate.

Dormancy posture (boot):
- Default ``scanner_state.cross_chain_arb.enabled = False``
- Every per-bridge and per-chain enable flag ships False.
- If a real ``transfer_provider`` has not been injected, the default
  no-op provider returns ``None`` and every candidate ends as
  ``denied:venue_unreadable`` — visibly counted, never emitted.

No execution. Detection-only.
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
from ..discovery_source import DiscoverySourceRegistry
from ..opportunity_verifier import OpportunityVerifierRegistry
from .bridge_intelligence import BridgeRouteCatalog, MevRiskScorer
from .chain_liveness import ChainLivenessRegistry
from .economics import BridgeEconomicsAssessor
from .filter import (
    CrossChainGate7BridgeLiveness, CrossChainGate8ChainLiveness,
    CrossChainGate9CrossChainMev,
)
from .sources import build_all_cross_chain_sources
from .transfer_provider import TransferModelProvider, noop_transfer_provider
from .verifier import CrossChainOpportunityVerifier

logger = logging.getLogger("arbicore.scanners.cross_chain_arb")


class CrossChainArbitrageScanner:
    """Orchestrator for ``OpportunityType.CROSS_CHAIN_ARBITRAGE``.

    Discovery → cooperative queue → claim → verify → (gate) → emit.
    Exactly ONE EmissionBus invocation per tick (line ``_TICK_EMIT``
    inside ``_tick`` below).
    """

    def __init__(
        self,
        *,
        emission_bus,
        discovery_queue: DiscoveryQueue,
        venue_capability_repo,
        config_loader: Callable[[], Dict[str, Any]],
        state_loader: Callable[[], Dict[str, Any]],
        confidence_engine=None,
        transfer_provider: Optional[TransferModelProvider] = None,
        chain_liveness_loader: Optional[Callable[[], Awaitable[Dict[str, Any]]]] = None,
    ) -> None:
        self._bus = emission_bus
        self._queue = discovery_queue
        self._caps = venue_capability_repo
        self._cfg = config_loader
        self._state = state_loader
        self._confidence_engine = confidence_engine

        # ── Discovery sources (D-5.1) ────────────────────────────────────
        self._sources = build_all_cross_chain_sources(
            config_loader=config_loader)
        self._source_registry = DiscoverySourceRegistry()
        for s in self._sources:
            self._source_registry.register(s)

        # ── Bridge / chain intelligence ─────────────────────────────────
        self._chain_liveness = ChainLivenessRegistry(
            config_loader=config_loader,
            liveness_loader=chain_liveness_loader,
        )
        self._routes = BridgeRouteCatalog(config_loader=config_loader)
        self._mev = MevRiskScorer()

        # ── Verifier composition ────────────────────────────────────────
        cfg0 = config_loader() or {}
        gate_cfg = cfg0.get("gate_thresholds") or {}
        roi_cfg = cfg0.get("roi_probability") or {}
        notional = float(cfg0.get("default_notional_usd") or 1000.0)

        self._gate_7 = CrossChainGate7BridgeLiveness(
            thresholds=dict(gate_cfg.get("default", {})),
            per_bridge={k: dict(v) for k, v in gate_cfg.items()
                          if k != "default"},
        )
        self._gate_8 = CrossChainGate8ChainLiveness(
            thresholds=dict(gate_cfg.get("default", {})),
        )
        self._gate_9 = CrossChainGate9CrossChainMev(
            thresholds=dict(gate_cfg.get("default", {})),
        )

        # ── Transfer providers (D-5.2 multi-bridge dispatch) ────────────
        # Per-bridge registry. The verifier sees a single TransferModelProvider
        # callable; internally it dispatches by ``candidate.hint_metric.bridge``.
        # Empty registry → default no-op → every candidate ends
        # denied:venue_unreadable (D-5.1 boot posture preserved).
        self._providers_by_bridge: Dict[str, TransferModelProvider] = {}
        if transfer_provider is not None:
            self._providers_by_bridge["__default__"] = transfer_provider

        async def _dispatcher(candidate):  # async closure
            hm = candidate.hint_metric or {}
            bridge = (hm.get("bridge") or "").lower()
            prov = self._providers_by_bridge.get(bridge) or \
                self._providers_by_bridge.get("__default__")
            if prov is None:
                return None
            return await prov(candidate)
        self._transfer_dispatch = _dispatcher

        self._verifier = CrossChainOpportunityVerifier(
            transfer_provider=self._transfer_dispatch,
            economics_assessor=BridgeEconomicsAssessor(
                roi_engine=ROIProbabilityEngine(
                    min_sample=int(roi_cfg.get("min_sample_size", 8)),
                    winsorize_pct=float(roi_cfg.get("winsor_low_pct", 5.0))
                                    / 100.0,
                ),
                default_notional_usd=notional,
            ),
            chain_liveness=self._chain_liveness,
            route_catalog=self._routes,
            mev_scorer=self._mev,
            gate_7=self._gate_7,
            gate_8=self._gate_8,
            gate_9=self._gate_9,
            default_notional_usd=notional,
        )
        self._verifier_registry = OpportunityVerifierRegistry()
        self._verifier_registry.register(self._verifier)

        # ── Orchestrator state ────────────────────────────────────────────
        self._worker_id = f"cross_chain_arb:{uuid.uuid4().hex[:8]}"
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._stats: Dict[str, Any] = {
            "iterations":           0,
            "rows_emitted":         0,
            "verifier_confirmed":   0,
            "verifier_denied":      0,
            "verifier_errors":      0,
            "candidates_claimed":   0,
            "gate_rejections": {
                "gate_7_bridge_liveness": 0,
                "gate_8_chain_liveness":  0,
                "gate_9_cross_chain_mev": 0,
            },
            "denied_venue_unreadable": 0,
            "last_run_at":          None,
            "last_error":           None,
        }

    # -- public read-only accessors --------------------------------------

    @property
    def opportunity_type(self) -> OpportunityType:
        return OpportunityType.CROSS_CHAIN_ARBITRAGE

    @property
    def scanner_id(self) -> str:
        return "cross_chain_arb"

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
    def transfer_provider_is_default(self) -> bool:
        """True when no per-bridge provider has been operator-attached."""
        return not self._providers_by_bridge

    def transfer_providers(self) -> Dict[str, str]:
        """Read-only view of attached providers, keyed by bridge."""
        return {b: type(p).__name__
                for b, p in self._providers_by_bridge.items()}

    @property
    def chain_liveness(self) -> ChainLivenessRegistry:
        return self._chain_liveness

    @property
    def route_catalog(self) -> BridgeRouteCatalog:
        return self._routes

    @property
    def config_loader(self) -> Callable[[], Dict[str, Any]]:
        """D-5.2 — Expose the config loader for operator-side loaders
        (e.g. RpcChainLivenessLoader uses this to read per-chain
        scanner_config.chains.<id>.rpc_env_var)."""
        return self._cfg

    def is_enabled(self) -> bool:
        st = self._state() or {}
        return bool(st.get("enabled", False))

    # -- operator hooks (do NOT change INV-2 contract) -------------------

    def set_transfer_provider(self, provider: TransferModelProvider) -> None:
        """Operator-controlled wiring of a default transfer provider.

        Back-compat with D-5.1: when called with a single callable, the
        provider is registered under ``__default__`` and handles every
        bridge that has no dedicated provider attached.
        """
        self._providers_by_bridge["__default__"] = provider

    def register_transfer_provider(
        self, bridge: str, provider: TransferModelProvider) -> None:
        """D-5.2 — Per-bridge provider attach. Verifier sees a single
        callable; the scanner dispatches by ``candidate.hint_metric.bridge``.
        """
        self._providers_by_bridge[(bridge or "").lower()] = provider

    def set_chain_liveness_loader(
        self,
        loader: Callable[[], Awaitable[Dict[str, Any]]],
    ) -> None:
        """Operator hook for live chain-liveness snapshots."""
        self._chain_liveness.set_loader(loader)

    # -- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        logger.info(
            "CrossChainArbitrageScanner started: worker=%s transfer_providers=%s",
            self._worker_id,
            self.transfer_providers() or "default-noop",
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
                logger.exception("cross_chain scanner tick failed: %s", exc)
            cfg = self._cfg() or {}
            interval = float(cfg.get("interval_s") or 45.0)
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        """Single discover → claim → verify → emit cycle.

        This method is the ONLY place in the cross-chain subsystem that
        invokes the EmissionBus for CROSS_CHAIN_ARBITRAGE (INV-2).
        """
        if not self.is_enabled():
            return
        self._stats["iterations"] += 1
        self._stats["last_run_at"] = time.time()
        # Refresh chain-liveness + route-catalog overrides each tick.
        try:
            await self._chain_liveness.refresh()
        except Exception as exc:  # noqa: BLE001
            self._stats["last_error"] = f"liveness_refresh: {exc!r}"
        try:
            self._routes.refresh_overrides()
        except Exception as exc:  # noqa: BLE001
            self._stats["last_error"] = f"routes_refresh: {exc!r}"

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
            if c.opportunity_type != OpportunityType.CROSS_CHAIN_ARBITRAGE:
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

            # ---- 4. Emit (INV-2 single call site for CROSS_CHAIN_ARBITRAGE) -
            if opp is not None and outcome.startswith(
                    VerifiedOutcome.CONFIRMED_PREFIX):
                try:
                    # ── _TICK_EMIT: SOLE CROSS_CHAIN_ARBITRAGE emit site ──
                    await self._bus.emit(
                        opp,
                        venue_ids=[v for v in
                                    (opp.buy_venue, opp.sell_venue) if v],
                        actor="cross_chain_arb_scanner",
                    )
                    self._stats["rows_emitted"] += 1
                except Exception as exc:  # noqa: BLE001
                    self._stats["last_error"] = f"bus_publish: {exc!r}"

            # ---- 5. Stats roll-up ----------------------------------------
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
                        "gate_7": "gate_7_bridge_liveness",
                        "gate_8": "gate_8_chain_liveness",
                        "gate_9": "gate_9_cross_chain_mev",
                    }.get(gate_name)
                    if key:
                        self._stats["gate_rejections"][key] += 1

            # ---- 6. Mark processed ---------------------------------------
            try:
                await self._queue.mark_processed(
                    c.candidate_id, outcome,
                    opportunity_id=(opp.opportunity_id if opp else None),
                    observed_at=c.hint_observed_at,
                )
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"queue_mark: {exc!r}"
