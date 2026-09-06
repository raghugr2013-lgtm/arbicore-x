"""Base canonical M3 integration into the Six-Chain Opportunity Race.

Proves the DEFAULT base evaluator composes the EXISTING canonical Base M3
read-only path (build_controlled_live_safety + _probe_fresh_stages +
validate_candidate over CANDIDATES) without modifying that engine, that Base
participates in the common RaceResult, stays isolated on failure/timeout, can
become the deterministic best_candidate, and remains fail-closed on
negative/stale/missing economics.
"""
from __future__ import annotations

import asyncio

import arbicore.runtime.opportunity_race as race_mod
from arbicore.runtime.opportunity_race import (
    SixChainOpportunityRace, _default_base_evaluator,
    STATUS_EVALUATED, STATUS_ERROR, STATUS_TIMEOUT, STATUS_SKIPPED,
)

SIX_CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]


# ── The race wires the canonical M3 evaluator as the DEFAULT base path ───────
def test_default_base_evaluator_is_wired():
    race = SixChainOpportunityRace()
    assert race._base_eval is _default_base_evaluator


def test_base_routes_to_base_evaluator_not_generic():
    calls = {"base": 0, "generic": 0}

    async def _base_ev(chain, cap):
        calls["base"] += 1
        return {"skipped": None, "head": {"block": 5, "error": None},
                "rows": [], "candidates": []}

    async def _gen_ev(chain, cap):
        calls["generic"] += 1
        return {"skipped": None, "head": {"block": 5, "error": None},
                "rows": [], "candidates": []}

    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_gen_ev, base_evaluator=_base_ev)
    asyncio.run(race.scan_once())
    assert calls["base"] == 1           # base handled by base evaluator only
    assert calls["generic"] == 5        # the other five chains


# ── The DEFAULT base evaluator actually invokes the canonical M3 functions ───
def _install_canonical_spies(monkeypatch, *, gates_ok, net, quote_ok=True, tvl=1000.0):
    """Patch the canonical read-only building blocks with spies (no RPC)."""
    seen = {"probe": 0, "validate": 0, "safety": 0, "candidates": 0}

    monkeypatch.setattr(
        "arbicore.config.persistent.resolve_rpc_url_from_env",
        lambda chain: "https://base.example/rpc")

    class _FakeProvider:
        def __init__(self, *a, **k):
            pass

        async def eth_get_block_number(self):
            return 1000

    monkeypatch.setattr("arbicore.providers.rpc.EthJsonRpcProvider", _FakeProvider)

    class _FakeQuoter:
        pass

    monkeypatch.setattr("arbicore.execution.quoter.QuoterRegistry", _FakeQuoter)

    def _fake_safety(quoter):
        seen["safety"] += 1
        return ("VALIDATOR_SENTINEL", "BREAKER_SENTINEL")

    monkeypatch.setattr("arbicore.runtime.composition.build_controlled_live_safety",
                        _fake_safety)

    async def _fake_probe(plan, quoter):
        seen["probe"] += 1
        return {
            "stage_6_facts": {"route_quote_status": "ok" if quote_ok else "break_even",
                              "gross_profit_pct": 0.2,
                              "min_pool_tvl_usd_in_route": tvl},
            "stage_10_all_in_cost": {"available": True, "net_profit_all_in_usd": net},
        }

    async def _fake_validate(validator, plan, unavailable):
        seen["validate"] += 1
        return {"ok": gates_ok, "gates": {"net_economics": gates_ok},
                "reasons": [] if gates_ok else ["true_net_not_positive"]}

    monkeypatch.setattr("scripts.m3_0_vps_validate._probe_fresh_stages", _fake_probe)
    monkeypatch.setattr("scripts.m3_0_real_candidate_scan.validate_candidate",
                        _fake_validate)

    import scripts.m3_0_real_candidate_scan as m3
    seen["candidates"] = len(m3.CANDIDATES)
    return seen


def test_default_base_evaluator_invokes_canonical_m3(monkeypatch):
    seen = _install_canonical_spies(monkeypatch, gates_ok=True, net=42.0)
    res = asyncio.run(_default_base_evaluator("base", 10))
    n = seen["candidates"]
    assert seen["safety"] == 1
    assert seen["probe"] == n and seen["validate"] == n and n >= 1
    assert res["skipped"] is None
    assert res["head"]["block"] == 1000
    assert len(res["candidates"]) == n
    c0 = res["candidates"][0]
    assert c0["chain"] == "base"
    assert c0["stages"]["ECONOMICALLY_VALID"] is True
    assert c0["all_in_net_usd"] == 42.0
    assert c0["evidence_id"].startswith("cand:base:m3:")


def test_default_base_evaluator_skips_without_rpc(monkeypatch):
    monkeypatch.setattr(
        "arbicore.config.persistent.resolve_rpc_url_from_env", lambda chain: None)
    res = asyncio.run(_default_base_evaluator("base", 10))
    assert res["skipped"] == "no_operator_configured_rpc"
    assert res["candidates"] == []


# ── Base participates in the common RaceResult ───────────────────────────────
def test_base_enters_common_race_result(monkeypatch):
    _install_canonical_spies(monkeypatch, gates_ok=True, net=7.5)

    async def _gen_ev(chain, cap):
        return {"skipped": None, "head": {"block": 1, "error": None},
                "rows": [{"quotable": True, "liquidity_verified": True}],
                "candidates": []}

    race = SixChainOpportunityRace(networks=SIX_CHAINS, chain_evaluator=_gen_ev)
    result = asyncio.run(race.scan_once())
    assert set(result.per_chain.keys()) == set(SIX_CHAINS)
    assert result.per_chain["base"].status == STATUS_EVALUATED
    assert result.per_chain["base"].positive_net_count >= 1
    assert result.positive_net_count >= 1


# ── Positive Base NET becomes the deterministic best_candidate ───────────────
def test_positive_base_net_becomes_best_candidate(monkeypatch):
    _install_canonical_spies(monkeypatch, gates_ok=True, net=999.0)

    async def _gen_ev(chain, cap):
        # other chains: one small positive so Base must WIN on magnitude
        return {"skipped": None, "head": {"block": 1, "error": None}, "rows": [],
                "candidates": [{"chain": chain, "block": 1,
                                "stages": {"ECONOMICALLY_VALID": True},
                                "all_in_net_usd": 1.0,
                                "evidence_id": f"cand:{chain}:x"}]}

    race = SixChainOpportunityRace(networks=SIX_CHAINS, chain_evaluator=_gen_ev)
    result = asyncio.run(race.scan_once())
    assert result.best_candidate["chain"] == "base"
    assert result.best_candidate["all_in_net_usd"] == 999.0
    assert result.best_candidate["operator_action_required"] is True
    assert result.operator_action_required is True


# ── Negative / missing Base economics stay fail-closed ───────────────────────
def test_negative_base_gates_not_positive(monkeypatch):
    _install_canonical_spies(monkeypatch, gates_ok=False, net=-3.0)
    res = asyncio.run(_default_base_evaluator("base", 10))
    assert all(c["stages"]["ECONOMICALLY_VALID"] is False for c in res["candidates"])

    race = SixChainOpportunityRace(networks=SIX_CHAINS)
    # route base through the default (patched) evaluator; other chains skip.
    result = asyncio.run(race.scan_once())
    assert result.per_chain["base"].positive_net_count == 0
    assert result.positive_net_count == 0


def test_base_gates_ok_but_missing_net_fail_closed(monkeypatch):
    # M3 gate ok=True but the all-in net is not extractable → not surfaced.
    seen = _install_canonical_spies(monkeypatch, gates_ok=True, net=None)

    async def _probe_no_net(plan, quoter):
        return {"stage_6_facts": {"route_quote_status": "ok",
                                  "gross_profit_pct": 0.2,
                                  "min_pool_tvl_usd_in_route": 1000.0},
                "stage_10_all_in_cost": {"available": False}}

    monkeypatch.setattr("scripts.m3_0_vps_validate._probe_fresh_stages", _probe_no_net)
    res = asyncio.run(_default_base_evaluator("base", 10))
    race = SixChainOpportunityRace(networks=SIX_CHAINS)
    result = asyncio.run(race.scan_once())
    # ECONOMICALLY_VALID may be True (gate ok) but net None ⇒ never positive.
    assert result.per_chain["base"].positive_net_count == 0


def test_stale_base_quote_rejected(monkeypatch):
    _install_canonical_spies(monkeypatch, gates_ok=True, net=50.0)
    # head_block returned by fake provider is 1000; candidate block is 1000 too,
    # so make max_block_lag negative-impossible by patching provider head high.

    class _FarProvider:
        def __init__(self, *a, **k):
            pass

        async def eth_get_block_number(self):
            return 100000  # head far ahead of the candidate quote block

    # candidates carry block=head_block (100000) in the evaluator, so to force a
    # stale case we instead lower the head used for candidates via the probe's
    # own block. Simpler: assert freshness path by using the orchestrator lag on
    # an injected base candidate with an old block.
    async def _old_base(chain, cap):
        return {"skipped": None, "head": {"block": 100000, "error": None}, "rows": [],
                "candidates": [{"chain": "base", "block": 5,
                                "stages": {"ECONOMICALLY_VALID": True},
                                "all_in_net_usd": 50.0,
                                "evidence_id": "cand:base:m3:old"}]}

    race = SixChainOpportunityRace(networks=SIX_CHAINS, max_block_lag=10,
                                   base_evaluator=_old_base)
    result = asyncio.run(race.scan_once())
    assert result.per_chain["base"].positive_net_count == 0
    assert result.best_candidate is None


# ── Base failure / timeout isolated from the other five ──────────────────────
def test_base_exception_isolated(monkeypatch):
    async def _boom(chain, cap):
        raise RuntimeError("base rpc down")

    async def _gen_ev(chain, cap):
        return {"skipped": None, "head": {"block": 1, "error": None},
                "rows": [{"quotable": True, "liquidity_verified": True}],
                "candidates": []}

    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_gen_ev, base_evaluator=_boom)
    result = asyncio.run(race.scan_once())
    assert result.per_chain["base"].status == STATUS_ERROR
    for c in SIX_CHAINS:
        if c != "base":
            assert result.per_chain[c].status == STATUS_EVALUATED


def test_base_timeout_isolated():
    async def _hang(chain, cap):
        await asyncio.sleep(5)
        return {"skipped": None, "head": {}, "rows": [], "candidates": []}

    async def _gen_ev(chain, cap):
        return {"skipped": None, "head": {"block": 1, "error": None},
                "rows": [{"quotable": True, "liquidity_verified": True}],
                "candidates": []}

    race = SixChainOpportunityRace(networks=SIX_CHAINS, per_chain_timeout_s=0.2,
                                   chain_evaluator=_gen_ev, base_evaluator=_hang)
    result = asyncio.run(race.scan_once())
    assert result.per_chain["base"].status == STATUS_TIMEOUT
    for c in SIX_CHAINS:
        if c != "base":
            assert result.per_chain[c].status == STATUS_EVALUATED


# ── Canonical M3 engine untouched (safety invariants preserved) ──────────────
def test_safety_invariants_preserved():
    from arbicore.runtime.opportunity_race import SAFETY_POSTURE
    for k in ("signing", "broadcast", "auto_execution", "full_live", "withdrawals"):
        assert SAFETY_POSTURE[k] is False


def test_no_execution_symbols_in_race_module():
    for banned in ("LiveSigner", "AutoExecutor", "LimitedLiveBroadcaster"):
        assert not hasattr(race_mod, banned)
