"""MID writer façade — the single write path for the platform.

Every producer in the codebase calls into ``MidWriter``.  No direct-to-Mongo
writes outside this module (per design invariant §6.5).

Every write returns the ``mid_id`` of the persisted row so the caller can
reference it later without re-querying.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .enums import (
    EnumRegistry, get_registry,
    STRATEGY_TYPE, OPPORTUNITY_TYPE, CAPITAL_SOURCE,
    CHAIN, PROTOCOL, EXECUTION_MODE, MARKET_REGIME,
)
from .schemas import (
    MidMetadata, ReplayContext, DOMAINS, MID_COLLECTION_MAP,
    MarketStateRecord, QuoteRecord, LiquidityRecord, GasRecord,
    ProviderRecord, RouteObservationRecord, OpportunityEventRecord,
    ConfidenceRecord, DecisionRecord, OutcomeRecord, ReplayRecord,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_mid_id() -> str:
    return str(uuid.uuid4())


def route_id_for(chain: str, family: str, in_token: str, out_token: str,
                 dex_path: List[str]) -> str:
    """Compute the stable canonical route_id fingerprint.

    Same route across weeks/months always resolves to the same id.
    """
    dex_path_hash = hashlib.sha1("|".join(dex_path).encode("utf-8")).hexdigest()[:12]
    return f"{chain}:{family}:{in_token}->{out_token}:{dex_path_hash}"


def market_snapshot_id_for(chain: str, dex: str, pair: str, ts_bucket: str) -> str:
    """Stable canonical id for a market moment.

    Sibling rows describing the same market moment across domains share this
    id.  ``ts_bucket`` should be a coarse (e.g. 30s-truncated) timestamp so
    writes near the same instant coalesce.
    """
    return f"ms:{chain}:{dex}:{pair}:{ts_bucket}"


def event_id_for(opp_id: str, event_ordinal: int) -> str:
    return f"{opp_id}:{event_ordinal:04d}"


def make_meta(*,
              strategy_type: str = "flash_loan_arbitrage",
              opportunity_type: str = "unknown",
              capital_source: Optional[str] = None,
              chain: str = "unknown",
              protocol: Optional[str] = None,
              execution_mode: str = "shadow",
              market_regime: str = "UNKNOWN",
              tags: Optional[List[str]] = None) -> MidMetadata:
    return MidMetadata(
        strategy_type=strategy_type,
        opportunity_type=opportunity_type,
        capital_source=capital_source,
        chain=chain,
        protocol=protocol,
        execution_mode=execution_mode,
        market_regime=market_regime,
        tags=list(tags) if tags else [],
    )


class MidWriter:
    """Async façade over the MID collections.

    Constructed once per app startup with the Motor db handle. Producers
    call the appropriate ``write_*`` method; every method returns the row's
    ``mid_id``.
    """

    def __init__(self, db: Any, *, registry: Optional[EnumRegistry] = None) -> None:
        self._db = db
        self._registry = registry or get_registry()

    # ---- enum validation --------------------------------------------------

    async def _audit_enum(self, name: str, value: Optional[str]) -> None:
        if value is None:
            return
        if self._registry.contains(name, value):
            return
        try:
            await self._db["mid_enum_warnings"].insert_one({
                "ts": _now_iso(),
                "enum": name,
                "value": value,
                "closed": self._registry.is_closed(name),
            })
            logger.warning("MID enum warning: %s = %r (unknown)", name, value)
        except Exception:
            logger.exception("failed to audit MID enum warning")

    async def _validate_meta(self, meta: MidMetadata) -> None:
        await self._audit_enum(STRATEGY_TYPE, meta.strategy_type)
        await self._audit_enum(OPPORTUNITY_TYPE, meta.opportunity_type)
        await self._audit_enum(CAPITAL_SOURCE, meta.capital_source)
        await self._audit_enum(CHAIN, meta.chain)
        await self._audit_enum(PROTOCOL, meta.protocol)
        await self._audit_enum(EXECUTION_MODE, meta.execution_mode)
        await self._audit_enum(MARKET_REGIME, meta.market_regime)

    async def _insert(self, domain: str, doc: Dict[str, Any]) -> str:
        coll = self._db[MID_COLLECTION_MAP[domain]]
        await coll.insert_one(doc)
        return doc["mid_id"]

    # ---- write_market_state -----------------------------------------------

    async def write_market_state(self, *, chain: str, dex: str, pair: str,
                                  mid_price: float,
                                  meta: Optional[MidMetadata] = None,
                                  replay_context: Optional[ReplayContext] = None,
                                  depth_bid: Optional[float] = None,
                                  depth_ask: Optional[float] = None,
                                  spread_bps: Optional[float] = None,
                                  imbalance: Optional[float] = None,
                                  ts: Optional[str] = None,
                                  market_snapshot_id: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta(chain=chain)
        await self._validate_meta(meta)
        ms_id = market_snapshot_id or market_snapshot_id_for(chain, dex, pair, ts[:19])
        rec = MarketStateRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            market_snapshot_id=ms_id, dex=dex, pair=pair, mid_price=mid_price,
            depth_bid=depth_bid, depth_ask=depth_ask, spread_bps=spread_bps, imbalance=imbalance,
        )
        return await self._insert("market_state", rec.to_doc())

    # ---- write_quote ------------------------------------------------------

    async def write_quote(self, *, route_id: str, dex: str,
                          hops: List[Dict[str, Any]],
                          meta: Optional[MidMetadata] = None,
                          replay_context: Optional[ReplayContext] = None,
                          quote_out: Optional[float] = None,
                          quote_wei: Optional[str] = None,
                          fallback_reason: Optional[str] = None,
                          ts: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        rec = QuoteRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            route_id=route_id, dex=dex, hops=hops, quote_out=quote_out,
            quote_wei=quote_wei, fallback_reason=fallback_reason,
        )
        return await self._insert("quotes", rec.to_doc())

    # ---- write_liquidity_snapshot ----------------------------------------

    async def write_liquidity_snapshot(self, *, dex: str, pool: str,
                                        reserves: Dict[str, Any],
                                        meta: Optional[MidMetadata] = None,
                                        replay_context: Optional[ReplayContext] = None,
                                        tick_liquidity: Optional[Dict[str, Any]] = None,
                                        ts: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        rec = LiquidityRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            dex=dex, pool=pool, reserves=reserves, tick_liquidity=tick_liquidity,
        )
        return await self._insert("liquidity", rec.to_doc())

    # ---- write_gas_snapshot ----------------------------------------------

    async def write_gas_snapshot(self, *,
                                  meta: Optional[MidMetadata] = None,
                                  replay_context: Optional[ReplayContext] = None,
                                  gas_price_wei: Optional[str] = None,
                                  priority_fee_wei: Optional[str] = None,
                                  base_fee_wei: Optional[str] = None,
                                  ts: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        rec = GasRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            gas_price_wei=gas_price_wei, priority_fee_wei=priority_fee_wei,
            base_fee_wei=base_fee_wei,
        )
        return await self._insert("gas", rec.to_doc())

    # ---- write_provider_snapshot -----------------------------------------

    async def write_provider_snapshot(self, *, provider_id: str,
                                       meta: Optional[MidMetadata] = None,
                                       replay_context: Optional[ReplayContext] = None,
                                       available: bool = True,
                                       observed_cost_bps: Optional[float] = None,
                                       observed_revert_count: int = 0,
                                       ts: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        rec = ProviderRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            provider_id=provider_id, available=available,
            observed_cost_bps=observed_cost_bps, observed_revert_count=observed_revert_count,
        )
        return await self._insert("providers", rec.to_doc())

    # ---- write_route_observation -----------------------------------------

    async def write_route_observation(self, *, route_id: str,
                                       fingerprint_parts: Dict[str, Any],
                                       meta: Optional[MidMetadata] = None,
                                       replay_context: Optional[ReplayContext] = None,
                                       ts: Optional[str] = None) -> str:
        """UPSERT one doc per route_id — update first_seen once, bump last_seen + sample_count."""
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        coll = self._db[MID_COLLECTION_MAP["routes"]]

        # find first, decide whether to insert with new mid_id or increment
        existing = await coll.find_one({"route_id": route_id})
        if existing:
            await coll.update_one(
                {"route_id": route_id},
                {
                    "$set": {
                        "last_seen": ts,
                        "meta": meta.to_doc(),
                        "replay_context": (replay_context or ReplayContext()).to_doc(),
                    },
                    "$inc": {"sample_count": 1},
                },
            )
            return existing["mid_id"]

        rec = RouteObservationRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            route_id=route_id, fingerprint_parts=fingerprint_parts,
            first_seen=ts, last_seen=ts, sample_count=1,
        )
        try:
            await coll.insert_one(rec.to_doc())
            return rec.mid_id
        except Exception:
            # race: another writer inserted between our find_one and insert.
            # do the upsert-increment path.
            after_race = await coll.find_one_and_update(
                {"route_id": route_id},
                {"$set": {"last_seen": ts}, "$inc": {"sample_count": 1}},
            )
            return (after_race or {}).get("mid_id", rec.mid_id)

    # ---- write_opportunity_event -----------------------------------------

    async def write_opportunity_event(self, *, opp_id: str, event_type: str,
                                       payload: Optional[Dict[str, Any]] = None,
                                       meta: Optional[MidMetadata] = None,
                                       replay_context: Optional[ReplayContext] = None,
                                       ts: Optional[str] = None,
                                       event_ordinal: Optional[int] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)

        # compute event_ordinal if not provided
        if event_ordinal is None:
            coll = self._db[MID_COLLECTION_MAP["opportunities"]]
            latest = await coll.find_one(
                {"opp_id": opp_id},
                sort=[("event_ordinal", -1)],
            )
            event_ordinal = ((latest or {}).get("event_ordinal", -1)) + 1

        rec = OpportunityEventRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            opp_id=opp_id, event_id=event_id_for(opp_id, event_ordinal),
            event_ordinal=event_ordinal, event_type=event_type,
            payload=payload or {},
        )
        return await self._insert("opportunities", rec.to_doc())

    # ---- write_confidence ------------------------------------------------

    async def write_confidence(self, *, opp_id: str, score: float,
                                inputs: Optional[Dict[str, Any]] = None,
                                meta: Optional[MidMetadata] = None,
                                replay_context: Optional[ReplayContext] = None,
                                ts: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        rec = ConfidenceRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            opp_id=opp_id, score=score, inputs=inputs or {},
        )
        return await self._insert("confidence", rec.to_doc())

    # ---- write_decision ---------------------------------------------------

    async def write_decision(self, *, opp_id: str, gate: str, verdict: str,
                              reason: Optional[str] = None,
                              meta: Optional[MidMetadata] = None,
                              replay_context: Optional[ReplayContext] = None,
                              ts: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        rec = DecisionRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            opp_id=opp_id, gate=gate, verdict=verdict, reason=reason,
        )
        return await self._insert("decisions", rec.to_doc())

    # ---- write_outcome ----------------------------------------------------

    async def write_outcome(self, *, opp_id: str, terminal: str,
                             pnl_usd: Optional[float] = None,
                             gas_actual_wei: Optional[str] = None,
                             revert_reason: Optional[str] = None,
                             meta: Optional[MidMetadata] = None,
                             replay_context: Optional[ReplayContext] = None,
                             ts: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        rec = OutcomeRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            opp_id=opp_id, terminal=terminal, pnl_usd=pnl_usd,
            gas_actual_wei=gas_actual_wei, revert_reason=revert_reason,
        )
        return await self._insert("outcomes", rec.to_doc())

    # ---- write_replay -----------------------------------------------------

    async def write_replay(self, *, opp_id: str, variant_id: str,
                            counter_factual_outcome: Dict[str, Any],
                            meta: Optional[MidMetadata] = None,
                            replay_context: Optional[ReplayContext] = None,
                            ts: Optional[str] = None) -> str:
        ts = ts or _now_iso()
        meta = meta or make_meta()
        await self._validate_meta(meta)
        rec = ReplayRecord(
            mid_id=new_mid_id(), ts=ts, meta=meta, replay_context=replay_context,
            opp_id=opp_id, variant_id=variant_id,
            counter_factual_outcome=counter_factual_outcome,
        )
        return await self._insert("replay", rec.to_doc())
