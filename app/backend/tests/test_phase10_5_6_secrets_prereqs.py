"""Phase 10.5 · Secrets REST + Phase 10.6 · Wizard prereqs — unit tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from arbicore.execution.operator_wizard import check_flash_loan_prereqs


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Wizard fix_path + reason enrichment (Phase 10.6)
# --------------------------------------------------------------------------- #

class _StubKS:
    def __init__(self, engaged=False):
        self._e = engaged

    async def state(self):
        class _S:
            def to_dict(_):
                return {"engaged": self._e}
        return _S()


class _StubMode:
    def __init__(self, mode="SHADOW"):
        self._m = mode

    async def get(self, s):
        return {"mode": self._m}


class _StubWReg:
    def __init__(self, wallets=None):
        self._w = wallets or []

    async def list_all(self, chain=None, execution_role=None):
        return list(self._w)


class _StubSReg:
    def __init__(self, handles=None):
        self._h = handles or []

    async def list_handles(self):
        return list(self._h)


class _StubBal:
    async def read(self, *, chain, address):
        from arbicore.execution.wallet_balance import BalanceReading
        return BalanceReading(
            chain=chain, address=address, symbol="ETH", balance_wei=0,
            balance_native=0.0, balance_usd=None, native_price_usd=None,
            block_number=1, rpc_endpoint_redacted="stub",
            ok=True, error=None, generated_at="2026-01-01T00:00:00+00:00",
        )


class _StubNetRepo:
    def __init__(self, enabled=False, rpcs=None):
        self._e = enabled
        self._r = rpcs or []

    async def get(self):
        return {"chains_enabled": {"base": self._e},
                 "rpc_urls": {"base": self._r}}


class _StubScannerRepo:
    def __init__(self, enabled=False):
        self._e = enabled

    async def get_family(self, fid):
        return {"enabled": self._e}


class TestFlashLoanPrereqs:
    def _run_prereqs(self, **kw):
        return _run(check_flash_loan_prereqs(
            kill_switch_repo=kw.get("ks", _StubKS()),
            mode_repo=kw.get("mode", _StubMode()),
            wallet_registry=kw.get("wr", _StubWReg()),
            secret_registry=kw.get("sr", _StubSReg()),
            wallet_balance_reader=_StubBal(),
            scanner_repo=kw.get("scan", _StubScannerRepo()),
            network_repo=kw.get("net", _StubNetRepo()),
        ))

    def test_all_blocked_defaults(self):
        r = self._run_prereqs()
        assert r["ok"] is False
        keys = {c["key"] for c in r["checks"]}
        assert "base_network_enabled" in keys
        assert "wallet_registered" in keys
        assert "secret_available" in keys
        assert "executor_verified" in keys
        assert "scanner_family_enabled" in keys
        assert "mode_limited_live" in keys
        assert "kill_switch_disengaged" in keys

    def test_fix_paths_populated(self):
        r = self._run_prereqs()
        for c in r["checks"]:
            assert c.get("fix_path"), f"{c['key']} missing fix_path"

    def test_network_ready_when_configured(self):
        r = self._run_prereqs(net=_StubNetRepo(enabled=True,
                                                 rpcs=["https://mainnet.base.org"]))
        step = next(c for c in r["checks"] if c["key"] == "base_network_enabled")
        assert step["status"] == "READY"

    def test_wallet_ready_when_registered(self):
        wallet = {"wallet_id": "w1", "address": "0xabc",
                   "chain": "base", "execution_role": "gas",
                   "secret_handle_id": "sec-1"}
        r = self._run_prereqs(wr=_StubWReg([wallet]),
                                sr=_StubSReg([{"handle_id": "sec-1"}]))
        wstep = next(c for c in r["checks"] if c["key"] == "wallet_registered")
        sstep = next(c for c in r["checks"] if c["key"] == "secret_available")
        assert wstep["status"] == "READY"
        assert sstep["status"] == "READY"

    def test_kill_switch_engaged_blocks(self):
        r = self._run_prereqs(ks=_StubKS(engaged=True))
        step = next(c for c in r["checks"] if c["key"] == "kill_switch_disengaged")
        assert step["status"] == "BLOCKED"
        assert "kill_switch_disengaged" in r["unmet"]

    def test_mode_wait_when_shadow(self):
        r = self._run_prereqs(mode=_StubMode(mode="SHADOW"))
        step = next(c for c in r["checks"] if c["key"] == "mode_limited_live")
        assert step["status"] == "WAIT"

    def test_scanner_family_wait_when_disabled(self):
        r = self._run_prereqs(scan=_StubScannerRepo(enabled=False))
        step = next(c for c in r["checks"] if c["key"] == "scanner_family_enabled")
        assert step["status"] == "WAIT"

    def test_scanner_family_ready_when_enabled(self):
        r = self._run_prereqs(scan=_StubScannerRepo(enabled=True))
        step = next(c for c in r["checks"] if c["key"] == "scanner_family_enabled")
        assert step["status"] == "READY"


# --------------------------------------------------------------------------- #
# Wizard step enrichment (fix_path + reason on every step)
# --------------------------------------------------------------------------- #

class TestWizardStepEnrichment:
    def test_every_step_has_fix_path_and_reason(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
        from arbicore.execution.operator_wizard import build_wizard_state
        r = _run(build_wizard_state(
            kill_switch_repo=_StubKS(),
            mode_repo=_StubMode(),
            wallet_registry=_StubWReg(),
            secret_registry=_StubSReg(),
            wallet_balance_reader=_StubBal(),
            certifier=None,
        ))
        for s in r["steps"]:
            assert s.get("fix_path"), f"step {s['key']} missing fix_path"
            assert s.get("reason"), f"step {s['key']} missing reason"
