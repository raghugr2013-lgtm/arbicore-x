"""VPS software-certification harness (P1 Batch 2 → VPS phase).

READ-ONLY, fail-closed certification of the ArbiCore X software against operator
infrastructure. It NEVER signs, broadcasts, deploys, mutates env, or performs a
real transaction. It reads operator RPCs from the environment (never from source
or chat) and classifies each check into one of:

    PASS | FAIL | BLOCKED | UNKNOWN | NOT_CONFIGURED

Fail-closed rule: VPS-unavailable / missing evidence is BLOCKED/UNKNOWN/
NOT_CONFIGURED — it is NEVER upgraded to PASS. No secret (RPC URL/API key) is
returned in any result — only redacted host:port or booleans.

Operator env conventions (set ONLY in the VPS git-ignored cert env):
  ARBICORE_RPC_URL_BASE / _ETHEREUM / _ARBITRUM / _OPTIMISM / _POLYGON / _BNB
  (or legacy <CHAIN>_RPC_URL / PROVIDER_RPC_URLS_<CHAIN>)
  ARBICORE_EXECUTOR_ADDRESS_BASE (+ per-chain via executor_registry)
  ARBICORE_PRICE_FEED_ENABLED=true and a price source ⇒ H05 sizer configured
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from arbicore.execution import quoter as _q
from arbicore.execution.receiver_capability import receiver_capability
from arbicore.certification.candidate_simulation import (
    CandidateSimulationBinding, evaluate_candidate_simulation,
)
from arbicore.certification.evidence_tiers import is_certifying_sim_method
from arbicore.execution.executor_registry import get_deployment
from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
    probe_executor_identity, resolve_executor_address,
)

SIX_CHAINS: List[str] = ["base", "ethereum", "arbitrum", "optimism",
                         "polygon", "bnb"]

PASS, FAIL, BLOCKED, UNKNOWN, NOT_CONFIGURED = (
    "PASS", "FAIL", "BLOCKED", "UNKNOWN", "NOT_CONFIGURED")
_VALID_STATUS = {PASS, FAIL, BLOCKED, UNKNOWN, NOT_CONFIGURED}


def _redact(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        return _q._redact_host(url)
    except Exception:  # noqa: BLE001
        return "redacted"


def _result(name: str, status: str, detail: str,
            evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    assert status in _VALID_STATUS, f"invalid status {status}"
    return {"check": name, "status": status, "detail": detail,
            "evidence": evidence or {}}


# ---------------------------------------------------------------------------
# A1 — six-chain read-only RPC + eth_chainId
# ---------------------------------------------------------------------------

async def check_rpc_and_chainid(chain: str) -> Dict[str, Any]:
    reg = _q.QuoterRegistry()
    cands = reg._rpc_url_candidates(chain)
    expected = _q._expected_chain_id(chain)
    if not cands:
        return _result(
            f"rpc:{chain}", NOT_CONFIGURED,
            "no operator RPC configured for this chain",
            {"expected_chain_id": expected, "endpoints": 0})
    verified: List[str] = []
    observed: Dict[str, Any] = {}
    reachable = 0
    for url in cands:
        _q._HOST_CHAIN_ID.pop(_q._host_key(url), None)
        cid = await _q._read_chain_id(url)
        host = _redact(url)
        observed[host] = cid
        if cid is not None:
            reachable += 1
            if cid == expected:
                verified.append(url)
    if reachable == 0:
        return _result(
            f"rpc:{chain}", BLOCKED,
            "all configured endpoints unreachable (eth_chainId unread) — "
            "VPS/network evidence unavailable (NOT a pass)",
            {"expected_chain_id": expected, "endpoints": len(cands),
             "observed": observed})
    if not verified:
        return _result(
            f"rpc:{chain}", FAIL,
            "reachable endpoints report the WRONG chain id (mismatch)",
            {"expected_chain_id": expected, "observed": observed})
    status = PASS
    failover = UNKNOWN if len(verified) < 2 else PASS
    return _result(
        f"rpc:{chain}", status,
        f"{len(verified)}/{len(cands)} endpoints verified for chain id "
        f"{expected}; failover={failover}",
        {"expected_chain_id": expected, "verified_endpoints": len(verified),
         "total_endpoints": len(cands), "failover": failover,
         "observed": observed})


# ---------------------------------------------------------------------------
# A2 — chain-scoped TVL / pricing isolation (code-property + config)
# ---------------------------------------------------------------------------

def check_chain_scoped_isolation(chain: str) -> Dict[str, Any]:
    # Isolation is structurally enforced (H06 endpoint chain-id guard + H07
    # tvl_provider_chain + Base-only global alias). Whether a *live* per-chain
    # TVL/price provider is wired is a config question answered per chain.
    reg = _q.QuoterRegistry()
    has_rpc = bool(reg._rpc_url_candidates(chain))
    price_feed = os.environ.get("ARBICORE_PRICE_FEED_ENABLED", "").lower() == "true"
    if not has_rpc:
        return _result(
            f"isolation:{chain}", NOT_CONFIGURED,
            "no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)",
            {"rpc": False, "price_feed_enabled": price_feed})
    # base has a wired composition/TVL/price feed; non-base needs per-chain wiring
    if chain == "base":
        status = PASS if price_feed else NOT_CONFIGURED
        return _result(
            f"isolation:{chain}", status,
            "base composition present; TVL/pricing chain-scoped "
            f"(price_feed_enabled={price_feed})",
            {"rpc": True, "price_feed_enabled": price_feed})
    return _result(
        f"isolation:{chain}", NOT_CONFIGURED,
        "non-base per-chain TVL/price provider not wired in-repo — fail closed "
        "(isolation guards enforced; live provider is VPS/operator work)",
        {"rpc": True, "price_feed_enabled": price_feed})


# ---------------------------------------------------------------------------
# A3 — H05 exact-size sizer prerequisites
# ---------------------------------------------------------------------------

def check_h05_sizer() -> Dict[str, Any]:
    enabled = os.environ.get("ARBICORE_PRICE_FEED_ENABLED", "").lower() == "true"
    sizer = os.environ.get("ARBICORE_BORROW_SIZER_ENABLED", "").lower() == "true"
    if not (enabled and sizer):
        return _result(
            "h05:exact_size_sizer", NOT_CONFIGURED,
            "operator price feed / borrow_sizer not enabled ⇒ quotes remain "
            "PROBE-sized and economics fail closed (DENIED_SIZE_NOT_QUOTED). "
            "This is the required fail-closed state without a sizer.",
            {"price_feed_enabled": enabled, "borrow_sizer_enabled": sizer})
    return _result(
        "h05:exact_size_sizer", PASS,
        "price feed + borrow_sizer enabled — exact-size economics can bind "
        "quote_notional_usd (verify a live exact-size quote separately)",
        {"price_feed_enabled": enabled, "borrow_sizer_enabled": sizer})


# ---------------------------------------------------------------------------
# A4 — H07 six-chain composition readiness
# ---------------------------------------------------------------------------

def check_h07_composition(chain: str) -> Dict[str, Any]:
    reg = _q.QuoterRegistry()
    has_rpc = bool(reg._rpc_url_candidates(chain))
    if not has_rpc:
        return _result(f"h07:{chain}", NOT_CONFIGURED,
                       "no RPC ⇒ composition fails closed", {"rpc": False})
    if chain == "base":
        return _result(f"h07:{chain}", UNKNOWN,
                       "base composition exists; live runtime proof requires "
                       "operator RPC + price feed + TVL provider (run on VPS)",
                       {"rpc": True})
    return _result(f"h07:{chain}", NOT_CONFIGURED,
                   "non-base canonical composition not wired — fail closed",
                   {"rpc": True})


# ---------------------------------------------------------------------------
# A5/B — H08 receiver capability + on-chain identity/bytecode/immutables
# ---------------------------------------------------------------------------

async def check_h08_receiver(chain: Any) -> Dict[str, Any]:
    cap = receiver_capability(chain)
    if not cap.deployed:
        return _result("h08:receiver", BLOCKED,
                       f"no deployed receiver for chain={chain} — {cap.note}",
                       cap.to_dict())
    if not cap.supported_providers:
        return _result(
            "h08:receiver", BLOCKED,
            "receiver deployed but declares NO supported_providers ⇒ every "
            "venue rejected (H08 stays FALSE until explicitly declared AND "
            "on-chain verified)", cap.to_dict())
    # providers declared → still must verify on-chain identity
    return _result("h08:receiver", UNKNOWN,
                   "supported_providers declared; on-chain verification "
                   "required (see bytecode/immutable check)", cap.to_dict())


async def check_receiver_bytecode_immutables(chain: Any) -> Dict[str, Any]:
    addr = resolve_executor_address(chain)
    reg = _q.QuoterRegistry()
    cands = reg._rpc_url_candidates(chain)
    rpc = cands[0] if cands else None
    rec = get_deployment(chain) or {}
    ctor = rec.get("constructor_args") or rec.get("constructor_args_expected") or {}
    expected = {"vault": ctor.get("balancerVault") or ctor.get("aavePool"),
                "router": ctor.get("uniRouter")}
    if not addr:
        return _result("b:bytecode_immutables", BLOCKED,
                       "no executor/receiver address for chain — fail closed",
                       {"chain": str(chain), "address": None})
    if not rpc:
        return _result("b:bytecode_immutables", BLOCKED,
                       "no operator RPC to inspect bytecode/immutables",
                       {"chain": str(chain), "address": addr,
                        "rpc_configured": False})
    probe = await probe_executor_identity(
        executor_address=addr, rpc_url=rpc, chain=chain, expected=expected)
    # map probe status to harness status (fail-closed)
    st_map = {"READY": PASS, "BLOCKED": FAIL, "UNKNOWN": UNKNOWN}
    status = st_map.get(probe.get("status"), UNKNOWN)
    return _result("b:bytecode_immutables", status,
                   f"on-chain identity probe: {probe.get('reason')}",
                   {"chain": str(chain), "address": addr,
                    "rpc": _redact(rpc), "expected": expected,
                    "probe": {k: probe.get(k) for k in
                              ("status", "reason", "exists", "bytecode_present",
                               "owner", "router", "vault",
                               "entrypoint_selector_present", "mismatches")}})


# ---------------------------------------------------------------------------
# A6 — H09 candidate-bound simulation prerequisites
# ---------------------------------------------------------------------------

def check_h09_simulation_prereqs() -> Dict[str, Any]:
    method = os.environ.get("ARBICORE_SIM_METHOD", "").strip().lower()
    certifying = is_certifying_sim_method(method)
    # a demonstration of the fail-closed contract with an intentionally empty
    # binding + the configured method (no live sim result available in-pod).
    empty = CandidateSimulationBinding()
    demo = evaluate_candidate_simulation(
        empty, type("S", (), {"ok": False, "method": method, "chain": None})())
    if not certifying:
        return _result(
            "h09:simulation_prereq", BLOCKED,
            f"no exact candidate-bound simulator configured "
            f"(ARBICORE_SIM_METHOD={method!r}); infra availability is NOT a "
            "PASS. Certifying methods: atomic_exact/atomic_state_override/"
            "fork_exact/exact_call.",
            {"sim_method": method, "certifying_method": False,
             "contract_demo_denied_reasons": demo["denied_reasons"]})
    return _result(
        "h09:simulation_prereq", UNKNOWN,
        "an exact candidate-bound simulator is configured; a real PASS still "
        "requires a COMPLETE candidate binding + ok + chain match on the VPS",
        {"sim_method": method, "certifying_method": True})


__all__ = [
    "SIX_CHAINS", "PASS", "FAIL", "BLOCKED", "UNKNOWN", "NOT_CONFIGURED",
    "check_rpc_and_chainid", "check_chain_scoped_isolation", "check_h05_sizer",
    "check_h07_composition", "check_h08_receiver",
    "check_receiver_bytecode_immutables", "check_h09_simulation_prereqs",
]
