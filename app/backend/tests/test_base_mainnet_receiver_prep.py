"""Offline consistency + security-declaration checks for the prepared Base mainnet
FlashLoanReceiver artifact. NO bytecode, NO network, NO deployment. Guards that the
mainnet immutable config and supported-provider declaration are internally consistent
and fail-closed, so a later build/deploy cannot silently drift.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_CONTRACTS = _REPO / "contracts"

MAINNET = {
    "balancerVault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    "aavePool": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    "uniRouter": "0x2626664c2603336E57B271c5C0b26F421741e481",
}


def _deploy_constants() -> dict:
    txt = (_CONTRACTS / "script" / "Deploy.s.sol").read_text()
    out = {}
    for key, const in (("balancerVault", "MAINNET_BALANCER_V2_VAULT"),
                       ("aavePool", "MAINNET_AAVE_V3_POOL"),
                       ("uniRouter", "MAINNET_UNIV3_ROUTER")):
        m = re.search(const + r"\s*=\s*(0x[0-9a-fA-F]{40})", txt)
        assert m, f"{const} not found in Deploy.s.sol"
        out[key] = m.group(1)
    return out


def test_mainnet_immutables_match_deploy_script():
    d = _deploy_constants()
    for k, v in MAINNET.items():
        assert d[k].lower() == v.lower(), f"{k} drift: {d[k]} != {v}"


def test_mainnet_immutables_match_registry_expected():
    reg = json.loads((_REPO / "deploy" / "executor_deployments.json").read_text())
    exp = reg["deployments"]["8453"]["constructor_args_expected"]
    for k, v in MAINNET.items():
        assert exp[k].lower() == v.lower(), f"{k} registry drift: {exp[k]} != {v}"


def test_mainnet_config_is_not_sepolia():
    # Sepolia aavePool/uniRouter differ — the artifact must be mainnet, not relabelled Sepolia.
    assert MAINNET["aavePool"].lower() != "0x8bab6d1b75f19e9ed9fce8b9bd338844ff79ae27"
    assert MAINNET["uniRouter"].lower() != "0x94cc0aac535ccdb3c01d6787d6413c739ae12bc4"


def test_supported_providers_match_abi_implementation():
    abi = json.loads((_CONTRACTS / "artifacts" / "FlashLoanReceiver.abi.json").read_text())
    fns = {e.get("name") for e in abi if e.get("type") == "function"}
    # Balancer head + callback and Aave head + callback are implemented.
    assert {"execute", "receiveFlashLoan"}.issubset(fns)      # balancer_v2
    assert {"executeAave", "executeOperation"}.issubset(fns)  # aave_v3
    # Morpho must NOT be present (never declarable as supported).
    src = (_CONTRACTS / "contracts" / "core" / "FlashLoanReceiver.sol").read_text().lower()
    assert "morpho" not in src


def test_receiver_capability_fail_closed_without_deployment():
    # With the REAL registry (no mainnet deploy), Base mainnet stays BLOCKED.
    from arbicore.execution.receiver_capability import receiver_capability, receiver_supports
    cap = receiver_capability("base")
    assert cap.deployed is False or cap.supported_providers == []
    for prov in ("balancer_v2", "aave_v3", "uniswap_v3", "morpho_blue"):
        assert receiver_supports("base", prov) is False


def test_receiver_capability_declares_only_built_providers(monkeypatch, tmp_path):
    # Simulate a recorded mainnet deployment declaring ONLY balancer_v2 (+aave_v3) and
    # prove morpho_blue can never become supported via the declaration.
    from arbicore.execution import executor_registry as reg
    fake = {"schema": "arbicore.executor_deployments/v1", "deployments": {"8453": {
        "network": "base_mainnet", "address": "0x" + "11" * 20, "deploy_status": "success",
        "receiver_version": "v1.0.0-base-mainnet", "basescan_verified": "verified",
        "supported_providers": ["balancer_v2", "aave_v3"],
        "constructor_args": MAINNET}}}
    p = tmp_path / "reg.json"; p.write_text(json.dumps(fake))
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH", str(p))
    from arbicore.execution.receiver_capability import receiver_capability, receiver_supports
    cap = receiver_capability("base")
    assert cap.deployed is True and cap.version_verified is True
    assert receiver_supports("base", "balancer_v2") is True
    assert receiver_supports("base", "aave_v3") is True
    assert receiver_supports("base", "morpho_blue") is False   # never inferred
