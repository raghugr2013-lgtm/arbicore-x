# Phase 0.5 — October 5 opportunity ledger projection

**Classification: PHASE_0_5_LEDGER_PROJECTION_PASS**

**Date:** 2026-10-05

Controlled projection of one closed certification run into `arbicore_opportunity_ledger`. The ledger implementation was not changed. No other run was written. No scanner, SHADOW, PAPER, deploy, restart, RPC, Network Config, gate, execution-mode, signing, or broadcast change was made. No commit and no push.

The projector was the certified worktree package `arbicore.opportunity_ledger`, executed once against the production database and then removed from the container filesystem. The running process was not restarted and did not load that package. Phase 0 classification used the image copy of `phase0.strategy_intelligence.v1`.

---

## 1. Source population proof

Certification document `arbicore_shadow_certifications`:

| Field | Value |
|---|---|
| `run_id` | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |
| `status` | `ABORTED` |
| `started_at` | `2026-10-05T05:27:48.513927+00:00` |
| `completed_at` | `2026-10-05T05:58:04.231514+00:00` |

Source query, half-open on the stored window:

`arbicore_discovery_candidates` where `verified_at >= started_at` and `verified_at < completed_at`, and `verified_outcome` contains `gate_7:atomic_profit`.

Bundles joined on `source_model_id = candidate_id`, kept only when `schema_version = m2.3` and `diagnostics.worker_id = flash_loan_arb:0eb9228c`.

This read happened before any ledger write.

## 2. Exact source count

| Check | Result |
|---|---:|
| Gate-7 candidate documents | 288 |
| Distinct `candidate_id` | 288 |
| Unsafe or empty candidate ids | 0 |

## 3. Bundle-backed count

180 candidates had exactly one certified m2.3 bundle. Candidates with more than one such bundle: 0. Bundles for these ids from any other worker or schema: 0.

## 4. Decision-only count

108 candidates had no certified bundle.

## 5. Phase 0 reproduction before write

`observe_strategy_intelligence` (`phase0.strategy_intelligence.v1`) on the 288 source rows, in memory, before insert:

| Check | Result |
|---|---|
| `classification_state=COMPLETE` | 288 |
| `strategy_completeness=FULLY_CLASSIFIED` | 288 |
| Classifier version | `phase0.strategy_intelligence.v1` on 288 |
| Decision nets parsed | 288 |
| Best / mean | `-59.31` / `-345.32131944444467` |
| `>= $0` / `>= $25` | 0 / 0 |

Family counts before write:

| Family | Count |
|---|---:|
| `DEX_TO_DEX` | 17 |
| `CROSS_PROTOCOL` | 8 |
| `CROSS_POOL` | 27 |
| `MULTI_HOP` | 27 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 |
| `MULTI_DEX` | 34 |
| `TRIANGULAR` | 92 |

## 6. Ledger was empty for this run

Before the write, `arbicore_opportunity_ledger` did not exist. Rows for this `run_id`: 0. Rows for any other run: 0.

The write then called `project_opportunity_ledger` for each of the 288, with `mode=SHADOW`, `run_id` set to the certification id, `git_sha=823a79b617ddb1f19397cf5073b9c516aae4e9fd`, and `network_config_revision=rev-1068cb9715194f118c99e5f04f9e1bdb`. `OpportunityLedgerRepo.ensure_indexes` ran once, then `upsert` for each row.

---

## 7. Projection count and idempotency

| Step | Rows with this `run_id` | Rows in the collection |
|---|---:|---:|
| After the first upsert pass | 288 | 288 |
| After the same 288 projections were upserted again | 288 | 288 |
| Distinct `ledger_id` | 288 | |

No second row was created for any source. Every stored `run_id` is `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`. Other runs written: 0.

`opportunity_id` equals `candidate_id` on all 288. Every source bundle had a null `opportunity_id`, so the ledger used the documented fallback. `mode` is `SHADOW` on all 288.

---

## 8. Strategy distribution comparison

Stored ledger `evidence.strategy` versus the certified ranking and the pre-write observer:

| Family | Certified ranking | Ledger |
|---|---:|---:|
| `DEX_TO_DEX` | 17 | 17 |
| `CROSS_PROTOCOL` | 8 | 8 |
| `CROSS_POOL` | 27 | 27 |
| `MULTI_HOP` | 27 | 27 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 83 | 83 |
| `MULTI_DEX` | 34 | 34 |
| `TRIANGULAR` | 92 | 92 |
| **Total** | **288** | **288** |

`classification_state=COMPLETE` on 288. `classification_completeness=FULLY_CLASSIFIED` on 288. `classifier_version=phase0.strategy_intelligence.v1` on 288.

## 9. Economics comparison

| Check | Ledger |
|---|---|
| Decision nets present | 288 |
| Best | `-59.31` |
| Mean | `-345.3213194444445` (half-up `-$345.32`) |
| `>= $0` | 0 |
| `>= $25` | 0 |
| `true_net_usd` equals stored `economics.atomic_profit_usd` on bundle rows | 180 / 180, mismatches 0 |
| `gross_profit_usd` null | 288 (the field is not on the m2.3 bundle) |
| `dex_fee_usd` null | included in the same null check; invented-gross count 0 |
| Stored slippage `0.0` kept as `0.0` | mismatches 0 |
| Stored flash-loan fee `0.0` kept as `0.0` | mismatches 0 |
| Decision-only `notional_usd` and `true_net_usd` | null on all 108; invented-notional count 0 |

The projector did not call the economics assessor. `total_cost_usd` remains null because that total is not a stored field.

## 10. Gate 7 comparison

| Check | Result |
|---|---|
| `final_observed_status` equals the candidate `verified_outcome` | 288 / 288 |
| Bundle `gates.gate_7` copied unchanged (`FAIL` plus the stored reason) | 180 / 180 |
| Bundle Gates 8 and 9 remain the stored `NOT_EVALUATED` objects | included in the gate equality check, mismatches 0 |
| Decision-only Gate 7 status | null on all 108 |
| Decision net on decision-only rows | parsed from the stored Gate-7 sentence, not from a bundle economics object |

Gate mismatch count: 0.

## 11. Route evidence comparison

For each of the 180 bundles, ledger legs were compared with `quotes.hop_legs` and `route.route_pools`: index, token in, token out, protocol (`dex_protocol`), venue (`venue_id`), pool id, input wei, output wei, `fee_bps`, block, and source id. Mismatches: 0.

`quote` and `quote_timestamp` are null on every leg. The stored hop price is null, and no per-leg quote time exists. Those nulls were the expected comparison, not filled values.

Chain on the stored provenance: ethereum 45, arbitrum 54, base 54, optimism 45, polygon 45, bnb 45.

## 12. Run linkage

Every one of the 288 records has:

`run_id = shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065`

Collection total is 288. Records with any other `run_id`: 0.

## 13. Secret-safety verification

Before insert, `secrets_withheld` was false on all 288 projections. After both upserts, stored rows with `secrets_withheld` true: 0.

A walk of every stored string found 0 matches for a URL, a Mongo URI, a private-key banner, or a JWT-shaped token. `rpc_identity` is null. The git SHA and Network Config revision stored on the rows are the hex fingerprint and `rev-` id above, not endpoint URLs.

## 14. Production safety

| Check | Before projection | After projection |
|---|---|---|
| Image | `arbicore-x-backend:phase0-823a79b` | same |
| Container id | `096bcb87b121…d279ea33` | same |
| Started | `2026-10-04T15:14:34.569825639Z` | same |
| PID | `2823992` | same |
| Restart count | `0` | `0` |
| Status | running | running |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` | `SHADOW` |
| Runtime autostart | `false` | `false` |
| Autoexec autostart | `false` | `false` |
| Signing active key | unset | unset |
| Network Config revision | `rev-1068cb9715194f118c99e5f04f9e1bdb` | same |
| Network Config `updated_at` | `2026-10-04T14:24:36.649620+00:00` | same |
| Scanner `enabled` | six rows, all `false` | six rows, all `false` |
| Certification status | `ABORTED` | `ABORTED` |

The only production data change is the new collection `arbicore_opportunity_ledger` with these 288 rows. Source candidates and verifier bundles were not updated.

## 15. Discrepancies

None against the certified population. Source count, bundle split, family counts, best decision net, mean, and the zero counts at `$0` and `$25` match. Idempotency held. No secret-bearing string was stored. Runtime identity and safety flags are unchanged.

---

## Explicit statements

No historical backfill beyond this one run occurred.

No SHADOW, PAPER, or LIVE activity was started. The stored `mode` value `SHADOW` is the ledger label for evidence that already came from that closed run.

The ledger source files in the repository were not modified. Frontend, Excel, and the learning engine were not modified. No commit and no push.

PHASE_0_5_LEDGER_PROJECTION_PASS
