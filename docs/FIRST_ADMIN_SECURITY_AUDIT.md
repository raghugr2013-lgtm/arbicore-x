# FIRST-ADMIN SECURITY AUDIT (P0)

## Summary

**Severity: CRITICAL — FIXED (fail-closed).**

The first-admin bootstrap endpoint (`POST /api/auth/setup`) previously authorized
creation of the sole administrator based **solely on the absence of an existing
administrator**. On a fresh database (no env-provisioned users), **any anonymous
internet visitor** could POST a username/password and become the permanent sole
admin. This is fail-OPEN and matches the concern raised in the directive.

## Vulnerable code (before)

`routes/auth.py`:
```python
@router.post("/setup")
async def setup(body, response):
    if await db.users_col.count_documents({}) > 0:
        raise HTTPException(403, "...locked...")
    # <-- NO server-side authorization. "no admin yet" == authorization.
    ... insert admin ...
```

Weaknesses:
1. **No independent server-side authorization.** "No admin exists" ⇒ open.
2. **Race condition.** Two concurrent requests could each pass the count check and
   create **multiple admins** (proven: 3 admins created under a 10-way race before
   the fix; distinct usernames bypassed the username unique index).
3. Depended on optional env provisioning (`ARBICORE_ADMIN_PASS`) to close the hole,
   i.e. fail-open by default.

## State machine (desired, now enforced)

```
UNINITIALIZED ──(valid X-Bootstrap-Token)──► AUTHORIZED_BOOTSTRAP
              ──► ADMIN_CREATED ──► BOOTSTRAP_LOCKED (permanent)
```

## Fix (after) — `routes/auth.py`

- **`_authorize_bootstrap(request)`** — fail-closed, server-side:
  - If `ARBICORE_BOOTSTRAP_TOKEN` is **not** provisioned server-side → `503`
    (bootstrap DISABLED, never open).
  - Token compared in **constant time** (`hmac.compare_digest`) against the
    `X-Bootstrap-Token` header. Missing/wrong → `403`.
- **Atomic single-admin lock** — before any insert we defensively
  `create_index("key", unique=True)` on `settings` and insert a fixed sentinel
  `{"key": "auth_bootstrap_lock"}`. Only the first concurrent request wins; the rest
  get `DuplicateKeyError → 403`. This makes bootstrap atomic even on a fresh DB that
  has not yet run `ensure_indexes`.
- Defense in depth: username unique index + post-lock `count_documents` re-check.

The token is:
- **NOT** hardcoded in the frontend (operator types it into the setup form; it is a
  secret the operator possesses, never shipped in JS).
- **NOT** public config, **NOT** derivable from the no-admin state, **NOT** exposed
  by any API (`/status` only returns booleans `bootstrap_requires_token` /
  `bootstrap_available`, never the value), **NOT** bypassable by direct HTTP.

## Residual notes / lower-severity findings

- `services/auth.py` sets cookies with `secure=False` (required for the http
  preview). In production behind TLS this should be `secure=True`. Documented, not
  changed here (environment-dependent; would break the http preview).
- `ensure_provisioned_users` (env-seeded admin/operator) remains available and is
  insert-only; when it seeds an admin, `/setup` is additionally locked by the
  count/lock guards.

See `SECURITY_TEST_RESULTS.md` for adversarial proof, and
`AUTHORIZATION_ENDPOINT_MATRIX.md` for the endpoint classification.
