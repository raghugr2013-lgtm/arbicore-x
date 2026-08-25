# ArbiCore X — Isolated VPS Validator Runbook (READ-ONLY, no prod, no signing)

Target HEAD: `f36d7c9dfb10f152bc5fc87f51d802f4ae995291`
Branch:      `complete-Base-M1-M4-live-shadow-composition`

> ⚠️ FRONTEND SHA CAVEAT: a frontend-only nav fix (per-page title / breadcrumb /
> rail active-state — `frontend/src/v2/lib/nav.js` now uses `/dashboard/*`) landed
> AFTER `f36d7c9`. Build the FRONTEND image from the LATEST branch HEAD (the
> checkpoint that includes this nav fix), not `f36d7c9`, or the title/breadcrumb
> bug ships. The BACKEND is unaffected — the `f36d7c9` backend image is still valid
> (the nav fix is frontend-only). Re-push via Save to Github and use the new HEAD
> for the frontend build.

Objective: build + run an ISOLATED validator of the exact HEAD, verify identity/safety/
frontend truth, run the real Base Spread-Widener Watch on the dedicated RPC, and — when a route
flags `worth_m3_validation=true` — run the full M3 read-only validator (`confirm=False`).

HARD RULES (every step honors these):
- NEVER set LIMITED_LIVE / FULL_LIVE / ARBICORE_AUTOEXEC_AUTOSTART.
- NEVER provision a signing key. NEVER sign. NEVER broadcast.
- Do NOT touch production containers, the production proxy, or production data (read-only Mongo).
- Isolated Docker project name + non-conflicting loopback port. No public ports, no nginx/certbot.

--------------------------------------------------------------------------------
## 0. Prereqs (on the VPS)
```bash
export VDIR=/opt/arbicore-validator            # isolated working dir
export DEDICATED_BASE_RPC='https://<your-dedicated-base-rpc>'   # dedicated VPS RPC
export PROD_MONGO_URL='mongodb://<prod-mongo-host>:27017'       # read-only intent
export PROD_DB_NAME='<prod_db_name>'
```

## 1. Fetch + checkout the EXACT HEAD, verify the source SHA
```bash
sudo mkdir -p "$VDIR" && sudo chown "$USER" "$VDIR" && cd "$VDIR"
[ -d repo ] || git clone <YOUR_REPO_URL> repo
cd repo
git fetch --all --tags --prune
git checkout complete-Base-M1-M4-live-shadow-composition
git fetch origin complete-Base-M1-M4-live-shadow-composition
git checkout f36d7c9dfb10f152bc5fc87f51d802f4ae995291    # detached, exact HEAD

# VERIFY source SHA == expected
test "$(git rev-parse HEAD)" = "f36d7c9dfb10f152bc5fc87f51d802f4ae995291" \
  && echo "SOURCE SHA OK" || { echo "SHA MISMATCH — ABORT"; exit 1; }
# Confirm the four workstreams are present:
git log --oneline -4
ls app/frontend/public/arbicore-emblem.png app/frontend/public/favicon.ico   # branding assets
grep -n "economic_state" app/backend/server.py | head -1                     # data-truth
```

## 2. Build build-arg identity (feeds /api/arbicore/version)
```bash
export GITSHA="$(git rev-parse HEAD)"
export GITTAG="$(git describe --tags --always --dirty)"
export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export APP_VERSION="arbicore-x-backend:$(git describe --tags --always)"
export BACKEND_IMAGE_TAG="arbicore-x-backend:validator-${GITSHA:0:12}"
export FRONTEND_IMAGE_TAG="arbicore-x-frontend:validator-${GITSHA:0:12}"
# Frontend needs a backend URL baked in. For an isolated validator use the
# loopback the validator backend will listen on (see step 4):
export REACT_APP_BACKEND_URL='http://127.0.0.1:8199'
```

## 3. Build a FRESH isolated validator image (does NOT touch the running stack)
Backend Dockerfile context is the repo root; it also runs `scripts.gen_build_info`
so the identity is embedded even without .git.
```bash
docker build --no-cache \
  -f deployment/docker/backend/Dockerfile \
  --build-arg GITSHA="$GITSHA" \
  --build-arg GITTAG="$GITTAG" \
  --build-arg BUILD_TIME="$BUILD_TIME" \
  --build-arg APP_VERSION="$APP_VERSION" \
  --build-arg IMAGE_REF="$BACKEND_IMAGE_TAG" \
  -t "$BACKEND_IMAGE_TAG" .

# (optional) frontend image for the branding/data-truth check in step 7
docker build --no-cache \
  -f deployment/docker/frontend/Dockerfile \
  --build-arg REACT_APP_BACKEND_URL="$REACT_APP_BACKEND_URL" \
  --build-arg GITSHA="$GITSHA" \
  -t "$FRONTEND_IMAGE_TAG" .
```

## 4. Start the ISOLATED validator backend (loopback only, read-only, safe env)
Create `$VDIR/.env.validator` — NOTE the safety flags are explicitly OFF and NO signing key:
```bash
cat > "$VDIR/.env.validator" <<EOF
MONGO_URL=$PROD_MONGO_URL
DB_NAME=$PROD_DB_NAME
ARBICORE_RPC_URL_BASE=$DEDICATED_BASE_RPC
ARBICORE_RPC_URL=$DEDICATED_BASE_RPC
ARBICORE_USD_NUMERAIRE=USDC
ARBICORE_ENV=validator
# --- SAFETY: all OFF / unset ---
ARBICORE_LIMITED_LIVE=0
ARBICORE_FULL_LIVE=0
ARBICORE_AUTOEXEC_AUTOSTART=0
# (do NOT add any *PRIVATE_KEY* / signer var)
EOF

docker network create arbicore-validator-net 2>/dev/null || true
docker run -d --name arbicore-validator \
  --network arbicore-validator-net \
  --env-file "$VDIR/.env.validator" \
  -p 127.0.0.1:8199:8001 \
  "$BACKEND_IMAGE_TAG"

sleep 8 && curl -fs http://127.0.0.1:8199/api/ && echo "  <- backend up"
```

## 5. Verify /api/arbicore/version reports REAL identity
```bash
curl -s http://127.0.0.1:8199/api/arbicore/version | python3 -m json.tool
# EXPECT: git_sha == f36d7c9dfb10f152bc5fc87f51d802f4ae995291 (or short 12),
#         git_tag set, build_time set (step-2 value), app_version set,
#         image_ref == $BACKEND_IMAGE_TAG, runtime_env == "validator".
#         NO "unknown"/"unset" for git_sha/git_tag/build_time.
```

## 6. Verify M3 fail-closed + LIMITED_LIVE/FULL_LIVE/signing/broadcast all OFF
```bash
# a) Runtime env inside the container shows no live flags and no signer:
docker exec arbicore-validator sh -c 'env | grep -iE "LIMITED_LIVE|FULL_LIVE|AUTOEXEC|PRIVATE_KEY|SIGNER|SIGNING" || echo "no live/signer vars set"'

# b) Mode endpoint refuses live transitions (needs an operator cookie — do the
#    login first if auth is enabled), current mode must be SHADOW/PAPER:
TOKEN_COOKIE=/tmp/vcj.txt
curl -s -X POST http://127.0.0.1:8199/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"<admin>","password":"<pass>"}' -c "$TOKEN_COOKIE" -o /dev/null -w "login=%{http_code}\n"
curl -s http://127.0.0.1:8199/api/arbicore/control/mode -b "$TOKEN_COOKIE" | python3 -m json.tool   # current_mode: SHADOW/PAPER
curl -s -X POST http://127.0.0.1:8199/api/arbicore/control/mode -b "$TOKEN_COOKIE" \
  -H 'Content-Type: application/json' -d '{"mode":"LIMITED_LIVE"}' \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);print("applied:",d.get("applied"),"mode:",d.get("current_mode"))'
# EXPECT: applied False, mode still SHADOW/PAPER (fail-closed refusal).
```

## 7. Verify the new frontend branding + data-truth build

### 7a. Rebuild ONLY the frontend from the LATEST HEAD (includes the nav.js /dashboard/* fix)
Backend stays `f36d7c9` (unchanged — do NOT rebuild it). Frontend HEAD = `5875f4c2912227bc83f742f9b0fa42df3651f3c5`.
```bash
cd "$VDIR/repo"
git fetch origin complete-Base-M1-M4-live-shadow-composition
git checkout 5875f4c2912227bc83f742f9b0fa42df3651f3c5
test "$(git rev-parse HEAD)" = "5875f4c2912227bc83f742f9b0fa42df3651f3c5" \
  && echo "FRONTEND SHA OK" || { echo "SHA MISMATCH — ABORT"; exit 1; }

export FE_SHA=5875f4c2912227bc83f742f9b0fa42df3651f3c5
# SAME-ORIGIN mode: the browser hits the validator nginx only; nginx proxies
# /api -> the backend container on the private network. NEVER expose :8199 publicly.
export REACT_APP_BACKEND_URL='/api'
docker build --no-cache \
  -f deployment/docker/frontend/Dockerfile \
  --build-arg REACT_APP_BACKEND_URL="$REACT_APP_BACKEND_URL" \
  --build-arg GITSHA="$FE_SHA" \
  -t "arbicore-x-frontend:validator-${FE_SHA:0:12}" .

docker rm -f arbicore-validator-fe 2>/dev/null || true
docker run -d --name arbicore-validator-fe \
  --network arbicore-validator-net \
  -p 127.0.0.1:8299:80 \
  -v "$VDIR/repo/deployment/validator/nginx.validator.conf:/etc/nginx/conf.d/default.conf:ro" \
  "arbicore-x-frontend:validator-${FE_SHA:0:12}"
sleep 4
# Prove the API proxy reaches the f36d7c9 backend (same-origin):
curl -s http://127.0.0.1:8299/api/arbicore/version | python3 -m json.tool
curl -s http://127.0.0.1:8299/api/ && echo "  <- /api proxied to validator backend OK"
```

### 7b. Verify branding + data-truth
```bash
# Browser title = ArbiCore X, no "Emergent | Fullstack App":
curl -s http://127.0.0.1:8299/ | grep -o '<title>[^<]*</title>'
curl -s http://127.0.0.1:8299/ | grep -qi 'Emergent | Fullstack App' && echo "STALE BRANDING!" || echo "no stale branding OK"
# Favicon assets present (200):
for a in favicon.ico arbicore-emblem-32.png arbicore-emblem.png; do \
  echo -n "$a -> "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8299/$a; done
# Data-truth intact — opportunities contract has no return_low/return_high, has economic_state:
curl -s "http://127.0.0.1:8199/api/arbicore/opportunities?limit=3" -b "$TOKEN_COOKIE" \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);it=(d.get("items") or [{}])[0];print("fields:",sorted(it.keys()));assert "return_low" not in it and "return_high" not in it;print("economic_state present:", "economic_state" in it)'
```

## 8. Run the real Base Spread-Widener Watch (dedicated RPC)
Single-pass scan (or set interval to loop). Writes a clean JSON snapshot.
```bash
docker exec \
  -e ARBICORE_M3_AUDIT_FILE=/tmp/spread_watch.json \
  -e ARBICORE_SPREAD_WATCH_BORROW_USD=10000 \
  arbicore-validator python -m scripts.m3_0_spread_widener_watch
docker exec arbicore-validator python -m json.tool /tmp/spread_watch.json | tee "$VDIR/spread_watch_$(date -u +%Y%m%dT%H%M%SZ).json"
# Look for flagged routes (snapshot keys: flagged / flagged_count / near_threshold):
docker exec arbicore-validator python3 -c 'import json;d=json.load(open("/tmp/spread_watch.json"));print("flagged_count:",d.get("flagged_count"),"| near_threshold_count:",d.get("near_threshold_count"));[print("FLAGGED:",r.get("name"),"est_net_usd=",r.get("est_net_usd"),"pools=",r.get("route_pools")) for r in d.get("flagged",[])]'
# To watch continuously: add  -e ARBICORE_SPREAD_WATCH_INTERVAL_S=20  and run without -d exit.
```
(If it prints `{"error":"no Base RPC configured (fail-closed)"}` the RPC env didn't reach the
container — recheck `.env.validator` ARBICORE_RPC_URL_BASE.)

## 9. When worth_m3_validation=true → full M3 READ-ONLY validator (confirm=False)
`m3_0_vps_validate.py` runs the pre-broadcast validator + broadcaster ladder with `confirm=False`,
so the sign + `eth_sendRawTransaction` branch is UNREACHABLE. No key, no broadcast.
```bash
# Provide the flagged route/plan as arg (JSON). Minimal example:
PLAN='{"strategy":"flash_loan_arbitrage","route":"<flagged route id>","borrow_usd":10000}'
docker exec \
  -e ARBICORE_M3_AUDIT_FILE=/tmp/m3_audit.json \
  arbicore-validator python -m scripts.m3_0_vps_validate "$PLAN"
docker exec arbicore-validator python -m json.tool /tmp/m3_audit.json | tee "$VDIR/m3_audit_$(date -u +%Y%m%dT%H%M%SZ).json"
```

## 10. Required successful M3 read-only evidence (assert)
```bash
docker exec arbicore-validator python3 - <<'PY'
import json
a=json.load(open("/tmp/m3_audit.json"))
gates_ok = a.get("m3_final_gates",{}).get("ok")
sent     = a.get("broadcast_ladder",{}).get("broadcast_sent")
verdict  = a.get("verdict",{}) or {}
sob      = verdict.get("signed_or_broadcast")
safe     = verdict.get("safe")
print("m3_final_gates.ok         =", gates_ok)
print("broadcast_ladder.broadcast_sent =", sent)
print("verdict.signed_or_broadcast     =", sob)
print("verdict.safe                    =", safe)
ok = (gates_ok is True) and (sent is False) and (sob is False) and (safe is True)
print("=> M3 GREEN (read-only)" if ok else "=> NOT GREEN / not safe — DO NOT proceed")
PY
```
PASS criteria: `m3_final_gates.ok=true`, `signed_or_broadcast=false`, `broadcast_sent=false`, `safe=true`.
Archive the audit JSON. This is the FIRST GENUINE BASE M3 GREEN evidence.

## 11. Teardown (leaves production untouched)
```bash
docker rm -f arbicore-validator arbicore-validator-fe 2>/dev/null || true
```

--------------------------------------------------------------------------------
## Post-green next steps (do NOT auto-run)
1. Controlled-live readiness checklist (human confirmation gate; still no autosigning).
2. Provision a dedicated small-capital signer OUT-OF-BAND only when you explicitly decide.
3. First small HUMAN-CONFIRMED trade — operator presses confirm; single tx; capped size.
Never flip LIMITED_LIVE/FULL_LIVE or provision a key as part of validation.
