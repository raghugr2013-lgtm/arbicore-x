"""Write backend/BUILD_INFO.json from the current git checkout / build ARGs.

Run this in CI / the Docker build (before .git is stripped) so the deployed
image reports a real deployment identity via GET /api/arbicore/version and the
certification harness (``scripts.arbicore_certify``) even without a ``.git``
directory inside the image. Env/ARG values take precedence at runtime.

Provenance precedence (deterministic):
    ARBICORE_GIT_SHA (build ARG/env)  >  live ``git rev-parse HEAD``  >  ""

STRICT mode (``ARBICORE_GIT_STRICT`` truthy — set for certification image
builds): the resolved SHA MUST be a full 40-hex git object id. If it would
otherwise be ``unknown``/empty/malformed (e.g. ARG not passed AND no ``.git`` in
the Docker build context), the build FAILS LOUDLY (non-zero exit) instead of
silently embedding a wrong/placeholder identity. This is what guarantees the
isolated image self-reports its EXACT source SHA.

Usage:
    python3 -m scripts.gen_build_info
    ARBICORE_GIT_SHA=<sha> ARBICORE_GIT_STRICT=1 python3 -m scripts.gen_build_info
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # app/backend
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _git(args):
    try:
        out = subprocess.run(["git", *args], cwd=str(_ROOT),
                             capture_output=True, text=True, timeout=5)
        return (out.stdout or "").strip() or None
    except Exception:
        return None


def is_valid_full_sha(value) -> bool:
    """True only for a canonical 40-char lowercase-hex git object id."""
    return isinstance(value, str) and bool(_FULL_SHA_RE.match(value.strip().lower()))


def _truthy(value) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_git_identity(*, env: dict, live_sha, live_tag, strict: bool) -> dict:
    """Pure, testable identity resolver. In strict mode a non-40-hex SHA raises
    ValueError (the build must fail rather than embed a placeholder). Never
    silently coerces an unknown/malformed SHA into a passing build."""
    env_sha = (env.get("ARBICORE_GIT_SHA") or "").strip() or None
    if env_sha and not is_valid_full_sha(env_sha):
        # An explicitly-provided but malformed SHA is always an error, even in
        # non-strict mode — it can only mean a broken build invocation.
        raise ValueError(
            f"ARBICORE_GIT_SHA={env_sha!r} is not a 40-hex git object id")
    git_sha = env_sha or (live_sha or None) or "unknown"
    if strict and not is_valid_full_sha(git_sha):
        raise ValueError(
            "ARBICORE_GIT_STRICT is set but the source git SHA could not be "
            "resolved to a 40-hex id (got %r). Pass --build-arg "
            "GITSHA=$(git rev-parse HEAD) or run inside a git checkout; refusing "
            "to embed a placeholder identity." % git_sha)
    git_tag = ((env.get("ARBICORE_GIT_TAG") or "").strip()
               or (live_tag or None) or "unknown")
    return {"git_sha": git_sha, "git_tag": git_tag}


def build_info(*, env: dict, live_sha, live_tag, strict: bool) -> dict:
    ident = resolve_git_identity(env=env, live_sha=live_sha, live_tag=live_tag,
                                 strict=strict)
    return {
        "git_sha": ident["git_sha"],
        "git_tag": ident["git_tag"],
        "app_version": env.get("ARBICORE_VERSION") or ident["git_tag"],
        "image_digest": env.get("ARBICORE_IMAGE_DIGEST") or "unset",
        "image_ref": env.get("ARBICORE_IMAGE_REF") or "unset",
        "build_time": env.get("ARBICORE_BUILD_TIME")
        or datetime.now(timezone.utc).isoformat(),
        "runtime_env": env.get("ARBICORE_ENV") or "unset",
    }


def main() -> None:
    strict = _truthy(os.environ.get("ARBICORE_GIT_STRICT"))
    try:
        info = build_info(
            env=dict(os.environ),
            live_sha=_git(["rev-parse", "HEAD"]),
            live_tag=_git(["describe", "--tags", "--always", "--dirty"]),
            strict=strict)
    except ValueError as exc:
        print(f"gen_build_info: FATAL provenance error: {exc}", file=sys.stderr)
        raise SystemExit(2)
    dest = _ROOT / "BUILD_INFO.json"
    dest.write_text(json.dumps(info, indent=2) + "\n")
    print(f"wrote {dest}: {info}")


if __name__ == "__main__":
    main()
