# ArbiCore X — v2.9.3 VPS deployment pre-flight

**Target host:** VPS Contabo Ubuntu running `factory-mongo` + ArbiCore X shared-profile stack
**Domain:** https://arbicorex.coinnike.com
**Baseline:** v2.9.2 (`293a2c4`)
**Branch to deploy:** `hotfix/auth-routing` → tag `v2.9.3`
**Estimated downtime:** ~90 seconds (backend + frontend rebuild + rolling restart)

---

## 0. Pre-flight checklist (run before touching anything)

Everything below runs on the VPS as the ops user with `sudo` docker access.

```bash
# 0.1 Confirm current commit and clean tree
cd /opt/arbicorex
git status                           # must be clean; if not, stash / commit first
git log -1 --format='%h %s'          # expect: 293a2c4 v2.9.2 …

# 0.2 Confirm running containers are healthy on v2.9.2
docker compose -f deployment/compose/prod.shared-mongo.yml ps
# expect: arbicore-x-backend, arbicore-x-frontend, arbicore-x-opportunity-center all "healthy"

# 0.3 Confirm shared Mongo reachable + snapshot the auth store
docker exec factory-mongo mongosh --quiet --eval '
  db = db.getSiblingDB("arbicore_x");
  print("users:       " + db.users.countDocuments({}));
  print("auth_users:  " + db.auth_users.countDocuments({}));
  print("login_attempts: " + db.login_attempts.countDocuments({}));
  print("auth_sessions: " + db.auth_sessions.countDocuments({}));
'

# 0.4 Snapshot the two auth collections in case we need to roll back
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec factory-mongo mongodump --archive --db=arbicore_x \
    --collection=users        > /opt/arbicorex/backups/users_pre_v293_${STAMP}.archive
docker exec factory-mongo mongodump --archive --db=arbicore_x \
    --collection=auth_users   > /opt/arbicorex/backups/auth_users_pre_v293_${STAMP}.archive
docker exec factory-mongo mongodump --archive --db=arbicore_x \
    --collection=login_attempts > /opt/arbicorex/backups/login_attempts_pre_v293_${STAMP}.archive
docker exec factory-mongo mongodump --archive --db=arbicore_x \
    --collection=auth_sessions > /opt/arbicorex/backups/auth_sessions_pre_v293_${STAMP}.archive
ls -lah /opt/arbicorex/backups/*_${STAMP}.archive     # expect four files
```

## 1. Confirm required env vars on the backend service

**`JWT_SECRET`** (Tree-A canonical auth reads this). If it isn't already set in
`deployment/compose/.env.shared` or the service env, set a persistent 32-byte
secret ONCE and never rotate without also running `reset_admin.py`:

```bash
# On the VPS — one-time only, if JWT_SECRET is not already present
grep -q '^JWT_SECRET=' deployment/compose/.env.shared || {
  SECRET=$(openssl rand -hex 32)
  echo "JWT_SECRET=${SECRET}" >> deployment/compose/.env.shared
  chmod 600 deployment/compose/.env.shared
}
grep -E '^(JWT_SECRET|MONGO_URL|DB_NAME|CORS_ORIGINS)=' deployment/compose/.env.shared
# CORS_ORIGINS must be exactly: https://arbicorex.coinnike.com
```

Do NOT set `ARBICORE_LEGACY_AUTH_SEED`. Leaving it unset (or `0`) keeps the
retired Tree-B admin/operator auto-seed disabled — this is what makes the
first-run setup flow trigger.

## 2. Bring in the hotfix branch

```bash
cd /opt/arbicorex
git fetch --all --tags
git checkout hotfix/auth-routing
git log -1 --format='%h %s'
# expect a subject starting with: docs(deploy): update DEPLOY_v2.9.3.md
# (the branch tip advances as review comments land; the runbook is
# intentionally SHA-agnostic. What matters is that the branch is
# hotfix/auth-routing and the last commit is docs/tests, not a code fix
# added out of scope. If the subject reads "auth-routing" and belongs to
# the v2.9.3 series, the branch is deployable.)
git rev-list --count v2.9.2..HEAD
# expect a small number of commits — as of this runbook, ~10 commits
# (7 real + auto-commit noise from the platform).

# Optional: tag now so you can roll back by tag later. Substitute the
# actual tip SHA that `git rev-parse HEAD` prints on your VPS clone.
TIP_SHA=$(git rev-parse HEAD)
git tag -a v2.9.3-rc.1 -m "v2.9.3 RC1 — auth routing hotfix" "$TIP_SHA"
```

## 3. Rebuild the two container images

```bash
COMPOSE_FILE=deployment/compose/prod.shared-mongo.yml
docker compose -f $COMPOSE_FILE build --pull --no-cache \
    arbicore-x-backend arbicore-x-frontend
# Note: --no-cache is deliberate for this release to force a fresh pip install
# of any auth dependencies pulled in by routes/auth.py (bcrypt, PyJWT). The
# opportunity_center image is unchanged; do not rebuild it.
```

## 4. Reset the canonical auth store (single-admin first-run flow)

```bash
# 4.1 Inspect BEFORE touching Mongo
docker compose -f $COMPOSE_FILE run --rm arbicore-x-backend \
    python reset_admin.py --dry-run

# Expected output:
#   Auth store inventory in database 'arbicore_x':
#     canonical  'users'          -> N document(s)    (probably 0 already)
#     canonical  'login_attempts' -> N document(s)
#     legacy     'auth_users'     -> N document(s)
#     legacy     'auth_sessions'  -> N document(s)

# 4.2 If canonical is populated (from any prior test), clear it. If empty, skip.
docker compose -f $COMPOSE_FILE run --rm arbicore-x-backend python reset_admin.py

# 4.3 The legacy Tree-B store (auth_users) is left in place. It is now
# unreachable via HTTP — no more login/logout/me/diagnostics endpoints
# use it — but if you ever want to reclaim disk, run:
#   docker compose -f $COMPOSE_FILE run --rm arbicore-x-backend \
#     python reset_admin.py --legacy --skip-canonical
```

## 5. Roll out the new images

```bash
docker compose -f $COMPOSE_FILE up -d arbicore-x-backend arbicore-x-frontend
docker compose -f $COMPOSE_FILE ps       # both must return to "healthy" within ~40s
docker compose -f $COMPOSE_FILE logs --tail=50 arbicore-x-backend | \
    grep -E 'v2.9.3|legacy auth seed|canonical auth router'
# Expect two lines:
#   v2.9.3: canonical auth router mounted (/api/auth/*)
#   v2.9.3: legacy auth seed skipped (ARBICORE_LEGACY_AUTH_SEED != '1')
```

## 6. Verification — required 6-step smoke (all against production URL)

```bash
BASE=https://arbicorex.coinnike.com
JAR=/tmp/arbicore_v293_smoke.cookies; rm -f $JAR

# 6.1  status must report setup NOT complete
curl -sSf $BASE/api/auth/status
# → {"setup_complete":false,"auth_required":true}

# 6.2  setup: create the sole admin (choose your own strong password)
read -srp "Admin password to set: " PW; echo
curl -sSf -c $JAR -H 'Content-Type: application/json' \
    -X POST $BASE/api/auth/setup \
    -d "{\"username\":\"admin\",\"password\":\"${PW}\"}"
# → {"id":"…","username":"admin","role":"admin","created_at":"…"}

# 6.3  setup must now be locked
HTTP=$(curl -sS -o /tmp/o -w '%{http_code}' -H 'Content-Type: application/json' \
    -X POST $BASE/api/auth/setup -d '{"username":"admin2","password":"secondone123"}')
test "$HTTP" = "403" && cat /tmp/o
# → 403 · {"detail":"Setup already completed — registration is locked (single-admin system)"}

# 6.4  status now reports setup complete
curl -sSf $BASE/api/auth/status
# → {"setup_complete":true,"auth_required":true}

# 6.5  me works with the session cookie set by step 6.2
curl -sSf -b $JAR $BASE/api/auth/me
# → {"id":"…","username":"admin","role":"admin",…}

# 6.6  Tree-B endpoint removed
HTTP=$(curl -sS -o /dev/null -w '%{http_code}' $BASE/api/auth/diagnostics)
test "$HTTP" = "404" && echo "OK: diagnostics endpoint removed"
```

If **any** of the 6 checks fail, do not proceed to browser validation.
Jump to §8 rollback.

## 7. Browser validation (perform once §6 is green)

1. Open https://arbicorex.coinnike.com in a fresh incognito window.
2. Confirm the login page renders as **CREATE ADMINISTRATOR** (should NOT
   because setup was already completed via curl in §6.2). If you skipped
   §6.2 and want to setup via UI: `docker compose -f $COMPOSE_FILE run
   --rm arbicore-x-backend python reset_admin.py`, then reload — the UI
   must show CREATE ADMIN with a Confirm passphrase field.
3. Sign in with the credentials from §6.2 — should redirect to
   `/initialization` and then to `/dashboard/*`.
4. Open browser DevTools → Application → Cookies. Verify **both**
   `access_token` and `refresh_token` cookies are present with:
   - Path `/`, HttpOnly ✓, SameSite `Lax`, Secure ✓ (HTTPS)
5. Sign out via the header menu; verify the login card returns (without
   the confirm-password field).
6. Sign back in; confirm dashboard renders again.
7. Navigate to Settings → Security → Change Password. Change the password.
   Confirm the response is "Password changed — all other sessions revoked".
8. Reset test (optional):
   `docker compose -f $COMPOSE_FILE run --rm arbicore-x-backend python reset_admin.py`
   → reload the browser → CREATE ADMINISTRATOR card returns. Re-create admin.

## 8. Rollback plan (if any of §6 or §7 fails)

```bash
cd /opt/arbicorex
COMPOSE_FILE=deployment/compose/prod.shared-mongo.yml

# 8.1 Return code to v2.9.2
git checkout main                    # tip of main is 293a2c4 v2.9.2

# 8.2 If you had populated the canonical store (users), restore Tree-B
# so the v2.9.2 backend can auto-seed admin/operator:
docker exec factory-mongo mongosh --quiet --eval '
  db = db.getSiblingDB("arbicore_x");
  db.users.deleteMany({});
  db.login_attempts.deleteMany({});
'
# The v2.9.2 backend's _auth_seed_startup will re-seed auth_users on boot.

# 8.3 Rebuild + restart at v2.9.2
docker compose -f $COMPOSE_FILE build --pull arbicore-x-backend arbicore-x-frontend
docker compose -f $COMPOSE_FILE up -d arbicore-x-backend arbicore-x-frontend

# 8.4 Smoke: v2.9.2 login should work with the previously seeded admin/operator
curl -sSf -H 'Content-Type: application/json' -X POST \
    https://arbicorex.coinnike.com/api/auth/login \
    -d '{"username":"admin","password":"<pre-v2.9.3 admin password>"}'
```

If step 8.4 fails because you don't remember the pre-v2.9.3 admin password,
restore from the archive taken in §0.4:

```bash
docker exec -i factory-mongo mongorestore --archive --db=arbicore_x \
    --drop --nsInclude='arbicore_x.auth_users' \
    < /opt/arbicorex/backups/auth_users_pre_v293_${STAMP}.archive
```

## 9. Post-deployment: tag v2.9.3

Only after §6 and §7 are green **on production**:

```bash
cd /opt/arbicorex
git checkout hotfix/auth-routing
git tag -a v2.9.3 -m "v2.9.3 — Authentication routing hotfix"
# When ready for the review-approved merge into main:
git checkout main
git merge --ff-only hotfix/auth-routing     # or open a PR via GitHub UI
git push origin main --tags
```

## 10. What is NOT in this release (deferred)

- Any change to trading, scanning, validation, execution, or MID logic.
- Canonical activation of the ~187 preview-stub endpoints
  (documented separately in `docs/roadmap_v2.10/`).
- Any UI redesign or new pages.
- Deletion of the legacy `arbicore/auth/__init__.py` module (kept on-disk;
  no longer wired).

---

**Approvals required before executing §5**
Sign here once the pre-flight (§0–§4) is complete and clean:

- [ ] Ops lead signed
- [ ] Backup archives verified (§0.4)
- [ ] Rollback path (§8) is understood and rehearsed
