"""ArbiCore X — Operator Control / Readiness layer.

Backend-authoritative readiness evaluation + operator mode model.
The frontend may only *request* a mode; the backend decides whether the
transition is permitted. Never weakens or bypasses Phase-0 safety gates.
"""
from .readiness import (
    ExecutionReadinessEngine,
    OPERATOR_MODES,
    NON_BROADCAST_MODES,
    ControlStateRepo,
    RED, YELLOW, GREEN,
)

__all__ = [
    "ExecutionReadinessEngine", "OPERATOR_MODES", "NON_BROADCAST_MODES",
    "ControlStateRepo", "RED", "YELLOW", "GREEN",
]
