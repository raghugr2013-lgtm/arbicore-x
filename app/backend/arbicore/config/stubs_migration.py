"""Phase 10.2 · Persistent replacements for `_V2_*` in-process stubs.

Every ``_V2_*`` global in ``server.py`` was a demo/development stub that
lost its state on backend restart. This module provides three thin
domain wrappers on top of :class:`ConfigRepo` that promote those stubs
to real Mongo-backed documents with Draft/Apply/Rollback/Audit.

Kinds delivered here:
    * ``operator_account`` — display name, email, MFA, session TTL
    * ``execution_settings`` — position sizing, slippage, auto-execute
      knobs. Distinct from :class:`CapitalPolicyRepo` (which is
      per-strategy binding capital rules); this collection is the
      *cockpit-wide defaults* that drive the Settings > Risk & Safety
      surface.
    * ``operational_flags`` — maintenance mode, feature flags,
      verbose logging, dev mode.

These deliberately mirror the existing ``_V2_*`` stub schemas so the
existing frontend (SettingsPage.jsx) works unchanged after the swap.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from .persistent import ConfigRepo


# ---------------------------------------------------------------------------
# Kinds
# ---------------------------------------------------------------------------

ACCOUNT_KIND    = "operator_account"
EXECUTION_KIND  = "execution_settings"
OPERATIONAL_KIND = "operational_flags"
NOTIFICATIONS_KIND = "notifications"  # used by Phase 10.3

DEFAULT_ACCOUNT: Dict[str, Any] = {
    "username": "operator",
    "display_name": "Ops Desk 01",
    "email": "ops@arbicore.internal",
    "role": "operator",
    "mfa_enabled": True,
    "session_ttl_min": 60,
    "last_login_at": None,
    "created_at": "2025-11-04T09:12:00+00:00",
}

DEFAULT_EXECUTION_SETTINGS: Dict[str, Any] = {
    "max_position_usd": 100_000,
    "max_daily_notional_usd": 2_500_000,
    "slippage_bps": 8,
    "min_confidence": 0.60,
    "min_safety": 0.65,
    "freshness_max_s": 15,
    "auto_execute_enabled": False,
    "auto_execute_verdict": "GO",
    "kill_switch_wired": True,
}

DEFAULT_OPERATIONAL_FLAGS: Dict[str, Any] = {
    "maintenance_mode": False,
    "trading_paused": False,
    "read_only": False,
    "dev_mode": False,
    "verbose_logging": False,
    "feature_flags": {
        "ui_v2": True,
        "auto_execute": False,
        "cross_chain_scanner": True,
        "flash_loan_scanner": True,
    },
}


# ---------------------------------------------------------------------------
# Wrappers — one per kind
# ---------------------------------------------------------------------------

class _KindRepo:
    """Base helper — every kind wrapper shares this shape."""

    KIND = ""
    DEFAULT: Dict[str, Any] = {}
    _ALLOWED_KEYS: Optional[set] = None  # None = allow all keys in DEFAULT

    def __init__(self, config_repo: ConfigRepo):
        self._repo = config_repo

    async def ensure_indexes(self) -> None:
        await self._repo.ensure_indexes()

    async def ensure_seeded(self) -> Dict[str, Any]:
        current = await self._repo.get_current(self.KIND, default={})
        if current:
            return current
        await self._repo.apply(self.KIND, patch=copy.deepcopy(self.DEFAULT),
                                actor="system:boot",
                                reason=f"seed defaults for {self.KIND}")
        return await self._repo.get_current(self.KIND, default=self.DEFAULT)

    def _allowed_keys(self) -> set:
        return self._ALLOWED_KEYS or set(self.DEFAULT.keys())

    async def get(self) -> Dict[str, Any]:
        return await self._repo.get_current(self.KIND, default=self.DEFAULT)

    async def patch(self, patch: Dict[str, Any],
                     actor: str = "operator",
                     reason: str = "") -> Dict[str, Any]:
        allowed = self._allowed_keys()
        clean = {k: v for k, v in (patch or {}).items() if k in allowed}
        if not clean:
            raise ValueError(f"no valid fields in patch; allowed: {sorted(allowed)}")
        return await self._repo.apply(self.KIND, patch=clean,
                                       actor=actor, reason=reason)

    async def save_draft(self, patch: Dict[str, Any],
                          actor: str = "operator") -> Dict[str, Any]:
        allowed = self._allowed_keys()
        clean = {k: v for k, v in (patch or {}).items() if k in allowed}
        return await self._repo.save_draft(self.KIND, clean, actor=actor)

    async def get_draft(self) -> Optional[Dict[str, Any]]:
        return await self._repo.get_draft(self.KIND)

    async def apply_draft(self, actor: str = "operator",
                           reason: str = "") -> Dict[str, Any]:
        return await self._repo.apply(self.KIND, patch=None,
                                       actor=actor, reason=reason)

    async def rollback(self, revision_id: Optional[str] = None,
                        actor: str = "operator", reason: str = "") -> Dict[str, Any]:
        return await self._repo.rollback(self.KIND,
                                          revision_id=revision_id,
                                          actor=actor, reason=reason)

    async def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await self._repo.history(self.KIND, limit=limit)


class OperatorAccountRepo(_KindRepo):
    KIND = ACCOUNT_KIND
    DEFAULT = DEFAULT_ACCOUNT
    _ALLOWED_KEYS = {"display_name", "email", "mfa_enabled",
                      "session_ttl_min", "last_login_at"}


class ExecutionSettingsRepo(_KindRepo):
    KIND = EXECUTION_KIND
    DEFAULT = DEFAULT_EXECUTION_SETTINGS

    async def patch(self, patch: Dict[str, Any],
                     actor: str = "operator",
                     reason: str = "") -> Dict[str, Any]:
        # Extra sanity: sizing and thresholds must be non-negative.
        for k in ("max_position_usd", "max_daily_notional_usd",
                   "slippage_bps", "freshness_max_s"):
            v = (patch or {}).get(k)
            if isinstance(v, (int, float)) and v < 0:
                raise ValueError(f"'{k}' must be non-negative")
        for k in ("min_confidence", "min_safety"):
            v = (patch or {}).get(k)
            if isinstance(v, (int, float)) and (v < 0 or v > 1):
                raise ValueError(f"'{k}' must be within [0, 1]")
        return await super().patch(patch, actor=actor, reason=reason)


class OperationalFlagsRepo(_KindRepo):
    KIND = OPERATIONAL_KIND
    DEFAULT = DEFAULT_OPERATIONAL_FLAGS

    async def patch(self, patch: Dict[str, Any],
                     actor: str = "operator",
                     reason: str = "") -> Dict[str, Any]:
        clean = {}
        for k, v in (patch or {}).items():
            if k in self.DEFAULT and isinstance(v, type(self.DEFAULT[k])):
                clean[k] = v
        if "feature_flags" in (patch or {}) and isinstance(patch["feature_flags"], dict):
            base_flags = dict(self.DEFAULT["feature_flags"])
            for fk, fv in patch["feature_flags"].items():
                if isinstance(fv, bool):
                    base_flags[fk] = fv
            clean["feature_flags"] = base_flags
        if not clean:
            raise ValueError("no valid fields in patch")
        return await self._repo.apply(self.KIND, patch=clean,
                                       actor=actor, reason=reason)
