"""ArbiCore X — Phase D D-3.1 DEX quote cache.

Cross-source, in-process cache for the latest pool quote / mid price per
(chain, dex, pair). Mirrors arbicore.scanners.cex_arbitrage.sources.TickerCache.

Used by D-3.1 BaseDEXPoolSource implementations to detect cross-DEX
divergence and emit DiscoveryCandidate rows. Never persisted. Never returns
or contains a CanonicalOpportunity. INV-1 safe by construction.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CachedQuote:
    chain: str
    dex: str
    pair_canonical: str
    mid: float
    pool_liquidity_usd: Optional[float]
    last_update_ts: float
    source_id: str


class DEXQuoteCache:
    """Latest pool quote per (chain, dex, pair).

    Methods:
      - put(...)                  store a new observation
      - get(chain, dex, pair)     latest CachedQuote or None
      - reference_mid(pair)       median across all (chain, dex) for that pair
      - divergence_bps(...)       (mid - reference) / reference * 10_000
      - snapshot()                shallow copy for tests / health probe
    """

    def __init__(self, *, ttl_s: float = 300.0) -> None:
        self._store: Dict[Tuple[str, str, str], CachedQuote] = {}
        self._ttl_s = ttl_s

    def put(self, *, chain: str, dex: str, pair_canonical: str,
            mid: float, pool_liquidity_usd: Optional[float],
            source_id: str) -> None:
        key = (chain, dex, pair_canonical)
        self._store[key] = CachedQuote(
            chain=chain, dex=dex, pair_canonical=pair_canonical,
            mid=float(mid),
            pool_liquidity_usd=pool_liquidity_usd,
            last_update_ts=time.time(),
            source_id=source_id,
        )

    def get(self, *, chain: str, dex: str, pair_canonical: str) -> Optional[CachedQuote]:
        cq = self._store.get((chain, dex, pair_canonical))
        if cq is None:
            return None
        if (time.time() - cq.last_update_ts) > self._ttl_s:
            return None
        return cq

    def quotes_for(self, *, pair_canonical: str) -> List[CachedQuote]:
        now = time.time()
        return [
            cq for (_c, _d, p), cq in self._store.items()
            if p == pair_canonical and (now - cq.last_update_ts) <= self._ttl_s
        ]

    def reference_mid(self, *, pair_canonical: str) -> Optional[float]:
        observations = [cq.mid for cq in self.quotes_for(pair_canonical=pair_canonical)
                        if cq.mid > 0]
        if not observations:
            return None
        observations.sort()
        n = len(observations)
        return observations[n // 2] if n % 2 else (observations[n // 2 - 1]
                                                   + observations[n // 2]) / 2.0

    def divergence_bps(self, *, chain: str, dex: str,
                       pair_canonical: str) -> Optional[float]:
        cq = self.get(chain=chain, dex=dex, pair_canonical=pair_canonical)
        if cq is None:
            return None
        ref = self.reference_mid(pair_canonical=pair_canonical)
        if ref is None or ref <= 0:
            return None
        return (cq.mid - ref) / ref * 10_000.0

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return {
            f"{cq.chain}:{cq.dex}:{cq.pair_canonical}": {
                "mid": cq.mid,
                "age_s": time.time() - cq.last_update_ts,
            }
            for cq in self._store.values()
        }

    def clear(self) -> None:
        self._store.clear()
