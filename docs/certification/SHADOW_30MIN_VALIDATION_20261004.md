# 30-minute controlled SHADOW validation — 2026-10-04

**Classification: SHADOW_30MIN_PASS**

Observation only. No code, Network Config, RPC, deploy, restart, commit, or push. The window was not extended.

## 1–2. Window

| | |
|---|---|
| Start | `2026-10-04T08:39:49.741564+00:00` (`1791103189.7415638`) |
| End | `2026-10-04T09:09:49.741564+00:00` (`1791104989.7415638`) |
| Duration | **1800 seconds (30.00 minutes)** |

Counts below are the closed interval `[start, end)`. Later scanner ticks are not included.

## 3. Deployment identity

| | Start | At report query (unchanged) |
|---|---|---|
| Container | `27b930baa7c2b8ff07f952036185d7c66e433a463cc9a7849a19fa4312fb5c95` | same |
| Image | `arbicore-x-backend:b1b2-62ec784` | same |
| Image id | `sha256:25dd0905b70e728f333aca170706299f420fc94dc7204dd7ae183df792a687fb` | same |
| SHA | `62ec7844cdec9517b10a5d40378bd1c5aacc9551` | same |
| RestartCount | 0 | 0 |
| Health | healthy | healthy |

## 4. Network Config

`rev-d069f13244ba44da81f97e72f7cfce5b`, `updated_at` `2026-10-03T15:27:57.368745+00:00`. Unchanged at the end of the window.

## 5. Scanner and runtime

Start: enabled, `mode=SHADOW`, `detection_only=true`, iterations 3, claimed 64, denied 64, confirmed 0, venue_unreadable counter 0, Gate-7 counter 64, emitted 0, `last_error` None.

Environment unchanged: `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false`, `ARBICORE_SCANNER_AUTOSTART=true`, borrow sizer and price feed enabled, flash-loan shadow route true. `ARBICORE_PAPER_VALIDATION_ENABLED` was already true and was not changed. Kill switch `engaged=false` at start.

Process counters read after the window (about 09:31Z, so they include post-window ticks and are **not** the 30-minute slice): iterations 16, claimed 480, denied 480, confirmed 0, in-process venue_unreadable 6, Gate-7 counter 474, emitted 0, `last_error` None, still enabled, still SHADOW. The in-process venue_unreadable counter does not match the Mongo slice; the table below uses Mongo.

## 6–12. Per-chain pipeline

Discovery rows are candidates with `hint_observed_at` in the window. Every discovered row carried `route_pools`. TVL-qualified means the hint’s `min_tvl_usd` was at least $100,000 (search-time hint, not a separate Gate-8 denial). Live quotes and exact-size completions are the rows that reached Gate 7. `size_not_quoted` and probe outcomes were zero on every chain, so a Gate-7 row is an exact-size evaluation. There were no Gate-8 denials and no Gate-7 passes.

| Chain | Discovered / routes | TVL hint ≥ $100k | Verified | Live quote → Gate 7 | Exact-size / Gate-7 eval | Gate-7 pass | Gate-7 reject | venue_unreadable | size_not_quoted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ethereum | 7632 | 6480 | 488 | 40 | 40 | 0 | 40 | 448 | 0 |
| Arbitrum | 7296 | 5376 | 48 | 48 | 48 | 0 | 48 | 0 | 0 |
| Base | 4716 | 2472 | 80 | 48 | 48 | 0 | 48 | 32 | 0 |
| Optimism | 2496 | 672 | 40 | 40 | 40 | 0 | 40 | 0 | 0 |
| Polygon | 6024 | 4872 | 40 | 40 | 40 | 0 | 40 | 0 | 0 |
| BNB | 1792 | 1600 | 40 | 40 | 40 | 0 | 40 | 0 | 0 |
| **Total** | **29956** | **21472** | **736** | **256** | **256** | **0** | **256** | **480** | **0** |

Gate-7 rejections are all `denied:gate_rejection:gate_7:atomic_profit $… < floor $25.00`. Sample projected losses: Ethereum about $-110 to $-157, Arbitrum about $-151 to $-431, Base about $-90 to $-381, Optimism about $-210 to $-1691, Polygon about $-217 to $-1441, BNB about $-144 to $-377. No projected profit was at or above $25. No confirmed outcome.

BNB verified subjects were only `aave_v3` (40). Other chains’ verified mix included `aave_v3`, `balancer_v2`, and `uniswap_v3`. Base hints that reached Gate 7 did not carry `borrow_amount_wei` on the stored hint; they still were not `size_not_quoted`.

## 13. venue_unreadable

| Chain | Count | Reading |
|---|---:|---|
| Ethereum | 448 | Recurring during the window. Did not stop Gate 7 (40 evaluations). Not a return of `size_not_quoted`. |
| Base | 32 | Recurring, alongside 48 Gate-7 evaluations. Same class of quote-read denial seen before this window. |
| Polygon | 0 | Historical `venue_unreadable` did not recur. |
| Arbitrum, Optimism, BNB | 0 | Not observed. |

## 14. RPC / provider / failover

Backend logs from `2026-10-04T08:39:49Z` to `2026-10-04T09:09:49Z` (23,834 lines). No tracebacks. No `size_not_quoted` log lines. No broadcast lines.

HTTP 429 on Alchemy hosts:

| Host | 429 | 200 in the same log slice |
|---|---:|---:|
| arb-mainnet.g.alchemy.com | 452 | 6625 |
| opt-mainnet.g.alchemy.com | 307 | 3367 |
| base-mainnet.g.alchemy.com | 96 | 1278 |
| polygon-mainnet.g.alchemy.com | 68 | 3943 |
| eth-mainnet.g.alchemy.com | 45 | 2944 |
| bnb-mainnet.g.alchemy.com | 21 | 3302 |

Also about 80 HTTP 400 responses each on ethereum, polygon, arbitrum, and optimism Alchemy hosts. Quoter logs recorded **348** “failing over” lines; **29** of those also mention HTTP 429. Sampled Base failovers retried `base-mainnet.g.alchemy.com` to the same Alchemy host (`code=-32016`, HTTP 429 rate limited), not a demonstrated switch onto a different public endpoint. About 24 log lines contained `529`.

Alchemy dashboard context supplied for this hour: about 8.1M/30M CU, about 218 CU/s average, about 442 CU/s peak, 300 CU/s plan limit, about 1% throughput-limited, about 97.8% success. That matches the 429s as throughput throttling.

Correlation: Arbitrum had the most 429s and **zero** `venue_unreadable`, and still completed 48 Gate-7 evaluations. Ethereum had only 45 Alchemy 429s but 448 `venue_unreadable`. Base had 96 Alchemy 429s and 32 `venue_unreadable`, plus Gate 7. So Alchemy 429s are real and are classed as provider throttling. They do not, by themselves, explain the Ethereum `venue_unreadable` volume. Those Ethereum denials are a quote/venue read failure in the pipeline, separate from the sizing regression (`size_not_quoted` stayed 0).

## 15. Queue fairness

`claimed_at` is cleared when a row is marked processed, so a claim-time histogram for the window is empty. Fairness is taken from who reached the verifier. Non-`venue_unreadable` evaluations were even: Ethereum 40, Arbitrum 48, Base 48, Optimism 40, Polygon 40, BNB 40. Arbitrum, Optimism, and BNB were not starved. Ethereum’s higher verified total is the 448 `venue_unreadable` rows, not a monopoly of Gate-7 slots.

164 distinct `subject_id` values were verified more than once in the window. Repeat verification was not fully suppressed.

## 16–17. Errors and restarts

`last_error` remained None. No traceback lines in the window logs. RestartCount stayed 0. Container id did not change.

## 18–20. Execution safety

No signer activation. Autoexec stayed false. Runtime autostart stayed false. `emitted_opportunity_id` was null on every row verified in the window (`0` emitted). No profitable SHADOW opportunity (no Gate-7 pass, no confirmed outcome, no projected profit ≥ $25). **No execution was attempted. Nothing was signed or broadcast.**

## Classification

**SHADOW_30MIN_PASS**

Every chain discovered routes, kept a TVL-qualified subset, and completed exact-size Gate-7 evaluations that rejected profit below $25. Ethereum did not regress to `size_not_quoted` or probe-only sizing. Arbitrum, Optimism, and BNB kept verifier access. Polygon `venue_unreadable` did not recur. BNB stayed `aave_v3`. Base `venue_unreadable` did recur (32) without blocking Base Gate 7. Ethereum `venue_unreadable` was large (448) and is not explained only by that chain’s Alchemy 429 count; it is recorded as a quote/venue outcome, not as a sizing or execution failure.
