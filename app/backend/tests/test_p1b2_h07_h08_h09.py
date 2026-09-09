"""P1 Batch 2 regression — H07 six-chain isolation matrix, H08 receiver
capability (fail-closed + versioned), H09 candidate-bound simulation contract.
Offline / deterministic.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import pytest

from arbicore.execution import quoter as q
from arbicore.execution.receiver_capability import (
    receiver_capability, receiver_supports,
)
from arbicore.certification.candidate_simulation import (
    CandidateSimulationBinding, evaluate_candidate_simulation,
    REQUIRED_BINDING_FIELDS,
)
from arbicore.certification.evidence_tiers import EvidenceTier

SIX_CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]
CHAIN_IDS = {"base": 8453, "ethereum": 1, "arbitrum": 42161,
             "optimism": 10, "polygon": 137, "bnb": 56}


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ------------------------- H07 six-chain RPC/chain-id isolation -------------

def test_expected_chain_ids_for_all_six():
    for c in SIX_CHAINS:
        assert q._expected_chain_id(c) == CHAIN_IDS[c]


def test_no_chain_accepts_another_chains_endpoint():
    # A node reporting chain X must be rejected for every OTHER chain Y.
    reader_map = {f"https://node-{c}": CHAIN_IDS[c] for c in SIX_CHAINS}
    q._read_chain_id = lambda url, timeout=8.0: _async(reader_map.get(url))
    for served in SIX_CHAINS:
        for requested in SIX_CHAINS:
            q._HOST_CHAIN_ID.clear()
            ok = _run(q._endpoint_serves_chain(f"https://node-{served}", requested))
            assert ok is (served == requested), (
                f"endpoint serving {served} wrongly accepted for {requested}")


async def _async(v):
    return v


def test_global_base_alias_never_leaks_to_other_chains():
    import os
    os.environ["ARBICORE_RPC_URL"] = "https://GLOBAL-BASE"
    try:
        reg = q.QuoterRegistry()
        assert "https://GLOBAL-BASE" in reg._rpc_url_candidates("base")
        for c in ("ethereum", "arbitrum", "optimism", "polygon", "bnb"):
            cands = reg._rpc_url_candidates(c)
            assert all("GLOBAL-BASE" not in u for u in cands), \
                f"global Base RPC leaked into {c}"
    finally:
        os.environ.pop("ARBICORE_RPC_URL", None)


# ------------------------- H08 receiver capability --------------------------

def test_undeployed_chains_are_execution_incapable():
    # only base_sepolia (84532) is deployed in the committed registry; the six
    # production chains have no successful deployment → all fail closed.
    for c in SIX_CHAINS:
        cap = receiver_capability(c)
        assert cap.deployed is False
        assert cap.supported_providers == []
        for prov in ("balancer_v2", "aave_v3", "uniswap_v3", "aerodrome"):
            assert receiver_supports(c, prov) is False


def test_deployed_receiver_without_declared_providers_rejects_all_venues():
    cap = receiver_capability(84532)          # base_sepolia, deploy success
    assert cap.deployed is True
    # no supported_providers declared → every venue rejected (no inference)
    assert cap.supported_providers == []
    assert receiver_supports(84532, "balancer_v2") is False
    # version missing in record → reported unversioned/unverified
    assert cap.version_verified is False
    assert cap.receiver_version == "unversioned"


def test_unknown_chain_is_incapable():
    cap = receiver_capability("dogechain")
    assert cap.deployed is False
    assert receiver_supports("dogechain", "uniswap_v3") is False


# ------------------------- H09 candidate-bound simulation -------------------

@dataclass
class _Sim:
    ok: bool
    method: str
    chain: Optional[str] = "base"


def _complete_binding(**over):
    base = dict(chain="base", block_number=123, token="WETH", token_decimals=18,
                exact_input_wei=10 ** 18, route=["p1", "p2"], calldata="0xabcd",
                liquidity_state={"p1": 500_000.0}, economics={"net_usd": 1.2},
                executor_address="0x" + "11" * 20, receiver_version="v1.2.0")
    base.update(over)
    return CandidateSimulationBinding(**base)


def test_required_fields_enumerated():
    assert set(REQUIRED_BINDING_FIELDS) == {
        "chain", "block_number", "token", "token_decimals", "exact_input_wei",
        "route", "calldata", "liquidity_state", "economics",
        "executor_address", "receiver_version"}


def test_incomplete_binding_never_certifies():
    b = _complete_binding(calldata=None, economics={})
    r = evaluate_candidate_simulation(b, _Sim(ok=True, method="atomic_exact"))
    assert r["certified"] is False
    assert any("incomplete_binding" in x for x in r["denied_reasons"])
    assert "calldata" in r["denied_reasons"][0]
    assert "economics" in r["denied_reasons"][0]


def test_unversioned_receiver_is_incomplete():
    b = _complete_binding(receiver_version="unversioned")
    r = evaluate_candidate_simulation(b, _Sim(ok=True, method="atomic_exact"))
    assert r["certified"] is False


def test_heuristic_method_never_certifies_even_with_complete_binding():
    for m in ("noop", "symbolic", "estimate_symbolic", "paper", "heuristic"):
        r = evaluate_candidate_simulation(_complete_binding(), _Sim(ok=True, method=m))
        assert r["certified"] is False
        assert r["tier"] == EvidenceTier.EXECUTION_CAPABLE.name
        assert any("non_certifying_sim_method" in x for x in r["denied_reasons"])


def test_chain_mismatch_fails_closed():
    r = evaluate_candidate_simulation(
        _complete_binding(chain="base"),
        _Sim(ok=True, method="atomic_exact", chain="ethereum"))
    assert r["certified"] is False
    assert any("chain_mismatch" in x for x in r["denied_reasons"])


def test_exact_bound_ok_certifies():
    r = evaluate_candidate_simulation(
        _complete_binding(), _Sim(ok=True, method="atomic_exact", chain="base"))
    assert r["certified"] is True
    assert r["tier"] == EvidenceTier.SIMULATION_CERTIFIED.name
    assert r["denied_reasons"] == []


def test_failed_exact_sim_not_certified():
    r = evaluate_candidate_simulation(
        _complete_binding(), _Sim(ok=False, method="atomic_exact"))
    assert r["certified"] is False
    assert "simulation_not_ok" in r["denied_reasons"]
    assert r["tier"] == EvidenceTier.UNKNOWN.name
