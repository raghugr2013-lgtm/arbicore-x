"""Phase-2D — comma-separated RPC configuration consistency (regression).

The historical "verifier reports no bytecode" defect was a comma-separated
ARBICORE_RPC_URL being POSTed as ONE malformed URL. Every RPC consumer must
select the FIRST endpoint (or enumerate them), never use the joined string.
This test pins that invariant across ALL consumers so they can never drift.
"""
import os

import pytest

from arbicore.config.persistent import first_rpc_endpoint, resolve_rpc_url_from_env
from arbicore.execution.gas import RpcGasOracle
from arbicore.execution.simulation import EthCallSimulator
from arbicore.execution.wallet_balance import _rpc_urls_for

CSV = "https://rpc-a.example/key1, https://rpc-b.example/key2"


@pytest.fixture
def csv_env(monkeypatch):
    for k in ("ARBICORE_RPC_URL_BASE", "BASE_RPC_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ARBICORE_RPC_URL", CSV)
    yield


def test_first_rpc_endpoint_selector():
    assert first_rpc_endpoint("a,b,c") == "a"
    assert first_rpc_endpoint(" a , b ") == "a"
    assert first_rpc_endpoint(",,x") == "x"
    assert first_rpc_endpoint("solo") == "solo"
    assert first_rpc_endpoint("") is None
    assert first_rpc_endpoint(None) is None


def test_resolver_selects_first(csv_env):
    assert resolve_rpc_url_from_env("base") == "https://rpc-a.example/key1"


def test_gas_oracle_selects_first(csv_env):
    assert RpcGasOracle()._rpc_url == "https://rpc-a.example/key1"


def test_simulator_selects_first(csv_env):
    assert EthCallSimulator()._rpc_url == "https://rpc-a.example/key1"


def test_wallet_balance_enumerates_then_first(csv_env):
    urls = _rpc_urls_for("base")
    assert urls[0] == "https://rpc-a.example/key1"
    assert "https://rpc-b.example/key2" in urls  # both endpoints kept, not joined


def test_no_consumer_returns_joined_string(csv_env):
    joined = CSV  # the raw, wrong value
    assert resolve_rpc_url_from_env("base") != joined
    assert RpcGasOracle()._rpc_url != joined
    assert EthCallSimulator()._rpc_url != joined
    assert joined not in _rpc_urls_for("base")
