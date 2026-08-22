"""STAGE 2 — canonical build context resolves the Dockerfile's dependency file.

Guards the blocker where `COPY requirements.txt /app/requirements.txt` failed
because the build context (deployment/upgrade/backend) did not contain
requirements.txt or the app source. Verifies the prod compose backend
build.context (resolved relative to the compose file) contains requirements.txt
+ the app source, and that the referenced Dockerfile exists and is the canonical
upgrade Dockerfile.
"""
import os
import re

import yaml

REPO = "/app"
COMPOSE = f"{REPO}/deployment/upgrade/compose/docker-compose.prod.yml"
COMPOSE_DIR = os.path.dirname(COMPOSE)


def _build():
    doc = yaml.safe_load(open(COMPOSE))
    return doc["services"]["backend"]["build"]


def _resolve(*parts):
    return os.path.normpath(os.path.join(*parts))


def test_context_contains_requirements_and_app_source():
    b = _build()
    ctx = _resolve(COMPOSE_DIR, b["context"])
    assert os.path.isdir(ctx), f"context does not exist: {ctx}"
    # the exact file the Dockerfile COPYs
    assert os.path.isfile(os.path.join(ctx, "requirements.txt")), \
        f"requirements.txt missing from build context {ctx}"
    # app source for `COPY . /app`
    assert os.path.isfile(os.path.join(ctx, "server.py")), ctx
    assert os.path.isdir(os.path.join(ctx, "arbicore")), ctx


def test_dockerfile_reference_resolves_to_canonical_upgrade_dockerfile():
    b = _build()
    ctx = _resolve(COMPOSE_DIR, b["context"])
    # compose resolves `dockerfile` relative to the context dir
    dockerfile = _resolve(ctx, b["dockerfile"])
    assert os.path.isfile(dockerfile), f"dockerfile not found: {dockerfile}"
    assert dockerfile == f"{REPO}/deployment/upgrade/backend/Dockerfile", dockerfile


def test_dockerfile_copy_targets_are_satisfiable_from_context():
    b = _build()
    ctx = _resolve(COMPOSE_DIR, b["context"])
    dockerfile = _resolve(ctx, b["dockerfile"])
    text = open(dockerfile).read()
    # every `COPY <src> <dst>` with a concrete src must exist in the context
    for m in re.finditer(r"^COPY\s+(\S+)\s+\S+", text, re.M):
        src = m.group(1)
        if src == ".":
            continue
        assert os.path.exists(os.path.join(ctx, src)), \
            f"COPY source '{src}' not present in build context {ctx}"


def test_dockerignore_present_in_context_excludes_env():
    b = _build()
    ctx = _resolve(COMPOSE_DIR, b["context"])
    di = os.path.join(ctx, ".dockerignore")
    assert os.path.isfile(di), "context missing .dockerignore"
    body = open(di).read()
    assert ".env" in body
