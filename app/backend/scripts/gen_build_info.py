"""Write backend/BUILD_INFO.json from the current git checkout.

Run this in CI / the Docker build (before .git is stripped) so the deployed
image reports a real deployment identity via GET /api/arbicore/version even
without ARBICORE_GIT_* env vars. Env vars still take precedence at runtime.

Usage:
    python3 -m scripts.gen_build_info
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # app/backend


def _git(args):
    try:
        out = subprocess.run(["git", *args], cwd=str(_ROOT),
                             capture_output=True, text=True, timeout=5)
        return (out.stdout or "").strip() or None
    except Exception:
        return None


def main() -> None:
    git_sha = os.environ.get("ARBICORE_GIT_SHA") or _git(["rev-parse", "HEAD"]) or "unknown"
    git_tag = (os.environ.get("ARBICORE_GIT_TAG")
               or _git(["describe", "--tags", "--always", "--dirty"]) or "unknown")
    info = {
        "git_sha": git_sha,
        "git_tag": git_tag,
        "app_version": os.environ.get("ARBICORE_VERSION") or git_tag,
        "image_digest": os.environ.get("ARBICORE_IMAGE_DIGEST") or "unset",
        "image_ref": os.environ.get("ARBICORE_IMAGE_REF") or "unset",
        "build_time": os.environ.get("ARBICORE_BUILD_TIME")
        or datetime.now(timezone.utc).isoformat(),
        "runtime_env": os.environ.get("ARBICORE_ENV") or "unset",
    }
    dest = _ROOT / "BUILD_INFO.json"
    dest.write_text(json.dumps(info, indent=2) + "\n")
    print(f"wrote {dest}: {info}")


if __name__ == "__main__":
    main()
