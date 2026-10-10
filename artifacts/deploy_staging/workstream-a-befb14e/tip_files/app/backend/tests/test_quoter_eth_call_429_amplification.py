"""HTTP-429 retry-amplification remediation for the REAL quote path:

    live_quote_provider -> QuoterRegistry.quote_route() -> DEX backend
        -> execution/quoter.py::_eth_call  (module-level, direct httpx)

This is the path Cursor's root-cause investigation identified ("around
quoter.py"). It is DISTINCT from providers/rpc.py::EthJsonRpcProvider (hardened
separately in 2b86cda). Here the amplification is: QuoterRegistry.quote_route
gives the LAST/only RPC candidate the full ``_RPC_MAX_RETRIES`` budget (default
4 -> 5 POSTs) on HTTP 429, with NO per-host cooldown, so a rate-limited host
(e.g. Alchemy) is hammered and re-hammered across hops/cycles.

These tests exercise the real quote_route -> UniV3QuoterV2.quote_hop -> _eth_call
chain with a POST-counting fake transport. They are deterministic: no real
network, no real sleeping.
"""
import os

import pytest
from eth_abi import encode as abi_encode

os.environ.setdefault("ARBICORE_RPC_MIN_INTERVAL_MS", "0")

from arbicore.execution import quoter as Q  # noqa: E402

# Base token addresses (real, checksummable) — quote_hop checksums these.
WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# A valid UniV3 QuoterV2 return: (amountOut, sqrtPriceAfter, ticks, gasEstimate)
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
        # behaviour: host -> "429" | "ok"
        self.behaviour = behaviour
        self.posts = {}

    async def __call__(self, rpc_url, payload, timeout):
        host = Q._host_key(rpc_url)
        self.posts[host] = self.posts.get(host, 0) + 1
        mode = self.behaviour.get(host, "ok")
        if mode == "429":
            return _FakeResp(429, {})
        return _FakeResp(200, _batch_ok_body())


def _install(monkeypatch, transport, candidates, *, max_retries_default=4):
    async def _no_sleep(*_a, **_k):
        return None
    monkeypatch.setattr(Q.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(Q, "_post_json", transport)
    monkeypatch.setattr(Q, "_RPC_MAX_RETRIES", max_retries_default)
    # reset process-global per-host state so tests don't leak into each other
    monkeypatch.setattr(Q, "_HOST_BATCH_OK", {})
    monkeypatch.setattr(Q, "_RPC_LAST_TS", {})
    monkeypatch.setattr(Q, "_RPC_HOST_COOLDOWN_UNTIL", {}, raising=False)
    reg = Q.QuoterRegistry(backends=[Q.UniV3QuoterV2()], cache_ttl_s=0.0,
                           verify_chain_identity=False)
    monkeypatch.setattr(reg, "_rpc_url_candidates", lambda chain=None: list(candidates))
    return reg


def _hop():
    return {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
            "amount_in_wei": 10 ** 18, "fee": 500}


ALCHEMY = "https://base-mainnet.g.alchemy.com/v2/key"
HEALTHY = "https://base.publicnode.com/"
ANKR = "https://rpc.ankr.com/base/key"


# ---------------------------------------------------------------------------
# 1. Bounded 429 retry — no amplification (RED on current code: 5 POSTs)
# ---------------------------------------------------------------------------

async def test_quote_route_single_candidate_429_is_bounded(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429"})
    reg = _install(monkeypatch, t, [ALCHEMY])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    # fail-closed: a rate-limited host yields NO successful quote (downstream
    # live_quote_provider rejects any status != "ok"; break_even is in==out).
    assert rq.status == "fallback:break_even"
    assert rq.status != "ok"
    # the whole point: the rate-limited host must not be hammered 4-5x
    assert t.posts[Q._host_key(ALCHEMY)] <= 2, (
        f"429 amplification via quote_route: "
        f"{t.posts[Q._host_key(ALCHEMY)]} POSTs to the rate-limited host")


# ---------------------------------------------------------------------------
# 2. 429 -> host cooldown: a second quote does NOT re-POST the cooling host
#    (RED on current code: no cooldown -> host re-POSTed)
# ---------------------------------------------------------------------------

async def test_quote_route_429_sets_host_cooldown(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429"})
    reg = _install(monkeypatch, t, [ALCHEMY])
    monkeypatch.setattr(Q, "_RPC_RATE_LIMIT_COOLDOWN_S", 1000.0, raising=False)

    await reg.quote_route(chain="base", hops=[_hop()])
    posts_after_first = t.posts[Q._host_key(ALCHEMY)]

    await reg.quote_route(chain="base", hops=[_hop()])
    assert t.posts[Q._host_key(ALCHEMY)] == posts_after_first, (
        "cooling host was re-POSTed on the next quote (no cooldown)")


# ---------------------------------------------------------------------------
# 3. Prompt failover to a valid alternate RPC endpoint (invariant to preserve)
# ---------------------------------------------------------------------------

async def test_quote_route_fails_over_to_healthy_alternate(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429", Q._host_key(HEALTHY): "ok"})
    reg = _install(monkeypatch, t, [ALCHEMY, HEALTHY])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "ok"                       # served by the alternate
    assert rq.final_amount_out_wei == 2000 * 10 ** 6
    assert t.posts.get(Q._host_key(HEALTHY), 0) == 1
    # Alchemy (non-final) is bounded regardless; after the fix it is also cooled.
    assert t.posts[Q._host_key(ALCHEMY)] <= 2


# ---------------------------------------------------------------------------
# 4. Fail-closed when ALL providers are rate-limited (no fabricated quote)
# ---------------------------------------------------------------------------

async def test_quote_route_all_rate_limited_fails_closed(monkeypatch):
    t = _Transport({Q._host_key(ALCHEMY): "429", Q._host_key(ANKR): "429"})
    reg = _install(monkeypatch, t, [ALCHEMY, ANKR])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "fallback:break_even"
    assert rq.status != "ok"            # never a false success
    # each rate-limited host bounded (no amplification on either)
    assert t.posts[Q._host_key(ALCHEMY)] <= 2
    assert t.posts[Q._host_key(ANKR)] <= 2


# ---------------------------------------------------------------------------
# 5. Non-429 success path unchanged (no regression)
# ---------------------------------------------------------------------------

async def test_quote_route_healthy_single_post(monkeypatch):
    t = _Transport({Q._host_key(HEALTHY): "ok"})
    reg = _install(monkeypatch, t, [HEALTHY])
    rq = await reg.quote_route(chain="base", hops=[_hop()])
    assert rq.status == "ok"
    assert rq.final_amount_out_wei == 2000 * 10 ** 6
    assert t.posts[Q._host_key(HEALTHY)] == 1      # one batch POST, no retries
