"""HTTP-429 host-scoped cooldown + bounded retry for the REAL quote path:

    QuoterRegistry.quote_route() -> DEX backend -> execution/quoter.py::_eth_call

Covers surgical acceptance tests (TEST 1–10):
  1. 429 failover A→B without waiting 60s
  2. cooled host not hammered (zero HTTP to A)
  3. multi-host A→B→C fallback
  4. all hosts fail → fail-closed
  5. cooldown expiry via monotonic clock
  6. 429 does not consume full retry budget
  7. transport error failover unchanged
  8. genuine execution revert does not failover
  9. credential redaction in telemetry
 10. concurrent workers do not amplify 429 retries
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from eth_abi import encode as abi_encode

os.environ.setdefault("ARBICORE_RPC_MIN_INTERVAL_MS", "0")

from arbicore.execution import quoter as Q  # noqa: E402

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

_GOOD_RESULT_HEX = "0x" + abi_encode(
    ["uint256", "uint160", "uint32", "uint256"],
    [2000 * 10 ** 6, 0, 0, 120_000]).hex()


class _FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _batch_ok_body():
    return [
        {"jsonrpc": "2.0", "id": 1, "result": _GOOD_RESULT_HEX},
        {"jsonrpc": "2.0", "id": 2, "result": "0x100"},
    ]


class _Transport:
    """Fake ``_post_json`` that counts POSTs per host and serves per-host behaviour."""

    def __init__(self, behaviour):
        # behaviour: host -> "429" | "ok" | "transport" | "revert"
        self.behaviour = behaviour
        self.posts = {}

    async def __call__(self, rpc_url, payload, timeout):
        host = Q._host_key(rpc_url)
        self.posts[host] = self.posts.get(host, 0) + 1
        mode = self.behaviour.get(host, "ok")
        if mode == "429":
            return _FakeResp(429, {})
        if mode == "transport":
            raise Q.httpx.ConnectError("simulated transport failure")
        if mode == "revert":
            return _FakeResp(200, [
                {"jsonrpc": "2.0", "id": 1,
                 "error": {"code": 3, "message": "execution reverted: STF"}},
                {"jsonrpc": "2.0", "id": 2, "result": "0x100"},
            ])
        return _FakeResp(200, _batch_ok_body())


def _install(monkeypatch, transport, candidates, *, max_retries_default=4):
    async def _no_sleep(*_a, **_k):
        return None
    monkeypatch.setattr(Q.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(Q, "_post_json", transport)
    monkeypatch.setattr(Q, "_RPC_MAX_RETRIES", max_retries_default)
    monkeypatch.setattr(Q, "_RPC_MAX_RETRIES_429", 1, raising=False)
    monkeypatch.setattr(Q, "_HOST_BATCH_OK", {})
    monkeypatch.setattr(Q, "_RPC_LAST_TS", {})
    monkeypatch.setattr(Q, "_RPC_HOST_COOLDOWN_UNTIL", {}, raising=False)
    Q.reset_rpc_429_telemetry()
    reg = Q.QuoterRegistry(backends=[Q.UniV3QuoterV2()], cache_ttl_s=0.0,
                           verify_chain_identity=False)
    monkeypatch.setattr(reg, "_rpc_url_candidates", lambda chain=None: list(candidates))
    return reg


def _hop():
    return {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
            "amount_in_wei": 10 ** 18, "fee": 500}


ALCHEMY = "https://base-mainnet.g.alchemy.com/v2/SECRET_KEY_DO_NOT_LOG"
HEALTHY = "https://base.publicnode.com/"
ANKR = "https://rpc.ankr.com/base/SECRET_ANKR"
PUBLIC3 = "https://base-rpc.public.blastapi.io/"


# ---------------------------------------------------------------------------
# TEST 1 — 429 failover: A → bounded retry → cooldown → B succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1_429_failover_to_healthy_alternate(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429", Q._host_key(HEALTHY): "ok"})
    reg = _install(monkeypatch, t, [ALCHEMY, HEALTHY])
    t0 = time.monotonic()
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    elapsed = time.monotonic() - t0
    assert rq.status == "ok"
    assert rq.final_amount_out_wei == 2000 * 10 ** 6
    assert t.posts.get(Q._host_key(HEALTHY), 0) == 1
    assert t.posts[Q._host_key(ALCHEMY)] <= 2
    assert Q._rpc_host_cooled(ALCHEMY) is True
    assert elapsed < 5.0, "candidate must not wait for 60s cooldown"


# ---------------------------------------------------------------------------
# TEST 2 — cooled host is not hammered (zero HTTP to A)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_2_cooled_host_zero_http(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429", Q._host_key(HEALTHY): "ok"})
    reg = _install(monkeypatch, t, [ALCHEMY, HEALTHY])
    monkeypatch.setattr(Q, "_RPC_RATE_LIMIT_COOLDOWN_S", 1000.0, raising=False)

    await reg.quote_route(chain="base", hops=[_hop()])
    posts_a = t.posts.get(Q._host_key(ALCHEMY), 0)
    assert posts_a >= 1
    assert Q._rpc_host_cooled(ALCHEMY) is True

    # Reset POST counters; A remains cooled. Prefer reorder → B first.
    t.posts.clear()
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "ok"
    assert t.posts.get(Q._host_key(ALCHEMY), 0) == 0, (
        "cooled host A received an HTTP POST")
    assert t.posts.get(Q._host_key(HEALTHY), 0) >= 1


# ---------------------------------------------------------------------------
# TEST 3 — multi-host A→B→C without waiting for either cooldown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_3_multi_host_fallback_a_b_c(monkeypatch):
    t = _Transport({
        Q._host_key(ALCHEMY): "429",
        Q._host_key(ANKR): "429",
        Q._host_key(PUBLIC3): "ok",
    })
    reg = _install(monkeypatch, t, [ALCHEMY, ANKR, PUBLIC3])
    t0 = time.monotonic()
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    elapsed = time.monotonic() - t0
    assert rq.status == "ok"
    assert t.posts[Q._host_key(ALCHEMY)] <= 2
    assert t.posts[Q._host_key(ANKR)] <= 2
    assert t.posts.get(Q._host_key(PUBLIC3), 0) == 1
    assert elapsed < 5.0


# ---------------------------------------------------------------------------
# TEST 4 — all hosts fail → fail-closed (no fabricated quote)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_4_all_hosts_fail_closed(monkeypatch):
    urls = [ALCHEMY, ANKR, HEALTHY, PUBLIC3,
            "https://base.llamarpc.com/", "https://1rpc.io/base"]
    t = _Transport({Q._host_key(u): "429" for u in urls})
    reg = _install(monkeypatch, t, urls)
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "fallback:break_even"
    assert rq.status != "ok"
    for u in urls:
        assert t.posts.get(Q._host_key(u), 0) <= 2


# ---------------------------------------------------------------------------
# TEST 5 — cooldown expiry via monotonic clock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_5_cooldown_expiry(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429"})
    reg = _install(monkeypatch, t, [ALCHEMY])
    monkeypatch.setattr(Q, "_RPC_RATE_LIMIT_COOLDOWN_S", 60.0, raising=False)

    await reg.quote_route(chain="base", hops=[_hop()])
    host = Q._host_key(ALCHEMY)
    assert host in Q._RPC_HOST_COOLDOWN_UNTIL
    assert Q._rpc_host_cooled(ALCHEMY) is True

    # Advance monotonic past cooldown without wall-clock sleep.
    Q._RPC_HOST_COOLDOWN_UNTIL[host] = time.monotonic() - 1.0
    assert Q._rpc_host_cooled(ALCHEMY) is False

    t.posts.clear()
    # Still 429, but eligible again → POST happens.
    await reg.quote_route(chain="base", hops=[_hop()])
    assert t.posts.get(host, 0) >= 1


# ---------------------------------------------------------------------------
# TEST 6 — 429 does not use full _RPC_MAX_RETRIES budget
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_6_429_bounded_not_full_retry_budget(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429"})
    reg = _install(monkeypatch, t, [ALCHEMY], max_retries_default=4)
    monkeypatch.setattr(Q, "_RPC_MAX_RETRIES_429", 1, raising=False)
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "fallback:break_even"
    # max_retries for sole candidate is full budget (4) but 429 bound is 1
    # → at most 2 POSTs (attempt 0 + one retry).
    assert t.posts[Q._host_key(ALCHEMY)] <= 2
    assert t.posts[Q._host_key(ALCHEMY)] < 5


# ---------------------------------------------------------------------------
# TEST 7 — transport error failover unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_7_transport_error_failover(monkeypatch):
    t = _Transport({
        Q._host_key(ALCHEMY): "transport",
        Q._host_key(HEALTHY): "ok",
    })
    reg = _install(monkeypatch, t, [ALCHEMY, HEALTHY])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "ok"
    assert t.posts.get(Q._host_key(HEALTHY), 0) == 1
    # Transport failure must NOT put the host into 429 cooldown.
    assert Q._rpc_host_cooled(ALCHEMY) is False
    snap = Q.rpc_429_telemetry_snapshot()
    assert snap["http_429"] == 0
    assert snap["cooldown_gate"] == 0


# ---------------------------------------------------------------------------
# TEST 8 — genuine execution revert does not failover
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_8_execution_revert_no_failover(monkeypatch):
    t = _Transport({
        Q._host_key(ALCHEMY): "revert",
        Q._host_key(HEALTHY): "ok",
    })
    reg = _install(monkeypatch, t, [ALCHEMY, HEALTHY])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    # Genuine DEX revert stops the loop — must NOT advance to HEALTHY.
    assert rq.status != "ok"
    assert "execution reverted" in (rq.hops[0].error or "").lower()
    assert t.posts.get(Q._host_key(HEALTHY), 0) == 0
    assert Q._rpc_host_cooled(ALCHEMY) is False


# ---------------------------------------------------------------------------
# TEST 9 — credential redaction in cooldown/RPC telemetry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_9_credential_redaction(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429", Q._host_key(HEALTHY): "ok"})
    reg = _install(monkeypatch, t, [ALCHEMY, HEALTHY])
    await reg.quote_route(chain="base", hops=[_hop()])
    snap = Q.rpc_429_telemetry_snapshot()
    blob = str(snap)
    assert "SECRET_KEY_DO_NOT_LOG" not in blob
    assert "/v2/" not in blob
    assert ALCHEMY not in blob
    assert Q._host_key(ALCHEMY) in snap["by_host"]
    assert "base" in snap["by_chain"]
    # Fingerprint is sha256 of key segment, never the raw key.
    assert "SECRET_KEY_DO_NOT_LOG" not in str(snap.get("by_fp"))
    assert snap["http_429"] >= 1
    # cooldown_gate is distinct from http_429 (not counted as HTTP 429).
    assert "cooldown_gate" in snap


# ---------------------------------------------------------------------------
# TEST 10 — concurrent workers: cooldown prevents hammering; B still serves
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_10_concurrent_workers_no_amplification(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429", Q._host_key(HEALTHY): "ok"})
    reg = _install(monkeypatch, t, [ALCHEMY, HEALTHY])
    monkeypatch.setattr(Q, "_RPC_RATE_LIMIT_COOLDOWN_S", 1000.0, raising=False)

    # First wave establishes cooldown on A.
    await reg.quote_route(chain="base", hops=[_hop()])
    posts_after_prime = t.posts.get(Q._host_key(ALCHEMY), 0)
    assert posts_after_prime <= 2
    assert Q._rpc_host_cooled(ALCHEMY) is True

    t.posts.clear()
    results = await asyncio.gather(*[
        reg.quote_route(chain="base", hops=[_hop()]) for _ in range(8)
    ])
    assert all(r.status == "ok" for r in results)
    # Cooled A must receive ZERO additional POSTs under concurrency.
    assert t.posts.get(Q._host_key(ALCHEMY), 0) == 0
    assert t.posts.get(Q._host_key(HEALTHY), 0) >= 1
    snap = Q.rpc_429_telemetry_snapshot()
    # Concurrent cool-host hits are cooldown_gate, not new http_429 storms.
    assert snap["cooldown_gate"] >= 0


# ---------------------------------------------------------------------------
# Tip-compatible aliases (befb14e suite names preserved for regression)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quote_route_single_candidate_429_is_bounded(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429"})
    reg = _install(monkeypatch, t, [ALCHEMY])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "fallback:break_even"
    assert t.posts[Q._host_key(ALCHEMY)] <= 2


@pytest.mark.asyncio
async def test_quote_route_429_sets_host_cooldown(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429"})
    reg = _install(monkeypatch, t, [ALCHEMY])
    monkeypatch.setattr(Q, "_RPC_RATE_LIMIT_COOLDOWN_S", 1000.0, raising=False)
    await reg.quote_route(chain="base", hops=[_hop()])
    posts_after_first = t.posts[Q._host_key(ALCHEMY)]
    await reg.quote_route(chain="base", hops=[_hop()])
    assert t.posts[Q._host_key(ALCHEMY)] == posts_after_first


@pytest.mark.asyncio
async def test_quote_route_fails_over_to_healthy_alternate(monkeypatch):
    await test_1_429_failover_to_healthy_alternate(monkeypatch)


@pytest.mark.asyncio
async def test_quote_route_all_rate_limited_fails_closed(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429", Q._host_key(ANKR): "429"})
    reg = _install(monkeypatch, t, [ALCHEMY, ANKR])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "fallback:break_even"
    assert t.posts[Q._host_key(ALCHEMY)] <= 2
    assert t.posts[Q._host_key(ANKR)] <= 2


@pytest.mark.asyncio
async def test_quote_route_healthy_single_post(monkeypatch):
    t = _Transport({Q._host_key(HEALTHY): "ok"})
    reg = _install(monkeypatch, t, [HEALTHY])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "ok"
    assert rq.final_amount_out_wei == 2000 * 10 ** 6
    assert t.posts[Q._host_key(HEALTHY)] == 1
