# New Alchemy A→B→C→D RPC Rotation — 2026-10-04

- **Classification:** **RPC_ABCD_ROTATION_PASS**
- **Code changes:** none
- **Applied (UTC):** `2026-10-04T14:24:36.649620+00:00`
- **Re-read (UTC):** `2026-10-04T14:38:23Z` — live document is still this four-endpoint revision. Pending draft is null. No second APPLY.
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:b1b2-62ec784` · compose image `sha256:36601f3423d24569abb468d61623f136a27ec7e69226877133485de297e7ca1b` · `ARBICORE_GIT_SHA` `62ec7844cdec9517b10a5d40378bd1c5aacc9551` · image label `arbicore.gitsha` `2a6fadb8a43b750130cbe5dceee831718c5e51c9` · StartedAt `2026-10-04T08:28:21.865915247Z` · Pid `1698122` · RestartCount `0` (unchanged) · Status `running` · health `healthy`
- **Old revision:** `rev-d069f13244ba44da81f97e72f7cfce5b` (`updated_at` `2026-10-03T15:27:57.368745+00:00`, `updated_by` `admin`)
- **New revision:** `rev-1068cb9715194f118c99e5f04f9e1bdb` (`updated_by` `admin`)
- **Fingerprints:** A `dc432a6b` · B `6e67e161` · C `cd505118` · D `124bc59c`
- **Secrets policy:** Alchemy credentials not printed. Fingerprint = `sha256(<key>)[:8]` of the path segment after `/v2/`. URLs shown as host + `fp=…`. Admin password not printed. Login HTTP 200, role `admin`.

Exactly one APPLY, of the existing pending draft, with no `patch` body. The draft was not rewritten. No rollback, no executor edit, no execution-mode edit, no container restart, no Phase 0 deploy, no SHADOW start, no PAPER start, no RECOMMENDATION start, no LIVE start, no commit.

Phase 0 commit `823a79b617ddb1f19397cf5073b9c516aae4e9fd` was not deployed.

---

## Verdict

**RPC_ABCD_ROTATION_PASS.** All six chains have exactly four Alchemy endpoints applied, in order new A, new B, old A, old B. Chain ids match. The running process hot-reloaded the list into `PROVIDER_RPC_URLS_*` and the provider registry. Restart count stayed 0.

A later re-read of the live Network Config found the same revision and no pending draft. The apply that landed was the operator’s four-endpoint draft, not a two-endpoint configuration. It was not applied again.

The Alchemy dashboard 61.5% series correlates to the low-volume new account `6e67e161` (B). Its misses are the same `eth_getLogs` HTTP 400s that the other three fingerprints return in the same seconds. New A `dc432a6b` is 98.0% HTTP 200 over 2602 calls. That is not an account-level RPC outage, and it was not used to reorder providers.

---

## 1. Topology — four providers are already supported

Inspected the code inside the running image, not only the workspace tree.

| File | sha256 |
|---|---|
| `/app/arbicore/config/persistent.py` | `41c0865cd5b9a40873f98eec2fd01162b801b6d5b96300c16a2ba47e7142ca4c` |
| `/app/arbicore/config/env_sync.py` | `fdb8a6f8d5b57e4913d8f66060238684c1523eaa200a4f8b6c1f59bbe6c58ab8` |
| `/app/arbicore/providers/bootstrap.py` | `c50f29deef2dffe45add2e457b737c04d41376a1742ebf4bbbb84dca3ed0b454` |
| `/app/arbicore/providers/registry.py` | `cd40b5857c7a1bdca702d18521ef3616cef1eef9dfd09b30caf62d8e393b9bde` |
| `/app/arbicore/providers/rpc_failover.py` | `f3ced6823f24d947b3d2b51f94f5611fbfc5dcf3ffa947e05ca5dcc42565d5ca` |
| `/app/arbicore/execution/quoter.py` | `1b3b683f216f79a10d9d9f17e3dec509bd16438a7062b78d111149d25c76202c` |

`SUPPORTED_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")`.

| Capability | Running behavior |
|---|---|
| Count | `rpc_urls[chain]` is a list. Validate checks http(s) scheme and chain name. No length cap of 2. No `[:2]` slice in persistent config, env sync, bootstrap, or the quoter candidate splitter. |
| Priority | Each URL is registered at `priority = 100 + index`. Lower priority number scores higher when health is equal. |
| Health / failure | Per-provider successes, failures, consecutive failures, EWMA latency, status. |
| Cooldown | Circuit breaker: 5 consecutive failures, or failure rate ≥ 0.5 over a window of 20. Open duration 60 seconds. Live `GET /api/arbicore/providers/status` reports threshold 5, rate 0.5, open 60s. |
| Failover | Quoter walks every entry in the chain-scoped CSV. Registry `call()` walks health-sorted candidates. |
| Hot reload | `POST /api/arbicore/settings/network/apply` calls `sync_env_from_network_config`, then `sync_rpc_providers_from_env`. Unchanged URL+id keeps health. Changed URL replaces the provider. Stale `rpc_<chain>_<index>_*` ids are deregistered. |
| Persistence | Mongo current document, draft, and audit snapshot. Apply promotes the draft and clears it. |

This is not a two-provider hard limit. Classification is not `RPC_TOPOLOGY_REQUIRES_CONTROLLED_EXTENSION`. Architecture was not changed.

One property of the existing registry facade, left as-is: `ProviderRegistry.call` and `RegistryRpcProvider` default to `max_attempts = 3`. With all four healthy, one registry call tries A, then B, then C. D is still registered at priority 103. A tripped provider is omitted from the candidate list, so D enters that three-attempt window once an earlier provider is circuit-open. The quoter path does not use that cap; it walks the full CSV. No code change was made to raise the cap.

Explicit `PROVIDER_RPC_URLS_<CHAIN>` is not augmented with a public default. After this apply, those variables hold the four-URL list, so the public fallback in `_rpc_urls` does not run.

---

## 2. Pending draft — used as stored

`GET /api/arbicore/settings/network` before APPLY.

| Field | Observed |
|---|---|
| Draft present | yes |
| `updated_at` | `2026-10-04T14:16:08.381421+00:00` |
| `updated_by` | `operator` |
| `kind` | `network` |
| Chains | ethereum, arbitrum, base, optimism, polygon, bnb |
| Enabled | all six `true` |
| RPC count | 4 per chain, 24 URLs, all `https://*.g.alchemy.com` |
| Order | index 0 `dc432a6b`, 1 `6e67e161`, 2 `cd505118`, 3 `124bc59c` on every chain |
| Public hosts | none |
| Fifth endpoint | none |
| Applied revision still | `rev-d069f13244ba44da81f97e72f7cfce5b` |

The draft already contained every required endpoint. It was not recreated and not saved again.

Non-RPC fields matched the applied document (canonical JSON sha256 prefix):

| Field | Same | Hash prefix |
|---|---|---|
| `executor_addresses` | yes | `1d8b0cb1a6c9` |
| `gas_settings` | yes | `b71af855f4cf` |
| `mev_relay_urls` | yes | `3371cb657b2f` |
| `native_price_usd` | yes | `e6bded1ea6a4` |
| `seeded_from_env` | yes | `b5bea41b6c62` |
| `chains_enabled` | yes | `31532da1eaf4` |

Every `executor_addresses` value was empty. The base executor address was not set. The existing warning was left in place.

Re-read immediately before POST: same draft timestamp, same revision, same four fingerprints, same non-RPC equality.

---

## 3. Validation of all 24 endpoints

Methods: `eth_chainId` and `eth_blockNumber` only, from inside the backend container, against the draft URLs. One HTTP attempt each. No URL or key printed.

Expected chain ids: ethereum 1, arbitrum 42161, base 8453, optimism 10, polygon 137, bnb 56.

| Chain | Slot | Host | fp | HTTP | chain id | block | Pass |
|---|---|---|---|---:|---:|---:|---|
| ethereum | A | `eth-mainnet.g.alchemy.com` | `dc432a6b` | 200 | 1 | 26119559 | yes |
| ethereum | B | `eth-mainnet.g.alchemy.com` | `6e67e161` | 200 | 1 | 26119559 | yes |
| ethereum | C | `eth-mainnet.g.alchemy.com` | `cd505118` | 200 | 1 | 26119559 | yes |
| ethereum | D | `eth-mainnet.g.alchemy.com` | `124bc59c` | 200 | 1 | 26119559 | yes |
| arbitrum | A | `arb-mainnet.g.alchemy.com` | `dc432a6b` | 200 | 42161 | 511637233 | yes |
| arbitrum | B | `arb-mainnet.g.alchemy.com` | `6e67e161` | 200 | 42161 | 511637233 | yes |
| arbitrum | C | `arb-mainnet.g.alchemy.com` | `cd505118` | 200 | 42161 | 511637234 | yes |
| arbitrum | D | `arb-mainnet.g.alchemy.com` | `124bc59c` | 200 | 42161 | 511637234 | yes |
| base | A | `base-mainnet.g.alchemy.com` | `dc432a6b` | 200 | 8453 | 52167204 | yes |
| base | B | `base-mainnet.g.alchemy.com` | `6e67e161` | 200 | 8453 | 52167204 | yes |
| base | C | `base-mainnet.g.alchemy.com` | `cd505118` | 200 | 8453 | 52167204 | yes |
| base | D | `base-mainnet.g.alchemy.com` | `124bc59c` | 200 | 8453 | 52167204 | yes |
| optimism | A | `opt-mainnet.g.alchemy.com` | `dc432a6b` | 200 | 10 | 157762489 | yes |
| optimism | B | `opt-mainnet.g.alchemy.com` | `6e67e161` | 200 | 10 | 157762489 | yes |
| optimism | C | `opt-mainnet.g.alchemy.com` | `cd505118` | 200 | 10 | 157762489 | yes |
| optimism | D | `opt-mainnet.g.alchemy.com` | `124bc59c` | 200 | 10 | 157762489 | yes |
| polygon | A | `polygon-mainnet.g.alchemy.com` | `dc432a6b` | 200 | 137 | 94945737 | yes |
| polygon | B | `polygon-mainnet.g.alchemy.com` | `6e67e161` | 200 | 137 | 94945737 | yes |
| polygon | C | `polygon-mainnet.g.alchemy.com` | `cd505118` | 200 | 137 | 94945737 | yes |
| polygon | D | `polygon-mainnet.g.alchemy.com` | `124bc59c` | 200 | 137 | 94945737 | yes |
| bnb | A | `bnb-mainnet.g.alchemy.com` | `dc432a6b` | 200 | 56 | 125691529 | yes |
| bnb | B | `bnb-mainnet.g.alchemy.com` | `6e67e161` | 200 | 56 | 125691530 | yes |
| bnb | C | `bnb-mainnet.g.alchemy.com` | `cd505118` | 200 | 56 | 125691530 | yes |
| bnb | D | `bnb-mainnet.g.alchemy.com` | `124bc59c` | 200 | 56 | 125691530 | yes |

24/24 passed. Host matched the chain. No public host. Fingerprints matched the required order.

`POST /api/arbicore/settings/network/validate` on the stored draft, twice (probe window and immediately before APPLY):

| Field | Result |
|---|---|
| HTTP | **200** |
| `ok` | **true** |
| `errors` | **[]** |
| `warnings` | `no executor address configured for chain 'base' — LIMITED_LIVE flow will BLOCK` |
| First `generated_at` | `2026-10-04T14:22:34.980334+00:00` |

That warning is the pre-existing base executor warning. It was not treated as a gate failure. No executor address was written.

At `2026-10-04T14:22:05Z`, before these probes, `GET /api/arbicore/rpc/check` returned `status=WAIT` with HTTP 429 against the then-live primary (old A on Base). The direct probes above, including C `cd505118` on Base, returned HTTP 200 and chain id 8453. The 429 did not fail the 24-endpoint gate.

---

## 4. APPLY

Gate before POST: four-provider support present; six chains; exactly four endpoints each; 24/24 chain ids correct; new A/B first; old A/B in slots C/D; no public RPC; no fifth endpoint; non-RPC network fields unchanged.

| Field | Value |
|---|---|
| Endpoint | `POST /api/arbicore/settings/network/apply` |
| Body | `{"reason":"apply certified six-network Alchemy A/B/C/D rotation"}` — no `patch` |
| HTTP | **200** |
| `ok` | **true** |
| `generated_at` | `2026-10-04T14:24:36.717165+00:00` |
| New `revision_id` | `rev-1068cb9715194f118c99e5f04f9e1bdb` |
| `updated_at` | `2026-10-04T14:24:36.649620+00:00` |
| `updated_by` | `admin` |
| Access log | one `POST /api/arbicore/settings/network/apply` 200 in this window |
| Rollback POSTs in this window | 0 |

`env_synced` (19 names, values not returned):

`ARBICORE_RPC_URL`, `ARBICORE_RPC_URL_{ETHEREUM,ARBITRUM,BASE,OPTIMISM,POLYGON,BNB}`, `{ETHEREUM,ARBITRUM,BASE,OPTIMISM,POLYGON,BNB}_RPC_URL`, `PROVIDER_RPC_URLS_{ETHEREUM,ARBITRUM,BASE,OPTIMISM,POLYGON,BNB}`.

No executor-address variable was in `env_synced`.

Log at `2026-10-04 14:24:36,673`:

`env_sync: exported 19 var(s) from persistent network config (chains=base,ethereum,arbitrum,optimism,polygon,bnb)`

No `g5.79 rpc provider sync failed` line. The next log lines registered indices 0–3 for all six chains.

Following `GET /api/arbicore/settings/network`: same revision, draft **null**, same fingerprint matrix. Apply cleared the draft by promoting it.

Latest audit row: action `apply`, revision `rev-1068cb9715194f118c99e5f04f9e1bdb`, actor `admin`, reason `apply certified six-network Alchemy A/B/C/D rotation`, `at=2026-10-04T14:24:36.649620+00:00`. Its `previous` snapshot is the prior six-chain A/B document (2 URLs per chain, base fps `cd505118`, `124bc59c`). Its `next` snapshot is 4 URLs per chain, base fps `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c`. Older audit rows were not deleted. `ce00e63d` remains only inside the historical `2026-10-03T04:57:17Z` row, not in this revision.

Applied matrix (every chain, index 0→3):

| Chain | Chain ID | Enabled | Host | A | B | C | D |
|---|---:|---|---|---|---|---|---|
| ethereum | 1 | true | `eth-mainnet.g.alchemy.com` | `dc432a6b` | `6e67e161` | `cd505118` | `124bc59c` |
| arbitrum | 42161 | true | `arb-mainnet.g.alchemy.com` | `dc432a6b` | `6e67e161` | `cd505118` | `124bc59c` |
| base | 8453 | true | `base-mainnet.g.alchemy.com` | `dc432a6b` | `6e67e161` | `cd505118` | `124bc59c` |
| optimism | 10 | true | `opt-mainnet.g.alchemy.com` | `dc432a6b` | `6e67e161` | `cd505118` | `124bc59c` |
| polygon | 137 | true | `polygon-mainnet.g.alchemy.com` | `dc432a6b` | `6e67e161` | `cd505118` | `124bc59c` |
| bnb | 56 | true | `bnb-mainnet.g.alchemy.com` | `dc432a6b` | `6e67e161` | `cd505118` | `124bc59c` |

Priority follows list order: 100, 101, 102, 103. Old providers do not outrank the new ones.

---

## 5. Post-apply runtime

Same process. RestartCount `0`. StartedAt `2026-10-04T08:28:21.865915247Z`. Pid `1698122`. No restart was required.

`GET /api/arbicore/providers/status` (`available=true`). Provider count 53 → 65. RPC rows 13 → 25. The added 12 are index 2 and index 3 on the six chains. EVM RPC ids are exactly indices 0–3. No index 4 or higher. No `mainnet.base.org` or other public EVM host id. Solana `rpc_solana_api_mainnet-beta_solana_` remains at priority 100; this apply did not add or remove it.

| Chain | Index 0 / prio | Index 1 / prio | Index 2 / prio | Index 3 / prio |
|---|---|---|---|---|
| ethereum | `rpc_ethereum_0_eth-mainnet_g_alchemy_co` / 100 | `rpc_ethereum_1_…` / 101 | `rpc_ethereum_2_…` / 102 | `rpc_ethereum_3_…` / 103 |
| arbitrum | `rpc_arbitrum_0_arb-mainnet_g_alchemy_co` / 100 | `rpc_arbitrum_1_…` / 101 | `rpc_arbitrum_2_…` / 102 | `rpc_arbitrum_3_…` / 103 |
| base | `rpc_base_0_base-mainnet_g_alchemy_c` / 100 | `rpc_base_1_…` / 101 | `rpc_base_2_…` / 102 | `rpc_base_3_…` / 103 |
| optimism | `rpc_optimism_0_opt-mainnet_g_alchemy_co` / 100 | `rpc_optimism_1_…` / 101 | `rpc_optimism_2_…` / 102 | `rpc_optimism_3_…` / 103 |
| polygon | `rpc_polygon_0_polygon-mainnet_g_alchem` / 100 | `rpc_polygon_1_…` / 101 | `rpc_polygon_2_…` / 102 | `rpc_polygon_3_…` / 103 |
| bnb | `rpc_bnb_0_bnb-mainnet_g_alchemy_co` / 100 | `rpc_bnb_1_…` / 101 | `rpc_bnb_2_…` / 102 | `rpc_bnb_3_…` / 103 |

Ids encode chain, index, and a truncated host. They do not encode the key. All 24 were `HEALTHY` immediately after register, with successes 0 and failures 0, and `circuit_open_until` null. Equal-health scores were 104.5, 104.495, 104.49, 104.485, so index 0 outranks 1, then 2, then 3.

Indices 0 and 1 were re-registered rather than skipped, which is the changed-URL path (pre-apply Base index 0 had successes 55; post-apply it is 0). Indices 2 and 3 are new. The URLs those registrations consumed are the `PROVIDER_RPC_URLS_*` values just written by env_sync from the applied lists above: A `dc432a6b`, B `6e67e161`, C `cd505118`, D `124bc59c`.

`GET /api/arbicore/multichain/readiness` reads the live process environment. All six: `rpc_configured=true`, `economic_rpc_configured=true`, `limited_live_eligible=false`. Eligible count 0.

In-app Base primary after apply, `GET /api/arbicore/rpc/check`: `status=READY`, `chain_id=8453`, `block_number=52167265`, `rpc_url_masked=base-mainnet.g.alchemy.com`, `is_base_mainnet=true`, `generated_at=2026-10-04T14:24:37.411907+00:00`.

Direct `eth_chainId` / `eth_blockNumber` on the applied index-0 URL (new A) for every chain:

| Chain | fp | chain id | block | Match |
|---|---|---:|---:|---|
| ethereum | `dc432a6b` | 1 | 26119570 | yes |
| arbitrum | `dc432a6b` | 42161 | 511637656 | yes |
| base | `dc432a6b` | 8453 | 52167264 | yes |
| optimism | `dc432a6b` | 10 | 157762549 | yes |
| polygon | `dc432a6b` | 137 | 94945818 | yes |
| bnb | `dc432a6b` | 56 | 125691797 | yes |

Base's in-app block (52167265) and the direct index-0 block (52167264) are the same head a moment apart.

Breaker metadata on the live registry: consecutive-failure threshold 5, failure-rate threshold 0.5, open duration 60 seconds. Running `CircuitBreaker.failure_rate_window` is 20.

---

## 6. Modes and safety — unchanged, nothing started

Compared immediately before and after the POST. Hashes exclude `generated_at`.

| Surface | Hash before | Hash after | Observed after |
|---|---|---|---|
| `GET /api/arbicore/execution/mode` | `df29a46c4532a514` | same | see modes below. Timestamps still `2026-09-07` |
| `GET /api/arbicore/settings/execution` | `5e7f3066359a3ef6` | same | `auto_execute_enabled=false`, `revision_id=rev-35aaafa0454f4a2d8c9aa7b750a2c803`, `updated_at=2026-09-07T05:24:08.858259+00:00`, `updated_by=system:boot` |
| Safety kill snapshot | `4266f30fe4e00aa3` | same | `live_execution_enabled=false`; in-memory kill `engaged=true`, reason `boot_default`, `engaged_at=2026-10-04T08:28:28.012062Z`; persistent kill `engaged=false`; `effective_kill_engaged=true` |
| `GET /api/arbicore/certification/shadow/current` | `73bc1058c12beac8` | same | `current` **null** |
| `GET /api/arbicore/engine/base-live-shadow/wss-status` | `a1380923648e6f65` | same | `enabled=false`, `running=false`, `broadcast=false`, `mode=SHADOW` |

Stored execution modes (unchanged timestamps):

| Strategy | Mode |
|---|---|
| `flash_loan_arbitrage` | `SHADOW` |
| `cex_arbitrage` | `PAPER` |
| `cross_chain_arbitrage` | `PAPER` |
| `dex_capital_arbitrage` | `PAPER` |
| `portfolio_rebalance` | `PAPER` |
| `position_management` | `PAPER` |
| `treasury_movement` | `PAPER` |

The `SHADOW` value on `flash_loan_arbitrage` is the stored mode from `2026-09-07`. `shadow/current` is null. This operation did not start a shadow session.

Logs since `2026-10-04T14:24:00Z`: `shadow/start` 0, `scanner/start` 0, `paper/start` 0, `network/rollback` 0, `network/apply` 1.

Container spec env observed via a fresh exec (not the hot-reloaded process environ): `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false`. Those names were not in `env_synced`.

Network-config non-RPC fields after apply still match the pre-apply document, including empty executor addresses.

---

## 7. Re-read — four endpoints still applied

`GET /api/arbicore/settings/network` at `2026-10-04T14:38:23Z`.

| Field | Observed |
|---|---|
| Revision | `rev-1068cb9715194f118c99e5f04f9e1bdb` |
| `updated_at` | `2026-10-04T14:24:36.649620+00:00` |
| Draft | **null** |
| Endpoints per chain | 4 |
| Order | `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c` |
| Enabled | all six true |
| Public / fifth | none |
| RestartCount | 0 |
| StartedAt / pid | unchanged (`2026-10-04T08:28:21.865915247Z`, pid `1698122`) |

No two-endpoint apply is the live document. No further APPLY was sent. Historical audit rows, backups, fixtures, and cert docs were not deleted. `cd505118` and `124bc59c` appear in this revision only at index 2 and index 3.

`GET /api/arbicore/rpc/check` at the same time: `status=READY`, `chain_id=8453`, `block_number=52167678`, host `base-mainnet.g.alchemy.com`.

---

## 8. Dashboard correlation and failure class

Dashboard figures are operator observations. They are not labeled with a key fingerprint. Correlation uses post-apply HTTP status lines in container logs from `2026-10-04T14:24:36Z` onward (httpx `HTTP/1.1 <status>` on the Alchemy host). Counts are HTTP calls, not Alchemy “requests” or compute units.

| Slot | fp | HTTP calls | HTTP 200 | 400 | 429 | HTTP 200 rate |
|---|---|---:|---:|---:|---:|---:|
| A new | `dc432a6b` | 2602 | 2550 | 52 | 0 | 98.0% |
| B new | `6e67e161` | 48 | 20 | 28 | 0 | 41.7% |
| C old A | `cd505118` | 5756 | 5503 | 80 | 173 | 95.6% |
| D old B | `124bc59c` | 1789 | 1754 | 33 | 2 | 98.0% |

| Dashboard observation | Correlation |
|---|---|
| Account #1: 52 requests/24h, 5.7 CU/s last 5m, success 61.5% last 1h, concurrent 0, median 1ms | Only `6e67e161` (new B) is in this volume band. 32/52 = 61.5%. This log window shows 20 successes and 28 HTTP 400s on that fingerprint; the certification probes before `14:24:36Z` add further successful `eth_chainId` / `eth_blockNumber` calls that are outside this log slice. |
| Account #2: 1.8K requests/24h, 96.9 CU/s last 5m, success 97.4% last 1h and 24h, concurrent 0, median 1ms | High-volume, ~97% success. `cd505118` (old A / C) is the largest post-apply HTTP source and the only fingerprint with a material 429 count. Its HTTP 200 rate is 95.6%. New A and old B are also near 98%. The dashboard 24h request total (1.8K) is a different counter from this 14-minute HTTP log (thousands of calls), so the rollup and the log window are not the same number. |

Failure class, from the log text that exists (httpx status and `providers: … eth_getLogs -> 400, failing over`). Response bodies are not logged.

| Class | Evidence |
|---|---|
| Actual RPC/provider outage | Not observed. All four fingerprints return HTTP 200 for the bulk of calls. Chain-id probes on all 24 were HTTP 200 with the expected chain id. |
| Unsupported method | No `method not found` / `-32601` text. |
| Application / query error | 193 HTTP 400 lines, all tied to `eth_getLogs -> 400`. The client treats other 4xx as non-retryable. The same second shows ethereum index 2, then 3, then 1, then 0 failing that method and failing over. The query fails on every account, so it is not one bad key. |
| Rate limiting | 173 HTTP 429 on `cd505118`, 2 on `124bc59c`, 0 on the new fingerprints in this window. `Too Many Requests` count in the log is 206 including the status text. |
| Malformed requests | No separate parse-error class in the log. The 400s are the getLogs calls above. |
| Expected rejected calls | No `execution reverted` lines in this window. |
| Other | None material. |

The 61.5% figure is the small-sample new B account, pulled down by those shared getLogs 400s. It is not the ArbiCore chain-head success rate, and it is not a new-A outage. New A is 98.0% HTTP 200. Providers were not reordered from the dashboard rates.

Registry health at the re-read (successes reset at apply, so these counts are post-apply only). EWMA latency is milliseconds. `circuit_open_until` was null on every row.

| Chain | A ok/fail (prio 100) | B ok/fail (101) | C ok/fail (102) | D ok/fail (103) |
|---|---|---|---|---|
| ethereum | 2/7 DEGRADED, 86 ms | 1/7 DEGRADED, 143 ms | 1133/27 HEALTHY, 22 ms | 1/7 DEGRADED, 77 ms |
| arbitrum | 2/7 DEGRADED, 74 ms | 1/7 DEGRADED, 61 ms | 2247/23 HEALTHY, 29 ms | 419/11 DEGRADED, 37 ms |
| base | 124/0 HEALTHY, 74 ms | 1/0 HEALTHY, 101 ms | 2/0 HEALTHY, 74 ms | 1/0 HEALTHY, 67 ms |
| optimism | 1316/27 HEALTHY, 21 ms | 2/7 DEGRADED, 59 ms | 1/7 DEGRADED, 45 ms | 1/7 DEGRADED, 49 ms |
| polygon | 184/11 DEGRADED, 35 ms | 14/7 DEGRADED, 101 ms | 1269/23 HEALTHY, 18 ms | 105/8 DEGRADED, 65 ms |
| bnb | 1/0 HEALTHY, 239 ms | 1/0 HEALTHY, 530 ms | 1/0 HEALTHY, 365 ms | 1227/0 HEALTHY, 39 ms |

Last error string on the degraded rows is `eth_getLogs -> 400`. Base and BNB have no failures in the registry counters. On BNB, D’s score (104.446) is above A (104.261) because latency penalty outweighs the 0.015 priority gap. Config order is still A→B→C→D. The registry’s existing score function is what selects among healthy providers. This certification did not change that function and did not reorder the stored list.

---

## 9. Failover — observed, not induced

No provider was taken offline. No destructive probe.

Safe evidence already in the running process:

| Check | Result |
|---|---|
| Config order | index 0–3 = A, B, C, D on all six |
| Registry priority | 100, 101, 102, 103 |
| Equal-health score order at register time | 104.5, 104.495, 104.49, 104.485 (A ahead of B ahead of C ahead of D) |
| Breaker | threshold 5 consecutive, failure rate 0.5 over 20 events, open 60s |
| Natural failover | 193 `failing over` lines since apply, all `eth_getLogs -> 400` |
| Cooldown | 36 `breaker_tripped`, 75 `TRIPPED`, 39 `breaker_reset` |

First ethereum burst at `14:26:33` tried index 2, then 3, then 1, then 0. That is score order after C had already accumulated successes, not a rewrite of the stored A→B→C→D list. The same 400 then walked the other registered providers, which is the failover path. Circuit open/reset lines show the 60s cooldown running. At the re-read, breakers were closed (`circuit_open_until` null) and several rows were still DEGRADED with consecutive failures still above the trip threshold, which is the existing reset path: leaving TRIPPED clears the open-until timestamp and does not zero the consecutive-failure counter.

---

## Checklist

| # | Check | Result |
|---:|---|---|
| 1 | Four ordered providers already supported | **PASS** — not a two-provider hard limit |
| 2 | Existing draft used; not recreated | **PASS** |
| 3 | 24/24 connectivity, chain id, block, fingerprint | **PASS** |
| 4 | Schema validate HTTP 200, `ok=true`, `errors=[]` | **PASS** |
| 5 | New A/B first, old A/B as C/D | **PASS** — `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c` |
| 6 | No public RPC, no fifth endpoint, six chains enabled | **PASS** |
| 7 | Unrelated network fields unchanged | **PASS** |
| 8 | New revision applied | **PASS** — `rev-1068cb9715194f118c99e5f04f9e1bdb` |
| 9 | Registry contains all four, priorities 100–103 | **PASS** |
| 10 | Old fingerprints only as C/D | **PASS** |
| 11 | No stale provider beyond D; no public fallback id | **PASS** |
| 12 | Chain id on all six primaries | **PASS** |
| 13 | Failover metadata present | **PASS** — breaker threshold, rate, 60s cooldown |
| 14 | Hot reload; restart count unchanged | **PASS** — RestartCount 0, same pid and StartedAt |
| 15 | No Phase 0 deploy, no SHADOW/PAPER/RECOMMENDATION/LIVE start, no commit, no code change | **PASS** |
| 16 | Re-read: still four endpoints, draft null, no second APPLY | **PASS** |
| 17 | 61.5% account is not a material new-A RPC outage | **PASS** — new B small sample; shared `eth_getLogs` HTTP 400; new A 98.0% HTTP 200 |
| 18 | Failover/cooldown observed without taking providers down | **PASS** |

**RPC_ABCD_ROTATION_PASS**

**STOP.** Phase 0 is not deployed. Phase 1 SHADOW is not started. No further APPLY.
