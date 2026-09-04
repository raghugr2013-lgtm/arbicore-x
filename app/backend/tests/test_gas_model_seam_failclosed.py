"""Regression — BaseGasModel.from_env() fail-closed without a configured Base RPC.

The Base all-in-cost gate (M3 controlled-live) must DENY (return None) unless the
operator EXPLICITLY configured a Base RPC endpoint. A hardcoded public default
(providers.rpc.DEFAULT_RPC_URLS['base']) auto-registered by the provider
bootstrap must NOT satisfy the gate — otherwise a controlled-live trade would be
priced against an implicit public endpoint the operator never sanctioned.

Deterministic + offline: no network, no signing, no broadcast, no Mongo.
Logically separate from P0-3 (Base UniV3 liquidity eligibility).
"""
from __future__ import annotations

import asyncio

from arbicore.chains.gas_model import BaseGasModel
from arbicore.searcher.base_all_in_cost import (
    base_rpc_explicitly_configured,
    make_base_all_in_cost_estimator_from_env,
)

_RPC_ENVS = ("PROVIDER_RPC_URLS_BASE", "PROVIDER_RPC_URL_BASE")


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_no_configured_base_rpc_is_failclosed(monkeypatch):
    for k in _RPC_ENVS:
        monkeypatch.delenv(k, raising=False)

    assert base_rpc_explicitly_configured() is False
    assert make_base_all_in_cost_estimator_from_env() is None

    gm = BaseGasModel.from_env()
    assert gm.chain == "base"
    # Even with valid gas_units + eth_usd, the gate DENIES (no configured RPC).
    assert _run(gm.all_in_cost(
        gross_profit_usd=1000.0, borrow_amount_usd=10_000.0,
        notional_usd=10_000.0, gas_units=250_000, eth_usd=3000.0)) is None


def test_public_default_does_not_count_as_configured(monkeypatch):
    # Whatever the auto-bootstrapped registry default is, only an explicit
    # operator env counts — the helper stays False when neither env is set.
    for k in _RPC_ENVS:
        monkeypatch.delenv(k, raising=False)
    assert base_rpc_explicitly_configured() is False


def test_explicit_singular_env_counts_as_configured(monkeypatch):
    monkeypatch.delenv("PROVIDER_RPC_URLS_BASE", raising=False)
    monkeypatch.setenv("PROVIDER_RPC_URL_BASE", "https://base.example.operator")
    assert base_rpc_explicitly_configured() is True
    # Estimator is now built (a callable) rather than fail-closed None.
    assert callable(make_base_all_in_cost_estimator_from_env())
    assert BaseGasModel.from_env()._estimator is not None


def test_explicit_plural_env_counts_as_configured(monkeypatch):
    monkeypatch.delenv("PROVIDER_RPC_URL_BASE", raising=False)
    monkeypatch.setenv("PROVIDER_RPC_URLS_BASE",
                       "https://a.example,https://b.example")
    assert base_rpc_explicitly_configured() is True
    assert callable(make_base_all_in_cost_estimator_from_env())


def test_blank_env_is_not_configured(monkeypatch):
    monkeypatch.setenv("PROVIDER_RPC_URL_BASE", "   ")
    monkeypatch.setenv("PROVIDER_RPC_URLS_BASE", "")
    assert base_rpc_explicitly_configured() is False
    assert make_base_all_in_cost_estimator_from_env() is None
