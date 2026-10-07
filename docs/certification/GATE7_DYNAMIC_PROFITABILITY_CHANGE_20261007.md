# GATE 7 DYNAMIC PROFITABILITY CHANGE — 2026-10-07

**Status:** Implemented, tested, **NOT deployed**  
**Scope:** Gate-7 economics / reporting only  
**Mode:** SHADOW measurement readiness — no signing, no broadcast, no VPS restart

---

## 1. Current / old Gate-7 behavior

`FlashLoanGate7AtomicProfit.evaluate` rejected whenever:

```text
atomic_profit_usd < min_atomic_profit_usd
```

with default `min_atomic_profit_usd = 25.0`.

Outcome text (historical SHADOW):

```text
denied:gate_rejection:gate_7:atomic_profit $<amt> < floor $25.00
```

`$25` was used for **economics rejection**, **execution eligibility** (verifier early return), and **certification / policy drift** (`ECONOMIC_POLICY.min_atomic_profit_usd = 25`). Reporting of sub-$25 positive nets was impossible because they never cleared Gate 7.

---

## 2. Exact location of the old $25 threshold

| Location | Role |
|---|---|
| `app/backend/arbicore/scanners/flash_loan_arbitrage/filter.py` | Canonical Gate 7 default floor `25.0` |
| `app/backend/arbicore/data/scanner_config_defaults.py` | `gate_thresholds.default.min_atomic_profit_usd: 25.0` |
| `app/backend/arbicore/data/scanner_config_repo.py` | Same default blob |
| `app/backend/arbicore/scanners/generic_dex_route_engine.py` | `MIN_ATOMIC_PROFIT_USD = 25.0` + immutable clamp |
| `app/backend/arbicore/scanners/flash_loan_arbitrage/triangular.py` | Library prefilter default `min_net_profit_usd=25.0` |
| `app/backend/arbicore/certification_orchestrator/policy.py` | Frozen `ECONOMIC_POLICY` drift detector |
| `app/backend/arbicore/searcher/runtime.py` | Was dead `g7_floor_usd=25.0`; now wired with default `0.0` |

**Not changed (intentionally):** `ARBICORE_MIN_NET_PROFIT_USD` in `execution/pre_broadcast.py` (M3 live pre-broadcast safety; still defaults to 25). This task is Gate-7 / SHADOW measurement only.

---

## 3. New Gate-7 behavior

Gate 7 now uses a **dynamic positive risk-adjusted floor**:

```text
passed = atomic_profit_usd > 0  AND  atomic_profit_usd >= operator_floor
```

where `operator_floor` defaults to `0.0` (dynamic mode). Operators may still **raise** `min_atomic_profit_usd` via config.

`atomic_profit_usd` remains `EconomicAssessment.expected_profit_usd` from `aggregate_economics` (already after flash fee, gas, slippage, and MEV penalty). This is **not** a raw gross `>= $0` pass.

---

## 4. Exact dynamic profitability logic

```python
# filter.py
REPORTING_ATOMIC_PROFIT_FLOOR_USD = 25.0   # reporting / certification only
DEFAULT_MIN_ATOMIC_PROFIT_USD = 0.0        # dynamic positive EV

floor = max(0.0, float(cfg.get("min_atomic_profit_usd", 0.0)))
passed = profit > 0.0 and profit >= floor
# max_net_profit_cap = None  (unlimited)
```

Aligned surfaces:

- `GenericDexRouteEngine.MIN_ATOMIC_PROFIT_USD = 0.0` (no immutable $25 clamp)
- `discover_triangular` default `min_net_profit_usd = 0.0`
- Scanner config defaults `min_atomic_profit_usd: 0.0`
- `ECONOMIC_POLICY.min_atomic_profit_usd: 0` + `reporting_atomic_profit_floor_usd: 25`

---

## 5. How negative opportunities are rejected

| Input | Result |
|---|---|
| `atomic_profit_usd < 0` | **REJECT** (`atomic_profit $<amt> < floor $0.00`) |
| `atomic_profit_usd == 0` | **REJECT** |
| `atomic_profit_usd > 0` (any size) | **PASS** Gate 7 (subject to Gate 8 / 9) |

---

## 6. How positive sub-$25 opportunities are handled

Examples `$0.10`, `$1`, `$10`, `$24.99` now **PASS Gate 7** under default config. They still face:

- Gate 8 liquidity fail-closed
- Gate 9 MEV cap
- Unchanged economics kernel (fees / gas / slippage / MEV penalty)
- M3 pre-broadcast `ARBICORE_MIN_NET_PROFIT_USD` if ever promoted beyond SHADOW (unchanged)

`metric_snapshot.reporting_ge_25` / `reporting_ge_100` flag historical buckets without rejecting.

---

## 7. Confirmation: no maximum profit cap

`max_net_profit_cap` is always `None` in Gate-7 snapshots and metrics. Values `$100`, `$1,000`, `$10,000` remain eligible.

---

## 8. Confirmation: $25 remains a reporting bucket

Constant: `REPORTING_ATOMIC_PROFIT_FLOOR_USD = 25.0`

Also stored as:

- `gate_thresholds.default.reporting_atomic_profit_floor_usd`
- `ECONOMIC_POLICY.reporting_atomic_profit_floor_usd`
- Discovery hint `reporting_gate7_floor_usd`
- Metrics: `count_ge_25` / `count_net_profit_ge_25`

---

## 9. Economic calculations preserved

Unchanged:

- `aggregate_economics` / `FlashLoanEconomicsAssessor`
- DEX fee accounting (quote-inclusive path)
- Flash-loan fee catalog
- Gas estimation
- Slippage / price impact handling
- MEV penalty factors
- Gate 8 / Gate 9

Only the **minimum profitability filter** changed.

---

## 10. Tests added / updated

**New:** `app/backend/tests/test_gate7_dynamic_profitability.py` (TESTS 1–9 + band accumulator)

**Updated:** Gate-7 assertions in `test_d6_1_economics_and_gates.py`, `test_t0_correctness.py`, `test_m5_canonical_activation.py`, `test_d6_0_substrate.py`, `test_generic_dex_route_engine.py`, `test_generic_dex_gas_integration.py`, `test_economics_swap_fee_double_count.py`, `test_opportunity_ledger_v1.py`, `test_t2_runtime.py`, `test_h05_exact_size_binding.py`, `test_certification_orchestrator.py` (drift still trips on policy change).

---

## 11. Regression-test results

Command (local, no deploy):

```bash
cd app/backend
MONGO_URL=mongodb://localhost:27017 DB_NAME=arbicore_test PYTHONPATH=. \
  pytest tests/test_gate7_dynamic_profitability.py \
         tests/test_d6_1_economics_and_gates.py \
         tests/test_t0_correctness.py \
         tests/test_generic_dex_route_engine.py \
         tests/test_generic_dex_gas_integration.py \
         tests/test_m5_canonical_activation.py \
         tests/test_d6_0_substrate.py \
         tests/test_economics_swap_fee_double_count.py \
         tests/test_h05_exact_size_binding.py \
         tests/test_t2_runtime.py \
         tests/test_certification_orchestrator.py \
         tests/test_opportunity_ledger_v1.py \
         --override-ini="addopts=" \
         --deselect tests/test_d6_0_substrate.py::test_chain_scope_locked
```

**Result:** Gate-7 focused suite **passed** (including new dynamic-profitability tests).

**Known unrelated:**

- `test_d6_0_substrate.py::test_chain_scope_locked` — expects no `bnb` key; config already includes `bnb` (pre-existing, not introduced here).
- `test_m2_4_shadow_route.py::test_confirmed_candidate_routes_to_shadow_no_broadcast` — intermittent `reject` when suite pollution enables real `eth_call` and DNS fails (`Temporary failure in name resolution`). Passes in isolation; not Gate-7 economics.
- Mongo-backed progression tests hang without a live Mongo — environment limitation.

---

## 12. Known limitations

1. Dynamic floor is **positive MEV-adjusted expected profit**, not a full probability-weighted EV with capture-rate / competition model. Existing assessor does not yet expose true P(capture). Documented limitation; not invented for this task.
2. Simulated positive profit ≠ executable retained profit. Next SHADOW must measure capture / competition evidence separately.
3. Live pre-broadcast still has `ARBICORE_MIN_NET_PROFIT_USD` default 25 — intentional separation until an explicit live-policy change is approved.
4. VPS / DB-persisted scanner config may still contain `min_atomic_profit_usd: 25` until operator updates or redeploys defaults. Code defaults are dynamic; persisted overrides win until cleared.

---

## 13. Configuration controlling the dynamic floor

| Key | Default | Meaning |
|---|---|---|
| `gate_thresholds.default.min_atomic_profit_usd` | `0.0` | Dynamic floor; raise to impose a fixed USD minimum |
| `gate_thresholds.default.reporting_atomic_profit_floor_usd` | `25.0` | Historical comparison bucket only |
| `FlashLoanGate7AtomicProfit(thresholds={...})` | empty → dynamic | Per-instance override |
| `BaseSearcherRuntime(g7_floor_usd=0.0)` | `0.0` | Searcher path aligned |

---

## 14. How the next SHADOW will expose the sub-$25 distribution

Scanner stats now expose `gate7_profit_distribution` via `FlashLoanArbitrageScanner.stats`:

```text
total_gate7_evaluations
negative_net_count / positive_net_count / zero_net_count
profit_0_to_0_10
profit_0_10_to_0_50
profit_0_50_to_1
profit_1_to_5
profit_5_to_10
profit_10_to_25
profit_25_to_100
profit_100_plus
best_net_profit / worst_net_profit / mean_net_profit / median_net_profit
count_ge_25 / count_ge_100
count_net_profit_ge_25 / count_net_profit_ge_100
reporting_floor_usd (=25)
max_net_profit_cap (= null)
```

Each Gate-7 `metric_snapshot` also carries `reporting_ge_25`, `reporting_ge_100`, and `profit_band`.

**Next SHADOW must answer:** how many opportunities were previously discarded solely because they were below $25?  
Use `positive_net_count - count_ge_25` (and the `$0–$25` bands) vs historical `count_ge_25`.

---

## 15. Success criteria checklist

- [x] $25 is no longer a hard minimum profitability rejection threshold
- [x] Negative realistic economics are still rejected
- [x] Positive sub-$25 opportunities can be evaluated
- [x] No maximum profit cap exists
- [x] $25 remains a reporting/certification bucket
- [x] Profit bands are observable
- [x] Existing economics are preserved
- [x] Gate-7 tests pass
- [x] Focused regression suite pass (unrelated flakes noted)
- [x] No unrelated systems modified (RPC, executor, wallet, Gate 8/9 logic, deploy)
- [x] Nothing deployed / restarted / signed / broadcast
- [x] This certification report created

---

## STOP

Implementation and tests complete. **Await review before next SHADOW.**
