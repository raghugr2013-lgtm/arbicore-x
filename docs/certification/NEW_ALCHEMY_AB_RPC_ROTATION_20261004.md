# New Alchemy A/B RPC Rotation — 2026-10-04

- **Classification:** **RPC_ROTATION_BLOCKED**
- **Checked (UTC):** `2026-10-04T14:08Z` through `2026-10-04T14:12Z`
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:b1b2-62ec784` · image id `sha256:25dd0905b70e728f333aca170706299f420fc94dc7204dd7ae183df792a687fb` · `ARBICORE_GIT_SHA` `62ec7844cdec9517b10a5d40378bd1c5aacc9551` · StartedAt `2026-10-04T08:28:21.865915247Z` · RestartCount **0** · Status `running` · host pid `1698122`
- **Applied revision (unchanged):** `rev-d069f13244ba44da81f97e72f7cfce5b` · `updated_at` `2026-10-03T15:27:57.368745+00:00` · `updated_by` `admin`
- **Pending draft:** **null**
- **Canonical store:** Mongo `arbicore_x.arbicore_config` `_id=network` (`kind=network`), applied through `POST /api/arbicore/settings/network/draft` then `validate` then `apply`. That path was **not** called.
- **Secrets policy:** Alchemy credentials not printed. Fingerprint = `sha256(<key>)[:8]` of the path segment after `/v2/`. URLs shown as host + `fp=…`. Admin password not printed. Login HTTP 200, role `admin`.

No draft. No validate of a new document. No APPLY. No rollback. No execution-mode, executor, risk, Gate 7, Gate 8, MEV, scanner, or wallet edit. No signing. No broadcast. No image deploy. No container restart. No SHADOW start or resume.

---

## Verdict

**RPC_ROTATION_BLOCKED.** A clearly designated new Alchemy Account A and new Alchemy Account B, distinct from the exhausted fingerprints `cd505118` and `124bc59c`, are not present in the server-side secret or Network Config stores. The twelve new endpoints were not invented and were not validated. The applied revision is unchanged.

---

## 1. Where RPC credentials live

| Store | What it holds | Authoritative for live RPC? |
|---|---|---|
| Mongo Network Config `arbicore_config` `_id=network` | Six chains, two Alchemy URLs each. Index 0 fp `cd505118`, index 1 fp `124bc59c` | **Yes.** Apply hot-loads this document through `env_sync` into the running process |
| Mongo `arbicore_config_drafts` | No `_id=network` draft | No pending rotation |
| Mongo `arbicore_secrets` | One handle `sec-3cec159e23d7495ab89140e5452a3d67`, scope `evm_sign`, algorithm `eth_privkey`, label `arbicore-executor-owner`, created `2026-09-12T11:47:51Z` | Signer material. Not an RPC credential |
| Container bootstrap env and `deployment/upgrade/backend/.env` | Alchemy URLs fp `5e5d5bb1` on the non-Base `ARBICORE_RPC_URL*` vars and archive URL. `ARBICORE_RPC_URL_BASE` is host `mainnet.base.org`. `ALCHEMY_API_KEY` empty | Bootstrap only. Live Base `rpc/check` is Alchemy, not that public host |
| Older env backups under the v2 tree | fps `ce00e63d`, `ff5eb596`, `5e5d5bb1` | Historical. Not a new pair |
| Docker secrets / `/run/secrets` | None | No |
| Host process environment | No Alchemy or RPC variables | No |

Frontend was not given keys by this task. `GET /api/arbicore/settings/network` still returns full URLs to an authenticated admin; those values were fingerprinted in-process and not written here.

Sibling databases on the same Mongo server were scanned for Alchemy `/v2/` URLs. No fingerprint other than the known historical set (`cd505118`, `124bc59c`, `5e5d5bb1`, `ce00e63d`, `ff5eb596`) appeared.

No file, env var, secret handle, or draft was labeled as a new Account A and a new Account B.

---

## 2. Pre-change audit (still the live state)

`GET /api/arbicore/settings/network` matches Mongo.

| Field | Observed |
|---|---|
| Revision | `rev-d069f13244ba44da81f97e72f7cfce5b` |
| Draft | null |
| Chains enabled | ethereum, arbitrum, base, optimism, polygon, bnb — all `true` |
| RPC count | 2 per chain, 12 URLs, all `*.g.alchemy.com` |
| Priority model | Index 0 priority **100**, index 1 priority **101** (registry `100 + index`) |
| Account A | fp **`cd505118`** on every chain |
| Account B | fp **`124bc59c`** on every chain |
| Public RPC in the applied document | none |
| Execution | `flash_loan_arbitrage=SHADOW`; other strategies `PAPER`. Timestamps still `2026-09-07T05:24:07Z` |
| Auto-execute | `false` · execution revision `rev-35aaafa0454f4a2d8c9aa7b750a2c803` · `updated_by=system:boot` |
| Container env | `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false` |
| Shadow campaign | `GET /api/arbicore/certification/shadow/current` → `current` **null** |
| Base WSS | `enabled=false`, `running=false`, `broadcast=false` |
| Safety | `live_execution_enabled=false` |
| RestartCount | **0** (unchanged) |

| Chain | Expected chain id | Host `[0]` and `[1]` | `[0]` fp / priority | `[1]` fp / priority |
|---|---:|---|---|---|
| ethereum | 1 | `eth-mainnet.g.alchemy.com` | `cd505118` / 100 | `124bc59c` / 101 |
| arbitrum | 42161 | `arb-mainnet.g.alchemy.com` | `cd505118` / 100 | `124bc59c` / 101 |
| base | 8453 | `base-mainnet.g.alchemy.com` | `cd505118` / 100 | `124bc59c` / 101 |
| optimism | 10 | `opt-mainnet.g.alchemy.com` | `cd505118` / 100 | `124bc59c` / 101 |
| polygon | 137 | `polygon-mainnet.g.alchemy.com` | `cd505118` / 100 | `124bc59c` / 101 |
| bnb | 56 | `bnb-mainnet.g.alchemy.com` | `cd505118` / 100 | `124bc59c` / 101 |

Read-only `eth_chainId` / `eth_blockNumber` against this **current** document (not a new pair):

| Chain | Index | fp | chain id | Match | Latest block observed |
|---|---:|---|---:|---|---:|
| ethereum | 0 | `cd505118` | 1 | yes | block read succeeded on an immediate retry; a later isolated read returned HTTP 429 |
| ethereum | 1 | `124bc59c` | 1 | yes | 26119491 |
| arbitrum | 0 | `cd505118` | 42161 | yes | 511634244 |
| arbitrum | 1 | `124bc59c` | 42161 | yes | 511634245 |
| base | 0 | `cd505118` | 8453 | yes | 52166794 (chain id confirmed on retry after one HTTP error) |
| base | 1 | `124bc59c` | 8453 | yes | 52166794 |
| optimism | 0 | `cd505118` | 10 | yes | 157762079 |
| optimism | 1 | `124bc59c` | 10 | yes | 157762079 |
| polygon | 0 | `cd505118` | 137 | yes | 94945190 |
| polygon | 1 | `124bc59c` | 137 | yes | 94945191 |
| bnb | 0 | `cd505118` | 56 | yes | 125689709 |
| bnb | 1 | `124bc59c` | 56 | yes | 125689709 |

No wrong chain id was observed. Runtime `GET /api/arbicore/rpc/check` at `2026-10-04T14:08:25Z`: `status=READY`, chain id **8453**, block **52166779**, masked host `base-mainnet.g.alchemy.com`.

---

## 3. New endpoint gate

| Check | Result |
|---|---|
| Designated new Account A, distinct from `cd505118` | **ABSENT** |
| Designated new Account B, distinct from `124bc59c` | **ABSENT** |
| Twelve new endpoint probes | **NOT RUN** |
| Pending draft | **NOT CREATED** |
| `POST /api/arbicore/settings/network/validate` | **NOT CALLED** |
| `POST /api/arbicore/settings/network/apply` | **NOT CALLED** |

---

## 4. Runtime registry (unchanged)

`GET /api/arbicore/providers/status` (`available=true`). Six-chain RPC rows:

| Chain | Provider 0 | Priority | Status | Provider 1 | Priority | Status |
|---|---|---:|---|---|---:|---|
| ethereum | `rpc_ethereum_0_eth-mainnet_g_alchemy_co` | 100 | DEGRADED | `rpc_ethereum_1_eth-mainnet_g_alchemy_co` | 101 | HEALTHY |
| arbitrum | `rpc_arbitrum_0_arb-mainnet_g_alchemy_co` | 100 | HEALTHY | `rpc_arbitrum_1_arb-mainnet_g_alchemy_co` | 101 | DEGRADED |
| base | `rpc_base_0_base-mainnet_g_alchemy_c` | 100 | HEALTHY | `rpc_base_1_base-mainnet_g_alchemy_c` | 101 | HEALTHY |
| optimism | `rpc_optimism_0_opt-mainnet_g_alchemy_co` | 100 | HEALTHY | `rpc_optimism_1_opt-mainnet_g_alchemy_co` | 101 | DEGRADED |
| polygon | `rpc_polygon_0_polygon-mainnet_g_alchem` | 100 | DEGRADED | `rpc_polygon_1_polygon-mainnet_g_alchem` | 101 | HEALTHY |
| bnb | `rpc_bnb_0_bnb-mainnet_g_alchemy_co` | 100 | HEALTHY | `rpc_bnb_1_bnb-mainnet_g_alchemy_co` | 101 | DEGRADED |

Provider ids encode host and index, not the key. They are the same ids written by the 2026-10-03 apply of `cd505118` / `124bc59c`. No public EVM host is in the registry. Pre-existing Solana provider `rpc_solana_api_mainnet-beta_solana_` (priority 100) is still present and was not part of this task.

Old fingerprints **`cd505118` and `124bc59c` are still present** on all six applied chains. No new fingerprint replaced them.

---

## 5. Safety

| Control | State |
|---|---|
| Revision | unchanged `rev-d069f13244ba44da81f97e72f7cfce5b` |
| Mode | SHADOW for flash-loan; PAPER for the other strategies |
| Auto-execute / runtime autostart | false / false |
| Shadow campaign | not started; `current` null |
| Signing / broadcast | not performed |
| RestartCount | **0** |
| StartedAt | `2026-10-04T08:28:21.865915247Z` |

A restart was not required and was not performed. Hot reload was not used because there was no new document to apply.

---

## What unblocks a later rotation

Place a clearly designated new Alchemy Account A and new Alchemy Account B on the server, distinct from `cd505118` and `124bc59c`, through the existing Network Config secret path. Until those two credentials exist, do not draft and do not apply.

**RPC_ROTATION_BLOCKED**

**STOP.** Do not start Phase 1 SHADOW.
