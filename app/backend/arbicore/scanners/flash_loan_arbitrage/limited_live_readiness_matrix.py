"""End-to-end Limited-Live readiness matrix (pure, fail-closed reporting).

Aggregates every Limited-Live prerequisite into one classified matrix so the
audit report states EXACTLY what remains. Pure/deterministic: the caller passes
in the already-probed state; this module only classifies + summarises. It never
signs, broadcasts, enables Limited-Live, changes mode, or weakens a gate.

Status vocabulary:
  READY             prerequisite satisfied by software/config now
  BLOCKED           requires an irreversible on-chain / operator action
  UNKNOWN           could not be determined (fail closed — treated as not ready)
  MARKET-DEPENDENT  cannot be satisfied by us; needs a genuine on-chain
                    opportunity (a real CONFIRMED + profitable candidate)

Category tags separate WHO must act:
  software           already provisioned in the repo
  onchain_operator   deploy/verify executor, provision signer (IRREVERSIBLE)
  operator           mode ladder / kill switch (operator authorization)
  market             a naturally-discovered profitable candidate
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

READY = "READY"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"
MARKET = "MARKET-DEPENDENT"


def _item(name: str, status: str, category: str, detail: str) -> Dict[str, Any]:
    return {"prerequisite": name, "status": status, "category": category,
            "detail": detail}


def build_readiness_matrix(
    *,
    rpc_configured: bool,
    mongo_ok: bool,
    executor_address: Optional[str],
    executor_identity_ok: Optional[bool],
    signer: Dict[str, Any],
    operator_state: Dict[str, Any],
    confirmed_count: int,
) -> Dict[str, Any]:
    """Classify every Limited-Live prerequisite. See module docstring."""
    items: List[Dict[str, Any]] = []

    # --- Infrastructure (software-provisionable) -------------------------
    items.append(_item(
        "rpc_base", READY if rpc_configured else BLOCKED, "software",
        "read-only Base RPC for eth_call/eth_getCode/eth_blockNumber"
        if rpc_configured else "ARBICORE_RPC_URL_BASE not configured"))
    items.append(_item(
        "mongo_provenance", READY if mongo_ok else UNKNOWN, "software",
        "evidence store + exact-run provenance"
        if mongo_ok else "mongo/provenance unavailable"))

    # --- Executor (on-chain operator boundary) ---------------------------
    if executor_address:
        items.append(_item(
            "executor_deployed", READY, "software",
            f"executor address resolved: {executor_address}"))
        if executor_identity_ok is True:
            items.append(_item("executor_onchain_identity", READY, "software",
                               "on-chain owner/router/vault match expected"))
        elif executor_identity_ok is False:
            items.append(_item("executor_onchain_identity", BLOCKED, "onchain_operator",
                               "deployed bytecode/getters do not match expected"))
        else:
            items.append(_item("executor_onchain_identity", UNKNOWN, "onchain_operator",
                               "not verified on-chain in this run (RPC/inspection pending)"))
    else:
        items.append(_item(
            "executor_deployed", BLOCKED, "onchain_operator",
            "no executor address in env or registry for target chain — deploy required"))
        items.append(_item(
            "executor_onchain_identity", BLOCKED, "onchain_operator",
            "executor not provisioned"))

    # --- Signer authorization (operator vault; never a key here) ---------
    items.append(_item(
        "signer_authorization",
        READY if signer.get("ready") else BLOCKED, "onchain_operator",
        signer.get("reason", "signer readiness unknown")))

    # --- Operator mode + kill switch (operator authorization) ------------
    mode = operator_state.get("mode", "UNKNOWN")
    items.append(_item(
        "operator_mode_allows",
        READY if operator_state.get("mode_allows") else BLOCKED, "operator",
        f"mode={mode} (Limited-Live attempt permitted only in LIMITED_LIVE/"
        f"FULL_AUTOMATION; SHADOW correctly denies)"))
    ks_engaged = operator_state.get("kill_switch_engaged")
    items.append(_item(
        "kill_switch_ok",
        READY if operator_state.get("kill_switch_ok") else BLOCKED, "operator",
        f"kill_switch_engaged={ks_engaged}"))

    # --- Market-dependent (a genuine opportunity must appear) ------------
    items.append(_item(
        "confirmed_candidate",
        READY if confirmed_count > 0 else MARKET, "market",
        f"{confirmed_count} CONFIRMED candidate(s) this run"
        if confirmed_count > 0 else "0 CONFIRMED — WAIT (no defect)"))
    items.append(_item("executor_capability_route", MARKET, "market",
                       "per-candidate: UniV3-only routes SUPPORTED; Aerodrome/"
                       "unsupported venues remain DENIED"))
    items.append(_item("economics_gate7", MARKET, "market",
                       "per-candidate: atomic profit must clear the $25 floor "
                       "(unchanged)"))
    items.append(_item("gate8_liquidity", MARKET, "market",
                       "per-candidate: route TVL / Gate 8 (unchanged)"))
    items.append(_item("gate9_mev", MARKET, "market",
                       "per-candidate: Gate 9 MEV (unchanged)"))
    items.append(_item("balancer_liquidity", MARKET, "market",
                       "per-candidate: Balancer V2 AVAILABLE >= REQUESTED borrow"))
    items.append(_item("freshness", MARKET, "market",
                       "per-candidate: quote-age <= 12s, block-lag <= policy "
                       "(unchanged)"))
    # Atomic sim is software-wired but BLOCKED until a signer is authorized
    # (and then only satisfiable per real candidate) — fail closed today.
    atomic_status = MARKET if signer.get("ready") else BLOCKED
    items.append(_item("atomic_simulation", atomic_status, "onchain_operator",
                       "exact-tx read-only sim wired against executor; DENY until "
                       "signer authorized (and then per real candidate)"))

    blocked = [i for i in items if i["status"] == BLOCKED]
    unknown = [i for i in items if i["status"] == UNKNOWN]
    market = [i for i in items if i["status"] == MARKET]

    software_blockers = [i for i in blocked if i["category"] == "software"]
    if software_blockers:
        overall = "SOFTWARE_INCOMPLETE"
    elif blocked or unknown:
        overall = "AWAITING_OPERATOR_AND_ONCHAIN_ACTIONS"
    else:
        overall = "SOFTWARE_READY_MARKET_AND_OPERATOR_PENDING"

    return {
        "overall": overall,
        "counts": {"ready": sum(1 for i in items if i["status"] == READY),
                   "blocked": len(blocked), "unknown": len(unknown),
                   "market_dependent": len(market), "total": len(items)},
        "items": items,
        "blocked": [i["prerequisite"] for i in blocked],
        "unknown": [i["prerequisite"] for i in unknown],
        "market_dependent": [i["prerequisite"] for i in market],
        "signed": False, "broadcast": False, "limited_live_enabled": False,
        "note": ("software/readiness matrix only — code readiness is NOT "
                 "Limited-Live operational; enabling remains operator-gated"),
    }


__all__ = ["READY", "BLOCKED", "UNKNOWN", "MARKET", "build_readiness_matrix",
           "gather_and_build"]


async def gather_and_build(
    *, db: Any, rpc_url: str = "", chain: Any = None,
    confirmed_count: int = 0, mongo_ok: bool = True,
    inspector: Any = None,
) -> Dict[str, Any]:
    """CANONICAL readiness assembler reused by the VPS audit AND the readiness
    API — the single source of truth. Runs the read-only probes (operator mode +
    kill switch, executor identity, signer authorization) and builds the matrix.
    Never signs/broadcasts/enables anything.

    Returns: {matrix, operator_state, signer_state, executor_identity,
              executor_address, executor_address_resolved}.
    """
    from .live_readiness_probes import (
        probe_mode_and_kill_switch, probe_signer_readiness,
        probe_executor_identity, resolve_executor_address,
    )
    if chain is None:
        import os
        chain = os.environ.get("ARBICORE_CHAIN_ID", "8453")

    operator_state = await probe_mode_and_kill_switch(db=db)
    executor_address = resolve_executor_address(chain)
    identity = await probe_executor_identity(
        executor_address=executor_address, rpc_url=rpc_url, chain=chain,
        inspector=inspector)
    signer_state = probe_signer_readiness(executor_owner=identity.get("owner"))

    identity_ok = {"READY": True, "BLOCKED": False}.get(identity.get("status"))
    matrix = build_readiness_matrix(
        rpc_configured=bool(rpc_url), mongo_ok=mongo_ok,
        executor_address=executor_address, executor_identity_ok=identity_ok,
        signer=signer_state, operator_state=operator_state,
        confirmed_count=confirmed_count)
    return {
        "matrix": matrix, "operator_state": operator_state,
        "signer_state": signer_state, "executor_identity": identity,
        "executor_address": executor_address,
        "executor_address_resolved": bool(executor_address),
    }
