"""HolderAnalytics — concentration / churn / age-weighted holder counts.

REBUILD FRESH (no legacy equivalent). Per D-4 Authorization Package §2.2,
this module computes evidence-only holder-distribution intelligence the
LaunchOpportunityVerifier (D-4.4) will consume for rug-risk gating
(Operator Decision 1: Helius `getTokenLargestAccounts` reads).

Inputs:
  - holder rows: each row has {address, balance, last_seen_ts}
  - total_supply: token total supply (used for share calculation)

Outputs (all evidence-only):
  - `top_n_concentration_pct` for n ∈ {1, 5, 10, 20}
  - `dispersion_score` (0..100, inverse of concentration)
  - `whale_count` (holders ≥ 1% of supply)
  - `dust_holder_count` (holders < 0.001% — discarded for cleanliness)
  - `age_weighted_holder_count` (decays by hours-since-last-seen)
  - `churn_signal` ('stable' | 'moderate' | 'turning_over') if a prior
    snapshot is supplied

Discipline:
  - INV-1 — evidence only; never DiscoveryCandidate / Canonical.
  - INV-2 — no EmissionBus references.
  - Pure compute, no I/O, deterministic.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


# ============================================================================
# Output type
# ============================================================================

@dataclass
class HolderSnapshot:
    """Per-token evidence payload. NEVER a DiscoveryCandidate/Canonical."""

    token_id: str
    holder_count: int
    total_supply_raw: float
    top_1_concentration_pct: float
    top_5_concentration_pct: float
    top_10_concentration_pct: float
    top_20_concentration_pct: float
    dispersion_score: float                  # 0..100 (higher = healthier)
    whale_count: int                          # ≥ 1% of supply
    dust_holder_count: int                    # < 0.001% of supply
    age_weighted_holder_count: float
    churn_signal: Optional[str] = None        # set only when prior given
    churn_delta_pct: Optional[float] = None
    rationale: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "holder_count": self.holder_count,
            "total_supply_raw": self.total_supply_raw,
            "top_1_concentration_pct": self.top_1_concentration_pct,
            "top_5_concentration_pct": self.top_5_concentration_pct,
            "top_10_concentration_pct": self.top_10_concentration_pct,
            "top_20_concentration_pct": self.top_20_concentration_pct,
            "dispersion_score": self.dispersion_score,
            "whale_count": self.whale_count,
            "dust_holder_count": self.dust_holder_count,
            "age_weighted_holder_count": self.age_weighted_holder_count,
            "churn_signal": self.churn_signal,
            "churn_delta_pct": self.churn_delta_pct,
            "rationale": list(self.rationale),
        }


# ============================================================================
# Analyser
# ============================================================================

class HolderAnalytics:
    """Stateless analyser.

    Holder row shape::
        {"address": str, "balance": float, "last_seen_ts": Optional[float]}

    Holders with ``balance <= 0`` are discarded. Holders with
    balance below the dust threshold (default 0.001% of supply) are
    counted into ``dust_holder_count`` but excluded from concentration
    percentile math to prevent rounding noise.
    """

    def __init__(self,
                 *,
                 dust_share_threshold: float = 0.00001,    # 0.001%
                 whale_share_threshold: float = 0.01,      # 1%
                 age_halflife_hours: float = 168.0,        # 7 days
                 ) -> None:
        self.dust_threshold = dust_share_threshold
        self.whale_threshold = whale_share_threshold
        self.age_halflife = age_halflife_hours

    # ------------------------------------------------------------ public

    def analyse(self, *,
                 token_id: str,
                 holders: Iterable[Dict[str, Any]],
                 total_supply: float,
                 prior_snapshot: Optional["HolderSnapshot"] = None,
                 now_ts: Optional[float] = None,
                 ) -> HolderSnapshot:
        rows = [
            {
                "address": h.get("address"),
                "balance": float(h.get("balance") or 0),
                "last_seen_ts": h.get("last_seen_ts"),
            }
            for h in holders
            if (h.get("address")
                 and isinstance(h.get("balance"), (int, float))
                 and h.get("balance") > 0)
        ]
        n_total = len(rows)
        if total_supply <= 0:
            return _empty_snapshot(token_id, n_total,
                                     "total_supply non-positive")

        # Dust / whale partition
        dust_count = sum(1 for r in rows
                          if (r["balance"] / total_supply) < self.dust_threshold)
        non_dust = [r for r in rows
                     if (r["balance"] / total_supply) >= self.dust_threshold]

        whale_count = sum(1 for r in non_dust
                           if (r["balance"] / total_supply)
                               >= self.whale_threshold)

        # Concentration
        sorted_balances = sorted(
            (r["balance"] for r in non_dust),
            reverse=True,
        )

        def _conc(n: int) -> float:
            top = sum(sorted_balances[:n])
            return round(top / total_supply * 100.0, 2)

        c1, c5, c10, c20 = _conc(1), _conc(5), _conc(10), _conc(20)

        # Dispersion: inverse of top-10 concentration, smoothed
        dispersion = max(0.0, min(100.0, round(100.0 - c10, 2)))

        # Age-weighted holder count (exp half-life decay)
        now = now_ts if now_ts is not None else time.time()
        age_weighted = 0.0
        for r in non_dust:
            lst = r.get("last_seen_ts")
            if lst is None:
                age_weighted += 1.0
                continue
            hours = max(0.0, (now - float(lst)) / 3600.0)
            decay = 0.5 ** (hours / self.age_halflife)
            age_weighted += decay
        age_weighted = round(age_weighted, 2)

        rationale = _build_rationale(c10, dispersion, whale_count,
                                       len(non_dust))

        churn_signal = None
        churn_delta_pct = None
        if prior_snapshot is not None:
            prev_n = prior_snapshot.holder_count
            if prev_n > 0:
                delta_pct = round(
                    (n_total - prev_n) / prev_n * 100.0, 1
                )
                churn_delta_pct = delta_pct
                if abs(delta_pct) < 5:
                    churn_signal = "stable"
                elif abs(delta_pct) < 25:
                    churn_signal = "moderate"
                else:
                    churn_signal = "turning_over"
                rationale.append(
                    f"Δ holders {delta_pct:+.1f}% vs prior snapshot"
                )

        return HolderSnapshot(
            token_id=token_id,
            holder_count=n_total,
            total_supply_raw=total_supply,
            top_1_concentration_pct=c1,
            top_5_concentration_pct=c5,
            top_10_concentration_pct=c10,
            top_20_concentration_pct=c20,
            dispersion_score=dispersion,
            whale_count=whale_count,
            dust_holder_count=dust_count,
            age_weighted_holder_count=age_weighted,
            churn_signal=churn_signal,
            churn_delta_pct=churn_delta_pct,
            rationale=rationale,
        )


# ============================================================================
# helpers
# ============================================================================

def _build_rationale(c10: float, dispersion: float,
                       whale_count: int, n_holders: int) -> List[str]:
    out: List[str] = []
    if c10 >= 80:
        out.append(f"top-10 hold {c10:.1f}% — heavy concentration risk")
    elif c10 >= 50:
        out.append(f"top-10 hold {c10:.1f}% — meaningful concentration")
    elif c10 >= 25:
        out.append(f"top-10 hold {c10:.1f}% — moderate distribution")
    else:
        out.append(f"top-10 hold {c10:.1f}% — broad distribution")
    if whale_count:
        out.append(f"{whale_count} whale(s) ≥1% supply")
    if n_holders >= 1_000:
        out.append(f"{n_holders:,} non-dust holders — broad base")
    elif n_holders < 100:
        out.append(f"only {n_holders} non-dust holders — narrow base")
    return out


def _empty_snapshot(token_id: str, n_total: int, reason: str) -> HolderSnapshot:
    return HolderSnapshot(
        token_id=token_id,
        holder_count=n_total,
        total_supply_raw=0,
        top_1_concentration_pct=0.0,
        top_5_concentration_pct=0.0,
        top_10_concentration_pct=0.0,
        top_20_concentration_pct=0.0,
        dispersion_score=0.0,
        whale_count=0,
        dust_holder_count=0,
        age_weighted_holder_count=0.0,
        rationale=[reason],
    )
