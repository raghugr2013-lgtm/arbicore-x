# Phase 0.5 — Opportunity Intelligence & Learning Ledger architecture audit

**Classification: PHASE_0_5_ARCHITECTURE_AUDIT_COMPLETE**

**Date:** 2026-10-05

**Mode:** read-only inspection. No source edit, MongoDB write, collection, schema change, configuration change, scanner control, SHADOW start or stop, deploy, restart, RPC change, Network Config change, Gate change, wallet change, signing, broadcast, commit, or push.

**Inputs already closed:**

| Input | Identity |
|---|---|
| Phase 0 observer | `phase0.strategy_intelligence.v1` |
| SHADOW certification | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |
| Strategy × economics ranking | `docs/certification/REAL_SHADOW_288_STRATEGY_ECONOMICS_RANKING_20261005.md` (`STRATEGY_ECONOMICS_RANKING_COMPLETE`) |

This document designs nothing that runs. It records what already exists, what a ledger can reuse, and what is absent. It does not implement the ledger, the proposed failure codes, or Excel.

Field classes used below:

| Class | Meaning |
|---|---|
| `AVAILABLE` | A stored field already holds the value, including a stored null or a stored zero. |
| `PARTIAL` | The field exists for some rows of the 288, or it exists in a form that is not the requested unit. |
| `MISSING` | No persisted field. An in-memory calculator result that was not copied onto the document is `MISSING`. It is not recomputed here. |
| `DERIVABLE` | An existing read-only function can project the value from stored fields without applying the economics formula again. |

---

## 1. Executive summary

The 288 Gate-7 candidates already have a persistence spine. Every row is a `DiscoveryCandidate` in `arbicore_discovery_candidates`. One hundred eighty of them also have an m2.3 verifier document in `evidence_bundles`. The Phase 0 observer can classify those records in memory. It does not write `primary_family`, secondary tags, or an economics observation back to MongoDB.

There is no single immutable `opportunity_id` on this population. Denied verification sets `opportunity_id` to null and does not insert `arbicore_opportunities`. The stable key that exists on all 288 rows is `candidate_id`. The certification `run_id` exists on `arbicore_shadow_certifications` and is not stamped onto the candidate or the bundle. The scanner stamps a different id, `diagnostics.audit_run_id`.

Gate reasons already exist as verifier strings (`denied:gate_rejection:gate_7:atomic_profit $… < floor $25.00`, `denied:venue_unreadable`, `denied:quote_invalid:`, `denied:size_not_quoted`). The proposed normalized codes (`NO_GROSS_EDGE`, `FEES_KILLED`, `GAS_KILLED`, and the rest) are not canonical enums. This window’s 288 rows stopped at Gate 7, so Gates 8 and 9 remain `NOT_EVALUATED` on the 180 bundles.

The learning ledger, calibration log, and adaptive-weight observer already implement observe-and-recommend behaviour for **canonical** opportunities that reach the journal. The flash-loan verifier does not call that journal on a Gate-7 denial. The 288 rows are therefore outside the current learning sample path.

The UI Opportunities page reads `arbicore_opportunities` and filters `OpportunityType` (scanner family such as `FLASH_LOAN_ARBITRAGE`). It does not list these denied candidates and it does not filter `phase0.strategy_intelligence.v1` families. Excel export exists for a different ledger (institutional cycle accounting), not for this population.

A minimal Phase 0.5 ledger is a persistable projection of records that already exist, keyed by `candidate_id`, joined to the certification run by an explicit link that does not exist yet. It is not a new trading engine.

---

## 2. Existing architecture

Five layers already touch an opportunity, and they do not share one document.

| Layer | Role on a flash-loan SHADOW denial |
|---|---|
| Discovery | `DiscoveryCandidate` in `arbicore_discovery_candidates`. Separate type from `CanonicalOpportunity`. |
| Verifier | `FlashLoanOpportunityVerifier` writes an m2.3 bundle for both `CONFIRMED` and `DENIED`, then returns. On Gate 7 failure, `canonical` is `None`. |
| Phase 0 observer | `observe_strategy_intelligence(bundle, candidate)` in the certified image. Read-only. Not imported by the verifier. Not in this worktree. |
| Canonical opportunity | `CanonicalOpportunity` in `arbicore_opportunities`. Created only when verification confirms. Status machine: `candidate → validated → approved → executed → completed`, plus `rejected`. Execution statuses are reserved. |
| Journal and learning | `arbicore_opportunity_journal`, then `LearningLedger` → `calibration_log` and adaptive-weight recommendations. Written for canonical rows the executor path records. Not written by the flash-loan denial path. |
| Certification run | `ShadowCertificationRun` in `arbicore_shadow_certifications`. Counts the certification engine’s own opportunity counters. This run recorded seen 0, processed 0, executable 0. The 288 Gate-7 rows are outside those counters. |

Two strategy classifiers exist. They are not interchangeable.

| Classifier | Where | What it emits | Used on the 288? |
|---|---|---|---|
| `phase0.strategy_intelligence.v1` | Certified image `arbicore.observability`. Absent from this worktree. | `primary_family`, `secondary_tags`, `classification_state`, `confidence`, `strategy_completeness`, evidence lines. | Yes, in memory, for the ranking. Not persisted. |
| `classify_strategy` in `strategy_tagging.py` | This worktree. | `StrategyType`: `GENERIC_DEX`, `TRIANGULAR`, `STABLECOIN`, `MULTI_HOP`, `LST_LRT`. Uses token symbols and hop count. | No. It runs at canonical emit time. Denied rows are not emitted. |

The ledger’s strategy section has one legal source: `phase0.strategy_intelligence.v1`. `StrategyType` from `strategy_tagging.py` is a different vocabulary (`GENERIC_DEX` versus `DEX_TO_DEX`, hop-count `MULTI_HOP`, no `CROSS_POOL`, `CROSS_PROTOCOL`, `MULTI_DEX`, or `COMPLEX_TRIANGULAR_CROSS_PROTOCOL`).

---

## 3. Existing data flow

For the certified flash-loan scanner the path is:

1. A discovery source inserts a `DiscoveryCandidate` (`hint_observed_at`, `hint_metric`, `candidate_id`, `subject_id`, `chain`).
2. The scanner claims the candidate and calls the verifier.
3. The quote provider, when it returns, fills `hop_legs`, gross percent, size basis, and block.
4. `FlashLoanEconomicsAssessor.assess` calls `aggregate_economics` in memory.
5. Gate 7 runs. On failure the verifier returns immediately. Gates 8 and 9 stay at their initial `NOT_EVALUATED`.
6. `_finalize` persists `_build_evidence_bundle` through the evidence sink. `broadcast` is hard-coded `false`. `canonical` is null, so `opportunity_id` on the bundle is null, and the SHADOW sink is not called.
7. The queue stores `verified_outcome` and `verified_at` on the candidate.
8. Phase 0 can be applied later, in memory, to the stored bundle and candidate. Nothing in that call writes.

Rows that never receive a bundle (108 of 288, including all 45 BNB Gate-7 rows in this window) stop at step 7. Their decision net exists only as text inside `verified_outcome`. Their route fields exist on `hint_metric`, which the Phase 0 reader accepts when the bundle is absent.

`venue_unreadable` rows (480 in the same certification window, other worker) never reach economics or Gate 7. They are outside the ranked 288.

---

## 4. Existing persistence map

| Collection | What it is | Present for this population |
|---|---|---|
| `arbicore_discovery_candidates` | Discovery hint plus verifier outcome. | 288 Gate-7 rows. `hint_source=flash_loan_route_search`. |
| `evidence_bundles` | m2.3 verifier audit document from `flash_loan_arb_verifier`. | 180 rows, worker `flash_loan_arb:0eb9228c`, one bundle each. |
| `arbicore_shadow_certifications` | Immutable-by-convention certification run (`shadow_cert_v1`). | The run document. `status=ABORTED`. |
| `arbicore_opportunities` | Canonical opportunity, one schema for every scanner family. | Not written for these denials. |
| `arbicore_opportunity_journal` | One document per `opportunity_id`, append-only `events`. | Not written by the flash-loan denial path. |
| `calibration_log` | Learning samples (`predicted_confidence`, `survived`, `opportunity_id`). | Fed by the journal ledger, not by these 288 rows. |
| `adaptive_weight_recommendations` | Observe-mode weight recommendations. | Global learning output. Not keyed to these candidates. |
| `production_ledger` | Frozen institutional cycle accounting, with CSV and xlsx export. | A different product. Not this population. |

The signed-evidence helper `new_bundle` (`bundle_version=v1`, hashed payload, optional signature) is a second bundle shape used by the evidence signing worker. The flash-loan verifier writes the m2.3 document directly. The 180 rows are the m2.3 shape (`schema_version=m2.3`), not the hashed `v1` envelope.

---

## 5. Candidate → verifier → observer relationship

| Link | Rule | On the 288 |
|---|---|---|
| Candidate → bundle | `evidence_bundles.source_model_id = candidate.candidate_id`, `source_component = flash_loan_arb_verifier`. | 180 one-to-one. 108 have no bundle. |
| Bundle → canonical opportunity | `bundle.opportunity_id` is set only when a `CanonicalOpportunity` was built. | Null on these denials. |
| Candidate id formula | `make_candidate_id`: SHA-1 of hint source, opportunity type, `subject_id`, asset, venues, and `floor(hint_observed_at / 60)`, truncated to 20 hex characters. | `AVAILABLE` on all 288. Stable inside one 60-second discovery window. A later minute produces a different id for the same route. |
| Confirmed opportunity id formula | `_opp_id`: `flash_loan_arb:{subject_id}:{int(verified_at_ts)}`. | Not applied. Confirmation did not occur. |
| Bundle id | `flarb:{candidate_id}:{int(verified_at_ts)}`. | `AVAILABLE` on the 180. |
| Observer input | `observe_strategy_intelligence(bundle, candidate)`. Bundle fields win. Candidate `hint_metric` fills lists the bundle does not carry. Disagreement on hop count is a conflict and yields `INCOMPLETE`. | Applied in memory for the ranking. `COMPLETE` / `FULLY_CLASSIFIED` on all 288 when the candidate is passed. Not stored. |
| Certification run | `run_id` on `arbicore_shadow_certifications`. | Not a field on the candidate or the bundle. The ranking joined on `verified_at` inside `[started_at, completed_at)`. |

`diagnostics` on the bundle carries `audit_run_id` (`flarb_audit:…`, stable for one scanner process), `scanner_tick_id`, `worker_id`, `candidate_id`, claim timestamps, `hint_observed_at`, and `stamped_at`. That audit id is not `shadowcert-…`.

---

## 6. Field availability matrix

### A. Opportunity identity

| Field | Class | Where |
|---|---|---|
| `candidate_id` | `AVAILABLE` | Candidate, and bundle `candidate_id` / `source_model_id` on 180. |
| Immutable lifetime `opportunity_id` | `MISSING` | Denied bundles store null. Canonical collection has no row. `candidate_id` changes across the 60-second window. |
| Certification `run_id` | `PARTIAL` | Stored on the run document. Absent on candidate and bundle. |
| Chain | `AVAILABLE` | Candidate `chain`. Bundle `chain` on 180. |
| Discovery timestamp | `AVAILABLE` | `hint_observed_at`. |
| Strategy family | `DERIVABLE` | Phase 0 `primary_family`. Not persisted. See section 8. |
| Lifecycle state | `PARTIAL` | `verified_outcome` is a denial string, not the requested state enum. See section 7. |

### B. Price / route path

Applies to m2.3 `quotes.hop_legs` plus `route.*`. Decision-only rows have `hint_metric` route lists and no hop quote.

| Field | On 180 bundles | On 108 decision-only | Class |
|---|---|---|---|
| Leg index | Array position | `MISSING` | `PARTIAL` |
| Token in / out | `hop_legs[].token_in`, `token_out`. Also `route.cycle_token_path`. | Path symbols on `hint_metric.cycle_token_path` only. | `PARTIAL` |
| Protocol | `dex_protocol`, also `route.route_dex_protocols`. | `hint_metric.route_dex_protocols`. | `PARTIAL` |
| DEX / venue | `venue_id` is `{dex}:{chain}`. `source_id` is the quote source id. | `MISSING` | `PARTIAL` |
| Pool id | `route.route_pools`, aligned by index when lengths match. | `hint_metric.route_pools`. | `PARTIAL` |
| Pool address | `route.route_pool_addresses`. Unresolved entries are stored null. | `MISSING` | `PARTIAL` |
| Input amount | `amount_in_wei`. Route-level `quoted_amount_in_wei` and `quote_notional_usd`. | `MISSING` | `PARTIAL` |
| Output amount | `amount_out_wei`. Route-level `final_amount_out_wei` is in quote facts; the bundle copies hop legs, not a separate final-out field in the economics block. | `MISSING` | `PARTIAL` |
| Price | Key `price` is stored and the value is `None`. | `MISSING` | `PARTIAL` |
| Fee | `fee_bps` per hop. Dollar fee per hop is `MISSING`. | `MISSING` | `PARTIAL` |
| Slippage | No per-leg slippage field. Route `fees.total_slippage_pct` on rows that stored economics. | `MISSING` | `PARTIAL` |
| Quote timestamp | No per-leg quote time. Route `block_context.verified_at_ts` and candidate `verified_at`. | `verified_at` only. | `PARTIAL` |
| Block | `hop_legs[].block_number` and `quotes.quote_block` / `block_context.block_number`. | `MISSING` | `PARTIAL` |
| Provider / source | Flash-loan provider on the bundle. Per-leg `source_id`. | Provider from `subject_id` and `hint_metric.provider`. | `PARTIAL` |
| Depth | `depth_usd` per hop. Zero is stored when TVL was not resolved. | `MISSING` | `PARTIAL` |
| Quote status | `status` per hop and `quotes.route_quote_status`. | `MISSING` | `PARTIAL` |

`price: null` stays null. It is not a missing key on the 180, and it is not a number that can be filled from the gross percent.

### C. Strategy intelligence

See section 8. Summary: `DERIVABLE` for all 288, `MISSING` as a stored document.

### D. Economics waterfall

See section 9.

### E–J

Lifecycle, failure codes, provenance, run aggregates, UI, and learning are sections 7 and 10–14.

---

## 7. Lifecycle / timestamp availability

Requested ladder:

`DISCOVERED → CLASSIFIED → QUOTED → VERIFIED → ECONOMICS_CALCULATED → GATED → PROFITABLE / UNPROFITABLE → EXECUTED / NOT_EXECUTED`

| Requested stage | Existing timestamp or state | Class |
|---|---|---|
| `DISCOVERED` | `hint_observed_at` on all 288. | `AVAILABLE` |
| `CLASSIFIED` | No `classified_at`. Phase 0 has no persisted row. | `MISSING` |
| `QUOTED` | Quote block and `verified_at_ts` on the 180 bundles that contain `hop_legs` with `route_quote_status=ok` and `exact_size=true`. No separate `quoted_at`. | `PARTIAL` |
| `VERIFIED` | `verified_at` on all 288. Bundle `created_at` and `verification_status=DENIED` on 180. | `AVAILABLE` |
| `ECONOMICS_CALCULATED` | No separate timestamp. The economics object is stored on the same bundle as verification for the 180. | `PARTIAL` |
| `GATED` | Outcome string on all 288. `gates.gate_7.status=FAIL` on 180. Gates 8 and 9 stored as `NOT_EVALUATED` because the verifier returns at the first failure. | `PARTIAL` |
| `PROFITABLE` / `UNPROFITABLE` | No such enum on the candidate. Sign of the decision net is `DERIVABLE` from the stored Gate-7 text. This window: 288 unprofitable, 0 profitable. | `DERIVABLE` |
| `EXECUTED` | Not assumed. `broadcast=false` on all 180 bundles. Confirmed count 0. Rows emitted 0. | `AVAILABLE` as `broadcast=false` on 180. `MISSING` on 108. |
| `NOT_EXECUTED` | No stored stage with that name. The SHADOW posture is the absence of broadcast plus `broadcast=false`. | `PARTIAL` |

Other lifecycles that already exist, and that this population did not enter:

| Vocabulary | States | Writer |
|---|---|---|
| `OpportunityStatus` | `candidate`, `validated`, `approved`, `executed`, `completed`, `rejected` | Canonical FSM. Flash-loan denial does not create the row. |
| Journal `ExecutionStatus` | `DISCOVERED`, `QUOTED`, `GAS_ESTIMATED`, `PROFITED`, `CERTIFIED`, `POLICY_DENIED`, `REJECTED`, `SHADOW_RECORDED`, `BROADCAST_SENT`, `BROADCAST_FAILED`, `COMPLETED` | `OpportunityJournal`. Flash-loan verifier does not call `record_discovery`. |
| UI economic state | `DISCOVERED`, `LIVE_QUOTED`, `VERIFIED`, `ECONOMICALLY_VALID`, `M3_GREEN` | Display contract over a canonical row. |
| `VerifiedOutcome` | `confirmed_canonical:`, `denied:venue_unreadable`, `denied:venue_disagrees`, `denied:no_verifier_registered`, `denied:gate_rejection:`, `denied:quote_invalid:`, `denied:size_not_quoted`, `error:`, `expired_unclaimed` | Discovery queue. This is the outcome vocabulary the 288 actually use. |

A ledger lifecycle can record the timestamps that exist. It cannot backfill `CLASSIFIED` or `EXECUTED` times.

---

## 8. Strategy intelligence availability

| Field | Class | Notes |
|---|---|---|
| `primary_family` | `DERIVABLE` | Phase 0 output. Ranking distribution: `DEX_TO_DEX` 17, `CROSS_PROTOCOL` 8, `CROSS_POOL` 27, `MULTI_HOP` 27, `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` 83, `MULTI_DEX` 34, `TRIANGULAR` 92. |
| `secondary_tags` | `DERIVABLE` | Same call. Not stored. |
| `confidence` | `DERIVABLE` | `HIGH` 43, `MEDIUM` 245 in the ranking. |
| Evidence lines | `DERIVABLE` | Returned on the observation. Not stored. |
| `classifier_version` | `DERIVABLE` | Constant `phase0.strategy_intelligence.v1` on the observation. Not stored on the bundle. |
| `classification_state` | `DERIVABLE` | `COMPLETE` on all 288 when the candidate is included. |
| `strategy_completeness` | `DERIVABLE` | `FULLY_CLASSIFIED` on all 288 in that same call. |
| `STABLECOIN_CROSS_PROTOCOL` | `DERIVABLE` as count 0 | The classifier did not assign it. |
| `LST_LRT_CROSS_PROTOCOL` | `DERIVABLE` as count 0 | The classifier did not assign it. |
| Persisted strategy label on the 288 | `MISSING` | Bundles do not store `primary_family`. Candidates do not store `strategy`. |

The observer refuses a family when per-leg protocol fields are incomplete. Pool ids, venue ids, and addresses are not parsed into a protocol. The flash-loan provider is not a route protocol. Those rules are why the ranking could label the 108 from `hint_metric.route_dex_protocols` and still leave stablecoin and LST/LRT unproven.

`StrategyType` on `CanonicalOpportunity.strategy` is `MISSING` here because emit did not run. Using `classify_strategy` to fill it would be a different classifier. The ledger must not do that.

The observer module lives in the certified image (`/app/arbicore/observability/`, commit `823a79b617ddb1f19397cf5073b9c516aae4e9fd`). This worktree has no `arbicore/observability` package. A later implementation has to use that deployed module, or bring that same version into the tree under a separate change. This audit does not copy it.

---

## 9. Economics availability

`aggregate_economics` computes a full `EconomicAssessment` in memory: gross, slippage, fee percent, extra cost, gas, gas drag, MEV penalty, net after costs, MEV-adjusted net percent, expected profit, notional, and `profitable`. `_build_evidence_bundle` copies only a subset. Phase 0 `observe_economics` reads stored fields and parses the Gate-7 text. It does not call `aggregate_economics`.

| Waterfall field | 180 complete bundles | 108 decision-only | Class |
|---|---|---|---|
| Notional | `quotes.quote_notional_usd`, `economics.borrow_amount_usd`, `input_amount_usd` | `MISSING` | `PARTIAL` |
| Gross spread % | `economics.gross_spread_pct` and `quotes.gross_profit_pct` | `MISSING` | `PARTIAL` |
| Gross profit $ | No m2.3 field | `MISSING` | `MISSING` |
| DEX fee % | `fees.total_swap_fee_pct` | `MISSING` | `PARTIAL` |
| DEX fee $ | No field | `MISSING` | `MISSING` |
| Flash-loan fee $ | `fees.flash_loan_fee_usd` | `MISSING` | `PARTIAL` |
| Flash-loan fee rate | `fees.flash_loan_fee_bps` is the quote override coerced with `or 0`, not the applied catalog bps. Phase 0 marks the applied rate `AVAILABLE_NOT_PERSISTED`. | `MISSING` | `MISSING` as an applied rate. The stored override integer is `PARTIAL`. |
| Gas $ | `gas.gas_cost_usd` | `MISSING` | `PARTIAL` |
| Gas units | `gas.tx_gas_units` on 146 of 288 (absent on 34 of the 180) | `MISSING` | `PARTIAL` |
| Gas price | No field | `MISSING` | `MISSING` |
| Slippage % | `fees.total_slippage_pct` | `MISSING` | `PARTIAL` |
| Slippage $ | No field | `MISSING` | `MISSING` |
| MEV label | `mev` view on the bundle | `MISSING` | `PARTIAL` |
| MEV penalty %, MEV-adjusted net %, true net % | Computed inside `aggregate_economics` and not copied. Phase 0 status `AVAILABLE_NOT_PERSISTED` when an economics object exists. | `MISSING` | `MISSING` |
| True net $ | `economics.atomic_profit_usd`, stored equal to `economics.expected_net_after_costs_usd` | `MISSING` | `PARTIAL` |
| Decision net $ | Cent text inside `outcome_tag`, matched to candidate `verified_outcome` | Cent text inside `verified_outcome` | `AVAILABLE` as text on all 288. Structured field is `DERIVABLE` by the Phase 0 parser. |
| Net % | `atomic_profit_pct` is computed in `_fold_metadata` for the confirm metadata fold. It is not a key in the persisted `economics` object. | `MISSING` | `MISSING` |
| Total costs | Sum of components inside the assessor. Not copied as one field. | `MISSING` | `MISSING` |
| Gate 7 | `gates.gate_7` `FAIL` plus the outcome string | Outcome string only. No `gates` object. | `PARTIAL` |
| Gate 8 | `gates.gate_8.status = NOT_EVALUATED` | `MISSING` | `PARTIAL` |
| Gate 9 | `gates.gate_9.status = NOT_EVALUATED` | `MISSING` | `PARTIAL` |
| `economics.completeness` from Phase 0 | `PARTIAL` on every row of the ranking, including the 180, because several ranked fields are absent or `AVAILABLE_NOT_PERSISTED` | same | `DERIVABLE`, not stored |

Stored zero stays zero. `total_slippage_pct = 0.0` on a bundle is a stored zero. `flash_loan_fee_usd = 0.0` for Balancer is a stored zero. `price: null` is a stored null. `depth_usd = 0.0` is a stored zero when TVL was not resolved, and Gate 8 treats non-positive TVL as unverifiable when that gate runs. This window did not run Gate 8.

The decision net used by the ranking is the cent-rounded amount in the Gate-7 sentence. Full-precision `atomic_profit_usd` exists only on the 180. The largest absolute gap versus the cent text, measured in the 4 October economics note for an earlier window, was under one cent. This audit does not recompute the 5 October gap.

Population economics already measured, and not restated as a new calculation: 288 negative decision nets, best `-$59.31`, mean `-$345.32`, none `>= $0`, none `>= $25`.

---

## 10. Gate / failure reason availability

Canonical reasons that already exist on the flash-loan path:

| Code already stored | When it is written | Gate object |
|---|---|---|
| `denied:gate_rejection:gate_7:atomic_profit $<amt> < floor $<floor>` | Gate 7 fail. Reason body from `FlashLoanGate7AtomicProfit`: `atomic_profit $X.XX < floor $Y.YY`. | `gates.gate_7.status=FAIL` when a bundle exists. |
| `atomic-profit gate passed` | Gate 7 pass. Not present in this window. | `PASS` |
| `denied:gate_rejection:gate_8:` plus the Gate 8 sentence | Gate 8 fail, only if Gate 7 passed. | `FAIL` |
| `liquidity-depth gate FAILED CLOSED — route TVL unverifiable (no fabricated liquidity pass)` | Gate 8 when min TVL `<= 0`. | `FAIL` |
| `min route TVL $N < floor $M` | Gate 8 below the TVL floor. | `FAIL` |
| `liquidity-depth gate passed` | Gate 8 pass. | `PASS` |
| `denied:gate_rejection:gate_9:` plus the Gate 9 sentence | Gate 9 fail, only if Gates 7 and 8 passed. | `FAIL` |
| `MEV level <level> exceeds cap <cap>` | Gate 9 above the cap. | `FAIL` |
| `flash-loan MEV gate passed` | Gate 9 pass. | `PASS` |
| `denied:venue_unreadable` | Quote provider returned nothing. Gates stay `NOT_EVALUATED`. | All three `NOT_EVALUATED` |
| `denied:quote_invalid:<reason>` | Quote integrity failure before economics. Reasons include `route_status:…`, `hop_<i>_status:…`, `gross_profit_missing`, `gross_profit_malformed`, `gross_profit_nonfinite`. | Not a Gate 7/8/9 code |
| `denied:size_not_quoted` | Probe-sized quote, H05. | Not a Gate 7/8/9 code |
| `denied:venue_disagrees` | Declared on `VerifiedOutcome`. | Separate from Gate 7 |
| `denied:no_verifier_registered` | No verifier. | Separate |
| `error:` / `expired_unclaimed` | Queue errors and TTL. | Separate |
| `confirmed_canonical:<opportunity_id>` | Confirmation. Count 0 in this window. | Gates passed |
| `NOT_EVALUATED` | Initial gate status, left in place when an earlier gate fails. | Stored on the 180 for Gates 8 and 9 |

Scanner counters name the same gates (`gate_7_atomic_profit`, `gate_8_liquidity_depth`, `gate_9_flash_loan_mev`, `denied_venue_unreadable`). Those counters are process stats, not per-candidate documents.

Journal rejection labels (`REJECTED`, `POLICY_DENIED`, `BROADCAST_FAILED`) are a second vocabulary. They were not written for these 288 rows.

The proposed normalized set is **not implemented** and must not be invented by renaming the strings above:

| Proposed code | Existing canonical reason |
|---|---|
| `NO_GROSS_EDGE` | `MISSING` as a code. Gross percent is stored on 180 bundles. The stored denial is the Gate 7 atomic-profit sentence, which is net of costs, not a gross-edge code. |
| `FEES_KILLED` | `MISSING` |
| `FLASH_FEE_KILLED` | `MISSING` |
| `GAS_KILLED` | `MISSING` |
| `SLIPPAGE_KILLED` | `MISSING` |
| `MEV_KILLED` | `MISSING`. Gate 9’s sentence exists for when Gate 9 runs. It did not run on these 288. |
| `QUOTE_DECAY` | `MISSING` |
| `STALE_DATA` | `MISSING` as a denial code. UI freshness is a display flag on canonical rows (`age_s > 60`). |
| `TVL_GATE` | The Gate 8 sentences above are the canonical text. They were not the denial on these 288. |
| `VENUE_UNREADABLE` | `AVAILABLE` as `denied:venue_unreadable`. Outside the 288. Inside the same time window: 480 rows. |
| `SEARCH_LIMITATION` | `MISSING` as a denial code. `route_search_wall_ms` and `route_search_candidates_explored` are copied into confirm-path metadata (`_fold_metadata`), not into the denial bundle’s economics block. |
| `EXECUTION_FAILURE` | `MISSING` on this population. Journal has `BROADCAST_FAILED` for a different path. |
| `NOT_EXECUTED_SHADOW` | `MISSING` as a code. `broadcast=false` is the stored fact on 180 bundles. |

A future normalizer would be a new mapping. This audit does not define that mapping. The single stored denial is one cause: the first failing gate, or an earlier quote failure. Component economics on the 180 can be displayed beside that sentence. They are not already a multi-cause reason code.

---

## 11. Provenance availability

| Provenance item | Class | Where it lives |
|---|---|---|
| Flash-loan provider | `AVAILABLE` | `subject_id`, `hint_metric.provider`, and bundle `flash_loan_provider` on 180. The three agreed on all 288 in the ranking. |
| Quote source id | `PARTIAL` | `hop_legs[].source_id` on 180. |
| Quote status and size basis | `PARTIAL` | `route_quote_status`, `size_basis`, `exact_size` on 180. |
| Block number | `PARTIAL` | Per-hop `block_number` and route `quote_block` on 180. |
| Timestamps | `PARTIAL` | `hint_observed_at`, `verified_at`, bundle `created_at`, `block_context.verified_at_ts`, `diagnostics.stamped_at`. |
| TVL provenance | `PARTIAL` | `liquidity.tvl_provenance` (`onchain_reserves` or `unverified`) on 180. |
| Price provenance | `PARTIAL` | `liquidity.price_provenance` when the M2.5 callback is wired. Empty list when it is not. |
| Bundle provenance label | `AVAILABLE` on 180 | `provenance: "REAL"`. This is a constant string on the verifier bundle, not a per-field source. |
| Calculator version | `MISSING` | Phase 0 reads `economics.calculator_version` / `economics_version` only when stored. The m2.3 writer does not set them. |
| Classifier version | `DERIVABLE` | Returned by the observer. Not stored. |
| Verifier id | `MISSING` on the denial bundle | `verifier_id=flash_loan_opportunity_verifier` is placed in `_fold_metadata`, which is confirm-path metadata, not the denial bundle body. `source_component=flash_loan_arb_verifier` is `AVAILABLE` on 180. |
| Code / commit | `PARTIAL` | Image and `BUILD_INFO` / version endpoint identify the running process (`823a79b` for this certification). The commit is not a field on the candidate or the bundle. |
| Scanner audit identity | `PARTIAL` | `diagnostics.audit_run_id`, `scanner_tick_id`, `worker_id` on 180. |
| Certification run identity | `PARTIAL` | On the run document only. |
| RPC URL | `MISSING` on these documents | Network Config holds endpoints. They are secrets-bearing and must not be copied into a ledger, an export, or this report. |
| Signing | `AVAILABLE` as absent | Certification recorded no active signing key. m2.3 denial bundles are not the signed `v1` evidence envelope. |

`execution_plan` on the bundle can carry a B7 handoff status and calldata. That block is evidence of an unsigned plan. It is not an execution. A ledger view must treat calldata as sensitive operational material and must not treat it as a broadcast.

---

## 12. Run-level evidence availability

`ShadowCertificationRun` (`schema_version=shadow_cert_v1`) already stores:

| Requested run field | Class | Fact for `shadowcert-5605e7b9-…` |
|---|---|---|
| `run_id` | `AVAILABLE` | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |
| Start / end | `AVAILABLE` | `2026-10-05T05:27:48.513927+00:00` → `2026-10-05T05:58:04.231514+00:00` |
| Status | `AVAILABLE` | `ABORTED`, fail reason `aborted: real_30min_flash_loan_shadow_complete` |
| Cycle list | `AVAILABLE` | 91 cycles, all `PASS` / `ok_low_volume` |
| Engine opportunity counts | `AVAILABLE` | seen 0, processed 0, executable 0 |
| Chain coverage of Gate-7 rows | `DERIVABLE` | Not on the run document. Six chains appear on the candidates inside the window. |
| Candidate count 288 | `DERIVABLE` | Time-window query. Not a field on the run. |
| Verified count | `DERIVABLE` | 768 verified outcomes in the window (288 Gate 7 + 480 `venue_unreadable`). The run summary does not hold that split. |
| Profitable count | `DERIVABLE` | 0, from decision-net sign. Not on the run. |
| Gate 7 pass / fail | `DERIVABLE` | 0 pass, 288 fail, from outcome text. Not on the run. |
| Strategy-family distribution | `DERIVABLE` | Phase 0 in memory. Not on the run. |
| Economics distribution | `DERIVABLE` | From decision-net text, plus bundle economics on 180. Not on the run. |
| Failure distribution | `PARTIAL` | Outcome strings are stored per candidate. The run’s `outcome_counts` are the certification engine histogram, which did not include these denials. |

The run also stores `target_cycles`, threshold snapshot, per-cycle `validation_ids`, `stage_p95_ms`, and `infra_health`. `validation_ids` link to paper-validation evidence ids when the engine records them. They are not the 180 `flarb:` bundle ids.

A run-level ledger aggregate can be built by a read of three collections. It cannot be read back as one stored document today.

---

## 13. Frontend / export capability audit

| Surface | What exists | Relation to this population |
|---|---|---|
| 1. Opportunity Explorer | `OpportunitiesPage` calls `GET /api/arbicore/opportunities`. The handler reads `arbicore_opportunities` only. Filters: `OpportunityType` family, chain, verdict, min confidence. | The 288 denials are not in that collection. The family chip list is `CEX_ARBITRAGE`, `DEX_ARBITRAGE`, `FUNDING_ARBITRAGE`, `CROSS_CHAIN_ARBITRAGE`, `FLASH_LOAN_ARBITRAGE`, `LAUNCH_ARBITRAGE`. It is not the Phase 0 family list. |
| 2. Run Explorer | `ShadowCertificationRun.to_report()` and certification routes expose run status, cycles, and engine totals. `CertificationPanel` in the execution UI shows certification limits. | No page lists the 288, their families, or their decision nets for a `run_id`. |
| 3. Opportunity detail | `GET /api/arbicore/opportunities/{id}` returns the canonical display contract. Reasoning gates are empty unless a canonical row exists. 404 when the id is absent. | A `candidate_id` is not that id. Detail would 404 for these denials. |
| 4. Strategy-family filters | The page filter is scanner `opportunity_type`. | Phase 0 filters are `MISSING`. |
| 5. Economics waterfall | Canonical contract shows `expected_profit_usd` and capital when those canonical fields exist, and leaves missing numbers as null. | It does not render `fees`, `gas`, `mev`, or the Gate 7 sentence from an m2.3 bundle. |
| 6. Route / price path | No UI reads `quotes.hop_legs`. | `MISSING` for this population. |
| 7. Timeline | `GET /api/arbicore/opportunities/{id}/timeline` joins canonical state, journal events, execution plans, and `evidence_bundles` **by `opportunity_id`**, plus a few global audits. | Denied bundles have null `opportunity_id`, so this join does not find them. The tap sorts `evidence_bundles` on `signed_at`, which the m2.3 denial document does not use as its primary timestamp (`created_at` is the one it sets). |
| Excel | `permanent_ledger.export_xlsx` / `export_csv` and `GET /api/execution/permanent-ledger/export`. Columns are cycle capital, portal price, fees, and ROI for the institutional cycle ledger. A second CSV export exists on the modeled execution ledger. | Export machinery exists. The workbook is not a flash-loan opportunity export. Excel remains an export surface. It is not the canonical store. |

The detail payload names a download path `/api/arbicore/opportunities/{id}/evidence`. That string is written into the JSON. A matching route was not found in `server.py`. The UI must not treat that path as a working evidence download.

Approve and reject on the Opportunities page post to the canonical FSM. They are operator mutations of canonical rows. They are out of scope for a read-only ledger and they do not apply to these denials.

---

## 14. Learning-engine integration audit

What can already consume a structured record:

| Piece | Behaviour | Fit for a flash-loan learning row |
|---|---|---|
| `OpportunityJournal` | One row per `opportunity_id`, events, `learning_label`, `learning_consumed`. | Needs an `opportunity_id` these denials do not have. |
| `LearningLedger.label_entry` | Maps terminal journal status to `POSITIVE` / `NEGATIVE` / `NEUTRAL` / `PENDING`. SHADOW uses `would_survive` or certification-ok plus policy-allow. | That survival bit is not the Gate-7 decision net. A negative atomic profit would be misread if it were forced through `would_survive`. |
| `calibration_log` | Samples of predicted confidence versus `survived`. | Confidence on the canonical model is a score. Phase 0 confidence is `HIGH` / `MEDIUM` / `LOW`. They are different fields. |
| `CalibrationWorker` | Fits calibration from `calibration_log`. | Observe path. It does not see these 288. |
| `AdaptiveWeightsObserver` | `compute_recommendation` is read-only. `update_weights` is a no-op under the observe mandate. Snapshots go to `adaptive_weight_recommendations`. | Recommendation only. Signals are win-rate metrics, not strategy-family economics. |
| `DataProvenance` | Learning eligibility is `REAL` or `VERIFIED_REAL` only. | Bundle `provenance` is the string `REAL` on 180 rows. That label is not the same object as `CanonicalOpportunity.source_data_quality`. |
| Post-validation `recommendations()` | Advisory tuning text. | Not a per-opportunity feature store. |

A canonical learning record of the shape `features → strategy → economics → outcome → failure reason` is **not stored**. The pieces that exist are:

- features: route and quote fields, `PARTIAL` (section 6)
- strategy: `DERIVABLE`, not stored (section 8)
- economics: `PARTIAL` (section 9)
- outcome: `verified_outcome` `AVAILABLE`
- failure reason: the verifier sentence `AVAILABLE`; the proposed normalized code `MISSING`

The learning engine’s current contract is observe and recommend for canonical journal rows. It does not mutate scanner config, gates, or weights in the adaptive-weight observer. A Phase 0.5 learning row should stay in that posture: write a record, emit no weight change, emit no gate change, emit no execution.

`is_learning_eligible` on the canonical model is false unless provenance is `REAL` or `VERIFIED_REAL`. Denied flash-loan rows never become that model, so they are not in the eligible set today even though the bundle string says `REAL`.

---

## 15. Gaps

1. No persisted Phase 0 observation.
2. No immutable `opportunity_id` for a denied flash-loan evaluation. `candidate_id` is windowed to 60 seconds.
3. Certification `run_id` is not a foreign key on the candidate or the bundle.
4. `diagnostics.audit_run_id` is a scanner-process id, not the certification id.
5. 108 rows have a decision net and a classifiable hint, and no quote path, no fee, no gas, and no gate object.
6. Economics component fields that the assessor computes (MEV penalty percent, true-net percent, gross dollars, DEX-fee dollars, total costs, applied flash-loan fee rate) are not on the bundle.
7. Per-leg price is stored null. Per-leg slippage dollars and fee dollars are absent.
8. Gates 8 and 9 are unevaluated whenever Gate 7 fails first. One denial string cannot be split into `FEES_KILLED` versus `GAS_KILLED`.
9. The proposed normalized reason codes do not exist.
10. The Opportunities UI, timeline, and evidence download do not address this population.
11. The learning journal is not on the denial path.
12. The Phase 0 package is in the certified image and absent from this worktree.
13. Calculator version and verifier id are not stored on the denial bundle.
14. RPC endpoint identity must stay out of any ledger document.

---

## 16. Reusable components

| Component | Reuse |
|---|---|
| `DiscoveryCandidate` and `arbicore_discovery_candidates` | Identity, discovery time, chain, hint route, outcome text. |
| m2.3 `_build_evidence_bundle` | Route, hop legs, fees, gas, MEV label, gates, block, diagnostics, `broadcast=false`. |
| `observe_strategy_intelligence` | The only strategy writer the ledger may call. Version `phase0.strategy_intelligence.v1`. |
| `observe_economics` | Read-only economics envelope. Preserves null. Does not recompute. |
| `VerifiedOutcome` and Gate 7/8/9 reason sentences | Failure text. Stored as written. |
| `ShadowCertificationRun` | Run id, start, end, status, cycles. |
| `candidate_id` join | `source_model_id`. |
| `OpportunityJournal` event list | Pattern for a timeline. Not the store for these 288 until an id policy exists. |
| `AdaptiveWeightsObserver` observe mandate | Pattern for recommendation without mutation. |
| `permanent_ledger` xlsx/csv response | Pattern for a later export endpoint. Not the schema. |
| `OpportunitiesPage` filter-and-table shell | Pattern for a later explorer. Data source would be the ledger, not `arbicore_opportunities`. |
| Timeline joiner in `v2_opportunity_timeline` | Pattern for a read-only join. The join key would be `candidate_id` / `source_model_id`, not `opportunity_id`. |

---

## 17. Components that must be added

These are absent. Naming them is not an instruction to build them in this step.

| Addition | Why |
|---|---|
| A ledger document or collection whose payload is the Phase 0 observation plus the stored identifiers | Strategy and the economics envelope are in-memory today. |
| An explicit `run_id` link | Time-window joins are how the ranking was built. They are not an identity. |
| A stated opportunity key policy | Either adopt `candidate_id` as the ledger key and record its 60-second scope, or introduce a new id. Reusing a fresh UUID that is not already on the row would create a second identity. |
| Persistence of `classifier_version` with the observation | So a later classifier cannot be confused with this one. |
| A read model for candidate, bundle, and observation | The canonical opportunity API does not serve denials. |
| Optional later: normalized reason codes | Only after a written map from existing sentences. Not in Phase 0.5’s first slice. |
| Optional later: Excel workbook | Export of the ledger. Not the store. |
| Optional later: learning-sample writer | One row per ledger key, observe-only, no weight apply. |

No new scanner, verifier, gate, quote provider, or execution path belongs in this list.

---

## 18. Recommended minimal Phase 0.5 implementation

This is a recommendation for a later change. It is not authorized by this audit.

1. Keep the trading path unchanged. The verifier keeps writing the candidate outcome and the m2.3 bundle exactly as it does now.
2. After those writes, and only as a separate observer, call `observe_strategy_intelligence(bundle, candidate)` and persist that return value. Do not recompute economics. Do not replace a null with zero. Do not call `classify_strategy`.
3. Key the ledger row by `candidate_id`. Store `source_model_id`, `bundle_id` when present, `chain`, `hint_observed_at`, `verified_at`, and `verified_outcome` by copy.
4. Store certification `run_id` only when the row is being attached to a known closed run. Do not infer it from `diagnostics.audit_run_id`.
5. Copy gate status and the existing reason string. Leave Gates 8 and 9 as `NOT_EVALUATED` when that is what the bundle says.
6. Copy `broadcast`. For this population that value is `false`. Do not write `EXECUTED`.
7. Leave the 108 rows as decision-only inside the same ledger: strategy observation from the candidate, decision net from the outcome text, quote and component economics null.
8. Do not add normalized kill codes in the first slice.
9. Do not point the Opportunities page at the ledger until a read API exists. Do not export Excel in the first slice.
10. Learning, if added in the same slice, inserts an observe-only sample. It does not call `update_weights`, does not change gates, and does not approve or reject.

The first slice is complete when a closed run can be re-read as ledger rows whose `primary_family` and decision net match a fresh in-memory Phase 0 call on the same stored inputs.

---

## 19. Safety boundaries

- The ledger is a projection. It does not quote, size, gate, sign, or broadcast.
- `broadcast` stays false unless a future execution layer, separately gated, writes a real execution. SHADOW evidence must remain `NOT` executed.
- Gate floors stay where they are. This window’s floor is `$25`. The ledger records it. It does not change it.
- Phase 0 is the only strategy authority. Hop count, DEX names, pool ids, symbols, and letter-shape stay descriptive fields.
- Missing economics stay null. Stored zero stays zero. `AVAILABLE_NOT_PERSISTED` stays unpersisted until the verifier itself copies the field. The ledger must not run `aggregate_economics` to fill the hole.
- Secrets stay out: RPC URLs, API keys, JWTs, private keys, and secret-bearing connection strings. Provider names and chain names are not secrets. Calldata, if ever shown, is an unsigned plan, not a key.
- The adaptive-weight path stays observe-only. No autonomous mutation of config, weights, or gates.
- Approve and reject on the canonical FSM are not ledger operations.
- Writing the ledger, when a later gate allows it, is an insert of an observation. It is not an update of the candidate’s `verified_outcome` and not an update of the bundle’s economics.

---

## 20. Proposed implementation gates

These gates are a sequence for a future change. None of them is open now.

| Gate | Entry condition | Exit condition | Forbidden inside the gate |
|---|---|---|---|
| 0.5-A Contract | This audit accepted. | A field list restricted to sections 6–11, each marked `AVAILABLE`, `PARTIAL`, `MISSING`, or `DERIVABLE`. | New reason codes, new economics math, UI. |
| 0.5-B Identity | Contract frozen. | Written rule: ledger key is `candidate_id`; `run_id` is copied only from a certification document; `audit_run_id` stays a separate field. | Minting a second id that is not derived from an existing key. |
| 0.5-C Persist observation | Identity rule frozen. Observer version still `phase0.strategy_intelligence.v1`. | One stored observation per ledger key. Re-read matches a fresh observer call. Nulls unchanged. | Verifier edits, gate edits, scanner control, recomputation. |
| 0.5-D Read model | Persisted rows exist for a closed run. | A read API returns the 288 with the ranking’s family counts and decision-net totals. | Excel, learning apply, approve/reject. |
| 0.5-E Timeline view | Read model matches. | Stages in section 7 show only timestamps that exist. `CLASSIFIED` has a time only after 0.5-C stored one. | Backfilled execution events. |
| 0.5-F Export | Read model matches. | Workbook sheets Summary, Opportunities, Price Path, Economics, Strategy Intelligence, Timeline, Learning Dataset, each column sourced from the ledger. Excel is not the store. | New metrics that the ledger does not hold. |
| 0.5-G Learning sample | Observe-only writer. | A sample row points at the ledger key and does not change weights, gates, or config. | `update_weights`, autonomous retune, execution. |
| 0.5-H Reason codes | A separate written map from section 10 sentences, reviewed on stored text. | Normalized codes appear only where the map hits. Unmapped rows stay on the original sentence. | Guessing `GAS_KILLED` from a Gate 7 net. |

Gate 0.5-C is the first gate that would write. It is not approved by this document.

---

## Audit answers

1. **Opportunity persistence.** `DiscoveryCandidate` is the row that exists for all 288. `CanonicalOpportunity` is the platform-wide opportunity and was not created for these denials.
2. **Verifier bundle.** `evidence_bundles` documents with `schema_version=m2.3` and `source_component=flash_loan_arb_verifier`. 180 of 288.
3. **Relationship.** `source_model_id = candidate_id`. Phase 0 reads both in memory and writes nothing. `opportunity_id` is null on denial.
4. **Persisted versus in memory.** Outcome text, route hints, and (on 180) hop quotes, a subset of economics, and gate status are persisted. Phase 0 labels, MEV penalty percent, true-net percent, gross dollars, and applied flash-loan fee rate are in memory only.
5. **Immutable id.** `candidate_id` is reliable inside its 60-second formula and is not a lifetime opportunity id. No other id covers all 288.
6. **Timestamps.** `hint_observed_at` and `verified_at` exist for all 288. Bundle `created_at`, quote block, and diagnostic stamps exist for 180. Classification time and execution time do not.
7. **Route / price path.** Hop tokens, protocol, pool id, wei amounts, fee bps, venue, source, block, and a null price exist on 180. Decision-only rows have hint-level route lists only.
8. **Economics.** Decision net text on all 288. Component dollars and percents on the 180, with the gaps in section 9.
9. **Gate reasons.** Section 10. Normalized kill codes are not canonical.
10. **Provenance.** Section 11. Commit is on the process, not the row. RPC URLs must not be copied.
11. **Run metadata.** The certification document has identity, window, status, and engine counters. It does not contain the 288 or their family distribution.
12. **Frontend.** Opportunities, detail, and timeline serve canonical `opportunity_id`s. They do not display this population or Phase 0 families.
13. **Export.** CSV and xlsx exist for the institutional cycle ledger. There is no opportunity-intelligence workbook.
14. **Learning.** Journal, calibration, and observe-only adaptive weights exist for canonical rows. They do not consume these 288. They must not be given a mutation path.
15. **Genuinely missing.** A persisted observation, a run link, a denial identity that is stable beyond the discovery minute, component fields the assessor does not copy, normalized reason codes, and any UI or export over this spine.

---

## Scope of the classification

`PHASE_0_5_ARCHITECTURE_AUDIT_COMPLETE` means the fifteen questions are answered from the current verifier, discovery model, certification model, journal, learning ledger, Opportunities API, and the Phase 0 observer contract used for the 5 October ranking. The observer package is present in the certified image and absent from this worktree. That is recorded as a gap in section 15. It does not leave the audit unfinished. No ledger was built.
