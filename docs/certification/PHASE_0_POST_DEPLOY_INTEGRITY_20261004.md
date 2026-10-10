# Phase 0 post-deploy integrity — 2026-10-04

- **Classification:** `PHASE_0_POST_DEPLOY_INTEGRITY_PASS`
- **Verified (UTC):** `2026-10-04T16:24:13Z`
- **Scope:** Read-only integrity of the already deployed Phase 0 backend. No deploy, recreate, restart, Mongo write, Network Config write, RPC change, SHADOW start, execution enablement, signing, or broadcast.
- **Secrets policy:** RPC credentials not printed. Alchemy fingerprints are `sha256(<key>)[:8]` of the path segment after `/v2/`.

SHADOW WAS NOT STARTED BY THIS TASK.

---

## 1. Running image and commit

Identity is the image id, `BUILD_INFO`, the version endpoint `git_sha`, and byte comparison with git `823a79b`. The tag was not used alone.

| Field | Observed |
|---|---|
| Container | `arbicore-x-backend-new` |
| Container id | `096bcb87b121e9c56758c51c340b684d299ba9505442be60901540e9d279ea33` |
| PID | `2823992` |
| Image tag | `arbicore-x-backend:phase0-823a79b` |
| Image id | `sha256:768b4410a07843a11ddeda6fde31491cd4108eb00fd559099098627a9adb32a4` |
| Started | `2026-10-04T15:14:34.569825639Z` |
| Status | `running`, health `healthy`, `OOMKilled=false` |
| Restart count | `0` |
| `BUILD_INFO.git_sha` | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |
| `BUILD_INFO.git_tag` | `phase0-823a79b` |
| `BUILD_INFO.build_time` | `2026-10-04T14:58:40Z` |
| `GET /api/arbicore/version` `git_sha` | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` (`generated_at=2026-10-04T16:21:31.731510+00:00`) |
| Process `ARBICORE_GIT_SHA` | `823a79b617ddb1f19397cf5073b9c516aae4e9fd` |

Worktree `/tmp/arbicore-b1b2-reconcile-9ed2718` is clean at `823a79b617ddb1f19397cf5073b9c516aae4e9fd` (`feat: add strategy intelligence and economics observability phase 0`). Parent `62ec7844cdec9517b10a5d40378bd1c5aacc9551`. The commit diff is the five observability modules, `tests/test_phase0_strategy_intelligence.py`, and the Phase 0 implementation note.

Running-container SHA-256 matches that commit for:

| Path | SHA-256 |
|---|---|
| `/app/arbicore/observability/__init__.py` | `588d4ba0474861ea19bfc1bcaf177d4dbc4ba2d0884b628705a04e01f2ad1f00` |
| `/app/arbicore/observability/fields.py` | `5f8c4c6b51b60b9df4331934f0ef080416096acf5e0cdbfc3bfdfd7515fd9095` |
| `/app/arbicore/observability/taxonomy.py` | `d4a16af8611af3f6a31f4f34bfe5e38098df43ab18b502d150b7a9efce7c4189` |
| `/app/arbicore/observability/economics_observation.py` | `2c7961fb66882222a5ba178e8d478cebeafe04abef0f5d519b9bdcffebbf7399` |
| `/app/arbicore/observability/record.py` | `5ddacdb5ef9519a708580dafba33db3d056821d999f7b3a785fd7b3fe03accb7` |

`filter.py`, `verifier.py`, `economics.py`, and `scanner_config_defaults.py` in the container also match `823a79b`, and those git blobs are identical to parent `62ec784`. Gate and verifier code was not changed by this commit.

`ARBICORE_VERSION` and `ARBICORE_BUILD_TIME` in the process environment are still `arbicore-x-cert-baseline-99059c0-20260914-dirty` and `2026-09-14T09:11:11Z`. The version endpoint copies those two fields from the environment. Commit identity is the git SHA above.

---

## 2. Phase 0 modules

Imported inside the running container from `/app/arbicore/observability/__init__.py`:

- `observe_strategy_intelligence`
- `CLASSIFIER_VERSION` = `phase0.strategy_intelligence.v1`

The package import loads `fields.py`, `taxonomy.py`, `economics_observation.py`, and `record.py`. All five files are present and match the commit hashes above.

---

## 3. Real m2.3 observation

`observe_strategy_intelligence(bundle, candidate=None)` was called in the running container on stored `evidence_bundles` rows with `schema_version=m2.3` and `source_component=flash_loan_arb_verifier`. Inputs were not mutated. No document was written.

### 3.1 Complete economics bundle (pre-recreate)

Latest stored economics bundle, `created_at=2026-10-04T15:13:48.698675+00:00` (about one minute before this container started). Arbitrum. Outcome `denied:gate_rejection:gate_7:atomic_profit $-274.39 < floor $25.00`. `broadcast=false`.

| Field | Value |
|---|---|
| Path | `USDC → WETH → WBTC → WETH → USDC` (closed, 3 tokens, 4 hops) |
| Per-leg `dex_protocol` | `uniswap_v3`, `uniswap_v3`, `uniswap_v3`, `sushiswap_v3` |
| `route_dex_protocols` | same four values |
| Protocol source | `quotes.hop_legs[i].dex_protocol` |
| Flash-loan provider | `uniswap_v3`, recorded as not a route protocol |
| `bundle_presence` | `COMPLETE_BUNDLE` |
| `primary_family` | `COMPLEX_TRIANGULAR_CROSS_PROTOCOL` |
| `secondary_tags` | `TRIANGULAR`, `CROSS_POOL`, `CROSS_PROTOCOL` |
| `classification_state` | `COMPLETE` |
| `strategy_completeness` | `FULLY_CLASSIFIED` |
| `confidence` | `MEDIUM` |
| `classifier_version` | `phase0.strategy_intelligence.v1` |
| Economics completeness | `PARTIAL` |
| `atomic_profit_usd` / `true_net_usd` | stored `-274.391866` (not recomputed) |
| `decision_net_usd` | `-274.39`, floor parsed `25.0` |
| `gross_profit_usd` | `null` / `unavailable` |
| `slippage_usd` | `null` / `unavailable` |
| `mev_penalty` | `null` / `AVAILABLE_NOT_PERSISTED` |
| `fees.flash_loan_fee_usd` | stored `30.0`, status `available` |
| `fees.flash_loan_fee_bps` | stored `0`, status `available`, note: quote override coerced with `or 0`, not the applied catalog rate |
| `flash_loan_fee_pct` | `null` / `AVAILABLE_NOT_PERSISTED` |
| `fees.total_slippage_pct` | stored `0.0` stays `0.0` |

Cross-protocol is proven by distinct explicit hop protocols `uniswap_v3` and `sushiswap_v3`. The flash-loan provider name is the same string as a hop protocol and is not counted as a route protocol.

### 3.2 Same protocol, two hops

Optimism bundle `created_at=2026-10-04T15:13:45.791220+00:00`. Path `USDC → WETH → USDC`. Both hops `uniswap_v3`. Provider `balancer_v2`.

| Field | Value |
|---|---|
| `bundle_presence` | `COMPLETE_BUNDLE` |
| `primary_family` | `CROSS_POOL` |
| `secondary_tags` | empty (`CROSS_PROTOCOL` absent) |
| `confidence` | `HIGH` |
| `flash_loan_fee_usd` | stored `0.0` stays `0.0` |
| `flash_loan_fee_bps` | stored `0`, not treated as an applied 0 bps rate |
| `flash_loan_fee_pct` | `null` / `AVAILABLE_NOT_PERSISTED` |
| `total_slippage_pct` | stored `0.0` stays `0.0` |
| `atomic_profit_usd` | stored `-205.196759` |

### 3.3 Post-deploy bundle

Latest bundle at observation, `created_at=2026-10-04T16:22:08.530835+00:00`, written by this container. Base. `denied:venue_unreadable`. `broadcast=false`. No economics block, no fee block, `hop_legs` length 0. Explicit `route_dex_protocols` = `uniswap_v3`, `aerodrome`. Closed path `USDC → WETH → USDC`.

| Field | Value |
|---|---|
| `bundle_presence` | `PARTIAL_BUNDLE` |
| `primary_family` | `DEX_TO_DEX` |
| `secondary_tags` | `CROSS_POOL`, `CROSS_PROTOCOL` |
| `strategy_completeness` | `FULLY_CLASSIFIED` |
| Economics completeness | `PARTIAL` (`gates.gate_7.status` stored `NOT_EVALUATED`; dollar fields `null` / `unavailable`) |
| `flash_loan_fee_bps_stored` | absent (`null`, not a filled zero) |
| `flash_loan_fee_pct` | `null` / `unavailable` because the economics block is absent |

An in-memory copy with `route_dex_protocols` and hop `dex_protocol` removed, still passed as `candidate=None`, became `primary_family=UNCLASSIFIED`, `classification_state=INCOMPLETE`, `strategy_completeness=PARTIALLY_CLASSIFIED`, `confidence=LOW`, `secondary_tags=[]`. Evidence text: cross-protocol was not proven, and venue ids, pool ids, and pool addresses were not parsed as protocols. Provider `balancer_v2` did not assign a family.

Deleting slippage and gas-unit keys on a copy left `slippage_pct` and `gas_units` at `value=null`, status `unavailable`.

`observe_strategy_intelligence(None, None)` returned `NO_BUNDLE`, strategy `UNKNOWN`, economics `UNAVAILABLE`, classifier `phase0.strategy_intelligence.v1`.

---

## 4. Completeness

Observed separately on the calls above:

| Axis | Observed values |
|---|---|
| Bundle | `COMPLETE_BUNDLE`, `PARTIAL_BUNDLE`, `NO_BUNDLE` |
| Strategy | `FULLY_CLASSIFIED`, `PARTIALLY_CLASSIFIED`, `UNKNOWN` |
| Economics | `PARTIAL` on stored m2.3 rows, `UNAVAILABLE` with no bundle |

A normal complete m2.3 row stays economics `PARTIAL` because gross dollars, slippage dollars, applied flash-loan fee percent, and MEV penalty percent are not copied by the writer. Missing fields stay `null`. Stored numeric zero stays zero. Stored `flash_loan_fee_bps` `0` is not reported as an applied 0 bps rate.

Incomplete protocol evidence does not receive a family. The image tests `test_fixture_i_incomplete_evidence_is_not_forced` and `test_different_venues_do_not_prove_cross_protocol` passed.

---

## 5. Gates 7, 8, and 9

Executed in a throwaway `docker run --rm --network none` of image `arbicore-x-backend:phase0-823a79b` (same image id). The live process was not the test process.

Default `FlashLoanGate7AtomicProfit(thresholds={})`:

| Input | `passed` | Reason |
|---|---|---|
| `atomic_profit_usd=24.99` | `False` | `atomic_profit $24.99 < floor $25.00` |
| `atomic_profit_usd=25.00` | `True` | `atomic-profit gate passed` |

Default floor read from the evaluator is `25.0`.

Default `FlashLoanGate8LiquidityDepth(thresholds={})` floor is `100000.0`:

| Input | `passed` |
|---|---|
| `0.0` | `False`, `liquidity_unverifiable=True` |
| `99999.99` | `False` |
| `100000.0` | `True` |

The fail-closed reason for `99999.99` is formatted with `.0f`, so the text reads `$100000 < floor $100000` while `passed` is `False`. The comparison itself uses `>= 100000`. That formatter is in `filter.py`, which is byte-identical to parent `62ec784`.

Default `FlashLoanGate9FlashLoanMev` cap is `MEDIUM`. `LOW` and `MEDIUM` pass. `HIGH` fails: `MEV level HIGH exceeds cap MEDIUM`.

Focused pytest in that same throwaway container, tests mounted read-only from the Phase 0 worktree, `pytest -p no:cacheprovider --noconftest`:

`32 passed in 6.78s`.

Included `test_phase0_strategy_intelligence.py` (22 tests, including `test_gate7_and_gate8_thresholds_unchanged` and `test_real_m23_verifier_bundle_is_observed_not_recomputed`), `test_gate7_floor_is_still_25`, `test_gate8_fails_closed_on_unverifiable_tvl`, Gate 7/8/9 cases in `test_d6_1_economics_and_gates.py`, and `test_gate7_floor_still_25`.

---

## 6. Network Config and RPC

Read-only Mongo `arbicore_x.arbicore_config` `_id=network`. No draft (`arbicore_config_drafts` `_id=network` absent).

| Field | Value |
|---|---|
| Revision | `rev-1068cb9715194f118c99e5f04f9e1bdb` |
| `updated_at` | `2026-10-04T14:24:36.649620+00:00` |
| `updated_by` | `admin` |
| Latest network audit `at` | `2026-10-04T14:24:36.649620+00:00` (string, action `apply`, same revision) |
| Network audit rows with `at >= 2026-10-04T15:14:34` | `0` |

`arbicore_config_audit.at` is a string, so that comparison is valid.

Six chains, each enabled, each with exactly four Alchemy `/v2/` URLs, no public endpoint, no fifth provider. Fingerprints in order on every chain: `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c`.

| Chain | Chain id | Host |
|---|---|---|
| Ethereum | 1 | `eth-mainnet.g.alchemy.com` |
| Optimism | 10 | `opt-mainnet.g.alchemy.com` |
| BNB | 56 | `bnb-mainnet.g.alchemy.com` |
| Polygon | 137 | `polygon-mainnet.g.alchemy.com` |
| Base | 8453 | `base-mainnet.g.alchemy.com` |
| Arbitrum | 42161 | `arb-mainnet.g.alchemy.com` |

---

## 7. Execution, signing, broadcast

| Control | Observed |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `ARBICORE_ENABLE_SIGNING`, `ENABLE_SIGNING` | unset |
| `ARBICORE_ENABLE_BROADCAST`, `ENABLE_BROADCAST` | unset |
| `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` | unset |
| Execution settings | `rev-35aaafa0454f4a2d8c9aa7b750a2c803`, `updated_at=2026-09-07T05:24:08.858259+00:00`, `updated_by=system:boot`, `auto_execute_enabled=false` |
| `flash_loan_arbitrage` | `SHADOW`, `broadcast_allowed=false`, `updated_at=2026-09-07T05:24:07.928883+00:00` |
| Other six strategies | `PAPER`, `broadcast_allowed=false` |
| `execution_mode_audit.at` | string. Rows with `at >= 2026-10-04T15:14:34`: `0` |
| Verifier bundles since container start with `broadcast=true` | `0` |

Boot log (container start, not this task): evidence signing disabled (`SIGNING_ACTIVE_KEY_VERSION` unset); `arbicore_runtime autostart disabled`; T2 constructed `SHADOW, no-broadcast`; canonical flash-loan scanner registered dormant. The log line says `ARBICORE_RUNTIME_AUTOSTART not set` because the code only treats `1` / `true` / `yes` / `on` as enabled and uses that sentence for every other value. The process environment value is `false`.

`ARBICORE_SCANNER_AUTOSTART=true` is the pre-existing flag. The continuous scanner kept writing after recreate. This task did not call start, resume, or a campaign API.

---

## 8. Restart

After the read-only probes, at `2026-10-04T16:24:13Z`:

| Field | Value |
|---|---|
| Restart count | `0` |
| PID | `2823992` |
| Container id | `096bcb87b121e9c56758c51c340b684d299ba9505442be60901540e9d279ea33` |
| Started | `2026-10-04T15:14:34.569825639Z` |

No unexpected restart.

---

## Corrected post-deploy counts

`hint_observed_at` is a float epoch. Comparing it to the string `2026-10-04T15:14:34` returns `0`. That zero is not evidence of no writes.

Deploy instant as a number: `1791126874.569825` (`2026-10-04T15:14:34.569825639Z`).

| Query | Result |
|---|---|
| `arbicore_discovery_candidates.hint_observed_at >= "2026-10-04T15:14:34"` | `0` (invalid string comparison) |
| `hint_observed_at >= 1791126874.569825` | `840` |
| `evidence_bundles` verifier rows with string `created_at >= 2026-10-04T15:14:34.569825639Z` | `193` at `16:22Z` |
| Those rows with `outcome_tag=denied:venue_unreadable` | `194` on the follow-up read |
| Those rows with `economics.atomic_profit_usd` present | `0` |

`created_at` on evidence bundles is an ISO string, so the bundle comparison is valid. The economics rows used in section 3.1 and 3.2 are the latest stored complete bundles and predate this container by about a minute. Since recreate, the verifier rows seen here are `denied:venue_unreadable` partial bundles. The Phase 0 observer is not on the verifier write path.

---

## Result

`PHASE_0_POST_DEPLOY_INTEGRITY_PASS`

SHADOW WAS NOT STARTED BY THIS TASK.

Next gate is a separate task: Phase 1 SHADOW. Do not start it from this certification.
