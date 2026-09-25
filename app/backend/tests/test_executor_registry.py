"""Deterministic tests for the read-only executor deployment registry.

No network / no broadcast / no env mutation. Verifies the registry loads, is
consistent with the committed Foundry broadcast artifact, returns the deployed
Base Sepolia address, fails closed for mainnet (not deployed) and unknown
chains, and has NO side effects on the environment.
"""
import json
import os
from pathlib import Path

from arbicore.execution import executor_registry as reg

REPO_ROOT = Path(__file__).resolve().parents[3]
SEPOLIA_ARTIFACT = REPO_ROOT / "contracts/broadcast/Deploy.s.sol/84532/run-latest.json"


def test_registry_loads_with_deployments():
    data = reg.load_registry()
    assert isinstance(data.get("deployments"), dict)
    assert "84532" in data["deployments"]
    assert "8453" in data["deployments"]


def test_sepolia_deployment_matches_broadcast_artifact():
    rec = reg.get_deployment("base_sepolia")
    assert rec is not None and rec["deploy_status"] == "success"
    art = json.loads(SEPOLIA_ARTIFACT.read_text())
    tx = art["transactions"][0]
    # Address + constructor args must match the actual broadcast artifact.
    assert rec["address"].lower() == tx["contractAddress"].lower()
    args = [a.lower() for a in tx["arguments"]]
    ca = rec["constructor_args"]
    assert [ca["balancerVault"].lower(), ca["aavePool"].lower(),
            ca["uniRouter"].lower()] == args
    assert rec["deploy_tx"].lower() == art["receipts"][0]["transactionHash"].lower()


def test_deployed_address_for_sepolia_by_id_and_alias():
    addr = "0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052"
    assert reg.deployed_address(84532) == addr
    assert reg.deployed_address("base_sepolia") == addr
    assert reg.is_deployed("base_sepolia") is True


def test_mainnet_deployed_matches_registry_and_broadcast():
    """Mainnet (8453) IS now genuinely deployed (verified on-chain: bytecode +
    immutables match the committed broadcast artifact). Update the previously-
    stale not_deployed expectation to current reality while preserving the
    fail-closed contract: only deploy_status=="success" with a valid address
    returns an address."""
    addr = "0x0E3FDb0F0E615A517588BD44ac6C78Bb7615927f"
    assert reg.deployed_address(8453) == addr
    assert reg.deployed_address("base") == addr
    assert reg.is_deployed("base_mainnet") is True
    rec = reg.get_deployment(8453)
    assert rec is not None and rec["deploy_status"] == "success"
    assert rec["receiver_version"] == "v1"
    # Preserve fail-closed intent: unknown + not_deployed chains still return None.
    assert reg.deployed_address("ethereum") is None
    assert reg.is_deployed("ethereum") is False


def test_fail_closed_contract_preserved_for_undeployed_and_invalid():
    # not_deployed-style / malformed records must NOT yield an address.
    assert reg.deployed_address(1) is None          # ethereum unregistered
    assert reg.deployed_address("polygon") is None
    assert reg.is_deployed(137) is False


def test_unknown_chain_fails_closed():
    assert reg.get_deployment(1) is None
    assert reg.get_deployment("ethereum") is None
    assert reg.deployed_address(1) is None
    assert reg.deployed_address(None) is None


def test_missing_registry_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH", str(tmp_path / "nope.json"))
    assert reg.load_registry()["deployments"] == {}
    assert reg.deployed_address("base_sepolia") is None


def test_registry_has_no_env_side_effects():
    before = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    reg.load_registry()
    reg.deployed_address("base_sepolia")
    reg.get_deployment(8453)
    assert os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") == before  # unchanged
