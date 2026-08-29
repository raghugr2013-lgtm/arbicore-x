"""Deterministic guard for the DISPOSABLE VPS validation image layout.

Regression test for the real-VPS build failure:

    ERROR: Could not open requirements file:
    [Errno 2] No such file or directory: '/app/requirements.prod.txt'

`deployment/docker/backend/requirements.test.txt` begins with
`-r requirements.prod.txt`. pip resolves that include RELATIVE to the requirements
file's own directory inside the image. Therefore `Dockerfile.validation` must copy
EVERY locally-referenced requirements file into the SAME in-image directory (with
basenames preserved) before `pip install -r requirements.test.txt`, or the build
fails at parse time.

This test asserts that invariant without needing Docker, so a future edit that adds
a new `-r <local file>` to requirements.test.txt (or drops a COPY) is caught early.
It is intentionally NOT part of the 12-module deterministic audit runner list — it is
a repo-layout consistency guard collected by the full `pytest tests/` suite.
"""
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent            # app/backend
REPO_ROOT = BACKEND_DIR.parent.parent                           # repo root
REQ_DIR = REPO_ROOT / "deployment" / "docker" / "backend"
DOCKERFILE = REQ_DIR / "Dockerfile.validation"
TEST_REQ = REQ_DIR / "requirements.test.txt"


def _local_requirement_includes(req_file: Path) -> set[str]:
    """Recursively collect basenames of LOCAL `-r`/`--requirement` includes."""
    seen: set[str] = set()
    stack = [req_file]
    while stack:
        current = stack.pop()
        for raw in current.read_text().splitlines():
            line = raw.strip()
            if not (line.startswith("-r ") or line.startswith("--requirement ")):
                continue
            ref = line.split(None, 1)[1].strip()
            if "://" in ref:  # remote requirement URL — not a local file
                continue
            name = Path(ref).name
            seen.add(name)
            resolved = (current.parent / ref).resolve()
            if resolved.exists():
                stack.append(resolved)
    return seen


def _copy_dests(dockerfile_text: str) -> set[str]:
    """Destination paths of every `COPY <src> <dest>` line."""
    dests: set[str] = set()
    for m in re.finditer(r"(?im)^\s*COPY\s+(?:--\S+\s+)*(\S+)\s+(\S+)\s*$", dockerfile_text):
        dests.add(m.group(2))
    return dests


def _pip_install_target(dockerfile_text: str) -> str:
    """The `-r <path>` argument on the RUN pip install line (ignores comments)."""
    for line in dockerfile_text.splitlines():
        if "pip install" not in line:
            continue
        m = re.search(r"-r\s+(\S+)", line)
        if m:
            return m.group(1)
    raise AssertionError("Dockerfile.validation must `pip install -r <requirements file>`")


def test_validation_dockerfile_and_test_requirements_exist():
    assert DOCKERFILE.exists(), f"missing {DOCKERFILE}"
    assert TEST_REQ.exists(), f"missing {TEST_REQ}"


def test_validation_image_provides_every_referenced_requirements_file():
    text = DOCKERFILE.read_text()

    # The pip install target must be requirements.test.txt in a concrete dir.
    target = _pip_install_target(text)
    install_dir = Path(target).parent.as_posix()          # e.g. /app
    assert Path(target).name == "requirements.test.txt", (
        f"expected pip install target requirements.test.txt, got {target}"
    )

    dests = _copy_dests(text)

    # requirements.test.txt itself + every local `-r` include (e.g. requirements.prod.txt)
    # must be COPYed into install_dir with the basename preserved so pip can open them.
    referenced = {"requirements.test.txt"} | _local_requirement_includes(TEST_REQ)
    assert "requirements.prod.txt" in referenced, (
        "sanity: requirements.test.txt should include requirements.prod.txt via `-r`"
    )
    for name in sorted(referenced):
        expected = f"{install_dir}/{name}"
        assert expected in dests, (
            f"Dockerfile.validation must COPY '{name}' to '{expected}' "
            f"(referenced by requirements.test.txt). COPY dests found: {sorted(dests)}"
        )


def test_validation_image_does_not_copy_prod_requirements_into_a_different_dir():
    """The prod file must sit NEXT TO the test file (same dir) — not merely present."""
    text = DOCKERFILE.read_text()
    target = _pip_install_target(text)
    install_dir = Path(target).parent.as_posix()
    dests = _copy_dests(text)
    assert f"{install_dir}/requirements.prod.txt" in dests
    assert f"{install_dir}/requirements.test.txt" in dests
