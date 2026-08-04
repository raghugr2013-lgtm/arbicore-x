"""Flash-Loan Operator Journey (Stage 4 · v2.6.0).

Complete end-to-end DRY-RUN operator workflow that composes the existing
Provider Registry, safety layer, and paper engine into one journey
object. Zero signing. Zero broadcasts. Every ``execute`` returns a plan
plus a ``ready_for_signing: bool`` — the sign+broadcast step remains
disabled at the safety layer.

Contract:

    j = FlashLoanOperatorJourney(registry, kill_switch, capital, mid_writer)
    result = await j.run(opportunity)
    # result contains:
    #   qualified, route, capital_plan, simulation, tx_plan,
    #   execution_plan, safety_result, approval_result,
    #   rollback_plan, audit_evidence
    # plus ``ready_for_signing``  (always False in v2.6.0)
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class FlashLoanOperatorJourney:
    def __init__(self, *, registry: Any, kill_switch: Any,
                 capital_policy: Any, approval_gate: Any = None,
                 mid_writer: Any = None,
                 default_flash_loan_venue: str = "aave_v3",
                 default_flash_loan_fee_bps: float = 5.0):
        self._registry = registry
        self._kill = kill_switch
        self._capital = capital_policy
        self._approval = approval_gate
        self._mid = mid_writer
        self._default_venue = default_flash_loan_venue
        self._default_fee_bps = float(default_flash_loan_fee_bps)

    # ==================================================================
    # Phase A — qualification
    # ==================================================================
    def qualify(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        reasons: List[str] = []
        opp_type = opp.get("opportunity_type", "unknown")
        if opp_type not in ("cex_spot_arbitrage", "cex_dex_arbitrage",
                            "dex_arbitrage", "flash_loan_arbitrage"):
            reasons.append(f"unsupported_type:{opp_type}")
        if not opp.get("chain"):
            reasons.append("missing_chain")
        net = opp.get("net_profit_usd")
        if net is None:
            reasons.append("missing_net_profit")
        if isinstance(net, (int, float)) and net <= 0:
            reasons.append("unprofitable")
        return {"qualified": len(reasons) == 0, "reasons": reasons,
                 "opp_type": opp_type, "chain": opp.get("chain")}

    # ==================================================================
    # Phase B — route construction
    # ==================================================================
    def build_route(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        hops: List[Dict[str, Any]] = []
        buy_venue = opp.get("venue_buy") or "unknown"
        sell_venue = opp.get("venue_sell") or "unknown"
        symbol = opp.get("symbol") or "UNKNOWN"
        hops.append({"seq": 0, "action": "flash_loan_borrow",
                       "venue": self._default_venue,
                       "asset": _quote_asset(symbol),
                       "notional_usd": opp.get("capital_required_usd", 0.0)})
        hops.append({"seq": 1, "action": "buy",
                       "venue": buy_venue, "symbol": symbol,
                       "notional_usd": opp.get("notional_usd", 0.0)})
        hops.append({"seq": 2, "action": "sell",
                       "venue": sell_venue, "symbol": symbol,
                       "notional_usd": opp.get("notional_usd", 0.0)})
        hops.append({"seq": 3, "action": "flash_loan_repay",
                       "venue": self._default_venue,
                       "asset": _quote_asset(symbol),
                       "fee_bps": self._default_fee_bps})
        return {
            "route_id": f"journey:{opp.get('opp_id','anon')}",
            "hop_count": len(hops), "hops": hops,
            "atomic": True, "requires_flash_loan": True,
        }

    # ==================================================================
    # Phase C — capital estimation
    # ==================================================================
    def estimate_capital(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        notional = float(opp.get("notional_usd") or 0.0)
        gas = float(opp.get("expected_gas_usd") or 0.0)
        fees = float(opp.get("trading_fees_usd") or 0.0)
        slippage = float(opp.get("slippage_cost_usd") or 0.0)
        clipped = notional
        if self._capital is not None:
            try:
                clipped = float(self._capital.clip_capital(
                    requested_usd=notional,
                    chain=opp.get("chain") or None,
                    opportunity_type=opp.get("opportunity_type") or None))
            except Exception as exc:                                 # noqa
                logger.exception("clip_capital failed: %s", exc)
                clipped = notional
        return {
            "requested_notional_usd": notional,
            "clipped_notional_usd": clipped,
            "cap_applied": (
                None if clipped == notional else "per_trade_or_per_type_cap"),
            "flash_loan_notional_usd": clipped,
            "flash_loan_fee_bps": self._default_fee_bps,
            "estimated_gas_usd": gas,
            "estimated_trading_fees_usd": fees,
            "estimated_slippage_usd": slippage,
            "peak_capital_at_risk_usd": 0.0,   # flash loan atomicity
        }

    # ==================================================================
    # Phase D — flash loan simulation (dry-run)
    # ==================================================================
    def simulate_flash_loan(self, opp: Dict[str, Any],
                             capital: Dict[str, Any]) -> Dict[str, Any]:
        # Dry-run: we do not call any RPC or Aave contract. We produce
        # the fee and liquidity envelope the operator will see live.
        notional = capital.get("flash_loan_notional_usd") or 0.0
        fee_usd = notional * self._default_fee_bps / 10_000.0
        return {
            "venue": self._default_venue,
            "asset": _quote_asset(opp.get("symbol") or "?"),
            "notional_usd": notional,
            "fee_bps": self._default_fee_bps,
            "fee_usd": round(fee_usd, 4),
            "available_liquidity_usd": None,   # requires live pool state
            "simulation_status": "dry_run",
            "would_repay_usd": round(notional + fee_usd, 4),
        }

    # ==================================================================
    # Phase E — transaction builder (dry-run)
    # ==================================================================
    def build_transactions(self, opp: Dict[str, Any],
                            route: Dict[str, Any]) -> Dict[str, Any]:
        tx_id = f"dryrun_tx_{uuid.uuid4().hex[:12]}"
        return {
            "transaction_id": tx_id,
            "atomic": True,
            "target_contract": "flashloan_arbitrage_executor",
            "chain": opp.get("chain"),
            "calldata_size_bytes": 0,   # not built in v2.6.0
            "signature_status": "not_signed",
            "nonce": None,
            "prepared_at": _iso(),
        }

    # ==================================================================
    # Phase F — execution planner
    # ==================================================================
    def plan_execution(self, opp: Dict[str, Any], route: Dict[str, Any],
                        capital: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "execution_id": f"plan_{uuid.uuid4().hex[:10]}",
            "route_id": route.get("route_id"),
            "chain": opp.get("chain"),
            "estimated_block_delay": 1,
            "priority_fee_gwei": 2.0,
            "mev_protection": True,
            "sequencing": "atomic-bundle",
        }

    # ==================================================================
    # Phase G — safety validation
    # ==================================================================
    def validate_safety(self, opp: Dict[str, Any],
                         capital: Dict[str, Any]) -> Dict[str, Any]:
        kill_engaged = bool(self._kill.is_engaged()) if self._kill else True
        live_exec = False
        if self._kill and hasattr(self._kill, "config"):
            live_exec = bool(getattr(self._kill.config,
                                       "live_execution_enabled", False))
        return {
            "kill_engaged": kill_engaged,
            "live_execution_enabled": live_exec,
            "requires_approval": True,
            "capital_within_caps": (
                capital.get("clipped_notional_usd")
                == capital.get("requested_notional_usd")),
            "paper_validation_required": True,
            "signing_allowed": False,   # v2.6.0 always False
            "broadcast_allowed": False, # v2.6.0 always False
        }

    # ==================================================================
    # Phase H — approval workflow
    # ==================================================================
    def request_approval(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        if self._approval is None:
            return {"status": "no_gate", "verdict": "UNKNOWN"}
        try:
            v = self._approval.evaluate(opportunity=opp)
        except Exception as exc:                                     # noqa
            return {"status": "error", "error": str(exc)}
        return {"status": "evaluated", "verdict": str(v)}

    # ==================================================================
    # Phase I — rollback plan
    # ==================================================================
    def build_rollback(self, route: Dict[str, Any]) -> Dict[str, Any]:
        # For flash-loan atomic routes rollback is intrinsic (the whole
        # bundle reverts). We still record the intended state.
        return {
            "strategy": "atomic_revert",
            "notes": ("Flash-loan atomic bundle — any hop failure reverts "
                       "the entire transaction. Contract-level revert is "
                       "the only failure mode."),
            "hop_count": route.get("hop_count", 0),
            "explicit_compensation_needed": False,
        }

    # ==================================================================
    # Phase J — audit evidence
    # ==================================================================
    async def record_audit_evidence(
        self, opp: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        evidence_id = f"evidence_{uuid.uuid4().hex[:10]}"
        payload = {"evidence_id": evidence_id, "opp_id": opp.get("opp_id"),
                    "at": _iso(), "result_keys": list(result.keys())}
        if self._mid is not None:
            try:
                await self._mid.write_opportunity_event(
                    opp_id=opp.get("opp_id") or evidence_id,
                    event_type="flashloan.operator.journey.evidence",
                    payload={"evidence_id": evidence_id,
                              "journey_summary": {
                                  "route_id": result["route"]["route_id"],
                                  "hop_count": result["route"]["hop_count"],
                                  "ready_for_signing": False,
                                  "ready_for_broadcast": False,
                                  "clipped_notional_usd":
                                      result["capital_plan"][
                                          "clipped_notional_usd"],
                                  "flash_loan_fee_usd":
                                      result["simulation"]["fee_usd"],
                              }})
            except Exception as exc:                                 # noqa
                logger.exception("audit evidence write failed: %s", exc)
        return payload

    # ==================================================================
    # Orchestrator
    # ==================================================================
    async def run(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        qualified = self.qualify(opp)
        if not qualified["qualified"]:
            return {"qualified": qualified, "aborted": True,
                    "reason": "did_not_qualify",
                    "ready_for_signing": False,
                    "elapsed_ms": round((time.time() - t0) * 1000, 2)}
        route = self.build_route(opp)
        capital = self.estimate_capital(opp)
        simulation = self.simulate_flash_loan(opp, capital)
        tx_plan = self.build_transactions(opp, route)
        exec_plan = self.plan_execution(opp, route, capital)
        safety = self.validate_safety(opp, capital)
        approval = self.request_approval(opp)
        rollback = self.build_rollback(route)

        result: Dict[str, Any] = {
            "qualified": qualified,
            "route": route,
            "capital_plan": capital,
            "simulation": simulation,
            "tx_plan": tx_plan,
            "execution_plan": exec_plan,
            "safety_result": safety,
            "approval_result": approval,
            "rollback_plan": rollback,
            "ready_for_signing": False,       # ← invariant for v2.6.0
            "ready_for_broadcast": False,     # ← invariant for v2.6.0
        }
        result["audit_evidence"] = await self.record_audit_evidence(opp, result)
        result["elapsed_ms"] = round((time.time() - t0) * 1000, 2)
        return result


def _quote_asset(symbol: str) -> str:
    if "/" in symbol:
        return symbol.split("/", 1)[1]
    return "USDC"


__all__ = ["FlashLoanOperatorJourney"]
