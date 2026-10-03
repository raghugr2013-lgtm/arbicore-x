"""Phase 10.10 — persistent Network config → runtime env shim.

Verifies that ``sync_env_from_network_config``:
    * exports ``ARBICORE_RPC_URL`` / ``ARBICORE_RPC_URL_BASE`` from the persistent
      ``rpc_urls.base[0]`` value;
    * exports ``ARBICORE_EXECUTOR_ADDRESS_BASE`` from ``executor_addresses.base``;
    * is a no-op when the persistent config has no value for a key (backward compat
      with pre-Phase-10 ``.env``-only setups);
    * is idempotent;
    * syncs all SUPPORTED_CHAINS by default (six-network generalisation).
"""
from __future__ import annotations

import os

import pytest

from arbicore.config.env_sync import sync_env_from_network_config
from arbicore.config.persistent import SUPPORTED_CHAINS


class _FakeNetworkRepo:
    def __init__(self, cfg):
        self._cfg = cfg
    async def get(self):
        return self._cfg


def _clear_sync_env(monkeypatch):
    keys = ["ARBICORE_RPC_URL"]
    for c in SUPPORTED_CHAINS:
        u = c.upper()
        keys.extend([
            f"ARBICORE_RPC_URL_{u}", f"{u}_RPC_URL",
            f"PROVIDER_RPC_URLS_{u}",
            f"ARBICORE_PROVIDER_RPC_URLS_{u}_MANAGED",
            f"ARBICORE_EXECUTOR_ADDRESS_{u}",
        ])
    for k in keys:
        # Force undo tracking even when the key was previously absent.
        monkeypatch.setenv(k, "")
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _clean_env_sync_keys(monkeypatch):
    # Clear only at setup via monkeypatch so teardown restores "absent".
    _clear_sync_env(monkeypatch)
    yield


@pytest.mark.asyncio
async def test_exports_rpc_and_executor_from_persistent(monkeypatch):
    # Ensure clean env slate for the vars we care about.
    for k in ("ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE",
              "ARBICORE_EXECUTOR_ADDRESS_BASE",
              "PROVIDER_RPC_URLS_BASE", "ARBICORE_PROVIDER_RPC_URLS_BASE_MANAGED"):
        monkeypatch.delenv(k, raising=False)

    repo = _FakeNetworkRepo({
        "rpc_urls": {"base": ["https://mainnet.base.org",
                                "https://base.publicnode.com"]},
        "executor_addresses": {"base": "0xExecutorAddress0000000000000000000000abcd"},
        "chains_enabled": {"base": True},
    })
    exported = await sync_env_from_network_config(repo)

    assert exported["ARBICORE_RPC_URL"] == "https://mainnet.base.org"
    assert exported["ARBICORE_RPC_URL_BASE"] == "https://mainnet.base.org"
    assert exported["ARBICORE_EXECUTOR_ADDRESS_BASE"] == \
        "0xExecutorAddress0000000000000000000000abcd"
    # Actually set in os.environ
    assert os.environ["ARBICORE_RPC_URL"] == "https://mainnet.base.org"
    assert os.environ["ARBICORE_EXECUTOR_ADDRESS_BASE"] == \
        "0xExecutorAddress0000000000000000000000abcd"


@pytest.mark.asyncio
async def test_empty_persistent_leaves_env_alone(monkeypatch):
    """Backward-compat: if persistent config is empty, existing env is untouched."""
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://pre-existing.rpc")
    monkeypatch.delenv("ARBICORE_RPC_URL_BASE", raising=False)
    monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
    for c in SUPPORTED_CHAINS:
        monkeypatch.delenv(f"PROVIDER_RPC_URLS_{c.upper()}", raising=False)
        monkeypatch.delenv(
            f"ARBICORE_PROVIDER_RPC_URLS_{c.upper()}_MANAGED", raising=False)

    repo = _FakeNetworkRepo({"rpc_urls": {}, "executor_addresses": {}})
    exported = await sync_env_from_network_config(repo)

    assert exported == {}
    assert os.environ["ARBICORE_RPC_URL"] == "https://pre-existing.rpc"
    assert "ARBICORE_RPC_URL_BASE" not in os.environ
    assert "ARBICORE_EXECUTOR_ADDRESS_BASE" not in os.environ


@pytest.mark.asyncio
async def test_idempotent(monkeypatch):
    for k in ("ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE", "BASE_RPC_URL",
              "ARBICORE_EXECUTOR_ADDRESS_BASE",
              "PROVIDER_RPC_URLS_BASE", "ARBICORE_PROVIDER_RPC_URLS_BASE_MANAGED"):
        monkeypatch.delenv(k, raising=False)
    repo = _FakeNetworkRepo({
        "rpc_urls": {"base": ["https://a"]},
        "executor_addresses": {"base": "0xabc"},
    })
    await sync_env_from_network_config(repo)
    snap = {
        "ARBICORE_RPC_URL": os.environ.get("ARBICORE_RPC_URL"),
        "ARBICORE_RPC_URL_BASE": os.environ.get("ARBICORE_RPC_URL_BASE"),
        "BASE_RPC_URL": os.environ.get("BASE_RPC_URL"),
        "ARBICORE_EXECUTOR_ADDRESS_BASE": os.environ.get(
            "ARBICORE_EXECUTOR_ADDRESS_BASE"),
        "PROVIDER_RPC_URLS_BASE": os.environ.get("PROVIDER_RPC_URLS_BASE"),
    }
    await sync_env_from_network_config(repo)
    # Idempotent on env state (exported audit map may omit unchanged managed keys).
    assert os.environ.get("ARBICORE_RPC_URL") == snap["ARBICORE_RPC_URL"] == "https://a"
    assert os.environ.get("ARBICORE_RPC_URL_BASE") == snap["ARBICORE_RPC_URL_BASE"]
    assert os.environ.get("BASE_RPC_URL") == snap["BASE_RPC_URL"]
    assert os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") == \
        snap["ARBICORE_EXECUTOR_ADDRESS_BASE"]
    assert os.environ.get("PROVIDER_RPC_URLS_BASE") == snap["PROVIDER_RPC_URLS_BASE"]


@pytest.mark.asyncio
async def test_gracefully_handles_repo_error():
    class _Broken:
        async def get(self):
            raise RuntimeError("mongo down")
    r = await sync_env_from_network_config(_Broken())
    assert r == {}


@pytest.mark.asyncio
async def test_default_sync_covers_all_supported_chains(monkeypatch):
    """Default (no chain=) walks every SUPPORTED_CHAINS entry."""
    for c in SUPPORTED_CHAINS:
        monkeypatch.delenv(f"ARBICORE_RPC_URL_{c.upper()}", raising=False)
        monkeypatch.delenv(f"PROVIDER_RPC_URLS_{c.upper()}", raising=False)
        monkeypatch.delenv(
            f"ARBICORE_PROVIDER_RPC_URLS_{c.upper()}_MANAGED", raising=False)
    monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)

    rpc_urls = {c: [f"https://{c}.test/rpc"] for c in SUPPORTED_CHAINS}
    exported = await sync_env_from_network_config(
        _FakeNetworkRepo({"rpc_urls": rpc_urls, "executor_addresses": {}}))
    for c in SUPPORTED_CHAINS:
        assert exported[f"ARBICORE_RPC_URL_{c.upper()}"] == f"https://{c}.test/rpc"
    assert exported["ARBICORE_RPC_URL"] == "https://base.test/rpc"
