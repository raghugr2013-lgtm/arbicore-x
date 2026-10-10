# Real 30-minute flash-loan SHADOW — 2026-10-05

**Operational result:** the certified flash-loan scanner was resumed, an iteration increase was observed, one Shadow Certification window was opened and stopped, and the scanner was then killed. SHADOW, detection-only, and broadcast-disabled posture stayed in place. No source file, controller, script, commit, push, deploy, Docker restart, MongoDB configuration change, Network Config change, RPC change, runtime-autostart change, or execution-mode change was made.

The wall clock from `started_at` to `completed_at` is **1815.718 seconds**. The operator stop was aimed at 1800 seconds. The first `POST /api/arbicore/certification/shadow/stop` at `2026-10-05T05:57:54.196Z` returned HTTP 401 because the login cookie had expired. The same stop endpoint, after a fresh login with the existing admin environment variables, completed at `2026-10-05T05:58:04.232Z`. Credentials were not printed.

---

## 1. Window

| | |
|---|---|
| Run id | `shadowcert-5605e7b9-004b-49c7-ab8e-f618caba4065` |
| Start | `2026-10-05T05:27:48.513927+00:00` (`1791178068.513927`) |
| Intended stop | `2026-10-05T05:57:48.513927+00:00` (`1791179868.513927`) |
| `completed_at` | `2026-10-05T05:58:04.231514+00:00` |
| Elapsed | **1815.718 seconds** (15.718 seconds past the 1800-second mark) |
| Status after stop | `ABORTED` (`aborted: real_30min_flash_loan_shadow_complete`) |
| `shadow/current` after stop | `null` |
| Cycles recorded | **91**, all `PASS`, reason `ok_low_volume`, flag `low_volume` |
| First cycle | `2026-10-05T05:27:53.858504+00:00` |
| Last cycle | `2026-10-05T05:57:56.161418+00:00` … `2026-10-05T05:57:56.166863+00:00` |
| Cycle infra | `mongo_ok=true`, `runner_ok=true`, runner exceptions **0** on all 91 |
| Certification-engine opportunities | seen **0**, processed **0**, executable **0** |

`ABORTED` is the operator stop before `target_cycles`. It is not a restart, a signature, or a broadcast.

Counts below use `[2026-10-05T05:27:48.513927Z, 2026-10-05T05:58:04.231514Z)`. Discovery rows with `hint_observed_at` at or after the 1800-second mark: **0**. Verifications in the 15.718-second tail: **21**. Certified-worker bundles in that tail: **12**.

---

## 2. Preflight

`GET /api/arbicore/certification/shadow/current` at `2026-10-05T05:26:23Z` was `current: null`. The same null check was repeated immediately before start.

| Check | Observed |
|---|---|
| Container | `arbicore-x-backend-new` |
| Container id | `096bcb87b121e9c56758c51c340b684d299ba9505442be60901540e9d279ea33` |
| Image | `arbicore-x-backend:phase0-823a79b` |
| Image id | `sha256:768b4410a07843a11ddeda6fde31491cd4108eb00fd559099098627a9adb32a4` |
| Commit | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` (`BUILD_INFO.git_sha` and `GET /api/arbicore/version`) |
| PID | `2823992` |
| Started | `2026-10-04T15:14:34.569825639Z` |
| Restart count | `0` |
| Health | `healthy` |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `flash_loan_arbitrage` mode | `SHADOW`, `broadcast_allowed=false`, row `updated_at=2026-09-07T05:24:07.928883+00:00` |
| Canonical `detection_only` | `true` |
| Canonical `mode` | `SHADOW` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` (readiness `runtime_autostart.attempted=false`) |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| Auto-executor | `running=false`, `total_ticks=0`, `total_actions={}` |
| Signing key | `active_key_version=null`, `keys=[]`, `success_count=0`, `last_signed_at=null` |
| Unsigned reason | `no active signing key configured (SIGNING_ACTIVE_KEY_VERSION unset)` |

Readiness before resume was `is_live_ready=false` with `no_scanners_running` and `paper_runner_zero_processed`. After resume, the start snapshot still had `is_live_ready=false`, with `scanners_running=["flash_loan_arb"]` and the remaining issue `paper_runner_zero_processed`. The start body therefore set `infrastructure_only=true`.

`ARBICORE_SHADOW_CERT_ENABLED=true` and the engine threshold `target_cycles` was 20. The start body set `target_cycles=1000` on this run only so the runner could not auto-finalize inside the window. The runner recorded 91 cycles and did not finalize.

Network Config at preflight and on every authenticated observation: `rev-1068cb9715194f118c99e5f04f9e1bdb`, `updated_at=2026-10-04T14:24:36.649620+00:00`, `updated_by=admin`. All six chains enabled. RPC URL values were not printed.

---

## 3. Resume, iteration proof, stop, kill

| Step | Result |
|---|---|
| `POST /api/arbicore/scanners/flash_loan_arb/resume` | HTTP 200, `enabled=true`, `updated_by=operator_resume`, `updated_at_ts=1791178011.8265805` (`2026-10-05T05:26:51.826581Z`) |
| Status immediately after | Mongo `enabled=true`, canonical cache `enabled=true`, `detection_only=true`, `mode=SHADOW`, iterations still **1** |
| Iteration increase | **1 → 2** at `last_run_at=1791178046.9384048` (`2026-10-05T05:27:26.938405Z`), `last_error=null` |
| Start | HTTP 200, status `RUNNING`, `infrastructure_only=true` |
| Stop | HTTP 200 at `2026-10-05T05:58:04.232Z` after the 401 retry described above |
| `POST /api/arbicore/scanners/flash_loan_arb/kill` | HTTP 200, `enabled=false`, `updated_by=operator_kill`, `updated_at_ts=1791179884.317408` (`2026-10-05T05:58:04.317408Z`) |

Scanner control used only `flash_loan_arb/resume`, `flash_loan_arb/status`, and `flash_loan_arb/kill`.

### In-process flash-loan counters

Quote provider on the canonical object: `live`. Status route label: `operator-provided`. `interval_s=60`. Providers `aave_v3`, `balancer_v2`, `uniswap_v3` enabled. Chains `ethereum`, `arbitrum`, `base`, `optimism`, `polygon`, `bnb` enabled. `last_error` stayed `null`.

| | Before resume | At window open (05:28:15Z) | Last in-window sample (05:56:20Z) | After kill (05:58:33Z and 05:59:48Z) |
|---|---:|---:|---:|---:|
| enabled / cache | false / false | true / true | true / true | **false / false** |
| iterations | 1 | 2 | 10 | **10** (unchanged across 75 seconds) |
| `last_run_at` | `1791176717.201` | `1791178046.938` | `1791179728.218` (`2026-10-05T05:55:28.218Z`) | **same** |
| candidates claimed | 32 | 32 | 288 | 320 |
| verifier denied | 32 | 32 | 288 | 320 |
| verifier confirmed | 0 | 0 | 0 | 0 |
| rows emitted | 0 | 0 | 0 | 0 |
| Gate 7 | 32 | 32 | 288 | 320 |
| Gate 8 | 0 | 0 | 0 | 0 |
| Gate 9 | 0 | 0 | 0 | 0 |
| venue_unreadable | 0 | 0 | 0 | 0 |

The pre-resume `32` is the earlier smoke tick and is outside this window. The counter moved **2 → 10** while the window was open (eight increments). Tick 2 had already incremented at `05:27:26Z`, 21.6 seconds before the window, and its bundles were written inside the window. Claimed/denied/Gate 7 rose by **288** from the pre-resume baseline of 32 to the final 320. That 288 matches the Gate-7 candidate outcomes below.

Post-kill samples at `05:58:33Z` and `05:59:48Z` are identical on iterations, `last_run_at`, claimed, denied, and gates. One full 60-second interval elapsed with the counter frozen.

---

## 4. Who wrote the verifier rows

`arbicore_x` is shared with `arbicore-x-b7-candidate`. That container was not restarted or reconfigured. Two worker ids appear in `evidence_bundles` for this interval.

| Worker | Bundles | What they contain |
|---|---:|---|
| `flash_loan_arb:0eb9228c` | **180** | Certified scanner. Quote status `ok`, exact size, Gate 7 `FAIL`, economics stored, `broadcast=false` |
| `flash_loan_arb:33291a96` | **480** | b7. `route_quote_status` absent, Gate 7 `NOT_EVALUATED`, economics absent. These are the 480 `denied:venue_unreadable` candidate outcomes |

Certified tick ids on those 180 bundles: 2 (22), 3 (16), 4 (16), 5 (24), 6 (18), 7 (22), 8 (22), 9 (20), 10 (20).

The certified in-process `denied_venue_unreadable` counter stayed **0**. The 480 `venue_unreadable` rows are the b7 worker.

---

## 5. Discoveries and six-chain activity

`arbicore_discovery_candidates` with `hint_observed_at` in the window: **33,311**. Every row had `route_pools`. TVL hint `min_tvl_usd >= 100000`: **24,231**. `emitted_opportunity_id` populated: **0**.

Discovery documents do not carry the certified worker id. `claimed_by` was empty on 33,299 rows and `flash_loan_arb:33291a96` on **12**. Empty `claimed_by` is what remains after a claim is cleared, so those 33,299 rows are not stamped to one process. The certified scanner was the process whose iteration counter advanced in this window.

| Chain | Discovered | Verified in window | Certified Gate 7 | b7 venue_unreadable | Certified bundles |
|---|---:|---:|---:|---:|---:|
| Ethereum | 8,586 | 493 | 45 | 448 | 45 |
| Arbitrum | 8,208 | 54 | 54 | 0 | 51 |
| Base | 4,916 | 86 | 54 | 32 | 29 |
| Optimism | 2,808 | 45 | 45 | 0 | 45 |
| Polygon | 6,777 | 45 | 45 | 0 | 10 |
| BNB | 2,016 | 45 | 45 | 0 | 0 |
| **Total** | **33,311** | **768** | **288** | **480** | **180** |

Discovery sources: `flash_loan_route_search` 24,383, `flash_loan_triangular` 7,128, `flash_loan_generic_dex` 1,800.

Discovery providers: `aave_v3` 11,781, `balancer_v2` 11,765, `uniswap_v3` 9,765.

All six chains produced discoveries and all six produced certified Gate-7 outcomes.

---

## 6. Quotes, Gate 7 / 8 / 9, economics

Verified outcomes with `verified_at` in the window: **768**. Of those, **288** are `denied:gate_rejection:gate_7:atomic_profit … < floor $25.00` and **480** are `denied:venue_unreadable` (b7). Gate 8 denials: **0**. Gate 9 denials: **0**. Confirmed outcomes: **0**. `size_not_quoted` log lines: **0**.

The 288 Gate-7 outcomes are the certified counter delta. **180** have a bundle from `flash_loan_arb:0eb9228c`. **108** have the Gate-7 outcome on the candidate and no evidence bundle in a search from `2026-10-05T05:26:00Z` through `2026-10-05T06:02:00Z`:

| Chain | Gate-7 outcomes | Certified bundles | Outcome without a bundle |
|---|---:|---:|---:|
| Ethereum | 45 | 45 | 0 |
| Arbitrum | 54 | 51 | 3 |
| Base | 54 | 29 | 25 |
| Optimism | 45 | 45 | 0 |
| Polygon | 45 | 10 | 35 |
| BNB | 45 | 0 | 45 |
| **Total** | **288** | **180** | **108** |

On the 180 certified bundles:

| Field | Value |
|---|---|
| `verification_status` | `DENIED` on all 180 |
| `broadcast` | `false` on all 180 |
| `quotes.route_quote_status` | `ok` on all 180 |
| `quotes.exact_size` | `true` on all 180 |
| `quotes.size_basis` | `exact` on all 180 |
| `quotes.hop_legs` | present on all 180 |
| Gate 7 | `FAIL` on all 180 |
| Gate 8 | `NOT_EVALUATED` on all 180 |
| Gate 9 | `NOT_EVALUATED` on all 180 |
| `bundle_presence` via the Phase 0 reader | `COMPLETE_BUNDLE` on all 180 |

Atomic profit parsed from the 288 stored Gate-7 outcome strings. All are below zero. None reached $0. None reached the $25 floor.

| Chain | n | Min USD | Max USD |
|---|---:|---:|---:|
| Ethereum | 45 | -1068.05 | -103.04 |
| Arbitrum | 54 | -419.73 | -70.37 |
| Base | 54 | -394.89 | -59.31 |
| Optimism | 45 | -1709.90 | -192.19 |
| Polygon | 45 | -1483.17 | -156.50 |
| BNB | 45 | -439.68 | -146.87 |
| **All** | **288** | **-1709.90** | **-59.31** |

Certified-bundle provider mix: Arbitrum 17/17/17, Ethereum 17/16/12, Optimism 17/16/12, Base 11/7/11, Polygon 4/3/3 for `aave_v3` / `balancer_v2` / `uniswap_v3`. BNB has Gate-7 outcomes and no stored bundle, so it has no stored provider split on a bundle.

---

## 7. Strategy evidence

Phase 0 `observe_strategy_intelligence` (`classifier_version=phase0.strategy_intelligence.v1`) was applied in memory to the 180 certified bundles. No document was written. Stored bundles do not themselves persist `primary_family`. The 108 Gate-7 rows without a bundle, including all 45 BNB rows, have no bundle for that reader.

All 180 classified bundles: `classification_state=COMPLETE`, `strategy_completeness=FULLY_CLASSIFIED`. Confidence `MEDIUM` 137, `HIGH` 43.

| Primary family | Ethereum | Arbitrum | Base | Optimism | Polygon | Total |
|---|---:|---:|---:|---:|---:|---:|
| `TRIANGULAR` | 9 | 27 | 0 | 31 | 6 | 73 |
| `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` | 21 | 24 | 0 | 0 | 0 | 45 |
| `CROSS_POOL` | 0 | 0 | 13 | 14 | 0 | 27 |
| `DEX_TO_DEX` | 0 | 0 | 16 | 0 | 0 | 16 |
| `MULTI_HOP` | 15 | 0 | 0 | 0 | 0 | 15 |
| `CROSS_PROTOCOL` | 0 | 0 | 0 | 0 | 4 | 4 |
| **Total** | **45** | **51** | **29** | **45** | **10** | **180** |

Secondary tags on those 180: `CROSS_POOL` 88; `TRIANGULAR` + `CROSS_POOL` + `CROSS_PROTOCOL` 45; none 27; `CROSS_POOL` + `CROSS_PROTOCOL` 16; `TRIANGULAR` + `CROSS_POOL` 4.

Hop counts on the 180 bundles: 4 hops 99, 2 hops 43, 3 hops 38. Closed three-distinct-token paths: 122. Most frequent stored DEX sequences include four-hop `uniswap_v3` (54), three-hop `uniswap_v3` (34), two-hop `uniswap_v3` (27), and mixed `uniswap_v3` with `sushiswap_v3` (18), `aerodrome_slipstream` (13), `sushiswap_v2`, `camelot_v3`, `aerodrome`, and `quickswap_v3`.

---

## 8. RPC and failover

Backend logs from `2026-10-05T05:27:48Z` to `2026-10-05T05:58:05Z`: **28,589** lines. Tracebacks **0**. Exception lines **0**. `size_not_quoted` **0**. Lines containing `broadcast` **0**.

Lines containing `429`, by hostname only:

| Host | Lines |
|---|---:|
| arb-mainnet.g.alchemy.com | 664 |
| polygon-mainnet.g.alchemy.com | 201 |
| bnb-mainnet.g.alchemy.com | 201 |
| eth-mainnet.g.alchemy.com | 104 |
| opt-mainnet.g.alchemy.com | 23 |
| base-mainnet.g.alchemy.com | 9 |

`failing over` warnings: **433**. Parsed as `eth_getLogs -> 400` on ethereum 108, arbitrum 108, optimism 108, polygon 108, plus one polygon `eth_call -> 429`. The warning names the failing provider slot. It does not print a destination URL. Base and BNB produced no `failing over` line in this slice. Hostname mentions (any line) were present for all six Alchemy mainnet hosts: arbitrum 8,502, polygon 5,177, optimism 4,363, bnb 4,055, ethereum 3,498, base 1,416. Those mention counts are not HTTP 200 counts.

26 lines contain the digits `529`. They were not classified as an HTTP status.

Network Config revision stayed `rev-1068cb9715194f118c99e5f04f9e1bdb` on every authenticated observation through `05:56:20Z` and was not written by this run.

---

## 9. Safety after kill

Re-checked at `2026-10-05T05:58:33Z` and `2026-10-05T05:59:48Z`.

| Check | Result |
|---|---|
| Mongo `enabled` | `false` |
| Canonical cache `enabled` | `false` |
| Iterations | **10**, `last_run_at` frozen at `2026-10-05T05:55:28.218Z` |
| `detection_only` | `true` |
| Canonical mode and execution mode | `SHADOW` |
| `broadcast_allowed` | `false` |
| Auto-executor | `running=false`, actions empty |
| Active signing key | none, `success_count=0`, `last_signed_at=null`, evidence keys `[]` |
| Certified bundles `broadcast` | `false` on all 180 |
| `rows_emitted` / confirmed | 0 / 0 |
| Container PID / restart count / start time | `2823992` / `0` / `2026-10-04T15:14:34.569825639Z` |
| Image and commit | unchanged `phase0-823a79b` / `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| Health | `healthy` |
| Certification window | `current=null` |

The evidence worker object still reports `signer.enabled=true` with `unsigned_reason` equal to no active signing key. No key is registered, no signature succeeded, and `broadcast_allowed` stayed false.

`ARBICORE_RUNTIME_AUTOSTART` and `ARBICORE_AUTOEXEC_AUTOSTART` remained `false`. Execution mode was not changed. Network Config was not applied. RPC configuration was not edited. Docker was not restarted.
