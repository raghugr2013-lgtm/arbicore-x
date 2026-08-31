"""Regression: RPC registry lifecycle / Base provider availability.

Reproduces + guards the P0 bug where a fresh process saw
get_registry_rpc_provider("base") == None despite bootstrap succeeding.
No signing/broadcast. Read-only provider wiring only.
"""
import importlib

import pytest

import arbicore.providers.rpc_failover as F
import arbicore.providers.bootstrap as B
from arbicore.providers.registry import ProviderRegistry

TWO = "https://base-mainnet.example/key,https://mainnet.base.org"


@pytest.fixture(autouse=True)
def _fresh_process(monkeypatch):
    """Emulate a fresh process: no default registry set yet."""
    F.set_default_registry(None)
    monkeypatch.setenv("PROVIDER_RPC_URLS_BASE", TWO)
    yield
    F.set_default_registry(None)


def _base_rpc(summary):
    return [r for r in summary["rpc"] if r.get("chain") == "base"]


def test_env_two_endpoints_register_two_base_rpc():
    summary = B.bootstrap(ProviderRegistry())
    assert summary["totals"]["rpc"] >= 2
    assert len(_base_rpc(summary)) == 2


def test_bootstrap_sets_process_default_registry():
    reg = ProviderRegistry()
    assert F.get_default_registry() is None
    B.bootstrap(reg)
    assert F.get_default_registry() is reg


def test_get_provider_after_explicit_bootstrap():
    B.bootstrap(ProviderRegistry())
    assert F.get_registry_rpc_provider("base") is not None


def test_fresh_process_autoensures_base_provider():
    # No bootstrap called in this "process": the previous None-returning path.
    assert F.get_default_registry() is None
    prov = F.get_registry_rpc_provider("base")
    assert prov is not None                      # deterministic, auto-ensured
    assert F.get_default_registry() is not None   # default now populated


def test_ensure_default_registry_is_idempotent():
    r1 = B.ensure_default_registry()
    r2 = B.ensure_default_registry()
    assert r1 is r2 is F.get_default_registry()


def test_failover_has_two_base_candidates_after_ensure():
    B.ensure_default_registry()
    reg = F.get_default_registry()
    base_rpc = [h for h in reg._health.values()
                if getattr(h, "chain", None) == "base"
                and getattr(getattr(h, "kind", None), "value", None) == "rpc"]
    assert len(base_rpc) >= 2                     # failover has >1 target


def test_no_fabricated_provider_when_registry_unavailable(monkeypatch):
    # If ensure fails, must fail closed to None (never a fake provider).
    F.set_default_registry(None)
    monkeypatch.setattr(B, "ensure_default_registry",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert F.get_registry_rpc_provider("base") is None
