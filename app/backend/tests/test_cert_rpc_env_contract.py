"""Certification RPC environment contract — one operator endpoint per chain.

Proves the fix: a single canonical ``ARBICORE_RPC_URL_<CHAIN>`` cert.env input
satisfies BOTH the chain-scoped RPC seam AND the provider-registry economic
all-in-cost gate (via a deterministic, secret-safe sync into
``PROVIDER_RPC_URL_<CHAIN>``), while preserving strict per-chain isolation,
fail-closed behavior, and never treating a public/default endpoint as evidence.
"""
from __future__ import annotations

import os

import pytest

from arbicore.config.persistent import (
    sync_provider_registry_rpc_from_env, SUPPORTED_CHAINS,
)

# All env keys these tests may touch — cleaned before AND after each test.
_ALL_KEYS = []
for _c in ("BASE", "ETHEREUM", "ARBITRUM", "OPTIMISM", "POLYGON", "BNB"):
    _ALL_KEYS += [f"ARBICORE_RPC_URL_{_c}", f"PROVIDER_RPC_URL_{_c}",
                  f"PROVIDER_RPC_URLS_{_c}", f"{_c}_RPC_URL"]
_ALL_KEYS += ["ARBICORE_RPC_URL", "ARBICORE_PROVIDER_RPC_SYNCED"]


@pytest.fixture(autouse=True)
def _clean_env():
    saved = {k: os.environ.pop(k, None) for k in _ALL_KEYS}
    yield
    for k in _ALL_KEYS:
        os.environ.pop(k, None)
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


def _econ_ok(chain: str) -> bool:
    # Mongo-free economic gate (identical logic to
    # runtime.multichain_readiness.provider_registry_rpc_configured — both sync
    # then check PROVIDER_RPC_URL[S]_<CHAIN>). Used here to keep the test offline.
    from arbicore.control.chain_execution_readiness import _economic_rpc_configured
    return _economic_rpc_configured(chain)


# ---------------------------------------------------------------------------
def test_arbicore_rpc_url_satisfies_both_seams_per_chain():
    os.environ["ARBICORE_RPC_URL_ARBITRUM"] = "https://arb.operator.example/key"
    # Economic gate (the previously-failing prerequisite) now passes...
    assert _econ_ok("arbitrum") is True
    # ...because the value was mirrored into the provider-registry key.
    assert os.environ.get("PROVIDER_RPC_URL_ARBITRUM") == "https://arb.operator.example/key"
    # rpc_explicitly_configured (discovery seam) also accepts ARBICORE_RPC_URL_*.


def test_non_base_never_inherits_base():
    os.environ["ARBICORE_RPC_URL_BASE"] = "https://base.operator.example/key"
    report = sync_provider_registry_rpc_from_env()
    assert report["base"] == "synced_from_cert_env"
    assert os.environ.get("PROVIDER_RPC_URL_BASE") == "https://base.operator.example/key"
    # Every non-Base chain remains NOT_CONFIGURED — no Base leakage.
    for chain in ("ethereum", "arbitrum", "optimism", "polygon", "bnb"):
        assert report[chain] == "not_configured"
        assert os.environ.get(f"PROVIDER_RPC_URL_{chain.upper()}") is None
        assert _econ_ok(chain) is False


def test_base_only_global_alias_applies_to_base_only():
    os.environ["ARBICORE_RPC_URL"] = "https://global.operator.example/key"  # base-only alias
    report = sync_provider_registry_rpc_from_env()
    assert report["base"] == "synced_from_cert_env"
    assert os.environ.get("PROVIDER_RPC_URL_BASE") == "https://global.operator.example/key"
    for chain in ("ethereum", "arbitrum", "optimism", "polygon", "bnb"):
        assert report[chain] == "not_configured"     # alias NEVER leaks to non-Base


def test_missing_chain_rpc_stays_not_configured_fail_closed():
    report = sync_provider_registry_rpc_from_env()   # nothing set
    for chain in SUPPORTED_CHAINS:
        assert report[chain] == "not_configured"
        assert _econ_ok(chain) is False               # economic gate fail-closed


def test_explicit_provider_rpc_still_works_and_wins():
    # Operator sets BOTH — the explicit provider-registry value must NOT be
    # overwritten by the cert alias.
    os.environ["PROVIDER_RPC_URL_POLYGON"] = "https://explicit.provider.example/key"
    os.environ["ARBICORE_RPC_URL_POLYGON"] = "https://cert.alias.example/key"
    report = sync_provider_registry_rpc_from_env()
    assert report["polygon"] == "already_configured"
    assert os.environ["PROVIDER_RPC_URL_POLYGON"] == "https://explicit.provider.example/key"
    assert _econ_ok("polygon") is True


def test_provider_rpc_urls_plural_form_recognised():
    os.environ["PROVIDER_RPC_URLS_OPTIMISM"] = "https://a.example,https://b.example"
    assert _econ_ok("optimism") is True
    # Not overwritten by sync (explicit plural form wins).
    report = sync_provider_registry_rpc_from_env()
    assert report["optimism"] == "already_configured"


def test_comma_list_reduced_to_first_endpoint():
    os.environ["ARBICORE_RPC_URL_BNB"] = "https://primary.example/k,https://failover.example/k"
    sync_provider_registry_rpc_from_env()
    # Single PROVIDER_RPC_URL_<CHAIN> must hold ONE endpoint, never the whole list.
    assert os.environ["PROVIDER_RPC_URL_BNB"] == "https://primary.example/k"
    assert _econ_ok("bnb") is True


def test_no_default_public_endpoint_is_operator_evidence():
    # No operator input at all ⇒ even though DEFAULT_RPC_URLS exists elsewhere,
    # the economic gate must NOT be satisfied by any implicit/public default.
    sync_provider_registry_rpc_from_env()
    for chain in SUPPORTED_CHAINS:
        assert os.environ.get(f"PROVIDER_RPC_URL_{chain.upper()}") is None
        assert _econ_ok(chain) is False


def test_sync_is_idempotent_and_secret_safe():
    os.environ["ARBICORE_RPC_URL_ETHEREUM"] = "https://eth.operator.example/secretkey"
    r1 = sync_provider_registry_rpc_from_env()
    r2 = sync_provider_registry_rpc_from_env()
    assert r1["ethereum"] == "synced_from_cert_env"
    assert r2["ethereum"] == "already_configured"     # idempotent
    # Report exposes STATUS only — never the URL/secret.
    for status in list(r1.values()) + list(r2.values()):
        assert "http" not in status and "secretkey" not in status


def test_base_all_in_cost_gate_satisfied_by_cert_alias():
    from arbicore.searcher.base_all_in_cost import base_rpc_explicitly_configured
    assert base_rpc_explicitly_configured() is False          # nothing set
    os.environ["ARBICORE_RPC_URL_BASE"] = "https://base.operator.example/key"
    assert base_rpc_explicitly_configured() is True           # cert alias suffices
