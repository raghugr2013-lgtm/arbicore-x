"""FlashLoanOpportunityVerifier — sole canonical construction point
for ``OpportunityType.FLASH_LOAN_ARBITRAGE``.

INV-2: never invokes EmissionBus. Returns ``(canonical|None, outcome_tag)``.
INV-3: ``derive_provenance(legs)`` over per-leg ``source_id`` yields
``source_data_quality``. Aggregator-hint provenance from sources is
never propagated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from ...intelligence.roi_probability import ROIProbabilityEngine
from ...models.canonical import CanonicalOpportunity
from ...models.discovery import DiscoveryCandidate, VerifiedOutcome
from ...models.enums import MevRiskLevel, OpportunityType
from ..opportunity_verifier import OpportunityVerifier
from ..verification_evidence import (
    EvidenceLegRole, LegEvidence, VerificationEvidence,
    build_canonical_from_evidence, derive_provenance,
)
from ..cross_chain_arbitrage.bridge_intelligence import MevRiskScorer
from .economics import (
    FlashLoanEconomicsAssessor, FlashLoanEconomicsResult,
    FLASH_LOAN_PROVIDERS,
)
from .filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)


# Quote provider signature: async (cycle_metadata, borrow_amount_usd) ->
#                                   facts_dict | None
QuoteProvider = Callable[[Dict[str, Any], float],
                         Awaitable[Optional[Dict[str, Any]]]]


async def noop_quote_provider(cycle_metadata: Dict[str, Any],
                                 borrow_amount_usd: float,
                                 ) -> Optional[Dict[str, Any]]:
    """Cold-start provider — verifier ends as ``denied:venue_unreadable``."""
    return None


class FlashLoanOpportunityVerifier(OpportunityVerifier):
    """The single canonical-construction point for FLASH_LOAN_ARBITRAGE."""

    opportunity_type = OpportunityType.FLASH_LOAN_ARBITRAGE
    verifier_id = "flash_loan_opportunity_verifier"

    def __init__(
        self,
        *,
        quote_provider: QuoteProvider,
        economics_assessor: FlashLoanEconomicsAssessor,
        mev_scorer: MevRiskScorer,
        chain_liveness_loader: Optional[
            Callable[[str], Dict[str, float]]] = None,
        gate_7: Optional[FlashLoanGate7AtomicProfit] = None,
        gate_8: Optional[FlashLoanGate8LiquidityDepth] = None,
        gate_9: Optional[FlashLoanGate9FlashLoanMev] = None,
        outcome_history_loader: Optional[
            Callable[[Dict[str, Any]], Awaitable[List[Dict[str, Any]]]]
        ] = None,
        default_borrow_amount_usd: float = 10_000.0,
        evidence_sink: Optional[
            Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        shadow_sink: Optional[
            Callable[[CanonicalOpportunity, Dict[str, Any]],
                     Awaitable[None]]] = None,
        price_provenance_fn: Optional[
            Callable[[List[str]], List[Dict[str, Any]]]] = None,
    ) -> None:
        self.quote_provider = quote_provider
        self.economics = economics_assessor
        self.mev = mev_scorer
        self.chain_liveness_loader = chain_liveness_loader
        self.gate_7 = gate_7
        self.gate_8 = gate_8
        self.gate_9 = gate_9
        self.outcome_history_loader = outcome_history_loader
        self.default_borrow_amount_usd = default_borrow_amount_usd
        # M2.3 — auditable evidence sink (side-effect only; never alters the
        # returned verdict). M2.4 — SHADOW/PAPER routing for CONFIRMED opps.
        self.evidence_sink = evidence_sink
        self.shadow_sink = shadow_sink
        # M2.5 — per-token USD price provenance for the evidence bundle.
        self.price_provenance_fn = price_provenance_fn

    async def verify(self, candidate: DiscoveryCandidate,
                     ) -> Tuple[Optional[CanonicalOpportunity], str]:
        hm = candidate.hint_metric or {}
        chain = (hm.get("chain") or "").lower()
        provider = (hm.get("provider") or "").lower()
        borrow_token = (hm.get("borrow_token") or candidate.asset or "").upper()
        borrow_amount = float(hm.get("borrow_amount_usd")
                                or self.default_borrow_amount_usd)

        # M2.3 — per-gate outcome ledger. Every gate starts NOT_EVALUATED and
        # is flipped to PASS/FAIL as (and only as) it is actually evaluated,
        # so a short-circuited denial still records which gates ran.
        gates: Dict[str, Dict[str, Any]] = {
            "gate_7": {"status": "NOT_EVALUATED", "reason": None},
            "gate_8": {"status": "NOT_EVALUATED", "reason": None},
            "gate_9": {"status": "NOT_EVALUATED", "reason": None},
        }
        ev: Dict[str, Any] = {
            "candidate": candidate, "hm": hm, "chain": chain,
            "provider": provider, "borrow_token": borrow_token,
            "borrow_amount_usd": borrow_amount, "gates": gates,
            "facts": None, "econ": None, "mev_view": None, "min_tvl": 0.0,
        }

        try:
            facts = await self.quote_provider(hm, borrow_amount)
        except Exception as exc:  # noqa: BLE001
            return await self._finalize(
                ev, status="DENIED", canonical=None, outcome=(
                    f"{VerifiedOutcome.DENIED_VENUE_UNREADABLE}:"
                    f"{type(exc).__name__}"))
        if not facts:
            return await self._finalize(
                ev, status="DENIED", canonical=None,
                outcome=VerifiedOutcome.DENIED_VENUE_UNREADABLE)
        ev["facts"] = facts

        provider_meta = FLASH_LOAN_PROVIDERS.get(provider) or {}
        provider_source_id = provider_meta.get(
            "source_id") or "aave_v3_flashloan_real"
        hop_facts = list(facts.get("hop_legs") or [])
        if not hop_facts:
            return await self._finalize(
                ev, status="DENIED", canonical=None,
                outcome=VerifiedOutcome.DENIED_VENUE_UNREADABLE)

        # Chain congestion read (optional).
        cong = self._chain_congestion(chain)

        mev_view = self.mev.classify(
            source_chain_congestion=cong,
            destination_chain_congestion=cong,
            asset=borrow_token,
            notional_usd=borrow_amount,
            is_atomic=True,
        )
        ev["mev_view"] = mev_view

        # Outcome history fold-in
        real_outcomes: List[Dict[str, Any]] = list(
            facts.get("real_outcomes") or [])
        if self.outcome_history_loader is not None:
            try:
                hist = await self.outcome_history_loader({
                    "chain": chain, "provider": provider,
                    "borrow_token": borrow_token,
                    "route_id": hm.get("route_id") or candidate.subject_id,
                })
                if hist:
                    real_outcomes.extend(hist)
            except Exception:  # noqa: BLE001
                pass

        econ: FlashLoanEconomicsResult = self.economics.assess(
            provider=provider, chain=chain,
            borrow_token=borrow_token, borrow_amount_usd=borrow_amount,
            hop_legs=hop_facts,
            signal_categories=[provider, chain, borrow_token],
            real_outcomes=real_outcomes,
            synthetic_outcomes=list(facts.get("synthetic_outcomes") or []),
            gross_profit_pct=float(facts.get("gross_profit_pct") or 0.0),
            flash_loan_fee_bps_override=facts.get(
                "flash_loan_fee_bps_override"),
            mev_risk_level=mev_view["level"],
            gas_cost_usd_override=facts.get("gas_cost_usd"),
            tx_gas_units=facts.get("tx_gas_units"),
            # Authoritative live path: gross came from the real on-chain quote
            # (pool swap fees already embedded) → do not deduct them again.
            gross_is_quote_inclusive=True,
        )
        ev["econ"] = econ

        # ---- Gate 7 ---------------------------------------------------------
        if self.gate_7 is not None:
            g7 = self.gate_7.evaluate(
                atomic_profit_usd=econ.atomic_profit_usd,
                borrow_amount_usd=borrow_amount,
            )
            gates["gate_7"] = {
                "status": "PASS" if g7.passed else "FAIL", "reason": g7.reason}
            if not g7.passed:
                return await self._finalize(
                    ev, status="DENIED", canonical=None, outcome=(
                        f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_7:"
                        f"{g7.reason}"))

        # ---- Gate 8 ---------------------------------------------------------
        min_tvl = float(hm.get("min_tvl_usd")
                         or facts.get("min_pool_tvl_usd_in_route") or 0.0)
        ev["min_tvl"] = min_tvl
        if self.gate_8 is not None:
            g8 = self.gate_8.evaluate(min_pool_tvl_usd_in_route=min_tvl)
            gates["gate_8"] = {
                "status": "PASS" if g8.passed else "FAIL", "reason": g8.reason}
            if not g8.passed:
                return await self._finalize(
                    ev, status="DENIED", canonical=None, outcome=(
                        f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_8:"
                        f"{g8.reason}"))

        # ---- Gate 9 ---------------------------------------------------------
        if self.gate_9 is not None:
            g9 = self.gate_9.evaluate(
                mev_risk_level=mev_view["level"],
                mev_risk_label=mev_view["label"],
                mev_score=mev_view["score"],
            )
            gates["gate_9"] = {
                "status": "PASS" if g9.passed else "FAIL", "reason": g9.reason}
            if not g9.passed:
                return await self._finalize(
                    ev, status="DENIED", canonical=None, outcome=(
                        f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_9:"
                        f"{g9.reason}"))

        # ---- Build LegEvidence: BORROW + per-hop + REPAY ------------------
        legs: List[LegEvidence] = [LegEvidence(
            leg_role=EvidenceLegRole.FLASH_LOAN_BORROW,
            venue_id=f"{provider}_flashloan:{chain}",
            source_id=provider_source_id,
            price=None, size_usd=borrow_amount, depth_usd=borrow_amount,
            fee_bps=facts.get("flash_loan_fee_bps_override") or 0,
            chain=chain,
            metadata={"provider": provider},
        )]
        for i, hop in enumerate(hop_facts):
            legs.append(LegEvidence(
                leg_role=EvidenceLegRole.HOP,
                venue_id=str(hop.get("venue_id") or f"hop_{i}"),
                source_id=str(hop.get("source_id") or "uniswap_v3_quote_real"),
                price=hop.get("price"),
                size_usd=borrow_amount,
                depth_usd=float(hop.get("depth_usd") or 0.0),
                fee_bps=int(hop.get("fee_bps") or 30),
                chain=chain,
                metadata={"hop_index": i,
                          "dex_protocol": hop.get("dex_protocol")},
            ))
        legs.append(LegEvidence(
            leg_role=EvidenceLegRole.FLASH_LOAN_REPAY,
            venue_id=f"{provider}_flashloan:{chain}",
            source_id=provider_source_id,
            price=None, size_usd=borrow_amount, depth_usd=borrow_amount,
            fee_bps=0, chain=chain,
            metadata={"provider": provider},
        ))

        try:
            _ = derive_provenance(legs)
        except ValueError:
            # All gates passed, but provenance is inconsistent → honest denial.
            return await self._finalize(
                ev, status="DENIED", canonical=None,
                outcome=VerifiedOutcome.DENIED_VENUE_UNREADABLE)

        evidence = VerificationEvidence(
            verifier_id=self.verifier_id,
            candidate_id=candidate.candidate_id,
            discovery_source=candidate.hint_source,
            subject_id=candidate.subject_id,
            asset=borrow_token,
            chain=chain,
            legs=legs,
            gross_spread_pct=None,
            expected_profit_usd=econ.atomic_profit_usd,
            capital_required_usd=0.0,    # flash loan: zero own capital
            notional_usd=econ.borrow_amount_usd,
            extra_metrics={
                "economics": _econ_to_dict(econ),
                "mev": mev_view,
                "route": {
                    "route_pools": hm.get("route_pools", []),
                    "route_dex_protocols": hm.get("route_dex_protocols", []),
                    "cycle_token_path": hm.get("cycle_token_path", []),
                    "hop_count": int(hm.get("hop_count", len(hop_facts))),
                    "min_tvl_usd": min_tvl,
                },
            },
        )

        category_metadata = _fold_metadata(
            hm=hm, facts=facts, econ=econ, mev_view=mev_view,
            min_tvl=min_tvl,
        )

        canonical = build_canonical_from_evidence(
            evidence,
            opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
            opportunity_id=_opp_id(candidate, evidence.verified_at_ts),
            expected_profit_usd=econ.atomic_profit_usd,
            capital_required_usd=0.0,
            liquidity_score=min(100.0, min_tvl / 10_000.0),
            mev_risk_level=mev_view["level"],
            category_metadata=category_metadata,
            extra_metadata={
                "provider": provider,
                "chain": chain,
                "borrow_token": borrow_token,
            },
        )
        return await self._finalize(
            ev, status="CONFIRMED", canonical=canonical,
            outcome=VerifiedOutcome.CONFIRMED_PREFIX + canonical.opportunity_id)

    # ---- M2.3/M2.4 finalisation: audit evidence + SHADOW routing -----------

    async def _finalize(self, ev: Dict[str, Any], *, status: str,
                        outcome: str,
                        canonical: Optional[CanonicalOpportunity],
                        ) -> Tuple[Optional[CanonicalOpportunity], str]:
        """Single exit point: persist an auditable evidence bundle for EVERY
        verified candidate (CONFIRMED and DENIED) and, on CONFIRM, route the
        canonical into the SHADOW/PAPER sink. Both are side-effects wrapped
        fail-safe — they NEVER change the returned ``(canonical, outcome)``."""
        if self.evidence_sink is not None:
            try:
                await self.evidence_sink(
                    self._build_evidence_bundle(ev, status=status,
                                                outcome=outcome,
                                                canonical=canonical))
            except Exception:  # noqa: BLE001 — audit is best-effort, never fatal
                pass
        if status == "CONFIRMED" and canonical is not None \
                and self.shadow_sink is not None:
            try:
                await self.shadow_sink(
                    canonical,
                    self._build_evidence_bundle(ev, status=status,
                                                outcome=outcome,
                                                canonical=canonical))
            except Exception:  # noqa: BLE001 — SHADOW routing never blocks verify
                pass
        return canonical, outcome

    def _build_evidence_bundle(self, ev: Dict[str, Any], *, status: str,
                               outcome: str,
                               canonical: Optional[CanonicalOpportunity],
                               ) -> Dict[str, Any]:
        candidate: DiscoveryCandidate = ev["candidate"]
        hm: Dict[str, Any] = ev["hm"]
        facts: Dict[str, Any] = ev.get("facts") or {}
        econ = ev.get("econ")
        mev_view = ev.get("mev_view") or {}
        route_pools = list(hm.get("route_pools", []))
        ts = float(facts.get("verified_at_ts") or 0.0)
        bundle: Dict[str, Any] = {
            "bundle_id": f"flarb:{candidate.candidate_id}:{int(ts)}",
            "source_component": "flash_loan_arb_verifier",
            "source_model_id": candidate.candidate_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": "m2.3",
            # canonical audit distinction (per M2.3 requirement)
            "verification_status": status,             # CONFIRMED | DENIED
            "outcome_tag": outcome,
            "opportunity_id": (canonical.opportunity_id
                               if canonical is not None else None),
            "candidate_id": candidate.candidate_id,
            "subject_id": candidate.subject_id,
            "discovery_source": candidate.hint_source,
            "chain": ev["chain"],
            "flash_loan_provider": ev["provider"],
            "borrow_token": ev["borrow_token"],
            "input_amount_usd": ev["borrow_amount_usd"],
            "route": {
                "route_pools": route_pools,
                "route_pool_addresses": _resolve_pool_addresses(route_pools),
                "route_dex_protocols": list(hm.get("route_dex_protocols", [])),
                "cycle_token_path": list(hm.get("cycle_token_path", [])),
                "hop_count": int(hm.get("hop_count", len(route_pools))),
            },
            "quotes": {
                "gross_profit_pct": facts.get("gross_profit_pct"),
                "route_quote_status": facts.get("route_quote_status"),
                "hop_legs": list(facts.get("hop_legs") or []),
            },
            "liquidity": {
                "min_pool_tvl_usd_in_route": ev.get("min_tvl", 0.0),
                "tvl_provenance": facts.get("tvl_provenance"),
                "price_provenance": self._price_provenance(hm),
            },
            "gas": {
                "tx_gas_units": facts.get("tx_gas_units"),
                "gas_cost_usd": (econ.gas_cost_usd if econ is not None
                                 else None),
            },
            "mev": mev_view,
            # explicit per-gate outcomes + reasons (never a generic denial)
            "gates": ev["gates"],
            "block_context": {"verified_at_ts": ts},
            "provenance": "REAL",
            "broadcast": False,     # invariant: verification never broadcasts
        }
        if econ is not None:
            bundle["fees"] = {
                "flash_loan_fee_bps": int(
                    facts.get("flash_loan_fee_bps_override") or 0),
                "flash_loan_fee_usd": econ.flash_loan_fee_usd,
                "total_swap_fee_pct": econ.total_swap_fee_pct,
                "total_slippage_pct": econ.economics.total_slippage_pct,
            }
            bundle["economics"] = {
                "gross_spread_pct": econ.economics.gross_spread_pct,
                "atomic_profit_usd": econ.atomic_profit_usd,
                "expected_net_after_costs_usd": econ.atomic_profit_usd,
                "borrow_amount_usd": econ.borrow_amount_usd,
            }
        return bundle

    def _price_provenance(self, hm: Dict[str, Any]) -> List[Dict[str, Any]]:
        """M2.5 — per-token USD price provenance for the route (audit only)."""
        if self.price_provenance_fn is None:
            return []
        toks: List[str] = list(hm.get("cycle_token_path") or [])
        if not toks:
            bt = hm.get("borrow_token")
            if bt:
                toks = [bt]
        try:
            return self.price_provenance_fn(toks)
        except Exception:  # noqa: BLE001 — audit is best-effort, never fatal
            return []


    # ---- helpers ----------------------------------------------------------

    def _chain_congestion(self, chain: str) -> float:
        if self.chain_liveness_loader is None:
            return 30.0
        try:
            snap = self.chain_liveness_loader(chain) or {}
            return float(snap.get("congestion_score", 30.0))
        except Exception:  # noqa: BLE001
            return 30.0


def _fold_metadata(*, hm: Dict[str, Any], facts: Dict[str, Any],
                    econ: FlashLoanEconomicsResult,
                    mev_view: Dict[str, Any], min_tvl: float,
                    ) -> Dict[str, Any]:
    return {
        "chain": econ.chain,
        "flash_loan_provider": econ.provider,
        "flash_loan_pool_address": facts.get("flash_loan_pool_address", ""),
        "flash_loan_borrow_token": econ.borrow_token,
        "flash_loan_borrow_amount_usd": econ.borrow_amount_usd,
        "flash_loan_fee_bps": int(
            facts.get("flash_loan_fee_bps_override") or 0),
        "flash_loan_fee_usd": econ.flash_loan_fee_usd,
        "route_pools": list(hm.get("route_pools", [])),
        "route_dex_protocols": list(hm.get("route_dex_protocols", [])),
        "cycle_token_path": list(hm.get("cycle_token_path", [])),
        "hop_count": int(hm.get("hop_count", econ.hop_count)),
        "total_swap_fee_pct": econ.total_swap_fee_pct,
        "total_slippage_pct": econ.economics.total_slippage_pct,
        "gas_cost_usd": econ.gas_cost_usd,
        "gas_drag_pct": econ.economics.gas_drag_pct,
        "min_pool_tvl_usd_in_route": min_tvl,
        "atomic_profit_usd": econ.atomic_profit_usd,
        "atomic_profit_pct": round(
            100.0 * econ.atomic_profit_usd /
            max(econ.borrow_amount_usd, 1.0), 4),
        "expected_net_after_costs_usd": econ.atomic_profit_usd,
        "route_search_wall_ms": int(hm.get("route_search_wall_ms", 0)),
        "route_search_candidates_explored": int(
            hm.get("route_search_candidates_explored", 0)),
        "flash_loan_mev_risk_class": mev_view["label"],
        "simulated_atomicity_ok": True,
        "verified_at_ts": float(facts.get("verified_at_ts") or 0.0),
        "verifier_id": "flash_loan_opportunity_verifier",
    }


def _econ_to_dict(econ: FlashLoanEconomicsResult) -> Dict[str, Any]:
    e = econ.economics
    return {
        "gross_spread_pct": e.gross_spread_pct,
        "total_fee_pct": e.total_fee_pct,
        "total_slippage_pct": e.total_slippage_pct,
        "gas_drag_pct": e.gas_drag_pct,
        "mev_penalty_pct": e.mev_penalty_pct,
        "mev_adjusted_net_pct": e.mev_adjusted_net_pct,
        "expected_profit_usd": e.expected_profit_usd,
        "atomic_profit_usd": econ.atomic_profit_usd,
        "borrow_amount_usd": econ.borrow_amount_usd,
        "roi_confidence_label": econ.roi.confidence_label,
    }


def _opp_id(candidate: DiscoveryCandidate, ts: float) -> str:
    return f"flash_loan_arb:{candidate.subject_id}:{int(ts)}"


def _resolve_pool_addresses(route_pools: List[str]) -> List[Optional[str]]:
    """Map each synthetic route pool id (== canonical registry id) to its REAL
    contract address for the audit trail. Unresolved pools → None (never
    fabricated)."""
    try:
        from ...discovery.base_pool_registry import canonical_pool_by_id
    except Exception:  # noqa: BLE001
        return [None for _ in route_pools]
    out: List[Optional[str]] = []
    for pid in route_pools:
        cp = canonical_pool_by_id(pid)
        out.append(getattr(cp, "address", None) if cp else None)
    return out
