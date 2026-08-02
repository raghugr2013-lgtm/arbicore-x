"""ArbiCore X — Phase D D-4.5 Launch Arbitrage scanner orchestrator.

Mirrors ``funding_arbitrage/scanner.py`` and ``cex_arbitrage/scanner.py``
structurally. This is the FOURTH authorised emission call site across the
scanner tree (after ``cex_arbitrage``, ``funding_arbitrage``, and
``dex_arbitrage``).

INV-1 — sources emit ``DiscoveryCandidate`` only; the verifier produces
``CanonicalOpportunity`` via the universal substrate.

INV-2 — EmissionBus is invoked ONLY here (``_tick``), with the
verifier-built ``CanonicalOpportunity``. Sources, verifier, gates,
economics, and evidence engines never emit.

INV-3 — the verifier sets ``source_data_quality`` from the per-leg
``source_id`` (``helius_token_rpc``) via the universal ``derive_provenance``
substrate — never from the aggregator hint source.

Dormancy posture (boot):
- Default ``scanner_state.launch_arb.enabled = False``
- Orchestrator does NOT call ``start()`` unless operator flips state
  (``POST /api/arbicore/scanners/launch_arb/resume``) or sets the
  ``ARBICORE_SCANNER_LAUNCH_ARB=on`` boot env gate.
- If a real ``venue_provider`` has not been injected (e.g.
  ``HELIUS_API_KEY`` not provisioned), the default no-op provider returns
  ``None`` and every candidate ends as ``denied:venue_unreadable`` —
  visibly counted, never emitted. This is the operator-controlled
  cold-start posture for D-4.5.

No execution. Detection-only.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ...data.discovery_queue import DiscoveryQueue
from ...intel.launch.holder_analytics import HolderAnalytics
from ...intel.launch.phase_classifier import PhaseClassifier
from ...intel.launch.smart_money import SmartMoneyDetector
from ...intel.launch.timeline import LaunchTimelineEngine
from ...intelligence.roi_probability import ROIProbabilityEngine
from ...models.discovery import DiscoveryCandidate, VerifiedOutcome
from ...models.enums import OpportunityType
from ..discovery_source import DiscoverySourceRegistry
from ..opportunity_verifier import OpportunityVerifierRegistry
from .economics import LaunchEconomicsAssessor
from .filter import LaunchGate1Filter, LaunchGate6RugRiskFilter
from .sources import build_all_launch_sources
from .verifier import LaunchOpportunityVerifier, LaunchVenueProvider

logger = logging.getLogger("arbicore.scanners.launch_arb")


# ============================================================================
# Default no-op venue provider — operator-controlled cold start
# ============================================================================

async def _noop_venue_provider(
        candidate: DiscoveryCandidate,
        ) -> Optional[Dict[str, Any]]:
    """Operator-controlled cold-start provider. Returns ``None`` for every
    candidate, which the verifier translates to ``denied:venue_unreadable``.

    The orchestrator never silently emits anything against this provider —
    the operator must explicitly wire a real Helius-backed provider via
    ``set_venue_provider()`` before any canonical row can be confirmed.
    """
    return None


# ============================================================================
# LaunchArbitrageScanner
# ============================================================================

class LaunchArbitrageScanner:
    """Orchestrator for ``OpportunityType.LAUNCH_ARBITRAGE``.

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
        entity_scorer=None,
        venue_provider: Optional[LaunchVenueProvider] = None,
        token_universe_loader: Optional[Callable[[], List[str]]] = None,
    ) -> None:
        self._bus = emission_bus
        self._queue = discovery_queue
        self._caps = venue_capability_repo
        self._cfg = config_loader
        self._state = state_loader
        self._confidence_engine = confidence_engine

        # ── Tracked-token universe: by default empty (so HeliusWalletSource
        # graceful-disables). Operator/D-4.6 can wire a real loader later.
        self._token_universe_loader = token_universe_loader or (lambda: [])

        # ── Discovery sources (D-4.1) ───────────────────────────────────
        self._sources = build_all_launch_sources(
            config_loader=config_loader,
            token_universe_loader=self._token_universe_loader,
        )
        self._source_registry = DiscoverySourceRegistry()
        for s in self._sources:
            self._source_registry.register(s)

        # ── D-4.3 evidence engines + D-4.4 verifier composition ────────
        cfg0 = config_loader() or {}
        gate_cfg = cfg0.get("gate_thresholds") or {}
        rug_cfg = cfg0.get("rug_gate") or {}
        roi_cfg = cfg0.get("roi_probability") or {}
        notional = float(cfg0.get("default_notional_usd") or 250.0)

        self._gate_1 = LaunchGate1Filter(
            thresholds=dict(gate_cfg.get("default", {})),
            per_launchpad={k: dict(v) for k, v in gate_cfg.items()
                            if k != "default"},
        )
        self._gate_6 = LaunchGate6RugRiskFilter(dict(rug_cfg))

        self._venue_provider: LaunchVenueProvider = (
            venue_provider or _noop_venue_provider
        )

        self._verifier = LaunchOpportunityVerifier(
            venue_provider=self._venue_provider,
            phase_classifier=PhaseClassifier(),
            timeline_engine=LaunchTimelineEngine(),
            smart_money_detector=SmartMoneyDetector(
                entity_scorer=entity_scorer,
            ),
            holder_analytics=HolderAnalytics(),
            economics_assessor=LaunchEconomicsAssessor(
                roi_engine=ROIProbabilityEngine(
                    min_sample=int(roi_cfg.get("min_sample_size", 6)),
                    winsorize_pct=float(roi_cfg.get("winsor_low_pct", 5.0))
                                    / 100.0,
                ),
                default_notional_usd=notional,
            ),
            gate_1=self._gate_1, gate_6=self._gate_6,
            default_notional_usd=notional,
        )
        self._verifier_registry = OpportunityVerifierRegistry()
        self._verifier_registry.register(self._verifier)

        # ── Orchestrator state ─────────────────────────────────────────
        self._worker_id = f"launch_arb:{uuid.uuid4().hex[:8]}"
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
                "gate_1_launch_composite": 0,
                "gate_6_rug_risk":         0,
            },
            "denied_venue_unreadable": 0,
            "last_run_at":          None,
            "last_error":           None,
        }

    # -- public read-only accessors --------------------------------------

    @property
    def opportunity_type(self) -> OpportunityType:
        return OpportunityType.LAUNCH_ARBITRAGE

    @property
    def scanner_id(self) -> str:
        return "launch_arb"

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
    def venue_provider_is_default(self) -> bool:
        """True when the no-op provider is wired (no live Helius backend)."""
        return self._venue_provider is _noop_venue_provider

    def is_enabled(self) -> bool:
        st = self._state() or {}
        return bool(st.get("enabled", False))

    # -- operator hooks (do NOT change INV-2 contract) -------------------

    def set_venue_provider(self, provider: LaunchVenueProvider) -> None:
        """Operator-controlled wiring of a live venue provider.

        Replacing the provider does NOT enable the scanner; the operator
        must still flip ``scanner_state.launch_arb.enabled`` via the
        ``/resume`` endpoint. Used by D-4.6 / future Helius wiring waves.
        """
        self._venue_provider = provider
        self._verifier.venue_provider = provider

    def set_token_universe_loader(
            self, loader: Callable[[], List[str]]) -> None:
        """Operator-controlled wiring of the tracked-token universe."""
        self._token_universe_loader = loader
        # Re-build HeliusWalletSource with the new loader to keep the
        # registry self-consistent.
        from .sources import HeliusWalletSource
        new_sources: List[Any] = []
        for s in self._sources:
            if isinstance(s, HeliusWalletSource):
                new_sources.append(HeliusWalletSource(
                    config_loader=self._cfg,
                    token_universe_loader=loader,
                ))
            else:
                new_sources.append(s)
        self._sources = new_sources
        self._source_registry = DiscoverySourceRegistry()
        for s in self._sources:
            self._source_registry.register(s)

    # -- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
        logger.info(
            "LaunchArbitrageScanner started: worker=%s venue_provider=%s",
            self._worker_id,
            "default-noop" if self.venue_provider_is_default else "operator-provided",
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
                logger.exception("launch scanner tick failed: %s", exc)
            cfg = self._cfg() or {}
            interval = float(cfg.get("interval_s") or 60.0)
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        """Single discover → claim → verify → emit cycle.

        This method is the ONLY place in the launch subsystem that invokes
        the EmissionBus for LAUNCH_ARBITRAGE (INV-2).
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
            # Route by opportunity_type — LaunchArbitrageScanner only
            # services LAUNCH_ARBITRAGE candidates.
            if c.opportunity_type != OpportunityType.LAUNCH_ARBITRAGE:
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

            # ---- 4. Emit (INV-2 single call site for LAUNCH_ARBITRAGE) ----
            if opp is not None and outcome.startswith(
                    VerifiedOutcome.CONFIRMED_PREFIX):
                try:
                    # ── _TICK_EMIT: the SOLE LAUNCH_ARBITRAGE emit site ──
                    await self._bus.emit(
                        opp,
                        venue_ids=[v for v in
                                    (opp.buy_venue, opp.sell_venue) if v],
                        actor="launch_arb_scanner",
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
                    # Map gate ids to the two launch_arb gate counters
                    if gate_name == "gate_1":
                        self._stats["gate_rejections"][
                            "gate_1_launch_composite"] += 1
                    elif gate_name == "gate_6":
                        self._stats["gate_rejections"][
                            "gate_6_rug_risk"] += 1

            # ---- 6. Mark processed ---------------------------------------
            try:
                await self._queue.mark_processed(
                    c.candidate_id, outcome,
                    opportunity_id=(opp.opportunity_id if opp else None),
                    observed_at=c.hint_observed_at,
                )
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"queue_mark: {exc!r}"
