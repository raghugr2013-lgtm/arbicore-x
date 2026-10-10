#!/usr/bin/env python3
"""Read-only Base→Alchemy failover metrics from isolated container logs.

HARD RULES
- Does NOT touch Gate 9 (`arbicore-x-backend-new`).
- Does NOT restart containers, change env/keys, or call RPC providers.
- Redacts Alchemy `/v2/<secret>` path segments; never prints key material.
- Intended for throwaway / second-stack log captures only.

See: docs/certification/BASE_FAILOVER_FIX_VALIDATION_PROCEDURE_20261002.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

GATE9_DENY = frozenset(
    {
        "arbicore-x-backend-new",
        "/arbicore-x-backend-new",
    }
)

# httpx default: HTTP Request: POST https://host[/path] "HTTP/1.1 429 Too Many Requests"
HTTPX_RE = re.compile(
    r"""HTTP Request:\s+POST\s+(https?://[^\s"]+)\s+"HTTP/1\.1\s+(\d+)""",
    re.IGNORECASE,
)
FAILOVER_RE = re.compile(
    r"""quoter:\s+hop\s+(\d+)\s+failing over from\s+(\S+)\s+to\s+(\S+)""",
    re.IGNORECASE,
)
COOLDOWN_RE = re.compile(r"host cooldown", re.IGNORECASE)
TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?)"
)

ALCHEMY_BASE_HOST = "base-mainnet.g.alchemy.com"
PUBLIC_BASE_HOST = "mainnet.base.org"


def _die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _redact_url(url: str) -> Tuple[str, Optional[str]]:
    """Return (host, optional fp8 of /v2/ path segment). Never return the secret."""
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        host = (p.hostname or "").lower()
        fp8 = None
        parts = [x for x in (p.path or "").split("/") if x]
        # Alchemy style: /v2/<key>
        if len(parts) >= 2 and parts[0].lower() == "v2":
            fp8 = hashlib.sha256(parts[1].encode("utf-8")).hexdigest()[:8]
        return host, fp8
    except Exception:  # noqa: BLE001
        return "unknown", None


def _parse_ts(line: str) -> Optional[float]:
    m = TS_RE.match(line.strip())
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    # Normalize Z
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    # Truncate fractional seconds to 6 digits for fromisoformat
    if "." in raw:
        head, rest = raw.split(".", 1)
        frac = ""
        tz = ""
        for i, ch in enumerate(rest):
            if ch.isdigit():
                frac += ch
            else:
                tz = rest[i:]
                break
        else:
            tz = ""
        raw = f"{head}.{frac[:6]}{tz}"
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _iter_lines_from_file(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            yield line.rstrip("\n")


def _iter_lines_from_docker(container: str, since: Optional[str], until: Optional[str]) -> Iterable[str]:
    name = container.strip()
    if name in GATE9_DENY or name.lstrip("/") in {x.lstrip("/") for x in GATE9_DENY}:
        _die(
            f"refusing Gate9 container {container!r}. "
            "Point this tool at an isolated throwaway container or a redacted log file."
        )
    cmd = ["docker", "logs", container]
    if since:
        cmd.extend(["--since", since])
    if until:
        cmd.extend(["--until", until])
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        _die("docker binary not found; pass --log-file instead")
    if proc.returncode != 0:
        _die(f"docker logs failed (rc={proc.returncode}): {(proc.stderr or '')[:200]}")
    # docker logs merges stdout/stderr; both may contain app lines
    blob = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    for line in blob.splitlines():
        yield line


def measure(lines: Iterable[str]) -> Dict:
    http_by_host_status: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    http_timestamps: Dict[str, List[float]] = defaultdict(list)
    failovers: List[Dict] = []
    cooldown_hits = 0
    first_ts: Optional[float] = None
    last_ts: Optional[float] = None
    fps: Dict[str, str] = {}

    for line in lines:
        ts = _parse_ts(line)
        if ts is not None:
            first_ts = ts if first_ts is None else min(first_ts, ts)
            last_ts = ts if last_ts is None else max(last_ts, ts)

        if COOLDOWN_RE.search(line):
            cooldown_hits += 1

        fm = FAILOVER_RE.search(line)
        if fm:
            src, dst = fm.group(2), fm.group(3)
            failovers.append(
                {
                    "hop": int(fm.group(1)),
                    "from_host": src,
                    "to_host": dst,
                    "ts": ts,
                    "base_to_alchemy": (
                        PUBLIC_BASE_HOST in src and "alchemy.com" in dst
                    ),
                }
            )

        hm = HTTPX_RE.search(line)
        if hm:
            host, fp8 = _redact_url(hm.group(1))
            status = hm.group(2)
            http_by_host_status[host][status] += 1
            if ts is not None:
                http_timestamps[host].append(ts)
            if fp8 and host.endswith("alchemy.com"):
                fps.setdefault(host, fp8)

    base_to_alchemy = [f for f in failovers if f.get("base_to_alchemy")]
    alchemy_stats = dict(http_by_host_status.get(ALCHEMY_BASE_HOST, {}))
    alchemy_posts = sum(alchemy_stats.values())
    alchemy_429 = int(alchemy_stats.get("429", 0))
    alchemy_200 = int(alchemy_stats.get("200", 0))
    public_stats = dict(http_by_host_status.get(PUBLIC_BASE_HOST, {}))
    public_posts = sum(public_stats.values())

    window_s = 0.0
    if first_ts is not None and last_ts is not None and last_ts > first_ts:
        window_s = last_ts - first_ts
    window_h = window_s / 3600.0 if window_s > 0 else 0.0

    n_fail = len(base_to_alchemy)
    posts_per_failover = (alchemy_posts / n_fail) if n_fail else None

    def _rate(host: str) -> Dict[str, Optional[float]]:
        stamps = sorted(http_timestamps.get(host, []))
        if len(stamps) < 2:
            return {"avg_per_s_10s": None, "peak_per_s": None, "n": len(stamps)}
        # 1s peak
        by_sec: Dict[int, int] = defaultdict(int)
        for t in stamps:
            by_sec[int(t)] += 1
        peak = max(by_sec.values()) if by_sec else 0
        # 10s rolling avg of rate
        rates = []
        left = 0
        for right, t in enumerate(stamps):
            while stamps[left] < t - 10.0:
                left += 1
            rates.append((right - left + 1) / 10.0)
        avg10 = sum(rates) / len(rates) if rates else None
        return {"avg_per_s_10s": avg10, "peak_per_s": float(peak), "n": len(stamps)}

    return {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {
            "first_ts_utc": (
                datetime.fromtimestamp(first_ts, tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                if first_ts is not None
                else None
            ),
            "last_ts_utc": (
                datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                if last_ts is not None
                else None
            ),
            "seconds": round(window_s, 3),
            "hours": round(window_h, 6),
        },
        "metrics": {
            "M1_base_failover_events": n_fail,
            "M1_base_failover_events_per_hour": (
                round(n_fail / window_h, 3) if window_h > 0 else None
            ),
            "M2_alchemy_posts_per_failover": (
                round(posts_per_failover, 3) if posts_per_failover is not None else None
            ),
            "M3_alchemy_429_count": alchemy_429,
            "M3_alchemy_429_per_hour": (
                round(alchemy_429 / window_h, 3) if window_h > 0 else None
            ),
            "M4_eth_call_volume": None,  # fill manually / from app counters
            "M5_successful_quotes": None,  # fill manually / validation API
            "M6_alchemy_request_rate": _rate(ALCHEMY_BASE_HOST),
            "M6_public_base_request_rate": _rate(PUBLIC_BASE_HOST),
            "M7_cooldown_log_hits": cooldown_hits,
            "M8_opportunity_impact": None,  # A/B/C/E or ok rates — fill manually
        },
        "counts": {
            "failover_events_total": len(failovers),
            "failover_base_to_alchemy": n_fail,
            "alchemy_base_posts": alchemy_posts,
            "alchemy_base_by_status": alchemy_stats,
            "alchemy_base_200": alchemy_200,
            "alchemy_base_429": alchemy_429,
            "public_base_posts": public_posts,
            "public_base_by_status": public_stats,
            "http_posts_by_host_status": {
                h: dict(st) for h, st in sorted(http_by_host_status.items())
            },
        },
        "identity_redacted": {
            "alchemy_host_fps": fps,  # host -> fp8 only
            "note": "fp8 = sha256(url_path_segment)[:8]; secret never emitted",
        },
        "pass_hints": {
            "C1_alchemy_posts_per_failover_le_2": (
                posts_per_failover is not None and posts_per_failover <= 2.0
            ),
            "C7_baseline_amplifier_approx_5": (
                posts_per_failover is not None and 4.5 <= posts_per_failover <= 5.5
            ),
            "note": "Full PASS/FAIL requires both arms + safety checks in the procedure doc.",
        },
        "safety": {
            "gate9_denied": True,
            "secrets_redacted": True,
            "mutates_runtime": False,
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Measure Base→Alchemy failover amplification from isolated logs. "
            "Refuses Gate9 container arbicore-x-backend-new."
        )
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--log-file", type=Path, help="Redacted or raw log file path")
    src.add_argument(
        "--container",
        help="Isolated container name for docker logs (Gate9 name refused)",
    )
    ap.add_argument("--since", help="docker logs --since (with --container)")
    ap.add_argument("--until", help="docker logs --until (with --container)")
    ap.add_argument("--arm", choices=("baseline", "treatment", "other"), default="other")
    ap.add_argument("--window-minutes", type=float, default=None, help="Annotate only")
    ap.add_argument("--out", type=Path, help="Write JSON metrics here")
    args = ap.parse_args(argv)

    if args.container:
        lines = _iter_lines_from_docker(args.container, args.since, args.until)
        source = {"type": "docker_logs", "container": args.container}
    else:
        if not args.log_file.exists():
            _die(f"log file not found: {args.log_file}")
        lines = _iter_lines_from_file(args.log_file)
        source = {"type": "log_file", "path": str(args.log_file)}

    result = measure(lines)
    result["arm"] = args.arm
    result["source"] = source
    if args.window_minutes is not None:
        result["declared_window_minutes"] = args.window_minutes

    text = json.dumps(result, indent=2, sort_keys=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
