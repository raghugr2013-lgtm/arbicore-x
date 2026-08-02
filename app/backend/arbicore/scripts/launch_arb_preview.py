"""CLI helper — `python -m arbicore.scripts.launch_arb_preview`.

Read-only operator dashboard. Fetches the existing
``GET /api/arbicore/scanners/launch_arb/preview`` diagnostic endpoint and
renders the result to terminal. Zero side effects: no DB writes, no state
mutation, no scanner activation.

Usage:
    python -m arbicore.scripts.launch_arb_preview \
        --base-url http://localhost:8001 \
        --username admin --password '...'

If `--base-url` is omitted, the script reads `REACT_APP_BACKEND_URL` from
`frontend/.env`. Credentials may be supplied via `ARBICORE_ADMIN_USER` and
`ARBICORE_ADMIN_PASS` env vars instead of CLI flags.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import httpx


def _load_default_base_url() -> Optional[str]:
    """Read REACT_APP_BACKEND_URL from /app/frontend/.env if available."""
    env_path = Path("/app/frontend/.env")
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _login(base_url: str, username: str, password: str
           ) -> httpx.Cookies:
    with httpx.Client(timeout=15.0) as c:
        r = c.post(f"{base_url}/api/auth/login",
                    json={"username": username, "password": password})
        if r.status_code != 200:
            raise SystemExit(
                f"login failed: HTTP {r.status_code} {r.text[:200]}"
            )
        return c.cookies


def _fetch_preview(base_url: str, cookies: httpx.Cookies) -> dict:
    with httpx.Client(timeout=15.0, cookies=cookies) as c:
        r = c.get(f"{base_url}/api/arbicore/scanners/launch_arb/preview")
        if r.status_code != 200:
            raise SystemExit(
                f"preview fetch failed: HTTP {r.status_code} {r.text[:200]}"
            )
        return r.json()


# ----- pretty render -------------------------------------------------------

def _render(payload: dict) -> str:
    lines: list = []
    lines.append("=" * 72)
    lines.append("ArbiCore X — Launch Intelligence Preview "
                  f"(wave {payload.get('wave', '?')})")
    lines.append("=" * 72)
    st = payload.get("scanner_state") or {}
    lines.append(f"Scanner state:   enabled={st.get('enabled')}  "
                  f"dormant_reason='{st.get('dormant_reason')}'")
    lines.append("")
    lines.append("Sources:")
    for s in payload.get("sources") or []:
        flag_creds = "Y" if s.get("credentials_present") else "N"
        flag_ok    = "Y" if s.get("health_ok") else "N"
        flag_en    = "Y" if s.get("enabled_in_config") else "N"
        err = s.get("health_last_error") or ""
        lines.append(
            f"  {s.get('source_id','?'):32s}"
            f"  tier={s.get('tier','?')}"
            f"  enabled={flag_en}"
            f"  creds={flag_creds}"
            f"  ok={flag_ok}"
            f"  err={err}"
        )
    lines.append("")
    lines.append("Credentials (presence only):")
    for k, v in (payload.get("credential_status") or {}).items():
        lines.append(f"  {k:30s}  {'SET' if v else 'MISSING'}")
    lines.append("")
    lines.append("Invariants:")
    for k, v in (payload.get("invariants") or {}).items():
        lines.append(f"  {k:50s} {v}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url",
                        default=os.environ.get("ARBICORE_BASE_URL")
                                or _load_default_base_url(),
                        help="ArbiCore API base URL (default: from "
                              "/app/frontend/.env REACT_APP_BACKEND_URL)")
    parser.add_argument("--username",
                        default=os.environ.get("ARBICORE_ADMIN_USER", "admin"))
    parser.add_argument("--password",
                        default=os.environ.get("ARBICORE_ADMIN_PASS"))
    parser.add_argument("--json", action="store_true",
                        help="Print raw JSON instead of the dashboard")
    args = parser.parse_args()

    if not args.base_url:
        print("error: --base-url not provided and "
                "/app/frontend/.env not readable", file=sys.stderr)
        return 2
    if not args.password:
        print("error: --password or ARBICORE_ADMIN_PASS required",
                file=sys.stderr)
        return 2

    cookies = _login(args.base_url, args.username, args.password)
    payload = _fetch_preview(args.base_url, cookies)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(_render(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
