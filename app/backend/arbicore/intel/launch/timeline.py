"""LaunchTimelineEngine — heuristic temporal investment intelligence.

REUSE WITH REFINEMENT of `archive/backend/investor/timeline.py`. The legacy
module was already a pure-derivation function; the refinement is:
  - Public class wrapper for consistent caller pattern (mirrors
    `PhaseClassifier`).
  - Returns a typed ``TimelineResult`` dataclass with the same payload
    shape as legacy plus `temporal_state_label` always derived.

Discipline:
  - INV-1 — evidence-only output; never DiscoveryCandidate / Canonical.
  - INV-2 — no EmissionBus references, no `.emit()` calls.
  - Pure function. No I/O, no LLM, no providers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


TEMPORAL_STATES = (
    "early_accumulation",
    "presale_active",
    "launching_soon",
    "migration_expected",
    "price_discovery",
    "retail_expansion",
    "overheated",
)

PRESALE_LAUNCHPADS = {"pumpfun", "pumpfun-solana", "pump.fun"}
LIVE_LAUNCHPADS = {
    "uniswap", "raydium", "pancakeswap", "jupiter",
    "pancake-ifo", "pumpswap-solana",
}

PHASE_TO_TEMPORAL = {
    "stealth_accumulation": "early_accumulation",
    "early_momentum":       "launching_soon",
    "pre_migration":        "migration_expected",
    "retail_discovery":     "retail_expansion",
    "momentum_expansion":   "price_discovery",
    "overheated_risk":      "overheated",
    "liquidity_exhaustion": None,
}

_STATE_LABELS = {
    "early_accumulation":  "Early Accumulation",
    "presale_active":      "Presale Active",
    "launching_soon":      "Launching Soon",
    "migration_expected":  "Migration Expected",
    "price_discovery":     "Price Discovery",
    "retail_expansion":    "Retail Expansion",
    "overheated":          "Overheated",
}


@dataclass
class TimelineResult:
    """Evidence-only timeline payload."""

    temporal_state: Optional[str]
    temporal_state_label: Optional[str]
    temporal_confidence: str            # 'confirmed' | 'estimated' | 'unknown'
    eta_label: Optional[str]
    eta_window_hours: Optional[List[int]]
    readiness: str
    roi_scenario: Optional[str]
    rationale: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temporal_state": self.temporal_state,
            "temporal_state_label": self.temporal_state_label,
            "temporal_confidence": self.temporal_confidence,
            "eta_label": self.eta_label,
            "eta_window_hours": self.eta_window_hours,
            "readiness": self.readiness,
            "roi_scenario": self.roi_scenario,
            "rationale": list(self.rationale),
        }


class LaunchTimelineEngine:
    """Stateless timeline derivation."""

    def derive(self,
               token: Dict[str, Any],
               intel: Dict[str, Any],
               ) -> TimelineResult:
        phase_obj = intel.get("phase") or {}
        phase = phase_obj.get("phase")
        phase_conf = float(phase_obj.get("phase_confidence") or 0)
        age_h = float(token.get("age_hours") or 0)
        launchpad = (token.get("launchpad_id") or "").lower()
        composite = float(intel.get("composite_score") or 0)
        confidence = float(intel.get("confidence_score") or 0)
        roi = intel.get("roi") or {}

        state = PHASE_TO_TEMPORAL.get(phase)
        if state == "launching_soon" and launchpad in PRESALE_LAUNCHPADS:
            state = "presale_active"

        eta_label, eta_window, temp_conf = self._infer_eta(
            state, age_h, launchpad, phase_conf,
        )
        readiness = self._readiness(phase, composite, confidence)
        roi_scenario = self._roi_scenario(
            roi.get("base_low"), roi.get("base_high"), confidence,
        )

        return TimelineResult(
            temporal_state=state,
            temporal_state_label=_STATE_LABELS.get(state) if state else None,
            temporal_confidence=temp_conf,
            eta_label=eta_label,
            eta_window_hours=eta_window,
            readiness=readiness,
            roi_scenario=roi_scenario,
            rationale=self._rationale(state, launchpad, readiness),
        )

    # ----- internal helpers ------------------------------------------------

    def _infer_eta(self, state: Optional[str], age_h: float,
                   launchpad: str, phase_conf: float,
                   ) -> Tuple[Optional[str], Optional[List[int]], str]:
        if state in ("retail_expansion", "price_discovery", "overheated"):
            return None, None, "confirmed"
        if state == "migration_expected":
            if launchpad in PRESALE_LAUNCHPADS:
                return "Migration window: 12–48h", [12, 48], "estimated"
            return "Migration window: 1–3d", [24, 72], "estimated"
        if state == "presale_active":
            return "Presale ending: 1–4d", [24, 96], "estimated"
        if state == "launching_soon":
            if age_h <= 6:
                return "Launch window: <12h", [0, 12], "estimated"
            if age_h <= 24:
                return "Launch window: 12–48h", [12, 48], "estimated"
            return "Launch window: 1–3d", [24, 72], "estimated"
        if state == "early_accumulation":
            if phase_conf >= 0.5:
                return "Window: 2–7d", [48, 168], "estimated"
            return None, None, "unknown"
        return None, None, "unknown"

    def _readiness(self, phase: Optional[str], composite: float,
                   confidence: float) -> str:
        if phase in ("overheated_risk", "liquidity_exhaustion"):
            return "live"
        if phase in ("retail_discovery", "momentum_expansion"):
            return "live"
        if phase == "pre_migration" and confidence >= 55 and composite >= 25:
            return "elevated"
        if phase == "pre_migration":
            return "developing"
        if phase == "early_momentum" and composite >= 25:
            return "developing"
        if phase == "stealth_accumulation":
            return "early"
        return "developing"

    def _roi_scenario(self, low_pct: Optional[float], high_pct: Optional[float],
                       confidence: float) -> Optional[str]:
        if low_pct is None or high_pct is None:
            return None
        mult_low = max(0.5, 1 + float(low_pct) / 100.0)
        mult_high = 1 + float(high_pct) / 100.0
        if mult_high < 1.5:
            return None
        qualifier = (
            "plausible" if confidence >= 60
            else "speculative" if confidence < 45
            else "tentative"
        )

        def _fmt(m: float) -> str:
            if m >= 10:
                return f"{int(m)}x"
            if m >= 2:
                return f"{int(round(m))}x"
            return f"{m:.1f}x"

        upper = _fmt(mult_high) + ("+" if mult_high >= 10 else "")
        return f"{_fmt(mult_low)}–{upper} scenario {qualifier}"

    def _rationale(self, state: Optional[str], launchpad: str,
                    readiness: str) -> List[str]:
        bits: List[str] = []
        if state == "migration_expected":
            bits.append("Approaching launchpad migration threshold")
        elif state == "presale_active":
            bits.append("Bonding curve still progressing")
        elif state == "launching_soon":
            bits.append("Fresh launch maturing on momentum")
        elif state == "early_accumulation":
            bits.append("Quiet accumulation — pre-discovery")
        elif state == "price_discovery":
            bits.append("Live and actively re-pricing")
        elif state == "retail_expansion":
            bits.append("Broadening retail attention")
        elif state == "overheated":
            bits.append("Late-stage; risk-off territory")
        if launchpad in PRESALE_LAUNCHPADS and state in (
            "early_accumulation", "presale_active",
            "launching_soon", "migration_expected",
        ):
            bits.append("Pre-DEX (bonding curve)")
        if readiness == "elevated":
            bits.append("Launch readiness elevated")
        elif readiness == "early":
            bits.append("Readiness early — incomplete validation")
        return bits
