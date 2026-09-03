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


def test_mainnet_not_deployed_fails_closed():
    assert reg.deployed_address(8453) is None
    assert reg.deployed_address("base") is None
    assert reg.is_deployed("base_mainnet") is False
    rec = reg.get_deployment(8453)
    assert rec is not None and rec["deploy_status"] == "not_deployed"


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
