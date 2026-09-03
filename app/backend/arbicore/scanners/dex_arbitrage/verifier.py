"""ArbiCore X — Phase D D-3.2 DEXQuoteVerifier.

The future single canonical emitter for ``OpportunityType.DEX_ARBITRAGE``.

This module is **DEX-specific only at the I/O boundary** — it knows how to
ask a `BaseDEXQuoter` for a pair quote across viable (dex, chain) pools.
Everything downstream of evidence assembly is handled by the **universal
verification-evidence substrate** (``arbicore.scanners.verification_evidence``)
so D-4 (Launch), D-5 (Cross-Chain), and D-6 (FlashLoan) can reuse the same
canonical builder without protocol-specific branching.

INV-1: returns (CanonicalOpportunity, outcome_tag) — never accepts a
       DiscoveryCandidate as canonical. The canonical row is built fresh
       from normalized VerificationEvidence.
INV-2: never invokes the EmissionBus emit method — the D-3.4 scanner does that.
INV-3: every CanonicalOpportunity built here derives ``source_data_quality``
       from the per-leg quoter SOURCE_REGISTRY classification — never from
       the candidate.hint_source nor any aggregator HINT.

D-3.2 verifier intentionally lets `_quote_impl` return the D-3.1 stub
result (ok=False, reason='not_yet_wired:...'). Until D-3.6 wires live
HTTP, verify() will return ``(None, DENIED_VENUE_UNREADABLE)`` for live
candidates — which is the **correct** observable outcome: the verifier-first
architecture refuses to fabricate a CanonicalOpportunity when no venue read
succeeded. Tests inject mocked quoter results to exercise the full pipeline.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...data.provenance import get_classification
from ...data.venue_capability_repo import VenueCapabilityRepository
from ...models.canonical import CanonicalOpportunity
from ...models.discovery import DiscoveryCandidate, VerifiedOutcome
from ...models.enums import DataProvenance, OpportunityType
from ..gates.types import GateContext
from ..opportunity_verifier import OpportunityVerifier
from ..verification_evidence import (
    EvidenceLegRole, LegEvidence, VerificationEvidence,
    build_canonical_from_evidence,
)
from .economics import DEXEconomicsAssessor
from .filter import DEXGateContext, run_dex_gates
from .quoter import BaseDEXQuoter, DEXQuoteResult

logger = logging.getLogger("arbicore.scanners.dex_arb.verifier")


_DEX_FAMILY_NAME = "dex_quote_verifier"


def _parse_subject_id(subject_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse "BASE/QUOTE@chain" → (base, quote, chain). Returns Nones on malformed."""
    if not subject_id or "@" not in subject_id or "/" not in subject_id:
        return None, None, None
    pair_part, chain = subject_id.split("@", 1)
    if "/" not in pair_part:
        return None, None, chain.strip().lower() or None
    base, quote = pair_part.split("/", 1)
    return base.strip(), quote.strip(), chain.strip().lower() or None


def _pair_canonical_for_chain(base: str, quote: str, chain: str) -> str:
    return f"{base}/{quote}@{chain}"


class DEXQuoteVerifier(OpportunityVerifier):
    """Quote-based DEX-arb verifier. Protocol-agnostic at canonical-build time."""

    opportunity_type = OpportunityType.DEX_ARBITRAGE

    def __init__(self, *,
                 quoters: List[BaseDEXQuoter],
                 venue_caps: VenueCapabilityRepository,
                 confidence_engine: Any = None,
                 config_loader: Callable[[], Dict[str, Any]] = lambda: {},
                 economics_assessor: Optional["DEXEconomicsAssessor"] = None,
                 ) -> None:
        if not quoters:
            raise ValueError("DEXQuoteVerifier requires at least one quoter")
        self._venue_caps = venue_caps
        self._confidence = confidence_engine
        self._config_loader = config_loader
        self._economics = economics_assessor or DEXEconomicsAssessor(
            config_loader=config_loader,
        )
        # Build a lookup keyed by chain → list of quoters on that chain
        self._quoters_by_chain: Dict[str, List[BaseDEXQuoter]] = {}
        for q in quoters:
            self._quoters_by_chain.setdefault(q.chain, []).append(q)

    # ----- public OpportunityVerifier API -----------------------------------

    async def verify(self, candidate: DiscoveryCandidate,
                     ) -> Tuple[Optional[CanonicalOpportunity], str]:
        """INV-2 emit path is in the scanner, not here. We return
        (CanonicalOpportunity, outcome_tag) or (None, denied_reason)."""
        base, quote, chain = _parse_subject_id(candidate.subject_id)
        if base is None or quote is None or chain is None:
            return None, VerifiedOutcome.ERROR_PREFIX + "malformed_subject_id"
        quoters = self._quoters_by_chain.get(chain) or []
        if not quoters:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE
        pair_canonical = _pair_canonical_for_chain(base, quote, chain)
        cfg = self._config_loader() or {}
        notional = float(cfg.get("default_notional_usd", 1000.0))

        # Quote every eligible (chain, dex) — both buy and sell sides
        per_dex: Dict[str, Dict[str, DEXQuoteResult]] = {}
        for q in quoters:
            buy_res = await q.quote(pair_canonical=pair_canonical,
                                    size_in_usd=notional, direction="buy")
            sell_res = await q.quote(pair_canonical=pair_canonical,
                                     size_in_usd=notional, direction="sell")
            per_dex[q.dex] = {"buy": buy_res, "sell": sell_res, "quoter": q}

        # Filter to (dex) where both buy and sell quotes succeeded and yielded
        # a positive effective price
        viable: Dict[str, Dict[str, Any]] = {
            dex: bag
            for dex, bag in per_dex.items()
            if (bag["buy"].ok and bag["sell"].ok
                and (bag["buy"].effective_price or 0) > 0
                and (bag["sell"].effective_price or 0) > 0)
        }
        if len(viable) < 2:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        # Best buy = lowest effective ask; best sell = highest effective bid
        buy_dex = min(viable, key=lambda d: viable[d]["buy"].effective_price)
        sell_dex = max(viable, key=lambda d: viable[d]["sell"].effective_price)
        if buy_dex == sell_dex:
            return None, VerifiedOutcome.DENIED_VENUE_DISAGREES

        buy_q: DEXQuoteResult = viable[buy_dex]["buy"]
        sell_q: DEXQuoteResult = viable[sell_dex]["sell"]
        buy_price = float(buy_q.effective_price)
        sell_price = float(sell_q.effective_price)
        spread_pct = (sell_price - buy_price) / buy_price * 100.0
        if spread_pct <= 0:
            return None, VerifiedOutcome.DENIED_VENUE_DISAGREES

        # INV-3 attribution: provenance per leg from quoter.source_id
        for q_res in (buy_q, sell_q):
            cls = get_classification(q_res.source_id or "")
            if cls in (DataProvenance.DEAD, DataProvenance.CONTAMINATED):
                return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        # Run economics assessment (D-3.3 — protocol-agnostic substrate)
        from ...models.enums import MevRiskLevel
        assessment = self._economics.assess(
            buy_quote=buy_q, sell_quote=sell_q, chain=chain,
            gross_spread_pct=spread_pct, notional_usd=notional,
            mev_risk_level=MevRiskLevel.LOW,    # D-3.6+: derive from MEV classifier
        )

        # Build normalized evidence (protocol-agnostic — D-4/5/6 use same shape)
        legs = [
            LegEvidence(
                leg_role=EvidenceLegRole.BUY,
                venue_id=f"{buy_dex}:{chain}",
                source_id=buy_q.source_id or f"{buy_dex}_quoter_{chain}",
                price=buy_price,
                size_usd=notional,
                depth_usd=buy_q.pool_liquidity_usd,
                fee_bps=buy_q.fee_tier_bps,
                age_ms=buy_q.age_ms,
                chain=chain,
                metadata={
                    "pool_address": buy_q.pool_address,
                    "mid_price": buy_q.mid_price,
                    "slippage_pct": buy_q.slippage_pct,
                    "gas_estimate_usd": buy_q.gas_estimate_usd,
                    "quote_backend": (buy_q.raw or {}).get("winning_backend"),
                },
            ),
            LegEvidence(
                leg_role=EvidenceLegRole.SELL,
                venue_id=f"{sell_dex}:{chain}",
                source_id=sell_q.source_id or f"{sell_dex}_quoter_{chain}",
                price=sell_price,
                size_usd=notional,
                depth_usd=sell_q.pool_liquidity_usd,
                fee_bps=sell_q.fee_tier_bps,
                age_ms=sell_q.age_ms,
                chain=chain,
                metadata={
                    "pool_address": sell_q.pool_address,
                    "mid_price": sell_q.mid_price,
                    "slippage_pct": sell_q.slippage_pct,
                    "gas_estimate_usd": sell_q.gas_estimate_usd,
                    "quote_backend": (sell_q.raw or {}).get("winning_backend"),
                },
            ),
        ]
        evidence = VerificationEvidence(
            verifier_id=_DEX_FAMILY_NAME,
            candidate_id=candidate.candidate_id,
            discovery_source=candidate.hint_source,
            subject_id=candidate.subject_id,
            asset=base,
            chain=chain,
            legs=legs,
            gross_spread_pct=spread_pct,
            notional_usd=notional,
            extra_metrics={
                "buy_dex": buy_dex, "sell_dex": sell_dex,
                "buy_mid": buy_q.mid_price, "sell_mid": sell_q.mid_price,
                "buy_pool_address": buy_q.pool_address,
                "sell_pool_address": sell_q.pool_address,
            },
        )

        # Hand off to the UNIVERSAL canonical builder (D-4/5/6 will too).
        epoch_min = int(time.time() / 60)
        opp_id = f"dexarb:{base}/{quote}:{chain}:{buy_dex}->{sell_dex}:{epoch_min}"
        try:
            opp = build_canonical_from_evidence(
                evidence,
                opportunity_type=OpportunityType.DEX_ARBITRAGE,
                opportunity_id=opp_id,
                category_metadata={
                    "chain": chain,
                    "buy_dex": buy_dex, "sell_dex": sell_dex,
                    "buy_pool_address": buy_q.pool_address,
                    "sell_pool_address": sell_q.pool_address,
                    "fee_tier_bps": buy_q.fee_tier_bps or sell_q.fee_tier_bps,
                    "estimated_slippage_pct": assessment.total_slippage_pct,
                    "gas_estimate_usd": assessment.total_gas_usd,
                    "gas_drag_pct": assessment.gas_drag_pct,
                    "total_slippage_pct": assessment.total_slippage_pct,
                    "mev_penalty_pct": assessment.mev_penalty_pct,
                    "mev_adjusted_net_pct": assessment.mev_adjusted_net_pct,
                    "net_spread_after_slip_pct": (
                        assessment.net_spread_after_slip_after_fees_pct),
                    "net_spread_after_slip_after_gas_pct": (
                        assessment.net_after_costs_pct),
                },
            )
        except ValueError:
            # CONTAMINATED / DEAD leg — already caught above, defensive
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        # Run gates: Gate 1 (DEX economics-aware) then universal Gates 2-5
        ctx = DEXGateContext(
            cfg=cfg,
            venue_caps=self._venue_caps,
            buy_venue=opp.buy_venue,
            sell_venue=opp.sell_venue,
            buy_side_depth_usd=float(buy_q.pool_liquidity_usd or 0.0),
            sell_side_depth_usd=float(sell_q.pool_liquidity_usd or 0.0),
            confidence_engine=self._confidence,
            assessment=assessment,
        )
        passed, gate, reason = await run_dex_gates(opp, ctx)
        from ...models.enums import OpportunityStatus
        if passed:
            opp.status = OpportunityStatus.VALIDATED
            return opp, VerifiedOutcome.CONFIRMED_PREFIX + opp_id
        # Even on rejection we still hand back the canonical row so the
        # scanner orchestrator (D-3.4) can persist it as a CANDIDATE with
        # gate-rejection metadata (same pattern as D-1 / D-2).
        if opp.metadata is None:
            opp.metadata = {}
        opp.metadata["rejected_at_gate"] = gate
        opp.metadata["rejected_gate_name"] = (
            reason.split(":")[0] if reason else "")
        opp.metadata["rejected_reason"] = reason
        return opp, VerifiedOutcome.DENIED_GATE_PREFIX + (reason or "unknown")
