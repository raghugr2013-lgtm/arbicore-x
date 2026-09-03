"""Phase-2B/2C — deterministic economics & size-optimizer proof.

Pins the exact behaviour the Phase-2 directive asked to prove and guards the
fail-closed invariants. Pure/deterministic — no RPC, no I/O. A route with
negative economics MUST stay negative; a route with missing evidence MUST stay
UNKNOWN/infeasible (never becomes profitable via a fallback).
"""
from arbicore.economics.net_profit import compute_net_profit
from arbicore.economics.size_optimizer import optimize_size, DEFAULT_SIZE_GRID_USD
from arbicore.economics.expected_value import (
    estimate_success_probability, compute_expected_value, evaluate_expected_value)
from arbicore.economics.opportunity_decision import (
    run_simulation_gate, decide_opportunity)


# ── net_profit ───────────────────────────────────────────────────────────
def test_gross_and_costs_are_linear_and_separable():
    r = compute_net_profit(gross_spread_bps=100, notional_usd=10_000,
                           buy_venue_fee_bps=5, sell_venue_fee_bps=5,
                           slippage_bps=10, liquidity_impact_bps=4,
                           flash_loan_notional_usd=10_000, flash_loan_fee_bps=9)
    assert r.gross_profit_usd == 100.0            # 100bps * 10k
    assert r.trading_fees_usd == 10.0             # 10bps * 10k (dex fees, ONCE)
    assert r.slippage_cost_usd == 10.0            # 10bps * 10k
    assert r.liquidity_impact_usd == 4.0          # separate line, not folded into slippage
    assert r.flash_loan_fee_usd == 9.0            # 9bps * 10k flash notional
    # total = 10 + 0 + 0(gas) + 10 + 9 + 4 = 33 ; net = 100 - 33 = 67
    assert r.total_cost_usd == 33.0
    assert r.net_profit_usd == 67.0
    assert r.is_profitable is True


def test_gas_is_zero_when_triple_absent_and_counted_once_when_present():
    no_gas = compute_net_profit(gross_spread_bps=50, notional_usd=10_000)
    assert no_gas.gas_cost_usd == 0.0
    # full triple: 30e9 wei/gas * 300000 gas / 1e18 * $1900 = 0.009*1900 = 17.1
    with_gas = compute_net_profit(gross_spread_bps=50, notional_usd=10_000,
                                  gas_native_wei=30_000_000_000,
                                  estimated_gas_units=300_000,
                                  native_price_usd=1900.0)
    assert round(with_gas.gas_cost_usd, 2) == 17.10
    # gas appears exactly once in total_cost
    assert round(with_gas.total_cost_usd, 2) == 17.10


def test_negative_spread_stays_negative():
    r = compute_net_profit(gross_spread_bps=-5, notional_usd=10_000)
    assert r.net_profit_usd < 0
    assert r.is_profitable is False


# ── size optimizer ───────────────────────────────────────────────────────
def test_negative_spread_gives_null_chosen_with_evidence():
    """optimal_notional_usd == null must mean 'no feasible size', WITH a reason
    on every rejected candidate (not an optimizer that was never invoked)."""
    r = optimize_size(gross_spread_bps=-5, pool_liquidity_usd=1_000_000,
                      gas_cost_usd=10, flash_loan_fee_bps=9)
    assert r["chosen"] is None
    assert len(r["candidates"]) >= len([n for n in DEFAULT_SIZE_GRID_USD])
    assert all(c["reject_reason"] for c in r["candidates"])
    assert all(c["feasible"] is False for c in r["candidates"])


def test_none_liquidity_fails_closed_not_crash():
    """REGRESSION: pool_liquidity_usd=None previously raised TypeError. Missing
    liquidity is UNKNOWN → fully impacted → infeasible, never a crash."""
    r = optimize_size(gross_spread_bps=200, pool_liquidity_usd=None,
                      gas_cost_usd=5, flash_loan_fee_bps=9)
    assert r["chosen"] is None
    assert all(c["slippage_bps"] == 10_000.0 for c in r["candidates"])


def test_zero_liquidity_is_fully_impacted():
    r = optimize_size(gross_spread_bps=200, pool_liquidity_usd=0,
                      gas_cost_usd=5, flash_loan_fee_bps=9)
    assert r["chosen"] is None
    assert r["candidates"][0]["slippage_bps"] == 10_000.0


def test_impact_layering_is_conservative_125pct():
    """slippage (full leg impact) + liquidity_impact (0.25x same impact) = 1.25x.
    Documented as an intentional CONSERVATIVE over-count (reduces net profit),
    never a profit inflator."""
    r = optimize_size(gross_spread_bps=300, pool_liquidity_usd=1_000_000,
                      gas_cost_usd=1, flash_loan_fee_bps=9,
                      size_grid_usd=[100_000], refine=False)
    c = r["candidates"][0]
    assert c["liquidity_impact_usd"] == round(c["slippage_usd"] * 0.25, 6)


def test_optimizer_evaluates_multiple_notionals_and_picks_max_ev():
    r = optimize_size(gross_spread_bps=120, pool_liquidity_usd=5_000_000,
                      gas_cost_usd=5, flash_loan_fee_bps=9,
                      prob_kwargs=dict(simulation_passed=True, quote_age_sec=1,
                                       gas_certainty=1.0, mev_risk=0.0,
                                       historical_success_rate=0.9))
    feasible = [c for c in r["candidates"] if c["feasible"]]
    assert len(r["candidates"]) >= 5            # a real grid, not a single probe
    if r["chosen"] is not None:
        best_ev = max(c["expected_value_usd"] for c in feasible)
        assert r["chosen"]["expected_value_usd"] == best_ev


def test_optimizer_never_exceeds_max_notional_cap():
    r = optimize_size(gross_spread_bps=500, pool_liquidity_usd=1e12,
                      gas_cost_usd=1, flash_loan_fee_bps=1,
                      max_notional_usd=50_000,
                      prob_kwargs=dict(simulation_passed=True, quote_age_sec=1,
                                       gas_certainty=1.0, mev_risk=0.0,
                                       historical_success_rate=0.9))
    for c in r["candidates"]:
        assert c["notional_usd"] <= 50_000
    if r["chosen"]:
        assert r["chosen"]["notional_usd"] <= 50_000


# ── expected value ───────────────────────────────────────────────────────
def test_absent_evidence_is_zero_confidence_not_neutral():
    est = estimate_success_probability()
    assert est["probability"] == 0.0            # NOT 0.5
    assert est["uncertainty_penalty"] == 1.0


def test_failed_simulation_caps_probability():
    est = estimate_success_probability(simulation_passed=False, quote_age_sec=1,
                                       liquidity_ratio=0.01, gas_certainty=1.0,
                                       mev_risk=0.0, historical_success_rate=1.0)
    assert est["probability"] <= 0.10


def test_ev_formula_is_p_net_minus_q_maxloss():
    ev = compute_expected_value(net_profit_usd=100.0, maximum_loss_usd=20.0,
                                success_probability=0.8)
    assert ev.expected_value_usd == round(0.8 * 100.0 - 0.2 * 20.0, 6)  # 76.0


# ── decision path / simulation gate ───────────────────────────────────────
def _ready_opp():
    return {
        "opportunity_id": "opp-ready",
        "quote_status": "REAL", "quote_age_sec": 1.0,
        "hops": [{"router": "0xrouter", "token_in": "0xa", "token_out": "0xb",
                  "amount_out_min_wei": 123}],
        "max_hops": 3, "flash_loan_provider": "aave_v3",
        "expected_slippage_bps": 20, "gas_cost_usd": 5.0, "repayment_ok": True,
        "calldata_hex": "0xdeadbeef", "gross_spread_bps": 120,
        "pool_liquidity_usd": 5_000_000, "flash_loan_fee_bps": 9,
        "gas_certainty": 1.0, "mev_risk": 0.0, "historical_success_rate": 0.9,
    }


def test_sim_gate_each_check_blocks():
    allow_r, allow_t = ["0xrouter"], ["0xa", "0xb"]
    base = _ready_opp()
    ok = run_simulation_gate(base, router_allowlist=allow_r, token_allowlist=allow_t)
    assert ok.passed is True
    # stale quote
    assert not run_simulation_gate({**base, "quote_status": "STALE"},
                                   router_allowlist=allow_r, token_allowlist=allow_t).passed
    # zero gas (unknown) → gas_ok false
    assert not run_simulation_gate({**base, "gas_cost_usd": 0},
                                   router_allowlist=allow_r, token_allowlist=allow_t).passed
    # unapproved router
    assert not run_simulation_gate(base, router_allowlist=["0xother"],
                                   token_allowlist=allow_t).passed
    # missing calldata
    o = {**base}; o.pop("calldata_hex")
    assert not run_simulation_gate(o, router_allowlist=allow_r, token_allowlist=allow_t).passed
    # repayment not modeled
    assert not run_simulation_gate({**base, "repayment_ok": False},
                                   router_allowlist=allow_r, token_allowlist=allow_t).passed


def test_decision_distinct_reasons_and_shadow_advisory():
    allow_r, allow_t = ["0xrouter"], ["0xa", "0xb"]
    # ready → executable (SHADOW advisory), optimal size not None
    d = decide_opportunity(_ready_opp(), router_allowlist=allow_r, token_allowlist=allow_t)
    assert d.would_execute is True
    assert d.optimal_notional_usd is not None
    assert "SHADOW" in d.reason and "advisory" in d.reason
    # stale quote → distinct sim-gate reason, not executable
    d2 = decide_opportunity({**_ready_opp(), "quote_status": "STALE"},
                            router_allowlist=allow_r, token_allowlist=allow_t)
    assert d2.would_execute is False
    assert d2.reason.startswith("simulation gate failed")
    assert "quote_fresh" in d2.reason
    # no pool → not executable, distinct reason (size infeasible)
    d3 = decide_opportunity({**_ready_opp(), "pool_liquidity_usd": 0},
                            router_allowlist=allow_r, token_allowlist=allow_t)
    assert d3.would_execute is False


def test_confidence_never_flips_execution():
    """Even with perfect confidence signals, a failed hard gate stays non-exec."""
    allow_r, allow_t = ["0xrouter"], ["0xa", "0xb"]
    opp = {**_ready_opp(), "gross_spread_bps": 0}   # expected_profit_positive fails
    d = decide_opportunity(opp, router_allowlist=allow_r, token_allowlist=allow_t)
    assert d.would_execute is False
