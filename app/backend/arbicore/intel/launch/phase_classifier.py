"""PhaseClassifier — heuristic 7-stage Solana launch lifecycle classifier.

REUSE WITH REFINEMENT of `archive/backend/investor/phases.py`. Refinements:
  - Decoupled from legacy ``self.repo`` (took signals via repo.list_signals).
    The classifier is now a pure synchronous function over already-fetched
    token + signals data. The D-4.5 LaunchArbitrageScanner is responsible
    for fetching signals before calling.
  - Sequence-aware nudge layer is now optional and takes patterns +
    sequences as caller-provided arguments — no DB coupling at this wave.
  - Returns a typed ``PhaseResult`` (dataclass) so callers consume a stable
    shape regardless of repo-mocking patterns.

Discipline:
  - INV-1: returns intelligence evidence ONLY (never DiscoveryCandidate /
    CanonicalOpportunity).
  - INV-2: does not import EmissionBus, does not call ``.emit()``.
  - Pure-compute, side-effect free, deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


PHASE_TAGS = (
    "stealth_accumulation",
    "early_momentum",
    "pre_migration",
    "retail_discovery",
    "momentum_expansion",
    "overheated_risk",
    "liquidity_exhaustion",
)


@dataclass
class PhaseResult:
    """Evidence-only output. NEVER a DiscoveryCandidate/CanonicalOpportunity."""

    phase: str
    phase_confidence: float
    rationale: List[str] = field(default_factory=list)
    sequence_match: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "phase": self.phase,
            "phase_confidence": self.phase_confidence,
            "rationale": list(self.rationale),
        }
        if self.sequence_match:
            out["sequence_match"] = self.sequence_match
        return out


class PhaseClassifier:
    """Stateless 7-stage Solana launch classifier."""

    def __init__(self) -> None:
        pass  # no repo coupling

    def classify(self,
                 token: Dict[str, Any],
                 signals: Optional[List[Dict[str, Any]]] = None,
                 ) -> PhaseResult:
        signals = signals or []
        cats = [s.get("category") for s in signals]
        titles_lower = [(s.get("title") or "").lower() for s in signals]

        score = float(token.get("score") or 0)
        score_delta = float(token.get("score_delta_24h") or 0)
        liq = float(token.get("liquidity_usd") or 0)
        vol_24 = float(token.get("volume_h24") or 0)
        holders = int(token.get("holders") or 0)
        age_h = float(token.get("age_hours") or 0)
        price_chg_24 = float(token.get("price_change_24h") or 0)
        launchpad_id = (token.get("launchpad_id") or "").lower()

        smart_money_count = sum(1 for c in cats if c == "smart_money")
        social_count = sum(1 for c in cats if c == "social")
        momentum_count = sum(1 for c in cats if c == "momentum")
        retail_fomo = sum(1 for t in titles_lower if "retail fomo" in t)
        liquidity_drains = sum(
            1 for t in titles_lower
            if "liquidity" in t and ("drain" in t or "pulled" in t)
        )
        whale_rotations = sum(1 for t in titles_lower if "whale rotation" in t)

        rationale: List[str] = []

        # ---- LIQUIDITY EXHAUSTION (precedence: risk-off first) ----
        if (score_delta < -8 or liquidity_drains >= 1
                or (liq > 0 and liq < 4_000)):
            rationale.append(f"score Δ24h {score_delta:+.1f} · LP ${liq:,.0f}")
            if liquidity_drains:
                rationale.append(f"{liquidity_drains} liquidity drain alerts")
            return PhaseResult("liquidity_exhaustion", 0.78, rationale)

        # ---- OVERHEATED RISK ----
        if (price_chg_24 > 90
                and (retail_fomo or social_count >= 2 or momentum_count >= 2)):
            rationale.append(
                f"price +{price_chg_24:.0f}% 24h with broad retail signal mix"
            )
            if retail_fomo:
                rationale.append(f"{retail_fomo} retail-fomo signals")
            return PhaseResult("overheated_risk", 0.74, rationale)

        # ---- PRE-MIGRATION (Pump.fun specific) ----
        if "pump" in launchpad_id and 35_000 <= liq <= 80_000 and age_h < 72:
            rationale.append(
                f"pump.fun token approaching Raydium migration (LP ${liq:,.0f})"
            )
            if smart_money_count:
                rationale.append(f"{smart_money_count} smart-money entries")
            return PhaseResult("pre_migration", 0.82, rationale)

        # ---- STEALTH ACCUMULATION ----
        if (smart_money_count >= 1 and social_count == 0
                and holders < 800 and age_h < 36):
            rationale.append(
                f"{smart_money_count} smart-money entries · social visibility low"
            )
            rationale.append(f"holders {holders:,} · age {age_h:.0f}h")
            return PhaseResult("stealth_accumulation", 0.81, rationale)

        # ---- EARLY MOMENTUM ----
        if score_delta >= 4 and age_h < 48 and (smart_money_count >= 1 or score >= 65):
            rationale.append(
                f"score Δ24h +{score_delta:.1f} on a {age_h:.0f}h-old token"
            )
            if smart_money_count:
                rationale.append(f"{smart_money_count} smart-money entries")
            return PhaseResult("early_momentum", 0.76, rationale)

        # ---- RETAIL DISCOVERY ----
        if social_count >= 1 and momentum_count >= 1 and holders >= 800:
            rationale.append(
                f"social + momentum signals · holders {holders:,}"
            )
            if vol_24:
                rationale.append(f"24h volume ${vol_24:,.0f}")
            return PhaseResult("retail_discovery", 0.70, rationale)

        # ---- MOMENTUM EXPANSION ----
        if score >= 60 and score_delta > 0 and liq >= 25_000:
            rationale.append(
                f"score {score:.0f} (Δ24h +{score_delta:.1f}) · LP ${liq:,.0f}"
            )
            if whale_rotations:
                rationale.append(f"{whale_rotations} whale-rotation signals")
            return PhaseResult("momentum_expansion", 0.66, rationale)

        # ---- DEFAULT FALLBACK ----
        if smart_money_count:
            return PhaseResult(
                "stealth_accumulation", 0.55,
                [f"{smart_money_count} smart-money entries · awaiting confirmation"],
            )
        return PhaseResult(
            "early_momentum", 0.45,
            ["limited signal evidence — early-stage observation"],
        )

    # ----- sequence-aware nudge (caller-supplied data, no repo) -----

    def apply_sequence_nudge(self, base: PhaseResult,
                              token_sequences: List[Dict[str, Any]],
                              learned_patterns: List[Dict[str, Any]],
                              *, min_support: int = 3,
                              max_nudge: float = 0.08,
                              cap: float = 0.95,
                              ) -> PhaseResult:
        """Pure function — caller fetches sequences + patterns.

        Heuristic baseline ALWAYS leads. The sequence layer only:
          - adds a `sequence_match` block
          - nudges `phase_confidence` upward by ≤ max_nudge, capped at cap
          - appends ONE rationale line — never overwrites

        Skipped silently when input data is insufficient.
        """
        if not token_sequences or not learned_patterns:
            return base
        kinds_seqs: List[tuple] = []
        for s in token_sequences:
            ks = tuple(e["kind"] for e in (s.get("events") or [])
                        if e.get("kind"))
            if len(ks) >= 2:
                kinds_seqs.append(ks)
        if not kinds_seqs:
            return base
        best = None
        for kinds in kinds_seqs:
            for p in learned_patterns:
                pk = tuple(p.get("kinds") or [])
                sup = int(p.get("frequency") or p.get("support") or 0)
                if len(pk) < 2 or len(pk) > len(kinds) or sup < min_support:
                    continue
                if _is_subsequence(pk, kinds):
                    wr = float(p.get("win_rate") or 0)
                    if (best is None or wr > best[0]
                            or (wr == best[0] and sup > best[1])):
                        best = (wr, sup, pk)
            if best:
                break
        if not best:
            return base
        wr, sup, pk = best
        nudge = 0.0
        if wr >= 0.60:
            nudge = min(max_nudge, (wr - 0.50) * 0.20)
        new_conf = min(cap, base.phase_confidence + nudge)
        new_rationale = list(base.rationale)
        new_rationale.append(
            f"sequence match: {' → '.join(pk)} (historical win {wr:.0%}, n={sup})"
        )
        return PhaseResult(
            phase=base.phase,
            phase_confidence=round(new_conf, 3),
            rationale=new_rationale,
            sequence_match={
                "matched": True, "pattern": list(pk),
                "win_rate": round(wr, 3), "support": sup,
            },
        )


def _is_subsequence(needle: tuple, haystack: tuple) -> bool:
    it = iter(haystack)
    return all(any(x == n for x in it) for n in needle)
