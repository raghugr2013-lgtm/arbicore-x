# Alchemy PAYG — Post-APPLY Verification (READ-ONLY) — 2026-10-03

- **Status:** **READ-ONLY verification** — no APPLY, no restart/recreate, no deploy, no source/env mutation, no remediation
- **Fetched (UTC):** `2026-10-03T05:00:23Z` (primary evidence window; APPLY at `2026-10-03T04:57:17Z`)
- **Container:** `arbicore-x-backend-new` · Image `arbicore-x-backend:ws-a-befb14e-20261002`
- **Secrets policy:** Alchemy credentials never printed. Fingerprint = `sha256(<key>)[:8]` where `<key>` is the path segment after `/v2/`. URLs shown as `https://<host>/v2/<REDACTED:fp=…>`.

**Prior plans:** `ALCHEMY_PAYG_NETWORK_CONFIG_CHANGE_PLAN_20261003.md`, `ALCHEMY_PAYG_CONFIG_DISCOVERY_20261002.md`, `BASE_ALCHEMY_ROOT_CAUSE_AUDIT_20261002.md`.

---

## Executive summary

| Item | Result |
|---|---|
| **PRIMARY fingerprint** | **`cd505118`** (`base-mainnet.g.alchemy.com`) |
| **FALLBACK hostname** | **`mainnet.base.org`** |
| **Stale `ce00e63d`** | **ABSENT** (Network Config, effective Base RPC path, ProviderRegistry Base slots, Docker `.env` Base/Alchemy path scan) |
| **Primary health** | **OK** — HTTP 200, `eth_chainId=8453`, `eth_blockNumber≈52107121` |
| **Fallback health** | **OK** — HTTP 200, `eth_chainId=8453`, `eth_blockNumber≈52107122` |
| **env_sync status** | **OK** — APPLY triggered sync (`exported 4 var(s)`); no later overwrite; Network Config + live primary still PAYG |
| **Safety state** | **SHADOW ON**; `AUTOEXEC_AUTOSTART=false`; `RUNTIME_AUTOSTART=false`; kill engaged; `live_execution_enabled=false`; `auto_execute_enabled=false` |
| **Container restart** | **None** — StartedAt unchanged from T0; RestartCount=`0` |
| **Overall** | **PASS** (checks 1–12) |

---

## Checks 1–12

| # | Check | Verdict | Evidence |
|---:|---|---|---|
| **1** | Mongo Network Config `rpc_urls.base[]` ordering | **PASS** | `[0]` Alchemy PAYG · `[1]` `https://mainnet.base.org` |
| **2** | Fingerprint Alchemy `/v2/<key>` as sha256[:8] | **PASS** | **`cd505118`** (≠ `ce00e63d`, ≠ `5e5d5bb1`) |
| **3** | Stale `ce00e63d` absent from Network Config / effective Base RPC / env_sync path | **PASS** | No `ce00e63d` in Network Config Alchemy fps; ProviderRegistry Base = alchemy then `mainnet.base.org`; Docker `.env` Base scan has no `ce00e63d` |
| **4** | New PAYG fingerprint actually used (logs/env/API) | **PASS** | `GET /api/arbicore/rpc/check` → `rpc_url_masked=base-mainnet.g.alchemy.com`; providers `rpc_base_0_base-mainnet_g_alchemy_c` |
| **5** | env_sync did not overwrite newly applied config | **PASS** | APPLY `04:57:17Z` → `env_sync: exported 4 var(s)`; only prior sync was startup `2026-10-02T15:09:08Z`; no subsequent env_sync; live Network Config still PAYG primary |
| **6** | Primary RPC health (`eth_chainId` / `eth_blockNumber`) | **PASS** | Alchemy: HTTP **200**, chainId **8453**, block **52107121** |
| **7** | Fallback RPC health (`eth_chainId` / `eth_blockNumber`) | **PASS** | `mainnet.base.org`: HTTP **200**, chainId **8453**, block **52107122** |
| **8** | Primary-first ordering | **PASS** | Network Config index order; ProviderRegistry priorities Base `100` (Alchemy) then `101` (`mainnet.base.org`); `rpc/check` uses Alchemy |
| **9** | SHADOW ON | **PASS** | `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_SHADOW_CERT_ENABLED=true` (Docker Config.Env / override) |
| **10** | AUTOEXEC=false | **PASS** | `ARBICORE_AUTOEXEC_AUTOSTART=false`; execution settings `auto_execute_enabled=false` |
| **11** | RUNTIME=false; signing/broadcast disabled | **PASS** | `ARBICORE_RUNTIME_AUTOSTART=false`; safety `live_execution_enabled=false`, kill **engaged** (`boot_default`); flash_loan strategy mode **SHADOW** |
| **12** | No container restart from APPLY | **PASS** | StartedAt=`2026-10-02T15:08:52.884157323Z` (**same as T0**); RestartCount=`0` |

---

## 1. Network Config `rpc_urls.base[]` (canonical)

| Field | Value |
|---|---|
| **revision_id** | `rev-7c93bb93e65b4f5a9b7340bf513437c0` *(was `rev-615fa528…` pre-APPLY)* |
| **updated_at** | `2026-10-03T04:57:17.836236+00:00` |
| **updated_by** | `admin` |
| **draft** | `null` |

| Index | Role | Host | Path | fp8 |
|---:|---|---|---|---|
| **0** | **PRIMARY** | `base-mainnet.g.alchemy.com` | `/v2/<REDACTED>` | **`cd505118`** |
| **1** | **FALLBACK** | `mainnet.base.org` | `/` | n/a |

`chains_enabled.base=true`; other chains OFF with empty/absent RPC lists in Network Config.

---

## 2–4. Fingerprints & effective use

| Fingerprint | Present in Network Config? | Role |
|---|---|---|
| **`cd505118`** | **YES** — `rpc_urls.base[0]` | **PAYG PRIMARY (expected)** |
| `ce00e63d` | **NO** | Stale (retired) |
| `5e5d5bb1` | **NO** (not in Network Config Base) | Docker `.env` bootstrap / non-Base singles only |

**Live primary API:** `GET /api/arbicore/rpc/check` → `status=READY`, `chain_id=8453`, `block_number=52107138`, `rpc_url_masked=base-mainnet.g.alchemy.com`, `is_base_mainnet=true`.

**ProviderRegistry (Base RPC):**

| provider_id | priority | status |
|---|---:|---|
| `rpc_base_0_base-mainnet_g_alchemy_c` | 100 | HEALTHY |
| `rpc_base_1_mainnet_base_org` | 101 | HEALTHY |

---

## 5. env_sync (APPLY path)

| When (UTC) | Event |
|---|---|
| `2026-10-02T15:09:08Z` | Startup sync — exported 5 vars incl. `PROVIDER_RPC_URLS_BASE` (pre-PAYG Network Config) |
| `2026-10-03T04:57:17Z` | **APPLY** → `env_sync: exported 4 var(s) (chain=base)` then `POST …/network/apply` **200** |
| After APPLY → verify | **No further env_sync lines** |

Expected APPLY export set (executor empty → 4 vars): `ARBICORE_RPC_URL`, `ARBICORE_RPC_URL_BASE`, `BASE_RPC_URL`, `PROVIDER_RPC_URLS_BASE`.

**Note (observability only):** Linux `/proc/<pid>/environ` still shows Docker **bootstrap** values (`ARBICORE_RPC_URL` fp `5e5d5bb1`, `ARBICORE_RPC_URL_BASE=mainnet.base.org`, no `PROVIDER_RPC_URLS_BASE`). That snapshot does **not** reliably reflect post-`putenv` `os.environ` updates. Effective post-APPLY state is taken from Network Config + `rpc/check` + ProviderRegistry + env_sync audit logs (not `/proc` environ).

**Docker `.env` (non-authoritative for Base while Network Config non-empty):** still carries fp `5e5d5bb1` on global/archive/non-Base Alchemy singles; Base primary line remains `mainnet.base.org`; **`ce00e63d` absent**. Recreate durability mirror is **out of scope** for this read-only verify (called out in the change plan as a separate step).

**Separate surface:** `GET /api/arbicore/config/runtime` still lists Base as `["https://mainnet.base.org"]` only — that RuntimeConfig document is **not** the Network Config / env_sync Base failover list. Authoritative Base ordering for this APPLY is Network Config → env_sync → `rpc/check` / ProviderRegistry.

---

## 6–7. Dual Base endpoint RPC probes (read-only)

Probed from inside the backend container using Network Config URLs (credentials never printed).

| Role | Host | fp8 | `eth_chainId` | `eth_blockNumber` |
|---|---|---|---|---|
| PRIMARY `[0]` | `base-mainnet.g.alchemy.com` | **`cd505118`** | HTTP **200**, chainId **8453** | HTTP **200**, block **52107121** |
| FALLBACK `[1]` | `mainnet.base.org` | n/a | HTTP **200**, chainId **8453** | HTTP **200**, block **52107122** |

---

## 8. Primary-first confirmation

1. Network Config list order: Alchemy → public Base  
2. ProviderRegistry Base priorities: `100` Alchemy, `101` `mainnet.base.org`  
3. `rpc/check` masked primary host: `base-mainnet.g.alchemy.com`

---

## 9–11. Safety posture (unchanged by APPLY)

| Control | Observed |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `ARBICORE_SCANNER_AUTOSTART` | `true` |
| Execution settings `auto_execute_enabled` | `false` |
| Safety `live_execution_enabled` | `false` |
| Kill | **engaged** (`reason=boot_default`, since `2026-10-02T15:09:00Z`) |
| flash_loan_arbitrage mode | `SHADOW` |

Signing/broadcast paths remain gated (kill + SHADOW / non-live execution). No APPLY-related enablement of AUTOEXEC/RUNTIME/live observed.

---

## 12. Container identity (APPLY must not restart)

| Field | T0 (post-fix cutover) | Now | Match |
|---|---|---|---|
| StartedAt | `2026-10-02T15:08:52.884157323Z` | `2026-10-02T15:08:52.884157323Z` | **YES** |
| RestartCount | `0` | `0` | **YES** |
| Image | `arbicore-x-backend:ws-a-befb14e-20261002` | same | **YES** |
| Health | — | `healthy` | — |

---

## Verdict

**PASS** — Alchemy PAYG is live as Base primary (`cd505118`); public Base is sole fallback; stale `ce00e63d` is absent from the effective Base Network Config path; both endpoints healthy; env_sync applied once at APPLY without later overwrite; SHADOW safety unchanged; container not restarted.

**No remediation performed.** Optional follow-ups (not executed): mirror PAYG URLs into `deployment/upgrade/backend/.env` for recreate durability; reconcile `/api/arbicore/config/runtime` Base list if that surface is used by any consumer outside Network Config/env_sync.
