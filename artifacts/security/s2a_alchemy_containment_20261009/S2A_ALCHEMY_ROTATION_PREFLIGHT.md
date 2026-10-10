# S2-A — Alchemy key-rotation preflight (READ-ONLY)

**Mode:** Read-only. **No** key create/rotate/revoke, **no** Mongo/ENV/container/image mutations.  
**Preflight UTC:** `2026-10-09T12:51Z` (approx.)  
**Verdict: GO — READY FOR SEPARATE ROTATION AUTHORISATION**  
Rotation / revocation remain **NOT AUTHORISED** by this document.

Secrets appear only as `sha256(path_segment_or_token)[:8]` (`fp8`). No raw credentials are printed or committed.

---

## Executive summary

| Gate | Status |
|---|---|
| S2-A redaction image live + healthy | **PASS** — `sha256:69fe2459…` |
| SHADOW / AUTOEXEC=false / RUNTIME=false | **PASS** |
| Legacy b7/h05/w1 stopped | **PASS** |
| Fresh logs still clean (60m) | **PASS** — 1593 httpx Alchemy lines, **0** unredacted |
| Credential inventory (fp8) refreshed | **PASS** — Mongo + ENV + legacy + adjacent |
| Config authority traced | **PASS** — Mongo Network Config drives live multi-RPC after `env_sync` |
| Replacement keys created | **NOT DONE** (operator prerequisite) |
| Alchemy dashboard access proven from this task | **UNCONFIRMED** (operator prerequisite) |

**Recommendation:** **GO** to seek explicit rotation authorisation **after** replacement keys exist and the cutover checklist below is accepted. Do **not** revoke any key until post-cutover acceptance passes.

---

## 1. Deployed S2-A state (verified this preflight)

| Field | Value |
|---|---|
| Container | `arbicore-x-backend-new` |
| Tag | `arbicore-x-backend:s2a-rpc-redact-5bd952568aed` |
| Digest | `sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313` |
| Health | `healthy` · `/api/` → 200 |
| Controls | `SHADOW` · `AUTOEXEC=false` · `RUNTIME=false` |
| Redaction module | present; `install_credential_url_log_redaction` wired in `server.py` |
| Rollback pin (unchanged) | Hybrid-E `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |

Evidence: live `docker inspect`; prior `S2A_PHASE2_DEPLOYMENT.md` / `.json`.

---

## 2. Consumer → fingerprint mapping

### 2.1 Production effective set (must rotate before revoke)

| fp8 | Role | Authoritative store | Effective consumer |
|---|---|---|---|
| **`24dab5d1`** | **Primary** (`rpc_urls.<chain>[0]`) all six EVM chains | Mongo `arbicore_x.arbicore_config` `_id=network` | Live provider registry after startup `env_sync` → `PROVIDER_RPC_URLS_<CHAIN>` (in-process). Dominates redacted httpx traffic (`*.g.alchemy.com`). |
| **`e315c86f`** | Fallback index 1 | Mongo network | Registered as `rpc_<chain>_1_*` after sync; idle unless failover |
| **`dc432a6b`** | Fallback index 2 | Mongo network | same |
| **`6e67e161`** | Fallback index 3 | Mongo network | same |
| **`cd505118`** | Fallback index 4 | Mongo network | same |
| **`124bc59c`** | Fallback index 5 | Mongo network | same |
| **`5e5d5bb1`** | Bootstrap / compose / `.env` | `deployment/upgrade/backend/.env` + container `Config.Env` | Used **before** `env_sync` and by any code path that reads compose ENV without going through managed provider lists; also `ARBICORE_ARCHIVE_RPC_URL`. **Still present** after sync in on-disk ENV (in-process primary for Base is overwritten from Mongo). |

Chains in Mongo `rpc_urls`: `base`, `ethereum`, `arbitrum`, `optimism`, `polygon`, `bnb` — **6 URLs each**, same fp order as Base:

`[0]=24dab5d1 … [5]=124bc59c`.

Mongo revision (identity only): `revision_id=rev-37e7b2123cda4d658fc7f5daf7ceaa81`, `updated_at=2026-10-08T05:09:17Z`, `updated_by=admin`.

### 2.2 Non-production / adjacent (do not assume unused)

| fp8 | Where seen | Status | Rotation note |
|---|---|---|---|
| **`ce00e63d`** | Stopped legacy: `arbicore-x-b7-candidate`, `h05`, `w1`, `arbicore-x-backend` Config.Env | Containers **exited** | Revoke candidate in Alchemy UI; **do not start** these containers |
| **`a7961b2b`** | Running `arbicore-g5-79-app` `PROVIDER_RPC_URLS_BASE` (CSV includes Alchemy) | **Running**, separate stack | **Out of production backend scope** — confirm ownership before any shared-app revoke; do not treat as unused |
| **`ff5eb596`** | Cited in prior remediation notes only | **Not observed** in this preflight’s container ENV scan | Treat as **unresolved** until Alchemy dashboard inventory confirms presence/absence |

### 2.3 Explicit non-Alchemy / empty

| Item | Note |
|---|---|
| Compose `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` (no key) — overwritten in-process for Base primary after `env_sync` |
| `ALCHEMY_API_KEY` on prod backend-new | empty |
| `arbicore-x-opportunity-center`, `factory-backend`, `factory-runner` | No Alchemy RPC env hits in this scan |

Evidence files:

- `rotation_preflight_mongo_fps.json`
- `rotation_preflight_env_live.json` (compose/Config.Env view)
- `rotation_preflight_dotenv_fps.json`
- `rotation_preflight_other_consumers.json`
- `live_key_fingerprints.json` (Phase 1; agrees with refreshed Mongo set)

---

## 3. Authoritative configuration source (per chain)

```
Mongo Network Config (arbicore_config _id=network)
        │  rpc_urls.<chain>[0..5]
        ▼
startup: ensure_seed_from_env() then sync_env_from_network_config()
        │  (image loops SUPPORTED_CHAINS; sets ARBICORE_RPC_URL_<CHAIN>,
        │   Base-only ARBICORE_RPC_URL, and managed PROVIDER_RPC_URLS_<CHAIN>)
        ▼
providers.bootstrap._rpc_urls(chain)
        │  precedence: PROVIDER_RPC_URLS_* > PROVIDER_RPC_URL_* >
        │              ARBICORE_RPC_URL_* > ARBICORE_RPC_URL > defaults
        ▼
EthJsonRpcProvider registry (6 Alchemy endpoints/chain after sync)
```

**Observed startup sequence (S2-A recreate, redacted):**

1. ~`11:42:25Z` — initial bootstrap registers **1** RPC/chain from compose ENV (Base = `mainnet.base.org`; others Alchemy bootstrap).  
2. ~`11:42:28Z` — `env_sync: exported 19 var(s) … (chains=base,ethereum,arbitrum,optimism,polygon,bnb)`.  
3. Immediately after — registry re-registers **6** `*.g.alchemy.com` providers per chain (Mongo list).

**Implications for rotation:**

| Surface | Must update? | Why |
|---|---|---|
| Mongo `rpc_urls` (all chains, all indices intended to remain) | **YES — primary** | Live traffic after sync |
| `deployment/upgrade/backend/.env` (`5e5d5bb1` URLs + archive) | **YES** | Bootstrap before sync; archive; recreate seed; any ENV-only readers |
| In-process only | Refresh via Network Config **apply** API **or** backend recreate on same S2-A image | `env_sync` on apply/startup |
| Working-tree `arbicore-x-v2/.../env_sync.py` | **Do not rely on tree** | Host tree copy is **older** (single-chain default); **running image** syncs all `SUPPORTED_CHAINS` |

UI apply path (no trading-mode change): `POST /api/arbicore/settings/network/apply` → `sync_env_from_network_config` (server.py ~5996/6024/8675).

---

## 4. Remaining consumers of old credentials

| Consumer | Old fps | Action before revoke |
|---|---|---|
| Prod backend-new (live) | Mongo set + ENV `5e5d5bb1` | Cutover Mongo + `.env`, then apply/recreate |
| Docker json-file history (pre- and post-redact) | Pre-redact: raw URLs; post-redact: markers only | Restrict access; scrub **separate** approval |
| Legacy stopped containers | `ce00e63d` in Config.Env | Keep stopped; revoke in Alchemy when ready |
| `arbicore-g5-79-app` | **`a7961b2b`** (distinct) | Confirm not same Alchemy app as prod before prod revoke |
| Operator laptops / docs / CI secrets | Unknown | Explicit uncertainty — inventory outside this host |

**Do not infer “unused” from quiet logs:** fallbacks `e315c86f`…`124bc59c` had **no** exclusive log attribution under redaction (all `/v2/[REDACTED]`). They are **registered** and remain **live credentials** until removed from Mongo and revoked.

---

## 5. Replacement-key prerequisites

Before seeking cutover authorisation, operator must:

1. **Alchemy UI access** for every app that owns fps: `24dab5d1`, `e315c86f`, `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c`, `5e5d5bb1`, plus candidates `ce00e63d`, `ff5eb596?`, and clarity on `a7961b2b` (g5.79).  
2. **Create** replacement keys (label e.g. `arbicore-prod-YYYYMMDD-primary` / `-fbN`). Prefer one primary + N fallbacks **or** a documented collapse of fallback count — **do not change failover semantics accidentally**.  
3. Record **new fp8s only** in an operator-private note (never chat/git).  
4. Stage full URLs privately: `https://<chain-host>.g.alchemy.com/v2/<newkey>`.  
5. Confirm intended hosts per chain match current hosts (Base/Eth/Arb/Op/Polygon/BNB Alchemy hostnames above).  
6. Keep **old keys valid** until acceptance (§8).  
7. Preserve posture: SHADOW, AUTOEXEC=false, RUNTIME=false, signing/broadcast off, legacy stopped, **no P2**, **no vault changes**.

### Safe per-chain validation (pre-revoke)

For each chain in `{base, ethereum, arbitrum, optimism, polygon, bnb}`:

1. After cutover sync/recreate: confirm Mongo primaries’ **new** fp8 via the same fingerprint probe used here (no raw URL dump).  
2. Confirm provider registry logs show six (or chosen N) `rpc_<chain>_*_<alchemy-host>` registrations.  
3. `eth_blockNumber` (or existing health endpoint) per chain — expect HTTP 200 / hex block; **not** 401/403.  
4. Spot-check Base archive path if still required (`ARBICORE_ARCHIVE_RPC_URL` new fp).  
5. Confirm controls still SHADOW / autostarts false.

---

## 6. Proposed cutover order (NOT EXECUTED)

Execute **only** under a later explicit rotation authorisation.

| Step | Action | Health gate | Rollback trigger |
|---|---|---|---|
| 0 | Precheck: S2-A digest `69fe2459…`, healthy, redaction clean, legacy stopped | Fail → **abort** | n/a |
| 1 | Create replacement keys in Alchemy (no revoke) | Keys listed in UI | n/a |
| 2 | Update Mongo `network.rpc_urls` (all chains) to new URLs; keep list length/order policy | Fingerprint probe shows **only** new fp8s in Mongo | Restore previous network revision / known-good rpc_urls backup |
| 3 | Update `.env` bootstrap + archive off `5e5d5bb1` to new fps (or intentional public endpoints) | Dotenv fp scan shows no old `5e5d5bb1` | Restore `.env` from backup |
| 4 | Apply Network Config **or** recreate backend-new on **same** S2-A image + override (SHADOW flags unchanged) | healthy; `/api/` 200; env_sync log; 6 providers/chain | Recreate using prior Mongo revision + prior `.env`; image stays S2-A |
| 5 | Per-chain validation (§5) | All chains pass | Roll back config (§ below) **before** any revoke |
| 6 | One-hour clean-log + error/429 watch (§7) | Gates green | Investigate; rollback config if auth failures |
| 7 | **Revoke** old fps in Alchemy (prod set, then legacy candidates) | Controlled probe with revoked URL → 401/403; logs stay redacted | Cannot un-revoke — only mitigate by ensuring new keys serve all consumers |
| 8 | Optional: historical log scrub | Separate approval | n/a |

### Rollback conditions (config — prefer before revoke)

- Backend unhealthy / API non-200 after apply/recreate.  
- Any chain eth_blockNumber / health fails with **401/403**.  
- Sudden sustained **429** or **5xx** vs preflight baseline (§7).  
- Fingerprint probe still shows an **old** fp that should have been replaced (incomplete cutover).  
- Unexpected need to enable LIVE/signing or start legacy containers → **STOP**, report BLOCKED mid-change.

**Image rollback** to Hybrid-E `40b2116b…` is **not** the first choice for a bad key cutover (would re-expose URLs in logs). Prefer Mongo/ENV rollback **while staying on S2-A redaction image**.

### Provider-side revocation checks

1. In Alchemy UI: key status = revoked/deleted for each old fp.  
2. From a **controlled** operator probe (not production logs): request with old URL expects auth failure.  
3. Production logs must continue to show only `/v2/[REDACTED]` (redaction still installed).  
4. Confirm g5.79 `a7961b2b` **unaffected** if it is a different app key.

---

## 7. One-hour clean-log verification & telemetry

### 7.1 Preflight baseline (last 60m on current keys, redaction on)

| Metric | Value |
|---|---|
| Window | `docker logs --since 60m` @ preflight |
| httpx lines | 1593 |
| `/v2/[REDACTED]` | 1593 |
| Unredacted `alchemy.com/v2/<token>` | **0** |
| httpx lines with `429` | 2 |
| httpx `5xx` | 0 |
| httpx `401`/`403` | 0 |
| Failover keyword lines | 0 |

Evidence: `rotation_preflight_log_baseline_60m.json`.

### 7.2 Post-rotation 1h acceptance measurements

Because redaction hides key material, **log cleanliness ≠ proof of new key identity**. Combine:

| Check | Method | Pass criteria |
|---|---|---|
| Clean logs | `docker logs --since 60m` regex: unredacted Alchemy `/v2/` count | **0** |
| Redaction still active | Count `/v2/[REDACTED]` | **>0** under traffic |
| Auth health | Count httpx `401`/`403` in window | **≈0** (spike → rollback) |
| Rate limit | Count httpx `429` vs baseline (~2/h) | No large sustained spike unexplained |
| Upstream errors | httpx `5xx` | No material regression |
| Failover pressure | Registry/failover logs; rise of non-primary provider use if measurable | Investigate before revoke |
| Endpoint health | Per-chain block/health probes | All configured chains OK |
| Config identity | Fingerprint probe Mongo + `.env` | Old prod fps **absent**; new fps **present** |

**Do not** disable redaction to “see” new keys in logs.

---

## 8. Post-rotation acceptance criteria (for future authorisation)

1. Backend still on S2-A digest `69fe2459…`, healthy, SHADOW / AUTOEXEC=false / RUNTIME=false.  
2. Legacy containers still exited.  
3. Mongo + `.env` fingerprints contain **no** old prod fps (`24dab5d1`, fallbacks, `5e5d5bb1`) unless intentionally retained.  
4. Per-chain health probes pass.  
5. One-hour log gate: **0** unredacted credential URLs; no auth-failure storm.  
6. Only then: Alchemy revoke of old keys + revocation checks.  
7. g5.79 / other stacks confirmed intact.  
8. Incident record updated; historical Docker logs remain access-restricted until scrub approval.

---

## 9. Unresolved uncertainties (explicit)

1. **Alchemy dashboard access / app ownership** for each fp8 was **not** verified from this host.  
2. **`ff5eb596`** not found in scanned container ENV — may still exist in Alchemy or other hosts.  
3. **Fallback keys** show no exclusive recent log traffic under redaction; **cannot** treat as unused.  
4. **`a7961b2b` on g5-79** relationship to prod Alchemy apps unknown — revoke risk if shared.  
5. **In-process `PROVIDER_RPC_URLS_*`** after `env_sync` are **not** visible via `docker exec` Config.Env; rely on startup logs + Mongo fingerprints + apply/recreate.  
6. **Host git tree `env_sync.py`** differs from **running image** (all-chain sync) — operators must not assume tree == prod.  
7. **Archive RPC** consumer coverage beyond ENV presence not fully exercised this preflight.  
8. **Off-host copies** of keys (backups, laptops, CI) not inventoried.  
9. **Historical json-file logs** still hold pre-redaction secrets — access control assumed, scrub not done.  
10. Absence of a fingerprint in **recent** logs is **not** evidence the credential is unused.

---

## 10. Evidence index

| Artifact | Content |
|---|---|
| `S2A_PHASE2_DEPLOYMENT.md` / `.json` | Deploy record |
| `rotation_preflight_mongo_fps.json` | Live Mongo fp map |
| `rotation_preflight_dotenv_fps.json` | `.env` fps |
| `rotation_preflight_env_live.json` | Container Config.Env fps |
| `rotation_preflight_other_consumers.json` | Legacy + g5.79 |
| `rotation_preflight_log_baseline_60m.json` | 60m clean-log baseline |
| `live_key_fingerprints.json` | Phase 1 inventory |
| `S2A_ALCHEMY_REMEDIATION_PLAN.md` §6 | Earlier rotation sketch |

---

## Verdict

**GO — READY FOR SEPARATE ROTATION AUTHORISATION**

Preconditions for a later cutover approval: replacement keys created, Mongo+`.env` change plan accepted, 1h acceptance metrics agreed, revoke deferred until validation passes.  

**This preflight did not rotate or revoke any credential and did not change production configuration.**
