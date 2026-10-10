# Six-Network A/B-Only — APPLY — 2026-10-03

- **Status:** **APPLY_SUCCESS**
- **Applied (UTC):** `2026-10-03T15:27:57.368745+00:00`
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:27dfab4-20261003` · digest `sha256:77f0bb536f7f02ca18d18dadb16985aac34e980de5f6de540aaf660a0e7ca2bb` · StartedAt `2026-10-03T12:42:03.446652725Z` · RestartCount `0` (unchanged) · Status `running`
- **Running commit:** `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` (`ARBICORE_GIT_SHA`)
- **Endpoint:** `POST /api/arbicore/settings/network/apply` (the Settings → Network apply route). Body was `{"reason":"apply certified six-network Alchemy A/B draft"}` with **no `patch`**, so the server promoted the pending draft. The draft was not edited before this call.
- **Prior gate:** `docs/certification/SIX_NETWORK_AB_ONLY_PRE_APPLY_GATE_20261003.md` (`PRE_APPLY_GO`). Draft cert: `docs/certification/SIX_NETWORK_AB_ONLY_DRAFT_CERT_20261003.md`.
- **Secrets policy:** Alchemy credentials not printed. Fingerprint = `sha256(<key>)[:8]` of the path segment after `/v2/`. URLs shown as host + `fp=…`. Admin password not printed. Login HTTP 200, role `admin`.

Exactly one APPLY. No second APPLY, no rollback, no draft save, no executor edit, no mode edit, no RPC edit, no container restart, no SHADOW start.

---

## Verdict

**APPLY_SUCCESS.** The saved six-network Alchemy A/B draft is now the applied Network Config. Public RPC #3 is gone from the applied document and from the live provider registry. `ce00e63d` is absent from the new revision.

---

## Before APPLY (read-only)

`GET /api/arbicore/settings/network` immediately before the POST matched the certified draft.

| Field | Observed |
|---|---|
| Draft present | yes |
| `updated_at` | `2026-10-03T15:06:18.846543+00:00` |
| `updated_by` | `operator` |
| `kind` | `network` |
| Chains | ethereum, arbitrum, base, optimism, polygon, bnb |
| Enabled | all six `true` |
| RPC count | 2 per chain, 12 URLs, all `https://*.g.alchemy.com` |
| Order | index 0 fp `cd505118`, index 1 fp `124bc59c` on every chain |
| Public hosts | none in the draft |
| `ce00e63d` | absent from the draft |
| Applied revision still | `rev-7c93bb93e65b4f5a9b7340bf513437c0` (`updated_at` `2026-10-03T04:57:17.836236+00:00`, `updated_by` `admin`) |
| Draft vs applied non-RPC fields | `executor_addresses`, `gas_settings`, `mev_relay_urls`, `native_price_usd`, `seeded_from_env` identical |

Chain identity is the chain key plus Alchemy hostname. Numeric chain IDs are not Network Config fields. The running image map `chain_execution_readiness.EXPECTED_CHAIN_IDS` is ethereum 1, optimism 10, bnb 56, polygon 137, base 8453, arbitrum 42161. Hosts on the draft were `eth-mainnet`, `arb-mainnet`, `base-mainnet`, `opt-mainnet`, `polygon-mainnet`, `bnb-mainnet` (all `g.alchemy.com`).

The re-check immediately before POST was the same document. Gate did not block.

---

## APPLY

| Field | Value |
|---|---|
| HTTP | **200** |
| `ok` | **true** |
| `generated_at` | `2026-10-03T15:27:57.632433+00:00` |
| Response keys | `ok`, `config`, `env_synced`, `generated_at` |
| Access log | `POST /api/arbicore/settings/network/apply` **200** (the only such POST since this container started) |
| Rollback POSTs since container start | **0** |

New applied revision: **`rev-d069f13244ba44da81f97e72f7cfce5b`**. `updated_by` `admin`. The pending draft was cleared by apply (`GET` draft is null afterward). That is the repository promoting the draft, not a second write.

`env_synced` names (19), values not returned by the API:

`ARBICORE_RPC_URL`, `ARBICORE_RPC_URL_{ETHEREUM,ARBITRUM,BASE,OPTIMISM,POLYGON,BNB}`, `{ETHEREUM,ARBITRUM,BASE,OPTIMISM,POLYGON,BNB}_RPC_URL`, `PROVIDER_RPC_URLS_{ETHEREUM,ARBITRUM,BASE,OPTIMISM,POLYGON,BNB}`.

No executor-address variables were in `env_synced`.

---

## After APPLY (read-only)

`POST` response `config` and a following `GET /api/arbicore/settings/network` agree.

| # | Check | Result |
|---:|---|---|
| 1 | New applied `revision_id` | **PASS** — `rev-d069f13244ba44da81f97e72f7cfce5b` (was `rev-7c93bb93e65b4f5a9b7340bf513437c0`) |
| 2 | All six chains present | **PASS** |
| 3 | All six enabled | **PASS** — `chains_enabled` true for ethereum, arbitrum, base, optimism, polygon, bnb |
| 4 | Exactly two RPC URLs per chain | **PASS** |
| 5 | A → B ordering | **PASS** — index 0 then index 1 |
| 6 | A fingerprint `cd505118` on all six | **PASS** |
| 7 | B fingerprint `124bc59c` on all six | **PASS** |
| 8 | No public RPC #3 | **PASS** — applied `rpc_urls` are Alchemy-only. Live registry no longer has `rpc_base_1_mainnet_base_org` |
| 9 | `ce00e63d` absent | **PASS** on the new revision (`next` snapshot stale=false, public=none). It remains only inside the historical `previous` snapshot of the older `2026-10-03T04:57:17Z` apply |
| 10 | Executor settings unchanged | **PASS** — `executor_addresses`, `gas_settings`, `mev_relay_urls`, `native_price_usd`, `seeded_from_env` match the pre-APPLY document |
| 11 | Execution modes unchanged | **PASS** — see below. Nothing was started |
| 12 | Generalized env_sync from `27dfab4` in the running backend | **PASS** |
| 13 | Runtime env_sync reflects the new configuration | **PASS for the live process.** Container bootstrap environ was not rewritten. See below |

| Chain | Chain ID | Enabled | Host `[0]` and `[1]` | `[0]` fp | `[1]` fp |
|---|---:|---|---|---|---|
| ethereum | 1 | true | `eth-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| arbitrum | 42161 | true | `arb-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| base | 8453 | true | `base-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| optimism | 10 | true | `opt-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| polygon | 137 | true | `polygon-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| bnb | 56 | true | `bnb-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |

Latest audit row: action `apply`, revision `rev-d069f13244ba44da81f97e72f7cfce5b`, actor `admin`, reason `apply certified six-network Alchemy A/B draft`, `at=2026-10-03T15:27:57.368745+00:00`. Its `previous` snapshot is the prior Base PAYG document (base `[0]` fp `cd505118`, base `[1]` `mainnet.base.org`). Its `next` snapshot is the six-chain A/B matrix above.

---

## 10–11. Executor, modes, safety

Compared immediately before and after the POST. Response hashes exclude `generated_at`.

| Surface | Unchanged | Observed after |
|---|---|---|
| `executor_addresses` / gas / MEV / native price | yes | same as pre-APPLY applied document |
| `GET /api/arbicore/settings/execution` | yes (hash `5e7f3066359a3ef6`) | `auto_execute_enabled=false`, `revision_id=rev-35aaafa0454f4a2d8c9aa7b750a2c803`, `updated_at=2026-09-07T05:24:08.858259+00:00`, `updated_by=system:boot` |
| `GET /api/arbicore/execution/mode` | yes | `flash_loan_arbitrage=SHADOW`; cex, cross-chain, dex-capital, portfolio, position, treasury = `PAPER`. Timestamps still `2026-09-07T05:24:07Z` |
| `GET /api/arbicore/settings/operational` | yes | hash `1bcf91de2d15f047` |
| `GET /api/arbicore/safety/status` | yes | `live_execution_enabled=false`; in-memory kill engaged, reason `boot_default`, `engaged_at=2026-10-03T12:42:17.737653Z`; persistent kill `engaged=false` |
| Container env `ARBICORE_EXECUTION_MODE` | not written | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | not written | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | not written | `false` |
| `GET /api/arbicore/certification/shadow/current` | yes | `current` **null** |
| `GET /api/arbicore/engine/base-live-shadow/wss-status` | yes | `enabled=false`, `running=false`, `broadcast=false` |
| `POST …/shadow/start` or `scanner/start` in this container's log | none | — |

`GET /api/arbicore/rpc/check` stayed READY on `base-mainnet.g.alchemy.com`, chain id **8453**. The response hash moved because the live block moved (after: block **52125965**). That probe did not change configuration.

---

## 12. Generalized env_sync (`27dfab4`)

| File | Running sha256 | `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` | Match |
|---|---|---|---|
| `/app/arbicore/config/env_sync.py` | `fdb8a6f8d5b57e4913d8f66060238684c1523eaa200a4f8b6c1f59bbe6c58ab8` | same | **yes** |
| `/app/arbicore/config/persistent.py` | `41c0865cd5b9a40873f98eec2fd01162b801b6d5b96300c16a2ba47e7142ca4c` | same | **yes** |

`SUPPORTED_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")`.

Running `/app/server.py` calls `sync_env_from_network_config(_NETWORK_CONFIG)` with no single-chain override at apply (line 6004), rollback (line 6032), and startup (line 8675).

---

## 13. Runtime reflection

The apply path hot-loaded the new document into the running process. The container was not restarted.

Log at `2026-10-03 15:27:57,622`:

`env_sync: exported 19 var(s) from persistent network config (chains=base,ethereum,arbitrum,optimism,polygon,bnb)`

That count matches the 19 `env_synced` names. Startup on this same process, `2026-10-03 12:42:25`, had exported **4** vars because the applied document was still Base-only.

Live provider registry (`GET /api/arbicore/providers/status`), RPC rows only:

| | Before | After |
|---|---|---|
| Six chains, index 0 Alchemy host | present | present |
| Six chains, index 1 Alchemy host | absent | **present** (priority 101) |
| `rpc_base_1_mainnet_base_org` | present | **absent** |

Same-second registry log: index 0 was re-registered on ethereum, arbitrum, optimism, polygon, and bnb (same host id, URL replaced). Base index 0 was not re-registered (URL already the PAYG primary). Base index 1 was registered as `rpc_base_1_base-mainnet_g_alchemy_c`, replacing the public Base provider. Index 1 was registered on the other five chains. Provider ids carry the host, not the key. The URLs written into that registry are the strings env_sync copied from the applied `rpc_urls` lists, whose fingerprints are `cd505118` then `124bc59c`.

`/proc/2830498/environ` (uvicorn pid, initial exec block) does **not** show those writes. It still has bootstrap fingerprints: `ARBICORE_RPC_URL` and the five non-Base `ARBICORE_RPC_URL_*` vars at fp `5e5d5bb1`, and `ARBICORE_RPC_URL_BASE` at `mainnet.base.org`. `PROVIDER_RPC_URLS_*` and the legacy `*_RPC_URL` aliases are absent there. `ce00e63d` is absent there. Linux does not update `/proc/<pid>/environ` when the process assigns `os.environ`. Docker was not recreated, so the container spec is still that bootstrap environ. No restart was performed to copy the hot-loaded values into the container spec.

---

## What this apply did not do

No second APPLY. No rollback. No draft edit. No executor, gas, MEV, or native-price edit. No execution-mode, autoexec, or runtime edit. No SHADOW, PAPER, RECOMMENDATION, or LIMITED_LIVE start. No signing or broadcast. No public RPC added. No container restart (StartedAt and RestartCount unchanged).

**APPLY_SUCCESS**

**STOP.** Do not start SHADOW.
