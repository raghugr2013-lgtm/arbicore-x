# Workstream C — Economic / Evidence Refinement (read-only audit)

Branch: `engineering/gate9-parallel-93a20c9`  ·  Base: `93a20c9`  ·  Code changes: **NONE** (audit only)
Rule honoured: do NOT build another economic engine. Inspect the existing verifier/assessor + evidence
path and identify ONLY genuine packaging / reproducibility gaps. **None material found.** Gate 9 untouched.

---

## Existing economic decision chain (authoritative — do NOT rebuild)

```
discovery candidate (REAL hint)
   → verifier.py  (per-gate evaluation, fail-closed)
        gross_profit_pct   (REAL on-chain round-trip quote, fee+impact embedded)
        FlashLoanEconomicsAssessor.assess()  → aggregate_economics()
            legs: per-hop swap_fee (deducted only when NOT quote-inclusive) + flash_loan_premium leg
            flash fee  = borrow × provider_fee_bps/10_000   (Aave 5 / Balancer 0 / Morpho 0 / UniV3 tier)
            gas        = per_chain_gas_estimate_usd × (tx_gas_units/250_000)
            → net profit (atomic_profit_usd)
        multichain_economics.compute_true_net_profit()  (triangular/multichain path)
            gross − DEX fees − flash fee − gas − L1/chain − slippage − provider overhead
   → Gate7 ($25 floor) · Gate8 (liquidity/TVL) · Gate9 (MEV) · freshness (≤12s / block-lag)
   → EXECUTABLE/CONFIRMED  |  DENIED  (per-gate reason, never a generic denial)
   → _build_evidence_bundle()  → evidence_sink + (CONFIRM) shadow_sink
```

### Economic invariants verified present (all preserved — do NOT weaken)
- **Gross profit** = real quote-inclusive round-trip (double-count fix: pool swap fee NOT deducted
  twice when `gross_is_quote_inclusive=True`; observed fee retained as telemetry).
- **Flash repayment / premium** = explicit `flash_loan_premium` leg at verified provider bps.
- **DEX fees** = embedded in quote (live path) or deducted per hop (estimated path) — never both.
- **Gas** = per-chain estimate scaled by tx gas units; applied once on the loan leg.
- **Buffers / slippage** = per-hop slippage respected (0 in live path since impact is in the quote).
- **Net profit** = `aggregate_economics.expected_profit_usd` / `true_net_profit_usd`.
- **Gate7 $25** and **Gate8/H05** fail-closed; **never lowered**.
- **EXECUTABLE vs rejected** = explicit verification_status + per-gate outcomes.
- **Fail-closed on incomplete data**: unquotable leg → cycle skipped; unknown liquidity → infeasible;
  missing base price → `base_token_price_unavailable`; no fabricated values anywhere.

---

## Evidence bundle contents (`verifier.py::_build_evidence_bundle`, schema `m2.3`)

Reconstructs the full decision — confirmed present:
`bundle_id, verification_status (CONFIRMED|DENIED), outcome_tag, opportunity_id, candidate_id,
subject_id, discovery_source, chain, flash_loan_provider, borrow_token, input_amount_usd,
route{pools, pool_addresses, dex_protocols, token_path, hop_count},
quotes{gross_profit_pct, route_quote_status, hop_legs, H05 size_basis/exact_size/
quoted_amount_in_wei/quote_notional_usd/quote_block}, liquidity{min_pool_tvl + provenance,
price_provenance}, gas{tx_gas_units, gas_cost_usd}, mev{...}, gates{per-gate outcomes+reasons},
block_context{...}`.

→ This is sufficient to **replay the economic decision offline** from the bundle alone.

---

## Gap assessment

| Candidate gap | Finding | Delta |
|---|---|---|
| Separate economic engine missing | FALSE — assessor+verifier already reconstruct it | none |
| Net-profit fields missing from bundle | Present (quotes/gas/liquidity/gates all stamped) | none |
| Decision not reproducible from bundle | Reproducible — route+quotes+gas+gates+block_context captured | none |
| Replay harness absent | A dedicated offline replay *script* is not present, but is **not required** for the Gate 9/10 evidence campaign (verifier already re-derives on each run; bundles are self-describing) | **none now**; build only if a gate requires signed offline replay |
| Double-count risk | Already fixed (audit 2026-08), telemetry retained | none |

### Only actionable (optional, read-only) item
A post-Gate9 **read-only reproducibility spot-check**: take N CONFIRMED/DENIED bundles from the SHADOW
run and re-compute net profit from the stamped fields, asserting it matches `atomic_profit_usd` /
`true_net_profit_usd` and the recorded gate verdicts. This is a **test/verification artefact**, not an
engine change, and would only be written if you want an explicit reproducibility certificate. It must
NOT modify the verifier, economics, gates, or evidence schema.

**Net recommendation:** no economic/evidence code change during Gate 9. The infrastructure is complete,
truthful, and fail-closed. Preserve exactly as-is.
