"""Tests for the VPS certification harness itself — every fail-closed boundary
and every status (PASS/FAIL/BLOCKED/UNKNOWN/NOT_CONFIGURED). Deterministic;
eth_chainId reads and env are stubbed. VPS-unavailable is never PASS.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.certification import vps_harness as H


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _stub_reader(mapping):
    async def _r(url, timeout=8.0):
        return mapping.get(url)
    return _r


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # start from a clean RPC/sim/price env for each test
    for c in ("BASE", "ETHEREUM", "ARBITRUM", "OPTIMISM", "POLYGON", "BNB"):
        monkeypatch.delenv(f"ARBICORE_RPC_URL_{c}", raising=False)
        monkeypatch.delenv(f"{c}_RPC_URL", raising=False)
        monkeypatch.delenv(f"PROVIDER_RPC_URLS_{c}", raising=False)
    monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
    monkeypatch.delenv("ARBICORE_PRICE_FEED_ENABLED", raising=False)
    monkeypatch.delenv("ARBICORE_BORROW_SIZER_ENABLED", raising=False)
    monkeypatch.delenv("ARBICORE_SIM_METHOD", raising=False)
    H._q._HOST_CHAIN_ID.clear()
    yield


def test_status_values_are_valid():
    assert {H.PASS, H.FAIL, H.BLOCKED, H.UNKNOWN, H.NOT_CONFIGURED} == \
        {"PASS", "FAIL", "BLOCKED", "UNKNOWN", "NOT_CONFIGURED"}


def test_rpc_not_configured_when_no_endpoint():
    r = _run(H.check_rpc_and_chainid("ethereum"))
    assert r["status"] == H.NOT_CONFIGURED


def test_rpc_blocked_when_unreachable(monkeypatch):
    monkeypatch.setenv("ARBICORE_RPC_URL_ETHEREUM", "https://eth-dead")
    monkeypatch.setattr(H._q, "_read_chain_id", _stub_reader({}))  # all None
    r = _run(H.check_rpc_and_chainid("ethereum"))
    assert r["status"] == H.BLOCKED  # unreachable is NOT a pass


def test_rpc_fail_on_wrong_chain_id(monkeypatch):
    monkeypatch.setenv("ARBICORE_RPC_URL_ETHEREUM", "https://liar")
    monkeypatch.setattr(H._q, "_read_chain_id",
                        _stub_reader({"https://liar": 8453}))  # base id on eth
    r = _run(H.check_rpc_and_chainid("ethereum"))
    assert r["status"] == H.FAIL


def test_rpc_pass_single_endpoint_failover_unknown(monkeypatch):
    monkeypatch.setenv("ARBICORE_RPC_URL_ETHEREUM", "https://eth-a")
    monkeypatch.setattr(H._q, "_read_chain_id",
                        _stub_reader({"https://eth-a": 1}))
    r = _run(H.check_rpc_and_chainid("ethereum"))
    assert r["status"] == H.PASS
    assert r["evidence"]["failover"] == H.UNKNOWN


def test_rpc_pass_with_failover(monkeypatch):
    monkeypatch.setenv("ARBICORE_RPC_URL_ETHEREUM", "https://eth-a,https://eth-b")
    monkeypatch.setattr(H._q, "_read_chain_id",
                        _stub_reader({"https://eth-a": 1, "https://eth-b": 1}))
    r = _run(H.check_rpc_and_chainid("ethereum"))
    assert r["status"] == H.PASS
    assert r["evidence"]["failover"] == H.PASS


def test_h05_not_configured_by_default():
    assert H.check_h05_sizer()["status"] == H.NOT_CONFIGURED


def test_h05_pass_when_enabled(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_BORROW_SIZER_ENABLED", "true")
    assert H.check_h05_sizer()["status"] == H.PASS


def test_h08_blocked_for_undeployed_chain():
    assert _run(H.check_h08_receiver("ethereum"))["status"] == H.BLOCKED


def test_h08_blocked_when_no_supported_providers():
    # base sepolia 84532 is deployed but declares no supported_providers
    r = _run(H.check_h08_receiver(84532))
    assert r["status"] == H.BLOCKED
    assert r["evidence"]["deployed"] is True
    assert r["evidence"]["supported_providers"] == []


def test_h08_unknown_when_providers_declared(monkeypatch):
    from arbicore.execution.receiver_capability import ReceiverCapability
    fake = ReceiverCapability(
        chain="84532", deployed=True, address="0x" + "de" * 20,
        receiver_version="v1", abi_version="v1", version_verified=True,
        bytecode_verified=True, supported_providers=["balancer_v2"],
        constructor_args={}, note="declared")
    monkeypatch.setattr(H, "receiver_capability", lambda c: fake)
    r = _run(H.check_h08_receiver(84532))
    assert r["status"] == H.UNKNOWN  # declared but still needs on-chain verify


def test_h09_blocked_without_exact_method():
    r = H.check_h09_simulation_prereqs()
    assert r["status"] == H.BLOCKED
    assert r["evidence"]["certifying_method"] is False


def test_h09_unknown_with_exact_method(monkeypatch):
    monkeypatch.setenv("ARBICORE_SIM_METHOD", "atomic_exact")
    r = H.check_h09_simulation_prereqs()
    assert r["status"] == H.UNKNOWN
    assert r["evidence"]["certifying_method"] is True


def test_vps_unavailable_never_pass_end_to_end():
    # in-pod with no operator RPC/sim/receiver: NO check may be PASS.
    results = []
    for c in H.SIX_CHAINS:
        results.append(_run(H.check_rpc_and_chainid(c)))
        results.append(H.check_chain_scoped_isolation(c))
        results.append(H.check_h07_composition(c))
    results.append(H.check_h05_sizer())
    results.append(_run(H.check_h08_receiver("84532")))
    results.append(H.check_h09_simulation_prereqs())
    statuses = {r["status"] for r in results}
    assert H.PASS not in statuses, f"VPS-unavailable produced a PASS: {statuses}"
    assert statuses <= {H.NOT_CONFIGURED, H.BLOCKED, H.UNKNOWN, H.FAIL}
