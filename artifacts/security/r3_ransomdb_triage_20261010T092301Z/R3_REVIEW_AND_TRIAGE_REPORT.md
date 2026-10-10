# R3 review and read-only triage report

**Mode:** read-only · no mutations · no cleanup · no payments · no external contact  
**Report UTC:** `2026-10-10T09:25:00Z` (approx)  
**Artifact dir:** `artifacts/security/r3_ransomdb_triage_20261010T092301Z/`  
**Inputs:** R3 preflight `r3_mongo_leastpriv_preflight_20261010T091636Z/`; live `factory-mongo` inspection

**Preserved:** R1/R2 · S2-A digest · six-chain config · SHADOW · AUTOEXEC/RUNTIME false · legacy stopped · g5.79 untouched · **no R3 apply**

---

## Executive verdicts

| Question | Verdict | Confidence |
|---|---|---|
| What is `READ_ME_TO_RECOVER_YOUR_DATA`? | **MongoDB ransomware / scare-note database** (not a test artifact) | **High** |
| Active ongoing remote compromise of `factory-mongo` right now? | **No evidence of host-published Mongo**; auth enabled; note is a **historical artifact** (ObjectId `2026-09-06`) | **Medium–High** for “not currently host-exposed”; **Medium** that original intrusion was a typical unauthenticated-Mongo campaign |
| Is `readWrite` on `arbicore_x` enough for ArbiCore app? | **Yes** for observed runtime ops (CRUD + indexes/TTL create) | **High** |
| Can Factory containers stay on root for R3? | **Yes** — separate DBs; R3 scope is ArbiCore URI only | **High** |
| Proceed with R3 apply? | **Technically compatible**; treat ransom DB as **separate incident hygiene** (do not pay; do not delete under this task) | Operator decision |

**Do not** pay, contact the note’s addresses, or follow the note’s URL. Full note text is only in the evidence JSON for forensics.

---

## 1. Classification of `READ_ME_TO_RECOVER_YOUR_DATA`

### Metadata (read-only)

| Field | Value |
|---|---|
| Database | `READ_ME_TO_RECOVER_YOUR_DATA` |
| Collections | `README` (1) |
| Objects | 1 · dataSize ≈ 395 B · storageSize 20 KiB |
| Index | default `_id_` only |
| Document `_id` ObjectId time | **`2026-09-06T22:15:25Z`** |
| Content shape | Single string field `content` with payment / disclosure threat / “DATAID” (classic Mongo ransom-note pattern) |

**Evidence:** `readme_db_inspection.json`

### Classification

| Candidate | Fit |
|---|---|
| Expected ArbiCore / Factory test DB | **No** — not referenced in app code or compose DB_NAME values |
| Operator documentation DB | **No** — adversarial payment language |
| **MongoDB ransomware scare-note** | **Yes** — name + `README.content` match widely reported unauthenticated-Mongo campaigns |

**Confidence: High** that this is a **ransom-note artifact**, not unexplained noise and not an intentional product database.

### Integrity context (adjacent DBs still populated)

| DB | Collections | Notes |
|---|---:|---|
| `arbicore_x` | 62 | e.g. discovery ≈ 3.92M, decision_history ≈ 740k, users = 1 |
| `strategy_factory_v1` | 55 | peer data present |
| `strategy_knowledge_base` | 4 | peer/knowledge data present |
| Ransom DB | 1 | note only |

So this instance does **not** currently look like a wiped-empty mongod; the note sits **alongside** live application data. That pattern is consistent with campaigns that drop a note (and sometimes drop/exfil claims) without fully destroying every database — **or** with a note left after partial remediation. This triage **cannot** prove whether any historical wipe/exfil occurred before `2026-09-06`.

**Evidence:** `db_integrity_snapshot.json`

---

## 2. Log / exposure indicators

### Current network posture

| Check | Result |
|---|---|
| `factory-mongo` published ports | **None** (`Ports={"27017/tcp":null}`) |
| Host listen `:27017` | **None** |
| Networks | `vqb-network` + `strategy-factory-canonical_default` only |
| Image / version | `mongo:7` · reported `7.0.39` |
| Container started | `2026-09-07T05:21:43Z` (≈7h after note ObjectId) |
| Startup options (log) | `security.authorization: enabled`, `net.bindIp: *` **inside** container |

**Evidence:** `factory_mongo_inspect.txt`, `factory_mongo_logs_head100.txt`, host port check.

Bind-all **inside** Docker without host publish is normal; internet reachability would require a published port, host firewall hole, or lateral move from another container on those networks.

### Log signals

| Signal | Observation |
|---|---|
| Auth enabled at boot | Confirmed `2026-09-07T05:21:44Z` |
| Early `Failed to authenticate` as `root` | `2026-09-07T05:21:52Z` from `172.18.0.5` (Docker net) — SCRAM storedKey mismatch; consistent with app using stale password during recreate, not proof of external attacker |
| Recent tail (5k lines) `Failed to authenticate` | **39** matches in filtered sample |
| Lifetime SCRAM-SHA-256 counters | received 631298 / successful 299509 (includes speculative auth accounting — interpret cautiously) |
| Ransom DB creation event in retained logs | **Not found** in head/tail samples (note predates current container start; older logs rotated) |
| Prior security docs mentioning this DB | **No** prior hit outside R3 preflight |

**Evidence:** `factory_mongo_logs_head100.txt`, `factory_mongo_logs_tail5k_filtered.txt`, `db_integrity_snapshot.json` (`security.authentication`).

### Compromise assessment (bounded)

| Claim | Assessment |
|---|---|
| Historical unauthorized **write** that created the note DB | **Likely** (High confidence note is adversarial; Low–Medium on exact intrusion path — typical cause is historically exposed/unauth Mongo) |
| Ongoing **host-internet** Mongo exposure now | **Not supported** by current publish/listen evidence |
| Application data currently destroyed by this note | **Not supported** — large collections remain |
| Need to pay / contact note addresses | **No** — do not engage |

**Separate follow-on (not R3):** incident hygiene — root password age/rotation, peer Factory least-privilege, confirm no other listeners, decide retention vs controlled deletion of the note DB under change control, review whether `172.18.0.0/16` / `172.22.0.0/16` peers are fully trusted.

---

## 3. `arbicore_app` / `readWrite` validation

### Observed ArbiCore Mongo usage

| Pattern | Location | Needs beyond `readWrite@arbicore_x`? |
|---|---|---|
| `AsyncIOMotorClient(MONGO_URL)` + `client[DB_NAME]` | `services/db.py`, `server.py` | No |
| CRUD on many collections | runtime | No |
| `create_index` incl. unique + TTL | `ensure_indexes()`, repos | No — `readWrite` includes index create |
| `get_database(db.db.name)` | `drift_runner.py` status | No — **same** DB |
| `admin.command("ping")` | validation helpers | No — allowed for authenticated users |
| `collMod` for TTL change | `mid/indexes.py` — **skipped on failure** | Not required for steady state |
| `drop_database` / `createUser` | **tests only** | Must not run in prod path |
| Cross-DB to `strategy_factory_v1` / knowledge / ransom DB | **Not found** in runtime server paths | N/A — denial is desirable |

### Compatibility risks after removing root from **ArbiCore** URI

| Risk | Severity | Mitigation |
|---|---|---|
| App cannot `listDatabases` / manage users | None for app | Expected |
| Cannot `collMod` TTL expiry changes | Low | Already soft-fail; operators use break-glass if needed |
| Boot index ensure fails | Low if role wrong | Offline verify `createIndex` as `arbicore_app` before cutover |
| Scripts/operators using ArbiCore `.env` root for admin tasks | Process | Document break-glass root escrow |
| Factory still on root | Residual shared risk | **Out of R3 scope** — leave unchanged |

### Factory unchanged

| Container | DB | R3 action |
|---|---|---|
| `factory-backend` | `strategy_factory_v1` | **Remain on root URI** |
| `factory-runner` | `strategy_factory_v1` | **Remain on root URI** |
| `arbicore-x-backend-new` | `arbicore_x` | **Only** target for URI switch |

---

## 4. Precise proposed change plan (still **not authorised**)

Unchanged from preflight, refined by this triage:

1. **Backup:** `mongodump --db=arbicore_x` + 0600 copy of ArbiCore `backend/.env`.  
2. **Break-glass as root:** create user `arbicore_app` with `{ role: "readWrite", db: "arbicore_x" }` on `authSource=admin`.  
3. **Offline prove:** connect as `arbicore_app` — ping; read `users`; `createIndex` on a harmless test collection or list indexes; confirm **denied** on `strategy_factory_v1`.  
4. **Switch only** ArbiCore `MONGO_URL` to `arbicore_app`; recreate **only** `arbicore-x-backend-new` on digest `69fe2459…` / S2-A tag · `--pull never`.  
5. **Accept:** username ≠ root; `/api/` 200; login 200; R1 404 docs; R2 setup 503; fps `ca6545ba` + fallbacks; controls unchanged.  
6. **Do not** delete the ransom DB in the same change window unless separately authorised.  
7. **Do not** rotate Factory URIs or root password in the same change unless separately authorised (root rotation recommended as **later** incident hardening).

### Rollback

Restore ArbiCore `.env` root URI from 0600 backup → recreate backend on same S2-A image → verify username `root` + healthy. Optionally leave `arbicore_app` user in place.

---

## 5. Recommendations to the operator

1. **R3 apply** may proceed on technical grounds once explicitly authorised (`arbicore_app` + ArbiCore-only URI switch).  
2. Treat `READ_ME_TO_RECOVER_YOUR_DATA` as a **known adversarial artifact**; **do not pay or contact**.  
3. Open a **separate** incident-hygiene auth for: note-DB disposition, root credential freshness, Factory least-privilege, and network trust review.  
4. Overall security gate / P2 remains **BLOCKED** until R3–R6 (and policy on residuals) close independently.

---

## Safety confirmation

- Read-only inspection only.  
- No user creation, grants, URI edits, recreates, deletions, rotations, deployments, or trading.  
- Ransom note content stored in evidence JSON; do not amplify payment channels operationally.  

**Stopped for explicit authorisation.**
