# R3 apply readiness verdict (no mutations)

**Verdict: READY FOR EXPLICIT AUTHORISATION**  
**Reviewed UTC:** `2026-10-10T10:19:30Z`  
**Prior blocking verdict:** `NOT READY` @ `2026-10-10T10:05:21Z` (unauthenticated `mongodump`)  
**Inputs:** [`R3_DECISION_PACKAGE.md`](R3_DECISION_PACKAGE.md) (corrected §C.3), [`R3_BACKUP_CORRECTION.md`](R3_BACKUP_CORRECTION.md), [`backup_validation_meta.json`](backup_validation_meta.json), [`readiness_recheck.json`](readiness_recheck.json); original package preserved at [`R3_DECISION_PACKAGE.md.pre-backup-correction-20261010T101234Z`](R3_DECISION_PACKAGE.md.pre-backup-correction-20261010T101234Z)

---

## Blocking issue — resolved

Unauthenticated §C.3 `mongodump` failed live with `(Unauthorized) Command listCollections requires authentication`.

**Correction:** authenticate using `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD` already in the `factory-mongo` container ENV, expanded **inside** `docker exec … sh -c` (never on host argv / shell history). See decision-package §C.3 step 1 and `R3_BACKUP_CORRECTION.md`.

**Validation (non-mutating):** authenticated dump **PASS** — archive `0600`, `gzip -t` OK, 56 collections finished (incl. `arbicore_discovery_candidates` 3 921 188 docs), `mongorestore --dryRun` completed with **0 Unauthorized** / no writes. Path: `/home/raghu/arbicore_backups/r3_backup_validation_20261010T101234Z/arbicore_x_20261010T101234Z.archive.gz`.

---

## Readiness recheck (post-correction)

| Item | Result | Evidence |
|---|---|---|
| Authenticated backup procedure in §C.3 | **PASS** | package + `R3_BACKUP_CORRECTION.md` |
| Backup validation | **PASS** | `backup_validation_meta.json` · `validation_passed: true` |
| Original package preserved | **PASS** | `.pre-backup-correction-20261010T101234Z` |
| Live digest | `sha256:69fe2459…e7315313` · `s2a-rpc-redact-5bd952568aed` · healthy | `docker inspect` |
| Controls | `SHADOW` · `AUTOEXEC=false` · `RUNTIME=false` · no `BOOTSTRAP` | container ENV + override |
| Six-chain Alchemy primary fps | **`ca6545ba`** on ETH/ARB/OP/POLY/BNB (+ primary URL); BASE remains public `mainnet.base.org` (unchanged this review) | URL `/v2/` key sha8 |
| R1 public `/docs` | **404** (sslip / arbicorex.in / api) | curl |
| R2 `POST /api/auth/setup` | **503** fail-closed (local `:8001` + public) | curl |
| ArbiCore Mongo user | still **`root`** @ `factory-mongo` (pre-apply) | ENV username only |
| Factory | still root URI · untouched | inspect (redacted) |
| Legacy / g5.79 | legacy exited; g5.79 up untouched | `docker ps` |

---

## Remaining prerequisites (apply gate — not backup)

1. **Separate explicit R3-APPLY authorisation** (this review does **not** apply).  
2. Apply-time `createUser` (`arbicore_app` / `readWrite@arbicore_x` only) via `passwordPrompt` or escrow — **not** executed.  
3. Apply-time ArbiCore `MONGO_URL` switch + backend recreate (`--pull never`) — **not** executed.  
4. Historical ransom-note / pre-2026-09-07 log gap residual — accepted in decision package; **not** a backup blocker.

**Overall security gate / P2:** still **BLOCKED** until R3 (and later items) complete or risk-accepted.  
**Stop — no apply.**
