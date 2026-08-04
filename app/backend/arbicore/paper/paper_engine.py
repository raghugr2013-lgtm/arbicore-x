"""Paper Opportunity Engine — no execution ever."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..data.mid.writers import MidWriter, make_meta

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class PaperAnalysis:
    opp_id: str
    expected_profit_usd: float
    expected_gas_usd: float
    slippage_bps: float
    capital_required_usd: float
    flash_loan_cost_usd: float
    net_profit_usd: float
    risk_score: float                       # 0.0 (safe) - 1.0 (max risk)
    confidence: float                       # 0.0 - 1.0
    execution_probability: float            # 0.0 - 1.0
    expected_value_usd: float               # net * prob
    reason: Optional[str] = None
    policy_blocked: bool = False
    inputs: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "expected_profit_usd":    self.expected_profit_usd,
            "expected_gas_usd":       self.expected_gas_usd,
            "slippage_bps":           self.slippage_bps,
            "capital_required_usd":   self.capital_required_usd,
            "flash_loan_cost_usd":    self.flash_loan_cost_usd,
            "net_profit_usd":         self.net_profit_usd,
            "risk_score":             self.risk_score,
            "confidence":             self.confidence,
            "execution_probability":  self.execution_probability,
            "expected_value_usd":     self.expected_value_usd,
            "policy_blocked":         self.policy_blocked,
            "reason":                 self.reason,
            "inputs":                 self.inputs,
        }


@dataclass
class PaperEngineStats:
    analyses: int = 0
    policy_blocked: int = 0
    ev_positive: int = 0
    ev_negative: int = 0
    last_run_at: Optional[str] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analyses":       self.analyses,
            "policy_blocked": self.policy_blocked,
            "ev_positive":    self.ev_positive,
            "ev_negative":    self.ev_negative,
            "last_run_at":    self.last_run_at,
            "last_error":     self.last_error,
        }


class PaperEngine:
    """Given an opportunity payload, produce a full paper analysis
    and persist it to MID.

    Never executes anything. Never touches a wallet. Never signs.
    """

    def __init__(
        self,
        writer: MidWriter,
        *,
        kill_switch: Optional[Any] = None,
        capital_policy: Optional[Any] = None,
    ) -> None:
        self._writer = writer
        self._kill = kill_switch
        self._capital = capital_policy
        self.stats = PaperEngineStats()

    async def analyse(self, opp: Dict[str, Any]) -> PaperAnalysis:
        """Compute a paper analysis for one opportunity payload.

        ``opp`` shape (all fields optional except opp_id):
          - opp_id                (required)
          - opportunity_type
          - chain
          - expected_profit_usd
          - expected_gas_usd
          - slippage_bps
          - capital_required_usd
          - flash_loan_fee_bps
          - confidence
          - risk_score
        """
        opp_id = opp.get("opp_id")
        if not opp_id:
            raise ValueError("PaperEngine.analyse: opp_id is required")

        # Phase 8 gate
        if self._kill is not None and self._kill.is_engaged():
            self.stats.policy_blocked += 1
            self.stats.last_run_at = _now_iso()
            analysis = PaperAnalysis(
                opp_id=opp_id,
                expected_profit_usd=0.0, expected_gas_usd=0.0,
                slippage_bps=0.0, capital_required_usd=0.0,
                flash_loan_cost_usd=0.0, net_profit_usd=0.0,
                risk_score=1.0, confidence=0.0,
                execution_probability=0.0, expected_value_usd=0.0,
                policy_blocked=True,
                reason=f"kill_switch_engaged: {self._kill.reason()}",
                inputs=opp,
            )
            await self._persist(analysis)
            return analysis

        # inputs
        gross      = float(opp.get("expected_profit_usd", 0.0))
        gas        = float(opp.get("expected_gas_usd", 0.0))
        slippage   = float(opp.get("slippage_bps", 0.0))
        capital    = float(opp.get("capital_required_usd", 0.0))
        fl_bps     = float(opp.get("flash_loan_fee_bps", 0.0))
        confidence = float(opp.get("confidence", 0.5))
        risk_score = float(opp.get("risk_score", 0.5))

        # capital policy hook
        if self._capital is not None:
            try:
                capital = self._capital.clip_capital(
                    requested_usd=capital,
                    chain=opp.get("chain"),
                    opportunity_type=opp.get("opportunity_type"))
            except Exception as exc:  # noqa: BLE001
                self.stats.last_error = f"capital_policy: {exc!r}"

        # flash loan cost
        fl_cost = capital * (fl_bps / 10_000.0)
        slippage_cost = capital * (slippage / 10_000.0)
        net_profit = gross - gas - fl_cost - slippage_cost

        # execution probability — a simple monotone combination
        exec_prob = max(0.0, min(1.0,
            0.6 * confidence + 0.3 * (1.0 - risk_score)
            + 0.1 * (1.0 if net_profit > 0 else 0.0)))
        expected_value = net_profit * exec_prob

        analysis = PaperAnalysis(
            opp_id=opp_id,
            expected_profit_usd=gross, expected_gas_usd=gas,
            slippage_bps=slippage, capital_required_usd=capital,
            flash_loan_cost_usd=fl_cost, net_profit_usd=net_profit,
            risk_score=risk_score, confidence=confidence,
            execution_probability=exec_prob,
            expected_value_usd=expected_value,
            inputs=opp,
        )
        self.stats.analyses += 1
        if expected_value > 0:
            self.stats.ev_positive += 1
        else:
            self.stats.ev_negative += 1
        self.stats.last_run_at = _now_iso()
        await self._persist(analysis)
        return analysis

    async def _persist(self, analysis: PaperAnalysis) -> None:
        meta = make_meta(
            opportunity_type=analysis.inputs.get(
                "opportunity_type", "unknown"),
            chain=analysis.inputs.get("chain", "unknown"),
            execution_mode="paper",
            market_regime=analysis.inputs.get(
                "market_regime", "UNKNOWN"),
        )
        try:
            await self._writer.write_opportunity_event(
                opp_id=analysis.opp_id,
                event_type="paper.engine.analysed",
                payload=analysis.to_payload(),
                meta=meta,
            )
            await self._writer.write_decision(
                opp_id=analysis.opp_id,
                gate="paper_engine",
                verdict=("blocked" if analysis.policy_blocked
                          else ("proceed"
                                if analysis.expected_value_usd > 0
                                else "skip")),
                reason=(analysis.reason
                        or f"ev_usd={analysis.expected_value_usd:.4f}"),
                meta=meta,
            )
        except Exception as exc:  # noqa: BLE001
            self.stats.last_error = f"persist: {exc!r}"
            logger.exception("paper engine persist failed: %s", exc)
