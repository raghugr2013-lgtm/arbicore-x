"""Read-only ArbiCore X executor deployment registry.

Loads the committed provisioning registry (deploy/executor_deployments.json),
which records already-broadcast FlashLoanReceiver deployments per chain id.

STRICTLY informational / fail-closed:
  * It NEVER sets ARBICORE_EXECUTOR_ADDRESS_BASE or any environment variable.
  * It NEVER enables Limited-Live, signs, broadcasts, or deploys anything.
  * ``deployed_address`` returns a PUBLIC address ONLY when a deployment is
    explicitly recorded as ``success`` with a non-null address; every other
    case (unknown chain, ``not_deployed``, missing/invalid file) returns None.

The audit/runtime continue to read the executor address from the environment
only. This registry exists so tooling/operators can look up and independently
VERIFY a deployed address without hardcoding it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

_CHAIN_ALIASES: Dict[str, int] = {
    "base": 8453, "base_mainnet": 8453, "base-mainnet": 8453,
    "base_sepolia": 84532, "base-sepolia": 84532, "sepolia": 84532,
}


def _default_registry_path() -> Path:
    # app/backend/arbicore/execution/executor_registry.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4] / "deploy" / "executor_deployments.json"


def registry_path() -> Path:
    override = os.environ.get("ARBICORE_EXECUTOR_REGISTRY_PATH")
    return Path(override) if override else _default_registry_path()


def load_registry() -> Dict[str, Any]:
    """Return the parsed registry, or an empty (fail-closed) shell on any error."""
    try:
        with open(registry_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("deployments"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"schema": "arbicore.executor_deployments/v1", "deployments": {}}


def _normalise_chain(chain: Any) -> Optional[str]:
    if chain is None:
        return None
    if isinstance(chain, int):
        return str(chain)
    s = str(chain).strip()
    if s.isdigit():
        return s
    return str(_CHAIN_ALIASES[s.lower()]) if s.lower() in _CHAIN_ALIASES else None


def get_deployment(chain: Any) -> Optional[Dict[str, Any]]:
    """Return the raw deployment record for a chain id / alias, or None."""
    key = _normalise_chain(chain)
    if key is None:
        return None
    return load_registry().get("deployments", {}).get(key)


def deployed_address(chain: Any) -> Optional[str]:
    """PUBLIC executor address ONLY when explicitly deployed successfully.

    Returns None for unknown chains, ``not_deployed`` entries, missing address,
    or any non-``success`` status — never a guess.
    """
    rec = get_deployment(chain)
    if not rec:
        return None
    if rec.get("deploy_status") != "success":
        return None
    addr = rec.get("address")
    return addr if isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42 else None


def is_deployed(chain: Any) -> bool:
    return deployed_address(chain) is not None


def executor_provenance(chain: Any, *, env_address: Optional[str] = None) -> Dict[str, Any]:
    """READ-ONLY provenance reconciliation between the runtime env address and
    the committed registry. Pure observability — it NEVER changes readiness
    classification, NEVER writes env, and NEVER fabricates a deployment.

    Surfaces the Codex-transition drift case where the VPS configures
    ``ARBICORE_EXECUTOR_ADDRESS_BASE`` for a chain the registry still records as
    ``not_deployed`` (address null): operators then know the configured address
    is UNVERIFIED against repo provenance and must confirm it on-chain.
    """
    if env_address is None:
        env_address = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") or None
    rec = get_deployment(chain) or {}
    reg_status = rec.get("deploy_status", "absent") if rec else "absent"
    reg_addr = rec.get("address") if isinstance(rec.get("address"), str) else None

    if env_address and reg_addr:
        matches = (env_address.lower() == reg_addr.lower())
    elif env_address and not reg_addr:
        matches = None  # cannot compare — registry has no recorded address
    else:
        matches = None

    if not env_address and reg_addr:
        source = "registry"
    elif env_address:
        source = "env"
    else:
        source = "none"

    if not env_address and not reg_addr:
        note = "no executor address configured (env) and none recorded (registry)"
    elif env_address and reg_status != "success":
        note = ("env executor address configured but registry has no successful "
                f"deployment (status={reg_status}) — UNVERIFIED against repo "
                "provenance; confirm on-chain identity before trusting")
    elif env_address and reg_addr and matches is False:
        note = "env executor address DIFFERS from registry-recorded address — drift"
    elif env_address and reg_addr and matches is True:
        note = "env executor address matches registry-recorded deployment"
    else:
        note = "registry-recorded deployment present; no env override"

    return {
        "env_address": env_address,
        "registry_status": reg_status,
        "registry_address": reg_addr,
        "source": source,
        "matches_registry": matches,
        "note": note,
    }


__all__ = [
    "registry_path", "load_registry", "get_deployment",
    "deployed_address", "is_deployed", "executor_provenance",
]
