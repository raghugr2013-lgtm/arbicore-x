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
    # Certification init: mirror the canonical ARBICORE_RPC_URL_<CHAIN> cert.env
    # inputs into the provider-registry keys ONCE (idempotent, secret-safe,
    # per-chain, no Base leakage) so one operator endpoint per chain satisfies
    # BOTH the chain-scoped RPC seam AND the economic all-in-cost gate.
    from ..config.persistent import sync_provider_registry_rpc_from_env
    sync_provider_registry_rpc_from_env()
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

def _h05_fact_is_exact(fact: Optional[Dict[str, Any]]) -> bool:
    """True ONLY for a REAL exact-size quote fact produced by the live provider:
    size_basis=='exact', exact_size True, a positive bound quote_notional_usd,
    a positive quoted_amount_in_wei, and a named borrow token. Anything else
    (probe, missing, malformed) is NOT exact."""
    if not isinstance(fact, dict):
        return False
    try:
        return (
            str(fact.get("size_basis") or "").lower() == "exact"
            and bool(fact.get("exact_size"))
            and float(fact.get("quote_notional_usd") or 0.0) > 0.0
            and int(fact.get("quoted_amount_in_wei") or 0) > 0
            and bool(str(fact.get("borrow_token") or "").strip())
        )
    except (TypeError, ValueError):
        return False


def classify_h05(exact_quote_fact: Optional[Dict[str, Any]], *,
                 price_feed_enabled: bool,
                 borrow_sizer_enabled: bool) -> str:
    """Pure H05 certification decision. Environment flags can NEVER produce PASS.

    PASS requires a genuine exact-size quote FACT (see ``_h05_fact_is_exact``).
    With the flags set but no exact fact captured ⇒ BLOCKED (configured, but no
    live exact-size evidence). Without the flags ⇒ NOT_CONFIGURED (the required
    fail-closed state: quotes stay PROBE-sized and economics deny)."""
    if _h05_fact_is_exact(exact_quote_fact):
        return PASS
    if price_feed_enabled and borrow_sizer_enabled:
        return BLOCKED
    return NOT_CONFIGURED


def check_h05_sizer(exact_quote_fact: Optional[Dict[str, Any]] = None
                    ) -> Dict[str, Any]:
    """H05 exact-size certification — EVIDENCE-based, never flag-based.

    ``exact_quote_fact`` is the facts dict from a REAL live exact-size quote
    (captured by the VPS runner via the wired ``borrow_sizer``). Environment
    flags may only gate whether the runner ATTEMPTS the live quote — they can
    never by themselves certify H05."""
    enabled = os.environ.get("ARBICORE_PRICE_FEED_ENABLED", "").lower() == "true"
    sizer = os.environ.get("ARBICORE_BORROW_SIZER_ENABLED", "").lower() == "true"
    status = classify_h05(exact_quote_fact,
                          price_feed_enabled=enabled,
                          borrow_sizer_enabled=sizer)
    ev: Dict[str, Any] = {"price_feed_enabled": enabled,
                          "borrow_sizer_enabled": sizer,
                          "exact_quote_captured": _h05_fact_is_exact(exact_quote_fact)}
    if isinstance(exact_quote_fact, dict):
        ev["fact"] = {k: exact_quote_fact.get(k) for k in
                      ("size_basis", "exact_size", "quote_notional_usd",
                       "quoted_amount_in_wei", "borrow_token", "chain",
                       "quote_block")}
    if status == PASS:
        detail = ("exact-size quote CERTIFIED: a live quote bound "
                  "quote_notional_usd to an exact quoted_amount_in_wei "
                  "(real price + verified decimals) — not extrapolated")
    elif status == BLOCKED:
        detail = ("price feed + borrow_sizer enabled but NO live exact-size "
                  "quote evidence was captured — flags alone are NOT a PASS "
                  "(fail-closed). Provide a real exact-size quote fact.")
    else:
        detail = ("operator price feed / borrow_sizer not enabled ⇒ quotes "
                  "remain PROBE-sized and economics fail closed "
                  "(DENIED_SIZE_NOT_QUOTED). This is the required fail-closed "
                  "state without a sizer.")
    return _result("h05:exact_size_sizer", status, detail, ev)


def extract_exact_quote_fact(obj: Any, _depth: int = 0
                             ) -> Optional[Dict[str, Any]]:
    """Recursively find an EXACT-size quote fact inside a persisted evidence
    bundle (from ``db.evidence_bundles``). Returns the first dict satisfying
    ``_h05_fact_is_exact`` (real scanner output — never fabricated), else None.
    Bounded depth; pure/side-effect free (unit-testable without Mongo)."""
    if _depth > 8 or obj is None:
        return None
    if isinstance(obj, dict):
        if _h05_fact_is_exact(obj):
            return obj
        for v in obj.values():
            found = extract_exact_quote_fact(v, _depth + 1)
            if found is not None:
                return found
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found = extract_exact_quote_fact(v, _depth + 1)
            if found is not None:
                return found
    return None


async def latest_exact_quote_fact(repo: Any = None,
                                  limit: int = 50) -> Optional[Dict[str, Any]]:
    """Read the most recent REAL exact-size quote fact from the scanner's
    persisted evidence bundles (Mongo). Fail-closed: returns None on any error,
    no Mongo, or when no exact-size candidate has been recorded — so H05 can
    never PASS without genuine live exact-size evidence."""
    try:
        if repo is None:
            from ..runtime.composition import get_evidence_bundles_repo
            repo = get_evidence_bundles_repo()
        bundles = await repo.list_recent(None, limit)
        for bundle in bundles or []:
            fact = extract_exact_quote_fact(bundle)
            if fact is not None:
                return fact
    except Exception:  # noqa: BLE001 — evidence read never fabricates/raises
        return None
    return None


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
    "classify_h05", "extract_exact_quote_fact", "latest_exact_quote_fact",
    "check_h07_composition", "check_h08_receiver",
    "check_receiver_bytecode_immutables", "check_h09_simulation_prereqs",
]
