"""Regression — the certification container must be able to run
`python -m scripts.vps_certify` (bug: ModuleNotFoundError: No module named
'scripts' when working_dir != the image code root).

Ties the cert compose `working_dir` to the backend Dockerfile's COPY destination
so a future path drift is caught deterministically (no docker/container needed).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

_HERE = Path(__file__).absolute()

def _find_repo_root() -> Path:
    for p in _HERE.parents:
        if (p / "deployment/docker/backend/Dockerfile").is_file():
            return p
    raise AssertionError("repo root (with deployment/docker/backend/Dockerfile) not found")

_REPO = _find_repo_root()            # /app (not resolved — avoids symlink drift)
_BACKEND = _REPO / "app/backend" if (_REPO / "app/backend").is_dir() else _REPO / "backend"
_DOCKERFILE = _REPO / "deployment/docker/backend/Dockerfile"
_COMPOSE = _REPO / "deployment/compose/docker-compose.certification.yml"


def _copy_destination() -> str:
    """Destination dir of `COPY app/backend/ <DEST>` in the backend Dockerfile."""
    txt = _DOCKERFILE.read_text()
    m = re.search(r"^COPY\s+app/backend/\s+(\S+)\s*$", txt, flags=re.MULTILINE)
    assert m, "backend Dockerfile must COPY app/backend/ to a known destination"
    dest = m.group(1).rstrip("/")
    return dest or "/"


def test_scripts_is_an_importable_package():
    assert (_BACKEND / "scripts" / "__init__.py").is_file(), \
        "scripts/ must be a package (has __init__.py) for `python -m scripts.*`"
    assert (_BACKEND / "scripts" / "vps_certify.py").is_file()


def test_cert_working_dir_matches_dockerfile_code_root():
    dest = _copy_destination()          # e.g. "/app"
    compose = yaml.safe_load(_COMPOSE.read_text())
    svc = compose["services"]["certify"]
    assert svc["working_dir"].rstrip("/") == dest, (
        f"cert working_dir {svc['working_dir']!r} must equal the Dockerfile "
        f"code root {dest!r} so `scripts` is importable via -m")
    # command must invoke the module form that failed in the bug report
    assert svc["command"] == ["python3", "-m", "scripts.vps_certify"]


def test_module_spec_resolves_from_backend_root():
    # From the backend code root, the dotted module path must resolve — this is
    # exactly what `python -m scripts.vps_certify` needs (cwd on sys.path).
    import sys
    root = str(_BACKEND)
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        spec = importlib.util.find_spec("scripts.vps_certify")
        assert spec is not None, "scripts.vps_certify must be importable from code root"
    finally:
        if added:
            sys.path.remove(root)


def test_cert_stack_is_isolated_and_safe():
    compose = yaml.safe_load(_COMPOSE.read_text())
    svc = compose["services"]["certify"]
    env = svc.get("environment", {})
    # safety envelopes forced OFF in the cert runner
    for k in ("ARBICORE_SIGNING_ENABLED", "ARBICORE_BROADCAST_ENABLED",
              "ARBICORE_AUTOEXEC_AUTOSTART", "ARBICORE_FULL_LIVE_ENABLED",
              "ARBICORE_LIMITED_LIVE_ENABLED"):
        assert str(env.get(k)).lower() == "false", f"{k} must be false in cert runner"
    # one-shot, non-production isolation
    assert svc.get("restart") == "no"
    assert compose["networks"]["arbicore-cert-net"]["name"] == "arbicore-cert-net"
