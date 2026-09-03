"""Phase-3E — size-optimizer sweep across the exact requested notionals.

Proves the optimizer evaluates economics at every size (not probe extrapolation),
that impact/slippage scale with notional, net is recomputed per size, infeasible
sizes never win, and a null optimum always carries an evidence-backed reason.
Pure/deterministic — no RPC.
"""
from arbicore.economics.size_optimizer import optimize_size

SIZES = [100, 500, 1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000]


def _run(liq, spread=150, gas=3.0, flash_bps=9, **kw):
    return optimize_size(gross_spread_bps=spread, pool_liquidity_usd=liq,
                         gas_cost_usd=gas, flash_loan_fee_bps=flash_bps,
                         size_grid_usd=SIZES, refine=False,
                         prob_kwargs=dict(simulation_passed=True, quote_age_sec=1,
                                          gas_certainty=1.0, mev_risk=0.0,
                                          historical_success_rate=0.9), **kw)


def test_every_size_scored_with_recomputed_economics():
    r = _run(2_000_000)
    cands = {c["notional_usd"]: c for c in r["candidates"]}
    for s in SIZES:
        assert s in cands, f"size {s} not scored"
    # net profit is recomputed per size (distinct values, not a probe extrapolation)
    nets = [cands[s]["net_profit_usd"] for s in SIZES]
    assert len(set(nets)) > 1


def test_slippage_and_impact_increase_with_notional():
    r = _run(2_000_000)
    cands = {c["notional_usd"]: c for c in r["candidates"]}
    slips = [cands[s]["slippage_bps"] for s in SIZES]
    assert slips == sorted(slips)                 # monotonic non-decreasing
    assert cands[500_000]["slippage_bps"] > cands[100]["slippage_bps"]


def test_same_notional_different_liquidity_changes_impact():
    """Optimizer uses live liquidity, not a fixed probe: same size, deeper pool
    => strictly lower slippage."""
    shallow = {c["notional_usd"]: c for c in _run(500_000)["candidates"]}
    deep = {c["notional_usd"]: c for c in _run(50_000_000)["candidates"]}
    assert deep[50_000]["slippage_bps"] < shallow[50_000]["slippage_bps"]


def test_infeasible_sizes_never_chosen():
    r = _run(2_000_000)
    chosen = r["chosen"]
    if chosen is not None:
        assert chosen["feasible"] is True
    for c in r["candidates"]:
        if not c["feasible"]:
            assert c is not chosen


def test_flash_fee_scales_with_notional():
    r = _run(2_000_000, flash_bps=9)
    cands = {c["notional_usd"]: c for c in r["candidates"]}
    # 9 bps on notional: 100 -> 0.09 ; 100k -> 90
    assert round(cands[100]["flash_fee_usd"], 4) == 0.09
    assert round(cands[100_000]["flash_fee_usd"], 4) == 90.0


def test_null_optimum_has_evidence_backed_reason():
    r = _run(2_000_000, spread=-10)     # negative spread → nothing feasible
    assert r["chosen"] is None
    assert all(c["reject_reason"] for c in r["candidates"])


def test_missing_liquidity_is_fail_closed_across_all_sizes():
    r = _run(None)
    assert r["chosen"] is None
    assert all(c["slippage_bps"] == 10_000.0 for c in r["candidates"])


def test_optimizer_respects_capital_cap_across_sweep():
    r = optimize_size(gross_spread_bps=400, pool_liquidity_usd=1e12,
                      gas_cost_usd=1, flash_loan_fee_bps=1, size_grid_usd=SIZES,
                      max_notional_usd=25_000, refine=False,
                      prob_kwargs=dict(simulation_passed=True, quote_age_sec=1,
                                       gas_certainty=1.0, mev_risk=0.0,
                                       historical_success_rate=0.9))
    for c in r["candidates"]:
        assert c["notional_usd"] <= 25_000
