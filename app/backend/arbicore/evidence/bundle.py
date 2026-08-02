"""Evidence bundle schema + deterministic canonical serialisation.

Design commitments (per user directive):
    * Deterministic canonical JSON: sorted keys, no whitespace, UTC ISO
      timestamps, no float NaN / Inf.  Same payload → byte-for-byte
      identical hash on every platform / Python version.
    * Algorithm-agnostic bundle metadata — ``signing_algorithm`` +
      ``signing_key_version`` live on the bundle so future algorithms
      (Ed448, secp256k1, ...) are additive, not schema-breaking.
    * ``signature`` may be ``None`` — the bundle then reports
      ``verification_status='unsigned'``.  Historical unsigned bundles
      stay unsigned after key material is added.
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

BUNDLE_VERSION_DEFAULT = "v1"

# Fields that are hashed / signed.  Everything outside this set is
# operational metadata and can be added later without invalidating
# historical hashes.
HASHED_FIELDS = (
    "bundle_id",
    "bundle_version",
    "source_component",
    "source_model_id",
    "created_at",
    "payload",
)


def _canonicalise(value: Any) -> Any:
    """Recursively coerce a Python value to a canonical form.

    * ``dict`` → dict with str keys, values recursively canonicalised.
    * ``list`` / ``tuple`` → list of canonicalised values.
    * ``datetime`` → UTC ISO string (Z-suffixed).
    * ``float`` → rejects NaN / Inf (raises ValueError).
    * Everything else passes through.
    """
    if isinstance(value, dict):
        return {str(k): _canonicalise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalise(v) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("NaN / Inf not permitted in evidence payloads")
    return value


def canonical_json(payload: Dict[str, Any]) -> bytes:
    """Return the canonical byte serialisation of ``payload``."""
    canonical = _canonicalise(payload)
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def evidence_hash(bundle: Dict[str, Any]) -> str:
    """SHA-256 hash of the hashed subset of ``bundle``.  Returns
    ``sha256:<hex>``.  Deterministic across platforms."""
    subset = {k: bundle.get(k) for k in HASHED_FIELDS}
    digest = hashlib.sha256(canonical_json(subset)).hexdigest()
    return f"sha256:{digest}"


def new_bundle(
    source_component: str,
    source_model_id: Optional[str],
    payload: Dict[str, Any],
    *,
    bundle_version: str = BUNDLE_VERSION_DEFAULT,
    provider_version: Optional[str] = None,
    calibrator_version: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build an unsigned evidence bundle, ready for the signer to attach
    a signature (or to be persisted as-is when signing is disabled)."""
    bundle_id = f"evb-{uuid.uuid4().hex}"
    ts = created_at or datetime.now(timezone.utc).isoformat()
    b: Dict[str, Any] = {
        "bundle_id": bundle_id,
        "bundle_version": bundle_version,
        "source_component": source_component,
        "source_model_id": source_model_id,
        "created_at": ts,
        "payload": _canonicalise(payload),
        # Non-hashed operational metadata:
        "provider_version": provider_version,
        "calibrator_version": calibrator_version,
        "signing_algorithm": None,
        "signing_key_version": None,
        "signature": None,
        "verification_status": "unsigned",
        "unsigned_reason": None,
    }
    b["evidence_hash"] = evidence_hash(b)
    return b
