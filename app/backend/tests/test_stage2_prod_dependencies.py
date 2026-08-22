"""STAGE 2 — production dependency manifest is VPS-reproducible.

Guards the blocker where `emergentintegrations==0.2.0` (an Emergent-platform-only
package on a private index, not on public PyPI) was in the manifest the canonical
production Dockerfile installs, breaking `pip install` on the VPS. The manifest
consumed by the build (app/backend/requirements.txt) must contain only
public-PyPI-resolvable, pinned entries — no platform-only/private-index/VCS/local
packages — AND must not be imported anywhere in production code.
"""
import os
import re

REPO = "/app"
REQ = f"{REPO}/app/backend/requirements.txt"
SRC = f"{REPO}/app/backend"

# Packages that only exist on Emergent's private index (not on public PyPI).
PLATFORM_ONLY = {"emergentintegrations"}


def _entries():
    out = []
    for line in open(REQ):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def test_no_platform_only_packages_in_manifest():
    names = {re.split(r"[=<>!~ \[]", e, 1)[0].lower() for e in _entries()}
    leaked = names & PLATFORM_ONLY
    assert not leaked, f"platform-only package(s) in production manifest: {leaked}"


def test_no_private_index_or_vcs_or_local_entries():
    for e in _entries():
        assert not e.startswith(("git+", "http://", "https://")), f"VCS/URL dep: {e}"
        assert "@ file" not in e and not e.endswith(".whl"), f"local/wheel dep: {e}"
        assert not e.startswith(("--index-url", "--extra-index-url", "-i ")), f"index directive: {e}"


def test_all_entries_are_pinned():
    for e in _entries():
        assert "==" in e, f"unpinned dependency (not reproducible): {e}"


def test_removed_package_is_not_imported_in_production_code():
    # if it is genuinely unused, removing it cannot weaken the app
    pattern = re.compile(r"^\s*(from|import)\s+emergentintegrations", re.M)
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", ".pytest_cache")]
        for f in files:
            if f.endswith(".py"):
                txt = open(os.path.join(root, f)).read()
                assert not pattern.search(txt), f"emergentintegrations imported in {f}"
