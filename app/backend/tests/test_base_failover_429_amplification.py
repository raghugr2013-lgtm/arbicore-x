"""Base RPC failover / HTTP-429 retry-amplification remediation.

Root cause (established read-only against this branch):
  Public Base RPC returns a JSON-RPC error (e.g. -32016) which is non-retryable
  and raised after a single POST, so the registry fails over to Alchemy. The
  per-provider ``EthJsonRpcProvider._call`` retry loop then treats HTTP 429
  (rate-limit) exactly like a transient 5xx and retries the SAME rate-limited
  host up to ``ARBICORE_RPC_MAX_RETRIES`` (default 3 -> 4 POSTs, VPS 4 -> 5
  POSTs). This amplifies 429s against the very host that asked us to back off,
  instead of failing over quickly to a valid alternate provider.

Behavioural target (preserve provider abstraction, fail-closed, quote semantics):
  provider failure -> bounded retry -> HTTP 429 -> host cooldown
  -> avoid retry amplification -> fail closed / move to valid alternate provider

These tests pin that contract. They use no real network and no real sleeping.
"""
import os
import time

import httpx
import pytest

os.environ.setdefault("ARBICORE_RPC_BACKOFF_BASE_MS", "0")
os.environ.setdefault("ARBICORE_RPC_BACKOFF_CAP_MS", "0")

from arbicore.providers.rpc import EthJsonRpcProvider  # noqa: E402
from arbicore.providers.base import ProviderError, ProviderKind  # noqa: E402
from arbicore.providers.registry import ProviderRegistry  # noqa: E402


class _Resp:
    def __init__(self, status=200, json_body=None, headers=None):
        self.status_code = status
        self._json = json_body if json_body is not None else {
            "jsonrpc": "2.0", "id": 1, "result": "0x1"}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)

    def json(self):
        return self._json


class _Client:
    """Fake httpx client. ``script`` may be a finite list or ``repeat`` fills."""

    def __init__(self, script, repeat=None):
        self._script = list(script)
        self._repeat = repeat
        self.calls = 0

    async def post(self, url, json=None):
        self.calls += 1
        if self._script:
            item = self._script.pop(0)
        elif self._repeat is not None:
            item = self._repeat
        else:
            item = _Resp()
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self):
        pass


def _provider(monkeypatch, *, client, chain="base",
              url="https://base-mainnet.g.alchemy.com/v2/secret"):
    async def _no_sleep(*_a, **_k):
        return None
    monkeypatch.setattr("arbicore.providers.rpc.asyncio.sleep", _no_sleep)
    p = EthJsonRpcProvider(chain=chain, url=url)
    p._client = client
    return p


_RPC_ERR_32016 = {"jsonrpc": "2.0", "id": 1,
                  "error": {"code": -32016, "message": "no backend available"}}


# ---------------------------------------------------------------------------
# Provider-level: bounded 429 retry (no amplification)
# ---------------------------------------------------------------------------

async def test_429_bounded_retry_no_amplification(monkeypatch):
    """A rate-limited host must NOT be hammered 4-5 times. Bounded <= 2 POSTs."""
    client = _Client([], repeat=_Resp(429))
    p = _provider(monkeypatch, client=client)
    with pytest.raises(ProviderError) as ei:
        await p._call("eth_call", [{}, "latest"])
    assert "429" in str(ei.value)
    assert ei.value.retryable is True  # still fail-closed/failover-eligible
    assert client.calls <= 2, f"429 amplification: {client.calls} POSTs to host"


async def test_429_then_success_still_recovers(monkeypatch):
    """One bounded retry after a 429 still allows a legitimate recovery."""
    client = _Client([_Resp(429, headers={"Retry-After": "0"}), _Resp(200)])
    p = _provider(monkeypatch, client=client)
    assert await p._call("eth_blockNumber", []) == "0x1"
    assert client.calls == 2


# ---------------------------------------------------------------------------
# Provider-level: 429 -> host cooldown (don't re-POST a cooling host)
# ---------------------------------------------------------------------------

async def test_429_sets_host_cooldown_no_immediate_repost(monkeypatch):
    """After a 429, the next call on the SAME host fails fast with NO new POST."""
    client = _Client([], repeat=_Resp(429))
    p = _provider(monkeypatch, client=client)
    with pytest.raises(ProviderError):
        await p._call("eth_call", [{}, "latest"])
    posts_after_first = client.calls

    with pytest.raises(ProviderError) as ei:
        await p._call("eth_call", [{}, "latest"])
    assert client.calls == posts_after_first, "cooling host was re-POSTed"
    assert ei.value.retryable is True  # retryable -> registry fails over
    assert "cooldown" in str(ei.value).lower()


async def test_cooldown_expiry_allows_requests_again(monkeypatch):
    """Once the cooldown window elapses, the host is usable again."""
    client = _Client([_Resp(429), _Resp(429), _Resp(200)])
    p = _provider(monkeypatch, client=client)
    with pytest.raises(ProviderError):
        await p._call("eth_blockNumber", [])  # exhausts bounded 429 -> cooldown
    calls_during_cooldown_trip = client.calls

    # Simulate cooldown expiry by advancing the monotonic clock far ahead.
    base = time.monotonic()
    monkeypatch.setattr("arbicore.providers.rpc.time.monotonic",
                        lambda: base + 10_000.0)
    assert await p._call("eth_blockNumber", []) == "0x1"
    assert client.calls == calls_during_cooldown_trip + 1


async def test_5xx_retry_budget_unchanged(monkeypatch):
    """Transient 5xx keep the original (larger) retry budget — no regression."""
    os.environ["ARBICORE_RPC_MAX_RETRIES"] = "3"
    client = _Client([], repeat=_Resp(503))
    p = _provider(monkeypatch, client=client)
    with pytest.raises(ProviderError):
        await p._call("eth_call", [{}, "latest"])
    assert client.calls == 4  # 3 retries + 1 == original 5xx behaviour


# ---------------------------------------------------------------------------
# Registry-level: -32016 failover -> bounded Alchemy -> valid alternate
# ---------------------------------------------------------------------------

async def test_base_minus_32016_failover_alchemy_bounded_then_alternate(monkeypatch):
    """End-to-end: public Base -32016 -> failover; Alchemy 429 is bounded and
    cooled; a healthy alternate still serves the quote (fail-OPEN to a valid
    provider, never a fabricated quote)."""
    async def _no_sleep(*_a, **_k):
        return None
    monkeypatch.setattr("arbicore.providers.rpc.asyncio.sleep", _no_sleep)

    base_pub = EthJsonRpcProvider(
        chain="base", url="https://mainnet.base.org",
        provider_id="rpc_base_0_mainnet_base_org")
    base_pub._client = _Client([], repeat=_Resp(200, json_body=_RPC_ERR_32016))

    alchemy = EthJsonRpcProvider(
        chain="base", url="https://base-mainnet.g.alchemy.com/v2/k",
        provider_id="rpc_base_1_base-mainnet_g_alch")
    alchemy._client = _Client([], repeat=_Resp(429))

    healthy = EthJsonRpcProvider(
        chain="base", url="https://base.publicnode.com",
        provider_id="rpc_base_2_base_publicnode_com")
    healthy._client = _Client([], repeat=_Resp(
        200, json_body={"jsonrpc": "2.0", "id": 1, "result": "0xGOOD"}))

    reg = ProviderRegistry()
    reg.register(base_pub, chain="base", priority=100)
    reg.register(alchemy, chain="base", priority=101)
    reg.register(healthy, chain="base", priority=102)

    result = await reg.call(
        ProviderKind.RPC,
        lambda p: p.eth_call({}, "latest"),
        chain="base",
        max_attempts=5,
    )
    assert result == "0xGOOD"  # served by a valid alternate, not fabricated
    assert base_pub._client.calls == 1          # -32016 is non-retryable
    assert alchemy._client.calls <= 2           # bounded, no amplification
    assert alchemy._cooldown_until > time.monotonic()  # Alchemy host cooled
