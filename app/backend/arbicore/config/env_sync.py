"""Phase 10.10 — Persistent network config → runtime env shim.

Reuses the existing ``NetworkConfigRepo`` (Phase 10.1) to mirror the operator's
UI-managed network configuration into the process environment so that every
runtime read of ``ARBICORE_RPC_URL``, ``ARBICORE_RPC_URL_<CHAIN>``, and
``ARBICORE_EXECUTOR_ADDRESS_<CHAIN>`` transparently consumes the same values the
UI displays.

Design contract:
    * Read-only from the operator's perspective — this shim never writes back
      to Mongo; it only pushes persistent values into ``os.environ``.
    * If the persistent config has a value for a given key, that value wins.
    * If the persistent config has NO value, the existing environment variable
      is left untouched (full backward compatibility with pre-Phase-10 setups
      that configured everything via ``backend/.env``).
    * Idempotent — running it multiple times converges on the same env state.
    * Syncs every chain in ``SUPPORTED_CHAINS`` by default (six-network).
    * Global ``ARBICORE_RPC_URL`` is Base-only (never overwritten by non-Base).
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

import hashlib
import logging
import os
from typing import Any, Dict, Iterable, Optional

from arbicore.config.persistent import SUPPORTED_CHAINS


logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _provider_rpc_managed_marker(chain: str) -> str:
    return f"ARBICORE_PROVIDER_RPC_URLS_{chain.upper()}_MANAGED"


def _sync_managed_provider_rpc_urls(chain: str, rpcs, exported: Dict[str, str]
                                    ) -> None:
    """G5.79 — synchronize the persistent multi-RPC list into
    ``PROVIDER_RPC_URLS_<CHAIN>`` with explicit managed-vs-operator provenance.

    Provenance rules (deterministic):
      * explicit operator value (no marker, or value diverged from the marker)
        → authoritative; NEVER overwritten; any stale marker is cleared.
      * managed value (marker matches the current value) → safe to update or
        remove when the persistent Network Config changes.
      * nothing set → write the managed value + its provenance marker.

    Secret-safe: the returned ``exported`` audit map records only a redacted
    marker, never the raw URL (RPC URLs may embed API keys).
    """
    c = chain.upper()
    var = f"PROVIDER_RPC_URLS_{c}"
    mark = _provider_rpc_managed_marker(chain)
    cur = os.environ.get(var)
    marker = os.environ.get(mark)

    urls = [u.strip() for u in (rpcs or []) if isinstance(u, str) and u.strip()]
    desired = ",".join(urls)

    is_managed = bool(marker) and cur is not None and _sha256(cur) == marker
    is_explicit = cur is not None and not is_managed

    if is_explicit:
        # Operator-owned explicit config WINS and is never overwritten.
        os.environ.pop(mark, None)
        return
    if desired:
        if not is_managed or cur != desired:
            os.environ[var] = desired
            os.environ[mark] = _sha256(desired)
            exported[var] = f"<{len(urls)} endpoints, managed>"
    elif is_managed:
        # Persistent list was cleared AND we own the current value → remove it.
        os.environ.pop(var, None)
        os.environ.pop(mark, None)
        exported[var] = "<removed, managed>"


def _sync_one_chain(cfg: Dict[str, Any], chain: str,
                    exported: Dict[str, str]) -> None:
    """Push one chain's persistent Network config onto ``os.environ``."""
    # RPC URL — primary of the chain's rpc_urls list wins.
    rpcs = (cfg.get("rpc_urls") or {}).get(chain) or []
    primary_rpc = next((u for u in rpcs if isinstance(u, str) and u.strip()),
                       None)
    if primary_rpc:
        # Global ARBICORE_RPC_URL is Base-only — never overwrite with non-Base.
        if chain == "base":
            os.environ["ARBICORE_RPC_URL"] = primary_rpc
            exported["ARBICORE_RPC_URL"] = primary_rpc
        os.environ[f"ARBICORE_RPC_URL_{chain.upper()}"] = primary_rpc
        exported[f"ARBICORE_RPC_URL_{chain.upper()}"] = primary_rpc
        # T0-5: also export the legacy ``<CHAIN>_RPC_URL`` alias so legacy
        # readers (e.g. paper/simulator.py, scanner_config rpc_env_var) stay
        # consistent with the UI-managed persistent config during migration.
        os.environ[f"{chain.upper()}_RPC_URL"] = primary_rpc
        exported[f"{chain.upper()}_RPC_URL"] = primary_rpc

    # G5.79 — multi-RPC managed synchronization (managed/explicit provenance).
    # Runs even when the persistent list is empty so a managed value can be
    # removed; an explicit operator PROVIDER_RPC_URLS_<CHAIN> stays authoritative.
    _sync_managed_provider_rpc_urls(chain, rpcs, exported)

    # Executor address — chain-scoped.
    exec_addr = ((cfg.get("executor_addresses") or {}).get(chain) or "").strip()
    if exec_addr:
        env_key = f"ARBICORE_EXECUTOR_ADDRESS_{chain.upper()}"
        os.environ[env_key] = exec_addr
        exported[env_key] = exec_addr


async def sync_env_from_network_config(
    network_repo,
    *,
    chain: Optional[str] = None,
    chains: Optional[Iterable[str]] = None,
) -> Dict[str, str]:
    """Push the persistent Network config onto ``os.environ``.

    Args:
        network_repo: an instance of ``NetworkConfigRepo``.
        chain: optional single-chain override (backward compatible). When set,
            only that chain is synced. Prefer omitting this so all
            ``SUPPORTED_CHAINS`` are synced.
        chains: optional explicit iterable of chains to sync. Ignored when
            ``chain`` is provided. Defaults to ``SUPPORTED_CHAINS``.

    Returns:
        A dict of the env vars that were set on this call (for audit logging).

    Fail-closed: unknown chains in ``chain``/``chains`` are skipped with a
    warning; repo read failures return ``{}`` without mutating env.
    """
    exported: Dict[str, str] = {}
    try:
        cfg = await network_repo.get()
    except Exception as exc:  # noqa: BLE001
        logger.warning("env_sync: could not read network config: %s", exc)
        return exported

    if chain is not None:
        target = [chain]
    elif chains is not None:
        target = list(chains)
    else:
        target = list(SUPPORTED_CHAINS)

    for c in target:
        if c not in SUPPORTED_CHAINS:
            logger.warning("env_sync: skipping unsupported chain %r", c)
            continue
        before = len(exported)
        _sync_one_chain(cfg, c, exported)
        if len(exported) > before:
            logger.debug("env_sync: chain=%s exported %d var(s)",
                         c, len(exported) - before)

    if exported:
        logger.info("env_sync: exported %d var(s) from persistent network "
                     "config (chains=%s)", len(exported),
                     ",".join(target))
    return exported
