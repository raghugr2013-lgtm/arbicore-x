"""WalletEnrichmentOrchestrator — asyncio-only enrichment pipeline.

REBUILD FRESH per LEGACY_ARCHIVE_IMPORT_ASSESSMENT §2.2.2. The legacy
`archive/backend/intel/ingestion.py` was a monolithic APScheduler-coupled
orchestrator that called the legacy event bus. This rebuild:

  - Uses asyncio only (no APScheduler)
  - Does NOT spawn any background task at D-4.2 (the LaunchArbitrageScanner
    at D-4.5 owns the tick)
  - Does NOT call EmissionBus (INV-2). It returns DiscoveryCandidate rows
    and enriched WalletProfile updates; the scanner (D-4.5) is the only
    code that ever calls ``EmissionBus.emit()``.
  - Integrates with `arbicore/data/provenance.py` (`SOURCE_REGISTRY`) and
    `arbicore/models/category_metadata.py` (vocab keys).
  - Plug-points are typed and dependency-injected for testability:
      * `wallet_provider`   — supplies recent buyers + wallet transactions
      * `label_index`       — curated labels (per Operator Decision 4)
      * `cluster_detector`  — TimeWindowClusterDetector instance
      * `scorer`            — WalletScorer instance
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

from ...models.discovery import DiscoveryCandidate
from .cluster_detector import TimeWindowClusterDetector
from .signal_predicates import (
    SignalPredicateInput,
    WalletActivityEvent,
    evaluate_all_predicates,
)
from .wallet_profile import WalletProfile, merge_stats
from .wallet_scorer import WalletScorer

logger = logging.getLogger("arbicore.intel.launch.enrichment")


# ============================================================================
# Provider contract
# ============================================================================

class WalletProvider(Protocol):
    """Minimum surface the orchestrator expects from a wallet data provider.

    `MockWalletProvider` (tests) and the future Helius-backed provider
    (D-4.5 wiring) both satisfy this.
    """

    async def is_available(self) -> bool:
        ...

    async def recent_buyers(self, token_address: str, *, chain: str = "solana",
                            limit: int = 50) -> List[Dict[str, Any]]:
        ...

    async def wallet_transactions(self, wallet: str, *,
                                  since_ts: Optional[float] = None,
                                  limit: int = 100) -> List[Dict[str, Any]]:
        ...


# ============================================================================
# Output bundle
# ============================================================================

@dataclass
class EnrichmentResult:
    """Pure data; the orchestrator never emits, it RETURNS this."""

    profiles_updated: List[WalletProfile] = field(default_factory=list)
    clusters_detected: List[Dict[str, Any]] = field(default_factory=list)
    candidates: List[DiscoveryCandidate] = field(default_factory=list)
    provider_available: bool = False
    error: Optional[str] = None


# ============================================================================
# Orchestrator
# ============================================================================

class WalletEnrichmentOrchestrator:
    """One-shot enrichment cycle. Called by the LaunchArbitrageScanner (D-4.5).

    At D-4.2 nothing schedules `.run()` — the orchestrator is constructed
    and unit-tested but DOES NOT start any background loop.
    """

    def __init__(self, *,
                 wallet_provider: WalletProvider,
                 scorer: Optional[WalletScorer] = None,
                 cluster_detector: Optional[TimeWindowClusterDetector] = None,
                 label_index_loader: Callable[[], Dict[str, Dict[str, Any]]],
                 max_concurrent_enrichments: int = 4,
                 wallet_tx_lookback_seconds: float = 7 * 24 * 3600.0,
                 ) -> None:
        self.provider = wallet_provider
        self.scorer = scorer or WalletScorer()
        self.cluster_detector = cluster_detector or TimeWindowClusterDetector()
        self.label_index_loader = label_index_loader
        self.max_concurrent = max_concurrent_enrichments
        self.tx_lookback_s = wallet_tx_lookback_seconds

    # ------------------------------------------------------------------ public

    async def run(self, *,
                  tracked_tokens: List[Dict[str, Any]],
                  token_context: Dict[str, Dict[str, Any]],
                  ) -> EnrichmentResult:
        """One enrichment cycle.

        ``tracked_tokens`` is a list of ``{token_id, token_address, chain,
        token_symbol, age_hours}`` rows produced by the scanner from the
        DiscoveryQueue. At D-4.2 the scanner does not exist, so the caller
        in tests passes a synthetic list.
        """
        result = EnrichmentResult()

        if not await self.provider.is_available():
            result.provider_available = False
            result.error = "provider_unavailable"
            return result
        result.provider_available = True

        if not tracked_tokens:
            return result

        # 1. Gather recent buyers across all tracked tokens
        activity: List[WalletActivityEvent] = []
        wallets_seen: set = set()
        for tok in tracked_tokens:
            try:
                buyers = await self.provider.recent_buyers(
                    tok["token_address"], chain=tok.get("chain", "solana"),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("recent_buyers failed for %s: %s",
                                tok.get("token_id"), exc)
                continue
            for b in buyers:
                wallet = b.get("wallet")
                if not wallet:
                    continue
                wallets_seen.add(wallet)
                activity.append(WalletActivityEvent(
                    wallet=wallet,
                    token_id=tok["token_id"],
                    token_address=tok["token_address"],
                    token_symbol=tok.get("token_symbol", ""),
                    chain=tok.get("chain", "solana"),
                    action="buy",
                    timestamp=float(b.get("ts") or 0.0),
                    amount_usd=float(b.get("amount_usd") or 0.0),
                    is_early_entry=(
                        tok.get("age_hours") is not None
                        and tok["age_hours"] <= self.scorer.early_threshold
                    ),
                ))

        # 2. Enrich each wallet with a tx history (rate-limited via semaphore)
        sem = asyncio.Semaphore(self.max_concurrent)
        label_idx = self.label_index_loader() or {}
        token_ages_hours = {
            tok["token_address"]: float(tok.get("age_hours") or 999.0)
            for tok in tracked_tokens
        }

        async def _enrich_one(wallet: str) -> Optional[WalletProfile]:
            async with sem:
                try:
                    txs_raw = await self.provider.wallet_transactions(
                        wallet,
                        since_ts=(_now() - self.tx_lookback_s),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("wallet_transactions failed for %s: %s",
                                    wallet, exc)
                    return None
                # Project provider rows into WalletActivityEvent
                txs: List[WalletActivityEvent] = []
                for r in txs_raw:
                    txs.append(WalletActivityEvent(
                        wallet=wallet,
                        token_id=r.get("token_id")
                                  or f"solana:{r.get('token_mint','')}",
                        token_address=r.get("token_mint") or "",
                        token_symbol=r.get("token_symbol", ""),
                        chain=r.get("chain", "solana"),
                        action=r.get("direction") or r.get("action") or "swap",
                        timestamp=float(r.get("ts") or 0.0),
                        amount_usd=float(r.get("amount_usd") or 0.0),
                        is_early_entry=False,
                    ))
                curated = label_idx.get(wallet) or {}
                label = curated.get("label")
                scores = self.scorer.compute(
                    txs=txs, token_ages_hours=token_ages_hours, label=label,
                )
                stats = merge_stats({}, {
                    "total_buys": sum(1 for t in txs if t.action == "buy"),
                    "total_sells": sum(1 for t in txs if t.action == "sell"),
                    "total_volume_usd": sum(t.amount_usd for t in txs),
                })
                return WalletProfile(
                    address=wallet,
                    chain=curated.get("chain", "solana"),
                    label=label,
                    label_source=("curated" if label else "algorithmic"),
                    first_seen=int(min((t.timestamp for t in txs),
                                        default=_now())),
                    last_seen=int(max((t.timestamp for t in txs),
                                       default=_now())),
                    scores=scores,
                    stats=stats,
                )

        if wallets_seen:
            profiles = await asyncio.gather(
                *(_enrich_one(w) for w in wallets_seen),
                return_exceptions=False,
            )
            result.profiles_updated = [p for p in profiles if p is not None]

        # 3. Cluster detection (time-window only at D-4.2)
        cluster_activity = [
            {"wallet": e.wallet, "token_id": e.token_id,
             "timestamp": e.timestamp, "action": e.action}
            for e in activity
        ]
        clusters = self.cluster_detector.detect(cluster_activity)
        result.clusters_detected = clusters
        cluster_membership = self.cluster_detector.membership_index(clusters)

        # 4. Signal-predicate evaluation → DiscoveryCandidates
        profile_lookup = {p.address: p.model_dump()
                           for p in result.profiles_updated}
        result.candidates = evaluate_all_predicates(SignalPredicateInput(
            activity=activity,
            wallet_profiles=profile_lookup,
            token_context=token_context,
            cluster_membership=cluster_membership,
        ))
        return result


def _now() -> float:
    import time as _t
    return _t.time()
