"""Regression coverage for the VPS certification-harness fixes.

Two independent, previously-shipped defects are locked down here:

  (A) IMPORT PATH — ``vps_multichain_preflight`` (and its sibling read-only
      harnesses) must import the ``arbicore`` package when invoked by DIRECT
      PATH (``python <root>/scripts/vps_multichain_preflight.py``), which is the
      production-style command used by the authoritative VPS certification. That
      invocation puts the ``scripts/`` dir on ``sys.path[0]`` (NOT the app root),
      so before the fix it raised ``ModuleNotFoundError: No module named
      'arbicore'`` at Step 6. The script now bootstraps its own APP_ROOT.

  (B) PROVENANCE — isolated-image certification (``.git`` stripped) must report
      the identity BAKED into the image (``BUILD_INFO.json``), NOT a stale
      production ``ARBICORE_GIT_*`` value inherited from an unrelated env_file.
      A disagreeing env value is reported as ``provenance_contamination`` and
      IGNORED, never emitted as the certified identity.

Offline, deterministic, no RPC / signing / broadcast / Mongo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# APP_ROOT = <repo>/app/backend in a checkout, /app in the shipped image. The
# harness scripts live at APP_ROOT/scripts/*.py in BOTH layouts.
APP_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = APP_ROOT / "scripts"

from scripts.arbicore_certify import _resolve_identity, _build_identity  # noqa: E402

# The isolated Phase-5 image's true HEAD, and the stale production identity that
# leaked into certification before the fix.
IMAGE_SHA = "ad64a5083d6ead0fee1e221f96f63b1c2e479eb3"
IMAGE_TAG = "v2.9.2-268-gad64a50-dirty"
STALE_PROD_SHA = "bd969ee507bcf9b37311814aeae25556c951e86d"
STALE_PROD_TAG = "p0-3-bd969ee"


# ─────────────────────────── (A) IMPORT PATH ───────────────────────────────
def _run_direct_path(script_name: str) -> subprocess.CompletedProcess:
    """Invoke a harness by DIRECT PATH with a clean environment, so ``sys.path``
    is NOT pre-seeded with the app root (reproduces the production-style command
    that failed at Step 6). CWD is a neutral dir so CWD isn't on the path either.
    """
    script = SCRIPTS / script_name
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["MONGO_URL"] = "mongodb://localhost:27017"
    env["DB_NAME"] = "arbicore_x_test_invocation"
    return subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd="/tmp", env=env, capture_output=True, text=True, timeout=120)


def test_preflight_direct_path_invocation_imports_arbicore():
    """``python <root>/scripts/vps_multichain_preflight.py --json`` must succeed
    (the exact production-style command). Before the fix this raised
    ModuleNotFoundError: No module named 'arbicore'."""
    proc = _run_direct_path("vps_multichain_preflight.py")
    assert proc.returncode == 0, (
        f"preflight direct-path invocation failed:\nSTDERR:\n{proc.stderr}")
    assert "ModuleNotFoundError" not in proc.stderr
    assert "No module named 'arbicore'" not in proc.stderr
    rep = json.loads(proc.stdout)
    # Real content proves arbicore imported and ran (never fabricated).
    assert "matrix_summary" in rep and "networks" in rep
    assert rep["safety"]["broadcast"] is False
    assert rep["safety"]["limited_live_enabled"] is False


def test_certify_direct_path_invocation_imports_arbicore():
    """Sibling harness ``arbicore_certify`` must also import arbicore under the
    production-style direct-path invocation."""
    proc = _run_direct_path("arbicore_certify.py")
    assert "ModuleNotFoundError" not in proc.stderr
    assert "No module named 'arbicore'" not in proc.stderr
    rep = json.loads(proc.stdout)
    assert "opportunity_matrix" in rep and "repository" in rep


# ─────────────────────────── (B) PROVENANCE ────────────────────────────────
def test_image_mode_build_info_is_authoritative_over_stale_env():
    """IMAGE mode (no .git): the baked BUILD_INFO stamp is authoritative; an
    inherited production ARBICORE_GIT_* is IGNORED and flagged, never reported
    as the identity."""
    ident = _resolve_identity(
        stamp={"git_sha": IMAGE_SHA, "git_tag": IMAGE_TAG},
        live_sha="", live_describe="", branch="",
        git_available=False,
        env={"ARBICORE_GIT_SHA": STALE_PROD_SHA,
             "ARBICORE_GIT_TAG": STALE_PROD_TAG},
    )
    assert ident["git_sha"] == IMAGE_SHA
    assert ident["git_tag"] == IMAGE_TAG
    assert ident["git_source"] == "build_info"
    assert ident["git_sha"] != STALE_PROD_SHA
    c = ident["provenance_contamination"]
    assert c and c["detected"] is True
    assert c["inherited_env_git_sha"] == STALE_PROD_SHA
    assert c["authoritative_image_git_sha"] == IMAGE_SHA


def test_image_mode_clean_when_env_matches_stamp():
    ident = _resolve_identity(
        stamp={"git_sha": IMAGE_SHA, "git_tag": IMAGE_TAG},
        live_sha="", live_describe="", branch="",
        git_available=False,
        env={"ARBICORE_GIT_SHA": IMAGE_SHA, "ARBICORE_GIT_TAG": IMAGE_TAG},
    )
    assert ident["git_sha"] == IMAGE_SHA
    assert ident["provenance_contamination"] is None


def test_image_mode_no_stamp_env_is_unverified_not_trusted():
    """A .git-stripped image with NO baked stamp cannot be authoritatively
    identified; env is used only as a clearly-flagged unverified fallback."""
    ident = _resolve_identity(
        stamp={}, live_sha="", live_describe="", branch="",
        git_available=False,
        env={"ARBICORE_GIT_SHA": STALE_PROD_SHA},
    )
    assert ident["git_source"] == "env_unverified"
    assert ident["git_sha"] == STALE_PROD_SHA  # only source available, flagged


def test_checkout_mode_live_git_certifies_working_tree():
    """Dev/CI checkout: LIVE git wins over a (possibly stale) baked stamp so
    certify never reports a baked SHA over the actually-checked-out code."""
    ident = _resolve_identity(
        stamp={"git_sha": STALE_PROD_SHA, "git_tag": STALE_PROD_TAG},
        live_sha=IMAGE_SHA, live_describe=IMAGE_TAG, branch="work",
        git_available=True, env={},
    )
    assert ident["git_sha"] == IMAGE_SHA
    assert ident["git_source"] == "git"
    assert ident["provenance_contamination"] is None


def test_build_identity_end_to_end_image_mode(tmp_path, monkeypatch):
    """Full path: real BUILD_INFO.json read + module globals patched to IMAGE
    mode. Proves the wired ``_build_identity`` (not just the pure resolver)
    rejects stale env contamination."""
    import scripts.arbicore_certify as C
    (tmp_path / "BUILD_INFO.json").write_text(
        json.dumps({"git_sha": IMAGE_SHA, "git_tag": IMAGE_TAG}))
    monkeypatch.setattr(C, "GIT_ROOT", None)
    monkeypatch.setattr(C, "APP_ROOT", tmp_path)
    monkeypatch.setenv("ARBICORE_GIT_SHA", STALE_PROD_SHA)
    monkeypatch.setenv("ARBICORE_GIT_TAG", STALE_PROD_TAG)
    ident = C._build_identity()
    assert ident["git_sha"] == IMAGE_SHA
    assert ident["git_source"] == "build_info"
    assert ident["provenance_contamination"]["inherited_env_git_sha"] == STALE_PROD_SHA
