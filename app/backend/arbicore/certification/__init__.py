"""Shadow Certification (v2.11.9).

Continuous, canonical 20-cycle validation gate that sits between the
Paper Validation Framework and the Base Sepolia broadcast promotion.

Immutable :class:`ShadowCertificationRun` composed of frozen
:class:`ShadowCertificationCycle` snapshots, each linked back to the
Paper Validation :class:`EvidenceBundle` set produced during that cycle
window via ``validation_ids``.

Thresholds are canonical and env-tunable (never magic numbers in code).
See :mod:`arbicore.certification.thresholds`.

Endpoints live in :mod:`server` under ``/api/arbicore/certification/shadow/*``.
"""

from .thresholds import (
    CertificationThresholds,
    CertificationStatus,
    CycleStatus,
    load_thresholds_from_env,
)
from .models import (
    ShadowCertificationCycle,
    ShadowCertificationRun,
    new_run_id,
    new_cycle_id,
)
from .repo import (
    MongoShadowCertificationRepository,
    InMemoryShadowCertificationRepository,
)
from .engine import ShadowCertificationEngine
from .runner import ShadowCertificationRunner, is_shadow_cert_enabled_via_env

__all__ = [
    "CertificationThresholds",
    "CertificationStatus",
    "CycleStatus",
    "load_thresholds_from_env",
    "ShadowCertificationCycle",
    "ShadowCertificationRun",
    "new_run_id",
    "new_cycle_id",
    "MongoShadowCertificationRepository",
    "InMemoryShadowCertificationRepository",
    "ShadowCertificationEngine",
    "ShadowCertificationRunner",
    "is_shadow_cert_enabled_via_env",
]
