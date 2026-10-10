# R3 — MongoDB least-privilege preflight (read-only)

**Phase:** preflight only — **no mutation**  
**Captured UTC:** `2026-10-10T09:16:36Z` – `2026-10-10T09:18:00Z` (approx)  
**Artifact dir:** `artifacts/security/r3_mongo_leastpriv_preflight_20261010T091636Z/`  
**Baseline:** R1 **PASS** · R2-DISABLE **PASS** · overall gate / P2 **BLOCKED**

**Preserved (verified this preflight):** S2-A digest `69fe2459…` · public `/docs` **404** · `/api/` **200** · setup **503** · SHADOW / AUTOEXEC=false / RUNTIME=false expected to remain for any later apply

---

## Executive recommendation

**Create a dedicated MongoDB application user with `readWrite` on database `arbicore_x` only**, then switch **only** `arbicore-x-backend-new` `MONGO_URL` to that user (`authSource=admin`), recreating the backend on the **unchanged** S2-A image. Keep `root` offline as break-glass for `factory-mongo` administration. **Do not** change Strategy Factory (`factory-backend` / `factory-runner`) credentials in this workstream.

This matches [`docs/SHARED_INFRASTRUCTURE.md`](../../../docs/SHARED_INFRASTRUCTURE.md) §4.2 (user name there: `arbicore`; this plan prefers **`arbicore_app`** to make the app identity explicit — either is fine if unique).

**Do not execute** until explicit R3 apply authorisation.

---

## 1. Who uses `factory-mongo` root today

### Live `usersInfo` (via current app connection)

| Scope | Result |
|---|---|
| `admin` users | **only `root`** with role `root@admin` |
| `arbicore_x` DB-scoped users | **[]** (none) |

### Containers with `MONGO_URL` username `root` @ `factory-mongo` (`authSource=admin`)

| Container | Status | `DB_NAME` |
|---|---|---|
| **`arbicore-x-backend-new`** | **running** | `arbicore_x` |
| **`factory-backend`** | **running** | `strategy_factory_v1` |
| **`factory-runner`** | **running** | `strategy_factory_v1` |
| Multiple exited ArbiCore legacy/validators | exited | `arbicore_x` |

### Not on `factory-mongo`

| Service | Mongo host | Notes |
|---|---|---|
| `arbicore-g5-79-app` | `arbicore-g5-79-mongo` | DB `arbicore_g579_test` — out of scope |
| `foreman-backend` | `foreman-mongo` | separate |
| `foreman-cert-backend` | `foreman-cert-mongo` | separate |
| `factory-vie` / frontend | no Mongo ENV | — |

**Evidence:** `factory_mongo_consumers.json`, `mongo_summary.json`.

**Implication:** R3 must change **ArbiCore X only**. Factory stack remains on root until a **separate peer** remediation; that residual shared-root risk is acknowledged but out of R3 scope.

---

## 2. Databases on `factory-mongo`

| Database | Approx size (MB) | Owner / role |
|---|---:|---|
| `arbicore_x` | (see summary) | ArbiCore X |
| `strategy_factory_v1` | | Strategy Factory |
| `strategy_knowledge_base` | | Factory-related (peer) |
| `admin` / `config` / `local` | | system |
| `READ_ME_TO_RECOVER_YOUR_DATA` | | **Unexpected name** — see unknowns |

ArbiCore runtime binds exclusively to `DB_NAME=arbicore_x` via Motor (`services/db.py`, `server.py`).

---

## 3. ArbiCore X collections and access pattern

- **62 collections** in `arbicore_x` (names in `mongo_summary.json`).
- Heaviest: `arbicore_discovery_candidates` (~3.9M), `decision_history` (~739k), `evidence_bundles` (~584k).
- Auth: `users` (1 admin doc), `login_attempts`.
- Secrets vault material: `arbicore_secrets` (Fernet ciphertext; S1-B).
- Network/RPC config used by S2-A lives in this DB (primaries `ca6545ba`, fallbacks retained).

### Operations observed in runtime code

| Operation class | Required? | Covered by `readWrite` on `arbicore_x`? |
|---|---|---|
| find / insert / update / delete | Yes | **Yes** |
| `create_index` incl. unique + TTL (`expireAfterSeconds`) | Yes — boot `ensure_indexes()` and many repos | **Yes** |
| `list_collection_names` / collection CRUD within DB | Yes | **Yes** |
| `admin.command("ping")` | Health/tests | **Yes** (any auth user) |
| `collMod` to alter existing TTL expiry | Rare; mid indexes **skip silently** on failure | **No** — not required for steady state |
| `drop_database` / `createUser` / `listDatabases` / `usersInfo` | Tests only (not production server path) | **No** — must not be needed by app |
| Cross-DB access to `strategy_factory_v1` | Must not | **Denied** by scoped role (desired) |

**Minimum application role:** `{ role: "readWrite", db: "arbicore_x" }`  
**Not recommended for app:** `root`, `dbAdminAnyDatabase`, `readWriteAnyDatabase`, or readWrite on peer DBs.

**Optional hardening (later):** custom role without `dropCollection` if policy demands; not required for first cutover.

---

## 4. Background workers / indexes / migrations / health

| Concern | Finding |
|---|---|
| Index ensure at boot | Extensive `create_index` in `services/db.py` + arbicore repos — needs `readWrite` |
| TTL indexes | **17** existing TTL indexes — creation/ensure OK with `readWrite`; changing TTL via `collMod` is best-effort/skipped |
| Migrations | No production `createUser`/`dropDatabase` in server path; test suites drop isolated DBs only |
| Health | App healthy today with root; post-cutover: ping + `/api/` + login + scanner boot without auth errors |
| Multi-writer | Only `arbicore-x-backend-new` should write `arbicore_x` while legacy stay stopped |

---

## 5. Proposed apply plan (for later authorisation)

### 5.1 Break-glass handling of `root`

| Control | Plan |
|---|---|
| During apply | Use existing `root` **only** interactively (or via short-lived admin session) to `createUser` |
| After apply | ArbiCore `.env` / container ENV must **not** contain root URI |
| Storage | Root remains in `factory-mongo` init secret / existing peer ops escrow — **not** copied into ArbiCore compose |
| Use cases for root later | User/role changes, `mongodump`/`mongorestore` of other DBs, incident response — documented break-glass only |
| Peer apps | `factory-backend` / `factory-runner` still use root until peer project remediates (out of scope) |

### 5.2 Steps (ArbiCore only)

1. **Pre-backup:** `mongodump --db=arbicore_x` to restricted path; backup live `backend/.env` (0600).  
2. **Create user** (as root on `factory-mongo`), e.g.:

```javascript
// conceptual — password via prompt/escrow, never logged
use admin
db.createUser({
  user: "arbicore_app",
  pwd:  /* high-entropy secret */,
  roles: [ { role: "readWrite", db: "arbicore_x" } ]
})
```

3. **Offline verify** with a one-shot `mongosh`/Python client as `arbicore_app`: ping; `find` on `users`; refuse access to `strategy_factory_v1` (expect auth error).  
4. **Edit only** ArbiCore live `.env` `MONGO_URL` → `mongodb://arbicore_app:***@factory-mongo:27017/?authSource=admin` (plus `DB_NAME=arbicore_x` unchanged).  
5. **Recreate only** `arbicore-x-backend-new` with existing compose + S2-A override · `--pull never` · digest `69fe2459…`.  
6. **Accept** per §6.  
7. On failure → **rollback** §7 (restore root URI, recreate).

### 5.3 Explicit non-goals for R3 apply

- No Factory / Foreman / g5.79 credential changes  
- No root password rotation (optional later)  
- No deletion of `READ_ME_TO_RECOVER_YOUR_DATA` without separate incident auth  
- No R4/R5/R6, no P2, no historical env scrub  

### 5.4 Downtime / dependencies

| Item | Estimate |
|---|---|
| Downtime | Backend recreate ~1–3 minutes |
| Dependencies | Root break-glass available; S2-A override file present; operator approval on shared `factory-mongo` |
| Image rebuild | **Not required** |

---

## 6. Acceptance tests (post-apply)

| # | Test | Expected |
|---|---|---|
| A | Parsed live `MONGO_URL` username | `arbicore_app` (not `root`) |
| B | `usersInfo` on `arbicore_x` | includes app user with `readWrite` |
| C | Backend healthy | same digest `69fe2459…` |
| D | `GET /api/` | 200 |
| E | Admin login + `/api/auth/me` | 200 |
| F | `GET /api/auth/status` | `setup_complete: true` |
| G | Setup without bootstrap token | still **503** (R2 held) |
| H | R1 public docs | 404; `/api/` 200 |
| I | Mongo primary fps | still `ca6545ba`; fallbacks unchanged |
| J | Controls | SHADOW; AUTOEXEC/RUNTIME false; legacy exited; g5.79 untouched |
| K | Negative: app user cannot read `strategy_factory_v1` | auth failure |
| L | Boot logs | no repeated Mongo auth / unauthorized errors; indexes ensure OK |

---

## 7. Rollback

1. Restore `.env` `MONGO_URL` from R3 pre-apply 0600 backup (root URI).  
2. Recreate backend on same S2-A image/override.  
3. Confirm username `root`, healthy, login 200.  
4. Optionally leave `arbicore_app` user in place (harmless) or drop via break-glass in a follow-up.

---

## 8. Unknowns and open questions

| # | Question |
|---|---|
| U1 | Confirm preferred username: `arbicore_app` vs docs’ `arbicore` |
| U2 | Who holds Factory root escrow / is peer OK with ArbiCore creating a scoped user on shared mongod? |
| U3 | What is database `READ_ME_TO_RECOVER_YOUR_DATA`? Incident artifact vs intentional — needs operator triage (separate from R3) |
| U4 | Does any external job/host (not a Docker container) still use root against `arbicore_x`? Inventory was container-ENV based |
| U5 | Should R3 also rotate the root password after app cutover? (Recommended later; not required to close least-privilege for ArbiCore) |
| U6 | `strategy_knowledge_base` consumers — not seen in running container ENV; confirm no ArbiCore dependency (expected none) |

---

## 9. Safety confirmation (this phase)

- No users created, roles changed, credentials edited, env files modified, containers recreated, or DB mutations.  
- Secrets referenced only as usernames / role names / fingerprints.  
- R1/R2 posture spot-checked.  

**Stop for human authorisation before any R3 apply.**
