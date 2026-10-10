# R3-APPLY — MongoDB least-privilege remediation (execution report)

**Verdict: PASS WITH LIMITATIONS**  
**Authorisation:** R3-APPLY only  
**Final evidence dir:** `artifacts/security/r3_mongo_leastpriv_apply_20261010T105128Z/`  
**Related create/backup evid:** `…/r3_mongo_leastpriv_apply_20261010T102900Z/`  
**Overall security gate / P2:** **BLOCKED** (unchanged — R4/R5/R6 open)

---

## Timeline (UTC)

| Time | Stage | Result |
|---|---|---|
| `10:24:40Z` | Pre-apply checks | **PASS** (backup validated; digest `69fe2459…`; controls; R1/R2; targets unambiguous) |
| `10:29:00Z`–`10:32:xxZ` | Apply-time `mongodump` (authenticated INITDB env) | **PASS** (~463 MB, `0600`) |
| `10:33:xxZ` | `createUser arbicore_app` + offline verify | User **created**; isolation OK; orchestrator false-failed on `listDatabases` (see deviations) |
| `10:44:53Z` | Re-run create | Aborted — user already present (expected) |
| `10:51:28Z`–`10:52:xxZ` | `.env` `MONGO_URL` → `arbicore_app`; recreate `backend` | **PASS** · healthy · digest unchanged |
| `10:53:18Z`–`10:53:30Z` | Post-apply verification | **PASS WITH LIMITATIONS** |

---

## Actions performed (exact scope)

1. Confirmed validation backup + took apply-time authenticated dump of `arbicore_x`.  
2. Created MongoDB user **`arbicore_app`** on `admin` with roles **exactly** `[{ role: "readWrite", db: "arbicore_x" }]`.  
3. Switched **only** ArbiCore `…/upgrade/backend/.env` `MONGO_URL` username/password (host `factory-mongo:27017`, `authSource=admin`, `DB_NAME=arbicore_x` unchanged).  
4. Recreated **only** compose service `backend` → container `arbicore-x-backend-new` with `--pull never` + S2-A override.  
5. **Did not** change Factory URIs, root account, RPC config, g5.79, Foreman, legacy containers, or enable execution.

Credential delivery: password generated to `0600` escrow file; `createUser` via in-container script reading that file; root auth via `MONGO_INITDB_*` inside `docker exec` (never host argv). Reports attest **username + password sha12 only**.

---

## Backup evidence

| Item | Path |
|---|---|
| Validation (pre-auth) | `/home/raghu/arbicore_backups/r3_backup_validation_20261010T101234Z/arbicore_x_20261010T101234Z.archive.gz` · `validation_passed: true` |
| Apply-time dump | `/home/raghu/arbicore_backups/r3_mongo_leastpriv_20261010T102900Z/` (+ meta in `prior_102900Z_apply_backup_meta.json`) |
| Pre-switch `.env` | `…/r3_mongo_leastpriv_20261010T105128Z/backend.env.pre-r3` and `…/102900Z/backend.env.pre-r3` (mode `0600`) |
| App password escrow | `…/r3_mongo_leastpriv_20261010T102900Z/arbicore_app.password` (`0600`; not printed) |

---

## Before / after

| Item | Before | After |
|---|---|---|
| Backend digest | `sha256:69fe2459…e7315313` | **unchanged** |
| Backend health | healthy | **healthy** |
| ArbiCore `MONGO_URL` user | `root` | **`arbicore_app`** |
| App DB | `arbicore_x` | `arbicore_x` |
| Factory mongo user | `root` | **`root` (unchanged)** |
| Discovery docs | 3 921 188 | 3 921 188 |
| TTL indexes | 17 | **17** |

---

## Verification (executed)

| Check | Result |
|---|---|
| `/api/` local + public | **200** |
| Admin login + `/api/auth/me` (cookie) | **200** |
| App user ping / CRUD / createIndex+dropIndex | **PASS** |
| Isolation: `strategy_factory_v1` denied; `createUser` denied; `listDatabases` → only `arbicore_x` | **PASS** |
| Roles exact `readWrite@arbicore_x` | **PASS** |
| R1 public `/docs` | **404** |
| R2 `POST /api/auth/setup` | **503** |
| SHADOW / AUTOEXEC=false / RUNTIME=false / no BOOTSTRAP | **PASS** |
| Alchemy key fps `ca6545ba` on ETH/ARB/OP/POLY/BNB (+ primary) | **PASS** |
| Factory healthy + still root | **PASS** |
| Legacy stopped; g5.79 + Foreman untouched | **PASS** |
| No Mongo auth errors in backend log tail | **PASS** |

Evidence: [`post_apply_verification.json`](post_apply_verification.json)

---

## Five-vs-six Alchemy fingerprint (read-only)

Six chain RPC URL env keys remain present. Alchemy `/v2/` key fingerprint **`ca6545ba`** is shared by Ethereum, Arbitrum, Optimism, Polygon, BNB, and primary/archive URLs. **BASE** continues to use public `mainnet.base.org` (no Alchemy key → fps `null`). This is pre-existing configuration; **not modified** by R3.

---

## Deviations

1. First orchestrator run marked offline verify **FAIL** because `listDatabases` succeeded. On MongoDB 7 a scoped user may run `listDatabases` and receive **only** authorized DB names (`["arbicore_x"]`). Factory access remained denied. Resume proceeded without `dropUser`.  
2. Empty probe collection `r3_apply_probe` may remain (doc deleted); not removed (no unrelated cleanup).  
3. Brief API blip during `--force-recreate` (~healthy within &lt;1 min).

**Rollback:** not required. Script: [`rollback.sh`](rollback.sh).

---

## Limitations (do not clear overall gate)

- Factory still on root (peer project; out of R3 scope).  
- BASE public RPC endpoint pre-existing.  
- Historical ransomware note + pre-2026-09-07 log coverage gap (decision package).  
- R4, R5, R6 **not** addressed.  
- P2 / live execution / signing-broadcast enablement **still blocked**.

---

## Safety state (runtime)

- Execution mode: **SHADOW**  
- AUTOEXEC / RUNTIME autostart: **false**  
- Signing/broadcast: not enabled (no private-key ENV; signer address only)  
- Digest: **`69fe2459…`**  
- R1/R2: held  

**Stopped after R3 report — awaiting review. No P2, R4–R6, or execution activation.**
