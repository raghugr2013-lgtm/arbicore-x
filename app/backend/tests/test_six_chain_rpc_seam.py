"""Six-chain operator-RPC configuration seam — focused offline regression.

Validates (no network, no secrets):
  * all six chains have independent economic + discovery env keys,
  * a missing operator RPC FAILS CLOSED (not operator-authoritative),
  * a configured RPC is consumed by the CORRECT chain only (no cross-chain
    leakage — the base-only ``ARBICORE_RPC_URL`` alias never resolves elsewhere),
  * certification reports emit NO RPC URL values (secret-safe),
  * Base behaves exactly as before,
  * the five non-Base chains can independently become operator-authoritative.
"""
from __future__ import annotations

import json

import pytest

from arbicore.config.persistent import resolve_rpc_url_from_env
from arbicore.runtime import multichain_readiness as MR

SIX = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]
SENTINEL = "https://SECRET-OPERATOR-RPC.internal/DO-NOT-LEAK/xyz123"


def _clear_all(monkeypatch):
    for c in SIX:
        u = c.upper()
        for k in (f"PROVIDER_RPC_URLS_{u}", f"PROVIDER_RPC_URL_{u}",
                  f"ARBICORE_RPC_URL_{u}", f"{u}_RPC_URL"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)


# ── all six chains supported + keyed independently ─────────────────────────
def test_all_six_chains_supported():
    supported = MR.supported_networks()
    for c in SIX:
        assert c in supported


# ── missing operator RPC => fail closed ────────────────────────────────────
def test_missing_rpc_fails_closed(monkeypatch):
    _clear_all(monkeypatch)
    for c in SIX:
        assert MR.rpc_explicitly_configured(c) is False
        assert MR.provider_registry_rpc_configured(c) is False
        assert resolve_rpc_url_from_env(c) is None


# ── configured RPC consumed by the correct chain only ──────────────────────
def test_provider_rpc_consumed_per_chain(monkeypatch):
    for c in SIX:
        _clear_all(monkeypatch)
        monkeypatch.setenv(f"PROVIDER_RPC_URLS_{c.upper()}", SENTINEL)
        # target chain becomes economic + discovery configured
        assert MR.provider_registry_rpc_configured(c) is True
        assert MR.rpc_explicitly_configured(c) is True
        # every OTHER chain stays fail-closed
        for other in SIX:
            if other != c:
                assert MR.provider_registry_rpc_configured(other) is False
                assert MR.rpc_explicitly_configured(other) is False


def test_discovery_rpc_resolved_per_chain(monkeypatch):
    for c in SIX:
        _clear_all(monkeypatch)
        monkeypatch.setenv(f"ARBICORE_RPC_URL_{c.upper()}", SENTINEL)
        assert resolve_rpc_url_from_env(c) == SENTINEL
        for other in SIX:
            if other != c:
                assert resolve_rpc_url_from_env(other) is None


# ── no cross-chain leakage from the base-only global alias ─────────────────
def test_base_only_global_alias_never_leaks(monkeypatch):
    _clear_all(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL", SENTINEL)   # base-only global alias
    assert resolve_rpc_url_from_env("base") == SENTINEL
    for other in ["ethereum", "arbitrum", "optimism", "polygon", "bnb"]:
        assert resolve_rpc_url_from_env(other) is None            # NO leakage
        assert MR.rpc_explicitly_configured(other) is False


def test_base_precedence_preserved(monkeypatch):
    _clear_all(monkeypatch)
    monkeypatch.setenv("BASE_RPC_URL", "legacy")
    assert resolve_rpc_url_from_env("base") == "legacy"
    monkeypatch.setenv("ARBICORE_RPC_URL", "generic")
    assert resolve_rpc_url_from_env("base") == "generic"          # global beats legacy
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "chain")
    assert resolve_rpc_url_from_env("base") == "chain"            # chain beats global


# ── five non-Base chains independently operator-authoritative ──────────────
def test_five_chains_independently_authoritative(monkeypatch):
    _clear_all(monkeypatch)
    non_base = ["ethereum", "arbitrum", "optimism", "polygon", "bnb"]
    for c in non_base:
        monkeypatch.setenv(f"PROVIDER_RPC_URLS_{c.upper()}", SENTINEL + c)
    for c in non_base:
        assert MR.provider_registry_rpc_configured(c) is True
    assert MR.provider_registry_rpc_configured("base") is False   # untouched → closed


# ── certification reports never emit RPC URL values (secret-safe) ──────────
def test_readiness_report_has_no_rpc_values(monkeypatch):
    _clear_all(monkeypatch)
    for c in SIX:
        monkeypatch.setenv(f"PROVIDER_RPC_URLS_{c.upper()}", SENTINEL)
        monkeypatch.setenv(f"ARBICORE_RPC_URL_{c.upper()}", SENTINEL)
    report = MR.build_multichain_readiness_report()
    blob = json.dumps(report)
    assert SENTINEL not in blob
    # booleans are still surfaced (configuration is acknowledged, values are not)
    assert report["networks"]["ethereum"]["economic_rpc_configured"] is True
    assert report["networks"]["base"]["rpc_configured"] is True


# ── config template documents all twelve names, no real values ─────────────
def test_env_template_lists_all_twelve_names():
    from pathlib import Path
    tmpl = Path(__file__).resolve().parents[3] / "deployment" / "cert" / ".env.example"
    text = tmpl.read_text()
    for c in SIX:
        assert f"PROVIDER_RPC_URLS_{c.upper()}=" in text
        assert f"ARBICORE_RPC_URL_{c.upper()}=" in text
    # names only — no populated value after any of the required keys
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(("PROVIDER_RPC_URLS_", "ARBICORE_RPC_URL_")):
            assert line.endswith("="), f"template must not carry a value: {line}"
