#!/usr/bin/env python3
"""VPS software-certification runner (READ-ONLY, fail-closed).

Runs the ArbiCore X certification harness against operator infrastructure and
writes a human-readable report + machine-readable JSON to ``/app/vps_cert/``
(override with ARBICORE_CERT_OUT_DIR). NEVER signs / broadcasts / deploys /
mutates env / performs a real transaction. No secret is written to any output.

Usage (on the VPS certification/staging container, with operator RPCs exported
in its git-ignored env):

    cd /app/backend && PYTHONPATH=. python3 -m scripts.vps_certify
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from arbicore.certification import vps_harness as H

_OUT = Path(os.environ.get("ARBICORE_CERT_OUT_DIR", "/app/vps_cert"))


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd="/app",
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _safety_state() -> dict:
    def off(k, default="false"):
        return os.environ.get(k, default).lower() != "true"
    return {
        "signing_off": off("ARBICORE_SIGNING_ENABLED"),
        "broadcast_off": off("ARBICORE_BROADCAST_ENABLED"),
        "auto_exec_off": os.environ.get("ARBICORE_AUTOEXEC_AUTOSTART",
                                        "false").lower() != "true",
        "full_live_off": off("ARBICORE_FULL_LIVE_ENABLED"),
        "limited_live_off": off("ARBICORE_LIMITED_LIVE_ENABLED"),
    }


async def run() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    checks: list = []

    # Section 1/2: six-chain RPC + chain-id
    rpc = [await H.check_rpc_and_chainid(c) for c in H.SIX_CHAINS]
    # isolation (TVL/pricing chain scoping)
    iso = [H.check_chain_scoped_isolation(c) for c in H.SIX_CHAINS]
    # 3: H05 sizer
    h05 = H.check_h05_sizer()
    # 4: H07 composition
    h07 = [H.check_h07_composition(c) for c in H.SIX_CHAINS]
    # 5: H08 receiver capability (Phase-B target: base sepolia 84532)
    target_chain = os.environ.get("ARBICORE_CERT_RECEIVER_CHAIN", "84532")
    h08 = await H.check_h08_receiver(target_chain)
    # 7: bytecode / immutables
    bytecode = await H.check_receiver_bytecode_immutables(target_chain)
    # 6: H09 simulation prereqs
    h09 = H.check_h09_simulation_prereqs()

    checks = rpc + iso + [h05] + h07 + [h08, bytecode, h09]

    counts: dict = {}
    for c in checks:
        counts[c["status"]] = counts.get(c["status"], 0) + 1

    return {
        "schema": "arbicore.vps_certification/v1",
        "generated_at": ts,
        "commit": _git_commit(),
        "receiver_target_chain": target_chain,
        "safety_state": _safety_state(),
        "status_counts": counts,
        "sections": {
            "1_six_chain_rpc": rpc,
            "2_chain_id": [{"check": r["check"],
                            "expected_chain_id": r["evidence"].get("expected_chain_id"),
                            "status": r["status"]} for r in rpc],
            "3_h05_exact_size": h05,
            "4_h07_runtime": h07,
            "5_h08_receiver_capability": h08,
            "6_h09_simulation": h09,
            "7_bytecode_immutables": bytecode,
            "8_isolation_tvl_pricing": iso,
        },
        "all_checks": checks,
    }


_MD_ORDER = [
    ("1. Six-chain RPC verification", "1_six_chain_rpc"),
    ("2. Chain-ID results", "2_chain_id"),
    ("3. H05 exact-size result", "3_h05_exact_size"),
    ("4. H07 runtime result", "4_h07_runtime"),
    ("5. H08 receiver identity/capability result", "5_h08_receiver_capability"),
    ("6. H09 simulation result", "6_h09_simulation"),
    ("7. Executor/receiver bytecode & immutable verification", "7_bytecode_immutables"),
    ("8. Liquidity/provider evidence (chain-scoped TVL/pricing)", "8_isolation_tvl_pricing"),
]


def _fmt(v) -> str:
    if isinstance(v, list):
        return "\n".join(
            f"  - **{x['check']}** → `{x['status']}` — {x.get('detail','')}"
            for x in v)
    return f"  - **{v['check']}** → `{v['status']}` — {v.get('detail','')}"


def _report_md(data: dict) -> str:
    s = data["sections"]
    blockers = [
        f"  - **{c['check']}** (`{c['status']}`): {c['detail']}"
        for c in data["all_checks"]
        if c["status"] in (H.FAIL, H.BLOCKED, H.NOT_CONFIGURED)
    ] or ["  - none"]
    lines = [
        "# ArbiCore X v2 — VPS Software Certification Report",
        "",
        f"- Generated: {data['generated_at']}",
        f"- Commit: `{data['commit']}`",
        f"- Receiver target chain (non-production): `{data['receiver_target_chain']}`",
        f"- Status counts: `{data['status_counts']}`",
        "",
        "Statuses: PASS | FAIL | BLOCKED | UNKNOWN | NOT_CONFIGURED. "
        "VPS-unavailable evidence is never upgraded to PASS.",
        "",
    ]
    for title, key in _MD_ORDER:
        lines += [f"## {title}", _fmt(s[key]), ""]
    lines += [
        "## 9. Exact commit / image deployed",
        f"  - commit: `{data['commit']}`",
        "  - image: set ARBICORE_CERT_IMAGE in the cert env to record it",
        "",
        "## 10. Safety-state confirmations",
        *[f"  - {k}: `{v}`" for k, v in data["safety_state"].items()],
        "",
        "## 11. Failures / blockers requiring further work",
        *blockers,
        "",
        "## 12. Exact evidence required before Opportunity Race",
        "  - PASS on six-chain RPC + chain-id (operator RPCs, no mismatch, ≥2 endpoints for failover)",
        "  - H05: price feed + borrow_sizer enabled AND a live exact-size quote binding quote_notional_usd",
        "  - H07: live per-chain composition proven against operator RPC/TVL/pricing",
        "  - H08: deployed receiver on-chain-verified AND explicitly declaring the venue provider(s)",
        "  - H09: a COMPLETE candidate binding + an exact candidate-bound simulation PASS + chain match",
        "  - B: executor bytecode/immutables/owner verified on-chain against the artifact",
        "  - Signing/broadcast/auto-exec/Limited-Live remain OFF until explicitly approved",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    data = asyncio.get_event_loop().run_until_complete(run())
    _OUT.mkdir(parents=True, exist_ok=True)
    (_OUT / "certification_evidence.json").write_text(json.dumps(data, indent=2))
    (_OUT / "certification_report.md").write_text(_report_md(data))
    print(f"wrote {_OUT}/certification_report.md and certification_evidence.json")
    print("status_counts:", data["status_counts"])


if __name__ == "__main__":
    main()
