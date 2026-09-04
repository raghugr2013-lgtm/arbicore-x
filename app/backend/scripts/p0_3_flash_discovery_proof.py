"""P0 #3 — read-only Base flash-loan discovery proof (pod).

Wires the canonical FlashLoanArbitrageScanner with the LIVE Base quote provider
(no boot 8s cap) and runs exactly ONE real _tick() against live Base on-chain
data. Detection-only: never signs, never broadcasts, never enables a live mode.
Reads back the genuine evidence bundles produced by that exact tick.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def main() -> None:
    from arbicore.runtime import composition as comp
    from arbicore.execution.quoter import QuoterRegistry

    qr = QuoterRegistry()

    scanner_before = comp.get_flash_loan_arb_scanner()
    stats_before = dict(scanner_before.stats)

    meta = await comp.run_single_canonical_flash_loan_audit_tick(qr)

    scanner = comp.get_flash_loan_arb_scanner()
    stats_after = dict(scanner.stats)

    out = {
        "wiring_meta": meta,
        "stats_before": stats_before,
        "stats_after": stats_after,
        "quote_provider_is_default_after": scanner.quote_provider_is_default,
    }

    # Read back the genuine evidence bundles for this exact audit run/tick.
    audit_run_id = meta.get("audit_run_id")
    tick_id = meta.get("scanner_tick_id")
    bundles = []
    try:
        from arbicore.data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
        repo = EvidenceBundlesRepo(comp.get_db())
        if hasattr(repo, "find_for_audit"):
            bundles = await repo.find_for_audit(audit_run_id, tick_id)
    except Exception as exc:  # noqa: BLE001
        out["evidence_read_error"] = f"{type(exc).__name__}: {exc}"
    out["evidence_bundle_count"] = len(bundles)
    out["evidence_sample"] = bundles[:3]

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
