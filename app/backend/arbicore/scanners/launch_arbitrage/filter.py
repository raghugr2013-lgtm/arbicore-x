"""LaunchGate1Filter + Gate 6 Rug-Risk Filter.

Pure-function gate evaluators. Each returns a typed
``GateResult`` describing pass/fail and a reason string the verifier folds
into the canonical metadata. No I/O, no EmissionBus, no canonical mutation.

Gate 1  — composite launch score + holder/smart-money minima
Gate 6  — Solana-specific rug-risk hard rejection (auth revoked / LP burn /
          top-10 concentration)

(Gates 2-5 are the universal substrate gates — Liquidity / Venue Cap /
Confidence / Provenance — they live in the existing universal filter and
are reused by the D-4.5 orchestrator.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GateResult:
    """Evidence-only gate verdict."""

    gate_id: str
    passed: bool
    reason: str
    metric_snapshot: Dict[str, Any] = field(default_factory=dict)
    rationale: List[str] = field(default_factory=list)


# ============================================================================
# Gate 1 — composite launch score
# ============================================================================

class LaunchGate1Filter:
    """Composite-score gate (D-4 family-specific Gate 1).

    Operator-tunable via ``scanner_config.launch_arb.gate_thresholds.default``
    + per-launchpad overrides.

    Inputs are intelligence-payload dicts produced by D-4.3 engines.
    """

    def __init__(self, thresholds: Dict[str, Any],
                 per_launchpad: Optional[Dict[str, Dict[str, Any]]] = None,
                 ) -> None:
        self.default = thresholds or {}
        self.per_launchpad = per_launchpad or {}

    def evaluate(self,
                  *,
                  composite_launch_score: float,
                  bonding_curve_progress_pct: float,
                  holder_count: int,
                  smart_money_entry_count: int,
                  holder_concentration_top10_pct: float,
                  confidence_score: float,
                  launchpad: Optional[str] = None,
                  ) -> GateResult:
        t = dict(self.default)
        if launchpad and launchpad in self.per_launchpad:
            t.update(self.per_launchpad[launchpad])
        snap = {
            "composite_launch_score": composite_launch_score,
            "bonding_curve_progress_pct": bonding_curve_progress_pct,
            "holder_count": holder_count,
            "smart_money_entry_count": smart_money_entry_count,
            "holder_concentration_top10_pct": holder_concentration_top10_pct,
            "confidence_score": confidence_score,
            "launchpad": launchpad,
        }
        checks = [
            (composite_launch_score >= float(t.get("min_composite_launch_score", 55.0)),
             f"composite {composite_launch_score:.0f} < min {t.get('min_composite_launch_score')}"),
            (bonding_curve_progress_pct >= float(t.get("min_bonding_curve_progress_pct", 5.0)),
             f"bonding-curve {bonding_curve_progress_pct:.1f}% < min "
             f"{t.get('min_bonding_curve_progress_pct')}%"),
            (holder_count >= int(t.get("min_holders", 25)),
             f"holders {holder_count} < min {t.get('min_holders')}"),
            (smart_money_entry_count >= int(t.get("min_smart_money_entries", 1)),
             f"smart-money entries {smart_money_entry_count} < min "
             f"{t.get('min_smart_money_entries')}"),
            (holder_concentration_top10_pct
             <= float(t.get("max_holder_concentration_top10_pct", 50.0)),
             f"top-10 {holder_concentration_top10_pct:.1f}% > max "
             f"{t.get('max_holder_concentration_top10_pct')}%"),
            (confidence_score >= float(t.get("min_confidence", 55.0)),
             f"confidence {confidence_score:.0f} < min {t.get('min_confidence')}"),
        ]
        failures = [reason for ok, reason in checks if not ok]
        passed = not failures
        return GateResult(
            gate_id="gate_1_launch_composite",
            passed=passed,
            reason=("composite gate passed" if passed
                     else "; ".join(failures)),
            metric_snapshot=snap,
            rationale=[r for ok, r in checks if ok] if passed else failures,
        )


# ============================================================================
# Gate 6 — Rug-Risk (Solana hard rejection)
# ============================================================================

class LaunchGate6RugRiskFilter:
    """Solana-specific rug-risk gate. Hard veto on any failure.

    Operator-tunable via ``scanner_config.launch_arb.rug_gate``.

    Inputs are on-chain verification facts from the future Helius RPC
    reader: ``mint_authority_revoked`` (bool from `mintAuthority == null`),
    ``freeze_authority_revoked`` (bool from `freezeAuthority == null`),
    ``lp_burned_or_locked_pct`` (float), and the holder-analytics
    ``top_10_concentration_pct``.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.cfg = config or {}

    def evaluate(self,
                  *,
                  mint_authority_revoked: bool,
                  freeze_authority_revoked: bool,
                  lp_burned_or_locked_pct: float,
                  holder_concentration_top10_pct: float,
                  ) -> GateResult:
        require_mint = bool(self.cfg.get("require_mint_authority_revoked", True))
        require_freeze = bool(self.cfg.get("require_freeze_authority_revoked", True))
        min_lp_pct = float(self.cfg.get("min_lp_burned_or_locked_pct", 80.0))
        max_conc = float(self.cfg.get("max_holder_concentration_top10_pct", 60.0))

        snap = {
            "mint_authority_revoked": mint_authority_revoked,
            "freeze_authority_revoked": freeze_authority_revoked,
            "lp_burned_or_locked_pct": lp_burned_or_locked_pct,
            "holder_concentration_top10_pct": holder_concentration_top10_pct,
        }
        failures: List[str] = []
        if require_mint and not mint_authority_revoked:
            failures.append("mint_authority NOT revoked (rug-risk)")
        if require_freeze and not freeze_authority_revoked:
            failures.append("freeze_authority NOT revoked (rug-risk)")
        if lp_burned_or_locked_pct < min_lp_pct:
            failures.append(
                f"LP burn/lock {lp_burned_or_locked_pct:.1f}% < {min_lp_pct:.0f}%"
            )
        if holder_concentration_top10_pct > max_conc:
            failures.append(
                f"top-10 concentration {holder_concentration_top10_pct:.1f}% "
                f"> max {max_conc:.0f}%"
            )

        passed = not failures
        return GateResult(
            gate_id="gate_6_launch_rug_risk",
            passed=passed,
            reason=("rug-risk gate passed" if passed
                     else "; ".join(failures)),
            metric_snapshot=snap,
            rationale=(["mint/freeze revoked", "LP secured",
                         "top-10 concentration within limit"]
                       if passed else failures),
        )
