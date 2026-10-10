# S2-A — Alchemy key exposure containment (Phase 1 plan)

**Mode:** Phase 1 **READ-ONLY** discovery. No production modification, no key rotation, no P2, no vault changes.  
**Discovery window (UTC):** `2026-10-09T11:22Z` – `2026-10-09T11:29Z`  
**Host / backend:** `arbicore-x-backend-new` · image `arbicore-x-backend:hybrid-e-rpc-9244ebd` · digest `sha256:40b2116b…`  
**Posture at discovery:** `SHADOW` · AUTOEXEC=`false` · runtime autostart=`false` · legacy b7/h05/w1 **exited**  

**Verdict: READY FOR HUMAN AUTHORISATION** (redaction patch + controlled rotation).  
Phase 2 production changes remain **blocked** until separate explicit approval.

Secrets appear only as `sha256(path_segment)[:8]` fingerprints. **No full keys or key-bearing URLs are reproduced.**

---

## Executive summary

| Finding | Detail |
|---|---|
| Leak mechanism | `httpx` logs every HTTP request at **INFO** with the **full URL**, including Alchemy `/v2/<api-key>` |
| Why redaction vanished | S1/F2-B-LITE image `f2b-lite-rpc-redact-4a00171` included `arbicore/log_redaction.py` + `install_credential_url_log_redaction()` after `logging.basicConfig`. Hybrid-E image `hybrid-e-rpc-9244ebd` was built **without** that module/wiring and superseded the redaction image |
| Active traffic key (60m logs) | fp8 **`24dab5d1`** only (host `base-mainnet.g.alchemy.com`, ~1523 httpx INFO lines / 60m) |
| Config key inventory | ENV bootstrap fp8 **`5e5d5bb1`**; Mongo `arbicore_config._id=network` holds six Alchemy keys per chain (fps below) — **runtime RPC for Base prefers Mongo list primary `24dab5d1`**, not the ENV bootstrap key |
| App-level mitigations | Quoter `_redact_host()` only logs hostname — **does not** stop httpx’s own logger |
| Source trees | `log_redaction.py` **absent** from both `arbicore-x-cert` and `arbicore-x-v2` working trees; recoverable from image `f2b-lite-rpc-redact-4a00171` |

---

## 1. Sources of Alchemy RPC URLs / API keys

### 1.1 Environment (container / compose `env_file`)

| Env var | Host (identity only) | Key fp8 |
|---|---|---|
| `ARBICORE_RPC_URL` | `base-mainnet.g.alchemy.com` | `5e5d5bb1` |
| `ARBICORE_ARCHIVE_RPC_URL` | `base-mainnet.g.alchemy.com` | `5e5d5bb1` |
| `ARBICORE_RPC_URL_ETHEREUM` | `eth-mainnet.g.alchemy.com` | `5e5d5bb1` |
| `ARBICORE_RPC_URL_OPTIMISM` | `opt-mainnet.g.alchemy.com` | `5e5d5bb1` |
| `ARBICORE_RPC_URL_POLYGON` | `polygon-mainnet.g.alchemy.com` | `5e5d5bb1` |
| `ARBICORE_RPC_URL_BNB` | `bnb-mainnet.g.alchemy.com` | `5e5d5bb1` |
| `ARBICORE_RPC_URL_ARBITRUM` | `arb-mainnet.g.alchemy.com` | `5e5d5bb1` |
| `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` (public; no Alchemy key) | — |

Evidence: `live_key_fingerprints.json`.

### 1.2 Mongo `arbicore_config` (`_id=network`) — authoritative for live multi-RPC

Managed/network config stores **ordered** Alchemy `/v2/` URLs per chain (`rpc_urls.<chain>[i]`). Sync path: `arbicore/config/env_sync.py` / `persistent.py` / provider bootstrap — **does not change trading logic** when redacting logs.

| Key fp8 | Role (observed) | Chains present |
|---|---|---|
| `24dab5d1` | **Primary** (index 0) — dominates live httpx logs | base, eth, arb, op, polygon, bnb |
| `e315c86f` | Fallback | all six |
| `dc432a6b` | Fallback | all six |
| `6e67e161` | Fallback | all six |
| `cd505118` | Fallback | all six |
| `124bc59c` | Fallback | all six |

Base list length: **6**. Live 60m log window used **only** `24dab5d1` on Base (fallbacks idle in that window).

### 1.3 Code paths that **call** RPCs (read-only; URLs may be secret-bearing)

| Component | Transport | Logs URLs? |
|---|---|---|
| `arbicore/providers/rpc.py` `EthJsonRpcProvider` | `httpx.AsyncClient.post(self.url, …)` | Provider errors use `provider_id` (host-derived); **httpx still logs full URL at INFO** |
| `arbicore/execution/quoter.py` | `httpx` JSON-RPC | App messages use `_redact_host()`; **httpx still leaks** |
| Other `httpx` callers (dex, economics, scanners, connectors, …) | `httpx` | Same httpx INFO behaviour if URL is Alchemy |

### 1.4 Logging / diagnostics / exceptions

| Path | Behaviour |
|---|---|
| Process logging | `logging.basicConfig(level=INFO)` in `server.py` — root INFO enables `httpx` INFO |
| Emitting line shape | `httpx - INFO - HTTP Request: POST https://<host>/v2/<key> "HTTP/1.1 …"` |
| Docker log driver | `json-file` (default) — container logs retain key-bearing lines until rotated |
| Quoter / provider app logs | Prefer host-only / provider_id — incomplete coverage |
| API error responses | Not the dominant leak in this window; still must redact if URLs are echoed |

---

## 2. Why redaction disappeared after Hybrid-E

| Item | Evidence |
|---|---|
| Prior fix | Image `arbicore-x-backend:f2b-lite-rpc-redact-4a00171` contains `/app/arbicore/log_redaction.py` and wires `install_credential_url_log_redaction()` immediately after `logging.basicConfig` in `server.py` |
| Current prod | Image `hybrid-e-rpc-9244ebd` (`sha256:40b2116b…`): **`log_redaction.py` ABSENT**; `server.py` has **no** install call |
| Working trees | Neither `arbicore-x-v2` nor `arbicore-x-cert` currently contain `app/backend/arbicore/log_redaction.py` |
| Mechanism | Hybrid-E rebuild/deploy from a tip that never carried (or dropped) the F2-B-LITE redaction commit; production therefore logs raw httpx URLs again |

Recovered module (for patch baseline): `artifacts/security/s2a_alchemy_containment_20261009/f2b_log_redaction.py`  
Wiring snippets: `f2b_server_logging_snippet.txt` vs `hybrid_server_logging_snippet.txt`.

---

## 3. Where exposed keys have been stored or emitted

| Surface | Status |
|---|---|
| Docker / container logs (`json-file`) | **Active leak** — ~1523 Alchemy URL lines / 60m (fp8 `24dab5d1`) |
| Application INFO via httpx | **Active leak** (same) |
| Mongo `arbicore_config` network doc | **Stored** — six key fps × six chains (ciphertext not encrypted at rest) |
| Backend `.env` / compose env | **Stored** — bootstrap fp8 `5e5d5bb1` |
| Cert `artifacts/` / `reports/` scan (this pass) | **0** files with raw `alchemy.com/v2/<key>` in those trees |
| Upgrade logs dir | No raw hits in this scan |
| Monitoring | No separate Prometheus scrapes of full RPC URLs identified; primary persistence is Docker json-file logs |
| Historical docs/cert reports | May cite **hosts** and **fp8** only (policy); treat any older operator paste as potentially contaminated |

Redacted log samples (keys replaced with fp8 markers): `log_samples_redacted.txt`  
60m summary: `log_exposure_60m.json`.

---

## 4. Active key fingerprints (inventory)

| fp8 | Seen in | Live log (60m) |
|---|---|---|
| `24dab5d1` | Mongo network primary | **Yes** (exclusive in window) |
| `e315c86f` | Mongo fallbacks | No (idle) |
| `dc432a6b` | Mongo fallbacks | No |
| `6e67e161` | Mongo fallbacks | No |
| `cd505118` | Mongo fallbacks | No |
| `124bc59c` | Mongo fallbacks | No |
| `5e5d5bb1` | ENV bootstrap / archive / non-Base ENV chains | No in 60m Base httpx window (ENV not driving Base primary) |

**Prior remediation notes** also referenced legacy ENV fallbacks `ce00e63d` / `ff5eb596` on stopped containers — not re-opened here (legacy must stay stopped). Treat as revoke candidates when rotating.

---

## 5. Minimal remediation patch (NOT APPLIED — awaits Phase 2 approval)

### 5.1 Scope (must / must-not)

**Must:**

1. Add `app/backend/arbicore/log_redaction.py` (port from F2-B-LITE / recovered `f2b_log_redaction.py`).  
2. After `logging.basicConfig(...)` in `server.py`, call `install_credential_url_log_redaction()` (try/except, never fail startup).  
3. Redact:
   - path credentials under `/v2/` and `/v3/`;
   - sensitive query params (`apikey`, `api_key`, `key`, `token`, …);
   - userinfo `user:pass@host`;
   - embedded URLs inside log `msg` and `args` (covers retries / exceptions if they stringify URLs).  
4. Preserve host + path prefix so logs remain useful: e.g. `https://base-mainnet.g.alchemy.com/v2/[REDACTED]`.  
5. Automated tests with **synthetic** credentials only (never production keys).

**Must not:**

- Change RPC routing, fallback order, retry limits, workers, trading/risk logic, vault key, or execution mode.  
- Enable signing / broadcast / LIVE / AUTOEXEC / runtime autostart.  
- Start legacy containers.  
- Deploy P2.

### 5.2 Suggested regression tests (new)

File sketch: `app/backend/tests/test_log_redaction_credential_urls.py`

| Test | Assertion |
|---|---|
| `redact_credential_url` on Alchemy `/v2/SYNTHETIC…` | Output contains host; contains `[REDACTED]`; **does not** contain synthetic token |
| Infura-style `/v3/…` | Same |
| Query `?apikey=SYNTH` | Param value redacted |
| `user:pass@host` | Userinfo redacted |
| `CredentialUrlLogFilter` + `logging.Logger` + httpx-shaped message | Handler stream has no synthetic key |
| Install idempotence | Double `install_*` safe |

Use tokens like `SYNTHETIC_ALCHEMY_KEY_DO_NOT_USE_001` — never live fps.

### 5.3 Before/after evidence protocol (Phase 2)

1. Deploy redaction-only image on **same** digest lineage / recreate backend only after approval.  
2. Generate traffic or wait ≤5m of natural SHADOW traffic.  
3. `docker logs` scan: count `alchemy.com/v2/` **without** `[REDACTED]` must be **0**; lines with `/v2/[REDACTED]` should appear.  
4. Keep posture: SHADOW / AUTOEXEC false / runtime false / legacy stopped.

### 5.4 Rollback

- Recreate `arbicore-x-backend-new` on pinned current digest `sha256:40b2116b…` with existing override `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` (known-good Hybrid-E).  
- Redaction-only failure does not require DB rollback.  
- Do **not** roll forward to P2 as a “fix”.

---

## 6. Key rotation / revocation plan (NOT EXECUTED)

Execute **only after** redaction is live (or simultaneously under one change window), and only with Alchemy dashboard access.

### 6.1 Preconditions

1. Redaction patch merged + image built + recreate approved.  
2. Operator has Alchemy account access for **all** apps owning fps above.  
3. Replacement keys generated in Alchemy (do not paste into chat).  
4. Written rollback: keep old keys valid until new keys verified in SHADOW, then revoke.

### 6.2 Ordered steps

1. **Create** new Alchemy keys (label e.g. `arbicore-prod-YYYYMMDD`) for each app/network as needed.  
2. **Update** Mongo `arbicore_config` `_id=network` `rpc_urls` lists (all chains) to new URLs — preserve list length/order policy unless operator specifies otherwise.  
3. **Update** ENV bootstrap vars currently on `5e5d5bb1` (`ARBICORE_RPC_URL`, archive, per-chain ENV) to new keys or public endpoints as intended.  
4. **Recreate** backend-new on **non-P2** image that includes redaction (same safety flags).  
5. **Verify**: live httpx logs show only `[REDACTED]`; optional eth_blockNumber health per chain; fps in logs must not match old set.  
6. **Revoke/delete** old Alchemy keys for fps: `24dab5d1`, `e315c86f`, `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c`, `5e5d5bb1`, plus legacy `ce00e63d` / `ff5eb596` if still in account.  
7. Confirm revoked keys fail a controlled probe (expected 401/403) without logging raw URLs.  
8. Scrub or rotate Docker json-file logs if operationally required (separate approval — destructive to debug history).

### 6.3 Stop conditions → report **BLOCKED**

- Cannot create replacement keys or access Alchemy revoke UI.  
- New keys fail all chains and rollback to old keys would be needed without redaction still in place.  
- Any step would require enabling LIVE/signing or starting legacy containers.  
- Patch would need RPC routing / worker / risk changes (out of scope).

---

## 7. Residual exposure (even after redaction)

| Residual | Notes |
|---|---|
| Keys remain in Mongo + ENV until rotated | Redaction stops **log** leak; storage still secret-bearing |
| Historical Docker logs | Pre-patch json-file lines still contain old URLs until log rotation/scrub |
| Stopped legacy Config.Env | May hold older Alchemy fps — keep stopped |
| Quoter/host-only helpers | Keep; complementary, not sufficient alone |

---

## 8. Safety confirmation (Phase 1)

- No production config, images, or keys changed by this discovery  
- Legacy containers not started  
- SHADOW / AUTOEXEC false / runtime false preserved  
- Vault key untouched; P2 not deployed  
- Credentials not printed or committed  

---

## 9. Approvals required before Phase 2

Please approve **in writing**, separately:

1. **Implement and deploy** the minimal `log_redaction` patch (+ tests) onto production backend via non-P2 image recreate, preserving SHADOW and autostart flags.  
2. **Rotate/revoke** Alchemy keys per §6 (optional same window or follow-on), including Mongo `network` + ENV updates.  
3. Acknowledgement of rollback pin `sha256:40b2116b…` / Hybrid-E override path.

Until then: **no production modification.**

---

## Evidence index

Directory: `artifacts/security/s2a_alchemy_containment_20261009/`

| File | Purpose |
|---|---|
| `S2A_ALCHEMY_REMEDIATION_PLAN.md` | This plan |
| `f2b_log_redaction.py` | Recovered F2-B-LITE module (patch baseline) |
| `f2b_server_logging_snippet.txt` / `hybrid_server_logging_snippet.txt` | Wiring diff |
| `live_key_fingerprints.json` | ENV + Mongo fp8 inventory |
| `log_exposure_60m.json` | Live leak rate |
| `log_samples_redacted.txt` | Sample lines with keys replaced by fp8 markers |
| `artifact_key_exposure.json` | Artifact/report raw-URL scan |

---

## Verdict

**READY FOR HUMAN AUTHORISATION**

Root cause and fix are known, scoped, and separable from trading logic. Rotation is planned but depends on Alchemy account actions. Phase 2 must not start without explicit approval.
