"""Frozen certification policy: gates, requirements, economic envelope.

Everything here is DATA + PURE PREDICATES. No I/O, no mutation, no AI. The frozen
``ECONOMIC_POLICY`` mirrors the mandated thresholds and is used only to DETECT
drift — the orchestrator never writes these values back into the trading config.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Callable, List

ORCHESTRATOR_VERSION = "gate-orchestrator/1.0.0"


class Verdict(str, enum.Enum):
    GREEN = "GREEN"
    RED = "RED"
    BLOCKED = "BLOCKED"      # critical/circuit-breaker or corrupted evidence
    UNKNOWN = "UNKNOWN"      # evidence absent -> fail-closed (treated as not-passing)


class GateId(str, enum.Enum):
    G0_PREFLIGHT = "G0_PREFLIGHT"
    G1_CONFIG_INTEGRITY = "G1_CONFIG_INTEGRITY"
    G2_RUNTIME_LIQUIDITY = "G2_RUNTIME_LIQUIDITY"
    G3_EXECUTION_CAPABILITY = "G3_EXECUTION_CAPABILITY"
    G4_SIMULATION = "G4_SIMULATION"
    G5_PAPER_SHADOW = "G5_PAPER_SHADOW"


class LiveState(str, enum.Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    LIVE_ELIGIBILITY = "LIVE_ELIGIBILITY"
    LIMITED_LIVE_ELIGIBLE = "LIMITED_LIVE_ELIGIBLE"
    LIMITED_LIVE_AUTHORIZED = "LIMITED_LIVE_AUTHORIZED"
    FULL_LIVE_ELIGIBLE = "FULL_LIVE_ELIGIBLE"
    FULL_LIVE_AUTHORIZED = "FULL_LIVE_AUTHORIZED"
    PAUSED = "PAUSED"        # circuit-breaker safe state


# Mandated economic envelope — DRIFT DETECTION ONLY (never rewritten anywhere).
ECONOMIC_POLICY = {
    "min_atomic_profit_usd": 25,
    "conservative_cert_threshold_usd": 35,
    "min_tvl_usd": 100_000,
    "min_confidence": 60,
    "max_mev": "MEDIUM",
    "max_route_hops": 4,
    "max_wall_time_s": 5,
    "candidate_cap": 64,
}

# Minimum objective evidence so a single green test can NEVER qualify live.
# Observation windows are reliability OBSERVATION, not elapsed-time hard gates.
MIN_EVIDENCE = {
    "limited_live": {
        "min_qualifying_observations": 20,
        "min_successful_simulations": 20,
        "max_economic_violations": 0,
        "max_security_violations": 0,
        "max_repayment_anomalies": 0,
        "recommended_observation_window_h": 24,   # observed, not required-to-elapse
    },
    "full_live": {
        "min_qualifying_observations": 100,
        "min_successful_simulations": 100,
        "min_limited_live_executions": 10,
        "max_economic_violations": 0,
        "max_security_violations": 0,
        "max_repayment_anomalies": 0,
        "recommended_observation_window_h": 72,   # observed, not required-to-elapse
    },
}


@dataclass(frozen=True)
class Requirement:
    """A single mandatory (or advisory) condition, evaluated by a PURE predicate.

    ``evaluator`` maps an EvidenceContext -> (Verdict, reason:str). It must be
    deterministic and side-effect free.
    """
    id: str
    description: str
    evaluator: Callable
    mandatory: bool = True
    critical: bool = False   # a RED here trips a circuit breaker -> PAUSED


@dataclass(frozen=True)
class GateSpec:
    id: GateId
    title: str
    requirements: List[Requirement] = field(default_factory=list)
    auto_advance: bool = True   # technical/sim gates auto-advance when all GREEN


# --- Deterministic requirement predicates ---------------------------------- #
# Each takes ``ev`` (EvidenceContext). Kept tiny + explicit; fail-closed default.

def _req_toolchain(ev):
    ok = bool(ev.get("toolchain", {}).get("forge_available"))
    return (Verdict.GREEN, "forge toolchain available") if ok else \
        (Verdict.RED, "forge toolchain not available")

def _req_repo_clean_branch(ev):
    b = ev.get("git", {}).get("branch")
    if b:
        return (Verdict.GREEN, f"on branch {b}")
    return (Verdict.UNKNOWN, "git branch unknown")

def _req_economic_no_drift(ev):
    live = ev.get("economic_policy") or {}
    if not live:
        return (Verdict.UNKNOWN, "economic policy snapshot absent")
    drift = {k: (ECONOMIC_POLICY[k], live.get(k)) for k in ECONOMIC_POLICY
             if live.get(k) != ECONOMIC_POLICY[k]}
    if drift:
        return (Verdict.RED, f"economic policy drift detected: {drift}")
    return (Verdict.GREEN, "economic policy matches frozen envelope")

def _req_v1_source_unchanged(ev):
    return (Verdict.GREEN, "V1 bytecode-affecting source unchanged") \
        if ev.get("integrity", {}).get("v1_source_unchanged") \
        else (Verdict.RED, "V1 source integrity not confirmed")

def _req_security_no_violations(ev):
    n = ev.get("security", {}).get("violations")
    if n is None:
        return (Verdict.UNKNOWN, "security findings not evaluated")
    return (Verdict.GREEN, "no security invariant violations") if n == 0 \
        else (Verdict.RED, f"{n} security invariant violation(s)")

def _req_unit_tests_pass(ev):
    t = ev.get("tests", {})
    genuine_failures = t.get("genuine_failures")
    passed = t.get("passed")
    if genuine_failures is None or passed is None:
        return (Verdict.UNKNOWN, "test results not supplied")
    if genuine_failures > 0:
        return (Verdict.RED, f"{genuine_failures} genuine test failure(s)")
    return (Verdict.GREEN, f"{passed} tests passed, 0 genuine failures")

def _req_runtime_liquidity(ev):
    r = ev.get("runtime", {})
    if r.get("probe_available") is not True:
        return (Verdict.UNKNOWN, "runtime liquidity probe unavailable (no operator RPC) — fail-closed")
    return (Verdict.GREEN, "runtime liquidity probe healthy") if r.get("healthy") \
        else (Verdict.RED, "runtime liquidity probe reported unhealthy/insufficient")

def _req_executor_deployed_verified(ev):
    c = ev.get("execution_capability", {})
    if not c.get("receiver_deployed"):
        return (Verdict.RED, "no verified deployed receiver for target scope")
    if c.get("bytecode_verified") is not True:
        return (Verdict.RED, "deployed bytecode not verified")
    return (Verdict.GREEN, f"receiver {c.get('receiver_version')} deployed + bytecode verified")

def _req_capability_bound(ev):
    c = ev.get("execution_capability", {})
    if c.get("route_executable") is True:
        return (Verdict.GREEN, "route/calldata bound to deployed receiver capability")
    if c.get("route_executable") is None:
        return (Verdict.UNKNOWN, "capability binding not evaluated — fail-closed")
    return (Verdict.RED, f"route not executable: {c.get('reason')}")

def _req_ethcall_sim(ev):
    s = ev.get("simulation", {})
    if s.get("eth_call_available") is not True:
        return (Verdict.UNKNOWN, "eth_call simulation unavailable (no operator RPC) — fail-closed")
    return (Verdict.GREEN, "eth_call simulation succeeds") if s.get("eth_call_ok") \
        else (Verdict.RED, "eth_call simulation failed")

def _req_fork_sim(ev):
    s = ev.get("simulation", {})
    if s.get("fork_available") is not True:
        return (Verdict.UNKNOWN, "fork simulation unavailable (no operator RPC) — fail-closed")
    return (Verdict.GREEN, "fork simulation succeeds") if s.get("fork_ok") \
        else (Verdict.RED, "fork simulation failed")

def _req_failure_isolation(ev):
    s = ev.get("simulation", {})
    if s.get("failure_isolation_proven") is True:
        return (Verdict.GREEN, "unsupported-venue / revert isolation proven")
    return (Verdict.UNKNOWN, "failure isolation not proven — fail-closed")

def _req_paper_exec(ev):
    p = ev.get("paper", {})
    obs = p.get("qualifying_observations")
    if obs is None:
        return (Verdict.UNKNOWN, "no paper/shadow observations — fail-closed")
    need = MIN_EVIDENCE["limited_live"]["min_successful_simulations"]
    if p.get("economic_violations", 0) > 0 or p.get("security_violations", 0) > 0:
        return (Verdict.RED, "paper phase recorded economic/security violation(s)")
    if p.get("successful_simulations", 0) < need:
        return (Verdict.RED, f"insufficient paper evidence: {p.get('successful_simulations',0)}/{need}")
    return (Verdict.GREEN, f"paper evidence sufficient ({p.get('successful_simulations')} ok)")

def _req_evidence_complete(ev):
    e = ev.get("evidence_ledger", {})
    if e.get("complete") is True and e.get("corrupted") is False:
        return (Verdict.GREEN, "evidence ledger complete + intact")
    if e.get("corrupted") is True:
        return (Verdict.BLOCKED, "evidence ledger corrupted — circuit breaker")
    return (Verdict.UNKNOWN, "evidence ledger incomplete — fail-closed")


GATES: List[GateSpec] = [
    GateSpec(GateId.G0_PREFLIGHT, "Preflight", [
        Requirement("toolchain_available", "Build/test toolchain present", _req_toolchain),
        Requirement("repo_branch_known", "Repository on a known branch", _req_repo_clean_branch, mandatory=False),
    ]),
    GateSpec(GateId.G1_CONFIG_INTEGRITY, "Configuration Integrity", [
        Requirement("economic_no_drift", "Economic envelope unchanged", _req_economic_no_drift, critical=True),
        Requirement("v1_source_unchanged", "V1 source integrity", _req_v1_source_unchanged, critical=True),
        Requirement("unit_tests_pass", "Unit/security tests pass (no genuine failures)", _req_unit_tests_pass),
        Requirement("security_no_violations", "No security invariant violations", _req_security_no_violations, critical=True),
    ]),
    GateSpec(GateId.G2_RUNTIME_LIQUIDITY, "Runtime / Liquidity", [
        Requirement("runtime_liquidity", "Runtime liquidity probe healthy", _req_runtime_liquidity),
    ]),
    GateSpec(GateId.G3_EXECUTION_CAPABILITY, "Execution Capability", [
        Requirement("executor_deployed_verified", "Receiver deployed + bytecode verified", _req_executor_deployed_verified),
        Requirement("capability_bound", "Route bound to deployed capability", _req_capability_bound, critical=True),
    ]),
    GateSpec(GateId.G4_SIMULATION, "Simulation", [
        Requirement("eth_call_sim", "eth_call simulation succeeds", _req_ethcall_sim),
        Requirement("fork_sim", "Fork simulation succeeds", _req_fork_sim),
        Requirement("failure_isolation", "Failure/revert isolation proven", _req_failure_isolation),
    ]),
    GateSpec(GateId.G5_PAPER_SHADOW, "Paper / Shadow", [
        Requirement("paper_exec", "Paper/shadow evidence sufficient", _req_paper_exec),
        Requirement("evidence_complete", "Evidence ledger complete + intact", _req_evidence_complete),
    ]),
]


__all__ = [
    "ORCHESTRATOR_VERSION", "Verdict", "GateId", "LiveState",
    "ECONOMIC_POLICY", "MIN_EVIDENCE", "Requirement", "GateSpec", "GATES",
]
