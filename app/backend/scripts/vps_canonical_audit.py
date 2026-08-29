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


async def _assess_confirmed_readiness(
    bundles: list, *, db=None, rpc_url: str = "",
    executor_addr=None, chain: str = "base", operator_state=None,
) -> list:
    """Fail-closed Limited-Live readiness for each CONFIRMED bundle.

    Executor capability is PROVEN from the route venues. Balancer flash-loan
    liquidity, exact-tx atomic simulation and freshness are READ LIVE (read-only
    eth_call/eth_getCode/eth_blockNumber) via live_readiness_probes and DENY when
    unavailable/unverifiable/stale. Operator mode + kill switch are read honestly
    from the DB. Borrow sizing is feasible only when profitable AND executable.
    Nothing signs, broadcasts, or enables any live mode."""
    import time as _time
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
    from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
        ProviderStatus,
    )
    from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
        probe_atomic_simulation, probe_balancer_liquidity, probe_freshness,
    )

    try:
        _, pool_specs = build_pool_graph()
    except Exception:  # noqa: BLE001
        pool_specs = {}

    op = operator_state or {"mode_allows": False, "kill_switch_ok": False}

    # Current head block once (read-only) for the freshness policy.
    current_block = None
    if rpc_url:
        try:
            from arbicore.providers.rpc import EthJsonRpcProvider
            _p = EthJsonRpcProvider(chain=chain, url=rpc_url)
            try:
                current_block = await _p.eth_get_block_number()
            finally:
                await _p.close()
        except Exception:  # noqa: BLE001 — freshness fails closed on None
            current_block = None
    now_ts = _time.time()

    out = []
    for b in bundles:
        route = b.get("route") or {}
        route_pools = list(route.get("route_pools") or [])
        cap = evaluate_executor_capability(
            route_pools=route_pools, pool_specs=pool_specs,
            executor_address=executor_addr)

        # 1) Exact-tx atomic simulation (read-only; never signs/broadcasts).
        atomic = await probe_atomic_simulation(
            bundle=b, executor_address=executor_addr, rpc_url=rpc_url)

        # 2) Balancer V2 Vault liquidity (AVAILABLE vs REQUESTED borrow).
        bal = await probe_balancer_liquidity(
            bundle=b, rpc_url=rpc_url, chain=chain)
        bal_confirmed = (bal is not None
                         and bal.status == ProviderStatus.ON_CHAIN_CONFIRMED)

        # 3) Freshness (documented quote-age + block-lag policy).
        fresh = probe_freshness(
            bundle=b, current_block=current_block, now_ts=now_ts)

        econ = b.get("economics") or {}
        size_eval = BorrowSizeEval(
            size_usd=float(b.get("input_amount_usd") or 0.0),
            net_profit_usd=econ.get("atomic_profit_usd"),
            gross_spread_pct=(b.get("quotes") or {}).get("gross_profit_pct"),
            quote_complete=(b.get("quotes") or {}).get("route_quote_status") == "ok",
            economics_ok=isinstance(econ.get("atomic_profit_usd"), (int, float))
            and (econ.get("atomic_profit_usd") or 0) > 0,
            liquidity_sufficient=bool(bal_confirmed),
            executor_supported=cap.is_supported,
            atomic_sim_passed=bool(atomic.get("passed")),
            reason="live per-size proof from Balancer liquidity + atomic sim")
        size_decision = select_borrow_size([size_eval])

        controls = ReadinessControls(
            executor_capability=cap,
            balancer_liquidity=bal,
            borrow_size=size_decision,
            atomic_sim=atomic,
            freshness_ok=bool(fresh.get("ok")),
            mode_allows=bool(op.get("mode_allows")),
            kill_switch_ok=bool(op.get("kill_switch_ok")))
        rec = assess_candidate_readiness(b, controls)
        rec["freshness"] = fresh
        out.append(rec)
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

    # Honest operator mode + kill-switch state (read-only; never enables/changes
    # anything). Reported regardless of confirmed count for diagnosability.
    from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
        probe_mode_and_kill_switch, probe_signer_readiness,
        resolve_executor_address,
    )
    from arbicore.scanners.flash_loan_arbitrage.limited_live_readiness_matrix import (
        build_readiness_matrix,
    )
    operator_state = await probe_mode_and_kill_switch(db=db)
    report["operator_state"] = operator_state

    # Executor address: env first (sole runtime source), else read-only registry.
    executor_addr = resolve_executor_address()
    rpc_url = (os.environ.get("ARBICORE_RPC_URL_BASE")
               or os.environ.get("ARBICORE_RPC_URL") or "")
    signer_state = probe_signer_readiness(executor_owner=None)
    report["signer_state"] = signer_state
    report["executor_address_resolved"] = bool(executor_addr)

    report["readiness"] = await _assess_confirmed_readiness(
        confirmed_bundles, db=db, rpc_url=rpc_url,
        executor_addr=executor_addr, operator_state=operator_state)
    report["limited_live_eligible_candidates"] = [
        r["provenance"]["candidate_id"] for r in report["readiness"]
        if r["limited_live"]["eligible"]]

    # End-to-end readiness matrix (READY / BLOCKED / UNKNOWN / MARKET-DEPENDENT).
    report["limited_live_readiness_matrix"] = build_readiness_matrix(
        rpc_configured=bool(rpc_url), mongo_ok=True,
        executor_address=executor_addr, executor_identity_ok=None,
        signer=signer_state, operator_state=operator_state,
        confirmed_count=len(confirmed_candidate_ids))

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
