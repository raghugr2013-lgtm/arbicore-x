"""Authoritative diagnostic-run evidence attribution.

Isolates evidence bundles belonging to EXACTLY ONE audit execution using the
diagnostic provenance stamped by the flash-loan scanner/verifier onto every
bundle (``diagnostics.audit_run_id`` / ``scanner_tick_id`` / ``worker_id`` /
``candidate_id``).

This is OBSERVABILITY ONLY. It NEVER influences a trading verdict, a gate, an
economic threshold, a profit calculation, signing, broadcasting, or any live
mode. It exists so an independent auditor (Codex on the VPS) can attribute a
set of evidence records to the precise scan that produced them, rather than
grabbing "the latest CONFIRMED bundle" (which could belong to a foreign or
concurrent scanner run).

Fail-closed attribution rules — a diagnostic run MUST be unambiguously
identifiable, so this reader:
  * REQUIRES an exact, non-empty ``audit_run_id``;
  * REQUIRES a non-empty ``scanner_tick_id``;
  * treats ``candidate_id`` as OPTIONAL — omit it to retrieve every candidate
    of an ``audit_run_id + scanner_tick_id`` run (then enforce candidate-level
    matching), or supply an exact non-empty ``candidate_id`` to pin one; a
    blank/typed-wrong candidate selector is rejected and candidate id ALONE is
    never sufficient (run + tick stay mandatory);
  * REJECTS foreign ``audit_run_id`` records;
  * REJECTS records missing candidate provenance even when no candidate is
    pinned;
  * NEVER falls back to ``candidate_id`` alone;
  * NEVER falls back to timestamps / ``created_at`` / ``persisted_at``;
  * NEVER selects arbitrary flash-loan evidence;
  * NEVER mixes concurrent scanner records (``worker_id`` is an optional
    additional tie-breaker).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

DEFAULT_SOURCE_COMPONENT = "flash_loan_arb_verifier"

# The provenance keys, as stamped by the scanner/verifier onto ``diagnostics``.
_AUDIT_RUN_ID = "audit_run_id"
_SCANNER_TICK_ID = "scanner_tick_id"
_WORKER_ID = "worker_id"
_CANDIDATE_ID = "candidate_id"


class AuditProvenanceError(ValueError):
    """Raised when a diagnostic-run attribution request is itself ambiguous
    (a required selector is missing/empty). Fail closed — never guess."""


def _is_empty(value: Any) -> bool:
    """A selector is 'empty' when it cannot unambiguously identify a run:
    ``None`` or a blank/whitespace string. Integers (e.g. tick 0) are NOT
    empty — a numeric tick id is a valid identifier."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _require_id(name: str, value: Any) -> str:
    """A mandatory identifier must be a NON-EMPTY STRING. Rejecting non-strings
    (dicts, lists, Mongo operator documents like ``{'$ne': ...}``) is a
    fail-closed guard: it prevents a query operator from WIDENING an isolation
    request to foreign runs (NoSQL-injection safe)."""
    if isinstance(value, bool) or not isinstance(value, str) \
            or value.strip() == "":
        raise AuditProvenanceError(
            f"audit selector '{name}' is required and must be a non-empty "
            f"string (got {type(value).__name__}={value!r}) — refusing to "
            f"attribute evidence ambiguously")
    return value


def _require_tick(value: Any) -> Any:
    """A mandatory ``scanner_tick_id`` must be an ``int`` (tick 0 allowed, but
    NOT ``bool``) or a non-empty string. Any other type is rejected so a query
    operator cannot widen the isolation."""
    if isinstance(value, bool):
        raise AuditProvenanceError(
            f"scanner_tick_id must be an int or str, not bool (got {value!r})")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip() != "":
        return value
    raise AuditProvenanceError(
        f"scanner_tick_id is required and must be a non-empty str or int "
        f"(got {type(value).__name__}={value!r})")


def _optional_str(name: str, value: Any) -> Optional[str]:
    """An optional string constraint: ``None`` / blank ⇒ no constraint; a
    non-string ⇒ reject (again, no operator documents may slip through)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str):
        raise AuditProvenanceError(
            f"audit selector '{name}' must be a string when provided "
            f"(got {type(value).__name__}={value!r})")
    return value if value.strip() != "" else None


def _optional_id(name: str, value: Any) -> Optional[str]:
    """An OPTIONAL identifier selector. ``None`` ⇒ no constraint (used to
    retrieve every candidate of an ``audit_run_id + scanner_tick_id`` run and
    THEN enforce candidate-level matching). A blank string, non-string, or a
    Mongo operator document is rejected — an explicitly-supplied selector must
    be an exact, non-empty string (fail closed; never widen)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str) \
            or value.strip() == "":
        raise AuditProvenanceError(
            f"audit selector '{name}' must be a non-empty string when provided "
            f"(got {type(value).__name__}={value!r})")
    return value


def build_audit_evidence_query(
    *,
    audit_run_id: str,
    scanner_tick_id: Any,
    candidate_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    source_component: Optional[str] = DEFAULT_SOURCE_COMPONENT,
    verification_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the exact-match Mongo filter that isolates one audit run.

    ``audit_run_id`` and ``scanner_tick_id`` are ALWAYS mandatory and non-empty
    (else :class:`AuditProvenanceError`). ``candidate_id`` is OPTIONAL: omit it
    to retrieve EVERY candidate of that exact run+tick (then enforce
    candidate-level matching downstream), or supply an exact non-empty string
    to pin one candidate. The filter matches ONLY the nested diagnostic
    provenance — it never keys off timestamps and never widens to "any
    flash-loan evidence". ``candidate_id`` ALONE is never sufficient because
    run+tick remain mandatory.
    """
    audit_run_id = _require_id("audit_run_id", audit_run_id)
    scanner_tick_id = _require_tick(scanner_tick_id)
    candidate_id = _optional_id("candidate_id", candidate_id)
    worker_id = _optional_str("worker_id", worker_id)
    source_component = _optional_str("source_component", source_component)
    verification_status = _optional_str("verification_status", verification_status)

    q: Dict[str, Any] = {
        f"diagnostics.{_AUDIT_RUN_ID}": audit_run_id,
        f"diagnostics.{_SCANNER_TICK_ID}": scanner_tick_id,
    }
    if candidate_id is not None:
        q[f"diagnostics.{_CANDIDATE_ID}"] = candidate_id
    if worker_id is not None:
        q[f"diagnostics.{_WORKER_ID}"] = worker_id
    if source_component is not None:
        q["source_component"] = source_component
    if verification_status is not None:
        q["verification_status"] = verification_status
    return q


def evidence_matches_audit(
    bundle: Dict[str, Any],
    *,
    audit_run_id: str,
    scanner_tick_id: Any,
    candidate_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    source_component: Optional[str] = DEFAULT_SOURCE_COMPONENT,
    verification_status: Optional[str] = None,
) -> bool:
    """In-memory mirror of :func:`build_audit_evidence_query`.

    Returns ``True`` ONLY when ``bundle`` carries diagnostic provenance whose
    ``audit_run_id`` and ``scanner_tick_id`` match exactly. ``candidate_id`` is
    optional: when supplied it must ALSO match exactly; when omitted the bundle
    still must carry a non-empty ``candidate_id`` in its provenance (a record
    with missing provenance is always rejected — never a fall-back to
    candidate id, timestamps, or "latest").
    """
    audit_run_id = _require_id("audit_run_id", audit_run_id)
    scanner_tick_id = _require_tick(scanner_tick_id)
    candidate_id = _optional_id("candidate_id", candidate_id)
    worker_id = _optional_str("worker_id", worker_id)
    source_component = _optional_str("source_component", source_component)
    verification_status = _optional_str("verification_status", verification_status)

    if not isinstance(bundle, dict):
        return False
    diag = bundle.get("diagnostics")
    if not isinstance(diag, dict):
        return False  # missing provenance → reject (fail closed)

    # Mandatory provenance (run + tick) must be present AND exactly equal.
    required = [(_AUDIT_RUN_ID, audit_run_id), (_SCANNER_TICK_ID, scanner_tick_id)]
    if candidate_id is not None:
        required.append((_CANDIDATE_ID, candidate_id))
    for key, want in required:
        if key not in diag or _is_empty(diag.get(key)):
            return False
        if diag.get(key) != want:
            return False
    # Even when not pinning a candidate, the bundle MUST identify its candidate
    # (fail closed on a record with no candidate provenance).
    if candidate_id is None and _is_empty(diag.get(_CANDIDATE_ID)):
        return False

    if worker_id is not None:
        if diag.get(_WORKER_ID) != worker_id:
            return False
    if source_component is not None:
        if bundle.get("source_component") != source_component:
            return False
    if verification_status is not None:
        if bundle.get("verification_status") != verification_status:
            return False
    return True


def filter_evidence_for_audit(
    bundles: Iterable[Dict[str, Any]],
    *,
    audit_run_id: str,
    scanner_tick_id: Any,
    candidate_id: Optional[str] = None,
    worker_id: Optional[str] = None,
    source_component: Optional[str] = DEFAULT_SOURCE_COMPONENT,
    verification_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Authoritative in-memory selector: return ONLY the bundles that belong
    to exactly the requested audit run. Order-preserving.

    ``audit_run_id`` + ``scanner_tick_id`` are mandatory (else
    :class:`AuditProvenanceError`). ``candidate_id`` is optional — omit it to
    retrieve every candidate of the run+tick, or supply it to pin one. Never
    mixes concurrent runs; never selects arbitrary evidence; candidate id alone
    is never sufficient.
    """
    _require_id("audit_run_id", audit_run_id)
    _require_tick(scanner_tick_id)
    _optional_id("candidate_id", candidate_id)
    return [
        b for b in bundles
        if evidence_matches_audit(
            b, audit_run_id=audit_run_id, scanner_tick_id=scanner_tick_id,
            candidate_id=candidate_id, worker_id=worker_id,
            source_component=source_component,
            verification_status=verification_status)
    ]
