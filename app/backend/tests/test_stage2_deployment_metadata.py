"""STAGE 2 — deployment metadata propagation (deterministic, static).

Guards the exact drift that made the production image report
app_version=unset / git_sha=unknown: the canonical upgrade build
(deployment/upgrade/compose/docker-compose.prod.yml → deployment/upgrade/backend/
Dockerfile) must pass GITSHA/GITTAG/BUILD_TIME/APP_VERSION as build args, the
Dockerfile must map them to ARBICORE_* env, and 00_detect_env.sh must write all
four into compose/.env.
"""
import os
import re

import yaml

REPO = "/app"
PROD_COMPOSE = f"{REPO}/deployment/upgrade/compose/docker-compose.prod.yml"
UPGRADE_DOCKERFILE = f"{REPO}/deployment/upgrade/backend/Dockerfile"
DETECT_ENV = f"{REPO}/deployment/upgrade/steps/00_detect_env.sh"

METADATA_ARGS = ("GITSHA", "GITTAG", "BUILD_TIME", "APP_VERSION")
ENV_EXPORTS = ("ARBICORE_GIT_SHA", "ARBICORE_GIT_TAG",
               "ARBICORE_BUILD_TIME", "ARBICORE_VERSION")


def _read(path):
    with open(path) as f:
        return f.read()


def test_prod_compose_backend_declares_metadata_build_args():
    doc = yaml.safe_load(_read(PROD_COMPOSE))
    args = doc["services"]["backend"]["build"]["args"]
    # compose args may be a dict or a list; normalise to a set of names
    if isinstance(args, dict):
        names = set(args.keys())
    else:
        names = {str(a).split("=", 1)[0].split(":", 1)[0].strip() for a in args}
    for a in METADATA_ARGS:
        assert a in names, f"{a} missing from prod compose backend build.args ({names})"


def test_upgrade_dockerfile_declares_args_and_exports_env():
    txt = _read(UPGRADE_DOCKERFILE)
    for a in METADATA_ARGS:
        assert re.search(rf"^\s*ARG\s+{a}\b", txt, re.M), f"ARG {a} missing from upgrade Dockerfile"
    # each ARBICORE_* env must be wired to its corresponding build ARG
    pairs = {
        "ARBICORE_GIT_SHA": "GITSHA",
        "ARBICORE_GIT_TAG": "GITTAG",
        "ARBICORE_BUILD_TIME": "BUILD_TIME",
        "ARBICORE_VERSION": "APP_VERSION",
    }
    for env_key, arg in pairs.items():
        assert re.search(rf"{env_key}=\$\{{{arg}\}}", txt), \
            f"{env_key}=${{{arg}}} not exported in upgrade Dockerfile"


def test_detect_env_writes_all_four_into_compose_env():
    txt = _read(DETECT_ENV)
    # locate the compose/.env heredoc block
    m = re.search(r'cat > "\$COMPOSE_ENV" <<EOF(.*?)EOF', txt, re.S)
    assert m, "compose/.env heredoc not found in 00_detect_env.sh"
    block = m.group(1)
    for a in METADATA_ARGS:
        assert re.search(rf"^{a}=\$\{{{a}\}}", block, re.M), \
            f"{a} not written into compose/.env by 00_detect_env.sh"


def test_version_endpoint_contract():
    # runtime contract: the endpoint exposes the identity keys (no secrets).
    import requests
    base = os.environ.get("REACT_APP_BACKEND_URL")
    if not base:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    base = line.split("=", 1)[1].strip()
                    break
    r = requests.get(f"{base.rstrip('/')}/api/arbicore/version", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("git_sha", "git_tag", "build_time", "app_version", "image_digest"):
        assert k in d, d
    blob = str(d).lower()
    for bad in ("private", "vault_key", "secret", "password", "mongo_url"):
        assert bad not in blob
