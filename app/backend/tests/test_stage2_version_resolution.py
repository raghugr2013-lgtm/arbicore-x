"""STAGE 2 — VERSION resolved from the REPOSITORY ROOT (deterministic, static).

Guards the VPS preflight bug where 00_detect_env.sh read VERSION from
``$ROOT_DIR/VERSION`` (= deployment/upgrade/VERSION, which does not exist) and
therefore produced ``IMAGE_TAG=arbicore-x-backend:0.0.0-<sha>`` instead of the
real ``arbicore-x-backend:<repo-semver>-<sha>``.

Fix under test:
  * lib/common.sh defines REPO_ROOT (git --show-toplevel, fallback ROOT_DIR/../..)
  * 00_detect_env.sh reads VERSION from $REPO_ROOT/VERSION (never $ROOT_DIR)
No version is hardcoded — the semver comes from the repo VERSION file.
"""
import re
import subprocess

REPO = "/app"
COMMON = f"{REPO}/deployment/upgrade/lib/common.sh"
DETECT_ENV = f"{REPO}/deployment/upgrade/steps/00_detect_env.sh"
VERSION_FILE = f"{REPO}/VERSION"


def _read(path):
    with open(path) as f:
        return f.read()


def _repo_semver():
    return _read(VERSION_FILE).strip()


# ── Static guards ──────────────────────────────────────────────────────────
def test_common_sh_defines_repo_root_from_toplevel_with_fallback():
    txt = _read(COMMON)
    assert "REPO_ROOT=" in txt, "common.sh must define REPO_ROOT"
    assert "rev-parse --show-toplevel" in txt, \
        "REPO_ROOT must prefer git --show-toplevel"
    # fallback two levels up from the deployment/upgrade dir
    assert re.search(r'REPO_ROOT="\$\(cd "\$ROOT_DIR/\.\./\.\." && pwd\)"', txt), \
        "REPO_ROOT must fall back to ROOT_DIR/../.. when git is unavailable"


def test_detect_env_reads_version_from_repo_root_not_root_dir():
    txt = _read(DETECT_ENV)
    assert 'tr -d \'[:space:]\' < "$REPO_ROOT/VERSION"' in txt, \
        "APP_SEMVER must read $REPO_ROOT/VERSION"
    # the buggy path must be gone
    assert '< "$ROOT_DIR/VERSION"' not in txt, \
        "00_detect_env.sh must NOT read VERSION from $ROOT_DIR"
    assert 'IMAGE_TAG="arbicore-x-backend:${APP_SEMVER}-${GITSHA}"' in txt


# ── Functional: exercise the REAL common.sh REPO_ROOT resolution ───────────
def test_repo_root_resolves_to_repository_root_and_finds_version():
    script = (
        f'source {COMMON}\n'
        'APP_SEMVER="$(tr -d \'[:space:]\' < "$REPO_ROOT/VERSION" 2>/dev/null || true)"\n'
        '[ -n "$APP_SEMVER" ] || APP_SEMVER="0.0.0"\n'
        'GITSHA="$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo nogit)"\n'
        'echo "ROOT_DIR=$ROOT_DIR"\n'
        'echo "REPO_ROOT=$REPO_ROOT"\n'
        'echo "APP_SEMVER=$APP_SEMVER"\n'
        'echo "IMAGE_TAG=arbicore-x-backend:${APP_SEMVER}-${GITSHA}"\n'
    )
    out = subprocess.run(["bash", "-c", script], capture_output=True,
                         text=True, check=True).stdout
    kv = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)

    assert kv["ROOT_DIR"] == f"{REPO}/deployment/upgrade"
    assert kv["REPO_ROOT"] == REPO           # repo root, NOT deployment/upgrade
    assert kv["APP_SEMVER"] == _repo_semver()
    assert kv["APP_SEMVER"] != "0.0.0"       # the exact VPS regression
    assert kv["IMAGE_TAG"].startswith(f"arbicore-x-backend:{_repo_semver()}-")


def test_non_git_fallback_still_resolves_repo_root():
    # Simulate git being unavailable: force the fallback branch directly.
    script = (
        f'ROOT_DIR="{REPO}/deployment/upgrade"\n'
        'REPO_ROOT="$(cd "$ROOT_DIR/../.." && pwd)"\n'
        'APP_SEMVER="$(tr -d \'[:space:]\' < "$REPO_ROOT/VERSION" 2>/dev/null || true)"\n'
        'echo "REPO_ROOT=$REPO_ROOT"\n'
        'echo "APP_SEMVER=$APP_SEMVER"\n'
    )
    out = subprocess.run(["bash", "-c", script], capture_output=True,
                         text=True, check=True).stdout
    kv = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    assert kv["REPO_ROOT"] == REPO
    assert kv["APP_SEMVER"] == _repo_semver()
