"""Phase 10.1 · Persistent operator configuration substrate.

Introduces three collaborating pieces used by every UI-managed
configuration surface downstream of Phase 10:

    * :class:`ConfigRepo` — generic Mongo-backed key/value config
      repository with Draft / Apply / Rollback / Audit primitives.
    * :class:`NetworkConfigRepo` — first concrete user: RPC URLs,
      executor address, gas settings, chain enablement. Retires
      ~9 environment variables from the day-to-day operator surface.
    * :func:`resolve_network_setting` — env-fallback helper that lets
      every legacy call site keep using ``os.environ`` while the
      Mongo-side truth takes precedence.

Design notes:

    * READ-ONLY at construction; every write is explicit + audited.
    * NEVER stores encryption master keys, MongoDB URIs, JWT secrets,
      or Docker configuration — these remain infrastructure-only.
    * Every config kind carries its own ``*_config`` (current), ``*_config_draft``
      (pending), and ``*_config_audit`` (history) collections.
"""
from __future__ import annotations

import copy
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# ConfigRepo — reusable substrate
# ============================================================================

class ConfigRepo:
    """Generic Draft/Apply/Rollback/Audit repository.

    Every consumer picks a ``kind`` (e.g. ``network``, ``operator_account``,
    ``operational_flags``, ``learning``, ``telegram_alerts``) and gets:

        * one document at ``{_id: kind}`` in ``arbicore_config``
        * one document at ``{_id: kind}`` in ``arbicore_config_drafts``
        * an audit stream in ``arbicore_config_audit``, one row per
          apply/rollback with the full diff snapshot.
    """

    CURRENT_COLL = "arbicore_config"
    DRAFT_COLL   = "arbicore_config_drafts"
    AUDIT_COLL   = "arbicore_config_audit"

    def __init__(self, db):
        self._db = db
        self._current = db[self.CURRENT_COLL]
        self._drafts  = db[self.DRAFT_COLL]
        self._audit   = db[self.AUDIT_COLL]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._audit.create_index([("kind", 1), ("at", -1)])
        await self._audit.create_index("revision_id")
        self._indexes_ready = True

    # -----------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------

    async def get_current(self, kind: str,
                          default: Optional[Dict[str, Any]] = None
                          ) -> Dict[str, Any]:
        doc = await self._current.find_one({"_id": kind}, {"_id": 0})
        if doc:
            return doc
        return copy.deepcopy(default or {})

    async def get_draft(self, kind: str) -> Optional[Dict[str, Any]]:
        return await self._drafts.find_one({"_id": kind}, {"_id": 0})

    async def save_draft(self, kind: str, patch: Dict[str, Any],
                          actor: str = "operator") -> Dict[str, Any]:
        doc = {**(patch or {}),
                "kind": kind,
                "updated_at": _iso_now(),
                "updated_by": actor}
        await self._drafts.update_one({"_id": kind}, {"$set": doc}, upsert=True)
        return doc

    async def discard_draft(self, kind: str) -> bool:
        r = await self._drafts.delete_one({"_id": kind})
        return bool(r.deleted_count)

    async def apply(self, kind: str, *,
                     patch: Optional[Dict[str, Any]] = None,
                     actor: str = "operator",
                     reason: str = "") -> Dict[str, Any]:
        """Apply ``patch`` (or the pending draft) as the new current."""
        await self.ensure_indexes()
        if patch is None:
            draft = await self.get_draft(kind)
            if not draft:
                raise ValueError(f"no draft to apply for kind='{kind}'")
            patch = {k: v for k, v in draft.items()
                     if k not in ("kind", "updated_at", "updated_by")}
        previous = await self.get_current(kind)
        now = _iso_now()
        revision_id = f"rev-{uuid.uuid4().hex}"
        new_doc = {**previous, **patch,
                    "kind": kind,
                    "updated_at": now,
                    "updated_by": actor,
                    "revision_id": revision_id}
        await self._current.update_one(
            {"_id": kind},
            {"$set": {k: v for k, v in new_doc.items() if k != "_id"}},
            upsert=True,
        )
        await self._audit.insert_one({
            "kind": kind,
            "action": "apply",
            "revision_id": revision_id,
            "previous": previous,
            "next": {k: v for k, v in new_doc.items() if k != "_id"},
            "actor": actor,
            "reason": reason,
            "at": now,
        })
        # Clear pending draft — it's been promoted.
        await self._drafts.delete_one({"_id": kind})
        return await self.get_current(kind)

    async def rollback(self, kind: str, *,
                        revision_id: Optional[str] = None,
                        actor: str = "operator",
                        reason: str = "") -> Dict[str, Any]:
        """Rollback to the specified revision (default: the last).

        If ``revision_id`` is None, restores whatever was the ``previous``
        snapshot in the newest audit row (i.e. one-step undo).
        """
        await self.ensure_indexes()
        query: Dict[str, Any] = {"kind": kind}
        if revision_id:
            query["revision_id"] = revision_id
        row = await self._audit.find_one(
            query, sort=[("at", -1)],
        )
        if not row:
            raise ValueError(
                f"no audit row found for kind='{kind}' "
                f"revision_id={revision_id!r}")
        restored = row["previous"] or {}
        now = _iso_now()
        rollback_revision = f"rev-{uuid.uuid4().hex}"
        current_before = await self.get_current(kind)
        # Wipe & reset — a full snapshot restore, not a merge.
        await self._current.replace_one(
            {"_id": kind},
            {"_id": kind, **restored,
              "kind": kind, "updated_at": now, "updated_by": actor,
              "revision_id": rollback_revision,
              "rolled_back_from": row["revision_id"]},
            upsert=True,
        )
        await self._audit.insert_one({
            "kind": kind,
            "action": "rollback",
            "revision_id": rollback_revision,
            "rolled_back_from": row["revision_id"],
            "previous": current_before,
            "next": restored,
            "actor": actor,
            "reason": reason,
            "at": now,
        })
        return await self.get_current(kind)

    async def history(self, kind: str, limit: int = 50) -> List[Dict[str, Any]]:
        cur = self._audit.find({"kind": kind}, {"_id": 0}) \
                          .sort("at", -1).limit(limit)
        return await cur.to_list(limit)

    async def all_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self._audit.find({}, {"_id": 0}).sort("at", -1).limit(limit)
        return await cur.to_list(limit)


# ============================================================================
# Network Configuration (first concrete kind)
# ============================================================================

NETWORK_KIND = "network"

# Chain identifiers accepted by adapters + calldata module.
SUPPORTED_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")

DEFAULT_NETWORK_CONFIG: Dict[str, Any] = {
    # Ordered RPC list per chain — first is primary, rest are failover.
    "rpc_urls": {c: [] for c in SUPPORTED_CHAINS},
    # Chain enable / disable.
    "chains_enabled": {c: (c == "base") for c in SUPPORTED_CHAINS},
    # Deployed FlashLoanReceiver address per chain.
    "executor_addresses": {c: "" for c in SUPPORTED_CHAINS},
    # Per-chain gas overrides (all fields optional — None = use estimator).
    "gas_settings": {
        c: {"gas_price_gwei": None,
             "max_fee_gwei": None,
             "prio_fee_gwei": None}
        for c in SUPPORTED_CHAINS
    },
    # Per-chain native token price override (USD) — optional.
    "native_price_usd": {c: None for c in SUPPORTED_CHAINS},
    # Per-chain MEV relay override (URL) — optional.
    "mev_relay_urls": {c: "" for c in SUPPORTED_CHAINS},
    # Bootstrap origin metadata.
    "seeded_from_env": False,
}


# Environment-variable back-compat map: whenever a config field is
# missing/empty in Mongo, fall back to the corresponding env variable.
# This keeps every existing call site working during migration.
_ENV_FALLBACK: Dict[str, str] = {
    "rpc_urls.base":         "ARBICORE_RPC_URL_BASE",
    "rpc_urls._any_":        "ARBICORE_RPC_URL",
    "executor_addresses.base": "ARBICORE_EXECUTOR_ADDRESS_BASE",
    "gas_settings.base.gas_price_gwei": "ARBICORE_GAS_PRICE_GWEI",
    "gas_settings.base.max_fee_gwei":   "ARBICORE_MAX_FEE_GWEI",
    "gas_settings.base.prio_fee_gwei":  "ARBICORE_PRIO_FEE_GWEI",
    "native_price_usd.base":            "ARBICORE_NATIVE_PRICE_USD",
    "mev_relay_urls.base":              "ARBICORE_MEV_RELAY_URL",
}


class NetworkConfigRepo:
    """Thin domain wrapper on top of :class:`ConfigRepo`."""

    def __init__(self, config_repo: ConfigRepo):
        self._repo = config_repo

    async def ensure_indexes(self) -> None:
        await self._repo.ensure_indexes()

    async def ensure_seed_from_env(self) -> Dict[str, Any]:
        """Boot-time seed. Reads current env vars ONCE and writes them
        into the network config if the collection is empty. Never
        overwrites an existing config."""
        current = await self._repo.get_current(NETWORK_KIND, default={})
        if current:
            return current
        seed = copy.deepcopy(DEFAULT_NETWORK_CONFIG)
        # Base is the operational chain — bootstrap those env values.
        rpc = os.environ.get("ARBICORE_RPC_URL_BASE") \
              or os.environ.get("ARBICORE_RPC_URL") or ""
        if rpc:
            seed["rpc_urls"]["base"] = [u.strip() for u in rpc.split(",") if u.strip()]
        exec_addr = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") or ""
        if exec_addr:
            seed["executor_addresses"]["base"] = exec_addr
        for k in ("gas_price_gwei", "max_fee_gwei", "prio_fee_gwei"):
            v = os.environ.get(f"ARBICORE_{k.upper().replace('_GWEI', '')}_GWEI")
            if v:
                try:
                    seed["gas_settings"]["base"][k] = float(v)
                except ValueError:
                    pass
        if os.environ.get("ARBICORE_NATIVE_PRICE_USD"):
            try:
                seed["native_price_usd"]["base"] = float(os.environ["ARBICORE_NATIVE_PRICE_USD"])
            except ValueError:
                pass
        if os.environ.get("ARBICORE_MEV_RELAY_URL"):
            seed["mev_relay_urls"]["base"] = os.environ["ARBICORE_MEV_RELAY_URL"]
        seed["seeded_from_env"] = True
        await self._repo.apply(NETWORK_KIND, patch=seed,
                                actor="system:boot",
                                reason="seed from environment on first boot")
        return await self._repo.get_current(NETWORK_KIND)

    async def get(self) -> Dict[str, Any]:
        return await self._repo.get_current(NETWORK_KIND,
                                             default=DEFAULT_NETWORK_CONFIG)

    async def get_draft(self) -> Optional[Dict[str, Any]]:
        return await self._repo.get_draft(NETWORK_KIND)

    def validate(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Return ``{"ok": bool, "errors": [...], "warnings": [...]}``.

        Every downstream endpoint should call this before Apply so the
        UI can render diagnostics without partial writes.
        """
        errors: List[str] = []
        warnings: List[str] = []
        # rpc_urls: dict[chain -> list[str]]
        rpc = patch.get("rpc_urls") or {}
        if not isinstance(rpc, dict):
            errors.append("rpc_urls must be a mapping chain -> list of URLs")
        else:
            for chain, urls in rpc.items():
                if chain not in SUPPORTED_CHAINS:
                    errors.append(f"unsupported chain '{chain}' in rpc_urls")
                if not isinstance(urls, list):
                    errors.append(f"rpc_urls[{chain}] must be a list")
                    continue
                for u in urls:
                    if not isinstance(u, str) or not u.startswith(("http://", "https://")):
                        errors.append(f"rpc_urls[{chain}] entry {u!r} is not an http(s) URL")
        # executor_addresses
        for chain, addr in (patch.get("executor_addresses") or {}).items():
            if chain not in SUPPORTED_CHAINS:
                errors.append(f"unsupported chain '{chain}' in executor_addresses")
            if addr and not (isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42):
                errors.append(f"executor_addresses[{chain}] must be a 0x-prefixed 40-hex address")
        # gas_settings
        for chain, gas in (patch.get("gas_settings") or {}).items():
            if chain not in SUPPORTED_CHAINS:
                errors.append(f"unsupported chain '{chain}' in gas_settings")
                continue
            if not isinstance(gas, dict):
                errors.append(f"gas_settings[{chain}] must be a mapping")
                continue
            for k, v in gas.items():
                if v is not None and not isinstance(v, (int, float)):
                    errors.append(f"gas_settings[{chain}].{k} must be a number or null")
                elif isinstance(v, (int, float)) and v < 0:
                    errors.append(f"gas_settings[{chain}].{k} must be non-negative")
        # chains_enabled
        for chain, enabled in (patch.get("chains_enabled") or {}).items():
            if chain not in SUPPORTED_CHAINS:
                errors.append(f"unsupported chain '{chain}' in chains_enabled")
            if not isinstance(enabled, bool):
                errors.append(f"chains_enabled[{chain}] must be bool")
        # native_price_usd
        for chain, p in (patch.get("native_price_usd") or {}).items():
            if chain not in SUPPORTED_CHAINS:
                errors.append(f"unsupported chain '{chain}' in native_price_usd")
            if p is not None and not isinstance(p, (int, float)):
                errors.append(f"native_price_usd[{chain}] must be a number or null")
        # Warnings — non-blocking.
        base_rpc = (rpc.get("base") or [])
        if not base_rpc:
            warnings.append("no RPC configured for chain 'base' — LIMITED_LIVE flow will WAIT")
        if not (patch.get("executor_addresses") or {}).get("base"):
            warnings.append("no executor address configured for chain 'base' — LIMITED_LIVE flow will BLOCK")
        return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}

    async def save_draft(self, patch: Dict[str, Any],
                          actor: str = "operator") -> Dict[str, Any]:
        v = self.validate(patch)
        if not v["ok"]:
            raise ValueError("draft failed validation: " + "; ".join(v["errors"]))
        return await self._repo.save_draft(NETWORK_KIND, patch, actor=actor)

    async def apply(self, patch: Optional[Dict[str, Any]] = None,
                    actor: str = "operator",
                    reason: str = "") -> Dict[str, Any]:
        if patch is not None:
            v = self.validate(patch)
            if not v["ok"]:
                raise ValueError("apply failed validation: " + "; ".join(v["errors"]))
        return await self._repo.apply(NETWORK_KIND, patch=patch,
                                       actor=actor, reason=reason)

    async def rollback(self, revision_id: Optional[str] = None,
                        actor: str = "operator", reason: str = "") -> Dict[str, Any]:
        return await self._repo.rollback(NETWORK_KIND,
                                          revision_id=revision_id,
                                          actor=actor, reason=reason)

    async def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await self._repo.history(NETWORK_KIND, limit=limit)


# ============================================================================
# Env-fallback resolver — used by legacy call sites during migration
# ============================================================================

def resolve_rpc_url_from_env(chain: str = "base") -> Optional[str]:
    """T0-5 canonical *synchronous* RPC precedence resolver (no DB).

    Precedence (deterministic):
        ARBICORE_RPC_URL_<CHAIN>  >  ARBICORE_RPC_URL  >  legacy <CHAIN>_RPC_URL

    Returns None when unset — callers fail fast; no fabricated default.
    """
    c = chain.upper()
    return (os.environ.get(f"ARBICORE_RPC_URL_{c}")
            or os.environ.get("ARBICORE_RPC_URL")
            or os.environ.get(f"{c}_RPC_URL")
            or None)


async def resolve_rpc_url(*, network_repo: NetworkConfigRepo,
                           chain: str = "base") -> Optional[str]:
    """Return the primary RPC URL for ``chain`` (Mongo first, env fallback)."""
    try:
        cfg = await network_repo.get()
        urls = (cfg.get("rpc_urls") or {}).get(chain) or []
        if urls:
            return urls[0]
    except Exception:
        pass
    return (os.environ.get(f"ARBICORE_RPC_URL_{chain.upper()}")
            or os.environ.get("ARBICORE_RPC_URL")
            or None)


async def resolve_executor_address(*, network_repo: NetworkConfigRepo,
                                    chain: str = "base") -> Optional[str]:
    try:
        cfg = await network_repo.get()
        addr = ((cfg.get("executor_addresses") or {}).get(chain) or "").strip()
        if addr:
            return addr
    except Exception:
        pass
    if chain == "base":
        return os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") or None
    return None
