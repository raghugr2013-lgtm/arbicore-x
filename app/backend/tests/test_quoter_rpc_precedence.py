"""Audit 2026-06 — QuoterRegistry RPC resolution precedence.

Regression guard for the Base SHADOW dry-run blocker: the quoter previously read
ONLY the generic ``ARBICORE_RPC_URL`` env, so a Base deployment configured with
the canonical per-chain key ``ARBICORE_RPC_URL_BASE`` (what the TVL/aero/price
paths already use via ``resolve_rpc_url_from_env``) left the quoter blind and
every hop degraded to ``fallback:rpc_error`` → routes unpriceable → Gate 7/8
never saw a genuine quote. The fix makes ``_rpc_url`` fall back to the canonical
precedence resolver. No fabricated default: unset ⇒ None (fail-closed).
"""
from __future__ import annotations

import pytest

from arbicore.execution.quoter import QuoterRegistry

ENV_KEYS = ("ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE", "BASE_RPC_URL")


def _clear(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def test_generic_env_takes_precedence(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://generic.example")
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://base.example")
    assert QuoterRegistry()._rpc_url("base") == "https://generic.example"


def test_per_chain_base_key_resolves_when_generic_unset(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://base.example")
    # This is the exact dry-run scenario that previously returned None.
    assert QuoterRegistry()._rpc_url("base") == "https://base.example"
    assert QuoterRegistry()._rpc_url() == "https://base.example"


def test_unset_is_fail_closed_none(monkeypatch):
    _clear(monkeypatch)
    assert QuoterRegistry()._rpc_url("base") is None


@pytest.mark.asyncio
async def test_quote_route_no_longer_reports_unconfigured_with_base_key(monkeypatch):
    # With only the per-chain key set, quote_route must NOT emit the
    # "ARBICORE_RPC_URL not configured" fallback reason (it resolves the rpc).
    # We point it at an unroutable host so the network read fails fast, but the
    # failure must be a real rpc read error, not the "not configured" branch.
    _clear(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "http://127.0.0.1:9")  # closed port
    q = QuoterRegistry()
    rq = await q.quote_route(chain="base", hops=[{
        "dex": "uniswap_v3",
        "token_in": "0x4200000000000000000000000000000000000006",
        "token_out": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "amount_in_wei": 10 ** 18, "fee": 500}])
    reasons = " ".join(
        (getattr(h, "error", "") or "") for h in rq.hops)
    assert "not configured" not in reasons
