"""Executor V2 backend tests (Freeze v1.1) — calldata, interface mapping,
version-aware settlement binding. Fully offline/deterministic; no RPC, no
signing, no broadcast. Distinguishes mocks from any real-chain evidence
(there is NO real-chain evidence here — these are pure encoding/logic tests)."""
import json
import os
import tempfile

import pytest

from arbicore.execution import executor_interface_v2 as EI2
from arbicore.execution import calldata_v2 as C2
from arbicore.execution import executor_registry as exreg
from arbicore.execution.settlement_v2_binding import (
    evaluate_settlement_for_deployed_receiver as bind,
)
from arbicore.execution.settlement_dispatcher import Verdict


FAR = 2 ** 40  # far-future deadline
RECIP = "0x000000000000000000000000000000000000BEEF"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
WETH = "0x4200000000000000000000000000000000000006"
UNIV3_ROUTER_BASE = "0x2626664c2603336E57B271c5C0b26F421741e481"


# ---- interface / selector invariants ----

def test_v1_selectors_preserved_exactly():
    assert EI2.SEL_ENTRY_BALANCER == "0x64ba4bc1"
    assert EI2.SEL_ENTRY_AAVE == "0x4343d8b2"


def test_morpho_callback_selector_is_canonical():
    # onMorphoFlashLoan(uint256,bytes) — verified against morpho-blue source.
    assert EI2.SEL_CB_MORPHO == "0x31f57072"


def test_venue_enum_order_matches_solidity():
    assert EI2.VenueV2.UNISWAP_V3 == 0
    assert EI2.VenueV2.UNISWAP_V2 == 1
    assert EI2.VenueV2.AERODROME_CLASSIC == 2
    assert EI2.VenueV2.AERODROME_SLIPSTREAM == 3
    assert EI2.VenueV2.ALGEBRA_V3 == 4


def test_backend_venue_family_mapping():
    assert EI2.family_for_backend_venue("sushiswap_v3") == EI2.VenueV2.UNISWAP_V3
    assert EI2.family_for_backend_venue("aerodrome") == EI2.VenueV2.AERODROME_CLASSIC
    assert EI2.family_for_backend_venue("camelot_v3") == EI2.VenueV2.ALGEBRA_V3
    with pytest.raises(ValueError):
        EI2.family_for_backend_venue("nonexistent_dex")


def test_initial_scope_failclosed():
    assert EI2.in_initial_scope(8453, provider="morpho_blue", venue="aerodrome")
    assert EI2.in_initial_scope(1, provider="balancer_v2", venue="sushiswap_v2")
    # Base does NOT include sushiswap in scope
    assert not EI2.in_initial_scope(8453, venue="sushiswap_v2")
    # Out-of-scope chains always fail closed
    assert not EI2.in_initial_scope(42161, provider="balancer_v2", venue="uniswap_v3")
    assert not EI2.in_initial_scope(56, venue="pancakeswap_v3")


# ---- deterministic calldata ----

def _hop():
    return {
        "venue": "uniswap_v3", "router": UNIV3_ROUTER_BASE,
        "token_in": USDC, "token_out": WETH, "fee_or_tick_spacing": 500,
        "amount_in_wei": 1000, "amount_out_min_wei": 0, "deadline": FAR,
    }


def test_userdata_v2_deterministic():
    a = C2.build_user_data_v2(hops=[_hop()], profit_recipient=RECIP, min_profit_wei=25_000000, deadline=FAR)
    b = C2.build_user_data_v2(hops=[_hop()], profit_recipient=RECIP, min_profit_wei=25_000000, deadline=FAR)
    assert a == b and a.startswith("0x") and len(a) > 2


def test_encode_heads_selectors():
    ud = C2.build_user_data_v2(hops=[_hop()], profit_recipient=RECIP, min_profit_wei=0, deadline=FAR)
    bal = C2.encode_execute_balancer_v2(tokens=[USDC], amounts=[1000], user_data_hex=ud)
    aave = C2.encode_execute_aave_v2(asset=USDC, amount_wei=1000, user_data_hex=ud)
    morpho = C2.encode_execute_morpho_v2(token=USDC, amount_wei=1000, user_data_hex=ud)
    assert bal.selector_hex == "0x64ba4bc1"
    assert aave.selector_hex == "0x4343d8b2"
    assert morpho.selector_hex == EI2.SEL_ENTRY_MORPHO
    assert bal.calldata_hex.startswith("0x64ba4bc1")


def test_encode_v2_head_failclosed_for_unknown_provider():
    ud = C2.build_user_data_v2(hops=[_hop()], profit_recipient=RECIP, min_profit_wei=0, deadline=FAR)
    with pytest.raises(NotImplementedError):
        C2.encode_v2_head_for_provider(provider="uniswap_v3", token=USDC, amount_wei=1, user_data_hex=ud)


def test_empty_hops_rejected():
    with pytest.raises(ValueError):
        C2.build_user_data_v2(hops=[], profit_recipient=RECIP, min_profit_wei=0, deadline=FAR)


# ---- version-aware settlement binding (fail-closed) ----

def _registry_file(record):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump({"schema": "arbicore.executor_deployments/v2", "deployments": record}, fh)
    return path


def test_binding_v1_receiver_univ3_only(monkeypatch):
    path = _registry_file({"8453": {
        "network": "base_mainnet", "address": "0x0E3FDb0F0E615A517588BD44ac6C78Bb7615927f",
        "receiver_version": "v1", "deploy_status": "success",
        "supported_providers": ["balancer_v2", "aave_v3"], "supported_dexes": ["uniswap_v3"],
    }})
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH", path)
    ok = bind(flash_provider="balancer_v2", swap_venues=["uniswap_v3"], chain="base")
    assert ok.verdict == Verdict.EXECUTABLE
    # Aerodrome on a V1 receiver must REQUIRE_NEW_RECEIVER (not executable).
    ne = bind(flash_provider="balancer_v2", swap_venues=["aerodrome"], chain="base")
    assert ne.verdict == Verdict.REQUIRES_NEW_RECEIVER
    os.unlink(path)


def test_binding_v2_receiver_enables_scoped_venues(monkeypatch):
    path = _registry_file({"8453": {
        "network": "base_mainnet", "address": "0x00000000000000000000000000000000000000V2".replace("V2", "22"),
        "receiver_version": "v2", "deploy_status": "success",
        "supported_providers": ["balancer_v2", "aave_v3", "morpho_blue"],
        "supported_dexes": ["uniswap_v3", "aerodrome", "aerodrome_slipstream"],
    }})
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH", path)
    # Now Aerodrome + Morpho are executable on a V2 receiver within scope.
    d = bind(flash_provider="morpho_blue", swap_venues=["aerodrome"], chain="base")
    assert d.verdict == Verdict.EXECUTABLE
    d2 = bind(flash_provider="balancer_v2", swap_venues=["uniswap_v3", "aerodrome_slipstream"], chain="base")
    assert d2.verdict == Verdict.EXECUTABLE
    os.unlink(path)


def test_binding_v2_intersects_with_initial_scope(monkeypatch):
    # A V2 record that (wrongly) declares an out-of-scope venue must NOT become
    # executable — capability is intersection(record, frozen scope).
    path = _registry_file({"8453": {
        "network": "base_mainnet", "address": "0x0000000000000000000000000000000000000022",
        "receiver_version": "v2", "deploy_status": "success",
        "supported_providers": ["balancer_v2"],
        "supported_dexes": ["uniswap_v3", "sushiswap_v2"],  # sushi NOT in Base scope
    }})
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH", path)
    ne = bind(flash_provider="balancer_v2", swap_venues=["sushiswap_v2"], chain="base")
    assert ne.verdict == Verdict.REQUIRES_NEW_RECEIVER
    os.unlink(path)


def test_binding_no_deployment_rejected(monkeypatch):
    path = _registry_file({"8453": {
        "network": "base_mainnet", "address": None, "deploy_status": "not_deployed",
    }})
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH", path)
    d = bind(flash_provider="balancer_v2", swap_venues=["uniswap_v3"], chain="base")
    assert d.verdict == Verdict.REJECTED and not d.executable
    os.unlink(path)


def test_binding_out_of_scope_chain_rejected(monkeypatch):
    path = _registry_file({"42161": {
        "network": "arbitrum", "address": "0x0000000000000000000000000000000000000022",
        "receiver_version": "v2", "deploy_status": "success",
        "supported_providers": ["balancer_v2"], "supported_dexes": ["uniswap_v3"],
    }})
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH", path)
    d = bind(flash_provider="balancer_v2", swap_venues=["uniswap_v3"], chain="42161")
    assert d.verdict == Verdict.REJECTED
    os.unlink(path)
