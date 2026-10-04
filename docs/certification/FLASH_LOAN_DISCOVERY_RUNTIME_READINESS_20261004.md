# Flash-Loan Discovery Runtime Readiness — 2026-10-03

- **Classification:** **PIPELINE_WORKING_VERIFICATION_PARTIAL**
- **Checked (UTC):** `2026-10-03T19:34:27Z`
- **Smoke window:** scanner resumed `2026-10-03T19:23:47Z`, evidence read through `2026-10-03T19:34:27Z` (about ten minutes, three scanner iterations). Not an 8h/12h/24h/72h run.
- **Long-duration SHADOW campaign:** not started. `arbicore_shadow_certifications` with `status=RUNNING` is **0**.

Discovery is operational on all six certified networks. Live quoting, exact-size sizing, and the $25 profitability gate were demonstrated on Base. The other five chains produced measured routes in this window; the verifier batches that completed were still on Base and Ethereum. No candidate was confirmed. No transaction was signed or broadcast.

---

## 1. Deployed commit and image

| Field | Value |
|---|---|
| Deployed commit | `9ed2718b3550066934bd11e99a96503ce75a499f` |
| Commit subject | `fix(flash-loan): accept a missing BNB chain key and scope providers` |
| Image tag | `arbicore-x-backend:flash-discovery-readiness-9ed2718` |
| Image digest | `sha256:92a51023b75675f5be2d584345c6b3b7d2de44f66c659d4c291051879d842cfb` |
| BUILD_INFO | `git_sha=9ed2718b3550066934bd11e99a96503ce75a499f`, `git_tag=flash-discovery-readiness-9ed2718`, `build_time=2026-10-03T19:09:14Z` |
| Container | `arbicore-x-backend-new` |
| Started | `2026-10-03T19:19:43Z` |
| Health at `19:34:27Z` | healthy |
| RestartCount | 0 |
| Previous image | `arbicore-x-backend:27dfab4-20261003` (`sha256:77f0bb536f7f02ca18d18dadb16985aac34e980de5f6de540aaf660a0e7ca2bb`), still present, not retagged |

Phase 1, before the recreate: all five remediation commits were ancestors of checkout HEAD `ab2d6d5b8fc92b6deb47469152497a98d0245fcb`, and `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` is an ancestor of `9ed2718`. The only commit after `9ed2718` on this branch is the docs commit `ab2d6d5`. The image was built from a clean worktree of `9ed2718`, not from that docs tip and not from the dirty working tree. `app/backend/arbicore/execution/quoter.py` inside the image matches the clean tree (`sha256:1b3b683f216f79a10d9d9f17e3dec509bd16438a7062b78d111149d25c76202c`).

Remediation commits contained in the deployed commit:

| Commit | Subject |
|---|---|
| `cb79ef17ad52b8458babeb074adf38c6f0873da3` | mirror persisted scanner enabled state into the runtime cache |
| `df12c3dfb21630d98f7c8a70334a2d22787e0f86` | propagate measured pool TVL before the $100k floor |
| `4b25cc3b829b67b2590bc0d7169c7a3ea1e772bb` | plan hops on the quoters already registered |
| `1241e6ca23a9dc875aa19e1e5c4f36cdb12bc5e9` | pick triangular legs from quotable pools |
| `9ed2718b3550066934bd11e99a96503ce75a499f` | accept a missing BNB chain key and scope providers |

The running container before this deploy was still `arbicore-x-backend:27dfab4-20261003`, healthy, `RestartCount=0`, started `2026-10-03T12:42:03Z`.

Rollback images were not retagged:

| Tag | Digest |
|---|---|
| `arbicore-x-backend:g5.79-green-20260927` | `sha256:aaadc3a9cc78d695a9e7e2d16681babc71c576033ad3764061a918946d8e993a` |
| `arbicore-x-backend:ws-a-befb14e-20261002` | `sha256:12759b11a783619ad25746a030c5bbcc71b83ed64ff05b3316153d6402a594ae` |

---

## 2. Configuration changes made

Scanner config was written through the existing flash-loan API (`arbicore_scanner_config` / `arbicore_scanner_state`). Env flags were added only on the Phase 4 recreate, in a compose override, without editing RPC URLs in `deployment/upgrade/backend/.env`.

| Setting | Before | After |
|---|---|---|
| Scanner state `flash_loan_arb.enabled` | false | **true** (resume at `19:23:47Z`, actor `operator_resume`) |
| Config document `enabled` boolean | false | false (the patch API does not write this field; the tick reads scanner state, which is true) |
| `providers.aave_v3.enabled` | false | **true** |
| `providers.balancer_v2.enabled` | false | **true** |
| `providers.uniswap_v3.enabled` | false | **true** |
| `chains.ethereum/arbitrum/base/optimism/polygon` | true | true (unchanged) |
| `chains.bnb` | key absent | **enabled true**, chain id 56, no RPC URL stored |
| `route_search.min_pool_tvl_usd` | 100000 | 100000 |
| `gate_thresholds.default.min_atomic_profit_usd` | 25 | 25 |
| `gate_thresholds.default.min_pool_tvl_usd_in_route` | 100000 | 100000 |
| `ARBICORE_BORROW_SIZER_ENABLED` | unset | **true** |
| `ARBICORE_PRICE_FEED_ENABLED` | unset | **true** |
| `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` | unset | **true** |
| `ARBICORE_USD_NUMERAIRE` | USDC | USDC (unchanged) |
| `ARBICORE_EXECUTION_MODE` | SHADOW | SHADOW |
| `ARBICORE_AUTOEXEC_AUTOSTART` | false | false |
| `ARBICORE_RUNTIME_AUTOSTART` | false | false |
| `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` | unset | unset |
| `execution_mode_state.flash_loan_arbitrage` | SHADOW (`2026-09-07`) | SHADOW, same timestamp |
| `execution_settings.auto_execute_enabled` | false | false |

Startup log after recreate: route engine rebuilt with `max_hops=4`, `min_pool_tvl_usd=100000.0`, `candidate_cap=64`. Quote provider `live`. Price source `onchain_usd_feed_m2_5`. `shadow_route` wired because the env flag is on. The shadow sink builds `OpportunityPipeline` with no broadcaster and no mode repo, so a confirmed candidate would record SHADOW and cannot broadcast.

`ARBICORE_PAPER_VALIDATION_ENABLED=true` was already in the backend env file and was not changed. No strategy was moved to PAPER or LIVE. No PAPER campaign was started.

---

## 3. Six-chain runtime status

Smoke end state: scanner enabled, `iterations=3`, `verifier_confirmed=0`, `verifier_denied=64`, `candidates_claimed=64`, `rows_emitted=0`, `last_error=null`. Container healthy, restart count 0.

| Chain | RPC after env_sync | Route-search candidates | Non-zero route-search TVL | Triangular candidates | Verifier in this window |
|---|---|---:|---|---:|---|
| Ethereum | Alchemy, 820 calls | 1,554 | yes, min $131,074, max $46,895,249 | 288 | 32 bundles, all `venue_unreadable` |
| Arbitrum | Alchemy, 1,749 calls | 1,278 | yes, min $106,065, max $7,929,001 | 480 | not reached |
| Base | Alchemy, 615 calls | 636 | yes, min $772,913, max $8,772,873 | **0** | 59 bundles: 42 quoted and failed Gate 7, 17 `venue_unreadable` |
| Optimism | Alchemy, 771 calls | 108 | yes, min $113,321, max $275,942 | 480 | not reached |
| Polygon | Alchemy, 891 calls | 1,158 | yes, min $107,250, max $429,648 | 288 | not reached |
| BNB Chain | Alchemy, 587 calls | 384 | yes, min $131,078, max $5,223,714 | 48 | not reached |

New discovery candidates with ObjectIds at or after resume: **7,054**. Counts above are those rows. Generic-DEX 2-hop rows are included in the candidate total and are not repeated in the route-search column.

Call counts are `POST` lines in the container log after `19:20:00Z`. They show the process reached each chain's Alchemy host. They are not a CU bill.

---

## 4. Provider availability by chain

Catalog `supports_chains` was not edited. Enabled providers were Aave V3, Balancer V2, and Uniswap V3. Pairing is whatever `providers_for_chain` already does.

| Chain | Aave V3 | Balancer V2 | Uniswap V3 flash | Observed on new candidates |
|---|---|---|---|---|
| Ethereum | catalog yes | catalog yes | catalog yes | all three |
| Arbitrum | catalog yes | catalog yes | catalog yes | all three |
| Base | catalog yes | catalog yes | catalog yes | all three |
| Optimism | catalog yes | catalog yes | catalog yes | all three |
| Polygon | catalog yes | catalog yes | catalog yes | all three |
| BNB Chain | catalog yes | catalog **no** | catalog **no** | **Aave V3 only** (0 non-Aave rows) |

Morpho Blue stays unwired. It was not enabled.

---

## 5. TVL measurements observed

Route search stored a positive `min_tvl_usd` on every new route-search and generic-DEX candidate. The lowest route-search minimum on each chain is above $100,000 (section 3). Examples from the same rows: Ethereum WETH cycle `min_tvl_usd` **$24,774,094.71**; Base generic-DEX up to **$8,772,872.52**; BNB route-search up to **$5,223,714.48**.

A quoted Base hop carried `depth_usd` **$9,918,783.52** with quoter status `ok` (section 7). That is a measured depth on a route that had already passed the search floor.

Triangular candidates are a different source. Several of them have `min_tvl_usd` of 0 or only a few dollars (Ethereum sample `$0.01`, Arbitrum `$0`, BNB `$0`, Polygon sample `$5.44`). Optimism triangular rows reached a max of `$237,406.37` and also include sub-$100k rows. That source does not apply `min_pool_tvl_usd` before emit. The $100,000 floor on route search was not lowered.

---

## 6. Route-generation evidence

`flash_loan_route_search` emitted 2-hop, 3-hop, and 4-hop cycles on all six chains. `flash_loan_generic_dex` emitted 2-hop cycles on all six. Explored-count on an Ethereum sample was `route_search_candidates_explored=138`.

DEX mix actually chosen on route-search rows (sample of 4,000):

| Chain | DEX sets present |
|---|---|
| Ethereum | UniV3; UniV3+Sushi V2 |
| Arbitrum | UniV3; UniV3+Camelot V3; UniV3+Sushi V3; all three |
| Base | UniV3; UniV3+Aerodrome; UniV3+Aerodrome Slipstream; Aerodrome; Aerodrome+Slipstream; all three |
| Optimism | UniV3 |
| Polygon | UniV3; UniV3+QuickSwap V3 |
| BNB | Pancake V3; UniV3; Pancake V3+UniV3 |

---

## 7. DEX / quoter evidence

Persisted verifier bundles since `2026-10-03T19:24:00Z`: **91** (`source_component=flash_loan_arb_verifier`).

| Result | Count | What it shows |
|---|---:|---|
| Base, route quote `ok`, then Gate 7 fail | 42 | UniV3 quoter returned amounts. One hop: `source_id=uniswap_v3_quoter_base`, `dex_protocol=uniswap_v3`, `status=ok`, `block_number=52133244`, `fee_bps=5`, `amount_in_wei=3730003528945148928`, `amount_out_wei=9999082691`, `depth_usd=9918783.52`. The route also included Aerodrome pool `0xcDAC0d6c6C59727a65F871236188350531885C43`. |
| Base, `denied:venue_unreadable` | 17 | Quote facts were not produced. Gates not evaluated. |
| Ethereum, `denied:venue_unreadable` | 32 | Same fail-closed outcome. `flash_loan_provider=aave_v3`, route-search, USDC. No `route_quote_status=ok`. |
| Arbitrum, Optimism, Polygon, BNB | 0 bundles | Discovery rows exist. This window's claim batches had not verified them. |

All 42 successful quotes were Base routes labeled `balancer_v2` as the flash provider. `broadcast` is false on every bundle.

---

## 8. Triangular-route evidence

`flash_loan_triangular` rows, 3 hops, path shape `DAI → WETH → … → DAI` except BNB `DAI → WETH → USDT → DAI`.

| Chain | Rows | DEX chosen on the sampled cycle | Sample `min_tvl_usd` |
|---|---:|---|---:|
| Ethereum | 288 | `sushiswap_v2` on every leg | 0.0108 |
| Arbitrum | 480 | `camelot_v3` on every leg | 0 |
| Base | **0** | none emitted | — |
| Optimism | 480 | `uniswap_v3` on every leg | 98.73 (source max in the group was $237,406.37) |
| Polygon | 288 | `quickswap_v3` on every leg | 5.44 |
| BNB | 48 | `pancakeswap_v3` on every leg | 0 |

Base route-search did emit 3-hop cycles, including Aerodrome. The triangular source itself emitted none on Base in this window. Those triangular rows were not in the verifier batches, so they were not quoted.

---

## 9. Candidate-generation evidence

7,054 new `FLASH_LOAN_ARBITRAGE` discovery candidates after resume. By chain: Ethereum 1,908, Arbitrum 1,824, Polygon 1,506, Base 744, Optimism 624, BNB 448. Sources: route search, generic DEX, and triangular (Base triangular 0). None of the new ObjectIds were marked verified during the window; the verifier was still draining earlier queue rows and the Base/Ethereum slice of this run. In-memory stats: `candidates_claimed=64`, `rows_emitted=0`, `verifier_confirmed=0`.

No confirmed opportunity was required, and none appeared.

---

## 10. Exact-size borrow-sizing evidence

On the 42 Base quotes with `route_quote_status=ok`, the persisted quote record contains `"size_basis": "exact"` and `"exact_size": true`. One of those records has `quoted_amount_in_wei=10000000000` (10,000 USDC at 6 decimals, the configured `default_notional_usd`). Discovery-time `borrow_amount_provenance` on non-Base candidates remains `deterministic_probe`. That probe label is written at candidate build. The verifier rejects `size_basis=probe` as `DENIED_SIZE_NOT_QUOTED` before Gate 7. These 42 Base rows passed that check and were judged on profit instead.

No exact-size quote was persisted for Ethereum, Arbitrum, Optimism, Polygon, or BNB in this window. The wired sizer is the existing Base price feed (`MultichainPriceSource` with only `base`). Non-Base exact size was not demonstrated. It was not extended.

---

## 11. Profitability-gate evidence

Gate 7 floor is still **$25**. It was not lowered. All 42 quoted Base routes failed it. Recorded reasons include `atomic_profit $-112.98 < floor $25.00` and larger losses (about `-$60` to `-$6,714`). Gate 8 and Gate 9 on those bundles are `NOT_EVALUATED` because Gate 7 already failed. `min_pool_tvl_usd_in_route` remains `100000`. Route-search minima in section 3 are all above that floor. In-memory `gate_rejections.gate_7_atomic_profit` was 64 at `19:34Z`; the persisted bundles account for 42 Gate 7 fails plus 49 venue-unreadable denials. Confirmed count is 0.

---

## 12. Remaining blockers

1. **Verifier coverage is Base-heavy.** Arbitrum, Optimism, Polygon, and BNB have discovery, TVL, and routes, and no verifier bundle yet. Ethereum reached the verifier and failed closed as `venue_unreadable` (32), with no successful quote. A short claim batch (64 claimed across 3 iterations) cannot drain a multi-million historical `arbicore_discovery_candidates` queue plus 7,054 new rows.
2. **Exact-size evidence is Base-only.** The existing sizer is bound to the Base USD feed. Non-Base discovery rows are still tagged `deterministic_probe` at build time.
3. **Base triangular source emitted 0.** Base route-search cycles, including Aerodrome, did emit.
4. **No profitable candidate.** Every successful quote lost money against the $25 floor. That is market outcome, not a disabled gate.
5. **Startup bootstrap RPC.** In the seconds before `env_sync` (`19:19:54Z`–`19:19:55Z`) the process issued **34** `POST`s to `mainnet.base.org`, all HTTP 429. After `19:20:00Z` the log shows only the six Alchemy hosts. Applied Network Config was not edited. The existing env file still has that Base bootstrap URL; this gate did not change it.
6. **Encrypted signer material remains in `arbicore_secrets`** (`scope=evm_sign`, `algorithm=eth_privkey`, derived address `0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89`). It was not used. See section 14.
7. **Other strategies stay at their seeded PAPER rows.** Their scanners are `enabled=false`. They were not promoted and were not part of this smoke.

---

## 13. RPC / Network Config confirmation

Applied Network Config was not saved or applied by this gate.

| Check | Result |
|---|---|
| Revision | `rev-d069f13244ba44da81f97e72f7cfce5b` |
| `updated_at` | `2026-10-03T15:27:57.368745+00:00` |
| `updated_by` | `admin` |
| Chains enabled | ethereum, arbitrum, base, optimism, polygon, bnb |
| Order | Alchemy A fingerprint `cd505118`, then Alchemy B fingerprint `124bc59c`, on all six |
| Hosts | `eth-mainnet`, `arb-mainnet`, `base-mainnet`, `opt-mainnet`, `polygon-mainnet`, `bnb-mainnet` (all `g.alchemy.com`) |
| `ce00e63d` | absent from applied `rpc_urls` |
| Public RPC in the applied document | none |
| `env_sync` on the new process | `exported 19 var(s)` for `base,ethereum,arbitrum,optimism,polygon,bnb` at `19:19:55Z` |

---

## 14. Signer / broadcast safety confirmation

| Check | Result |
|---|---|
| `flash_loan_arbitrage` mode | SHADOW, unchanged since `2026-09-07T05:24:07Z` |
| Any strategy in `LIMITED_LIVE` or `FULL_LIVE` | none |
| `auto_execute_enabled` | false |
| `ARBICORE_AUTOEXEC_AUTOSTART` | false |
| `ARBICORE_RUNTIME_AUTOSTART` | false |
| Private-key env vars (`PRIVATE_KEY`, `MNEMONIC`) | absent |
| AutoExecutor start log | none |
| `eth_sendRawTransaction` / `broadcast_sent` / `shadow/start` since recreate | **0** |
| Evidence `broadcast` | false on all 91 bundles |
| `execution_plans` | 0 |
| Pipeline broadcast modes | `LIMITED_LIVE` and `FULL_LIVE` only. SHADOW and PAPER return at the shadow-record branch |
| Flash-loan shadow sink | no broadcaster wired |

The vault still holds an encrypted executor key. Signing it requires a live mode this process does not have, and auto-execute is off. This gate did not call the signer and did not broadcast.

PAPER and LIVE were not enabled. The pre-existing seeded PAPER rows for non-flash strategies were left as they were, with those scanners disabled.

---

## 15. Long-duration SHADOW run

Not started.

`arbicore_shadow_certifications` `status=RUNNING` is **0**. `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` is unset. The scanner is left **enabled** so discovery can keep ticking for controlled observation. That is not an 8h, 12h, 24h, or 72h SHADOW certification campaign. This procedure stops here.

---

## Boundaries held

Network Config and the Alchemy A→B topology were not changed. The $100,000 TVL floor and the $25 atomic-profit floor were not lowered. No risk gate was removed. PAPER and LIVE were not enabled. Nothing was signed or broadcast. Curve, Velodrome, Morpho, a dedicated stablecoin or LST/LRT scanner, a cross-chain scanner, and a capital DEX scanner were not added. Completed remediation code was not redesigned. The long-duration SHADOW phase was not started.
