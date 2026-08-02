"""Phase 10.10 — persistent Network config → runtime env shim.

Verifies that ``sync_env_from_network_config``:
    * exports ``ARBICORE_RPC_URL`` / ``ARBICORE_RPC_URL_BASE`` from the persistent
      ``rpc_urls.base[0]`` value;
    * exports ``ARBICORE_EXECUTOR_ADDRESS_BASE`` from ``executor_addresses.base``;
    * is a no-op when the persistent config has no value for a key (backward compat
      with pre-Phase-10 ``.env``-only setups);
    * is idempotent.
"""
from __future__ import annotations

import os

import pytest

from arbicore.config.env_sync import sync_env_from_network_config


class _FakeNetworkRepo:
    def __init__(self, cfg):
        self._cfg = cfg
    async def get(self):
        return self._cfg


@pytest.mark.asyncio
async def test_exports_rpc_and_executor_from_persistent(monkeypatch):
    # Ensure clean env slate for the vars we care about.
    for k in ("ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE",
              "ARBICORE_EXECUTOR_ADDRESS_BASE"):
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

    repo = _FakeNetworkRepo({"rpc_urls": {}, "executor_addresses": {}})
    exported = await sync_env_from_network_config(repo)

    assert exported == {}
    assert os.environ["ARBICORE_RPC_URL"] == "https://pre-existing.rpc"
    assert "ARBICORE_RPC_URL_BASE" not in os.environ
    assert "ARBICORE_EXECUTOR_ADDRESS_BASE" not in os.environ


@pytest.mark.asyncio
async def test_idempotent(monkeypatch):
    for k in ("ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE",
              "ARBICORE_EXECUTOR_ADDRESS_BASE"):
        monkeypatch.delenv(k, raising=False)
    repo = _FakeNetworkRepo({
        "rpc_urls": {"base": ["https://a"]},
        "executor_addresses": {"base": "0xabc"},
    })
    r1 = await sync_env_from_network_config(repo)
    r2 = await sync_env_from_network_config(repo)
    assert r1 == r2
    assert os.environ["ARBICORE_RPC_URL"] == "https://a"


@pytest.mark.asyncio
async def test_gracefully_handles_repo_error():
    class _Broken:
        async def get(self):
            raise RuntimeError("mongo down")
    r = await sync_env_from_network_config(_Broken())
    assert r == {}
