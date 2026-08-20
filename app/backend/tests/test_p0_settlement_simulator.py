"""P0 — Aerodrome settlement simulator (item #2/#5) + RPC capability gating."""
import asyncio
import pytest

import arbicore.execution.settlement_simulator as sim_mod
from arbicore.execution.settlement_simulator import SettlementSimulator
from arbicore.execution.aerodrome_settlement import AerodromeSettlementError
from eth_abi import encode as abi_encode

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def _amounts_hex(amounts):
    return "0x" + abi_encode(["uint256[]"], [amounts]).hex()


def _patch_eth_call(monkeypatch, amounts, block_number=123):
    async def fake(rpc_url, *, to, data, block="latest", timeout=12.0, with_block_number=True):
        return _amounts_hex(amounts), block_number, None
    monkeypatch.setattr(sim_mod, "_eth_call", fake)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_profitable_route_passes(monkeypatch):
    # 0.01 WETH -> ... -> 0.011 WETH (repays + clear profit over gas)
    _patch_eth_call(monkeypatch, [10**16, 25_000_000, 110 * 10**14])
    s = SettlementSimulator(rpc_url="http://x")
    out = _run(s.simulate(
        hops=[{"token_in": WETH, "token_out": USDC, "stable": False},
              {"token_in": USDC, "token_out": WETH, "stable": False}],
        amount_in_wei=10**16, token_decimals=18, token_usd=2500.0,
        gas_cost_usd=1.0, token_allowlist=[WETH, USDC],
        recipient="0x0000000000000000000000000000000000000001"))
    assert out["ran"] is True and out["passed"] is True
    assert out["repayment_ok"] is True and out["net_profit_usd"] > 0
    assert out["signed"] is False and out["broadcast"] is False


def test_unprofitable_route_rejected(monkeypatch):
    _patch_eth_call(monkeypatch, [10**16, 25_000_000, 99 * 10**14])   # returns < principal
    s = SettlementSimulator(rpc_url="http://x")
    out = _run(s.simulate(
        hops=[{"token_in": WETH, "token_out": USDC, "stable": False},
              {"token_in": USDC, "token_out": WETH, "stable": False}],
        amount_in_wei=10**16, token_decimals=18, token_usd=2500.0,
        gas_cost_usd=1.0, token_allowlist=[WETH, USDC],
        recipient="0x0000000000000000000000000000000000000001"))
    assert out["ran"] is True and out["passed"] is False
    assert "repay" in out["reason"]


def test_quote_failure_is_absolute_rejection(monkeypatch):
    async def fail(rpc_url, *, to, data, block="latest", timeout=12.0, with_block_number=True):
        return None, None, {"code": -32000, "message": "reverted"}
    monkeypatch.setattr(sim_mod, "_eth_call", fail)
    s = SettlementSimulator(rpc_url="http://x")
    out = _run(s.simulate(
        hops=[{"token_in": WETH, "token_out": USDC, "stable": False}],
        amount_in_wei=10**16, token_decimals=18, token_usd=2500.0,
        token_allowlist=[WETH, USDC],
        recipient="0x0000000000000000000000000000000000000001"))
    assert out["passed"] is False and out["ran"] is False


def test_non_allowlisted_token_rejected_before_rpc(monkeypatch):
    _patch_eth_call(monkeypatch, [10**16, 10**16])
    s = SettlementSimulator(rpc_url="http://x")
    out = _run(s.simulate(
        hops=[{"token_in": WETH, "token_out": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}],
        amount_in_wei=10**16, token_decimals=18, token_usd=2500.0,
        token_allowlist=[WETH, USDC],
        recipient="0x0000000000000000000000000000000000000001"))
    assert out["passed"] is False and out["stage"] == "encode"


def test_replay_pins_block(monkeypatch):
    _patch_eth_call(monkeypatch, [10**16, 25_000_000, 101 * 10**14], block_number=50000000)
    s = SettlementSimulator(rpc_url="http://x")
    out = _run(s.replay(
        block_number=50000000,
        hops=[{"token_in": WETH, "token_out": USDC, "stable": False},
              {"token_in": USDC, "token_out": WETH, "stable": False}],
        amount_in_wei=10**16, token_decimals=18, token_usd=2500.0,
        token_allowlist=[WETH, USDC],
        recipient="0x0000000000000000000000000000000000000001"))
    assert out["replay_block_number"] == 50000000
    assert out["block"] == hex(50000000)
