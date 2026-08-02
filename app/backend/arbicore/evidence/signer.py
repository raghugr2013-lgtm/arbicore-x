"""Evidence signer — algorithm-registry pattern.

* ``Ed25519Signer`` implements the ``SignerBackend`` protocol.
* ``EvidenceSigner`` composes a key registry over multiple ``(version,
  algorithm)`` slots.  Adding a new algorithm is additive — bundle
  schema stays intact.
* Signing never raises to callers: it returns an unsigned bundle when
  the signer is disabled or an error occurs, so a broken signer can
  never block inference or learning.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any, Dict, Optional, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ..config.signing_config import KeyMaterial, SigningConfig
from .bundle import canonical_json, evidence_hash

logger = logging.getLogger("arbicore.evidence_signer")


class SignerBackend(Protocol):
    algorithm: str

    def sign(self, message: bytes, key_material: KeyMaterial) -> str: ...

    def verify(self, message: bytes, signature_b64: str,
               key_material: KeyMaterial) -> bool: ...


class Ed25519Signer:
    algorithm = "ed25519"

    def sign(self, message: bytes, key_material: KeyMaterial) -> str:
        if not key_material.secret_b64:
            raise ValueError(f"key '{key_material.version}' has no secret material")
        raw = base64.b64decode(key_material.secret_b64)
        if len(raw) != 32:
            raise ValueError(
                f"key '{key_material.version}' secret is {len(raw)} bytes; expected 32"
            )
        priv = Ed25519PrivateKey.from_private_bytes(raw)
        sig = priv.sign(message)
        return base64.b64encode(sig).decode("ascii")

    def verify(self, message: bytes, signature_b64: str,
               key_material: KeyMaterial) -> bool:
        if not key_material.public_b64:
            return False
        try:
            pub_raw = base64.b64decode(key_material.public_b64)
            if len(pub_raw) != 32:
                return False
            pub = Ed25519PublicKey.from_public_bytes(pub_raw)
            pub.verify(base64.b64decode(signature_b64), message)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False


# ---------------------------------------------------------------------------
# EvidenceSigner + Verifier
# ---------------------------------------------------------------------------


class EvidenceSigner:
    """Attaches an Ed25519 signature (or leaves the bundle unsigned)."""

    def __init__(self, config: SigningConfig,
                 backends: Optional[Dict[str, SignerBackend]] = None):
        self._cfg = config
        self._backends: Dict[str, SignerBackend] = backends or {"ed25519": Ed25519Signer()}
        self._success_count = 0
        self._failure_count = 0
        self._last_signed_at: Optional[float] = None
        self._last_error: Optional[str] = None

    @property
    def config(self) -> SigningConfig:
        return self._cfg

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._cfg.enabled,
            "active_key_version": self._cfg.active_key_version,
            "algorithms_available": sorted(self._backends.keys()),
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "last_signed_at": self._last_signed_at,
            "last_error": self._last_error,
            "unsigned_reason": self._cfg.unsigned_reason(),
            "keys_registered": [
                {
                    "version": k.version,
                    "algorithm": k.algorithm,
                    "has_secret": bool(k.secret_b64),
                    "has_public": bool(k.public_b64),
                }
                for k in self._cfg.keys.values()
            ],
        }

    def sign_bundle(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy of ``bundle`` with a signature attached (or
        marked unsigned).  Never raises."""
        out = dict(bundle)
        # Recompute the hash defensively — an upstream mutation shouldn't
        # produce a bundle whose signature disagrees with its hash.
        out["evidence_hash"] = evidence_hash(out)
        unsigned_reason = self._cfg.unsigned_reason()
        if unsigned_reason:
            out["signature"] = None
            out["signing_algorithm"] = None
            out["signing_key_version"] = None
            out["verification_status"] = "unsigned"
            out["unsigned_reason"] = unsigned_reason
            return out
        key = self._cfg.active_key()
        assert key is not None  # unsigned_reason() would have caught it
        backend = self._backends.get(key.algorithm)
        if backend is None:
            self._failure_count += 1
            self._last_error = f"no backend for algorithm '{key.algorithm}'"
            logger.warning("evidence signing failed: %s", self._last_error)
            out["signature"] = None
            out["signing_algorithm"] = key.algorithm
            out["signing_key_version"] = key.version
            out["verification_status"] = "unsigned"
            out["unsigned_reason"] = self._last_error
            return out
        try:
            message = canonical_json({k: out.get(k) for k in _HASHED_FIELDS})
            sig = backend.sign(message, key)
            out["signature"] = sig
            out["signing_algorithm"] = key.algorithm
            out["signing_key_version"] = key.version
            out["verification_status"] = "signed"
            out["unsigned_reason"] = None
            self._success_count += 1
            self._last_signed_at = time.time()
            self._last_error = None
            return out
        except Exception as exc:  # noqa: BLE001
            self._failure_count += 1
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("evidence signing failed")
            out["signature"] = None
            out["signing_algorithm"] = key.algorithm
            out["signing_key_version"] = key.version
            out["verification_status"] = "unsigned"
            out["unsigned_reason"] = self._last_error
            return out


class EvidenceVerifier:
    """Verifies a bundle against the current key registry.

    Historical bundles remain verifiable after rotation: as long as the
    ``signing_key_version`` referenced by the bundle is still registered
    (public half required only), verification succeeds.
    """

    def __init__(self, config: SigningConfig,
                 backends: Optional[Dict[str, SignerBackend]] = None):
        self._cfg = config
        self._backends: Dict[str, SignerBackend] = backends or {"ed25519": Ed25519Signer()}

    def verify(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``{verified, key_version, algorithm, evidence_hash, reason?}``.

        Deterministic — no wall-clock inputs.  A missing signature or a
        missing key version yields ``verified=False`` with a reason.
        """
        expected_hash = evidence_hash(bundle)
        result: Dict[str, Any] = {
            "verified": False,
            "algorithm": bundle.get("signing_algorithm"),
            "key_version": bundle.get("signing_key_version"),
            "evidence_hash": expected_hash,
            "bundle_hash_matches": bundle.get("evidence_hash") == expected_hash,
        }
        sig = bundle.get("signature")
        if not sig:
            result["reason"] = "unsigned"
            return result
        if not result["bundle_hash_matches"]:
            result["reason"] = "evidence_hash mismatch — bundle mutated after signing"
            return result
        algo = bundle.get("signing_algorithm")
        key_version = bundle.get("signing_key_version")
        if not algo or not key_version:
            result["reason"] = "signing metadata missing"
            return result
        backend = self._backends.get(algo)
        if backend is None:
            result["reason"] = f"unknown signing algorithm '{algo}'"
            return result
        key = self._cfg.keys.get(key_version)
        if key is None or not key.public_b64:
            result["reason"] = f"key '{key_version}' not registered"
            return result
        message = canonical_json({k: bundle.get(k) for k in _HASHED_FIELDS})
        ok = backend.verify(message, sig, key)
        result["verified"] = ok
        if not ok:
            result["reason"] = "signature verification failed"
        return result


# Late binding to keep bundle.py canonical field names authoritative.
from .bundle import HASHED_FIELDS as _HASHED_FIELDS  # noqa: E402
