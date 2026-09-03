"""Regression tests for P1 Portfolio/Capital data-truth (no zero coercion).

Unwired portfolio sources must report available=False with **null** USD totals
(UI renders "—"), never a fabricated $0. Capital live balances must report
total_value_usd=None when the on-chain source is unavailable, and a genuine
confirmed zero (source ok) must stay 0.
"""
import asyncio
import importlib

server = importlib.import_module("server")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_portfolio_stubs_unavailable_not_zero():
    checks = {
        "deployable": (server.v2_deployable(), ["total_deployable_usd", "total_utilised_usd", "total_capital_usd", "utilisation_pct"]),
        "treasury": (server.v2_treasury(), ["total_usd"]),
        "exposure": (server.v2_exposure(), ["total_usd"]),
        "allocation": (server.v2_allocation(), ["total_target_usd", "total_actual_usd"]),
    }
    for name, (coro, usd_fields) in checks.items():
        d = _run(coro)
        assert d["available"] is False, f"{name}: expected available False"
        assert d.get("unavailable_reason"), f"{name}: missing reason"
        for f in usd_fields:
            assert d[f] is None, f"{name}.{f} must be None (UNAVAILABLE), not 0"


def test_portfolio_list_stubs_null_totals():
    for coro in (server.v2_positions(), server.v2_balances(), server.v2_transfers(), server.v2_ledger()):
        d = _run(coro)
        assert d["available"] is False
        assert d["total"] is None  # unknown count, not 0
        assert d["items"] == []


def test_capital_balances_unavailable_when_source_down():
    from arbicore.capital.wallet_intelligence import WalletIntelligenceEngine

    class _FakeNative:
        def to_dict(self):
            # ok=False → source unavailable
            return {"symbol": "ETH", "balance_native": None, "balance_wei": 0,
                    "balance_usd": None, "block_number": None,
                    "rpc_endpoint_redacted": None, "ok": False}

    class _FakeReader:
        async def read(self, *, chain, address):
            return _FakeNative()

    eng = WalletIntelligenceEngine(rpc_url="", balance_reader=_FakeReader(), chain="base")
    out = _run(eng._live_balances_impl("0x0000000000000000000000000000000000000001"))
    assert out["available"] is False
    assert out["total_value_usd"] is None, "unavailable source must not coerce total to $0"
    assert out["unavailable_reason"]


def test_capital_balances_genuine_zero_stays_zero():
    from arbicore.capital.wallet_intelligence import WalletIntelligenceEngine

    class _FakeNative:
        def to_dict(self):
            # ok=True, real zero balance
            return {"symbol": "ETH", "balance_native": 0.0, "balance_wei": 0,
                    "balance_usd": 0.0, "block_number": 123,
                    "rpc_endpoint_redacted": "base-rpc", "ok": True}

    class _FakeReader:
        async def read(self, *, chain, address):
            return _FakeNative()

    eng = WalletIntelligenceEngine(rpc_url="https://x", balance_reader=_FakeReader(), chain="base")
    out = _run(eng._live_balances_impl("0x0000000000000000000000000000000000000001"))
    assert out["available"] is True
    assert out["total_value_usd"] == 0.0  # confirmed zero stays 0


def test_build_identity_reports_real_sha():
    server._BUILD_IDENTITY = None
    ident = server._resolve_build_identity()
    assert ident["git_sha"] and ident["git_sha"] != "unknown"
    assert "app_version" in ident and "build_time" in ident and "runtime_env" in ident
