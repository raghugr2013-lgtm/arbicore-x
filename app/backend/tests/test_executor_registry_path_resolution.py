"""Regression — executor registry path resolution must work when /app is the
code root (container: `COPY app/backend/ /app/`) WITHOUT IndexError, and must
fail-closed (missing registry != valid deployment; H10 stays UNKNOWN/BLOCKED).

Bug: `_default_registry_path()` used `parents[4]` → IndexError at
/app/arbicore/execution/executor_registry.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from arbicore.execution import executor_registry as R


def _make_layout(root: Path, *, with_deploy: bool) -> Path:
    mod = root / "arbicore" / "execution" / "executor_registry.py"
    mod.parent.mkdir(parents=True, exist_ok=True)
    mod.write_text("# fake module")
    (root / "scripts").mkdir(parents=True, exist_ok=True)  # mimic /app/scripts
    if with_deploy:
        d = root / "deploy"
        d.mkdir(parents=True, exist_ok=True)
        (d / "executor_deployments.json").write_text(json.dumps(
            {"schema": "arbicore.executor_deployments/v1", "deployments": {}}))
    return mod


def test_container_layout_finds_registry(tmp_path):
    # reproduce /app code-root layout WITH the deploy dir present
    app = tmp_path / "app"
    mod = _make_layout(app, with_deploy=True)
    got = R._resolve_registry_path(mod)
    assert got == (app / "deploy" / "executor_deployments.json")
    assert got.is_file()


def test_container_layout_missing_registry_is_deterministic_and_failclosed(tmp_path):
    # /app code-root layout but NO deploy dir anywhere under tmp
    app = tmp_path / "app"
    mod = _make_layout(app, with_deploy=False)
    got = R._resolve_registry_path(mod)
    # deterministic code-root-relative path, and it does NOT exist ⇒ fail-closed
    assert got == (app / "deploy" / "executor_deployments.json")
    assert not got.is_file()


def test_shallow_path_does_not_indexerror():
    # the exact container path that triggered `parents[4]` IndexError
    got = R._resolve_registry_path(Path("/app/arbicore/execution/executor_registry.py"))
    assert str(got).endswith("deploy/executor_deployments.json")  # no exception


def test_env_override_is_preferred(tmp_path, monkeypatch):
    f = tmp_path / "custom_registry.json"
    f.write_text(json.dumps(
        {"schema": "arbicore.executor_deployments/v1",
         "deployments": {"8453": {"deploy_status": "not_deployed"}}}))
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH", str(f))
    assert R.registry_path() == f
    assert R.load_registry()["deployments"]["8453"]["deploy_status"] == "not_deployed"


def test_missing_registry_failcloses_h10(tmp_path, monkeypatch):
    # point the override at a non-existent file → empty registry, no deployment
    monkeypatch.setenv("ARBICORE_EXECUTOR_REGISTRY_PATH",
                       str(tmp_path / "does_not_exist.json"))
    reg = R.load_registry()
    assert reg["deployments"] == {}
    assert R.deployed_address(8453) is None           # never a guess
    assert R.get_deployment("base") is None
    # H10 boundary: receiver capability stays fail-closed (undeployed)
    from arbicore.execution.receiver_capability import receiver_capability
    cap = receiver_capability(8453)
    assert cap.deployed is False and cap.supported_providers == []
