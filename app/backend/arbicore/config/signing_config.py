"""Wave 5 · Evidence Signing configuration.

Bootstrap policy (per user directive, Option b):
    * If no key material is present in the environment, the system
      continues to run and emit UNSIGNED bundles with a clear operator
      warning.  It never auto-generates keys.
    * When key material is supplied via env vars, new bundles are
      signed automatically; historical unsigned bundles remain
      unsigned; historical signed bundles remain independently
      verifiable.

Key material is namespaced by version so rotations are non-destructive:
    * ``SIGNING_ACTIVE_KEY_VERSION`` — the version applied to new bundles.
    * For each version ``vX``:
        * ``SIGNING_KEY_vX_ALGORITHM`` — algorithm identifier (default ``ed25519``).
        * ``SIGNING_KEY_vX_SECRET`` — base64-encoded private key material.
        * ``SIGNING_KEY_vX_PUBLIC`` — base64-encoded public key material.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("arbicore.signing_config")

_KEY_VERSION_RE = re.compile(r"^SIGNING_KEY_(v[0-9]+)_(ALGORITHM|SECRET|PUBLIC)$")


def _int(env: str, default: int) -> int:
    try:
        return int(os.environ.get(env, default))
    except (TypeError, ValueError):
        return default


def _bool(env: str, default: bool) -> bool:
    v = os.environ.get(env)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class KeyMaterial:
    version: str
    algorithm: str
    secret_b64: Optional[str]  # None when only the public half is registered.
    public_b64: Optional[str]


@dataclass(frozen=True)
class SigningConfig:
    enabled: bool = True
    active_key_version: Optional[str] = None
    keys: Dict[str, KeyMaterial] = field(default_factory=dict)
    tick_interval_s: int = 60
    retired_ttl_days: int = 365
    bundle_version: str = "v1"
    failure_alert_threshold: int = 5
    backoff_ladder_s: tuple = (30, 60, 120, 300)

    def active_key(self) -> Optional[KeyMaterial]:
        if not self.active_key_version:
            return None
        return self.keys.get(self.active_key_version)

    def has_signing_material(self) -> bool:
        k = self.active_key()
        return bool(k and k.secret_b64)

    def unsigned_reason(self) -> Optional[str]:
        if not self.enabled:
            return "signing disabled via SIGNING_ENABLED=false"
        if not self.active_key_version:
            return "no active signing key configured (SIGNING_ACTIVE_KEY_VERSION unset)"
        k = self.active_key()
        if k is None:
            return f"active key version '{self.active_key_version}' not registered"
        if not k.secret_b64:
            return f"active key '{self.active_key_version}' has no secret material"
        return None

    @classmethod
    def from_env(cls) -> "SigningConfig":
        active = os.environ.get("SIGNING_ACTIVE_KEY_VERSION") or None
        keys: Dict[str, Dict[str, str]] = {}
        for env_key, env_val in os.environ.items():
            m = _KEY_VERSION_RE.match(env_key)
            if not m:
                continue
            version, field_ = m.group(1), m.group(2).lower()
            slot = keys.setdefault(version, {"algorithm": "ed25519"})
            slot[field_] = env_val

        materials: Dict[str, KeyMaterial] = {}
        for version, slot in keys.items():
            materials[version] = KeyMaterial(
                version=version,
                algorithm=slot.get("algorithm", "ed25519"),
                secret_b64=slot.get("secret"),
                public_b64=slot.get("public"),
            )

        cfg = cls(
            enabled=_bool("SIGNING_ENABLED", True),
            active_key_version=active,
            keys=materials,
            tick_interval_s=_int("SIGNING_TICK_INTERVAL_S", 60),
            retired_ttl_days=_int("SIGNING_RETIRED_TTL_DAYS", 365),
            bundle_version=os.environ.get("EVIDENCE_BUNDLE_VERSION", "v1"),
            failure_alert_threshold=_int("SIGNING_FAILURE_ALERT_THRESHOLD", 5),
        )
        reason = cfg.unsigned_reason()
        if reason:
            logger.warning(
                "EVIDENCE SIGNING DISABLED — bundles will be created UNSIGNED. Reason: %s. "
                "The evidence pipeline will continue running; supply SIGNING_ACTIVE_KEY_VERSION "
                "and matching key material to activate signing.",
                reason,
            )
        return cfg
