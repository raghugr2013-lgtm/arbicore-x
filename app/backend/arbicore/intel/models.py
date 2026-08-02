"""Universal entity models — Phase C Wave 4."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..models.enums import DataProvenance
from .entity_types import EntityType


@dataclass
class Entity:
    entity_id: str                           # deterministic; see resolver
    entity_type: str                         # EntityType.value
    external_refs: Dict[str, str] = field(default_factory=dict)
    # e.g. {"evm_address": "0x..", "cex_handle": "@maker_x"}
    labels: List[str] = field(default_factory=list)
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    provenance: str = DataProvenance.REAL.value
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WalletProfile:
    """Convenience view-model over an Entity of type WALLET. Wallets remain
    just-an-entity in the storage layer — this object is for API ergonomics
    only and is built on top of Entity."""
    entity_id: str
    address: str
    chain: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    provenance: str = DataProvenance.REAL.value
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_entity(cls, e: Entity) -> "WalletProfile":
        addr = e.external_refs.get("evm_address") or e.external_refs.get("address") or ""
        chain = e.external_refs.get("chain")
        return cls(
            entity_id=e.entity_id,
            address=addr,
            chain=chain,
            labels=list(e.labels),
            first_seen_at=e.first_seen_at,
            last_seen_at=e.last_seen_at,
            provenance=e.provenance,
            metadata=dict(e.metadata),
        )


@dataclass
class EntityCluster:
    cluster_id: str
    entity_ids: List[str]
    sample_count: int                   # co-occurrence support
    cluster_score: float                # 0..1 normalised strength
    detected_at: float
    method: str = "cooccurrence"
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EntityScore:
    entity_id: str
    entity_type: str
    sample_count: int
    success_rate: float                 # 0..1
    avg_outcome_score: float            # may be negative
    updated_at: float
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
