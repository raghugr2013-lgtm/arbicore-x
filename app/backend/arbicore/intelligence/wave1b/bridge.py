"""MidEvidenceBridge — the single write path from intelligence engines
into MID (Sprint 1B-α).

Each engine has a *native* output object (``RouteStats``, ``ROIProbability``,
``ScoreBreakdown``, ``CapitalSizing``, ``EntityScore``, ``RegimeSnapshot``).
The bridge accepts those native shapes and translates them into a
validated MID row using the corresponding ``MidWriter.write_*`` method
with proper ``MidMetadata``. Every write emits both:

  * the intended MID record (confidence / route / decision / opportunity
    event / outcome — whichever fits the engine), AND
  * a ``mid_opportunity_event`` row with ``event_type`` prefixed
    ``intel.<engine>.<event>`` so operators can replay the intelligence
    stream as a first-class timeline even before scanners are active.

The bridge is **strategy-agnostic**: the metadata block is caller-supplied.
An engine that publishes evidence for a specific opportunity supplies its
own metadata; the bridge only fills sensible defaults for missing keys.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...data.mid.writers import MidWriter, make_meta
from ...data.mid.schemas import MidMetadata

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class BridgeStats:
    """Per-engine and per-domain counters for observability."""
    total_writes: int = 0
    by_engine: Dict[str, int] = field(default_factory=dict)
    by_domain: Dict[str, int] = field(default_factory=dict)
    last_write_at: Optional[str] = None
    last_engine: Optional[str] = None
    last_domain: Optional[str] = None
    last_error: Optional[str] = None

    def record(self, engine: str, domain: str) -> None:
        self.total_writes += 1
        self.by_engine[engine] = self.by_engine.get(engine, 0) + 1
        self.by_domain[domain] = self.by_domain.get(domain, 0) + 1
        self.last_write_at = _now_iso()
        self.last_engine = engine
        self.last_domain = domain

    def record_error(self, msg: str) -> None:
        self.last_error = msg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_writes": self.total_writes,
            "by_engine": dict(self.by_engine),
            "by_domain": dict(self.by_domain),
            "last_write_at": self.last_write_at,
            "last_engine": self.last_engine,
            "last_domain": self.last_domain,
            "last_error": self.last_error,
        }


class MidEvidenceBridge:
    """The single ``intelligence → MID`` adapter.

    Every public method:
      1. Validates the payload minimally (never raises on missing optional
         fields — engines are trusted, but the bridge stamps ``ts`` and
         fills default metadata when absent).
      2. Delegates to the appropriate ``MidWriter.write_*`` method.
      3. Also writes a mirror ``opportunity_event`` row so the entire
         intelligence stream is replayable as a timeline.
      4. Records the emission in :class:`BridgeStats` for the
         ``/api/arbicore/intelligence/status`` endpoint.
    """

    def __init__(self, writer: MidWriter) -> None:
        self._writer = writer
        self.stats = BridgeStats()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_meta(
        *,
        opportunity_type: str = "unknown",
        chain: str = "unknown",
        protocol: Optional[str] = None,
        execution_mode: str = "shadow",
        market_regime: str = "UNKNOWN",
        tags: Optional[List[str]] = None,
    ) -> MidMetadata:
        return make_meta(
            opportunity_type=opportunity_type,
            chain=chain,
            protocol=protocol,
            execution_mode=execution_mode,
            market_regime=market_regime,
            tags=tags,
        )

    async def _mirror_event(
        self,
        *,
        engine: str,
        event_type: str,
        opp_id: str,
        payload: Dict[str, Any],
        meta: MidMetadata,
    ) -> Optional[str]:
        """Best-effort mirror of the emission into ``mid_opportunities``."""
        try:
            return await self._writer.write_opportunity_event(
                opp_id=opp_id,
                event_type=f"intel.{engine}.{event_type}",
                payload=payload,
                meta=meta,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("MidEvidenceBridge mirror event failed: %s", exc)
            self.stats.record_error(f"mirror_event[{engine}]: {exc!r}")
            return None

    # ------------------------------------------------------------------
    # Confidence engine
    # ------------------------------------------------------------------

    async def publish_confidence(
        self,
        *,
        opp_id: str,
        score: float,
        inputs: Optional[Dict[str, Any]] = None,
        meta: Optional[MidMetadata] = None,
    ) -> Optional[str]:
        meta = meta or self._default_meta()
        try:
            mid_id = await self._writer.write_confidence(
                opp_id=opp_id, score=float(score),
                inputs=inputs or {}, meta=meta,
            )
            self.stats.record("confidence", "confidence")
            await self._mirror_event(
                engine="confidence", event_type="score_written",
                opp_id=opp_id,
                payload={"score": float(score), "inputs": inputs or {}},
                meta=meta,
            )
            return mid_id
        except Exception as exc:  # noqa: BLE001
            logger.exception("publish_confidence failed: %s", exc)
            self.stats.record_error(f"confidence: {exc!r}")
            return None

    # ------------------------------------------------------------------
    # ROI probability engine
    # ------------------------------------------------------------------

    async def publish_roi_probability(
        self,
        *,
        opp_id: str,
        roi: Dict[str, Any],
        meta: Optional[MidMetadata] = None,
    ) -> Optional[str]:
        """Persist an ROIProbability estimate.

        ROI has no dedicated MID domain — it flows into ``opportunity_event``
        with ``event_type = intel.roi.probability`` so replay tooling can
        pick it up alongside the confidence stream.
        """
        meta = meta or self._default_meta()
        mid_id = await self._mirror_event(
            engine="roi", event_type="probability",
            opp_id=opp_id, payload=roi, meta=meta,
        )
        if mid_id:
            self.stats.record("roi", "opportunities")
        return mid_id

    # ------------------------------------------------------------------
    # Route ranking engine
    # ------------------------------------------------------------------

    async def publish_route_score(
        self,
        *,
        route_id: str,
        fingerprint_parts: Dict[str, Any],
        score: Dict[str, Any],
        opp_id: Optional[str] = None,
        meta: Optional[MidMetadata] = None,
    ) -> Optional[str]:
        """Persist a ranked route as a ``route_observation`` in MID plus a
        mirror ``opportunity_event`` (if ``opp_id`` supplied)."""
        meta = meta or self._default_meta()
        try:
            mid_id = await self._writer.write_route_observation(
                route_id=route_id,
                fingerprint_parts={
                    **fingerprint_parts,
                    "chain_score": score.get("chain_score"),
                    "meets_threshold": score.get("meets_threshold"),
                },
                meta=meta,
            )
            self.stats.record("route_ranking", "routes")
            if opp_id:
                await self._mirror_event(
                    engine="route_ranking",
                    event_type="scored",
                    opp_id=opp_id,
                    payload={"route_id": route_id, "score": score},
                    meta=meta,
                )
            return mid_id
        except Exception as exc:  # noqa: BLE001
            logger.exception("publish_route_score failed: %s", exc)
            self.stats.record_error(f"route_ranking: {exc!r}")
            return None

    # ------------------------------------------------------------------
    # Economics / capital sizing engine
    # ------------------------------------------------------------------

    async def publish_capital_sizing(
        self,
        *,
        opp_id: str,
        sizing: Dict[str, Any],
        meta: Optional[MidMetadata] = None,
    ) -> Optional[str]:
        """Persist a capital sizing verdict as a MID ``decision``.

        The engine's ``binding_constraint`` becomes the decision gate,
        ``suggested_trade_size_usd`` becomes the reason."""
        meta = meta or self._default_meta()
        try:
            mid_id = await self._writer.write_decision(
                opp_id=opp_id,
                gate="capital_sizing",
                verdict="proposed",
                reason=(
                    f"binding={sizing.get('binding_constraint')} "
                    f"suggested_usd={sizing.get('suggested_trade_size_usd')}"
                ),
                meta=meta,
            )
            self.stats.record("economics", "decisions")
            await self._mirror_event(
                engine="economics",
                event_type="capital_sizing",
                opp_id=opp_id,
                payload=sizing,
                meta=meta,
            )
            return mid_id
        except Exception as exc:  # noqa: BLE001
            logger.exception("publish_capital_sizing failed: %s", exc)
            self.stats.record_error(f"economics: {exc!r}")
            return None

    # ------------------------------------------------------------------
    # Regime detection engine
    # ------------------------------------------------------------------

    async def publish_regime(
        self,
        *,
        dominant_regime: str,
        tags: List[str],
        confidence: float,
        source: str,
        extras: Optional[Dict[str, Any]] = None,
        meta: Optional[MidMetadata] = None,
    ) -> Optional[str]:
        """Persist a regime classification as a ``provider_snapshot`` in
        MID (the closest existing domain) plus a mirror
        ``opportunity_event`` with ``opp_id="__regime__"`` so the regime
        stream is replayable independent of any single opportunity.

        Note: MID Sprint 1A intentionally left ``MARKET_REGIME`` open so
        this engine can back-annotate future rows without a schema
        migration.
        """
        meta = meta or self._default_meta(market_regime=dominant_regime)
        # attach the tags into meta.tags for MID enum audit
        merged_tags = list({*(meta.tags or []), *tags})
        meta = self._default_meta(
            opportunity_type=meta.opportunity_type,
            chain=meta.chain,
            protocol=meta.protocol,
            execution_mode=meta.execution_mode,
            market_regime=dominant_regime,
            tags=merged_tags,
        )
        try:
            mid_id = await self._writer.write_provider_snapshot(
                provider_id=f"regime:{source}",
                available=True,
                observed_cost_bps=None,
                observed_revert_count=None,
                meta=meta,
            )
            self.stats.record("regime", "providers")
            await self._mirror_event(
                engine="regime",
                event_type="classified",
                opp_id="__regime__",
                payload={
                    "dominant_regime": dominant_regime,
                    "tags": tags,
                    "confidence": confidence,
                    "source": source,
                    "extras": extras or {},
                },
                meta=meta,
            )
            return mid_id
        except Exception as exc:  # noqa: BLE001
            logger.exception("publish_regime failed: %s", exc)
            self.stats.record_error(f"regime: {exc!r}")
            return None

    # ------------------------------------------------------------------
    # Entity scoring engine
    # ------------------------------------------------------------------

    async def publish_entity_score(
        self,
        *,
        entity_id: str,
        entity_type: str,
        outcome_score: float,
        succeeded: bool,
        meta: Optional[MidMetadata] = None,
    ) -> Optional[str]:
        """Persist an entity outcome update as an ``opportunity_event``
        with a synthetic entity-scoped opp_id (``ent:<entity_id>``)."""
        meta = meta or self._default_meta()
        mid_id = await self._mirror_event(
            engine="entity_scoring",
            event_type="outcome_recorded",
            opp_id=f"ent:{entity_id}",
            payload={
                "entity_id": entity_id,
                "entity_type": entity_type,
                "outcome_score": outcome_score,
                "succeeded": succeeded,
            },
            meta=meta,
        )
        if mid_id:
            self.stats.record("entity_scoring", "opportunities")
        return mid_id
