"""Regression — certification build provenance handoff (GITSHA -> ARBICORE_GIT_SHA).

Blocker fixed: the isolated certification image build failed at
`RUN python -m scripts.gen_build_info` with

    gen_build_info: FATAL provenance error:
    ARBICORE_GIT_SHA='unknown' is not a 40-hex git object id

because the certification compose silently defaulted the ``GITSHA`` build-arg to
the literal ``unknown`` (``${GITSHA:-unknown}``) when it was not exported, and the
cert build did not run gen_build_info in STRICT mode. The `.git` directory is
excluded from the image (see .dockerignore), so the ARG is the ONLY provenance
source — a placeholder there is fatal.

These offline/deterministic checks (no docker, no container) LOCK IN the whole
handoff so it cannot silently regress:

  1. Dockerfile maps build ARG ``GITSHA`` -> ENV ``ARBICORE_GIT_SHA``.
  2. Certification compose passes the EXACT ``GITSHA`` and FAILS CLOSED (``:?``)
     instead of ever substituting ``unknown``; it also forces ``GIT_STRICT=1``.
  3. The compose builds the backend Dockerfile that owns the ARG->ENV mapping.
  4. End-to-end: the value compose threads reaches gen_build_info as the exact
     SHA under strict mode; missing/malformed SHAs still fail closed.

Strict provenance is NEVER disabled and ``unknown`` is NEVER accepted.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.gen_build_info import build_info, is_valid_full_sha

# The exact checkpoint SHA the certification build must accept as valid.
CHECKPOINT_SHA = "702709c216e47574f2c4484a9e4a48d6c1303b44"

_HERE = Path(__file__).absolute()


def _find_repo_root() -> Path:
    for p in _HERE.parents:
        if (p / "deployment/docker/backend/Dockerfile").is_file():
            return p
    raise AssertionError(
        "repo root (with deployment/docker/backend/Dockerfile) not found")


_REPO = _find_repo_root()
_DOCKERFILE = _REPO / "deployment/docker/backend/Dockerfile"
_CERT_COMPOSE = _REPO / "deployment/compose/docker-compose.certification.yml"


# ───────────────────────── (1) Dockerfile ARG -> ENV ────────────────────────
def test_dockerfile_declares_gitsha_arg():
    txt = _DOCKERFILE.read_text()
    assert re.search(r"^ARG\s+GITSHA(\s*=|\s*$)", txt, flags=re.MULTILINE), \
        "backend Dockerfile must declare `ARG GITSHA` for the provenance handoff"


def test_dockerfile_maps_gitsha_arg_into_arbicore_git_sha_env():
    """The build-arg GITSHA MUST be wired into ENV ARBICORE_GIT_SHA — otherwise
    gen_build_info (which reads ARBICORE_GIT_SHA) can never see the real SHA."""
    txt = _DOCKERFILE.read_text()
    assert re.search(r"ARBICORE_GIT_SHA=\$\{?GITSHA\}?", txt), (
        "backend Dockerfile must map ENV ARBICORE_GIT_SHA=${GITSHA}; without "
        "this, the exact commit SHA cannot reach scripts.gen_build_info")


# ─────────────────────── (2) certification compose ──────────────────────────
def _cert_build_args() -> dict:
    compose = yaml.safe_load(_CERT_COMPOSE.read_text())
    return compose["services"]["certify"]["build"]["args"]


def test_cert_compose_passes_gitsha_failing_closed_not_unknown():
    args = _cert_build_args()
    gitsha = str(args["GITSHA"])
    # Must reference the GITSHA interpolation variable ...
    assert gitsha.startswith("${GITSHA"), \
        f"cert GITSHA build-arg must interpolate ${{GITSHA}}, got {gitsha!r}"
    # ... and FAIL CLOSED (`:?`) — never silently default to a placeholder.
    assert gitsha.startswith("${GITSHA:?"), (
        "cert GITSHA build-arg must use `${GITSHA:?...}` so an unset/empty SHA "
        f"fails the build loudly; got {gitsha!r}")
    assert ":-unknown" not in gitsha and ":-local" not in gitsha, (
        "cert GITSHA build-arg must NOT silently default to unknown/local — a "
        "placeholder provenance identity is exactly the blocker being fixed")


def test_cert_compose_forces_strict_provenance():
    args = _cert_build_args()
    assert str(args.get("GIT_STRICT")) == "1", (
        "certification build must set GIT_STRICT=1 so gen_build_info fails on a "
        "missing/malformed source SHA instead of embedding a placeholder")


def test_cert_compose_builds_the_backend_dockerfile_that_owns_the_mapping():
    compose = yaml.safe_load(_CERT_COMPOSE.read_text())
    build = compose["services"]["certify"]["build"]
    assert build["dockerfile"] == "deployment/docker/backend/Dockerfile", (
        "cert build must target the backend Dockerfile that maps "
        "GITSHA -> ARBICORE_GIT_SHA")


# ───────────────── (3) end-to-end handoff through gen_build_info ─────────────
def test_exact_checkpoint_sha_is_accepted_and_embedded():
    """The value compose threads (a real 40-hex commit) reaches gen_build_info as
    ARBICORE_GIT_SHA and is embedded VERBATIM under strict certification."""
    assert is_valid_full_sha(CHECKPOINT_SHA)
    info = build_info(env={"ARBICORE_GIT_SHA": CHECKPOINT_SHA},
                      live_sha=None, live_tag=None, strict=True)
    assert info["git_sha"] == CHECKPOINT_SHA


def test_unknown_placeholder_still_fails_closed_under_strict():
    # The precise placeholder that produced the original FATAL error.
    with pytest.raises(ValueError):
        build_info(env={"ARBICORE_GIT_SHA": "unknown"},
                   live_sha=None, live_tag=None, strict=True)


def test_missing_sha_fails_closed_under_strict():
    with pytest.raises(ValueError):
        build_info(env={}, live_sha=None, live_tag=None, strict=True)
