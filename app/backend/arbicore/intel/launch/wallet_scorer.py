"""WalletScorer — 4-factor algorithmic wallet quality scoring.

REUSE WITH REFINEMENT of `archive/backend/intel/scoring.py` per
LEGACY_ARCHIVE_IMPORT_ASSESSMENT §2.2.2. Refinements:
  - Decoupled from legacy ``ParsedTx`` dataclass (now takes a generic
    ``WalletActivityEvent`` shape so the scorer is reusable across providers)
  - Pure-function design preserved (no side effects, deterministic outputs)
  - Returns a `dict` matching the legacy `scores` payload shape so the
    Phase C learning layer can ingest unchanged

Inputs:
  - List[WalletActivityEvent]   recent activity for the wallet
  - dict[token_addr -> age_h]   token-age context (for early-entry signal)
  - Optional[str]               curated label (boosts/penalises quality)
"""
from __future__ import annotations

import statistics
import time
from typing import Dict, List, Optional

from .signal_predicates import WalletActivityEvent

EARLY_ENTRY_THRESHOLD_HOURS = 1.0


class WalletScorer:
    """Stateless wallet scorer. Construct once; call ``compute`` many times."""

    label_boost = {
        "smart_money": 12,
        "influencer": 6,
        "whale": 8,
        "sniper": 4,
        "retail_fomo": -8,
        "rug_wallet": -25,
    }

    def __init__(self,
                 *,
                 early_entry_threshold_hours: float = EARLY_ENTRY_THRESHOLD_HOURS,
                 weight_early: float = 0.35,
                 weight_consistency: float = 0.25,
                 weight_conviction: float = 0.35,
                 baseline_score: float = 14.0,
                 ) -> None:
        self.early_threshold = early_entry_threshold_hours
        self.w_early = weight_early
        self.w_consistency = weight_consistency
        self.w_conviction = weight_conviction
        self.baseline = baseline_score

    # ----- 1. early_entry --------------------------------------------------

    def score_early_entry(self, txs: List[WalletActivityEvent],
                          token_ages_hours: Dict[str, float]) -> float:
        buys = [t for t in txs if t.action in ("buy", "swap")]
        if not buys:
            return 0.0
        early = 0
        for t in buys:
            age = token_ages_hours.get(t.token_address)
            if age is not None and age <= self.early_threshold:
                early += 1
        rate = early / len(buys)
        score = rate * 80.0
        if early >= 5:
            score = min(100.0, score + 18.0)
        elif early >= 2:
            score = min(100.0, score + 8.0)
        return round(score, 1)

    # ----- 2. consistency --------------------------------------------------

    def score_consistency(self, txs: List[WalletActivityEvent]) -> float:
        if len(txs) < 3:
            return 30.0
        txs_sorted = sorted(txs, key=lambda t: t.timestamp)
        gaps = [
            (txs_sorted[i].timestamp - txs_sorted[i - 1].timestamp) / 3600.0
            for i in range(1, len(txs_sorted))
        ]
        if not gaps:
            return 30.0
        median = statistics.median(gaps)
        try:
            std = statistics.stdev(gaps) if len(gaps) > 1 else 0
        except statistics.StatisticsError:
            std = 0
        if median > 168:  # > 1 week between txs
            return 20.0
        score = 100 - min(60, std * 2.0) - min(20, median * 0.5)
        return round(max(0.0, min(100.0, score)), 1)

    # ----- 3. conviction ---------------------------------------------------

    def score_conviction(self, txs: List[WalletActivityEvent]) -> float:
        buys = [t for t in txs
                if t.action in ("buy", "swap") and (t.amount_usd or 0) > 0]
        if not buys:
            return 0.0
        avg = statistics.mean(t.amount_usd for t in buys)
        if avg > 50_000:
            score = 95.0
        elif avg > 10_000:
            score = 80.0
        elif avg > 2_000:
            score = 60.0
        elif avg > 500:
            score = 40.0
        elif avg > 100:
            score = 22.0
        else:
            score = 8.0
        # DCA bonus
        by_token: Dict[str, List[float]] = {}
        for t in buys:
            if not t.token_address:
                continue
            by_token.setdefault(t.token_address, []).append(t.amount_usd)
        repeats = sum(1 for v in by_token.values() if len(v) >= 2)
        return round(min(100.0, score + min(15, repeats * 4)), 1)

    # ----- 4. weighted quality (composite) ---------------------------------

    def score_quality(self, *, early_entry: float, consistency: float,
                      conviction: float, label: Optional[str]) -> float:
        base = (early_entry * self.w_early
                + consistency * self.w_consistency
                + conviction * self.w_conviction)
        boost = self.label_boost.get(label or "", 0)
        return round(max(0.0, min(100.0, base + boost + self.baseline)), 1)

    # ----- top-level --------------------------------------------------------

    def compute(self, *, txs: List[WalletActivityEvent],
                token_ages_hours: Dict[str, float],
                label: Optional[str] = None) -> Dict[str, float]:
        early = self.score_early_entry(txs, token_ages_hours)
        consistency = self.score_consistency(txs)
        conviction = self.score_conviction(txs)
        quality = self.score_quality(
            early_entry=early, consistency=consistency,
            conviction=conviction, label=label,
        )
        return {
            "wallet_quality": quality,
            "early_entry": early,
            "consistency": consistency,
            "conviction": conviction,
            "overall": quality,
            "computed_at": int(time.time()),
        }
