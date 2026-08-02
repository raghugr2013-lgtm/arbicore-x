"""Universal entity scorer — Phase C Wave 4.

Reuses the existing `arbicore_wallet_metrics` collection (Phase B) by
generalising it to *any* EntityType. Writes via the foundation
MetricsRepository so the storage contract is unchanged.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from ..data.metrics_repo import MetricsRepository, WalletMetric
from ..data.provenance import is_learning_eligible
from ..models.enums import DataProvenance
from .entity_types import EntityType
from .models import EntityScore


class EntityScorer:
    """Records per-entity outcome statistics. Wallet metrics + smart-money
    metrics + market-maker metrics all share the same collection.

    ``entity_type`` is stamped on every row via ``extras`` so consumers can
    partition without a separate collection per type.
    """

    def __init__(self, metrics_repo: MetricsRepository):
        self._metrics = metrics_repo

    async def record_outcome(self,
                             entity_id: str,
                             entity_type: EntityType,
                             succeeded: bool,
                             outcome_score: float,
                             provenance: DataProvenance,
                             ) -> bool:
        """Provenance-gated upsert. Computes win-rate + mean outcome on the
        fly using current row (single round-trip aggregate)."""
        if not is_learning_eligible(provenance):
            return False
        if not entity_id:
            return False
        existing = await self._metrics.list_wallet_metrics(entity_id=entity_id, limit=1)
        if existing:
            prev = existing[0]
            n = prev.sample_count + 1
            wins = int(round(prev.success_rate * prev.sample_count))
            wins += 1 if succeeded else 0
            mean = ((prev.avg_outcome_score * prev.sample_count) + outcome_score) / n
        else:
            n = 1
            wins = 1 if succeeded else 0
            mean = outcome_score
        metric = WalletMetric(
            wallet_id=entity_id,
            entity_id=entity_id,
            sample_count=n,
            success_rate=wins / n if n else 0.0,
            avg_outcome_score=mean,
            updated_at=time.time(),
            extras={"entity_type": entity_type.value},
        )
        await self._metrics.upsert_wallet_metric(metric)
        return True

    async def get(self, entity_id: str) -> Optional[EntityScore]:
        rows = await self._metrics.list_wallet_metrics(entity_id=entity_id, limit=1)
        if not rows:
            return None
        r = rows[0]
        return EntityScore(
            entity_id=r.entity_id or entity_id,
            entity_type=(r.extras or {}).get("entity_type", EntityType.UNKNOWN.value),
            sample_count=r.sample_count,
            success_rate=r.success_rate,
            avg_outcome_score=r.avg_outcome_score,
            updated_at=r.updated_at,
            extras=r.extras or {},
        )

    async def top(self, limit: int = 50) -> List[EntityScore]:
        rows = await self._metrics.list_wallet_metrics(limit=limit)
        out: List[EntityScore] = []
        for r in rows:
            out.append(EntityScore(
                entity_id=r.entity_id or r.wallet_id,
                entity_type=(r.extras or {}).get("entity_type", EntityType.UNKNOWN.value),
                sample_count=r.sample_count,
                success_rate=r.success_rate,
                avg_outcome_score=r.avg_outcome_score,
                updated_at=r.updated_at,
                extras=r.extras or {},
            ))
        return out
