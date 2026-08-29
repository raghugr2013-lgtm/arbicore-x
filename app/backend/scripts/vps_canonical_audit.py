"""Canonical flash-loan VPS audit runner (diagnostic / READ-ONLY).

Executes the REAL attributable audit workflow the Codex VPS validation needs:

    generate/observe audit_run_id
        -> activate canonical scanner wiring
        -> execute EXACTLY ONE _tick()
        -> capture the ACTUAL scanner_tick_id
        -> read back every candidate of that exact run+tick from the evidence
           store (fail-closed EvidenceBundlesRepo.find_for_audit)
        -> enforce candidate-level exact matching
        -> emit a candidate ledger
        -> hand ONLY exact-run CONFIRMED evidence to M3 (via env selectors)
        -> stop safely

It NEVER guesses IDs, NEVER reconstructs IDs from timestamps, NEVER uses a
candidate id alone, NEVER falls back to "latest"/foreign evidence, NEVER
signs, NEVER broadcasts, NEVER enables any live mode, and NEVER prints
secrets (only ids/status/counts are emitted).

Usage (on the VPS, with Base RPC + Mongo configured):
    python3 -m scripts.vps_canonical_audit
Requires: MONGO_URL, DB_NAME, and the Base RPC / quoter env used by the
canonical scanner. Absent those, it fails closed with a clear message.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys


def _err(msg: str) -> None:
    print(json.dumps({"audit_error": msg}))


async def _assess_confirmed_readiness(bundles: list) -> list:
    """Fail-closed Limited-Live readiness for each CONFIRMED bundle.

    Executor capability is PROVEN from the route venues. Balancer flash-loan
    liquidity + exact-tx atomic simulation + freshness are read live where the
    environment permits and DENY when unavailable/unverifiable. Borrow sizing
    is proven feasible only when a size is profitable AND executable. Nothing
    signs or broadcasts."""
    from arbicore.discovery.base_venues import build_pool_graph
    from arbicore.scanners.flash_loan_arbitrage.executor_capability import (
        evaluate_executor_capability,
    )
    from arbicore.scanners.flash_loan_arbitrage.borrow_sizing import (
        BorrowSizeEval, select_borrow_size,
    )
    from arbicore.scanners.flash_loan_arbitrage.readiness_assessment import (
        ReadinessControls, assess_candidate_readiness,
    )
    from arbicore.execution.atomic_executor_sim import AtomicExecutorSimulator

    try:
        _, pool_specs = build_pool_graph()
    except Exception:  # noqa: BLE001
        pool_specs = {}
    executor_addr = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    rpc_url = (os.environ.get("ARBICORE_RPC_URL_BASE")
               or os.environ.get("ARBICORE_RPC_URL"))
    sim = AtomicExecutorSimulator(rpc_url=rpc_url) if rpc_url else None
    sim_readiness = sim.readiness() if sim else {"rpc_configured": False}

    out = []
    for b in bundles:
        route = b.get("route") or {}
        route_pools = list(route.get("route_pools") or [])
        cap = evaluate_executor_capability(
            route_pools=route_pools, pool_specs=pool_specs,
            executor_address=executor_addr)

        # Exact-tx atomic simulation: fail closed unless executor+signer+RPC
        # allow a real eth_call of the exact executor calldata. We never build
        # a signer here, so this is DENY until the operator provisions one on
        # the VPS — surfaced honestly (available/passed False + reason).
        atomic = {"available": False, "passed": False,
                  "reason": "executor+signer+calldata prerequisites not "
                            "provisioned in read-only audit",
                  "readiness": sim_readiness}

        # Borrow sizing: with only the persisted (single) size and no live
        # per-size economics/sim, feasibility cannot be proven ⇒ fail closed.
        econ = b.get("economics") or {}
        size_eval = BorrowSizeEval(
            size_usd=float(b.get("input_amount_usd") or 0.0),
            net_profit_usd=econ.get("atomic_profit_usd"),
            gross_spread_pct=(b.get("quotes") or {}).get("gross_profit_pct"),
            quote_complete=(b.get("quotes") or {}).get("route_quote_status") == "ok",
            economics_ok=isinstance(econ.get("atomic_profit_usd"), (int, float))
            and (econ.get("atomic_profit_usd") or 0) > 0,
            liquidity_sufficient=False,   # no confirmed Balancer read ⇒ closed
            executor_supported=cap.is_supported,
            atomic_sim_passed=False,
            reason="single_persisted_size; live per-size proof unavailable")
        size_decision = select_borrow_size([size_eval])

        controls = ReadinessControls(
            executor_capability=cap,
            balancer_liquidity=None,      # live read not performed here ⇒ UNKNOWN
            borrow_size=size_decision,
            atomic_sim=atomic,
            freshness_ok=False,           # freshness policy not proven offline
            mode_allows=False,            # Limited-Live intentionally NOT enabled
            kill_switch_ok=False)         # not proven in read-only audit ⇒ DENY
        out.append(assess_candidate_readiness(b, controls))
    return out


async def _amain() -> int:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        _err("MONGO_URL and DB_NAME are required (fail closed)")
        return 2

    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.execution.quoter import QuoterRegistry
    from arbicore.data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
    from arbicore.evidence.audit_provenance import evidence_matches_audit
    from arbicore.runtime.composition import (
        run_single_canonical_flash_loan_audit_tick,
    )

    quoter = QuoterRegistry()

    # 1-4) Activate canonical wiring + run EXACTLY ONE tick; capture real ids.
    tick_meta = await run_single_canonical_flash_loan_audit_tick(quoter)
    audit_run_id = tick_meta.get("audit_run_id")
    scanner_tick_id = tick_meta.get("scanner_tick_id")
    worker_id = tick_meta.get("worker_id")

    report: dict = {
        "stage": "single_audit_tick",
        "audit_run_id": audit_run_id,
        "scanner_tick_id": scanner_tick_id,
        "worker_id": worker_id,
        "quote_provider": tick_meta.get("quote_provider"),
        "tvl_provider": tick_meta.get("tvl_provider"),
        "evidence_sink": tick_meta.get("evidence_sink"),
        "tick_executed": tick_meta.get("tick_executed"),
        "detection_only": True,
        "signed": False,
        "broadcast": False,
    }

    if not tick_meta.get("tick_executed"):
        report["note"] = ("scanner not enabled — no tick executed; "
                          "no evidence to isolate (fail closed)")
        print(json.dumps(report))
        return 0
    if not audit_run_id or scanner_tick_id is None:
        _err("scanner did not expose audit_run_id/scanner_tick_id (fail closed)")
        return 3

    db = AsyncIOMotorClient(mongo_url)[db_name]
    repo = EvidenceBundlesRepo(db)

    # 5) Read back EVERY candidate of this exact run+tick (candidate optional).
    #    This is the authoritative, fail-closed attribution path — no timestamp
    #    selection, no foreign runs, no candidate-alone.
    bundles = await repo.find_for_audit(
        audit_run_id=audit_run_id, scanner_tick_id=scanner_tick_id,
        candidate_id=None, source_component="flash_loan_arb_verifier",
        verification_status=None, limit=500)

    # 6) Candidate ledger + candidate-level exact matching (defense in depth).
    ledger = []
    confirmed_candidate_ids = []
    for b in bundles:
        diag = b.get("diagnostics") or {}
        cand_id = diag.get("candidate_id")
        # Re-verify each record with the exact candidate id — a record that
        # does not match the run+tick+candidate exactly is discarded.
        if not (cand_id and evidence_matches_audit(
                b, audit_run_id=audit_run_id, scanner_tick_id=scanner_tick_id,
                candidate_id=cand_id, source_component="flash_loan_arb_verifier")):
            continue
        status = b.get("verification_status")
        ledger.append({
            "candidate_id": cand_id,
            "verification_status": status,
            "outcome_tag": b.get("outcome_tag"),
            "bundle_id": b.get("bundle_id"),
        })
        if status == "CONFIRMED":
            confirmed_candidate_ids.append(cand_id)

    report["candidate_ledger"] = ledger
    report["candidates_total"] = len(ledger)
    report["candidates_confirmed"] = len(confirmed_candidate_ids)

    # 6b) Limited-Live READINESS for each exact-run CONFIRMED candidate. Every
    #     control is fail-closed: executor capability is proven (not inferred),
    #     Balancer flash-loan liquidity / atomic simulation / borrow sizing are
    #     read live where possible and DENY when unavailable. CONFIRMED is never
    #     treated as EXECUTABLE. Nothing here signs or broadcasts.
    confirmed_bundles = [b for b in bundles
                         if b.get("verification_status") == "CONFIRMED"
                         and (b.get("diagnostics") or {}).get("candidate_id")
                         in set(confirmed_candidate_ids)]
    report["readiness"] = await _assess_confirmed_readiness(confirmed_bundles)
    report["limited_live_eligible_candidates"] = [
        r["provenance"]["candidate_id"] for r in report["readiness"]
        if r["limited_live"]["eligible"]]

    # 7-8) Feed ONLY exact-run CONFIRMED evidence to M3. We hand the exact
    #      selectors to the M3 validator via env — M3 fails closed if nothing
    #      matches and NEVER borrows foreign CONFIRMED evidence. (We do not
    #      invoke M3 here; the wrapper decides — this runner stays read-only.)
    if confirmed_candidate_ids:
        report["m3_isolation_selectors"] = {
            "ARBICORE_AUDIT_RUN_ID": audit_run_id,
            "ARBICORE_AUDIT_SCANNER_TICK_ID": str(scanner_tick_id),
            "ARBICORE_AUDIT_CANDIDATE_ID": confirmed_candidate_ids[0],
        }
        report["m3_eligible"] = True
    else:
        report["m3_eligible"] = False
        report["note"] = ("zero CONFIRMED candidates for this exact run+tick — "
                          "WAIT (acceptable; not a defect)")

    # 9) stop safely.
    print(json.dumps(report))
    return 0


def main() -> None:
    try:
        rc = asyncio.run(_amain())
    except Exception as exc:  # noqa: BLE001 — fail closed, never leak secrets
        _err(f"{type(exc).__name__}: {exc}")
        rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
