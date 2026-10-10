# Six-Network A/B-Only — Post-Apply Runtime Verification — 2026-10-03

- **Classification:** **RUNTIME_CONFIG_VERIFIED**
- **Checked (UTC):** `2026-10-03T15:47:53Z`
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:27dfab4-20261003` · `ARBICORE_GIT_SHA` `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` · StartedAt `2026-10-03T12:42:03.446652725Z` · Pid `2830498` · RestartCount `0` · Status `running`
- **Applied revision still current:** `rev-d069f13244ba44da81f97e72f7cfce5b` · `updated_at` `2026-10-03T15:27:57.368745+00:00` · `updated_by` `admin` · draft **null**
- **Prior apply:** `docs/certification/SIX_NETWORK_AB_ONLY_APPLY_20261003.md` (`APPLY_SUCCESS`)
- **Secrets policy:** Alchemy credentials not printed. Fingerprint = `sha256(<key>)[:8]` of the path segment after `/v2/`. URLs shown as host + `fp=…`. Admin password not printed. Login HTTP 200, role `admin`.

Read-only. No APPLY, no rollback, no draft or config edit, no container restart, no SHADOW start, no PAPER start, no execution-mode change, no signing, no broadcast.

---

## Verdict

**RUNTIME_CONFIG_VERIFIED.** The process that has been running since `12:42:03Z` (no restart) has the six-chain Alchemy A/B set in its live provider registry. The hot-loaded process environment matches that registry. `eth_chainId` and `eth_blockNumber` succeed on the effective provider (index 0) for all six chains, and on the failover provider (index 1).

A restart is not required for this configuration to be the one the running registry uses.

---

## What was compared

Two different surfaces can look like "the environment." Only the second one is the env_sync result.

| Surface | What it is | This check |
|---|---|---|
| Container spec (`docker inspect` / `printenv` inside a new exec) | Environ block from container start. Linux does not rewrite it when the process assigns `os.environ`. | Still the **bootstrap** picture: non-Base `ARBICORE_RPC_URL_*` fp `5e5d5bb1`, `ARBICORE_RPC_URL_BASE` host `mainnet.base.org`, `PROVIDER_RPC_URLS_*` **absent**. Not the post-apply env. |
| `GET /api/arbicore/config/runtime` | `RuntimeConfig` frozen at **import**, before startup env_sync, and not refreshed by apply. | Still bootstrap: five chains fp `5e5d5bb1`, Base host `mainnet.base.org`. **Not** the live registry. |
| **A. Live env_sync** | `os.environ` inside pid `2830498` after `sync_env_from_network_config`. | Adopted. See below. |
| **B. Live provider registry** | In-memory `ProviderRegistry` via `GET /api/arbicore/providers/status`. | Adopted. See below. |

A and B agree. The container spec and the frozen `RuntimeConfig` cache do not, and they are not the registry the running app calls.

---

## A. Live environment

Persisted Network Config (`GET /api/arbicore/settings/network`), which env_sync copies from, re-read at `15:47Z`:

| Chain | Enabled | Index 0 host / fp | Index 1 host / fp |
|---|---|---|---|
| ethereum | true | `eth-mainnet.g.alchemy.com` / `cd505118` | same host / `124bc59c` |
| arbitrum | true | `arb-mainnet.g.alchemy.com` / `cd505118` | same host / `124bc59c` |
| base | true | `base-mainnet.g.alchemy.com` / `cd505118` | same host / `124bc59c` |
| optimism | true | `opt-mainnet.g.alchemy.com` / `cd505118` | same host / `124bc59c` |
| polygon | true | `polygon-mainnet.g.alchemy.com` / `cd505118` | same host / `124bc59c` |
| bnb | true | `bnb-mainnet.g.alchemy.com` / `cd505118` | same host / `124bc59c` |

Exactly two URLs per chain. All twelve are `*.g.alchemy.com`. `ce00e63d` is absent. No public host in this document.

Evidence this document is what the **running process** is using, not only what is stored:

- Container logs since `15:27:00Z` contain one env_sync line and no later one: `2026-10-03 15:27:57,622 env_sync: exported 19 var(s) from persistent network config (chains=base,ethereum,arbitrum,optimism,polygon,bnb)`.
- `GET /api/arbicore/multichain/readiness` reads `os.environ` in that process. `rpc_configured=true` and `economic_rpc_configured=true` on all six. `economic_rpc_configured` is true only when `PROVIDER_RPC_URLS_<CHAIN>` or `PROVIDER_RPC_URL_<CHAIN>` is set. Those names are absent from the container spec, so they exist only because env_sync wrote them into the live process.
- `GET /api/arbicore/rpc/check` reads `ARBICORE_RPC_URL_BASE` first. Bootstrap value of that variable is `mainnet.base.org`. The live response is `status=READY`, `chain_id=8453`, `block_number=52126559`, `rpc_url_masked=base-mainnet.g.alchemy.com`. The live process primary for Base is Alchemy, not the public host.

`limited_live_eligible=false` on every chain in that readiness report.

---

## B. Live provider registry

`GET /api/arbicore/providers/status` (`available=true`). RPC rows for the six chains:

| Chain | Provider 0 | Priority | Provider 1 | Priority |
|---|---|---:|---|---:|
| ethereum | `rpc_ethereum_0_eth-mainnet_g_alchemy_co` | 100 | `rpc_ethereum_1_eth-mainnet_g_alchemy_co` | 101 |
| arbitrum | `rpc_arbitrum_0_arb-mainnet_g_alchemy_co` | 100 | `rpc_arbitrum_1_arb-mainnet_g_alchemy_co` | 101 |
| base | `rpc_base_0_base-mainnet_g_alchemy_c` | 100 | `rpc_base_1_base-mainnet_g_alchemy_c` | 101 |
| optimism | `rpc_optimism_0_opt-mainnet_g_alchemy_co` | 100 | `rpc_optimism_1_opt-mainnet_g_alchemy_co` | 101 |
| polygon | `rpc_polygon_0_polygon-mainnet_g_alchem` | 100 | `rpc_polygon_1_polygon-mainnet_g_alchem` | 101 |
| bnb | `rpc_bnb_0_bnb-mainnet_g_alchemy_co` | 100 | `rpc_bnb_1_bnb-mainnet_g_alchemy_co` | 101 |

Provider ids encode chain, index, and host. They do not encode the key. All twelve are HEALTHY. There is no `rpc_base_1_mainnet_base_org` and no other public EVM host in the registry. `ce00e63d` does not appear.

Same-process continuity: logs at `15:27:57,623–628` registered those ids (Base index 0 was not re-registered). No later `providers: registered` line. Base index 0 still has `successes=45` and `failures=0`, which is the skip path: same id and same URL, so the existing object was kept. That URL was already the PAYG primary (`cd505118` on `base-mainnet.g.alchemy.com`). The other eleven RPC objects were registered in that same second from `PROVIDER_RPC_URLS_*` just written by env_sync from the applied lists above (index 0 fp `cd505118`, index 1 fp `124bc59c`).

Effective path is index 0 (priority 100). The registry scores a lower priority number higher, so failover (priority 101) is used only if the primary fails.

A Solana RPC provider remains (`rpc_solana_api_mainnet-beta_solana_`, priority 100). It is the pre-existing default, not part of the six-chain network document, and this apply did not add or remove it.

---

## Probes

Methods used: `eth_chainId` and `eth_blockNumber` only.

In-process, through the running app (`GET /api/arbicore/rpc/check`), live-process Base primary:

| Host | chain id | block |
|---|---:|---:|
| `base-mainnet.g.alchemy.com` | 8453 | 52126559 |

The same two methods against the effective registry URL (applied index 0, the string env_sync loaded) and the failover URL (index 1):

| Chain | Path | fp | chain id | block | Match |
|---|---|---|---:|---:|---|
| ethereum | index 0 | `cd505118` | 1 | 26112805 | yes |
| ethereum | index 1 | `124bc59c` | 1 | 26112805 | yes |
| arbitrum | index 0 | `cd505118` | 42161 | 511344457 | yes |
| arbitrum | index 1 | `124bc59c` | 42161 | 511344458 | yes |
| base | index 0 | `cd505118` | 8453 | 52126561 | yes |
| base | index 1 | `124bc59c` | 8453 | 52126561 | yes |
| optimism | index 0 | `cd505118` | 10 | 157721846 | yes |
| optimism | index 1 | `124bc59c` | 10 | 157721846 | yes |
| polygon | index 0 | `cd505118` | 137 | 94891554 | yes |
| polygon | index 1 | `124bc59c` | 137 | 94891554 | yes |
| bnb | index 0 | `cd505118` | 56 | 125510948 | yes |
| bnb | index 1 | `124bc59c` | 56 | 125510949 | yes |

Base's in-app block (`52126559`) and the direct index-0 block (`52126561`) are the same head a moment apart. There is no existing HTTP route that issues only `eth_chainId` / `eth_blockNumber` through the registry for the other five chains. Those five were probed on the URLs the live registry was loaded with at `15:27:57Z` and still lists. Newly registered providers still show `successes=0` because that external probe does not go through their health counters. Base index 0's counter was left at 45 because its URL was unchanged.

---

## Modes and safety (unchanged, nothing started)

| Surface | Observed |
|---|---|
| `GET /api/arbicore/execution/mode` | `flash_loan_arbitrage=SHADOW`; cex, dex-capital, cross-chain, portfolio, treasury, position = `PAPER`. `updated_at` still `2026-09-07T05:24:07Z` |
| `GET /api/arbicore/settings/execution` | `auto_execute_enabled=false`, `revision_id=rev-35aaafa0454f4a2d8c9aa7b750a2c803`, `updated_at=2026-09-07T05:24:08.858259+00:00`, `updated_by=system:boot` |
| `GET /api/arbicore/safety/status` | `live_execution_enabled=false`; in-memory kill `engaged=true`, reason `boot_default`, `engaged_at=2026-10-03T12:42:17.737653Z`; persistent kill `engaged=false`; `effective_kill_engaged=true` |
| `GET /api/arbicore/certification/shadow/current` | `current` **null** |
| `GET /api/arbicore/engine/base-live-shadow/wss-status` | `enabled=false`, `running=false`, `broadcast=false` |
| Logs since `15:27:00Z` | the apply `POST …/network/apply` 200, the env_sync line, and the provider registrations above. No `shadow/start`, no `scanner/start`, no rollback |

Container env `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false` are the original container spec. They were not rewritten.

---

## Checklist

| # | Check | Result |
|---:|---|---|
| 1 | Running backend/runtime read | **PASS** — same pid `2830498`, StartedAt unchanged, RestartCount 0 |
| 2 | Live provider registry for all six | **PASS** |
| 3 | Provider 0 = Alchemy A `cd505118`, provider 1 = Alchemy B `124bc59c` | **PASS** |
| 4 | No public RPC on the six chains | **PASS** — public Base provider absent |
| 5 | `ce00e63d` absent | **PASS** |
| 6 | Chain ids 1, 42161, 8453, 10, 137, 56 | **PASS** on every probe |
| 7 | Running app resolves the configured endpoints | **PASS** — live env flags plus registry ids plus Base `rpc/check` |
| 8 | `eth_chainId` and `eth_blockNumber` on the effective path | **PASS** for all six index-0 endpoints; index 1 also passed |
| 9–15 | No tx, signing, APPLY, edit, restart, SHADOW, PAPER, or mode change | **PASS** — none performed |

**RUNTIME_CONFIG_VERIFIED**

**STOP.** Do not start SHADOW.
