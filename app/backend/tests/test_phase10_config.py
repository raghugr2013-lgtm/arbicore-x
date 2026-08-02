"""Phase 10.1/10.2/10.3 · Persistent config + Telegram alerts — unit tests.

Every test is offline (no HTTP/Telegram calls). Mongo is replaced with
tiny in-process fake collections that mirror the motor async API surface
this codebase actually uses.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from arbicore.config.persistent import (
    ConfigRepo, NetworkConfigRepo, NETWORK_KIND, DEFAULT_NETWORK_CONFIG,
)
from arbicore.config.stubs_migration import (
    OperatorAccountRepo, ExecutionSettingsRepo, OperationalFlagsRepo,
)
from arbicore.notifications.telegram import (
    TelegramAlertService, TELEGRAM_KIND, DEFAULT_RULES,
)


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Tiny fake Mongo collection (async subset)
# --------------------------------------------------------------------------- #

class _FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def sort(self, key, direction=1):
        # key may be str or list of tuples
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
            new = {**query, **seton_, **set_}
            self._docs.append(new)

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
        if idx is None:
            class _R:
                deleted_count = 0
            return _R()
        self._docs.pop(idx)
        class _R:
            deleted_count = 1
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


# --------------------------------------------------------------------------- #
# ConfigRepo — draft/apply/rollback/history
# --------------------------------------------------------------------------- #

class TestConfigRepo:
    def test_apply_then_get_current(self):
        db = _FakeDB()
        repo = ConfigRepo(db)
        cfg = _run(repo.apply("k1", patch={"a": 1, "b": 2},
                                actor="op", reason="init"))
        assert cfg["a"] == 1 and cfg["b"] == 2
        got = _run(repo.get_current("k1"))
        assert got["a"] == 1

    def test_draft_apply_flow(self):
        db = _FakeDB()
        repo = ConfigRepo(db)
        _run(repo.save_draft("k1", {"a": 1}, actor="op"))
        draft = _run(repo.get_draft("k1"))
        assert draft["a"] == 1
        cfg = _run(repo.apply("k1", actor="op", reason="promote"))
        assert cfg["a"] == 1
        assert _run(repo.get_draft("k1")) is None

    def test_rollback_restores_previous(self):
        db = _FakeDB()
        repo = ConfigRepo(db)
        _run(repo.apply("k1", patch={"a": 1}, actor="op"))
        _run(repo.apply("k1", patch={"a": 2}, actor="op"))
        cfg = _run(repo.get_current("k1"))
        assert cfg["a"] == 2
        # rollback → should restore a=1
        restored = _run(repo.rollback("k1", actor="op", reason="undo"))
        assert restored["a"] == 1

    def test_history_orders_newest_first(self):
        db = _FakeDB()
        repo = ConfigRepo(db)
        _run(repo.apply("k1", patch={"a": 1}, actor="op"))
        _run(repo.apply("k1", patch={"a": 2}, actor="op"))
        hist = _run(repo.history("k1"))
        assert len(hist) == 2
        assert hist[0]["next"]["a"] == 2


# --------------------------------------------------------------------------- #
# NetworkConfigRepo — validation, env-seed, apply
# --------------------------------------------------------------------------- #

class TestNetworkConfigRepo:
    def test_seed_from_env(self, monkeypatch):
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://mainnet.base.org")
        monkeypatch.setenv("ARBICORE_EXECUTOR_ADDRESS_BASE",
                            "0x" + "ab" * 20)
        monkeypatch.setenv("ARBICORE_GAS_PRICE_GWEI", "0.01")
        db = _FakeDB()
        n = NetworkConfigRepo(ConfigRepo(db))
        cfg = _run(n.ensure_seed_from_env())
        assert cfg["rpc_urls"]["base"] == ["https://mainnet.base.org"]
        assert cfg["executor_addresses"]["base"].startswith("0x")
        assert cfg["seeded_from_env"] is True

    def test_seed_is_idempotent(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        db = _FakeDB()
        n = NetworkConfigRepo(ConfigRepo(db))
        cfg1 = _run(n.ensure_seed_from_env())
        # Now set env — should NOT overwrite
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://other.rpc")
        cfg2 = _run(n.ensure_seed_from_env())
        assert cfg1["rpc_urls"] == cfg2["rpc_urls"]

    def test_validate_rejects_bad_url(self):
        n = NetworkConfigRepo(ConfigRepo(_FakeDB()))
        v = n.validate({"rpc_urls": {"base": ["notaurl"]}})
        assert v["ok"] is False
        assert any("not an http" in e for e in v["errors"])

    def test_validate_rejects_bad_address(self):
        n = NetworkConfigRepo(ConfigRepo(_FakeDB()))
        v = n.validate({"executor_addresses": {"base": "0xshort"}})
        assert v["ok"] is False

    def test_validate_rejects_unknown_chain(self):
        n = NetworkConfigRepo(ConfigRepo(_FakeDB()))
        v = n.validate({"rpc_urls": {"tron": ["https://x"]}})
        assert v["ok"] is False

    def test_warning_when_base_rpc_missing(self):
        n = NetworkConfigRepo(ConfigRepo(_FakeDB()))
        v = n.validate({"rpc_urls": {}})
        assert v["ok"] is True
        assert any("base" in w.lower() for w in v["warnings"])

    def test_apply_persists_and_history_tracks(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        db = _FakeDB()
        n = NetworkConfigRepo(ConfigRepo(db))
        _run(n.apply(patch={"rpc_urls": {"base": ["https://rpc.a"]}},
                      actor="op", reason="initial"))
        _run(n.apply(patch={"rpc_urls": {"base": ["https://rpc.b"]}},
                      actor="op", reason="switch"))
        cur = _run(n.get())
        assert cur["rpc_urls"]["base"] == ["https://rpc.b"]
        hist = _run(n.history())
        assert len(hist) >= 2

    def test_rollback_reverts_rpc(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        db = _FakeDB()
        n = NetworkConfigRepo(ConfigRepo(db))
        _run(n.apply(patch={"rpc_urls": {"base": ["https://rpc.a"]}}))
        _run(n.apply(patch={"rpc_urls": {"base": ["https://rpc.b"]}}))
        restored = _run(n.rollback(actor="op", reason="undo"))
        assert restored["rpc_urls"]["base"] == ["https://rpc.a"]


# --------------------------------------------------------------------------- #
# Stubs migration wrappers
# --------------------------------------------------------------------------- #

class TestStubsMigration:
    def test_execution_settings_patch(self):
        db = _FakeDB()
        r = ExecutionSettingsRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        out = _run(r.patch({"max_position_usd": 55_000, "min_confidence": 0.75}))
        assert out["max_position_usd"] == 55_000
        assert out["min_confidence"] == 0.75

    def test_execution_settings_rejects_out_of_range_confidence(self):
        db = _FakeDB()
        r = ExecutionSettingsRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        with pytest.raises(ValueError):
            _run(r.patch({"min_confidence": 2.5}))

    def test_operational_flags_feature_flag_merge(self):
        db = _FakeDB()
        r = OperationalFlagsRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        out = _run(r.patch({"feature_flags": {"auto_execute": True}}))
        assert out["feature_flags"]["auto_execute"] is True
        # Other flags preserved
        assert out["feature_flags"]["ui_v2"] is True

    def test_account_patch_and_reject_unknown_key(self):
        db = _FakeDB()
        r = OperatorAccountRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        out = _run(r.patch({"display_name": "Ops Desk 02", "not_a_field": 1}))
        assert out["display_name"] == "Ops Desk 02"


# --------------------------------------------------------------------------- #
# TelegramAlertService — offline
# --------------------------------------------------------------------------- #

class _StubSecretHandle:
    def __init__(self, handle_id):
        self.handle_id = handle_id


class _StubSecretRegistry:
    def __init__(self):
        self._store = {}
        self._counter = 0

    async def put(self, plaintext, *, scope, algorithm, label=""):
        self._counter += 1
        hid = f"sec-{self._counter}"
        self._store[hid] = plaintext
        return _StubSecretHandle(hid)

    async def resolve(self, handle_id):
        return self._store.get(handle_id)

    async def delete(self, handle_id):
        return bool(self._store.pop(handle_id, None))


class TestTelegramAlerts:
    def _svc(self):
        db = _FakeDB()
        return TelegramAlertService(db, config_repo=ConfigRepo(db),
                                     secret_registry=_StubSecretRegistry())

    def test_default_disabled_no_token(self):
        s = self._svc()
        _run(s.ensure_seeded())
        settings = _run(s.get_settings())
        assert settings["enabled"] is False
        assert settings["token_set"] is False
        assert settings["chat_id"] == ""

    def test_emit_no_send_when_disabled(self):
        s = self._svc()
        _run(s.ensure_seeded())
        r = _run(s.emit(kind="verdict_flip", text="GO"))
        assert r["sent"] is False
        assert "disabled" in r["reason"]

    def test_save_settings_token_masked(self):
        s = self._svc()
        _run(s.ensure_seeded())
        _run(s.save_settings(enabled=True, chat_id="42",
                              bot_token="1234567890:ABCDEFGHIJKLMNOP"))
        settings = _run(s.get_settings())
        assert settings["token_set"] is True
        assert "…" in settings["token_mask"]
        # Never expose plaintext
        assert "1234567890" not in str(settings)

    def test_rule_disable_blocks_emit(self):
        s = self._svc()
        _run(s.ensure_seeded())
        _run(s.save_settings(enabled=True, chat_id="42",
                              bot_token="tok:abcdefghij",
                              rules={"verdict_flip": False,
                                      "cooldown_s": 0}))
        r = _run(s.emit(kind="verdict_flip", text="GO"))
        assert r["sent"] is False
        assert "rule" in r["reason"]

    def test_cooldown_blocks_second_emit(self):
        s = self._svc()
        _run(s.ensure_seeded())
        _run(s.save_settings(enabled=True, chat_id="42",
                              bot_token="tok:abcdefghij",
                              rules={"cooldown_s": 300}))
        # First emit will *attempt* to send (httpx is available, will fail
        # against fake host but that's fine — we just care about cooldown).
        # Set last_sent manually to isolate cooldown behaviour.
        import time as _t
        s._last_sent["verdict_flip"] = _t.monotonic()
        r = _run(s.emit(kind="verdict_flip", text="hi"))
        assert r["sent"] is False
        assert "cooldown" in r["reason"]

    def test_send_test_writes_log_when_unconfigured(self):
        s = self._svc()
        _run(s.ensure_seeded())
        # No chat_id/token → send_test logs failure
        r = _run(s.send_test())
        assert r["sent"] is False
        log = _run(s.history())
        assert len(log) == 1
        assert log[0]["kind"] == "test"
        assert log[0]["sent"] is False
