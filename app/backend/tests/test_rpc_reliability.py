"""Deterministic RPC reliability tests for EthJsonRpcProvider.

Covers HTTP 429 (with/without Retry-After), 5xx, network error, malformed JSON,
JSON-RPC error object, missing result, retry-then-success, retry exhaustion
(fail closed), non-retryable 4xx, and fail-closed chain-id verification. No real
network and no real sleeping (backoff env set to 0; sleep patched to no-op).
"""
import os

import httpx
import pytest

os.environ.setdefault("ARBICORE_RPC_MAX_RETRIES", "3")
os.environ.setdefault("ARBICORE_RPC_BACKOFF_BASE_MS", "0")
os.environ.setdefault("ARBICORE_RPC_BACKOFF_CAP_MS", "0")

from arbicore.providers.rpc import EthJsonRpcProvider  # noqa: E402
from arbicore.providers.base import ProviderError  # noqa: E402


class _Resp:
    def __init__(self, status=200, json_body=None, headers=None, raise_json=False):
        self.status_code = status
        self._json = json_body if json_body is not None else {"jsonrpc": "2.0", "id": 1, "result": "0x1"}
        self.headers = headers or {}
        self._raise_json = raise_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)

    def json(self):
        if self._raise_json:
            raise ValueError("no json")
        return self._json


class _Client:
    """Fake httpx client: yields queued responses or raises queued exceptions."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    async def post(self, url, json=None):
        self.calls += 1
        item = self._script.pop(0) if self._script else _Resp()
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self):
        pass


def _provider(script, monkeypatch):
    async def _no_sleep(*_a, **_k):
        return None
    monkeypatch.setattr("arbicore.providers.rpc.asyncio.sleep", _no_sleep)
    p = EthJsonRpcProvider(chain="base", url="https://rpc.example/secret-key")
    p._client = _Client(script)  # inject fake client
    return p


async def test_429_retries_then_succeeds(monkeypatch):
    p = _provider([_Resp(429, headers={"Retry-After": "0"}), _Resp(200)], monkeypatch)
    assert await p._call("eth_blockNumber", []) == "0x1"
    assert p._client.calls == 2


async def test_429_exhaustion_fails_closed(monkeypatch):
    p = _provider([_Resp(429)] * 4, monkeypatch)  # max_retries=3 -> 4 attempts
    with pytest.raises(ProviderError) as ei:
        await p._call("eth_blockNumber", [])
    assert "429" in str(ei.value) and ei.value.retryable is True
    assert p._client.calls == 4


async def test_5xx_retries_then_fails_closed(monkeypatch):
    p = _provider([_Resp(503)] * 4, monkeypatch)
    with pytest.raises(ProviderError):
        await p._call("eth_call", [{}, "latest"])
    assert p._client.calls == 4


async def test_network_error_retryable_then_success(monkeypatch):
    p = _provider([httpx.ConnectError("boom"), _Resp(200)], monkeypatch)
    assert await p._call("eth_blockNumber", []) == "0x1"


async def test_malformed_json_retryable_then_fail(monkeypatch):
    p = _provider([_Resp(200, raise_json=True)] * 4, monkeypatch)
    with pytest.raises(ProviderError) as ei:
        await p._call("eth_blockNumber", [])
    assert "malformed_json" in str(ei.value)


async def test_rpc_error_object_not_retryable(monkeypatch):
    body = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "bad"}}
    p = _provider([_Resp(200, json_body=body)] * 4, monkeypatch)
    with pytest.raises(ProviderError) as ei:
        await p._call("eth_blockNumber", [])
    assert ei.value.retryable is False and p._client.calls == 1  # no retry


async def test_missing_result_not_retryable(monkeypatch):
    body = {"jsonrpc": "2.0", "id": 1}
    p = _provider([_Resp(200, json_body=body)], monkeypatch)
    with pytest.raises(ProviderError) as ei:
        await p._call("eth_blockNumber", [])
    assert "missing_result" in str(ei.value) and p._client.calls == 1


async def test_4xx_non_429_not_retryable(monkeypatch):
    p = _provider([_Resp(400)], monkeypatch)
    with pytest.raises(ProviderError) as ei:
        await p._call("eth_blockNumber", [])
    assert ei.value.retryable is False and p._client.calls == 1


async def test_provider_id_has_no_secret(monkeypatch):
    p = _provider([_Resp(200)], monkeypatch)
    assert "secret-key" not in p.provider_id  # host only, no path/key


async def test_verify_chain_id_match_and_mismatch(monkeypatch):
    ok = _provider([_Resp(200, json_body={"jsonrpc": "2.0", "id": 1, "result": "0x2105"})], monkeypatch)
    assert await ok.verify_chain_id(8453) is True  # 0x2105 == 8453 (Base)
    bad = _provider([_Resp(200, json_body={"jsonrpc": "2.0", "id": 1, "result": "0x1"})], monkeypatch)
    assert await bad.verify_chain_id(8453) is False


async def test_verify_chain_id_rpc_error_fails_closed(monkeypatch):
    p = _provider([_Resp(429)] * 4, monkeypatch)
    assert await p.verify_chain_id(8453) is False  # rate-limited -> fail closed
