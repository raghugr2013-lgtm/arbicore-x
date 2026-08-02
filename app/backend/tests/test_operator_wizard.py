"""Operator Wizard aggregator + Executor verifier — unit tests (offline).

Every test avoids the network: the RPC-dependent helpers are exercised
only for their offline branches (no ARBICORE_RPC_URL set), which is the
production baseline for the pre-deploy operator.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.execution.operator_wizard import (
    verify_executor,
    check_rpc,
    latest_broadcast_receipts,
    build_wizard_state,
)


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Executor verification — offline paths
# --------------------------------------------------------------------------- #

class TestVerifyExecutor:
    def test_missing_address_and_env_is_blocked(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
        r = _run(verify_executor())
        assert r["overall_status"] == "BLOCKED"
        assert r["ready"] is False
        assert r["checks"]["address_configured"]["status"] == "BLOCKED"

    def test_env_address_used_when_arg_missing(self, monkeypatch):
        monkeypatch.setenv(
            "ARBICORE_EXECUTOR_ADDRESS_BASE",
            "0x00000000000000000000000000000000feedFACE",
        )
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        monkeypatch.delenv("ARBICORE_RPC_URL_BASE", raising=False)
        r = _run(verify_executor())
        assert r["address"].lower().endswith("feedface")
        assert r["checks"]["address_configured"]["status"] == "READY"
        # Without RPC, the whole thing degrades to WAIT (not BLOCKED).
        assert r["overall_status"] == "WAIT"
        assert r["checks"]["rpc_available"]["status"] == "WAIT"

    def test_invalid_address_rejected(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
        r = _run(verify_executor(address="not-an-address"))
        assert r["overall_status"] == "BLOCKED"
        assert r["checks"]["address_configured"]["status"] == "BLOCKED"


# --------------------------------------------------------------------------- #
# RPC check — offline branch
# --------------------------------------------------------------------------- #

class TestCheckRpc:
    def test_no_rpc_is_blocked(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        monkeypatch.delenv("ARBICORE_RPC_URL_BASE", raising=False)
        r = _run(check_rpc())
        assert r["status"] == "BLOCKED"
        assert "not set" in r["detail"].lower()


# --------------------------------------------------------------------------- #
# Post-trade aggregator — synthetic plans repo
# --------------------------------------------------------------------------- #

class _StubPlansRepo:
    def __init__(self, plans):
        self._plans = plans

    async def list_recent(self, limit: int = 200):
        return list(self._plans)[:limit]


class TestPostTradeLatest:
    def test_empty(self):
        r = _run(latest_broadcast_receipts(plans_repo=_StubPlansRepo([])))
        assert r["count"] == 0
        assert r["latest"] is None

    def test_extracts_broadcast_result(self):
        plans = [
            {
                "plan_id": "plan-1", "strategy": "flash_loan_arbitrage",
                "chain": "base", "mode": "LIMITED_LIVE",
                "broadcast_last_result": {
                    "mode": "LIMITED_LIVE",
                    "broadcast_sent": True,
                    "tx_hash": "0x" + "ab" * 32,
                    "gas_used": 320_000,
                    "gas_price_wei": 100_000_000,
                    "nonce": 4,
                    "preflight_ok": True,
                    "at": "2026-08-01T00:00:00+00:00",
                },
                "borrow_amount_wei": 10 ** 17,
                "borrow_token": "0xToken",
                "recipient": "0xExec",
                "profit_recipient": "0xBurner",
            },
            {"plan_id": "plan-2", "strategy": "flash_loan_arbitrage"},  # no result
        ]
        r = _run(latest_broadcast_receipts(plans_repo=_StubPlansRepo(plans)))
        assert r["count"] == 1
        latest = r["latest"]
        assert latest["plan_id"] == "plan-1"
        assert latest["broadcast_sent"] is True
        assert latest["tx_hash"].startswith("0xabab")
        assert latest["mode"] == "LIMITED_LIVE"


# --------------------------------------------------------------------------- #
# Wizard aggregator — synthetic collaborators
# --------------------------------------------------------------------------- #

class _StubKillSwitch:
    def __init__(self, engaged=False, reason="test"):
        self._engaged = engaged
        self._reason = reason

    async def state(self):
        class _S:
            def to_dict(_self):
                return {"engaged": self._engaged, "reason": self._reason}
        return _S()


class _StubModeRepo:
    def __init__(self, mode="SHADOW"):
        self._mode = mode

    async def get(self, strategy):
        return {"mode": self._mode, "strategy": strategy}


class _StubWalletRegistry:
    def __init__(self, wallets=None):
        self._wallets = wallets or []

    async def list_all(self, chain=None, execution_role=None):
        out = self._wallets
        if chain:
            out = [w for w in out if w.get("chain") == chain]
        if execution_role:
            out = [w for w in out if w.get("execution_role") == execution_role]
        return out


class _StubSecretRegistry:
    def __init__(self, handles=None):
        self._handles = handles or []

    async def list_handles(self):
        return list(self._handles)


class _StubBalanceReader:
    def __init__(self, native=0.02):
        self._native = native

    async def read(self, *, chain, address):
        from arbicore.execution.wallet_balance import BalanceReading
        return BalanceReading(
            chain=chain, address=address, symbol="ETH",
            balance_wei=int(self._native * 1e18),
            balance_native=self._native, balance_usd=None,
            native_price_usd=None, block_number=1,
            rpc_endpoint_redacted="stub",
            ok=True, error=None, generated_at="2026-01-01T00:00:00+00:00",
        )


class TestWizardAggregator:
    def test_all_blocked_when_nothing_configured(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        monkeypatch.delenv("ARBICORE_RPC_URL_BASE", raising=False)
        monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
        r = _run(build_wizard_state(
            kill_switch_repo=_StubKillSwitch(engaged=False),
            mode_repo=_StubModeRepo(mode="SHADOW"),
            wallet_registry=_StubWalletRegistry([]),
            secret_registry=_StubSecretRegistry([]),
            wallet_balance_reader=_StubBalanceReader(),
            certifier=None,
        ))
        assert r["overall_status"] == "BLOCKED"
        assert r["ready_to_broadcast"] is False
        # Expect specific blockers.
        keys_blocked = set(r["blockers"])
        assert "rpc" in keys_blocked
        assert "wallet" in keys_blocked
        assert "executor" in keys_blocked

    def test_kill_switch_engaged_blocks(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
        r = _run(build_wizard_state(
            kill_switch_repo=_StubKillSwitch(engaged=True, reason="drill"),
            mode_repo=_StubModeRepo(),
            wallet_registry=_StubWalletRegistry([]),
            secret_registry=_StubSecretRegistry([]),
            wallet_balance_reader=_StubBalanceReader(),
            certifier=None,
        ))
        assert "kill_switch" in r["blockers"]

    def test_step_count_is_ten(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        r = _run(build_wizard_state(
            kill_switch_repo=_StubKillSwitch(),
            mode_repo=_StubModeRepo(),
            wallet_registry=_StubWalletRegistry([]),
            secret_registry=_StubSecretRegistry([]),
            wallet_balance_reader=_StubBalanceReader(),
            certifier=None,
        ))
        # 10 primary steps + 1 aggregate final row
        keys = [s["key"] for s in r["steps"]]
        assert keys[-1] == "final"
        expected = {"rpc", "wallet", "secret", "gas_balance", "executor",
                    "executor_verify", "kill_switch", "certification",
                    "mode", "final"}
        assert expected.issubset(set(keys))

    def test_wallet_registered_but_no_secret_is_blocked(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        wallet = {"wallet_id": "w1", "address": "0xabc", "chain": "base",
                   "execution_role": "gas", "secret_handle_id": None}
        r = _run(build_wizard_state(
            kill_switch_repo=_StubKillSwitch(),
            mode_repo=_StubModeRepo(),
            wallet_registry=_StubWalletRegistry([wallet]),
            secret_registry=_StubSecretRegistry([]),
            wallet_balance_reader=_StubBalanceReader(),
            certifier=None,
        ))
        assert "secret" in r["blockers"]

    def test_mode_wait_when_not_limited_live(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        r = _run(build_wizard_state(
            kill_switch_repo=_StubKillSwitch(),
            mode_repo=_StubModeRepo(mode="SHADOW"),
            wallet_registry=_StubWalletRegistry([]),
            secret_registry=_StubSecretRegistry([]),
            wallet_balance_reader=_StubBalanceReader(),
            certifier=None,
        ))
        mode_step = next(s for s in r["steps"] if s["key"] == "mode")
        assert mode_step["status"] == "WAIT"
