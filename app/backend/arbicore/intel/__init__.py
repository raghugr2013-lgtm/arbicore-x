"""ArbiCore X — Universal Entity Intelligence (Phase C Wave 4).

Wallets are one entity type among many. The same machinery handles smart
money, exchange wallets, market makers, liquidity providers, launch
participants, CEX accounts, DEX pools, and future categories — without any
wallet-specific architecture.

All entities share:
  - entity_id (deterministic hash of ref_type + external_ref)
  - entity_type (frozen enum)
  - external_refs (canonical map ref_type -> external_ref string)
  - provenance (Phase B DataProvenance gate at every write path)
  - metadata (free-form, opt-in)
"""
from .cluster_detector import EntityClusterDetector
from .entity_repo import MongoEntityRepository
from .entity_types import EntityType
from .models import Entity, EntityCluster, EntityScore, WalletProfile
from .resolver import EntityResolver, ref_id, ref_to_entity_id
from .scorer import EntityScorer

__all__ = [
    "EntityType",
    "Entity", "WalletProfile", "EntityCluster", "EntityScore",
    "MongoEntityRepository", "EntityResolver", "EntityClusterDetector",
    "EntityScorer", "ref_id", "ref_to_entity_id",
]
