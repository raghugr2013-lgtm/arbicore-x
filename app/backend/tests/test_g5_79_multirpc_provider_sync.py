"""G5.79 — multi-RPC provider synchronization regression suite.

Deterministic, offline, no network, no tx, no scanner. Covers:
  managed-vs-explicit provenance, managed updates, explicit precedence,
  cold-start restart (managed + explicit), stale removal, URL replace,
  rollback 2→1, health preservation, fresh health on change, chain isolation,
  fail-closed empty, secret-safety, no scanner activation, no tx side-effects.

Run:  pytest -q tests/test_g5_79_multirpc_provider_sync.py
"""
import asyncio
import hashlib

import pytest

from arbicore.config import env_sync
from arbicore.providers import bootstrap as pb
from arbicore.providers.registry import ProviderRegistry
from arbicore.providers.base import ProviderKind

BASE = "https://mainnet.base.org"
ALCH_A = "https://base-mainnet.g.alchemy.com/v2/KEYAAAA"
ALCH_B = "https://base-mainnet.g.alchemy.com/v2/KEYBBBB"   # same host, diff key
OTHER = "https://base-rpc.otherhost.org"                    # different host
EXPL_A = "https://explicit-a.example.com"
EXPL_B = "https://explicit-b.example.com"

VAR = "PROVIDER_RPC_URLS_BASE"
MARK = "ARBICORE_PROVIDER_RPC_URLS_BASE_MANAGED"

_ENV_KEYS = [
    "PROVIDER_RPC_URLS_BASE", "PROVIDER_RPC_URL_BASE", MARK,
    "ARBICORE_RPC_URL_BASE", "ARBICORE_RPC_URL", "BASE_RPC_URL",
    "PROVIDER_RPC_URLS_ETHEREUM", "ARBICORE_RPC_URL_ETHEREUM",
    "ARBICORE_DISCOVERY_AUTOSTART",
]


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Repo:
    def __init__(self, cfg):
        self._cfg = cfg

    async def get(self):
        return self._cfg


def _cfg(rpcs):
    return {"rpc_urls": {"base": list(rpcs)}}


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _sync_env(rpcs):
    return run(env_sync.sync_env_from_network_config(_Repo(_cfg(rpcs)), chain="base"))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    yield


# ---------------------------------------------------------------------------
# 1. managed export writes CSV + provenance marker, both endpoints registered
# ---------------------------------------------------------------------------
def test_managed_export_writes_csv_and_marker_and_registers_both():
    exp = _sync_env([BASE, ALCH_A])
    assert os_environ(VAR) == f"{BASE},{ALCH_A}"
    assert os_environ(MARK) == _sha(f"{BASE},{ALCH_A}")
    assert exp[VAR] == "<2 endpoints, managed>"          # secret-safe redaction

    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base"])
    ids = [e.provider_id for e in reg.list(chain="base")]
    assert any(i.startswith("rpc_base_0_") for i in ids)
    assert any(i.startswith("rpc_base_1_") for i in ids)


def os_environ(k):
    import os
    return os.environ.get(k)


# ---------------------------------------------------------------------------
# 2. provider priority ordering (primary index0 priority 100 outranks fallback)
# ---------------------------------------------------------------------------
def test_priority_ordering_primary_first():
    import os
    os.environ[VAR] = f"{BASE},{ALCH_A}"
    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base"])
    ordered = [e.provider_id for e in reg.list(chain="base")]
    assert ordered[0].startswith("rpc_base_0_")           # highest score first
    assert ordered[1].startswith("rpc_base_1_")


# ---------------------------------------------------------------------------
# 3. managed config UPDATES when persistent config changes (not stale)
# ---------------------------------------------------------------------------
def test_managed_config_updates_when_persistent_changes():
    _sync_env([BASE, ALCH_A])
    assert os_environ(VAR) == f"{BASE},{ALCH_A}"
    exp = _sync_env([BASE, OTHER])                        # persistent changed
    assert os_environ(VAR) == f"{BASE},{OTHER}"           # updated, not blocked
    assert os_environ(MARK) == _sha(f"{BASE},{OTHER}")


# ---------------------------------------------------------------------------
# 4. explicit operator PROVIDER_RPC_URLS_BASE stays authoritative
# ---------------------------------------------------------------------------
def test_explicit_config_remains_authoritative(monkeypatch):
    monkeypatch.setenv(VAR, f"{EXPL_A},{EXPL_B}")          # operator explicit
    _sync_env([BASE, ALCH_A])                              # persistent differs
    assert os_environ(VAR) == f"{EXPL_A},{EXPL_B}"         # untouched
    assert os_environ(MARK) is None                        # marker cleared


# ---------------------------------------------------------------------------
# 5. COLD START (managed): restart regenerates managed value from persistent
# ---------------------------------------------------------------------------
def test_cold_start_managed_regenerates_after_restart(monkeypatch):
    _sync_env([BASE, ALCH_A])                              # process 1 managed
    assert os_environ(MARK) is not None
    # simulate process restart: fresh env (nothing persists across processes)
    for k in (VAR, MARK):
        monkeypatch.delenv(k, raising=False)
    exp = _sync_env([BASE, OTHER])                         # persistent changed
    assert os_environ(VAR) == f"{BASE},{OTHER}"            # regenerated managed
    assert os_environ(MARK) == _sha(f"{BASE},{OTHER}")
    assert exp[VAR] == "<2 endpoints, managed>"


# ---------------------------------------------------------------------------
# 6. COLD START (explicit): explicit at process start survives config change
# ---------------------------------------------------------------------------
def test_cold_start_explicit_remains_authoritative(monkeypatch):
    # operator supplied explicit PROVIDER_RPC_URLS_BASE at process start
    monkeypatch.setenv(VAR, f"{EXPL_A},{EXPL_B}")          # launch-env explicit
    _sync_env([BASE, ALCH_A])                              # persistent config
    assert os_environ(VAR) == f"{EXPL_A},{EXPL_B}"         # still authoritative
    _sync_env([OTHER])                                     # persistent changes
    assert os_environ(VAR) == f"{EXPL_A},{EXPL_B}"         # STILL authoritative


# ---------------------------------------------------------------------------
# 7. stale provider removal (fallback dropped from config)
# ---------------------------------------------------------------------------
def test_stale_provider_removed_on_sync():
    import os
    os.environ[VAR] = f"{BASE},{ALCH_A}"
    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base"])
    assert len(reg.list(chain="base")) == 2
    os.environ[VAR] = BASE                                 # drop fallback
    out = pb.sync_rpc_providers_from_env(reg, ["base"])
    ids = [e.provider_id for e in reg.list(chain="base")]
    assert len(ids) == 1 and ids[0].startswith("rpc_base_0_")
    assert any(p.startswith("rpc_base_1_") for p in out["removed"]["base"])


# ---------------------------------------------------------------------------
# 8. rollback two RPCs -> one RPC removes only the stale provider
# ---------------------------------------------------------------------------
def test_rollback_two_to_one_removes_only_stale():
    _sync_env([BASE, ALCH_A])
    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base"])
    assert len(reg.list(chain="base")) == 2
    _sync_env([BASE])                                      # rollback to single
    pb.sync_rpc_providers_from_env(reg, ["base"])
    ids = [e.provider_id for e in reg.list(chain="base")]
    assert ids == [i for i in ids if i.startswith("rpc_base_0_")]
    assert len(ids) == 1


# ---------------------------------------------------------------------------
# 9. unchanged providers RETAIN health/EWMA/circuit state (skip re-register)
# ---------------------------------------------------------------------------
def test_unchanged_provider_preserves_health_state():
    import os
    os.environ[VAR] = f"{BASE},{ALCH_A}"
    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base"])
    pid = next(e.provider_id for e in reg.list(chain="base")
               if e.provider_id.startswith("rpc_base_0_"))
    reg._health[pid].successes = 7                          # simulate history
    reg._health[pid].ewma_latency_ms = 123.0
    out = pb.sync_rpc_providers_from_env(reg, ["base"])    # same config
    assert pid in out["skipped"]["base"]                   # skipped, not replaced
    assert reg._health[pid].successes == 7                 # health preserved
    assert reg._health[pid].ewma_latency_ms == 123.0


# ---------------------------------------------------------------------------
# 10. changed URL at same id gets FRESH health (no stale inheritance)
# ---------------------------------------------------------------------------
def test_changed_url_gets_fresh_health():
    import os
    os.environ[VAR] = f"{BASE},{ALCH_A}"
    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base"])
    pid = next(e.provider_id for e in reg.list(chain="base")
               if e.provider_id.startswith("rpc_base_1_"))
    reg._health[pid].successes = 9
    os.environ[VAR] = f"{BASE},{ALCH_B}"                   # same host, new key
    out = pb.sync_rpc_providers_from_env(reg, ["base"])
    assert pid in out["synced"]["base"]                    # replaced
    assert reg._health[pid].successes == 0                 # fresh health
    assert reg.get(pid).url == ALCH_B


# ---------------------------------------------------------------------------
# 11. chain isolation: base endpoints never leak to other chains
# ---------------------------------------------------------------------------
def test_chain_isolation_no_cross_chain_leak():
    import os
    os.environ[VAR] = f"{BASE},{ALCH_A}"
    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base", "ethereum"])
    base_ids = [e.provider_id for e in reg.list(chain="base")]
    eth_ids = [e.provider_id for e in reg.list(chain="ethereum")]
    assert all(i.startswith("rpc_base_") for i in base_ids)
    assert all(i.startswith("rpc_ethereum_") for i in eth_ids)
    # the base alchemy endpoint must not appear under ethereum
    assert not any("alchemy" in (reg.get(i).url or "") for i in eth_ids)


# ---------------------------------------------------------------------------
# 12. fail-closed MANAGED export on empty config + backward-compatible default
#     Two distinct contracts:
#       (a) G5.79 managed-export layer is FAIL-CLOSED: empty persistent config
#           writes NO managed PROVIDER_RPC_URLS_<CHAIN> (and no marker).
#       (b) The pre-existing bootstrap registry layer remains BACKWARD-COMPATIBLE:
#           with nothing configured, _rpc_urls() falls back to the canonical
#           public DEFAULT so the system is never left with zero Base providers.
#           This default fallback is INTENTIONAL (it predates G5.79 and underpins
#           existing single-endpoint certification) and is explicitly asserted
#           here so the behaviour is documented, not accidental.
# ---------------------------------------------------------------------------
def test_empty_config_failcloses_managed_export_and_keeps_default_provider():
    from arbicore.providers.bootstrap import DEFAULT_RPC_URLS

    # (a) managed-export layer is fail-closed on empty persistent config.
    exp = _sync_env([])
    assert VAR not in exp                                  # nothing exported
    assert os_environ(VAR) is None                         # no managed value
    assert os_environ(MARK) is None                        # no provenance marker

    # (b) registry layer retains the backward-compatible single DEFAULT provider.
    reg = ProviderRegistry()
    out = pb.sync_rpc_providers_from_env(reg, ["base"])
    assert out["ok"] is True
    ids = [e.provider_id for e in reg.list(chain="base")]
    assert len(ids) == 1 and ids[0].startswith("rpc_base_0_")
    # the single provider IS the canonical public default (documented fallback).
    assert reg.get(ids[0]).url == DEFAULT_RPC_URLS["base"]


# ---------------------------------------------------------------------------
# 13. secret-safety: no raw URL (with API key) in the returned audit map
# ---------------------------------------------------------------------------
def test_secret_safety_no_url_in_audit_map():
    exp = _sync_env([BASE, ALCH_A])
    for v in exp.values():
        assert "KEYAAAA" not in v
        assert "alchemy.com/v2" not in v
    assert exp[VAR] == "<2 endpoints, managed>"


# ---------------------------------------------------------------------------
# 14. no scanner activation as a side effect
# ---------------------------------------------------------------------------
def test_no_scanner_activation():
    _sync_env([BASE, ALCH_A])
    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base"])
    assert os_environ("ARBICORE_DISCOVERY_AUTOSTART") is None


# ---------------------------------------------------------------------------
# 15. no transaction / signing side effects — providers are read-only RPC
# ---------------------------------------------------------------------------
def test_no_transaction_side_effects_read_only_providers():
    import os
    os.environ[VAR] = f"{BASE},{ALCH_A}"
    reg = ProviderRegistry()
    pb.sync_rpc_providers_from_env(reg, ["base"])
    for e in reg.list(chain="base"):
        p = reg.get(e.provider_id)
        assert p.kind == ProviderKind.RPC                  # read-only kind only
        assert not hasattr(p, "sign")                      # no signing capability
        assert not hasattr(p, "broadcast")                 # no broadcast capability
