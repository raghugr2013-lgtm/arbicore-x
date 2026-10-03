"""Six-network dynamic Network Config — focused regression suite.

Covers:
  * SUPPORTED_CHAINS includes all six (incl. bnb)
  * validate accepts bnb / rejects unsupported
  * chains_enabled persistence
  * env_sync generalisation across all six
  * Base PAYG primary preserved; non-Base does not overwrite ARBICORE_RPC_URL
  * invalid RPC fail-closed
  * Base + five-network regression (existing five still valid)

No live APPLY. Offline only.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import os
from typing import Any, Dict, List

import pytest

from arbicore.config.persistent import (
    ConfigRepo, NetworkConfigRepo, SUPPORTED_CHAINS, DEFAULT_NETWORK_CONFIG,
)
from arbicore.config.env_sync import sync_env_from_network_config


SIX = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")

# Fingerprint helpers — never print full keys.
PAYG_KEY = "payg_base_key_cd505118_fixture"
STALE_KEY = "stale_key_ce00e63d_fixture"


def _fp8(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:8]


# Pre-compute expected fps for assertions (fixture keys only).
PAYG_FP = _fp8(PAYG_KEY)
STALE_FP = _fp8(STALE_KEY)


def _alchemy(host: str, key: str) -> str:
    return f"https://{host}.g.alchemy.com/v2/{key}"


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Tiny fake Mongo (subset — mirrors test_phase10_config)
# --------------------------------------------------------------------------- #

class _FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def sort(self, key, direction=1):
        if isinstance(key, str):
            self._docs.sort(key=lambda d: d.get(key), reverse=(direction == -1))
        else:
            for k, direction2 in reversed(key):
                self._docs.sort(key=lambda d: d.get(k) or "",
                                 reverse=(direction2 == -1))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n):
        return list(self._docs[:n])


class _FakeCollection:
    def __init__(self):
        self._docs: List[Dict[str, Any]] = []

    async def create_index(self, *a, **k):
        return "idx"

    async def find_one(self, query, projection=None, sort=None):
        rows = self._filter(query)
        if sort:
            for k, direction in reversed(sort):
                rows.sort(key=lambda d: d.get(k) or "",
                           reverse=(direction == -1))
        if not rows:
            return None
        row = dict(rows[0])
        if projection:
            for k, v in projection.items():
                if v == 0 and k in row:
                    row.pop(k, None)
        return row

    def find(self, query, projection=None):
        rows = [dict(d) for d in self._filter(query)]
        if projection:
            for r in rows:
                for k, v in projection.items():
                    if v == 0 and k in r:
                        r.pop(k, None)
        return _FakeCursor(rows)

    async def insert_one(self, doc):
        self._docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        rows = self._filter(query)
        set_ = update.get("$set") or {}
        seton_ = update.get("$setOnInsert") or {}
        if rows:
            rows[0].update(set_)
        elif upsert:
            self._docs.append({**query, **seton_, **set_})

    async def replace_one(self, query, doc, upsert=False):
        idx = next((i for i, d in enumerate(self._docs)
                     if self._match(d, query)), None)
        if idx is None:
            if upsert:
                self._docs.append(dict(doc))
        else:
            self._docs[idx] = dict(doc)

    async def delete_one(self, query):
        idx = next((i for i, d in enumerate(self._docs)
                     if self._match(d, query)), None)

        class _R:
            deleted_count = 0 if idx is None else 1

        if idx is not None:
            self._docs.pop(idx)
        return _R()

    def _filter(self, query):
        return [d for d in self._docs if self._match(d, query)]

    def _match(self, doc, query):
        for k, v in (query or {}).items():
            if doc.get(k) != v:
                return False
        return True


class _FakeDB:
    def __init__(self):
        self._collections: Dict[str, _FakeCollection] = {}

    def __getitem__(self, name):
        return self._collections.setdefault(name, _FakeCollection())


class _FakeNetworkRepo:
    def __init__(self, cfg):
        self._cfg = cfg

    async def get(self):
        return self._cfg


def _clear_network_env(monkeypatch):
    """Track+clear all env keys env_sync may write (xdist-safe teardown).

    ``delenv(..., raising=False)`` is a no-op (no undo record) when the key
    is absent — so we ``setenv`` first to force monkeypatch tracking.
    """
    keys = ["ARBICORE_RPC_URL"]
    for c in SIX:
        u = c.upper()
        keys.extend([
            f"ARBICORE_RPC_URL_{u}",
            f"{u}_RPC_URL",
            f"PROVIDER_RPC_URLS_{u}",
            f"ARBICORE_PROVIDER_RPC_URLS_{u}_MANAGED",
            f"ARBICORE_EXECUTOR_ADDRESS_{u}",
        ])
    for k in keys:
        monkeypatch.setenv(k, "")
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _clean_env_sync_keys(monkeypatch):
    # Clear only at setup via monkeypatch so teardown restores "absent"
    # (do NOT delenv again after yield — that would re-record values and
    # re-pollute os.environ when monkeypatch undoes).
    _clear_network_env(monkeypatch)
    yield


# --------------------------------------------------------------------------- #
# Schema / allowlist
# --------------------------------------------------------------------------- #

def test_supported_chains_is_exactly_six_including_bnb():
    assert SUPPORTED_CHAINS == SIX
    assert "bnb" in SUPPORTED_CHAINS
    assert len(SUPPORTED_CHAINS) == 6


def test_default_network_config_has_six_chain_keys():
    for c in SIX:
        assert c in DEFAULT_NETWORK_CONFIG["rpc_urls"]
        assert c in DEFAULT_NETWORK_CONFIG["chains_enabled"]
    assert DEFAULT_NETWORK_CONFIG["chains_enabled"]["base"] is True
    assert DEFAULT_NETWORK_CONFIG["chains_enabled"]["bnb"] is False


def test_validate_accepts_bnb_rpc_and_enable():
    n = NetworkConfigRepo(ConfigRepo(_FakeDB()))
    v = n.validate({
        "rpc_urls": {"bnb": ["https://bnb-mainnet.g.alchemy.com/v2/x"]},
        "chains_enabled": {"bnb": True},
    })
    assert v["ok"] is True


def test_validate_rejects_unsupported_chain():
    n = NetworkConfigRepo(ConfigRepo(_FakeDB()))
    v = n.validate({"rpc_urls": {"tron": ["https://x.example"]}})
    assert v["ok"] is False
    assert any("unsupported chain" in e for e in v["errors"])


def test_validate_rejects_invalid_rpc_fail_closed():
    n = NetworkConfigRepo(ConfigRepo(_FakeDB()))
    v = n.validate({"rpc_urls": {"base": ["notaurl"], "ethereum": ["ftp://bad"]}})
    assert v["ok"] is False
    assert any("not an http" in e for e in v["errors"])


def test_five_network_regression_still_valid():
    """Existing five-chain patches remain valid under six-chain schema."""
    n = NetworkConfigRepo(ConfigRepo(_FakeDB()))
    five = ("base", "ethereum", "arbitrum", "optimism", "polygon")
    patch = {
        "rpc_urls": {c: [f"https://{c}.example/rpc"] for c in five},
        "chains_enabled": {c: True for c in five},
    }
    v = n.validate(patch)
    assert v["ok"] is True


def test_persist_enabled_state_including_bnb():
    db = _FakeDB()
    n = NetworkConfigRepo(ConfigRepo(db))
    patch = copy.deepcopy(DEFAULT_NETWORK_CONFIG)
    patch["rpc_urls"]["base"] = [
        _alchemy("base-mainnet", PAYG_KEY), "https://mainnet.base.org",
    ]
    patch["rpc_urls"]["bnb"] = ["https://bnb.example/rpc"]
    patch["chains_enabled"] = {c: (c in ("base", "bnb")) for c in SIX}
    cfg = _run(n.apply(patch=patch, actor="test", reason="unit enable bnb"))
    assert cfg["chains_enabled"]["bnb"] is True
    assert cfg["chains_enabled"]["ethereum"] is False
    cur = _run(n.get())
    assert cur["chains_enabled"]["bnb"] is True
    assert cur["rpc_urls"]["bnb"] == ["https://bnb.example/rpc"]


# --------------------------------------------------------------------------- #
# env_sync generalisation
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_env_sync_all_six_configured_chains(monkeypatch):
    cfg = {
        "rpc_urls": {
            c: [f"https://{c}.example/{i}"] for i, c in enumerate(SIX)
        },
        "executor_addresses": {
            "base": "0x" + "ab" * 20,
            "bnb": "0x" + "cd" * 20,
        },
    }
    exported = await sync_env_from_network_config(_FakeNetworkRepo(cfg))

    for c in SIX:
        assert os.environ[f"ARBICORE_RPC_URL_{c.upper()}"] == \
            f"https://{c}.example/{list(SIX).index(c)}"
        assert f"ARBICORE_RPC_URL_{c.upper()}" in exported
        assert os.environ[f"PROVIDER_RPC_URLS_{c.upper()}"].startswith("https://")

    # Global alias is Base-only.
    assert os.environ["ARBICORE_RPC_URL"] == "https://base.example/0"
    assert os.environ["ARBICORE_EXECUTOR_ADDRESS_BNB"] == "0x" + "cd" * 20


@pytest.mark.asyncio
async def test_env_sync_base_payg_preserved_non_base_no_global_overwrite(monkeypatch):
    payg = _alchemy("base-mainnet", PAYG_KEY)
    fallback = "https://mainnet.base.org"
    eth = _alchemy("eth-mainnet", "eth_key_fixture")

    cfg = {
        "rpc_urls": {
            "base": [payg, fallback],
            "ethereum": [eth],
        },
        "executor_addresses": {},
    }
    await sync_env_from_network_config(_FakeNetworkRepo(cfg))

    assert os.environ["ARBICORE_RPC_URL_BASE"] == payg
    assert os.environ["ARBICORE_RPC_URL"] == payg  # Base global alias
    assert os.environ["PROVIDER_RPC_URLS_BASE"] == f"{payg},{fallback}"
    assert os.environ["ARBICORE_RPC_URL_ETHEREUM"] == eth
    # Non-Base must NOT steal the global alias.
    assert os.environ["ARBICORE_RPC_URL"] != eth
    # Fingerprint of primary key matches PAYG fixture (not stale).
    primary_key = payg.rsplit("/v2/", 1)[-1]
    assert _fp8(primary_key) == PAYG_FP
    assert _fp8(primary_key) != STALE_FP
    assert STALE_KEY not in os.environ.get("PROVIDER_RPC_URLS_BASE", "")


@pytest.mark.asyncio
async def test_env_sync_empty_non_base_leaves_docker_env(monkeypatch):
    """Mongo empty for eth ⇒ pre-existing Docker env untouched."""
    monkeypatch.setenv("ARBICORE_RPC_URL_ETHEREUM", "https://docker.eth.rpc")
    monkeypatch.delenv("ARBICORE_RPC_URL_BASE", raising=False)
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://pre-existing.global")

    cfg = {
        "rpc_urls": {"base": ["https://mainnet.base.org"]},
        "executor_addresses": {},
    }
    await sync_env_from_network_config(_FakeNetworkRepo(cfg))
    assert os.environ["ARBICORE_RPC_URL_ETHEREUM"] == "https://docker.eth.rpc"
    assert os.environ["ARBICORE_RPC_URL"] == "https://mainnet.base.org"


@pytest.mark.asyncio
async def test_env_sync_single_chain_compat(monkeypatch):
    cfg = {
        "rpc_urls": {
            "base": ["https://base.x"],
            "bnb": ["https://bnb.x"],
        },
        "executor_addresses": {},
    }
    exported = await sync_env_from_network_config(
        _FakeNetworkRepo(cfg), chain="bnb")
    assert "ARBICORE_RPC_URL_BNB" in exported
    assert "ARBICORE_RPC_URL_BASE" not in exported
    # Single-chain non-Base must not set global alias.
    assert "ARBICORE_RPC_URL" not in exported
    assert "ARBICORE_RPC_URL" not in os.environ


@pytest.mark.asyncio
async def test_env_sync_skips_unsupported_chain_fail_closed(monkeypatch):
    cfg = {"rpc_urls": {"base": ["https://base.x"]}, "executor_addresses": {}}
    exported = await sync_env_from_network_config(
        _FakeNetworkRepo(cfg), chains=["base", "tron"])
    assert "ARBICORE_RPC_URL_BASE" in exported
    assert os.environ["ARBICORE_RPC_URL"] == "https://base.x"


def test_apply_rejects_invalid_rpc_no_partial_write():
    db = _FakeDB()
    n = NetworkConfigRepo(ConfigRepo(db))
    good = copy.deepcopy(DEFAULT_NETWORK_CONFIG)
    good["rpc_urls"]["base"] = ["https://ok.example"]
    _run(n.apply(patch=good, actor="t", reason="seed"))
    bad = copy.deepcopy(DEFAULT_NETWORK_CONFIG)
    bad["rpc_urls"]["base"] = ["not-a-url"]
    with pytest.raises(ValueError):
        _run(n.apply(patch=bad, actor="t", reason="bad"))
    cur = _run(n.get())
    assert cur["rpc_urls"]["base"] == ["https://ok.example"]
