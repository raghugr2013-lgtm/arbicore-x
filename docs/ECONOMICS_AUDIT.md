# ECONOMICS AUDIT (Phase 2B/2C)

Scope: `arbicore/economics/{net_profit,size_optimizer,expected_value,opportunity_decision}.py`.
Method: static read + deterministic execution probes + pinned unit tests
(`tests/test_phase2_economics_proof.py`, 15 tests, all pass). Pure/deterministic —
no RPC. **No thresholds were changed to make routes look profitable.**

## Directive questions → findings (evidence-based)

| Question | Finding | Evidence |
|---|---|---|
| Why `optimal_notional_usd` becomes null | Correct = "no feasible size". Every grid candidate is scored and rejected WITH a reason; `chosen=None` when none feasible. Not "optimizer not invoked". | negative-spread probe → chosen None, all candidates `reject_reason="net profit <= 0"`. |
| Optimizer genuinely evaluating sizes? | Yes — evaluates a full grid `[5k…1M]` + adaptive bisection refinement, picks **max risk-adjusted EV** (not max gross, not max loan). | `test_optimizer_evaluates_multiple_notionals_and_picks_max_ev`. |
| Liquidity measured or silent default? | No silent default. Missing/zero liquidity → fully-impacted (10000 bps) → infeasible. **Was a crash on `None`; fixed to fail-closed.** | `test_none_liquidity_fails_closed_not_crash`, `test_zero_liquidity_is_fully_impacted`. |
| 30 bps slippage fallback double-counting quote impact? | The optimizer uses a depth-derived `leg_impact` for slippage; there is no separate fixed 30 bps added on top of the depth model. `liquidity_impact = 0.25 × leg_impact` is charged in addition → total impact cost = **1.25× leg_impact** (conservative OVER-count; reduces net profit). Not a profit inflator. | `test_impact_layering_is_conservative_125pct`. |
| Gas ever double-counted? | No. `compute_net_profit` gas=0 unless the full (wei, units, price) triple is supplied; the optimizer/decision subtract gas **once** externally. | `test_gas_is_zero_when_triple_absent_and_counted_once_when_present`. |
| DEX fees double-counted? | Trading (venue) fees charged **once** via `buy/sell_venue_fee_bps`. Contract: caller must pass a **fee-exclusive** gross spread (else double count — documented caller invariant). | `test_gross_and_costs_are_linear_and_separable`. |
| Flash-loan fee modeled correctly? | `flash_loan_fee = flash_loan_fee_bps/1e4 × flash_loan_notional` (charged on the borrowed notional, once). | same test. |
| Quote/arbitrary-notional impact extrapolation | Impact scales linearly with `notional/pool_liquidity × impact_k` (depth-aware), penalising large sizes; not a flat extrapolation of a fixed probe. | size grid probe. |
| No-pool/reverted classified as negative economics? | No — no-pool → infeasible via impact/size, and the sim gate emits a **distinct** reason; not folded into "negative spread". | `test_decision_distinct_reasons_and_shadow_advisory`. |
| net_profit/EV/optimizer consistent units? | Yes — all USD, bps consistently `/10_000`. EV = `p·net − q·max_loss`. | `test_ev_formula_is_p_net_minus_q_maxloss`. |
| Failed-simulation probability/max-loss conservative? | Yes — failed sim caps P(success) ≤ 0.10; **absent evidence → P=0.0** (not neutral 0.5), with uncertainty_penalty=1.0. | `test_absent_evidence_is_zero_confidence_not_neutral`, `test_failed_simulation_caps_probability`. |

## Fix applied
`size_optimizer._impact_bps` and `_score_size` now treat `pool_liquidity_usd is None`
as fully-impacted (was `None <= 0` → `TypeError`). Fail-closed, never a crash,
never silently profitable. (Note: `decide_opportunity` already coerced `None → 0.0`;
this hardens direct callers/tests.)

## Verdict: ECONOMICS = GREEN (deterministic layer). Live-RPC-fed economics
(real quotes/liquidity/gas) remain YELLOW pending Phase 2E fork validation with a
provisioned archive RPC — not available in this environment.
