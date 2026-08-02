"""Phase 10.10 — Persistent network config → runtime env shim.

Reuses the existing ``NetworkConfigRepo`` (Phase 10.1) to mirror the operator's
UI-managed network configuration into the process environment so that every
runtime read of ``ARBICORE_RPC_URL``, ``ARBICORE_RPC_URL_BASE``, and
``ARBICORE_EXECUTOR_ADDRESS_BASE`` transparently consumes the same values the
UI displays.

Design contract:
    * Read-only from the operator's perspective — this shim never writes back
      to Mongo; it only pushes persistent values into ``os.environ``.
    * If the persistent config has a value for a given key, that value wins.
    * If the persistent config has NO value, the existing environment variable
      is left untouched (full backward compatibility with pre-Phase-10 setups
      that configured everything via ``backend/.env``).
    * Idempotent — running it multiple times converges on the same env state.
    * No new schema, no new collections, no new configuration framework.

Invoked from:
    * ``@app.on_event("startup")`` — immediately after
      ``_NETWORK_CONFIG.ensure_seed_from_env()`` so persistent state is
      guaranteed to exist before we read it back.
    * ``POST /api/arbicore/settings/network/apply`` and ``.../rollback`` — so
      operator changes made through the UI take effect for subsequent
      broadcasts, wallet balance reads, RPC health checks, and executor
      verifications without a backend restart.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict


logger = logging.getLogger(__name__)


async def sync_env_from_network_config(network_repo, *, chain: str = "base"
                                        ) -> Dict[str, str]:
    """Push the persistent Network config onto ``os.environ``.

    Args:
        network_repo: an instance of ``NetworkConfigRepo``.
        chain: which chain's RPC / executor to export; default ``"base"``.

    Returns:
        A dict of the env vars that were set on this call (for audit logging).
    """
    exported: Dict[str, str] = {}
    try:
        cfg = await network_repo.get()
    except Exception as exc:  # noqa: BLE001
        logger.warning("env_sync: could not read network config: %s", exc)
        return exported

    # RPC URL — primary of the chain's rpc_urls list wins.
    rpcs = (cfg.get("rpc_urls") or {}).get(chain) or []
    primary_rpc = next((u for u in rpcs if isinstance(u, str) and u.strip()),
                       None)
    if primary_rpc:
        os.environ["ARBICORE_RPC_URL"] = primary_rpc
        os.environ[f"ARBICORE_RPC_URL_{chain.upper()}"] = primary_rpc
        exported["ARBICORE_RPC_URL"] = primary_rpc
        exported[f"ARBICORE_RPC_URL_{chain.upper()}"] = primary_rpc

    # Executor address — chain-scoped.
    exec_addr = ((cfg.get("executor_addresses") or {}).get(chain) or "").strip()
    if exec_addr:
        env_key = f"ARBICORE_EXECUTOR_ADDRESS_{chain.upper()}"
        os.environ[env_key] = exec_addr
        exported[env_key] = exec_addr

    if exported:
        logger.info("env_sync: exported %d var(s) from persistent network "
                     "config (chain=%s)", len(exported), chain)
    return exported
