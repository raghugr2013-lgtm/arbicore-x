# P2 Final Deployment & Rollback Runbook

**Status:** Proposed runbook only — **NOT EXECUTED**.  
**Audit date (UTC-local evidence):** 2026-10-09  
**Independent re-audit (UTC):** `2026-10-09T05:19Z` (read-only command/digest verification)  
**Audit posture:** Read-only. No build, deploy, recreate, commit, push, merge, or config mutation performed during this audit.  
**Final verdict:** **BLOCKED** (security gate — see §G). Deploy commands and digest-pinned rollback remain reviewed and held for a later, separate authorisation after security prerequisites are satisfied.

Related package docs (do not substitute for this runbook):  
`P2_RELEASE_MANIFEST.md`, `P2_RELEASE_CHECKSUMS.txt`, `P2_DIFF_AUDIT.md`, `P2_FINAL_REVIEW.md`, `P2_DEPLOYMENT_PREFLIGHT.md`, `P2_TEST_RESULTS.md`.  
Security baseline: `SECURITY_REMEDIATION_STATUS.md` + `artifacts/security/s1b_vault_rotation_preflight_20261009/S1B_PHASE1_PREFLIGHT.md`.

---

## A. Verified current-state evidence

### A.1 Repository / branch / HEAD

| Check | Expected | Observed (this audit) | Result |
|---|---|---|---|
| Repository | `/home/raghu/projects/arbicore-x-cert` | same | **PASS** |
| Branch | `cert/gate7-dynamic-profitability-20261007` | same | **PASS** |
| HEAD / base commit | `9244ebdee6a95188d925084e7e10d4a972cda7ad` | same | **PASS** |
| HEAD subject | `fix(quoter): host-scoped 429 cooldown with bounded retry and A→F failover` | same | **PASS** |
| Working tree | Dirty (expected) | Dirty: P2 seven-file set + many unrelated paths (~141 porcelain entries) | **PASS (documented)** |

### A.2 P2 patch identity (seven-file package)

| Check | Result |
|---|---|
| Combined patch SHA-256 | `56739a3d65470f61abfe3becfdf5a929576c41ce4ddc0a8bdd80615395690669` |
| Matches `P2_RELEASE_CHECKSUMS.txt` | **PASS** (full checksum file recomputed; `diff` empty) |
| Paths in `P2_ONLY_COMBINED.patch` | Exactly **7** approved files; no extras |
| Forbidden tokens in patch (`fresh_eligible`, `per_chain_backlog`, `per_strategy_backlog`) | **ABSENT** |
| Same tokens in dirty WT `discovery_queue.py` | **PRESENT** (unrelated work preserved; must not ship) |

Approved paths:

1. `app/backend/arbicore/data/discovery_queue.py`
2. `app/backend/arbicore/models/discovery.py`
3. `app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py`
4. `app/backend/arbicore/data/mongo/evidence_bundles_repo.py`
5. `app/backend/tests/test_flashloan_diagnostic_provenance.py`
6. `app/backend/tests/test_p2_flashloan_timing_instrumentation.py`
7. `app/backend/tests/test_p2_evidence_persisted_mongo.py`

### A.3 Clean-base apply verification (isolated; non-production)

Performed this audit in temp tree `/tmp/p2_final_audit_CpZK` (ephemeral evidence path; recreate at deploy time):

```text
git archive 9244ebdee6a95188d925084e7e10d4a972cda7ad | tar -x -C <WORKDIR>
git apply --check P2_ONLY_COMBINED.patch   # exit 0
git apply P2_ONLY_COMBINED.patch           # exit 0
```

Post-apply spot-checks:

- Durable `claimed_at` comment present; `mark_processed` clears only `claimed_by` / `claimed_until`.
- Applied `discovery_queue.py` has **no** `fresh_eligible` / backlog breakdowns.
- Option D stamp `_stamp_insert_evidence_persisted` present; verifier ternary / fail-safe timing present.
- New test modules present.

**Packaging quirk (non-blocking):** `01_discovery_queue_P2_ONLY.patch` `---` header is `/dev/fd/63`. Use `git apply` (verified). Do not assume every `patch(1)` variant tolerates that header.

### A.4 Production runtime (read-only inspect)

| Item | Observed |
|---|---|
| Container | `arbicore-x-backend-new` |
| Status / health | `running` / `healthy` |
| StartedAt | `2026-10-08T08:33:43.476717081Z` |
| RestartCount | `0` |
| Image tag | `arbicore-x-backend:hybrid-e-rpc-9244ebd` |
| Image ID / local digest | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |
| Publish | `127.0.0.1:8001->8001/tcp` |
| Compose project / service | `compose` / `backend` |
| Compose working dir | `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose` |
| Compose files | `docker-compose.prod.yml` + `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` |

Safety / execution posture (non-secret):

| Flag | Value |
|---|---|
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `ARBICORE_SCANNER_AUTOSTART` | `true` |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` |
| `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` | `true` |
| `ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS` | `6` |
| Strategy scanners (`DEX`/`CEX`/`FUNDING`/`LAUNCH`) | `false` |
| `ARBICORE_GIT_TAG` | `hybrid-e-rpc-9244ebd` |
| `ARBICORE_GIT_SHA` | `fff0d0eced5ce3783cff18fb976e55a2a6504504` (**stale** vs base `9244ebde…`; must be corrected on P2 deploy) |

Current override (exists; 687 bytes; verified 2026-10-09) sets image tag + identity + the safety flags above. Rendered `docker compose config` shows **only** service `backend` from that project slice when querying `--services` in the established pattern; backend `depends_on` is null in the rendered backend service (recreate with `--no-deps` remains the correct backend-only pattern).

### A.5 Test evidence (package; not re-executed in this audit)

Last recorded focused result (`P2_TEST_RESULTS.md` / `pytest_focused_output.txt`): **35 passed**.  
This final audit **did not** re-run pytest (read-only; avoid throwaway Mongo writes). Re-run is a **mandatory pre-deploy gate** in section D/B.

### A.6 Critical packaging constraint

| Do | Do not |
|---|---|
| Build from `git archive` of `9244ebde…` + `P2_ONLY_COMBINED.patch` | Build from dirty `/home/raghu/projects/arbicore-x-cert` working tree |
| Ship P2-only `discovery_queue` hunks | Copy WT `discovery_queue.py` wholesale (includes backlog reporting) |
| Use v2 compose path + new override | Edit production `.env`, Mongo Network Config, or unrelated services |

---

## B. Exact proposed deployment commands

> **STOP:** Execute only after separate human authorisation. Commands below are the authorised procedure draft.

### B.0 Constants

```bash
export REPO=/home/raghu/projects/arbicore-x-cert
export BASE=9244ebdee6a95188d925084e7e10d4a972cda7ad
export PATCH="$REPO/artifacts/performance/p2_release/P2_ONLY_COMBINED.patch"
export EXPECT_PATCH_SHA=56739a3d65470f61abfe3becfdf5a929576c41ce4ddc0a8bdd80615395690669
export P2_TAG=p2-instrumentation-9244ebd
export COMPOSE_DIR=/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
export CUR_OVERRIDE=/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml
export P2_OVERRIDE=/tmp/arbicore-${P2_TAG}-override.yml
export ROLLBACK_IMAGE_ID=sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52
export ROLLBACK_TAG=arbicore-x-backend:hybrid-e-rpc-9244ebd
export ROLLBACK_PIN_TAG=arbicore-x-backend:rollback-p2-pre-40b2116b
```

### B.1 Pre-flight identity freeze (before any build)

```bash
# Confirm production still on the audited image
test "$(docker inspect -f '{{.Image}}' arbicore-x-backend-new)" = "$ROLLBACK_IMAGE_ID"
test "$(docker inspect -f '{{.Config.Image}}' arbicore-x-backend-new)" = "$ROLLBACK_TAG"
test "$(docker inspect -f '{{.State.Health.Status}}' arbicore-x-backend-new)" = "healthy"

# Confirm rollback override still present
test -f "$CUR_OVERRIDE"

# Pin an immutable local alias to the exact image ID (tag alone is not enough later)
docker tag "$ROLLBACK_IMAGE_ID" "$ROLLBACK_PIN_TAG"
test "$(docker image inspect -f '{{.Id}}' "$ROLLBACK_PIN_TAG")" = "$ROLLBACK_IMAGE_ID"

# Record freeze evidence
docker image inspect -f 'Id={{.Id}} RepoTags={{json .RepoTags}}' "$ROLLBACK_IMAGE_ID" \
  | tee /tmp/p2_rollback_image_freeze.txt
```

**Stop if** container image ID ≠ `40b2116b…`, health ≠ healthy, or override missing.

### B.2 Clean source + patch apply

```bash
WORKDIR=$(mktemp -d /tmp/p2_deploy_src_XXXX)
git -C "$REPO" archive "$BASE" | tar -x -C "$WORKDIR"
cd "$WORKDIR"

echo "$EXPECT_PATCH_SHA  $PATCH" | sha256sum -c -
git apply --check "$PATCH"
git apply "$PATCH"

grep -n 'Keep claimed_at durable' app/backend/arbicore/data/discovery_queue.py
! grep -nE 'fresh_eligible|per_chain_backlog|per_strategy_backlog' \
  app/backend/arbicore/data/discovery_queue.py
```

**Stop if** checksum mismatch, apply conflict, or forbidden tokens appear.

### B.3 Focused tests (non-production Mongo)

```bash
cd "$WORKDIR/app/backend"
MONGO_URL=mongodb://172.26.0.2:27017 PYTHONPATH=. \
  /home/raghu/projects/arbicore-x-v2/.venv/bin/python -m pytest \
  tests/test_p2_evidence_persisted_mongo.py \
  tests/test_p2_flashloan_timing_instrumentation.py \
  tests/test_flashloan_diagnostic_provenance.py \
  tests/test_m2_3_evidence_bundle.py \
  -q --tb=line -o addopts= | tee /tmp/p2_predeploy_pytest.txt
```

**Required:** `35 passed`.  
**Stop if** any failure, or Mongo unreachable such that required round-trip coverage is skipped/unavailable.

### B.4 Build image from verified clean tree

```bash
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)

docker build --network=host \
  -f "$WORKDIR/deployment/upgrade/backend/Dockerfile" \
  --build-arg GITSHA="$BASE" \
  --build-arg GITTAG="$P2_TAG" \
  --build-arg BUILD_TIME="$BUILD_TIME" \
  --build-arg APP_VERSION="$P2_TAG" \
  --build-arg ARBICORE_GIT_SHA="$BASE" \
  --build-arg ARBICORE_GIT_TAG="$P2_TAG" \
  -t "arbicore-x-backend:$P2_TAG" \
  "$WORKDIR/app/backend"

# Record unambiguous image identity (do not rely on tag alone)
P2_IMAGE_ID=$(docker image inspect -f '{{.Id}}' "arbicore-x-backend:$P2_TAG")
echo "$P2_IMAGE_ID" | tee /tmp/p2_new_image_id.txt
test -n "$P2_IMAGE_ID"
test "$P2_IMAGE_ID" != "$ROLLBACK_IMAGE_ID"
```

Notes:

- Backend `.dockerignore` excludes `tests/`; runtime needs the four runtime modules, not the new tests.
- Passing both `GITSHA` and `ARBICORE_GIT_SHA` matches the established Phase-0 pattern and the Dockerfile’s dual ARG/ENV stamping.

**Stop if** build fails or new image ID equals rollback ID unexpectedly.

### B.5 Create P2 override (identity + safety; no secret edits)

Write **new** file `$P2_OVERRIDE` (do not edit `$CUR_OVERRIDE`, compose `.env`, or backend `.env`):

```yaml
services:
  backend:
    image: arbicore-x-backend:p2-instrumentation-9244ebd
    build: null
    environment:
      ARBICORE_GIT_SHA: "9244ebdee6a95188d925084e7e10d4a972cda7ad"
      ARBICORE_GIT_TAG: "p2-instrumentation-9244ebd"
      ARBICORE_RUNTIME_ENV: "production"
      ARBICORE_ENV: "production"
      ARBICORE_EXECUTION_MODE: "SHADOW"
      ARBICORE_AUTOEXEC_AUTOSTART: "false"
      ARBICORE_RUNTIME_AUTOSTART: "false"
      ARBICORE_SCANNER_AUTOSTART: "true"
      ARBICORE_SHADOW_CERT_ENABLED: "true"
      ARBICORE_BORROW_SIZER_ENABLED: "true"
      ARBICORE_PRICE_FEED_ENABLED: "true"
      ARBICORE_FLASH_LOAN_SHADOW_ROUTE: "true"
      ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS: "6"
```

### B.6 Compose render gate (backend-only recreate)

```bash
cd "$COMPOSE_DIR"

docker compose --env-file .env \
  -f docker-compose.prod.yml \
  -f "$P2_OVERRIDE" \
  config > /tmp/p2_compose_render.yml

# Hard gates on rendered backend identity / safety
python3 - <<'PY'
import sys, yaml
d = yaml.safe_load(open("/tmp/p2_compose_render.yml"))
b = d["services"]["backend"]
env = b.get("environment") or {}
if isinstance(env, list):
    env = {e.split("=",1)[0]: (e.split("=",1)[1] if "=" in e else "") for e in env}
checks = {
    "image": b.get("image") == "arbicore-x-backend:p2-instrumentation-9244ebd",
    "container_name": b.get("container_name") == "arbicore-x-backend-new",
    "mode": env.get("ARBICORE_EXECUTION_MODE") == "SHADOW",
    "autoexec": str(env.get("ARBICORE_AUTOEXEC_AUTOSTART")).lower() == "false",
    "runtime_autostart": str(env.get("ARBICORE_RUNTIME_AUTOSTART")).lower() == "false",
    "git_sha": env.get("ARBICORE_GIT_SHA") == "9244ebdee6a95188d925084e7e10d4a972cda7ad",
    "git_tag": env.get("ARBICORE_GIT_TAG") == "p2-instrumentation-9244ebd",
    "workers": str(env.get("ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS")) == "6",
}
bad = [k for k,v in checks.items() if not v]
print(checks)
if bad:
    raise SystemExit(f"RENDER_GATE_FAIL: {bad}")
print("RENDER_GATE_OK")
PY
```

Optional diff awareness (human review): compare prior render of current override vs `/tmp/p2_compose_render.yml` and confirm only image + `ARBICORE_GIT_SHA` + `ARBICORE_GIT_TAG` change.

**Stop if** render changes execution mode, AUTOEXEC, runtime autostart, worker count, RPC/env secrets surface unexpectedly, or more than `backend` would be targeted.

### B.7 Recreate backend only

```bash
cd "$COMPOSE_DIR"

docker compose --env-file .env \
  -f docker-compose.prod.yml \
  -f "$P2_OVERRIDE" \
  up -d --no-deps --force-recreate --no-build backend
```

**Must use** `--no-deps --force-recreate --no-build` and service name `backend` only.

---

## C. Exact rollback commands and image-identity verification

### C.1 Preferred rollback (digest-pinned)

Tag alone is **not** sufficient if `hybrid-e-rpc-9244ebd` is ever retagged. Prefer the frozen image ID / pin tag from B.1.

```bash
cd "$COMPOSE_DIR"

# Prove the rollback bytes still exist
test "$(docker image inspect -f '{{.Id}}' "$ROLLBACK_PIN_TAG")" = "$ROLLBACK_IMAGE_ID"
# Also acceptable if pin tag missing but original tag still points at same ID:
# test "$(docker image inspect -f '{{.Id}}' "$ROLLBACK_TAG")" = "$ROLLBACK_IMAGE_ID"

# Restore prior override exactly (includes prior stale GIT_SHA — intentional config restore)
test -f "$CUR_OVERRIDE"

# If CUR_OVERRIDE was lost, recreate it with image pinned by digest:
#   image: arbicore-x-backend@sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52
# plus the same environment block as the audited /tmp override.

docker compose --env-file .env \
  -f docker-compose.prod.yml \
  -f "$CUR_OVERRIDE" \
  up -d --no-deps --force-recreate --no-build backend
```

If the tag `hybrid-e-rpc-9244ebd` no longer resolves to `40b2116b…`, **do not** proceed with tag-only rollback. Instead write a temporary override with:

```yaml
services:
  backend:
    image: arbicore-x-backend@sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52
    build: null
    environment:
      # same keys/values as audited /tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml
```

### C.2 Rollback verification (mandatory)

```bash
test "$(docker inspect -f '{{.Image}}' arbicore-x-backend-new)" = "$ROLLBACK_IMAGE_ID"
test "$(docker inspect -f '{{.State.Health.Status}}' arbicore-x-backend-new)" = "healthy"

docker inspect arbicore-x-backend-new --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E 'ARBICORE_(EXECUTION_MODE|AUTOEXEC_AUTOSTART|RUNTIME_AUTOSTART|GIT_SHA|GIT_TAG|FLASH_LOAN_VERIFICATION_WORKERS)='
```

Required after rollback:

| Check | Required value |
|---|---|
| Image ID | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |
| Health | `healthy` |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| Workers | `6` |
| Signing / broadcasting / AUTOEXEC enablement | unchanged / still disabled |

Historical evidence rows written under P2 (if any) remain harmless append-only audit data — **no migration to undo**.

---

## D. Pre-deployment and post-deployment checklists

### D.1 Pre-deployment checklist

- [ ] Separate human deployment authorisation recorded (this runbook alone is not authorisation).
- [ ] Repo HEAD still `9244ebdee6a95188d925084e7e10d4a972cda7ad` (or re-verify apply-check if base moved).
- [ ] `sha256sum` of `P2_ONLY_COMBINED.patch` == `56739a3d…95690669`.
- [ ] Clean archive + `git apply` succeeds; forbidden backlog tokens absent.
- [ ] Focused tests: **35 passed** against non-production Mongo.
- [ ] Production still on image ID `sha256:40b2116b…`; health `healthy`.
- [ ] Rollback pin tag created; `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` present (or digest override prepared).
- [ ] New image tag `p2-instrumentation-9244ebd` built; **new image ID recorded**.
- [ ] Compose render gate passes; only backend recreate planned (`--no-deps`).
- [ ] Override preserves SHADOW + AUTOEXEC/runtime autostart false; workers=6; scanner autostart unchanged.
- [ ] No edits to production secrets/env files, RPC Mongo Network Config, or unrelated services.
- [ ] Signing / broadcasting remain disabled; no AUTOEXEC enablement planned.

### D.2 Post-deployment checklist

#### D.2.1 Container health / startup / identity

- [ ] `arbicore-x-backend-new` is `running` and `healthy` within the agreed window (healthcheck start-period ≈ 20s; allow retries).
- [ ] `Config.Image` == `arbicore-x-backend:p2-instrumentation-9244ebd`.
- [ ] Container `Image` ID == recorded `/tmp/p2_new_image_id.txt`.
- [ ] `ARBICORE_GIT_SHA` == `9244ebdee6a95188d925084e7e10d4a972cda7ad` (stale `fff0d0ec…` gone).
- [ ] `ARBICORE_GIT_TAG` == `p2-instrumentation-9244ebd`.
- [ ] RestartCount acceptable (no crash loop).
- [ ] Unrelated containers (frontend/caddy/nginx/etc.) not recreated.

#### D.2.2 Execution safety unchanged

- [ ] `ARBICORE_EXECUTION_MODE=SHADOW`
- [ ] `ARBICORE_AUTOEXEC_AUTOSTART=false`
- [ ] `ARBICORE_RUNTIME_AUTOSTART=false`
- [ ] `ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS=6`
- [ ] Strategy scanner toggles still false; SHADOW cert / flash-loan shadow route still true as before
- [ ] No new signing/broadcast activity attributable to this deploy

#### D.2.3 `claimed_at` retention

After a candidate is processed under the new image:

- [ ] Candidate document still has non-null `claimed_at`
- [ ] `claimed_by` is null and `claimed_until` is null (lock released)
- [ ] Eligibility still driven by `verified_outcome` / `expires_at` / `claimed_until` (not by durable `claimed_at`)

#### D.2.4 Stage-timing fields (null vs zero)

On newly written flash-loan evidence bundles:

- [ ] `diagnostics.timing` present
- [ ] Stage timings use **null** for missing/not-run stages (not coerced to `0` unless the stage actually measured ~0)
- [ ] Timing failures are fail-safe (verdict path unaffected)

#### D.2.5 `evidence_persisted` semantics (Option D)

- [ ] Successful Mongo insert stores `diagnostics.timing.evidence_persisted: true` on the **stored** row
- [ ] Failed insert does **not** leave a success row claiming `true`
- [ ] Marker means insert success only — **not** profitability, trade confirmation, or capture

#### D.2.6 Non-interference (strategy / risk / RPC / workers / execution)

- [ ] No change to strategy verdict thresholds / Gate behaviour vs pre-deploy sample
- [ ] No change to risk limits, eligibility rules, RPC configuration, or worker count
- [ ] No change to execution behaviour beyond observability fields on new evidence / durable `claimed_at`

---

## E. STOP / ROLLBACK conditions

### E.1 STOP before recreate (abort deploy; production untouched)

Abort immediately if any of:

1. Patch checksum ≠ `56739a3d65470f61abfe3becfdf5a929576c41ce4ddc0a8bdd80615395690669`
2. `git apply` fails or introduces forbidden backlog tokens
3. Focused tests ≠ 35 passed, or required Mongo round-trips unavailable
4. Current production image ID ≠ `sha256:40b2116b…` (baseline moved; re-audit required)
5. Compose render alters SHADOW / AUTOEXEC / runtime autostart / workers / RPC posture unexpectedly
6. Deployer is about to build from the dirty cert working tree
7. Human authorisation is absent or ambiguous

### E.2 ROLLBACK after recreate

Execute section C immediately if any of:

1. Container not `healthy` within agreed window / crash loop
2. Running image ID ≠ recorded P2 image ID, or git tag/SHA identity incorrect
3. `ARBICORE_EXECUTION_MODE` ≠ `SHADOW`
4. `ARBICORE_AUTOEXEC_AUTOSTART` or `ARBICORE_RUNTIME_AUTOSTART` becomes true
5. Worker count / RPC / scanner safety posture drifts unexpectedly
6. Instrumentation missing on new evidence after adequate sample window, or semantics wrong (`evidence_persisted=true` without insert success; `claimed_at` cleared on process; null/zero timing inverted)
7. Any signing/broadcast/AUTOEXEC/live-trading regression
8. Unexpected compose/service recreation beyond `backend`

### E.3 Do-not-do list (still binding at deploy time)

- Do not enable scanners beyond current autostart posture, signing, broadcasting, AUTOEXEC, or live trading
- Do not “fix forward” by deploying dirty-tree backlog/frontend/ledger changes under the P2 label
- Do not roll back to a newer local tag (e.g. `b1-route-coverage-1b52d09`) unless separately authorised
- Do not treat tag `hybrid-e-rpc-9244ebd` as identity without verifying image ID `40b2116b…`

---

## F. Re-audit evidence (2026-10-09T05:19Z, READ-ONLY)

| Check | Result |
|---|---|
| Branch | `cert/gate7-dynamic-profitability-20261007` **PASS** |
| HEAD | `9244ebdee6a95188d925084e7e10d4a972cda7ad` **PASS** |
| Patch SHA-256 | `56739a3d…95690669` **PASS** (`sha256sum -c`) |
| Seven-file apply scope | All 7 expected paths changed in isolated archive; no unexpected source edits **PASS** |
| Forbidden tokens in patch / applied queue | `fresh_eligible` / backlog breakdowns **ABSENT** **PASS** |
| Isolated `git apply` | **PASS** |
| Production image ID | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` **PASS** |
| Override present | `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` **PASS** |
| SHADOW / AUTOEXEC=false / RUNTIME_AUTOSTART=false | **PASS** |
| Legacy b7/h05/w1 | **exited** **PASS** |
| Sections B–C commands | Documented only — **NOT EXECUTED** |

Packaging note (non-blocking): `01_discovery_queue_P2_ONLY.patch` / combined patch use `/dev/fd/63` headers for some hunks; `git apply` tolerates this (verified).

---

## G. Security prerequisites (unresolved — binding)

From `SECURITY_REMEDIATION_STATUS.md` / S1-B Phase 1 (not assumed resolved):

| Risk | Must remediate or explicitly contain before P2? | Current state |
|---|---|---|
| Shared legacy/current `VAULT_KEY` + live `evm_sign` signing secret | **YES — hard gate** | Still shared sha12 `a46000441419`; decryptable `evm_sign` present; Phase 2 rotation **not** approved/executed |
| Unrotated Alchemy keys + missing log redaction | **YES — contain or remediate** | Redaction absent from running image; keys still logged |
| MongoDB root app credentials | Prefer remediate; may accept explicit residual risk waiver | Still `root` |
| Bootstrap token + public `/docs` | Prefer remediate / Caddy lock down | Still exposed |
| Plaintext admin in env/backups | Prefer scrub; JWT/admin already rotated once | Still in files |
| Deployer private key on disk | Assess/migrate or explicit waiver | Balance/migration **UNKNOWN** |

**Hard BLOCK rule (this audit):** while a signing-capable `evm_sign` secret remains decryptable under a `VAULT_KEY` also present in stopped legacy `Config.Env` and many on-disk backups, **P2 deployment remains BLOCKED** even though the patch/runbook mechanics are sound. Execution controls (SHADOW / AUTOEXEC false / no sendRaw in 60m) were independently verified, but they do **not** clear the vault exposure gate.

P2 must not be used as a vehicle to rotate vault/Alchemy/Mongo secrets.

---

## H. Final verdict

### BLOCKED

**What passed (mechanics):** patch integrity, seven-file scope, clean-base apply, production digest pin, digest-aware rollback design, SHADOW/AUTOEXEC/runtime safety flags, legacy stopped.

**What blocks authorisation:** unresolved security gate in §G — especially shared `VAULT_KEY` + live `evm_sign`. After S1-B Phase 2 (or an explicit written residual-risk acceptance covering vault containment), re-open this runbook for a **separate** human deployment authorisation of sections B–C.

**Not performed:** image build, compose recreate, production restart, focused pytest re-run, live instrumentation sampling, credential rotation.

**This document does not authorise deployment.**
