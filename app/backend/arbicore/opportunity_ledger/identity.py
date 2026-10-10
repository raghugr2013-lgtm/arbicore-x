"""Deterministic ledger identity.

The same source candidate, run, and mode always produce the same
``ledger_id``. ``opportunity_id`` is an existing identifier, never a
fresh random value.

Derivation:

* ``opportunity_id`` is the bundle's stored ``opportunity_id`` when that
  value is a non-empty safe identifier. Denied flash-loan rows store
  null there. The fallback is ``candidate_id``, the discovery key already
  on every row. ``candidate_id`` is the 60-second discovery hash from
  ``make_candidate_id``. This module does not mint a second route id.
* ``ledger_id`` is ``ol1:{mode}:{run_id}:{candidate_id}``. Projecting the
  same source twice addresses one row.

``run_id`` is supplied by the caller. The October 5 SHADOW certification
id is recorded here so that later projection of that population uses the
known run. This module does not attach that id by itself and does not
read or write the certification collection.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

DEFINED_MODES = frozenset({"SHADOW", "PAPER", "RECOMMENDATION"})

OCTOBER_5_SHADOW_RUN_ID = "shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_MODE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


def _safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be a safe identifier")
    return value


def normalize_mode(mode: Any) -> str:
    """Evidence label. Not an execution switch.

    ``SHADOW``, ``PAPER``, and ``RECOMMENDATION`` are the modes this
    version defines. Another uppercase identifier is accepted as a
    future label and does not start a runner, a scanner, or a broadcast.
    """
    if not isinstance(mode, str) or _MODE.fullmatch(mode) is None:
        raise ValueError("mode must be an uppercase identifier")
    return mode


def opportunity_id_for(
    *,
    candidate_id: str,
    bundle: Optional[Dict[str, Any]] = None,
) -> str:
    """Return the stable opportunity id for this source."""
    candidate_id = _safe_id(candidate_id, "candidate_id")
    if isinstance(bundle, dict):
        stored = bundle.get("opportunity_id")
        if isinstance(stored, str) and stored.strip():
            if _SAFE_ID.fullmatch(stored) is None:
                raise ValueError("bundle opportunity_id is not a safe identifier")
            return stored
    return candidate_id


def ledger_id_for(*, mode: str, run_id: str, candidate_id: str) -> str:
    """One ledger row per mode, run, and candidate."""
    mode = normalize_mode(mode)
    run_id = _safe_id(run_id, "run_id")
    candidate_id = _safe_id(candidate_id, "candidate_id")
    return f"ol1:{mode}:{run_id}:{candidate_id}"
