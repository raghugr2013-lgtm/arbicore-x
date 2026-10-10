# SIX-NETWORK A/B-ONLY DRAFT CERTIFICATION — 2026-10-03

- **Status:** **DRAFT UPDATED AND VALIDATED — NOT APPLIED.** No APPLY, no chain activation, no SHADOW start, no runtime env_sync.
- **Decision certified:** Alchemy Account A + Account B are the complete RPC topology for all six supported chains. Public RPC endpoints are not part of this pending draft.
- **Captured (UTC):** `2026-10-03T15:06:18Z`
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:27dfab4-20261003` · digest `sha256:77f0bb536f7f02ca18d18dadb16985aac34e980de5f6de540aaf660a0e7ca2bb` · started `2026-10-03T12:42:03Z` · port `127.0.0.1:8001`
- **Canonical store:** existing Settings/Network draft API → Mongo `NetworkConfigRepo` kind=`network`. No second config store.
- **Write path used:** `POST /api/arbicore/settings/network/draft` (the UI SAVE DRAFT path, `v2Api.networkDraft`).
- **Validate path used:** `POST /api/arbicore/settings/network/validate` only.
- **Secrets policy:** Alchemy credentials never printed. Fingerprint = `sha256(<key>)[:8]` of the path segment after `/v2/`. URLs shown as host + `/v2/<REDACTED>` + `fp=…`. Admin password never printed. Login role `admin`, HTTP 200.

Prior filenames `docs/certification/SIX_NETWORK_THREE_TIER_RPC_DRAFT_CERT_20261003.md` and `SIX_NETWORK_DRAFT_CERTIFICATION_20261003.md` were **not present** in this workspace at certification time. The pending draft loaded from `GET /api/arbicore/settings/network` was the three-tier document (`updated_at` `2026-10-03T14:37:36.940472+00:00`). Related applied-config context: `docs/certification/SIX_NETWORK_CONFIG_CERTIFICATION_MATRIX_20261003.md`.

---

## Executive verdict

| Check | Result |
|---|---|
| Six chains present in the pending draft | **PASS** — ethereum, arbitrum, base, optimism, polygon, bnb |
| Draft enabled flags | **Reported, unchanged** — all six `true` |
| Applied enabled flags | **Unchanged** — base `true`; ethereum, arbitrum, optimism, polygon, bnb `false` |
| 2 RPC URLs per chain | **PASS** |
| Ordering Alchemy A → Alchemy B | **PASS** — index 0 `cd505118`, index 1 `124bc59c` on every chain |
| Chain IDs | **Unchanged** — product map is 1, 42161, 8453, 10, 137, 56. Network Config does not store chain IDs; this save did not write them |
| Fingerprints `cd505118` and `124bc59c` | **PASS** — both present |
| `ce00e63d` | **ABSENT** from draft and from applied Network Config |
| Public RPC removed from the draft | **PASS** — third URL stripped on Base, Ethereum, Arbitrum, Optimism, BNB. Polygon already had two Alchemy URLs and was left as those two |
| VALIDATE | **PASS** — HTTP 200, `ok: true`, `errors: []` |
| APPLY | **NOT CALLED** |
| Applied revision | **UNCHANGED** — `rev-7c93bb93e65b4f5a9b7340bf513437c0` · `updated_at` `2026-10-03T04:57:17.836236+00:00` · `updated_by` `admin` |
| Runtime activation | **NONE** — execution-mode map unchanged; Base WSS `enabled=false`, `running=false`, `broadcast=false`; no `env_sync`, no scanner start |

**STOP.** This draft is not applied. Do not APPLY. Do not start SHADOW.

---

## What changed (pending draft only)

Loaded the pending draft, removed only RPC index 2 where it was a public endpoint, then saved that document through the draft API.

| Chain | Removed public host (was RPC #3) |
|---|---|
| Base | `mainnet.base.org` |
| Ethereum | `ethereum-rpc.publicnode.com` |
| Arbitrum | `arb1.arbitrum.io` |
| Optimism | `mainnet.optimism.io` |
| BNB | `bsc-dataseed.bnbchain.org` |
| Polygon | *(none — already two Alchemy URLs; left unchanged)* |

Preserved on the draft, byte-for-byte aside from `rpc_urls` list length and the server draft timestamps:

| Field | Unchanged |
|---|---|
| `chains_enabled` | yes |
| `executor_addresses` | yes |
| `gas_settings` | yes |
| `mev_relay_urls` | yes |
| `native_price_usd` | yes |
| `seeded_from_env` | yes |

Draft identity after save: `kind=network`, `updated_by=operator`, `updated_at=2026-10-03T15:06:18.846543+00:00`. The draft document still carries the applied `revision_id` field `rev-7c93bb93e65b4f5a9b7340bf513437c0` (form metadata copied with the draft). That field is not a new applied revision.

---

## Six-chain A/B matrix (pending draft)

Chain IDs below are the live product constants (`EXPECTED_CHAIN_IDS` in the running image). They are not Network Config fields and were not edited.

| Chain | Chain ID | Draft enabled | Applied enabled | RPC #1 primary | RPC #2 fallback | Count |
|---|---:|---|---|---|---|---:|
| Ethereum | 1 | true | false | `eth-mainnet.g.alchemy.com/v2/<REDACTED>` fp **`cd505118`** | same host fp **`124bc59c`** | 2 |
| Arbitrum | 42161 | true | false | `arb-mainnet.g.alchemy.com/v2/<REDACTED>` fp **`cd505118`** | same host fp **`124bc59c`** | 2 |
| Base | 8453 | true | **true** | `base-mainnet.g.alchemy.com/v2/<REDACTED>` fp **`cd505118`** | same host fp **`124bc59c`** | 2 |
| Optimism | 10 | true | false | `opt-mainnet.g.alchemy.com/v2/<REDACTED>` fp **`cd505118`** | same host fp **`124bc59c`** | 2 |
| Polygon | 137 | true | false | `polygon-mainnet.g.alchemy.com/v2/<REDACTED>` fp **`cd505118`** | same host fp **`124bc59c`** | 2 |
| BNB | 56 | true | false | `bnb-mainnet.g.alchemy.com/v2/<REDACTED>` fp **`cd505118`** | same host fp **`124bc59c`** | 2 |

Draft Alchemy fingerprints: **`cd505118`** (Account A, including Base primary) and **`124bc59c`** (Account B). No other Alchemy fingerprint is in the draft. **`ce00e63d` is absent.**

Live chain-id maps read from the running image (not modified):

| Source | IDs |
|---|---|
| `chain_execution_readiness.EXPECTED_CHAIN_IDS` | ethereum **1**, optimism **10**, bnb **56**, polygon **137**, base **8453**, arbitrum **42161** |
| `chains.registries.CHAIN_REGISTRIES` | ethereum 1, optimism 10, bnb 56, polygon 137, arbitrum 42161 (Base is not a row in this registry) |
| `execution.broadcast.CHAIN_IDS` | ethereum 1, base 8453, arbitrum 42161, optimism 10, polygon 137 (no `bnb` key in this map; left untouched) |

---

## VALIDATE result

`POST /api/arbicore/settings/network/validate` at `2026-10-03T15:06:18.904392+00:00`.

| Field | Value |
|---|---|
| HTTP | **200** |
| `ok` | **true** |
| `errors` | `[]` |
| `warnings` | `no executor address configured for chain 'base' — LIMITED_LIVE flow will BLOCK` |

The warning is the existing schema warning for an empty Base executor. `executor_addresses` was not modified. Schema validation does not probe RPC methods and does not APPLY.

Uvicorn access log for this operation (no apply line):

```
POST /api/arbicore/settings/network/draft     200
POST /api/arbicore/settings/network/validate  200
```

No `POST /api/arbicore/settings/network/apply`, no `rollback`, no `env_sync`, no `scanner/start`.

---

## Applied revision unchanged

`GET /api/arbicore/settings/network` immediately before the draft save and immediately after VALIDATE.

| Field | Before | After |
|---|---|---|
| `config.revision_id` | `rev-7c93bb93e65b4f5a9b7340bf513437c0` | `rev-7c93bb93e65b4f5a9b7340bf513437c0` |
| `config.updated_at` | `2026-10-03T04:57:17.836236+00:00` | `2026-10-03T04:57:17.836236+00:00` |
| `config.updated_by` | `admin` | `admin` |
| `config.chains_enabled` | base true; other five false | same |
| `config.rpc_urls` | Base only: `[0]` Alchemy fp `cd505118`, `[1]` `mainnet.base.org` | same |

Applied Network Config is still the prior PAYG document. It still contains the public Base fallback because this task did not modify applied config. The A/B-only topology exists only on the pending draft.

---

## No runtime activation

| Probe | Result |
|---|---|
| `GET /api/arbicore/execution/mode` before vs after | **identical** |
| Modes observed (pre-existing, not transitioned) | `flash_loan_arbitrage=SHADOW`; `cex_arbitrage`, `cross_chain_arbitrage`, `dex_capital_arbitrage`, `portfolio_rebalance`, `position_management`, `treasury_movement` = `PAPER` |
| `GET /api/arbicore/engine/base-live-shadow/wss-status` | HTTP 200 · `enabled=false` · `running=false` · `broadcast=false` |
| SHADOW started by this operation | **NO** |
| Chain enablement on the applied document | **unchanged** (only Base remains enabled in applied config) |

---

## Safety posture

| Constraint | Confirmed |
|---|---|
| No APPLY | **YES** |
| Applied revision unchanged | **YES** |
| No chain activation against the applied document | **YES** |
| No SHADOW start, no scanner start, no env_sync | **YES** |
| Chain IDs, executor, gas, MEV, native price, auth, env_sync code untouched | **YES** |
| Current draft not applied | **YES** |
| Secrets fingerprint-only | **YES** |

---

## STOP

**STOP.** Six-network Alchemy A/B draft is saved and VALIDATE passed. Do not APPLY. Do not start SHADOW.
