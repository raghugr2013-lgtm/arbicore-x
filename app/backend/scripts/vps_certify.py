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
from arbicore.certification.h09_real_bridge import simulate_candidate_binding
from arbicore.data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
from arbicore.runtime.composition import (
    get_db,
    run_single_canonical_flash_loan_audit_tick,
)
from arbicore.execution.quoter import QuoterRegistry
from scripts.arbicore_certify import _build_identity

_OUT = Path(os.environ.get("ARBICORE_CERT_OUT_DIR", "/app/vps_cert"))


def _git_commit() -> str:
    try:
        identity = _build_identity()
        return identity.get("git_sha") or "unknown"
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
    # 3: H05 sizer — EVIDENCE-based (flags alone can never PASS): certifies only
    # against a REAL exact-size quote fact captured from scan evidence.
    h05 = H.check_h05_sizer(exact_quote_fact=await H.latest_exact_quote_fact())
    # 4: H07 composition
    h07 = [H.check_h07_composition(c) for c in H.SIX_CHAINS]
    # 5: H08 receiver capability (Phase-B target: base sepolia 84532)
    target_chain = os.environ.get("ARBICORE_CERT_RECEIVER_CHAIN", "84532")
    h08 = await H.check_h08_receiver(target_chain)
    # 7: bytecode / immutables
    bytecode = await H.check_receiver_bytecode_immutables(target_chain)
    # 6: H09 — exact candidate-bound simulation.
    #
    # Run exactly one canonical diagnostic tick, then resolve candidates ONLY
    # from the evidence bundles stamped by that exact audit_run_id/tick_id.
    # No timestamp/latest fallback and no synthetic candidate construction.
    h09 = await _run_h09_candidate_simulation()

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


async def _run_h09_candidate_simulation() -> dict:
    """Run H09 against one real candidate from one canonical audit tick.

    Fail closed:
      - no exact tick identity -> UNKNOWN
      - no exact evidence -> UNKNOWN
      - no CONFIRMED candidate -> UNKNOWN
      - incomplete binding -> UNKNOWN
      - simulation failure -> UNKNOWN/FAIL as returned by bridge
    Never signs, broadcasts, or enables live execution.
    """
    try:
        rpc_url = os.environ.get("ARBICORE_RPC_URL_BASE", "").strip()
        if not rpc_url:
            return {
                "check": "H09 candidate-bound simulation",
                "status": H.UNKNOWN,
                "detail": "Base RPC unavailable; no candidate simulation attempted",
                "evidence": {"signed": False, "broadcast": False},
            }

        # Use the same canonical quoter/composition path as the scanner.
        quoter_registry = QuoterRegistry()
        meta = await run_single_canonical_flash_loan_audit_tick(quoter_registry)

        audit_run_id = meta.get("audit_run_id")
        scanner_tick_id = meta.get("scanner_tick_id")
        worker_id = meta.get("worker_id")

        if not audit_run_id or scanner_tick_id is None:
            return {
                "check": "H09 candidate-bound simulation",
                "status": H.UNKNOWN,
                "detail": "canonical audit tick did not produce exact provenance",
                "evidence": {
                    "audit_run_id": audit_run_id,
                    "scanner_tick_id": scanner_tick_id,
                    "worker_id": worker_id,
                    "signed": False,
                    "broadcast": False,
                },
            }

        repo = EvidenceBundlesRepo(get_db())
        rows = await repo.find_for_audit(
            audit_run_id=audit_run_id,
            scanner_tick_id=scanner_tick_id,
            worker_id=worker_id,
            source_component="flash_loan_arb_verifier",
        )

        confirmed = [
            r for r in rows
            if isinstance(r, dict)
            and r.get("verification_status") == "CONFIRMED"
            and r.get("broadcast") is not True
            and r.get("candidate_id")
        ]

        if not confirmed:
            return {
                "check": "H09 candidate-bound simulation",
                "status": H.UNKNOWN,
                "detail": (
                    "no CONFIRMED non-broadcast candidate was produced by "
                    "this exact canonical audit tick; simulation not attempted"
                ),
                "evidence": {
                    "audit_run_id": audit_run_id,
                    "scanner_tick_id": scanner_tick_id,
                    "worker_id": worker_id,
                    "bundle_count": len(rows),
                    "confirmed_candidates": 0,
                    "signed": False,
                    "broadcast": False,
                },
            }

        # Never simulate more than one candidate in this certification tick.
        # Deterministically select the strongest persisted economics only.
        def _profit(row):
            econ = row.get("economics")
            if not isinstance(econ, dict):
                return float("-inf")
            for key in (
                "expected_net_after_costs_usd",
                "atomic_profit_usd",
                "net_profit_usd",
            ):
                try:
                    value = econ.get(key)
                    if value is not None:
                        return float(value)
                except (TypeError, ValueError):
                    pass
            return float("-inf")

        candidate = max(
            confirmed,
            key=lambda r: (_profit(r), str(r.get("candidate_id") or "")),
        )
        candidate_id = str(candidate["candidate_id"])

        # Certification never needs or accepts a plaintext private key.
        # The bridge receives only the authoritative signer-presence boolean.
        signer_present = False
        signer_evidence = H.make_vault_signer_evidence(get_db())
        if isinstance(signer_evidence, dict):
            signer_present = bool(
                signer_evidence.get("present") is True
                and signer_evidence.get("matches_expected") is True
                and signer_evidence.get("derived_address")
            )

        result, diagnostic = await simulate_candidate_binding(
            repo,
            audit_run_id=audit_run_id,
            scanner_tick_id=scanner_tick_id,
            candidate_id=candidate_id,
            rpc_url=rpc_url,
            signer_present=signer_present,
            from_address=(
                signer_evidence.get("derived_address")
                if isinstance(signer_evidence, dict)
                else None
            ),
        )

        cert = diagnostic.get("certification") if isinstance(diagnostic, dict) else None
        passed = (
            isinstance(cert, dict)
            and cert.get("certified") is True
            and cert.get("tier") == "SIMULATION_CERTIFIED"
        )

        return {
            "check": "H09 candidate-bound simulation",
            "status": H.PASS if passed else H.UNKNOWN,
            "detail": (
                "real candidate-bound atomic simulation PASS"
                if passed
                else "candidate-bound simulation did not certify; fail closed"
            ),
            "evidence": {
                "audit_run_id": audit_run_id,
                "scanner_tick_id": scanner_tick_id,
                "worker_id": worker_id,
                "candidate_id": candidate_id,
                "simulation": result,
                "diagnostic": diagnostic,
                "signed": False,
                "broadcast": False,
            },
        }

    except Exception as exc:  # noqa: BLE001
        return {
            "check": "H09 candidate-bound simulation",
            "status": H.UNKNOWN,
            "detail": f"H09 integration failed closed: {type(exc).__name__}",
            "evidence": {
                "signed": False,
                "broadcast": False,
            },
        }


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
