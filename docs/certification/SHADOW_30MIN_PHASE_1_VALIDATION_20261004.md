# Phase 1 controlled 30-minute SHADOW validation — 2026-10-04

**Classification: SHADOW_30MIN_PARTIAL**

One authenticated canonical window was opened on the certified runtime and stopped at 1800 seconds. Phase 0 was not rerun. No code, commit, push, deploy, container recreate, Network Config, RPC, Gate 7/8/9, signing, or broadcast change was made. LIVE was not activated. A second SHADOW window was not started.

Earlier unauthenticated `GET /api/arbicore/certification/shadow/current` responses of HTTP 401 did not open a window and are not counted.

---

## 1. Window

| | |
|---|---|
| Control | `POST /api/arbicore/certification/shadow/start` then `POST /api/arbicore/certification/shadow/stop` |
| Run id | `shadowcert-0a95cbe2-5956-47d2-9ede-e282540bd7f3` |
| Start (window actually RUNNING) | `2026-10-04T17:08:32.861018+00:00` (`1791133712.861018`) |
| Observation end | `2026-10-04T17:38:32.861018+00:00` (`1791135512.861018`) |
| Duration | **1800 seconds** |
| Stop called | `2026-10-04T17:38:32.861309+00:00` |
| Run `completed_at` | `2026-10-04T17:38:34.102091+00:00` |
| Run status after stop | `ABORTED` (`aborted: phase1_shadow_30min_complete`) |
| `shadow/current` after stop | `null` |

Counts below use the closed numeric interval `[1791133712.861018, 1791135512.861018)`. `hint_observed_at` and `verified_at` are floats. Evidence-bundle `created_at` is an ISO string compared on that same interval.

The run record status `ABORTED` is the operator stop before `target_cycles`. It is not a signing, broadcast, or restart event. `target_cycles` was set to 1000 on this run only so the in-process certification ticker could not auto-finalise inside 1800 seconds. It recorded 89 cycles. The first cycle started `2026-10-04T17:08:37.193629+00:00`. The last cycle completed `2026-10-04T17:37:57.436181+00:00`.

Login was `POST http://127.0.0.1:8001/api/auth/login` inside `arbicore-x-backend-new`, using the existing admin environment variables and a cookie jar. Credentials were not printed and were not changed.

Before start, `shadow/current` was null. Readiness was `is_live_ready=false` with issues `no_scanners_running` and `paper_runner_zero_processed` (paper runner enabled and running, `opportunities_processed=0`, `cycles_completed=1353`, canonical opportunities 0). The start API refuses that state unless `infrastructure_only=true`. The window was opened with that flag. Scanner enablement was not changed.

Pre-window figures of 980 candidates / 237 verifications, and the quiet period after `2026-10-04T16:31:57Z`, are diagnostic only and are outside this interval.

---

## 2. Certified runtime

Identity matched before the window was opened and again at the stop.

| Field | Value |
|---|---|
| Container | `arbicore-x-backend-new` |
| Container id | `096bcb87b121e9c56758c51c340b684d299ba9505442be60901540e9d279ea33` |
| Image | `arbicore-x-backend:phase0-823a79b` |
| Image id | `sha256:768b4410a07843a11ddeda6fde31491cd4108eb00fd559099098627a9adb32a4` |
| Commit | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| PID | `2823992` |
| Restart count | `0` |
| Started | `2026-10-04T15:14:34.569825639Z` |
| Health | `healthy` |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |

No unexpected restart.

The certified flash-loan scanner object reported by `GET /api/arbicore/scanners/flash_loan_arb/status` stayed at the zero initial counters for the whole window: `iterations=0`, `candidates_claimed=0`, `verifier_denied=0`, `last_run_at=null`, `last_error=null`. Mongo `arbicore_scanner_state.flash_loan_arb.enabled` stayed `true` (`updated_by=operator_resume`, `updated_at_ts=1791102673.2352312` / `2026-10-04T08:31:13.235231+00:00`). Boot log at `2026-10-04T15:16:07Z` records `FlashLoanArbitrageScanner started` for worker `flash_loan_arb:0eb9228c` with an operator-provided quote provider. Wave1B registration at boot listed `flash_loan_arbitrage` dormant, and readiness `scanners_running` was empty. The tick body did not run on this object.

A separate continuous Base scanner on this same container was running. Its cumulative counters at collection were scans 89, routes evaluated 1068, executable 0, errors 0, `last_error=null`, `last_scan_at=2026-10-04T17:38:18.235961+00:00`. Funnel: real quotes 694, quote failures 374, all `revert_no_pool`, negative economics 694, positive net 0. That scanner is not the six-chain discovery queue.

---

## 3. Who wrote the shared discovery and verifier rows

`arbicore_x` is also mounted by `arbicore-x-b7-candidate` (`arbicore-x-backend:2.9.3-99059c0-b7`, image id `sha256:12800464ac39e1c3e38455fb6b59f54385c94cde7929f1da2e4bf8d4a6ab1912`, commit `99059c0ec19ed4aa00b909d16cb26e2c3c65efdc`, started `2026-09-12T17:22:21Z`, PID `2497265`, restart count 0). That container was not restarted or reconfigured.

Every verifier bundle in the interval has `diagnostics.worker_id=flash_loan_arb:33291a96`. That worker id is the b7 scanner, not `flash_loan_arb:0eb9228c`. Bundle tick ids are 13315 (24), 13316 (32), and 13317 (5). b7 in-process stats at collection: `iterations=13317`, `last_run_at=1791135373.1463006` (`2026-10-04T17:36:13.146301+00:00`), `rows_emitted=0`, `verifier_confirmed=0`. The certified scanner's iterations remained 0, so these rows are not its output.

b7 `last_error` is still a `queue_claim` `ServerSelectionTimeoutError` for `factory-mongo:27017` (name resolution failure). Later ticks still wrote bundles into `arbicore_x`, so that error string was not the only claim outcome during the window.

---

## 4. Network Config, RPC, gates

Unchanged at the end of the window.

| Field | Value |
|---|---|
| Revision | `rev-1068cb9715194f118c99e5f04f9e1bdb` |
| `updated_at` | `2026-10-04T14:24:36.649620+00:00` |
| `updated_by` | `admin` |
| Draft | absent |
| Network audit rows with `at >=` window start | 0 |

Six chains enabled. Each has four Alchemy `/v2/` URLs and no other host. Fingerprints in order on every chain: `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c`.

| Chain | Host |
|---|---|
| Ethereum | `eth-mainnet.g.alchemy.com` |
| Optimism | `opt-mainnet.g.alchemy.com` |
| BNB | `bnb-mainnet.g.alchemy.com` |
| Polygon | `polygon-mainnet.g.alchemy.com` |
| Base | `base-mainnet.g.alchemy.com` |
| Arbitrum | `arb-mainnet.g.alchemy.com` |

Stored flash-loan gate thresholds, read from `arbicore_scanner_config` and from the status payload:

| Gate | Stored value |
|---|---|
| Gate 7 `min_atomic_profit_usd` | `25.0` |
| Gate 8 `min_pool_tvl_usd_in_route` | `100000.0` |
| Route search `min_pool_tvl_usd` | `100000` |
| Gate 9 `max_flash_loan_mev_risk_class` | `MEDIUM` |

---

## 5. Six-chain discovery and verification

Discovery is `arbicore_discovery_candidates` with `hint_observed_at` in the interval. Verification is `verified_at` in the interval. All 280 discoveries and all 61 verifications are Base. Every discovery `hint_source` is `flash_loan_route_search`. Every discovery has `route_pools`. Every discovery `hint_metric.min_tvl_usd` is stored `0.0`, so none meet the $100,000 TVL hint. Top-level `chain` is absent on all 280 discoveries and all 61 verifications (`chain` lives only inside `hint_metric`).

First in-window hint: `2026-10-04T17:20:08.299914+00:00`. Last: `2026-10-04T17:36:13.198797+00:00`. That last timestamp matches b7 `last_run_at`.

| Chain | Discovered | TVL hint ≥ $100k | Verified | Gate 7 pass | Gate 7 reject | Gate 7/8/9 evaluated | venue_unreadable | size_not_quoted | Emitted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ethereum | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Arbitrum | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Base | 280 | 0 | 61 | 0 | 0 | 0 | 61 | 0 | 0 |
| Optimism | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Polygon | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| BNB | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **280** | **0** | **61** | **0** | **0** | **0** | **61** | **0** | **0** |

All 61 verifications are `denied:venue_unreadable`, provider `balancer_v2`, `emitted_opportunity_id` null. No `size_not_quoted`, no `quote_invalid`, no confirmed outcome, no Gate 7/8/9 rejection text.

The 61 `evidence_bundles` rows with `source_component=flash_loan_arb_verifier` and `created_at` in the interval match those verifications: chain Base, `broadcast=false`, `outcome_tag=denied:venue_unreadable`, gates 7, 8, and 9 stored `NOT_EVALUATED`.

Eligible backlog at collection, scanned 130 rows: all `hint_metric.chain=base`, all provider `balancer_v2`, top-level `chain` absent. Other chains were not sitting eligible and skipped.

---

## 6. Phase 0 strategy intelligence and economics

`observe_strategy_intelligence(bundle, candidate=None)` from the certified image (`CLASSIFIER_VERSION=phase0.strategy_intelligence.v1`) was applied read-only to the 61 stored bundles. Inputs were not written back.

| Observer field | Count |
|---|---:|
| `bundle_presence=PARTIAL_BUNDLE` | 61 |
| `strategy_completeness=FULLY_CLASSIFIED` | 61 |
| Economics completeness `PARTIAL` | 61 |
| Economics block present on the stored document | 0 |

Primary family on those partial bundles:

| primary_family | Count |
|---|---:|
| `CROSS_PROTOCOL` | 27 |
| `TRIANGULAR` | 14 |
| `CROSS_POOL` | 12 |
| `DEX_TO_DEX` | 8 |

Secondary tag `CROSS_PROTOCOL` is present on 8 bundles. Sampled bundles have `quotes.hop_legs` length 0, so per-leg `dex_protocol` is absent. Stored `route.route_dex_protocols` is present. Examples of distinct stored route-level names, with flash-loan provider `balancer_v2` not counted as a hop:

| created_at | primary_family | route_dex_protocols | hop dex_protocol |
|---|---|---|---|
| `2026-10-04T17:33:33.498000+00:00` | `DEX_TO_DEX` | `uniswap_v3`, `aerodrome` | none stored |
| `2026-10-04T17:32:14.118641+00:00` | `DEX_TO_DEX` | `uniswap_v3`, `aerodrome_slipstream` | none stored |
| sample triangular | `TRIANGULAR` | `uniswap_v3`, `uniswap_v3`, `uniswap_v3` | none stored |
| sample three-name route | `CROSS_PROTOCOL` | `uniswap_v3`, `uniswap_v3`, `aerodrome` | none stored |

Per-leg cross-protocol is not proven on this window. The observer's `CROSS_PROTOCOL` assignment is from stored `route_dex_protocols` on a partial bundle whose hop list is empty.

Economics were not reconstructed. On the observed bundles every dollar field is `value=null`, `status=unavailable`, because the economics block is absent. That includes `atomic_profit_usd`, `true_net_usd`, `gross_profit_usd`, `slippage_usd`, `flash_loan_fee_usd`, and `mev_penalty`. Gate 7 is stored `NOT_EVALUATED` with reason null, so no floor dollar was parsed from a decision string. No projected profit was available to compare with $25.

---

## 7. RPC, venue, queue

Certified-container logs from `2026-10-04T17:08:32Z` to `2026-10-04T17:38:33Z` (886 lines):

| Host | HTTP 200 | HTTP 429 |
|---|---:|---:|
| `base-mainnet.g.alchemy.com` | 787 | 0 |

No other Alchemy host appears in that slice. Failover lines 0. Tracebacks 0. `size_not_quoted` lines 0. HTTP 529 lines 0. `eth_sendRawTransaction` lines 0.

b7 logs over the same timestamps (926 lines), which is the process that wrote the verifier bundles:

| Host | HTTP 200 | HTTP 429 |
|---|---:|---:|
| `base-mainnet.g.alchemy.com` | 0 | 804 |

b7 failover lines 0. Tracebacks 0. No demonstrated switch onto another host. The Base `venue_unreadable` outcomes line up with b7 HTTP 429 on `base-mainnet.g.alchemy.com`, not with the certified container's HTTP 200s.

Queue at collection:

| Field | Value |
|---|---:|
| Total | 3260338 |
| Unprocessed | 2401257 |
| Claimed in flight | 0 |
| Unclaimed eligible | 133–134 |
| Oldest eligible age | about 187 seconds |

Claims are not stuck. The eligible set is a single untagged bucket and its contents are Base only, so this window does not show other chains being starved by queue order.

Cause of the narrow discovery, from the evidence above:

- Certified flash-loan loop: dormancy. Iterations stayed 0 while Mongo `enabled` stayed true and the task had been started at boot under a different worker id.
- Rows that do exist: produced by b7, Base only, `min_tvl_usd` stored 0.0, then `denied:venue_unreadable`.
- Venue/quote on those rows: b7 Base Alchemy HTTP 429, with no failover line. Not market silence, and not a certified-container 429.
- Queue: eligible work is also Base only. Not starvation of a non-Base backlog.
- Not `size_not_quoted`. Not an exception traceback. Not claim backpressure (`claimed_in_flight=0`).

---

## 8. Safety

| Control | Observed |
|---|---|
| Certified `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_ENABLE_SIGNING`, `ENABLE_SIGNING` | unset |
| `ARBICORE_ENABLE_BROADCAST`, `ENABLE_BROADCAST` | unset |
| `SIGNING_ACTIVE_KEY_VERSION` | unset |
| Execution settings | `rev-35aaafa0454f4a2d8c9aa7b750a2c803`, `auto_execute_enabled=false`, `updated_at=2026-09-07T05:24:08.858259+00:00` |
| `flash_loan_arbitrage` mode | `SHADOW`, `updated_at=2026-09-07T05:24:07.928883+00:00` |
| `broadcast_allowed` | false while mode is `SHADOW` |
| Other six strategies | `PAPER` |
| `execution_mode_audit` since window start | 0 |
| Bundles in the interval with `broadcast=true` | 0 |
| `emitted_opportunity_id` set | 0 |
| `eth_sendRawTransaction` in certified and b7 window logs | 0 |

b7 signing and broadcast environment variables are also unset. Nothing in this window was signed or broadcast. LIVE was not set.

---

## Classification

**SHADOW_30MIN_PARTIAL**

The canonical window is real: 1800 seconds, opened only after `shadow/current` was null, stopped so `shadow/current` is null again. Certified identity, PID, and restart count held. Network Config, RPC fingerprints, and Gate 7/8/9 stored thresholds held. Signing and broadcast stayed off.

The certified phase0 flash-loan scanner did not iterate, so this window does not show that runtime discovering or verifying six chains. The shared-collection Base rows belong to `arbicore-x-b7-candidate`. They stop at `venue_unreadable` under Base HTTP 429, with gates not evaluated and economics dollars unstored. That is a classified venue/RPC outcome on the older writer, plus dormancy of the certified loop. It is not a PASS of the certified six-chain SHADOW path, and it is not a FAIL of runtime identity or execution safety.

---

## Next gate

Do not start Stablecoin or Cross-Protocol work.

The next gate is another Phase 1 SHADOW window only after the certified `phase0-823a79b` process is the one writing discovery and verifier rows, with in-process flash-loan iterations moving, and after shared-mongo writes from `arbicore-x-b7-candidate` are no longer the rows being measured.
