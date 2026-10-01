"""H06 safety remediation — the new EVM eth_call seam MUST enforce the same
canonical operator-RPC gate (``rpc_explicitly_configured``) as the rest of the
codebase. An unconfigured operator RPC must FAIL CLOSED (return ``None``); no
implicit/public-default RPC, no Base substitution, no fabricated provider.

Cursor CONDITIONAL-PASS finding addressed: ``make_evm_eth_call_from_env`` was a
parallel, ungated duplicate of the canonical ``make_eth_call_for_chain_from_env``.
It is now a thin alias to that gated implementation.
"""
import pytest

from arbicore.searcher.runtime import (
    make_evm_eth_call_from_env,
    make_eth_call_for_chain_from_env,
)

_RPC_KEYS = ("PROVIDER_RPC_URLS_{C}", "PROVIDER_RPC_URL_{C}",
             "ARBICORE_RPC_URL_{C}", "{C}_RPC_URL")


def _clear_chain_rpc(monkeypatch, chain):
    for tmpl in _RPC_KEYS:
        monkeypatch.delenv(tmpl.format(C=chain.upper()), raising=False)


def test_unconfigured_operator_rpc_fails_closed(monkeypatch):
    _clear_chain_rpc(monkeypatch, "arbitrum")
    # No operator RPC for arbitrum → the new H06 seam must return None.
    assert make_evm_eth_call_from_env("arbitrum") is None
    # And it must behave identically to the canonical gated implementation.
    assert make_eth_call_for_chain_from_env("arbitrum") is None


def test_configured_operator_rpc_returns_callable(monkeypatch):
    _clear_chain_rpc(monkeypatch, "arbitrum")
    monkeypatch.setenv("ARBITRUM_RPC_URL", "https://arb.operator.example/rpc")
    seam = make_evm_eth_call_from_env("arbitrum")
    assert seam is not None and callable(seam)


def test_never_falls_back_to_base(monkeypatch):
    # Only Base is configured; a non-Base request must NOT borrow Base's RPC.
    _clear_chain_rpc(monkeypatch, "arbitrum")
    _clear_chain_rpc(monkeypatch, "optimism")
    monkeypatch.setenv("BASE_RPC_URL", "https://base.operator.example/rpc")
    assert make_evm_eth_call_from_env("arbitrum") is None
    assert make_evm_eth_call_from_env("optimism") is None


def test_alias_delegates_to_canonical_gate():
    # Structural guarantee: the H06 seam reuses the canonical gate rather than a
    # parallel implementation (no second, weaker eth_call path).
    import inspect
    src = inspect.getsource(make_evm_eth_call_from_env)
    assert "make_eth_call_for_chain_from_env" in src
    assert "get_registry_rpc_provider" not in src  # no ungated direct provider
