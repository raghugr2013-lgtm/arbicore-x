"""MID typed schemas — one dataclass per domain.

Every record carries:
  * stable canonical ``mid_id`` (UUID4)
  * ISO-8601 UTC ``ts`` (host clock)
  * ``meta`` — strategy-agnostic metadata block (see docs §P1-α invariant 6)
  * ``replay_context`` — replay-readiness block (see docs §P1-α invariant 7)
  * domain-specific payload fields

All dataclasses are frozen at write time and serialised via ``to_doc()`` — the
Mongo document shape is stable and never depends on Python attribute order.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Shared metadata + replay context blocks
# ---------------------------------------------------------------------------


@dataclass
class MidMetadata:
    """Strategy-agnostic metadata block — attached to every MID row.

    v2.0.1 populates only flash-loan-family values; the schema is not
    narrowed. Future strategy families (CEX-DEX, funding, treasury,
    liquidation, institutional credit, cross-chain) populate the same
    block with different values — zero schema migration.
    """

    strategy_type: str = "flash_loan_arbitrage"
    opportunity_type: str = "unknown"
    capital_source: Optional[str] = None
    chain: str = "unknown"
    protocol: Optional[str] = None
    execution_mode: str = "shadow"
    market_regime: str = "UNKNOWN"  # regime engine (dormant) back-annotates
    tags: List[str] = field(default_factory=list)

    def to_doc(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayContext:
    """Replay-readiness block — attached to every MID row where applicable.

    Sufficient to reconstruct the market moment later without duplicating
    payload. All fields optional — writers populate what they know.
    Cross-domain correlation uses these snapshot IDs.
    """

    block_number: Optional[int] = None
    block_timestamp: Optional[str] = None  # ISO-8601 UTC (chain clock)
    quote_snapshot_id: Optional[str] = None
    liquidity_snapshot_id: Optional[str] = None
    gas_snapshot_id: Optional[str] = None
    route_snapshot_id: Optional[str] = None
    decision_snapshot_id: Optional[str] = None
    market_snapshot_id: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Per-domain records
# ---------------------------------------------------------------------------


def _base_doc(mid_id: str, ts: str, meta: MidMetadata,
              replay_context: Optional[ReplayContext]) -> Dict[str, Any]:
    return {
        "mid_id": mid_id,
        "ts": ts,
        "meta": meta.to_doc(),
        "replay_context": (replay_context or ReplayContext()).to_doc(),
    }


@dataclass
class MarketStateRecord:
    """``mid_market_state`` — mid / depth / spread / imbalance per market moment."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    # canonical id shared with sibling rows describing the same market moment
    market_snapshot_id: str
    # domain payload
    dex: str
    pair: str
    mid_price: float
    depth_bid: Optional[float] = None
    depth_ask: Optional[float] = None
    spread_bps: Optional[float] = None
    imbalance: Optional[float] = None

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "market_snapshot_id": self.market_snapshot_id,
            "dex": self.dex,
            "pair": self.pair,
            "mid_price": self.mid_price,
            "depth_bid": self.depth_bid,
            "depth_ask": self.depth_ask,
            "spread_bps": self.spread_bps,
            "imbalance": self.imbalance,
        })
        return d


@dataclass
class QuoteRecord:
    """``mid_quotes`` — every route quote produced by discovery / planner."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    route_id: str
    dex: str
    hops: List[Dict[str, Any]]
    quote_out: Optional[float] = None
    quote_wei: Optional[str] = None  # bigint as string
    fallback_reason: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "route_id": self.route_id,
            "dex": self.dex,
            "hops": self.hops,
            "quote_out": self.quote_out,
            "quote_wei": self.quote_wei,
            "fallback_reason": self.fallback_reason,
        })
        return d


@dataclass
class LiquidityRecord:
    """``mid_liquidity`` — pool depth snapshots."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    dex: str
    pool: str
    reserves: Dict[str, Any]  # per-token reserves
    tick_liquidity: Optional[Dict[str, Any]] = None  # concentrated-liquidity DEXes only

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "dex": self.dex,
            "pool": self.pool,
            "reserves": self.reserves,
            "tick_liquidity": self.tick_liquidity,
        })
        return d


@dataclass
class GasRecord:
    """``mid_gas`` — gas price / priority fee / base fee snapshots."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    gas_price_wei: Optional[str] = None  # bigint as string
    priority_fee_wei: Optional[str] = None
    base_fee_wei: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "gas_price_wei": self.gas_price_wei,
            "priority_fee_wei": self.priority_fee_wei,
            "base_fee_wei": self.base_fee_wei,
        })
        return d


@dataclass
class ProviderRecord:
    """``mid_providers`` — per-capital-source availability / cost / revert snapshots."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    provider_id: str  # canonical id: `{provider_family}:{chain}`
    available: bool = True
    observed_cost_bps: Optional[float] = None  # for flash-loan: premium; for CEX: fees
    observed_revert_count: int = 0

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "provider_id": self.provider_id,
            "available": self.available,
            "observed_cost_bps": self.observed_cost_bps,
            "observed_revert_count": self.observed_revert_count,
        })
        return d


@dataclass
class RouteObservationRecord:
    """``mid_routes`` — per-route-fingerprint lifetime observation.

    UPSERT semantics: one doc per unique ``route_id``, updated in-place on
    every discovery observation.  The write path uses this record type but
    the underlying Mongo op is ``update_one($set + $inc, upsert=True)``.
    """

    mid_id: str  # UUID assigned on first insert
    ts: str  # first-observation ISO
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    route_id: str
    fingerprint_parts: Dict[str, Any]  # {chain, family, in_token, out_token, dex_path}
    first_seen: str
    last_seen: str
    sample_count: int = 1

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "route_id": self.route_id,
            "fingerprint_parts": self.fingerprint_parts,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "sample_count": self.sample_count,
        })
        return d


@dataclass
class OpportunityEventRecord:
    """``mid_opportunities`` — every state transition of every opportunity."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    opp_id: str
    event_id: str  # `{opp_id}:{event_ordinal}`
    event_ordinal: int
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "opp_id": self.opp_id,
            "event_id": self.event_id,
            "event_ordinal": self.event_ordinal,
            "event_type": self.event_type,
            "payload": self.payload,
        })
        return d


@dataclass
class ConfidenceRecord:
    """``mid_confidence`` — every confidence score emitted + inputs."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    opp_id: str
    score: float
    inputs: Dict[str, Any] = field(default_factory=dict)

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "opp_id": self.opp_id,
            "score": self.score,
            "inputs": self.inputs,
        })
        return d


@dataclass
class DecisionRecord:
    """``mid_decisions`` — every gate verdict per opportunity."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    opp_id: str
    gate: str  # kill_switch | mode | capital | secret | preflight | operator
    verdict: str  # allow | deny | skip
    reason: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "opp_id": self.opp_id,
            "gate": self.gate,
            "verdict": self.verdict,
            "reason": self.reason,
        })
        return d


@dataclass
class OutcomeRecord:
    """``mid_outcomes`` — terminal outcome per opportunity."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    opp_id: str
    terminal: str  # executed | shadow | rejected | policy_denied | expired
    pnl_usd: Optional[float] = None
    gas_actual_wei: Optional[str] = None
    revert_reason: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "opp_id": self.opp_id,
            "terminal": self.terminal,
            "pnl_usd": self.pnl_usd,
            "gas_actual_wei": self.gas_actual_wei,
            "revert_reason": self.revert_reason,
        })
        return d


@dataclass
class ReplayRecord:
    """``mid_replay`` — computed counter-factual outcomes."""

    mid_id: str
    ts: str
    meta: MidMetadata
    replay_context: Optional[ReplayContext]
    opp_id: str
    variant_id: str
    counter_factual_outcome: Dict[str, Any]

    def to_doc(self) -> Dict[str, Any]:
        d = _base_doc(self.mid_id, self.ts, self.meta, self.replay_context)
        d.update({
            "opp_id": self.opp_id,
            "variant_id": self.variant_id,
            "counter_factual_outcome": self.counter_factual_outcome,
        })
        return d


# ---------------------------------------------------------------------------
# Domain <-> collection map
# ---------------------------------------------------------------------------


DOMAINS: List[str] = [
    "market_state",
    "quotes",
    "liquidity",
    "gas",
    "providers",
    "routes",
    "opportunities",
    "confidence",
    "decisions",
    "outcomes",
    "replay",
]

MID_COLLECTION_MAP: Dict[str, str] = {d: f"mid_{d}" for d in DOMAINS}
# also expose the enum-warnings audit collection name
MID_COLLECTION_MAP["enum_warnings"] = "mid_enum_warnings"
