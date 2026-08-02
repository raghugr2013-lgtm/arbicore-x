"""Cross-Chain Gates 7, 8, 9 — family-specific gates.

(Gates 2-5 are the universal substrate gates inherited automatically.)

  - Gate 7  Bridge Liveness   bridge_health/liveness + inventory + p95 latency
  - Gate 8  Chain Liveness    chain finality + congestion (source + dest)
  - Gate 9  Cross-Chain MEV   MevRiskScorer classification check

Pure-function evaluators. Each returns a ``GateResult``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...models.enums import MevRiskLevel


@dataclass
class GateResult:
    """Evidence-only gate verdict (matches D-4 GateResult shape)."""
    gate_id: str
    passed: bool
    reason: str
    metric_snapshot: Dict[str, Any] = field(default_factory=dict)
    rationale: List[str] = field(default_factory=list)


# ============================================================================
# Gate 7 — Bridge liveness
# ============================================================================

class CrossChainGate7BridgeLiveness:
    """Operator-tunable bridge-liveness gate."""

    def __init__(self, thresholds: Dict[str, Any],
                 per_bridge: Optional[Dict[str, Dict[str, Any]]] = None,
                 ) -> None:
        self.default = thresholds or {}
        self.per_bridge = per_bridge or {}

    def evaluate(self,
                  *,
                  bridge: str,
                  bridge_health_score: float,
                  bridge_liveness_score: float,
                  bridge_inventory_pct: float,
                  inbound_latency_p95_s: float,
                  ) -> GateResult:
        t = dict(self.default)
        if bridge and bridge in self.per_bridge:
            t.update(self.per_bridge[bridge])
        snap = {
            "bridge": bridge,
            "bridge_health_score": bridge_health_score,
            "bridge_liveness_score": bridge_liveness_score,
            "bridge_inventory_pct": bridge_inventory_pct,
            "inbound_latency_p95_s": inbound_latency_p95_s,
        }
        checks = [
            (bridge_health_score >= float(t.get("min_bridge_health_score", 70.0)),
             f"bridge_health {bridge_health_score:.0f} < "
             f"min {t.get('min_bridge_health_score')}"),
            (bridge_liveness_score >= float(t.get("min_bridge_liveness_score", 75.0)),
             f"bridge_liveness {bridge_liveness_score:.0f} < "
             f"min {t.get('min_bridge_liveness_score')}"),
            (bridge_inventory_pct >= float(t.get("min_bridge_inventory_pct", 30.0)),
             f"bridge_inventory {bridge_inventory_pct:.0f}% < "
             f"min {t.get('min_bridge_inventory_pct')}%"),
            (inbound_latency_p95_s <= float(t.get("max_inbound_latency_p95_s", 1800.0)),
             f"inbound_p95 {inbound_latency_p95_s:.0f}s > "
             f"max {t.get('max_inbound_latency_p95_s')}s"),
        ]
        failures = [reason for ok, reason in checks if not ok]
        passed = not failures
        return GateResult(
            gate_id="gate_7_bridge_liveness",
            passed=passed,
            reason=("bridge-liveness gate passed" if passed
                     else "; ".join(failures)),
            metric_snapshot=snap,
            rationale=[r for ok, r in checks if ok] if passed else failures,
        )


# ============================================================================
# Gate 8 — Chain liveness
# ============================================================================

class CrossChainGate8ChainLiveness:
    """Operator-tunable chain-liveness gate (source + destination chain)."""

    def __init__(self, thresholds: Dict[str, Any]) -> None:
        self.cfg = thresholds or {}

    def evaluate(self,
                  *,
                  source_chain: str,
                  destination_chain: str,
                  source_finality_s: float,
                  destination_finality_s: float,
                  source_congestion_score: float,
                  destination_congestion_score: float,
                  ) -> GateResult:
        max_congestion = float(
            self.cfg.get("max_chain_congestion_score", 80.0))
        max_finality_s = float(
            self.cfg.get("max_chain_finality_s", 1800.0))
        snap = {
            "source_chain": source_chain,
            "destination_chain": destination_chain,
            "source_chain_finality_s": source_finality_s,
            "destination_chain_finality_s": destination_finality_s,
            "source_chain_congestion_score": source_congestion_score,
            "destination_chain_congestion_score": destination_congestion_score,
        }
        failures: List[str] = []
        if source_congestion_score > max_congestion:
            failures.append(
                f"src {source_chain} congestion "
                f"{source_congestion_score:.0f} > {max_congestion:.0f}"
            )
        if destination_congestion_score > max_congestion:
            failures.append(
                f"dst {destination_chain} congestion "
                f"{destination_congestion_score:.0f} > {max_congestion:.0f}"
            )
        if source_finality_s > max_finality_s:
            failures.append(
                f"src {source_chain} finality "
                f"{source_finality_s:.0f}s > {max_finality_s:.0f}s"
            )
        if destination_finality_s > max_finality_s:
            failures.append(
                f"dst {destination_chain} finality "
                f"{destination_finality_s:.0f}s > {max_finality_s:.0f}s"
            )
        passed = not failures
        return GateResult(
            gate_id="gate_8_chain_liveness",
            passed=passed,
            reason=("chain-liveness gate passed" if passed
                     else "; ".join(failures)),
            metric_snapshot=snap,
            rationale=(["finality within limits", "congestion within limits"]
                       if passed else failures),
        )


# ============================================================================
# Gate 9 — Cross-Chain MEV
# ============================================================================

_MEV_ORDER = {MevRiskLevel.LOW: 0, MevRiskLevel.MEDIUM: 1, MevRiskLevel.HIGH: 2}


class CrossChainGate9CrossChainMev:
    """Hard veto when the MEV classification exceeds the operator cap.
    Default cap is MEDIUM (anything HIGH rejects)."""

    def __init__(self, thresholds: Dict[str, Any]) -> None:
        self.cfg = thresholds or {}

    def evaluate(self,
                  *,
                  mev_risk_level: MevRiskLevel,
                  mev_risk_label: str,
                  mev_score: float,
                  ) -> GateResult:
        cap_label = str(
            self.cfg.get("max_cross_chain_mev_risk_class", "MEDIUM")).upper()
        try:
            cap_level = MevRiskLevel(cap_label)
        except ValueError:
            cap_level = MevRiskLevel.MEDIUM
        snap = {
            "mev_risk_level": mev_risk_level.value,
            "mev_risk_label": mev_risk_label,
            "mev_score": mev_score,
            "cap": cap_level.value,
        }
        passed = _MEV_ORDER[mev_risk_level] <= _MEV_ORDER[cap_level]
        reason = ("cross-chain MEV gate passed"
                   if passed else
                   f"MEV level {mev_risk_level.value} "
                   f"exceeds cap {cap_level.value}")
        return GateResult(
            gate_id="gate_9_cross_chain_mev",
            passed=passed,
            reason=reason,
            metric_snapshot=snap,
            rationale=[reason],
        )
