"""Phase 2 — Opportunity Lifetime Intelligence.

Extends the Sprint 1 pipeline with a per-opportunity aggregate that
lives in MID (canonical). Every scanner emission upserts one document
per ``opp_id`` in the new ``mid_opportunity_lifetime`` collection.

Modules:
  * :mod:`config`   — env-driven configuration (ACTIVE / STALE / EXPIRED
                       thresholds, trend ring-buffer size, sweeper interval).
  * :mod:`tracker`  — :class:`OpportunityLifetimeTracker`, invoked by the
                       Wave 1B-β scanner bridge on every emission and by
                       intelligence writes on demand.
  * :mod:`sweeper`  — background async task that transitions ACTIVE →
                       STALE → EXPIRED status when no fresh emissions
                       arrive.
"""
from .config import LifetimeConfig, load_config_from_env
from .tracker import OpportunityLifetimeTracker
from .sweeper import LifetimeSweeper

__all__ = [
    "LifetimeConfig",
    "load_config_from_env",
    "OpportunityLifetimeTracker",
    "LifetimeSweeper",
]
