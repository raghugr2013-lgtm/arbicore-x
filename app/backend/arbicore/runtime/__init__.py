"""Arbicore runtime package.

Public API is preserved but resolved lazily (PEP 562) so that importing this
package — or one of its Mongo-free submodules such as ``multichain_readiness`` —
does NOT eagerly drag in ``composition`` and, through it, the MongoDB layer.
This keeps offline/deterministic tests genuinely Mongo-free while leaving the
runtime composition entry points available on first attribute access.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

_COMPOSITION_EXPORTS = frozenset(
    {
        "get_adaptive_weights",
        "get_audit_log",
        "get_confidence_engine",
        "get_event_bus",
        "get_metrics_aggregator",
        "get_metrics_repo",
        "get_opportunity_repo",
        "get_outcome_evaluator",
        "get_outcome_repo",
        "get_outcome_tracker",
        "get_regime_classifier",
        "get_regime_snapshot_repo",
        "get_regime_worker",
        "get_route_tracker",
        "get_sequence_miner",
        "get_state_observer_registry",
        "get_survival_analytics",
        "initialise_arbicore_runtime",
        "shutdown_arbicore_runtime",
    }
)

__all__ = [
    "EventBus",
    "get_adaptive_weights",
    "get_audit_log",
    "get_confidence_engine",
    "get_event_bus",
    "get_metrics_aggregator",
    "get_metrics_repo",
    "get_opportunity_repo",
    "get_outcome_evaluator",
    "get_outcome_repo",
    "get_outcome_tracker",
    "get_regime_snapshot_repo",
    "get_route_tracker",
    "get_state_observer_registry",
    "initialise_arbicore_runtime",
    "shutdown_arbicore_runtime",
]


def __getattr__(name: str):
    """Lazily resolve public runtime symbols on first access (PEP 562)."""
    if name == "EventBus":
        from .event_bus import EventBus

        return EventBus
    if name in _COMPOSITION_EXPORTS:
        from . import composition

        return getattr(composition, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(__all__) | set(globals()))


if TYPE_CHECKING:  # pragma: no cover - type-checker visibility only
    from .composition import (  # noqa: F401
        get_adaptive_weights,
        get_audit_log,
        get_confidence_engine,
        get_event_bus,
        get_metrics_aggregator,
        get_metrics_repo,
        get_opportunity_repo,
        get_outcome_evaluator,
        get_outcome_repo,
        get_outcome_tracker,
        get_regime_classifier,
        get_regime_snapshot_repo,
        get_regime_worker,
        get_route_tracker,
        get_sequence_miner,
        get_state_observer_registry,
        get_survival_analytics,
        initialise_arbicore_runtime,
        shutdown_arbicore_runtime,
    )
    from .event_bus import EventBus  # noqa: F401
