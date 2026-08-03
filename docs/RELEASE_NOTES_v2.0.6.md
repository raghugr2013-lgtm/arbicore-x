# ArbiCore X — Release Notes v2.0.6

**Release date:** 2026-08-03
**Type:** Bug-fix / hardening (authentication canonicalization)

---

## Summary

Fixes a truthfulness bug in the authentication seed routine that caused the
backend startup log to falsely report `"seeded 2 default users (admin,
operator)"` even when nothing had been inserted into MongoDB. The seed
routine is now:

1. **Truthful** — the log lines it emits exactly describe the actions it
   took against the `auth_users` collection.
2. **Idempotent** — repeated restarts produce identical DB state and
   never create duplicate users.
3. **Non-destructive** — existing accounts (admin or otherwise) are never
   overwritten, re-hashed, or reissued a new `user_id`.
4. **Self-verifying** — a post-seed verification step confirms both
   `admin` and `operator` exist in the collection before the routine
   returns, and the FastAPI startup handler logs the full summary at
   INFO level so operators can compare log ↔ database at a glance.

## Changed files

* `app/backend/arbicore/auth/__init__.py`
  * `ensure_seed_users(db)` rewritten. Now:
    * Creates the `username` unique index BEFORE inserting.
    * Queries each desired username individually.
    * Inserts only what is missing.
    * Performs a post-seed verification query and returns a rich summary
      dict `{database, collection, existed_before, inserted,
      skipped_existing, verified, ok}`.
    * Logs one of four truthful messages depending on what happened
      (all seeded, some seeded some existed, all existed, or nothing at
      all — the last case escalates to a WARNING).
* `app/backend/server.py`
  * `_auth_seed_startup` now consumes the summary dict returned by
    `ensure_seed_users` and logs it verbatim. Emits an ERROR if
    `ok is False` (default users missing after routine ran).

## Verification (executed on 2026-08-03)

### 1. Production-parity scenario — existing admin only

State before:

```
auth_users = [{'username': 'admin', 'role': 'admin', 'active': True}]
```

Startup log after backend restart:

```
auth: seeded 1 new user(s) [operator] in arbicore.auth_users; 1 already existed [admin]
auth: post-seed verification OK — admin=True, operator=True present in arbicore.auth_users
auth: startup seed summary — db=arbicore coll=auth_users
    inserted=['operator'] existed_before=['admin']
    skipped_existing=['admin']
    verified={'admin': True, 'operator': True} ok=True
```

Log exactly matches DB state. Admin `user_id`, `password_hash` and
`created_at` are byte-identical before vs. after, confirming the
existing admin was not overwritten.

### 2. Idempotency — two additional restarts

Restart #1 and #2 both produce:

```
auth: all 2 default user(s) already exist in arbicore.auth_users [admin, operator] — no seed needed
auth: post-seed verification OK — admin=True, operator=True present in arbicore.auth_users
auth: startup seed summary — db=arbicore coll=auth_users
    inserted=[] existed_before=['admin', 'operator']
    skipped_existing=['admin', 'operator']
    verified={'admin': True, 'operator': True} ok=True
```

Final DB state:

```
auth_users count      = 2
admin username count  = 1
operator username count = 1
users = [{admin, admin}, {operator, operator}]
```

No duplicates. No spurious writes.

### 3. Auth API validation (external preview URL)

| Endpoint             | Account   | Expected  | Observed  |
|----------------------|-----------|-----------|-----------|
| `POST /api/auth/login` | admin     | 200 + JWT | 200 + JWT |
| `GET  /api/auth/me`    | admin     | 200       | 200       |
| `POST /api/auth/logout`| admin     | 200 revoked=true | 200 revoked=true |
| `GET  /api/auth/me`    | admin (revoked JTI) | 401 | 401 |
| `POST /api/auth/login` | operator  | 200 + JWT | 200 + JWT |
| `GET  /api/auth/me`    | operator  | 200       | 200       |
| `POST /api/auth/login` | admin + wrong pw | 401 | 401 |

## Migration notes

None required. Change is server-side only, backward-compatible, and
schema-preserving. Existing installations should simply redeploy the
new backend image.

## Version tag

`v2.0.6`
