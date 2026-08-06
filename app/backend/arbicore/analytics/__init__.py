"""Opportunity Decision Analytics — canonical rejection taxonomy (v2.11.10).

Every EvidenceBundle produced by the Paper Validation pipeline is
mapped into a fixed rejection *category* + *sub-code* so operator
analytics can aggregate honestly across scanner families, time
windows and pipeline versions.

Design axioms:

1. **Immutable input.**  We NEVER edit EvidenceBundles — the taxonomy
   is a pure function of `(outcome, outcome_reason, stages[])`.
2. **Closed set.**  Every category is a member of :class:`RejectionCategory`.
   The catch-all is ``OTHER`` (never ``None``) so aggregations don't
   silently drop rows.
3. **Sub-codes are opaque strings.**  They may be free-form (extracted
   from the pipeline's stage messages) but never mixed across
   categories.
4. **Stage attribution.**  The *first* failing pipeline stage is the
   attributing stage, matching how the pipeline itself decides.

The mapper is fed the whole EvidenceBundle so the taxonomy can
evolve without re-shipping the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class RejectionCategory(str, Enum):
    """Closed set of rejection dimensions the operator dashboard groups by."""

    ROUTE          = "ROUTE"           # quote failure, no hops, no path
    LIQUIDITY      = "LIQUIDITY"       # under-liquid pool
    GAS            = "GAS"             # gas estimation failed / gas > profit
    PROFITABILITY  = "PROFITABILITY"   # net expected value below threshold
    SLIPPAGE       = "SLIPPAGE"        # expected slippage too large
    FEES           = "FEES"            # venue / platform fees dominate
    POLICY         = "POLICY"          # kill-switch / mode / capital cap
    CERTIFICATION  = "CERTIFICATION"   # flash-loan certifier vetoed
    SIMULATION     = "SIMULATION"      # eth_call / heuristic sim reverted
    LATENCY        = "LATENCY"         # stage or e2e latency exceeded
    RISK           = "RISK"            # safety / risk score gate
    CONFIDENCE     = "CONFIDENCE"      # confidence score floor
    OBSERVE_ONLY   = "OBSERVE_ONLY"    # meta: pipeline mode gated (not real rejection)
    EXECUTABLE     = "EXECUTABLE"      # meta: not a rejection, listed for aggregation parity
    OTHER          = "OTHER"


#: Stages the pipeline emits, in the order it runs them.  Used to
#: pick the "attributing stage" (first failing stage).
CANONICAL_STAGE_ORDER: Tuple[str, ...] = (
    "observe_only",
    "quote",
    "liquidity",
    "gas",
    "profit",
    "policy",
    "certification",
    "simulate",
    "decision",
)


#: Direct stage → category attribution.
STAGE_TO_CATEGORY: Dict[str, RejectionCategory] = {
    "observe_only":  RejectionCategory.OBSERVE_ONLY,
    "quote":         RejectionCategory.ROUTE,
    "liquidity":     RejectionCategory.LIQUIDITY,
    "gas":           RejectionCategory.GAS,
    "profit":        RejectionCategory.PROFITABILITY,
    "policy":        RejectionCategory.POLICY,
    "certification": RejectionCategory.CERTIFICATION,
    "simulate":      RejectionCategory.SIMULATION,
}


#: Keyword mapping so `outcome_reason` free text can be classified when
#: the stages array is missing / thin.  Ordered — first match wins.
_KEYWORD_RULES: List[Tuple[Tuple[str, ...], RejectionCategory]] = [
    (("no swap_hops", "no route", "unroutable"),      RejectionCategory.ROUTE),
    (("under-liquid", "insufficient liquidity",
      "pool depth"),                                  RejectionCategory.LIQUIDITY),
    (("gas cost", "gas exceeds", "gas budget"),       RejectionCategory.GAS),
    (("net profit", "unprofitable", "loss",
      "after_gas"),                                   RejectionCategory.PROFITABILITY),
    (("slippage",),                                   RejectionCategory.SLIPPAGE),
    (("fee",),                                        RejectionCategory.FEES),
    (("kill switch", "kill-switch", "policy",
      "capital cap"),                                 RejectionCategory.POLICY),
    (("certifier", "certification"),                  RejectionCategory.CERTIFICATION),
    (("simulation reverted", "sim reverted",
      "eth_call revert"),                             RejectionCategory.SIMULATION),
    (("latency", "timeout"),                          RejectionCategory.LATENCY),
    (("risk", "safety"),                              RejectionCategory.RISK),
    (("confidence",),                                 RejectionCategory.CONFIDENCE),
    (("mode is observe",),                            RejectionCategory.OBSERVE_ONLY),
]


@dataclass(frozen=True)
class DecisionRecord:
    """Frozen analytical projection of a single EvidenceBundle.

    Constructed lazily on demand — never persisted separately.
    """

    validation_id: Optional[str]
    opportunity_id: str
    scanner_family: Optional[str]
    strategy: Optional[str]
    mode: Optional[str]
    outcome: str
    executable: bool
    category: str                       # RejectionCategory.value
    attributing_stage: Optional[str]
    reason_text: str
    sub_code: Optional[str]
    stage_failures: List[Dict[str, Any]] = field(default_factory=list)
    stage_durations_ms: Dict[str, float] = field(default_factory=dict)
    e2e_duration_ms: float = 0.0
    created_at: Optional[str] = None
    pipeline_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validation_id":       self.validation_id,
            "opportunity_id":      self.opportunity_id,
            "scanner_family":      self.scanner_family,
            "strategy":            self.strategy,
            "mode":                self.mode,
            "outcome":             self.outcome,
            "executable":          self.executable,
            "category":            self.category,
            "attributing_stage":   self.attributing_stage,
            "reason_text":         self.reason_text,
            "sub_code":            self.sub_code,
            "stage_failures":      list(self.stage_failures),
            "stage_durations_ms":  dict(self.stage_durations_ms),
            "e2e_duration_ms":     self.e2e_duration_ms,
            "created_at":          self.created_at,
            "pipeline_action":     self.pipeline_action,
        }


def _classify_by_keywords(reason: str) -> RejectionCategory:
    lowered = (reason or "").lower()
    if not lowered:
        return RejectionCategory.OTHER
    for keywords, cat in _KEYWORD_RULES:
        for kw in keywords:
            if kw in lowered:
                return cat
    return RejectionCategory.OTHER


def _extract_sub_code(stage_name: Optional[str], reason: str) -> Optional[str]:
    """Best-effort sub-code — the first significant token in the reason."""
    if not reason:
        return None
    # Common patterns: 'net=50 gas=60 after_gas=-10' → 'unprofitable_after_gas'
    lowered = reason.lower()
    if "after_gas" in lowered and ("-" in reason or "neg" in lowered):
        return "negative_after_gas"
    if "no swap_hops" in lowered:
        return "no_hops"
    if "no route" in lowered:
        return "no_route"
    if "under-liquid" in lowered:
        return "under_liquid_pool"
    if "kill switch" in lowered or "kill-switch" in lowered:
        return "kill_switch"
    if "capital cap" in lowered:
        return "capital_cap"
    if "simulation reverted" in lowered:
        return "revert"
    # Fallback — first 32 chars, cleaned.
    trimmed = reason.strip().split(".")[0][:64]
    return trimmed.replace(" ", "_").lower() or None


def classify_evidence(doc: Dict[str, Any]) -> DecisionRecord:
    """Map a raw EvidenceBundle document into a :class:`DecisionRecord`.

    ``doc`` is expected to be the raw Mongo doc shape (dict).  All
    fields are optional — missing values produce an OTHER-category
    record so the analytics never silently drop data.
    """
    outcome  = str(doc.get("outcome") or "UNKNOWN")
    reason   = str(doc.get("outcome_reason") or "")
    stages   = list(doc.get("stages") or [])
    action   = doc.get("pipeline_action")

    executable = (outcome == "EXECUTABLE")

    # 1. Find attributing stage — the first failing stage (or the last
    #    completed one for EXECUTABLE).
    attributing: Optional[str] = None
    for s in stages:
        if s.get("ok") is False:
            attributing = str(s.get("stage") or s.get("name") or "").strip() or None
            if not reason:
                reason = str(s.get("failure_reason") or s.get("detail") or "")
            break
    if attributing is None and stages:
        attributing = str(stages[-1].get("stage") or stages[-1].get("name") or "").strip() or None

    # 2. Category attribution — stage first, then keyword-fallback.
    if executable:
        category = RejectionCategory.EXECUTABLE
    elif attributing and attributing in STAGE_TO_CATEGORY:
        category = STAGE_TO_CATEGORY[attributing]
        # Refinement: quote stage might be a legitimate ROUTE failure
        # or an upstream mode issue; check.
        if attributing == "observe_only":
            category = RejectionCategory.OBSERVE_ONLY
    else:
        category = _classify_by_keywords(reason)

    # 3. Stage durations for bottleneck reporting.
    durations: Dict[str, float] = {}
    e2e = 0.0
    stage_failures: List[Dict[str, Any]] = []
    for s in stages:
        name = str(s.get("stage") or s.get("name") or "").strip()
        if not name:
            continue
        dur = s.get("duration_ms")
        if dur is not None:
            try:
                dur_f = float(dur)
                durations[name] = max(durations.get(name, 0.0), dur_f)
                e2e += dur_f
            except (TypeError, ValueError):
                pass
        if s.get("ok") is False:
            stage_failures.append({
                "stage":  name,
                "reason": str(s.get("failure_reason") or s.get("detail") or ""),
            })

    return DecisionRecord(
        validation_id=doc.get("validation_id"),
        opportunity_id=str(doc.get("opportunity_id") or ""),
        scanner_family=doc.get("scanner_family"),
        strategy=doc.get("strategy"),
        mode=doc.get("mode"),
        outcome=outcome,
        executable=executable,
        category=category.value,
        attributing_stage=attributing,
        reason_text=reason,
        sub_code=_extract_sub_code(attributing, reason),
        stage_failures=stage_failures,
        stage_durations_ms=durations,
        e2e_duration_ms=e2e,
        created_at=doc.get("created_at"),
        pipeline_action=action,
    )
