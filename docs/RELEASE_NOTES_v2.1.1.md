# ArbiCore X — v2.1.1 Release Notes

**Release date:** 2026-08-03
**Type:** bug fix — auth seed env-var contract

## The bug (found on the VPS after the v2.1.0 upgrade)

`arbicore.auth.ensure_seed_users` read the seed password from
`ARBICORE_ADMIN_PASSWORD` / `ARBICORE_OPERATOR_PASSWORD`. The
shared-profile production deployment sets those secrets as
`ARBICORE_ADMIN_PASS` / `ARBICORE_OPERATOR_PASS` (the convention used
by every other service on the shared VPS).

Effect: at seed time the code looked for a variable the operator never
set, silently fell back to the hardcoded default `admin-shadow-2026`,
and stored a bcrypt hash of the default. Login later compared the
operator's *real* password against that hash and failed with
`invalid_credentials`. This regression is not visible from the seed
summary (which only reports whether documents exist, not whose secret
was used to seed them).

## The fix

Two-part change; both parts land in v2.1.1.

1. **`ensure_seed_users` accepts both env-var names** (`ARBICORE_ADMIN_PASS`
   preferred, `ARBICORE_ADMIN_PASSWORD` as fallback; same for the
   operator).  First non-empty wins; falls back to the hardcoded
   default only if neither is set.  This is the permanent contract
   change so no deployment convention can silently miss the secret
   again.

2. **Self-heal for legacy stale-default hashes.** On every seed run,
   if a doc's stored hash matches the *hardcoded default* plaintext
   AND a real env secret is now present AND the stored hash does NOT
   already match the real env secret, the seed rehashes only the
   `password_hash` field on that one doc using the real env secret.
   All other fields (`user_id`, `created_at`, `role`, `active`,
   `username`) are preserved byte-identical.  The self-heal is fully
   idempotent — on subsequent boots the hash already matches, so the
   guard skips the update.  A hash that already matches the real env
   secret is **never** overwritten.

The seed summary now also reports `rehashed_from_default: [...]` and
the startup log emits a WARNING listing which usernames were repaired.

## Regression results

**1499 passed, 76 skipped, 0 failures** (v2.1.0 baseline was 1494).
+5 new tests in `tests/test_auth_v2_1_1.py`:

* `test_seed_prefers_new_env_var_name`
* `test_seed_falls_back_to_old_env_var`
* `test_seed_falls_back_to_default_when_no_env`
* `test_self_heal_rehashes_stale_default`
* `test_self_heal_never_overwrites_matching_hash`

## Files modified

* `app/backend/arbicore/auth/__init__.py` — env-var-name tuple support
  + `_resolve_password` helper + self-heal block + WARNING log line.

## Files added

* `app/backend/tests/test_auth_v2_1_1.py`
* `docs/RELEASE_NOTES_v2.1.1.md`

## Migration risk

**Very low.** No schema change. No new env var required (deployments
that used the old name keep working).  Self-heal only fires when the
mismatch is provable (default-hash detected AND a real env secret
present).  Roll-forward = `docker compose build backend && up -d`.
Rollback = `git checkout v2.1.0` — but note the immediate one-shot
rehash you already applied on the VPS still holds, so v2.1.0 login
works too.

## VPS deployment

You already ran the one-shot rehash in Part 1 of the fix message, so
login already works on v2.1.0.  v2.1.1 is optional right now — it
matters for the *next* fresh install or the next environment where
the operator forgets to set the env var.  Recommended path:

```
cd $HOME/staging && (upload arbicore-x-v2.1.1.bundle + .SHASUMS)
# then follow deploy runbook, replacing every 'v2.1.0' with 'v2.1.1'
```

## API surface

No changes.
