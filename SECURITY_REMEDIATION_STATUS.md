# ArbiCore X — Execution Security Remediation Status

**Mode:** read-only reconciliation. No credentials rotated, no config changed, no restarts, no signing, no broadcast.  
**Verification timestamp (UTC):** `2026-10-09T05:07:39Z` – `2026-10-09T05:10:42Z`  
**S1-B Phase 1 preflight (UTC):** `2026-10-09T05:16:50Z` – `2026-10-09T05:19:30Z` — see `artifacts/security/s1b_vault_rotation_preflight_20261009/S1B_PHASE1_PREFLIGHT.md`  
**Host:** `vmi3410070`  
**Prior plan sources:**  
- [Security inventory assessment](a15856db-812b-4049-8307-d2c3478ac420) — S1-A inventory + S1-B/F1 + S1/F2-A + S1/F2-B-LITE  
- `docs/certification/ARBiCORE_X_ROOT_CAUSE_AND_BEST_PATH_ANALYSIS_20261005.md` (§11, F1/F2)  
- `docs/certification/FIRST_LIVE_PATH_DECISION_MEMO_20261005.md` (M1/M2)

**Legend**

| Verdict | Meaning |
|---|---|
| **PASS** | Required outcome verified in the **running** production environment |
| **FAIL** | Required outcome not met in production (includes partial/incomplete work) |
| **UNKNOWN** | Insufficient evidence from read-only checks (e.g. provider-side revoke) |

**Scope note:** “Planned / prior gate” is historical evidence only. **Production verdict** is what is true on the live host now.

---

## Executive summary

| # | Item | Completion | Production verdict |
|---|---|---|---|
| 1 | Legacy isolation + single scanner-writer | Complete | **PASS** |
| 2 | Admin password + JWT rotation | Partial (rotated; still plaintext in ENV/files) | **FAIL** |
| 3 | Alchemy key rotation + log redaction | Outstanding (redaction briefly done, then lost; keys not rotated) | **FAIL** |
| 4 | `VAULT_KEY` replacement + re-encryption | Complete (S1-B Phase 2 `2026-10-09T10:44Z`) | **PASS** (legacy Config.Env still holds old key while stopped) |
| 5 | MongoDB least-privilege + root rotation | Outstanding | **FAIL** |
| 6 | Bootstrap-token rotation + backups/admin surface | Outstanding | **FAIL** |
| 7 | Deployer private-key exposure / wallet migration | Outstanding (key present; migration need unresolved) | **FAIL** |

**Unresolved critical risks (production):**

1. **Alchemy API keys are actively logged in plaintext** by `arbicore-x-backend-new` (~1.5k credential-bearing `/v2/<key>` lines/hour; live fp8 `24dab5d1`). Log redaction commit `4a00171` is **not** in the running image.  
2. **Mongo app access is still `root`** on shared `factory-mongo` / `arbicore_x`.  
3. **Public `/docs` + `/openapi.json`** remain reachable; bootstrap token unrotated and present in backups.  
4. **Residual old `VAULT_KEY`** sha12 `a46000441419` remains in stopped legacy b7/h05/w1 `Config.Env` (containers must stay stopped until removed/recreated). Active vault path uses new sha12 `fb5ca619211e`.

---

## Runtime baseline (verified)

| Fact | Evidence |
|---|---|
| Production backend | `arbicore-x-backend-new`, image `arbicore-x-backend:hybrid-e-rpc-9244ebd`, healthy, started `2026-10-08T08:33:43Z`, RestartCount=0 |
| `BUILD_INFO` | `git_sha=fff0d0ec…`, tag `hybrid-e-rpc-9244ebd`, `build_time=2026-10-08T07:58:15Z` |
| Mode | `ARBICORE_EXECUTION_MODE=SHADOW`, `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_SCANNER_AUTOSTART=true` |
| DB | `DB_NAME=arbicore_x` → `factory-mongo:27017` |
| Edge | Caddy alias `arbicore-x-backend` → `arbicore-x-backend-new` (`172.18.0.12` on `vqb-network`) |
| Compose launch | `docker-compose.prod.yml` + `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` (ephemeral override still in use) |
| Signing/broadcast (60m logs) | `sendRawTransaction` = 0 |

Secrets below are referenced only as `sha256[:12]` or Alchemy path `sha256[:8]` fingerprints. **No secret values are reproduced.**

---

## 1. Legacy backend isolation + single scanner-writer

| | |
|---|---|
| **Prior gate** | S1-B/F1 **PASS** on 2026-10-07 (`docker stop` of b7/h05/w1) |
| **Completion** | Complete |
| **Production verdict** | **PASS** |
| **Verified at** | `2026-10-09T05:07:52Z` |

**Evidence**

| Container | State now | `DB_NAME` | Scanner env |
|---|---|---|---|
| `arbicore-x-backend-new` | running, healthy | `arbicore_x` | `true` |
| `arbicore-x-b7-candidate` | Exited (137) ~2 days | `arbicore_x` (stale Config.Env) | was `true` |
| `arbicore-x-backend-h05` | Exited (137) ~2 days | `arbicore_x` | was `true` |
| `arbicore-x-backend-w1` | Exited (137) ~2 days | `arbicore_x` | was `true` |
| `arbicore-g5-79-app` | running | `arbicore_g579_test` (isolated) | `false` |

Only **one** running container uses `DB_NAME=arbicore_x`: `arbicore-x-backend-new`.

**Residual risk (not a FAIL of this item):** legacy containers still exist with old env material and can be restarted. They must remain stopped until secrets are rotated and env wiped.

---

## 2. Admin password and JWT secret rotation

| | |
|---|---|
| **Prior gate** | S1/F2-A **PASS** on 2026-10-07 (login 401/200 tests; JWT sha `7013ef842946` → `066b178751e1`; admin len=36; Mongo `session_version` 1→2) |
| **Completion** | **Partial** — rotation still present in production; “out of compose/env” and backup scrub **not** done |
| **Production verdict** | **FAIL** (full plan criterion not met) |
| **Verified at** | `2026-10-09T05:08:40Z` / `05:10:13Z` |

**Evidence (production)**

| Secret | backend-new sha12 | legacy (b7/h05/w1) sha12 | Interpretation |
|---|---|---|---|
| `JWT_SECRET` | `066b178751e1` | `7013ef842946` | Rotated; matches F2-A post-rotation |
| `ARBICORE_ADMIN_PASS` | `6757aa3396d8` (len=36) | `6780d7b21193` | Rotated vs legacy |
| `ARBICORE_ADMIN_USER` | `admin` | `admin` | Still default username |
| Mongo `users` | `session_version=2` | — | Consistent with F2-A hash update |

**Still FAIL against plan wording**

- Admin password remains **plaintext in container ENV** and in live `.env` files (`deployment/upgrade/backend/.env`, repo-root `.env`).  
- Multiple `.env*` backups still contain **pre-rotation** admin/JWT hashes (`7013ef842946` / `6780d7b21193`).  
- Re-login with old password was not re-tested in this reconciliation (avoided auth probing beyond presence checks); rotation hashes remain consistent with F2-A.

---

## 3. Production + fallback Alchemy key rotation and log redaction

| | |
|---|---|
| **Prior gate** | S1/F2-B-LITE **PASS** for redaction only (commit `4a00171`, image `f2b-lite-rpc-redact-4a00171`); **explicitly did not rotate** Alchemy keys |
| **Completion** | Outstanding |
| **Production verdict** | **FAIL** |
| **Verified at** | `2026-10-09T05:08:24Z` / `05:09:56Z` |

**Evidence**

| Check | Result |
|---|---|
| `log_redaction.py` in running container | **Absent** |
| Redaction commit ancestor of image tip `9244ebd` | **No** (`merge-base --is-ancestor` false; tree has no `log_redaction.py`) |
| Credential-bearing Alchemy URLs in logs (60m) | **1565** matches; redacted markers **0** |
| Live log key fp8 (10m/60m) | **`24dab5d1` only** |
| ENV Alchemy fp8 (`ARBICORE_RPC_URL*`) | **`5e5d5bb1`** (bootstrap/docker key; still present) |
| Mongo `arbicore_config` `_id=network` Alchemy fp8 | `124bc59c`, **`24dab5d1`**, `6e67e161`, `cd505118`, `dc432a6b`, `e315c86f` |
| Legacy ENV fallback fps (stopped) | `ce00e63d`, `ff5eb596` |
| Provider-side revoke of old keys | **UNKNOWN** (no Alchemy dashboard access in this audit) |

**Interpretation:** A later Hybrid-E deploy superseded the redaction image. Production is again leaking the **Mongo-active** key (`24dab5d1`) at INFO via httpx. Neither production nor fallback keys have verified rotation/revoke.

---

## 4. `VAULT_KEY` replacement and stored-secret re-encryption

| | |
|---|---|
| **Prior plan** | F2 / M2 / S1-A step 8 |
| **S1-B Phase 1** | **COMPLETE** — `artifacts/security/s1b_vault_rotation_preflight_20261009/S1B_PHASE1_PREFLIGHT.md` |
| **S1-B Phase 2** | **COMPLETE** — `artifacts/security/s1b_vault_rotation_preflight_20261009/S1B_PHASE2_COMPLETION.md` |
| **Completion** | Complete (production key + ciphertext rotated; recovery drill passed) |
| **Production verdict** | **PASS** (active path); residual old key remains only in stopped legacy `Config.Env` + retained recovery escrow |
| **Verified at** | Phase 2 completion `2026-10-09T10:44:42Z` |

**Evidence (post Phase 2)**

| Check | Result |
|---|---|
| `VAULT_KEY` sha12 backend-new | `fb5ca619211e` |
| Prior sha12 `a46000441419` on b7 / h05 / w1 Config.Env | **Still present** (containers **exited** — do not start) |
| Active `.env` sha12 | `fb5ca619211e` (v2 root + `deployment/upgrade/backend/.env`) |
| Historical `.env*` / `/tmp` old plaintext | **Scrubbed** (`REDACTED_AFTER_S1B_PHASE2`) |
| `arbicore_secrets` count | **1** |
| Secret metadata | same handle/scope/label/address; cipher_sha12 now `45e7f15ca337` |
| Decrypt with new key + address | **OK** (plaintext_sha12 `b4ce2e6143a2`; address `0x0a43F432…Fa89`) |
| Backend image digest after recreate | `sha256:40b2116b…` (**unchanged**; not P2) |
| Recovery drill | **PASS** (pre-rotation archive + old escrow on scratch DB) |

**Interpretation:** Active production vault path uses the new key. Old key material is retained under restricted escrow for recovery and still embedded in stopped legacy containers until they are removed under separate change control.

---

## 5. MongoDB least-privilege credentials and root rotation

| | |
|---|---|
| **Prior plan** | S1-A step 9 — not executed |
| **Completion** | Outstanding |
| **Production verdict** | **FAIL** |
| **Verified at** | `2026-10-09T05:08:54Z` |

**Evidence**

| Check | Result |
|---|---|
| App `MONGO_URL` user | **`root`** (`authSource=admin`, host `factory-mongo:27017`) |
| `MONGO_URL` sha12 vs legacy Config.Env | **Identical** (`3a59d8617b72`) |
| `admin` DB users | only `root` with `root@admin` |
| `arbicore_x` DB users | **0** (no DB-scoped app user) |

---

## 6. Bootstrap-token rotation and backups / admin endpoint exposure

| | |
|---|---|
| **Prior plan** | S1-A step 10 — not executed |
| **Completion** | Outstanding |
| **Production verdict** | **FAIL** |
| **Verified at** | `2026-10-09T05:08:24Z` / `05:09:36Z` |

**Evidence**

| Check | Result |
|---|---|
| `ARBICORE_BOOTSTRAP_TOKEN` sha12 | `d5a682fbe887` on backend-new **and** all three legacy Config.Env |
| Token present in live `.env` + many backups | **Yes** (≥15 `.env*` paths under `arbicore-x-v2`) |
| Public `https://arbicorex.in/docs` | **200** |
| Public `https://arbicorex.in/openapi.json` | **200** |
| `https://api.arbicorex.in/docs` | **200** |
| `https://arbicorex.in/api/auth/login` | **405** on GET (endpoint exposed) |
| Backup scrub / Caddy restriction | **Not done** |

---

## 7. Deployer private-key exposure / wallet migration

| | |
|---|---|
| **Prior plan** | S1-A inventory flagged `contracts/.env` `DEPLOYER_PRIVATE_KEY` — rotation/migration not executed |
| **Completion** | Outstanding |
| **Production verdict** | **FAIL** |
| **Verified at** | `2026-10-09T05:09:43Z` / `05:10:13Z` |

**Evidence**

| Check | Result |
|---|---|
| File | `/home/raghu/projects/arbicore-x-v2/contracts/.env` |
| `DEPLOYER_PRIVATE_KEY` | **SET** (len=64, no `0x` prefix) |
| File mode | `0600`, gitignored, **not** git-tracked |
| Derived address | `0x3b37a5E124b177fEE30365deb295A5CCF76841Cd` |
| Equals executor owner `0x0a43…Fa89` | **No** |
| Equals gas wallet `0x998d…aad25` | **No** |
| Present in backend container ENV | **No** matching deployer/validation private-key env found |
| On-chain balances / whether funded | **UNKNOWN** (Base RPC `eth_getBalance` returned HTTP 403 from this host during audit) |
| Wallet migration performed | **No evidence** |

**Interpretation:** A distinct deployer key remains on the VPS filesystem. Migration necessity is **UNKNOWN** until balance/nonce/ownership of `0x3b37…41Cd` and any contracts it owns are confirmed. Treat as exposed material until revoked/migrated or proven empty and destroyed under change control.

---

## Planned vs verified (production)

| Remediation step (S1-A order) | Planned / prior gate | Verified in production now |
|---|---|---|
| Stop legacy b7/h05/w1 | Done (S1-B/F1 PASS) | **Yes** — still exited |
| Rotate admin + JWT | Done (S1/F2-A PASS) | **Hashes yes**; plaintext ENV/backups remain |
| Log redaction | Done then superseded (F2-B-LITE) | **No** — not in running image |
| Rotate Alchemy prod + fallback | Planned only | **No** |
| Replace `VAULT_KEY` + re-encrypt | Done (S1-B Phase 2) | **Yes** — active sha12 `fb5ca619211e`; legacy Config.Env residual only |
| Mongo least-privilege + root rotate | Planned only | **No** — still root |
| Bootstrap rotate + backup/docs lockdown | Planned only | **No** |
| Deployer key handling | Planned only | **Key still on disk** |

---

## Minimum safe remediation sequence (remaining)

Do **not** enable signing, broadcast, or LIVE while Alchemy logging / Mongo root / bootstrap exposure remain open.

1. **Keep** b7 / h05 / w1 stopped (already true); remove/recreate them under change control to clear old `VAULT_KEY` from `Config.Env`.  
2. **Next (single action):** restore log redaction into the **exact image that will run**, then rotate Mongo-network + ENV Alchemy keys and **revoke** old keys at Alchemy (incl. legacy fps `ce00e63d` / `ff5eb596` and log-active `24dab5d1`).  
3. Create Mongo least-privilege user for `arbicore_x`; rotate root; update `MONGO_URL`.  
4. Rotate `ARBICORE_BOOTSTRAP_TOKEN`; scrub backups; block public `/docs` + `/openapi.json` at Caddy.  
5. Move admin password out of compose ENV; scrub old admin/JWT from backups.  
6. Assess deployer `0x3b37…41Cd` (balance/nonce/ownership); migrate or destroy key material under explicit authorisation.

---

## Next single recommended action

**Alchemy log redaction + key rotation/revoke** (item 3) — production still leaks Mongo-active Alchemy credentials at INFO. S1-B Phase 2 vault rotation is complete; see `artifacts/security/s1b_vault_rotation_preflight_20261009/S1B_PHASE2_COMPLETION.md`. P2 remains blocked pending remaining security gates / separate authorisation.

---

## Change-control reminder

This document is audit-only. Any rotation, re-encryption, Caddy change, container recreate, or wallet migration requires **separate explicit authorisation**.
