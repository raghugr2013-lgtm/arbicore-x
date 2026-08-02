"""Wave 6A · Wallet registry + secret registry — unit tests."""
from __future__ import annotations

import base64

import pytest
from cryptography.fernet import Fernet

from arbicore.execution.wallet_registry import WalletRegistryRepo
from arbicore.secrets.backends import (
    CAPABILITY_SCOPES, FernetSecretBackend, InMemorySecretBackend,
)
from arbicore.secrets.registry import SecretRegistry


# ------- in-memory Motor stub -------

class _AsyncCursor:
    def __init__(self, docs): self._docs = list(docs); self._i = 0
    def sort(self, key, direction=1):
        if isinstance(key, str):
            self._docs.sort(key=lambda d: d.get(key), reverse=(direction == -1))
        elif isinstance(key, list):
            for k, dir_ in reversed(key):
                self._docs.sort(key=lambda x: x.get(k), reverse=(dir_ == -1))
        return self
    def limit(self, n): self._docs = self._docs[:n]; return self
    async def to_list(self, n): return list(self._docs[:n])

class _MemColl:
    def __init__(self): self._docs = []
    async def create_index(self, *a, **k): return None
    async def insert_one(self, doc): self._docs.append(dict(doc)); return type("R",(),{})()
    async def find_one(self, q, p=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                if p:
                    return {k: v for k, v in d.items() if p.get(k, 1) != 0}
                return dict(d)
        return None
    def find(self, q=None, p=None):
        q = q or {}
        docs = [dict(d) for d in self._docs
                if all(d.get(k) == v for k, v in q.items())]
        if p:
            docs = [{k: v for k, v in d.items() if p.get(k, 1) != 0} for d in docs]
        return _AsyncCursor(docs)
    async def update_one(self, q, u):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                for k, v in u.get("$set", {}).items(): d[k] = v
                for k in u.get("$unset", {}).keys(): d.pop(k, None)
                return type("R",(),{"modified_count":1})()
        return type("R",(),{"modified_count":0})()
    async def delete_one(self, q):
        for i, d in enumerate(self._docs):
            if all(d.get(k) == v for k, v in q.items()):
                del self._docs[i]
                return type("R",(),{"deleted_count":1})()
        return type("R",(),{"deleted_count":0})()

class _MemDB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _MemColl())


# ============================================================
# Wallet Registry
# ============================================================

VALID_ADDR = "0x" + "a" * 40


@pytest.mark.asyncio
async def test_register_watch_only_wallet():
    repo = WalletRegistryRepo(_MemDB())
    await repo.ensure_indexes()
    row = await repo.register(
        wallet_id="w1", address=VALID_ADDR, chain="base",
        execution_role="watch_only", label="test wallet",
    )
    assert row["execution_role"] == "watch_only"
    assert row["chain"] == "base"
    assert row["secret_handle_id"] is None


@pytest.mark.asyncio
async def test_register_gas_wallet_with_secret_handle():
    repo = WalletRegistryRepo(_MemDB())
    row = await repo.register(
        wallet_id="gas-1", address=VALID_ADDR, chain="base",
        execution_role="gas", secret_handle_id="sec-abc",
    )
    assert row["secret_handle_id"] == "sec-abc"


@pytest.mark.asyncio
async def test_reject_secret_handle_for_non_gas_role():
    repo = WalletRegistryRepo(_MemDB())
    with pytest.raises(ValueError, match="only 'gas'"):
        await repo.register(
            wallet_id="w1", address=VALID_ADDR, chain="base",
            execution_role="watch_only", secret_handle_id="sec-abc",
        )


@pytest.mark.asyncio
async def test_reject_bad_address():
    repo = WalletRegistryRepo(_MemDB())
    with pytest.raises(ValueError):
        await repo.register(wallet_id="w1", address="not-an-address")


@pytest.mark.asyncio
async def test_reject_unsupported_chain():
    repo = WalletRegistryRepo(_MemDB())
    with pytest.raises(ValueError):
        await repo.register(wallet_id="w1", address=VALID_ADDR, chain="solana")


@pytest.mark.asyncio
async def test_update_role_downgrades_scrub_secret_handle():
    repo = WalletRegistryRepo(_MemDB())
    await repo.register(
        wallet_id="w1", address=VALID_ADDR, chain="base",
        execution_role="gas", secret_handle_id="sec-abc",
    )
    updated = await repo.update_role("w1", "watch_only", reason="demoted")
    assert updated["execution_role"] == "watch_only"
    assert updated.get("secret_handle_id") is None


@pytest.mark.asyncio
async def test_audit_history_recorded():
    repo = WalletRegistryRepo(_MemDB())
    await repo.register(wallet_id="w1", address=VALID_ADDR, actor="alice",
                        reason="initial provision")
    await repo.update_role("w1", "funding", actor="bob", reason="promote")
    hist = await repo.audit_history("w1")
    assert len(hist) == 2
    actions = {h["action"] for h in hist}
    assert actions == {"register", "update_role"}


# ============================================================
# Secret Registry (InMemory backend for hermetic tests)
# ============================================================

@pytest.mark.asyncio
async def test_secret_put_returns_handle_no_plaintext():
    reg = SecretRegistry(InMemorySecretBackend())
    h = await reg.put(b"super-secret", scope="evm_sign",
                      algorithm="ed25519", label="test key")
    assert h.handle_id.startswith("sec-mem-")
    assert h.scope == "evm_sign"
    assert h.provider == "memory"
    d = h.to_dict()
    assert "plaintext" not in d and "cipher" not in d


@pytest.mark.asyncio
async def test_list_handles_scrubs_plaintext():
    reg = SecretRegistry(InMemorySecretBackend())
    await reg.put(b"secret-1", scope="evm_sign", algorithm="ed25519")
    handles = await reg.list_handles()
    for h in handles:
        assert "plaintext" not in h
        assert "cipher" not in h


@pytest.mark.asyncio
async def test_reject_unknown_scope():
    reg = SecretRegistry(InMemorySecretBackend())
    with pytest.raises(ValueError):
        await reg.put(b"secret", scope="rogue_scope", algorithm="ed25519")


@pytest.mark.asyncio
async def test_resolve_returns_plaintext_only_for_internal_callers():
    """Resolve is the only method that returns plaintext.  It exists
    exclusively for the internal signer path — REST never exposes it."""
    backend = InMemorySecretBackend()
    reg = SecretRegistry(backend)
    h = await reg.put(b"my-secret", scope="evm_sign", algorithm="ed25519")
    got = await reg.resolve(h.handle_id)
    assert got == b"my-secret"
    # Unknown handle → None (no raise, no leak).
    assert await reg.resolve("sec-nonexistent") is None


@pytest.mark.asyncio
async def test_delete_secret():
    reg = SecretRegistry(InMemorySecretBackend())
    h = await reg.put(b"x", scope="custom", algorithm="raw")
    assert await reg.delete(h.handle_id) is True
    assert await reg.delete(h.handle_id) is False


def test_registry_status_shape():
    reg = SecretRegistry(InMemorySecretBackend())
    s = reg.status
    assert s["default_provider"] == "memory"
    assert any(p["provider"] == "memory" and p["is_default"]
               for p in s["providers"])
    assert set(s["capability_scopes"]) == set(CAPABILITY_SCOPES)


# ============================================================
# FernetSecretBackend (with test VAULT_KEY)
# ============================================================

@pytest.mark.asyncio
async def test_fernet_backend_roundtrip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("VAULT_KEY", key)
    backend = FernetSecretBackend(_MemDB())
    assert backend.is_available()
    h = await backend.put(b"top-secret", scope="evm_sign",
                          algorithm="ed25519", label="test")
    assert h.provider == "fernet_local"
    got = await backend.get(h.handle_id)
    assert got == b"top-secret"


@pytest.mark.asyncio
async def test_fernet_backend_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("VAULT_KEY", raising=False)
    backend = FernetSecretBackend(_MemDB())
    assert backend.is_available() is False


@pytest.mark.asyncio
async def test_fernet_backend_list_scrubs_cipher(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("VAULT_KEY", key)
    backend = FernetSecretBackend(_MemDB())
    await backend.put(b"secret", scope="evm_sign", algorithm="ed25519")
    handles = await backend.list_handles()
    for h in handles:
        assert "cipher" not in h
