"""7 wallet-derived hint predicates — emit DiscoveryCandidate ONLY.

PARTIAL HARVEST of `archive/backend/engine/wallet_signals.py` per
LEGACY_ARCHIVE_IMPORT_ASSESSMENT §2.2.2 (rule predicates only — the
legacy bus pub/sub is stripped; INV-2 strictly enforced).

Legacy semantics preserved:
  1. SMART_MONEY_ENTRY    quality wallet bought tracked token
  2. CLUSTER_BUYING       ≥3 wallets from same cluster bought token in window
  3. EARLY_ACCUMULATION   ≥3 quality wallets entered within first hour
  4. STEALTH_ALPHA        quality wallet entry on socially silent token
  5. HIGH_CONVICTION_BUY  single buy ≥ threshold by any wallet
  6. RETAIL_FOMO          surge of unique buyers, few quality wallets
  7. WHALE_ROTATION       quality wallet sold A then bought B within window

INV-1: every predicate emits ``DiscoveryCandidate`` rows; the verifier at
D-4.4 owns the only canonical mapping.
INV-2: this module does not import EmissionBus and does not call
``.emit()``. AST-audited.
INV-3: ``provenance_of_hint`` is REAL but ``hint_source`` is
``launch_intel:<predicate>`` — telemetry-only. The verifier re-derives
``source_data_quality`` from the per-leg on-chain RPC source.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from ...models.discovery import DiscoveryCandidate, make_candidate_id
from ...models.enums import OpportunityType


# ============================================================================
# Input shapes
# ============================================================================

@dataclass
class WalletActivityEvent:
    """Normalised activity row consumed by predicates AND WalletScorer."""

    wallet: str
    token_id: str               # canonical "<chain>:<addr>"
    token_address: str          # raw token mint / contract addr
    token_symbol: str
    chain: str
    action: str                 # "buy" | "sell" | "swap"
    timestamp: float            # unix seconds
    amount_usd: float = 0.0
    is_early_entry: bool = False


@dataclass
class SignalPredicateInput:
    """Per-cycle input bundle for the predicate suite."""

    activity: List[WalletActivityEvent]
    wallet_profiles: Dict[str, Dict[str, Any]]    # address -> profile dict
    token_context: Dict[str, Dict[str, Any]]      # token_id -> token doc
    cluster_membership: Dict[str, str]            # wallet -> cluster_id
    # Predicate-level config knobs (operator-tunable per scanner_config)
    cluster_buying_window_s: int = 300
    cluster_buying_min_size: int = 3
    early_accumulation_min_quality: int = 3
    high_conviction_threshold_usd: float = 15_000.0
    retail_fomo_min_buyers: int = 15
    whale_rotation_window_minutes: int = 15


# ============================================================================
# Helpers
# ============================================================================

def _bucket_sid(*parts: str, bucket_seconds: int = 600) -> str:
    """Sticky-window dedupe id — same fingerprint inside `bucket_seconds`."""
    bucket = int(time.time() // bucket_seconds)
    blob = (":".join(parts) + f":{bucket}").encode()
    return hashlib.md5(blob).hexdigest()[:16]


def _is_quality(profile: Optional[Dict[str, Any]]) -> bool:
    if not profile:
        return False
    if profile.get("label") in ("smart_money", "whale", "influencer"):
        return True
    return ((profile.get("scores") or {}).get("wallet_quality") or 0) >= 60


def _has_low_social(token: Dict[str, Any]) -> bool:
    info = token.get("info") or {}
    return not (info.get("telegram") or info.get("twitter") or info.get("discord"))


def _candidate(*, predicate: str, token_id: str, asset: str,
               chain: Optional[str], hint_metric: Dict[str, Any],
               reason: str, hint_observed_at: float,
               candidate_venues: Optional[List[str]] = None
               ) -> DiscoveryCandidate:
    """Build a DiscoveryCandidate with the launch-intel naming convention."""
    venues = candidate_venues or ([f"launchpad:{chain}"] if chain else [])
    cid = make_candidate_id(
        hint_source=f"launch_intel:{predicate}",
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        subject_id=token_id, asset=asset,
        candidate_venues=venues,
        hint_observed_at=hint_observed_at,
    )
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        hint_source=f"launch_intel:{predicate}",
        hint_observed_at=hint_observed_at,
        subject_id=token_id,
        asset=asset,
        candidate_venues=venues,
        hint_metric=hint_metric,
        reason=reason,
    )


# ============================================================================
# 1. SMART_MONEY_ENTRY
# ============================================================================

def smart_money_entry(inp: SignalPredicateInput) -> List[DiscoveryCandidate]:
    now = time.time()
    out: List[DiscoveryCandidate] = []
    for a in inp.activity:
        if a.action != "buy":
            continue
        p = inp.wallet_profiles.get(a.wallet)
        if not _is_quality(p):
            continue
        label = (p or {}).get("label") or "Quality"
        chain = (inp.token_context.get(a.token_id) or {}).get("chain") or a.chain
        out.append(_candidate(
            predicate="smart_money_entry",
            token_id=a.token_id, asset=a.token_symbol, chain=chain,
            hint_observed_at=now,
            hint_metric={
                "wallet": a.wallet,
                "wallet_label": label,
                "amount_usd": a.amount_usd,
                "wallet_quality": (p.get("scores") or {}).get("wallet_quality")
                                    if p else None,
            },
            reason=f"smart_money_entry:{label}:{a.wallet[:6]}",
        ))
    return out


# ============================================================================
# 2. CLUSTER_BUYING
# ============================================================================

def cluster_buying(inp: SignalPredicateInput) -> List[DiscoveryCandidate]:
    by_token: Dict[str, List[WalletActivityEvent]] = defaultdict(list)
    for a in inp.activity:
        if a.action != "buy":
            continue
        if a.wallet in inp.cluster_membership:
            by_token[a.token_id].append(a)

    out: List[DiscoveryCandidate] = []
    now = time.time()
    for tid, events in by_token.items():
        events.sort(key=lambda e: e.timestamp)
        i = 0
        n = len(events)
        while i < n:
            j = i
            cluster_ids = set()
            wallets = set()
            window_start = events[i].timestamp
            while (j < n
                   and events[j].timestamp - window_start
                   <= inp.cluster_buying_window_s):
                cluster_ids.add(inp.cluster_membership[events[j].wallet])
                wallets.add(events[j].wallet)
                j += 1
            if (len(wallets) >= inp.cluster_buying_min_size
                    and len(cluster_ids) <= 2):
                cid = next(iter(cluster_ids))
                sym = events[0].token_symbol
                out.append(_candidate(
                    predicate="cluster_buying",
                    token_id=tid, asset=sym, chain=events[0].chain,
                    hint_observed_at=now,
                    hint_metric={
                        "cluster_id": cid,
                        "wallet_count": len(wallets),
                        "window_seconds": inp.cluster_buying_window_s,
                        "wallets_sample": sorted(wallets)[:5],
                    },
                    reason=f"cluster_buying:{len(wallets)}_wallets",
                ))
            i = j if j > i else i + 1
    return out


# ============================================================================
# 3. EARLY_ACCUMULATION
# ============================================================================

def early_accumulation(inp: SignalPredicateInput) -> List[DiscoveryCandidate]:
    by_token: Dict[str, List[WalletActivityEvent]] = defaultdict(list)
    for a in inp.activity:
        if a.action != "buy" or not a.is_early_entry:
            continue
        if _is_quality(inp.wallet_profiles.get(a.wallet)):
            by_token[a.token_id].append(a)

    out: List[DiscoveryCandidate] = []
    now = time.time()
    for tid, events in by_token.items():
        if len(events) < inp.early_accumulation_min_quality:
            continue
        sym = events[0].token_symbol
        out.append(_candidate(
            predicate="early_accumulation",
            token_id=tid, asset=sym, chain=events[0].chain,
            hint_observed_at=now,
            hint_metric={
                "quality_wallet_count": len(events),
                "wallets_sample": [e.wallet for e in events[:5]],
            },
            reason=f"early_accumulation:{len(events)}_quality_wallets",
        ))
    return out


# ============================================================================
# 4. STEALTH_ALPHA
# ============================================================================

def stealth_alpha(inp: SignalPredicateInput) -> List[DiscoveryCandidate]:
    now = time.time()
    out: List[DiscoveryCandidate] = []
    for a in inp.activity:
        if a.action != "buy":
            continue
        p = inp.wallet_profiles.get(a.wallet)
        if not _is_quality(p):
            continue
        token = inp.token_context.get(a.token_id) or {}
        if not _has_low_social(token):
            continue
        out.append(_candidate(
            predicate="stealth_alpha",
            token_id=a.token_id, asset=a.token_symbol,
            chain=token.get("chain") or a.chain,
            hint_observed_at=now,
            hint_metric={
                "wallet": a.wallet,
                "wallet_label": (p or {}).get("label"),
                "socials_present": False,
            },
            reason=f"stealth_alpha:{a.wallet[:6]}",
        ))
    return out


# ============================================================================
# 5. HIGH_CONVICTION_BUY
# ============================================================================

def high_conviction_buy(inp: SignalPredicateInput) -> List[DiscoveryCandidate]:
    now = time.time()
    out: List[DiscoveryCandidate] = []
    for a in inp.activity:
        if a.action != "buy" or a.amount_usd < inp.high_conviction_threshold_usd:
            continue
        p = inp.wallet_profiles.get(a.wallet) or {}
        out.append(_candidate(
            predicate="high_conviction_buy",
            token_id=a.token_id, asset=a.token_symbol, chain=a.chain,
            hint_observed_at=now,
            hint_metric={
                "wallet": a.wallet,
                "amount_usd": a.amount_usd,
                "wallet_quality": (p.get("scores") or {}).get("wallet_quality"),
                "threshold_usd": inp.high_conviction_threshold_usd,
            },
            reason=f"high_conviction_buy:${a.amount_usd:.0f}",
        ))
    return out


# ============================================================================
# 6. RETAIL_FOMO  (negative-signal indicator)
# ============================================================================

def retail_fomo(inp: SignalPredicateInput) -> List[DiscoveryCandidate]:
    by_token: Dict[str, List[WalletActivityEvent]] = defaultdict(list)
    for a in inp.activity:
        if a.action == "buy":
            by_token[a.token_id].append(a)

    now = time.time()
    out: List[DiscoveryCandidate] = []
    for tid, events in by_token.items():
        unique_buyers = {a.wallet for a in events}
        if len(unique_buyers) < inp.retail_fomo_min_buyers:
            continue
        quality_buyers = sum(
            1 for w in unique_buyers if _is_quality(inp.wallet_profiles.get(w))
        )
        if quality_buyers > max(2, len(unique_buyers) * 0.1):
            continue  # smart money still in
        sym = events[0].token_symbol
        out.append(_candidate(
            predicate="retail_fomo",
            token_id=tid, asset=sym, chain=events[0].chain,
            hint_observed_at=now,
            hint_metric={
                "unique_buyer_count": len(unique_buyers),
                "quality_buyer_count": quality_buyers,
                "polarity": "negative",   # rug/exit-time indicator
            },
            reason=f"retail_fomo:{len(unique_buyers)}_buyers_{quality_buyers}_quality",
        ))
    return out


# ============================================================================
# 7. WHALE_ROTATION
# ============================================================================

def whale_rotation(inp: SignalPredicateInput) -> List[DiscoveryCandidate]:
    by_wallet: Dict[str, List[WalletActivityEvent]] = defaultdict(list)
    for a in inp.activity:
        by_wallet[a.wallet].append(a)

    now = time.time()
    window_s = inp.whale_rotation_window_minutes * 60
    out: List[DiscoveryCandidate] = []
    for wallet, events in by_wallet.items():
        p = inp.wallet_profiles.get(wallet)
        if not _is_quality(p):
            continue
        events.sort(key=lambda e: e.timestamp)
        for i in range(len(events) - 1):
            a, b = events[i], events[i + 1]
            if a.action != "sell" or b.action != "buy":
                continue
            if (b.timestamp - a.timestamp) > window_s:
                continue
            if a.token_id == b.token_id:
                continue
            elapsed_min = int((b.timestamp - a.timestamp) // 60)
            out.append(_candidate(
                predicate="whale_rotation",
                token_id=b.token_id, asset=b.token_symbol, chain=b.chain,
                hint_observed_at=now,
                hint_metric={
                    "wallet": wallet,
                    "sold_token_id": a.token_id,
                    "bought_token_id": b.token_id,
                    "elapsed_minutes": elapsed_min,
                },
                reason=f"whale_rotation:{a.token_symbol}->{b.token_symbol}",
            ))
    return out


# ============================================================================
# Top-level dispatch
# ============================================================================

PREDICATE_REGISTRY: Dict[str, Callable[[SignalPredicateInput],
                                       List[DiscoveryCandidate]]] = {
    "smart_money_entry":     smart_money_entry,
    "cluster_buying":        cluster_buying,
    "early_accumulation":    early_accumulation,
    "stealth_alpha":          stealth_alpha,
    "high_conviction_buy":    high_conviction_buy,
    "retail_fomo":            retail_fomo,
    "whale_rotation":         whale_rotation,
}


def evaluate_all_predicates(inp: SignalPredicateInput
                            ) -> List[DiscoveryCandidate]:
    """Run the 7 predicates and return a single deduplicated candidate list.

    INV-1: returns ``List[DiscoveryCandidate]`` only.
    """
    out: List[DiscoveryCandidate] = []
    seen: set = set()
    for name, fn in PREDICATE_REGISTRY.items():
        for c in fn(inp):
            if c.candidate_id in seen:
                continue
            seen.add(c.candidate_id)
            out.append(c)
    return out
