# Six-Network A/B-Only — Pre-Apply Gate — 2026-10-03

- **Status:** **READ-ONLY PRE-APPLY GATE** — no APPLY, no rollback, no draft edit, no draft save, no executor or mode change, no SHADOW start, no production restart.
- **Read (UTC):** `2026-10-03T15:16:13Z`
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:27dfab4-20261003` · healthy · StartedAt `2026-10-03T12:42:03.446652725Z` · RestartCount `0`
- **Running commit:** `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` (`ARBICORE_GIT_SHA`, `BUILD_INFO.json`)
- **Canonical store:** `GET /api/arbicore/settings/network` (HTTP 200) cross-checked with Mongo `arbicore_x.arbicore_config` (`_id=network`) and `arbicore_config_drafts` (`_id=network`)
- **Secrets policy:** Alchemy credentials not printed. Fingerprint = `sha256(<key>)[:8]` of the path segment after `/v2/`. URLs shown as `https://<host>/v2/<fp:…>`.

Operator-reported validate (`POST /api/arbicore/settings/network/validate` HTTP 200, `ok=true`, `errors=[]`) was **not re-issued** by this gate. Backend access log shows earlier validate `200` responses and **no** `POST /settings/network/apply` or `POST /settings/network/rollback` since this container started.

---

## Verdict

All fourteen checks pass. The pending draft is the six-network Alchemy A/B topology. The applied Base PAYG revision is unchanged. This gate stops here and does not APPLY.

---

## Checks

| # | Check | Result |
|---:|---|---|
| 1 | Pending draft contains exactly six supported chains | **PASS** |
| 2 | Every chain is enabled in the draft | **PASS** |
| 3 | Every chain has exactly two RPC URLs | **PASS** |
| 4 | RPC ordering is A first, B second | **PASS** |
| 5 | A fingerprint `cd505118` for all six | **PASS** |
| 6 | B fingerprint `124bc59c` for all six | **PASS** |
| 7 | No public RPC URL remains in the draft | **PASS** |
| 8 | Chain IDs 1, 42161, 8453, 10, 137, 56 | **PASS** |
| 9 | Applied revision remains `rev-7c93bb93e65b4f5a9b7340bf513437c0` | **PASS** |
| 10 | Current applied configuration has not changed (Base PAYG vs draft) | **PASS** |
| 11 | `ce00e63d` absent | **PASS** |
| 12 | No executor settings or execution modes changed | **PASS** |
| 13 | No SHADOW session/process started by this work | **PASS** |
| 14 | Generalized env_sync from `27dfab4` present in the running backend | **PASS** |

---

## 1–8. Pending draft

Mongo draft and `GET /api/arbicore/settings/network` `draft` agree.

| Field | Value |
|---|---|
| Present | yes |
| `updated_at` | `2026-10-03T15:06:18.846543+00:00` |
| `updated_by` | `operator` |
| `kind` | `network` |
| Chain keys | `ethereum`, `arbitrum`, `base`, `optimism`, `polygon`, `bnb` (exactly these six) |
| HTTP URLs anywhere in the draft | **12**, all under `rpc_urls`, all `https`, all `*.g.alchemy.com` |

The draft document also stores `revision_id=rev-7c93bb93e65b4f5a9b7340bf513437c0`. That field is part of the saved patch. It is **not** a new applied revision. Applied `updated_at` is still the 04:57Z PAYG apply (check 9).

`chains_enabled` is `true` for all six. Each list length is 2. Index 0 is fingerprint `cd505118`. Index 1 is fingerprint `124bc59c`.

Network Config does not store a numeric chain id. Chain identity is the chain key plus the Alchemy hostname, which maps to the required chain id:

| Chain | chainId | Host `[0]` and `[1]` | `[0]` fp | `[1]` fp |
|---|---:|---|---|---|
| ethereum | 1 | `eth-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| arbitrum | 42161 | `arb-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| base | 8453 | `base-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| optimism | 10 | `opt-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| polygon | 137 | `polygon-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |
| bnb | 56 | `bnb-mainnet.g.alchemy.com` | `cd505118` | `124bc59c` |

Alchemy fingerprints on the draft are only `{cd505118, 124bc59c}`. No `mainnet.base.org`, publicnode, or other non-Alchemy host appears in the draft. `ce00e63d` does not appear.

Non-RPC draft fields (`executor_addresses`, `gas_settings`, `mev_relay_urls`, `native_price_usd`, `seeded_from_env`, `revision_id`) match the applied document. The draft differs from applied only in `rpc_urls`, `chains_enabled`, `updated_at`, and `updated_by`.

API `supported_chains` is `["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]`.

---

## 9–11. Applied configuration unchanged

| Field | Applied now | Expected Base PAYG |
|---|---|---|
| `revision_id` | `rev-7c93bb93e65b4f5a9b7340bf513437c0` | same |
| `updated_at` | `2026-10-03T04:57:17.836236+00:00` | same |
| `updated_by` | `admin` | `admin` |
| Enabled | base `true`; ethereum, arbitrum, optimism, polygon, bnb `false` | same |
| `rpc_urls` | **base only** | same |
| base `[0]` | `base-mainnet.g.alchemy.com` fp `cd505118` | same |
| base `[1]` | `https://mainnet.base.org` (public fallback) | same |
| Other chains' RPC lists | absent | same |
| `ce00e63d` | absent | absent |

Latest network audit row is still that apply: action `apply`, reason `fetch`, `at=2026-10-03T04:57:17.836236+00:00`, actor `admin`. Network applies with `at >= 2026-10-03T15:06:18Z`: **0**. API history limit 1 returns the same revision. The public Base fallback remains on the **applied** document only. It is not in the draft.

`ce00e63d` is absent from the draft and from the current applied document. It remains only inside the historical `previous` snapshot of the 04:57Z apply (`previous` revision `rev-615fa528802d4bd8ab7074b03bfdf373`).

---

## 12. Executor settings and execution modes

Unchanged relative to records that predate the draft (`2026-10-03T15:06:18Z`).

| Surface | Observed | Last write |
|---|---|---|
| `GET /api/arbicore/settings/execution` | `auto_execute_enabled=false`, `revision_id=rev-35aaafa0454f4a2d8c9aa7b750a2c803`, sizing/thresholds at boot defaults | `2026-09-07T05:24:08.858259+00:00` by `system:boot` |
| Execution-settings audit since `15:00Z` | **0** | — |
| Execution modes | `flash_loan_arbitrage=SHADOW`; the other six strategies `PAPER` | each `updated_at` `2026-09-07T05:24:07Z`, actor `system_bootstrap` |
| Mode audit since `15:00Z` | **0** | — |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` | container env, process started `12:42:03Z` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` | container env |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` | container env |
| `live_execution_enabled` | `false` | `GET /api/arbicore/safety/status` |
| In-memory safety kill | engaged, reason `boot_default`, history length **0** | `engaged_at=2026-10-03T12:42:17.737653Z` (process boot, not the draft) |
| Persistent kill switch | `engaged=false` | `last_disengaged_at=2026-09-13T10:11:33.130781+00:00` |
| Operational flags | `auto_execute=false`, `trading_paused=false` | `2026-09-07T05:24:08.879675+00:00` |
| Applied `executor_addresses` | unchanged vs draft (no field drift) | applied network `updated_at` still `04:57:17Z` |

No `POST /api/arbicore/execution/mode` appears in this container's log.

---

## 13. SHADOW

| Observation | Result |
|---|---|
| `GET /api/arbicore/certification/shadow/current` | HTTP 200, `current` is **null** (`2026-10-03T15:16:13.746410+00:00`) |
| Runs started on `2026-10-03` | **0** |
| Latest stored run | `shadowcert-47401f65-d06f-41ce-9d2b-c3aa70578619`, status `PASS_INFRASTRUCTURE_ONLY`, `started_at=2026-09-16T11:01:16.305617+00:00` |
| `POST /certification/shadow/start` in logs since container start | **none** |
| Process list | uvicorn `server:app` only (plus the inspection shell). No separate SHADOW worker started at draft time |

`ShadowCertificationRunner started (cycle_s=60.0)` is a boot log line at `2026-10-03 12:42:21`, from container start, before the draft. It is not a certification session. This gate's own calls were GET `shadow/current` and GET `shadow/runs`.

---

## 14. Generalized env_sync (`27dfab4`)

Running `/app/arbicore/config/env_sync.py` sha256 `fdb8a6f8d5b57e4913d8f66060238684c1523eaa200a4f8b6c1f59bbe6c58ab8` matches `git show 27dfab42ae6981b39628c04fd9d1b869c3f6c57b:app/backend/arbicore/config/env_sync.py`.

Running `/app/arbicore/config/persistent.py` sha256 `41c0865cd5b9a40873f98eec2fd01162b801b6d5b96300c16a2ba47e7142ca4c` matches the same commit. `SUPPORTED_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")`.

`sync_env_from_network_config` defaults to every `SUPPORTED_CHAINS` entry. Running `/app/server.py` calls it with no single-chain override at startup (line 8675), apply (line 6004), and rollback (line 6032).

Startup log, `2026-10-03 12:42:25`:

`env_sync: exported 4 var(s) from persistent network config (chains=base,ethereum,arbitrum,optimism,polygon,bnb)`

That is the generalized logger (`chains=` plus the six-chain list). The export count is 4 because the **applied** document is still Base-only, so only Base RPC aliases were written. The pending draft has not been applied, so env_sync has not promoted the six-chain draft.

---

## What this gate did not do

No APPLY. No rollback. No draft save. No validate POST. No executor or mode write. No SHADOW start. No container restart (StartedAt and RestartCount unchanged). The only mutations are this certification document.

**PRE_APPLY_GO**
