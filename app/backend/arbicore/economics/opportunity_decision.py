"""ArbiCore X — Opportunity decision path + simulation gate (P0 integrator).

Composes the ALREADY-BUILT engines (net_profit, confidence_v2, expected_value,
size_optimizer) into a single decision for one candidate opportunity, behind a
hard simulation/validation gate. Nothing here is rebuilt — it orchestrates.

INVARIANTS:
  * Confidence is ADVISORY — it never flips an execution decision on its own.
  * ``would_execute`` requires: simulation gate PASS  AND  EV > 0  AND  every
    hard gate PASS (router/token allowlist, non-zero min-output, slippage cap).
  * A stale/unavailable quote can NEVER be executable.
  * SHADOW/PAPER: this returns a decision object only. No signing/broadcast.

Pure / deterministic. No I/O, no RPC.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .net_profit import compute_net_profit
from .expected_value import evaluate_expected_value
from .size_optimizer import optimize_size
from ..intelligence.confidence_v2 import confidence_from_signals


@dataclass
class SimulationGateResult:
    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_simulation_gate(opp: Dict[str, Any], *,
                        router_allowlist: List[str],
                        token_allowlist: List[str],
                        max_slippage_bps: float = 150.0,
                        max_gas_usd: float = 50.0) -> SimulationGateResult:
    """Validate everything that must hold before an opp is EXECUTABLE.

    An empty/False on any check => not executable. This is a HARD gate;
    confidence/EV can never override a failure here.
    """
    routers = {r.lower() for r in router_allowlist}
    tokens = {t.lower() for t in token_allowlist}
    hops = opp.get("hops") or []
    checks: Dict[str, bool] = {}

    checks["quote_fresh"] = (opp.get("quote_status") == "REAL")
    checks["has_route"] = bool(hops) and len(hops) <= int(opp.get("max_hops", 3))
    checks["provider_ok"] = opp.get("flash_loan_provider") in ("aave_v3", "balancer_v2")
    checks["router_allowlisted"] = bool(hops) and all(
        str(h.get("router", "")).lower() in routers for h in hops)
    checks["tokens_allowlisted"] = bool(hops) and all(
        str(h.get("token_in", "")).lower() in tokens
        and str(h.get("token_out", "")).lower() in tokens for h in hops)
    checks["min_output_nonzero"] = bool(hops) and all(
        int(h.get("amount_out_min_wei") or 0) > 0 for h in hops)
    checks["slippage_ok"] = float(opp.get("expected_slippage_bps") or 0) <= max_slippage_bps
    checks["gas_ok"] = 0.0 < float(opp.get("gas_cost_usd") or 0) <= max_gas_usd
    checks["repayment_modeled"] = bool(opp.get("repayment_ok", False))
    checks["calldata_present"] = bool(opp.get("calldata_hex")) or bool(opp.get("user_data_hex"))
    checks["expected_profit_positive"] = float(opp.get("gross_spread_bps") or 0) > 0

    failures = [k for k, v in checks.items() if not v]
    return SimulationGateResult(passed=(len(failures) == 0), checks=checks,
                                failures=failures)


@dataclass
class OpportunityDecision:
    opportunity_id: str
    would_execute: bool
    reason: str
    gross_profit_usd: float
    net_profit_usd: float
    roi_bps: float
    confidence: float
    expected_value_usd: float
    optimal_notional_usd: Optional[float]
    simulation: Dict[str, Any]
    confidence_components: Dict[str, Any]
    size_optimization: Dict[str, Any]
    ev: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def decide_opportunity(opp: Dict[str, Any], *,
                       router_allowlist: List[str],
                       token_allowlist: List[str],
                       max_slippage_bps: float = 150.0,
                       max_gas_usd: float = 50.0,
                       wallet_reserve_usd: float = 0.0) -> OpportunityDecision:
    """Full decision path for one opportunity (SHADOW/PAPER — advisory)."""
    oid = str(opp.get("opportunity_id") or "")
    gross_spread_bps = float(opp.get("gross_spread_bps") or 0.0)
    pool_liq = float(opp.get("pool_liquidity_usd") or 0.0)
    gas_usd = float(opp.get("gas_cost_usd") or 0.0)
    flash_fee_bps = float(opp.get("flash_loan_fee_bps") or 0.0)

    sim = run_simulation_gate(
        opp, router_allowlist=router_allowlist, token_allowlist=token_allowlist,
        max_slippage_bps=max_slippage_bps, max_gas_usd=max_gas_usd)

    prob_kwargs = dict(
        simulation_passed=sim.passed,
        quote_age_sec=opp.get("quote_age_sec"),
        gas_certainty=opp.get("gas_certainty"),
        mev_risk=opp.get("mev_risk"),
        historical_success_rate=opp.get("historical_success_rate"))

    size = optimize_size(
        gross_spread_bps=gross_spread_bps, pool_liquidity_usd=pool_liq,
        gas_cost_usd=gas_usd, flash_loan_fee_bps=flash_fee_bps,
        buy_venue_fee_bps=float(opp.get("buy_venue_fee_bps") or 0.0),
        sell_venue_fee_bps=float(opp.get("sell_venue_fee_bps") or 0.0),
        native_price_usd=opp.get("native_price_usd"),
        max_slippage_bps=max_slippage_bps, wallet_reserve_usd=wallet_reserve_usd,
        prob_kwargs=prob_kwargs)
    chosen = size.get("chosen") or {}
    notional = chosen.get("notional_usd")

    # Net profit at the chosen size (or a reference size when nothing feasible).
    ref_notional = notional or float(opp.get("reference_notional_usd") or 10_000.0)
    npr = compute_net_profit(
        gross_spread_bps=gross_spread_bps, notional_usd=ref_notional,
        buy_venue_fee_bps=float(opp.get("buy_venue_fee_bps") or 0.0),
        sell_venue_fee_bps=float(opp.get("sell_venue_fee_bps") or 0.0),
        slippage_bps=float(opp.get("expected_slippage_bps") or 0.0),
        flash_loan_notional_usd=ref_notional, flash_loan_fee_bps=flash_fee_bps)
    net = npr.net_profit_usd - gas_usd

    conf = confidence_from_signals(
        quote_age_sec=opp.get("quote_age_sec"),
        liquidity_ratio=(ref_notional / pool_liq) if pool_liq else None,
        slippage_bps=opp.get("expected_slippage_bps"), max_slippage_bps=max_slippage_bps,
        gas_certainty=opp.get("gas_certainty"), flash_available=True,
        simulation_passed=sim.passed, mev_risk=opp.get("mev_risk"),
        historical_success=opp.get("historical_success_rate"),
        net_profit_bps=npr.net_profit_bps)

    ev = evaluate_expected_value(
        net_profit_usd=(chosen.get("net_profit_usd") if chosen else net),
        maximum_loss_usd=(chosen.get("maximum_loss_usd") if chosen else gas_usd),
        **prob_kwargs)

    ev_usd = chosen.get("expected_value_usd") if chosen else ev.expected_value_usd
    would = bool(sim.passed and chosen and (ev_usd is not None) and ev_usd > 0)
    if not sim.passed:
        reason = f"simulation gate failed: {', '.join(sim.failures)}"
    elif not chosen:
        reason = "no size produces positive risk-adjusted EV"
    elif ev_usd is None or ev_usd <= 0:
        reason = "expected value <= 0"
    else:
        reason = "executable candidate (SHADOW — advisory only, not broadcast)"

    return OpportunityDecision(
        opportunity_id=oid, would_execute=would, reason=reason,
        gross_profit_usd=npr.gross_profit_usd, net_profit_usd=round(net, 6),
        roi_bps=npr.net_profit_bps, confidence=conf.score,
        expected_value_usd=float(ev_usd if ev_usd is not None else ev.expected_value_usd),
        optimal_notional_usd=notional, simulation=sim.to_dict(),
        confidence_components=conf.to_dict(), size_optimization=size, ev=ev.to_dict())


__all__ = ["SimulationGateResult", "run_simulation_gate",
           "OpportunityDecision", "decide_opportunity"]
