"""Observed-field envelope for Phase 0 strategy and economics observability.

A missing value stays missing. Zero is recorded only when a stored field is
present and numeric zero. This module does not compute economics.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_PERSISTED = "AVAILABLE_NOT_PERSISTED"

KIND_BUNDLE = "verifier_bundle"
KIND_LEG = "route_leg"
KIND_QUOTE = "quote"
KIND_GAS = "gas_estimator"
KIND_FLASH = "flash_loan_provider"
KIND_ECON = "economics_calculator"
KIND_DECISION = "persisted_decision"
KIND_UNAVAILABLE = "unavailable"

CLASSIFIER_VERSION = "phase0.strategy_intelligence.v1"


def observed(
    *,
    value: Any,
    status: str,
    source: Optional[str],
    provenance_kind: str,
    timestamp: Optional[str] = None,
    calculator_version: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """One normalized field. Timestamp and calculator version are set only
    when the value itself is available from stored evidence."""
    if status != STATUS_AVAILABLE:
        timestamp = None
        calculator_version = None
    out: Dict[str, Any] = {
        "value": value,
        "status": status,
        "source": source,
        "provenance_kind": provenance_kind,
        "timestamp": timestamp,
        "calculator_version": calculator_version,
    }
    if note:
        out["note"] = note
    return out


def unavailable(note: Optional[str] = None) -> Dict[str, Any]:
    return observed(
        value=None,
        status=STATUS_UNAVAILABLE,
        source=None,
        provenance_kind=KIND_UNAVAILABLE,
        note=note,
    )


def not_persisted(*, source: str, note: str) -> Dict[str, Any]:
    """Calculator produced this concept and the m2.3 writer did not store it.

    The value stays None. Callers must not fill it from a formula.
    """
    return observed(
        value=None,
        status=STATUS_NOT_PERSISTED,
        source=source,
        provenance_kind=KIND_ECON,
        note=note,
    )


def is_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def lookup(doc: Any, path: str) -> tuple:
    """Return ``(found, value)``. A present null is found and is not a number."""
    if not isinstance(doc, dict):
        return False, None
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def as_dict(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None
