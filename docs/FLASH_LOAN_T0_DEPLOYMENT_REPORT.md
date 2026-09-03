# ArbiCore X — TIER-0 Deployment Report

**Scope:** T0 correctness only. No T1/T2, no chains, no frontend, no new MEV strategies, no live trading, no auto-promotion, no gate changes, no signing changes.

## ⚠️ Execution boundary (read first)
This Emergent workspace has **no access to your live VPS**, your `factory-mongo/arbicore_x`, your Docker host, or your Git remote. I therefore **cannot** build your image, dump your Mongo, rotate your PAT, push commits, restart your containers, or call your live endpoints from here.

What this report contains:
- **§ REHEARSAL** — a full local deployment rehearsal I executed with the exact production config (`ARBICORE_CANONICAL_STRICT_PROVENANCE=true`), proving the deploy is safe. All checks **PASS**.
- **§ RUNBOOK** — copy-paste commands for **you** to run on the VPS.
- **A–O** — the report structure you requested. Items I proved locally are marked **REHEARSED — PASS**; items that can only be executed/observed on the VPS are marked **OPERATOR ACTION (VPS)** with a blank to fill from your run.

---

## § REHEARSAL (executed here, prod config) — all PASS
Booted the real app via `uvicorn server:app` on a throwaway Mongo with:
`MONGO_URL=…localhost DB_NAME=arbicore_t0_deploy_rehearsal JWT_SECRET=… ARBICORE_CANONICAL_STRICT_PROVENANCE=true ARBICORE_RPC_URL=<generic> ARBICORE_RPC_URL_BASE=<chain-specific>`

| Check | Result |
|---|---|
| App boots + `Application startup complete` | PASS |
| Canonical FL scanner activates with **live** quote provider | PASS (`quote_provider='live'`) |
| `GET /engine/flash-loan/readiness` (auth) | PASS → `{ready:true, active:true, quote_provider:"live", readiness_error:null}` |
| `GET /certification/provenance-split` (auth) | PASS → `{real:0, synthetic:0, synthetic_executable_excluded:0, executable_real:0}` |
| `GET /execution/mode/flash_loan_arbitrage` | PASS → `mode=SHADOW, seeded=true, broadcast_allowed=false` |
| All seeded modes | PASS → cex/cross_chain/dex=PAPER, flash_loan=SHADOW; **no LIMITED_LIVE/FULL_LIVE** |
| Strict write-gate | PASS → SIMULATED **REJECTED**, REAL accepted (with flag=true) |
| Gate 7 $25 floor | PASS → 24.99 fail / 25.00 pass (unchanged) |
| Gate 8 fail-closed | PASS → tvl=0 → denied, `liquidity_unverifiable=true` |
| RPC resolution precedence | PASS → chain-specific `ARBICORE_RPC_URL_BASE` selected over generic |
| Endpoints auth-gated | PASS → 401 `{"detail":"not_authenticated"}` unauthenticated |
| Unit suite `tests/test_t0_correctness.py` | PASS → 19/19 |

---

## § RUNBOOK (operator, on VPS)

> Replace `<...>`. Never echo secrets to logs. Do NOT reset/clean/stash the working tree.

**1. Preserve tree + rotate PAT (before any push):**
```bash
git -C <repo> status              # confirm Dockerfile (Foundry/Anvil) + 44 URL edits present
# Remove the token-in-URL remote and re-add via a credential helper / SSH:
git -C <repo> remote set-url origin git@github.com:<org>/arbicore-x.git   # SSH, no PAT
# (or) use a fresh fine-grained PAT via a credential manager, NOT embedded in the URL.
# Revoke the old exposed PAT in GitHub → Settings → Developer settings → Tokens.
```

**2. Branch + commits off baseline (no destroy of unrelated work):**
```bash
git -C <repo> checkout -b t0/flash-loan-correctness 43230f6 || git checkout t0/flash-loan-correctness
# Commit 1 — T0 app correctness (all arbicore/** T0 files + server.py + test)
git add app/backend/arbicore app/backend/server.py app/backend/tests/test_t0_correctness.py
git commit -m "feat(t0): flash-loan correctness foundation + live readiness/provenance wiring"
# Commit 2 — infra, Dockerfile ONLY (independent revert)
git add <path>/Dockerfile
git commit -m "build(infra): add git + pinned Foundry/Anvil v1.7.1"
git push -u origin t0/flash-loan-correctness
```
Do NOT merge `feature/ui-v2-slices-0-2`, `archive-v1`, or `scanner-bootstrap-validator-fix`.

**3. Mongo backup (before migration):**
```bash
mongodump --uri="$MONGO_URL" --db=arbicore_x --out=/backups/arbicore_x_$(date +%F_%H%M) \
  && sha256sum -c <(find /backups/arbicore_x_* -type f -exec sha256sum {} \;) | tail -1
# No deletes are performed by T0. Historical evidence/discovery are retained.
```

**4. Build + deploy T0 image:**
```bash
docker compose build backend
docker compose up -d --no-deps backend        # frontend only if your compose requires it; no FE code changed
# Set the flag (compose env / .env consumed by the backend service):
#   ARBICORE_CANONICAL_STRICT_PROVENANCE=true
# Leave SIGNING_ACTIVE_KEY_VERSION UNSET (evidence stays explicitly unsigned).
```

**5. Additive migration (idempotent, dry-run first):**
```bash
docker compose exec backend python -m arbicore.scripts.t0_provenance_backfill          # DRY-RUN
docker compose exec backend python -m arbicore.scripts.t0_provenance_backfill --apply   # optional
```

**6. Verify (authenticated operator):**
```bash
TOKEN via your operator login; then:
curl -s .../api/arbicore/engine/flash-loan/readiness
curl -s .../api/arbicore/certification/provenance-split
curl -s .../api/arbicore/execution/mode/flash_loan_arbitrage
```

**Rollback:** `docker compose up -d backend` on the previous image tag; set `ARBICORE_CANONICAL_STRICT_PROVENANCE=false` + `ARBICORE_TVL_PROVIDER=sentinel` to restore prior behavior without redeploy; restore `mongodump` only if `--apply` backfill must be reverted (additive fields need no restore).

---

## A. Backup confirmation
**OPERATOR ACTION (VPS):** run §RUNBOOK-3. Record: dump path `__`, SHA256 verified `__`, collection counts captured `__`.

## B. Commits created
**OPERATOR ACTION (VPS):** §RUNBOOK-2. Record: Commit1 `__`, Commit2(Dockerfile) `__`, branch `t0/flash-loan-correctness` off `43230f6`. (Baseline & separation prepared/validated here.)

## C. Image / tag deployed
**OPERATOR ACTION (VPS):** record image tag/digest `__` (label `arbicore.gitsha` should be the T0 commit).

## D. Migration result
Additive/idempotent only; **REHEARSED — PASS** (script is dry-run by default, contains no `delete_many`/`drop`/`delete_one`). VPS dry-run counts: `__`; applied: `__`.

## E. Health results
Local **REHEARSED — PASS** (boot + startup complete + scanner live). VPS: container health `__`, Mongo connectivity `__`, **DB identity = `factory-mongo/arbicore_x`** `__` (already confirmed by you).

## F. Readiness endpoint result
**REHEARSED — PASS** → `{ready:true, active:true, quote_provider:"live", readiness_error:null}`. VPS value: `__`.

## G. Provenance-split result
**REHEARSED — PASS** → keys `{real, synthetic, synthetic_executable_excluded, executable_real}` (0 on fresh DB). VPS value: `__`.

## H. Execution mode result
**REHEARSED — PASS** → `flash_loan_arbitrage=SHADOW`, broadcast disabled, seeded; no strategy LIMITED_LIVE/FULL_LIVE. VPS value: `__`.

## I. Canonical opportunity / provenance counts (before vs after)
**OPERATOR ACTION (VPS):** capture before/after:
```
before: db.arbicore_opportunities.countDocuments({})              = __
        db.arbicore_opportunities.countDocuments({source_data_quality:"SIMULATED"}) = __
after:  new canonical rows all provenance ∈ {REAL,VERIFIED_REAL}  = __ (no NEW SIMULATED accepted)
        historical SIMULATED evidence retained (no deletes)        = __
```
Reminder: a **drop in executable opportunity count is expected** (synthetic removed) — NOT a regression.

## J. Gate 7 / Gate 8 verification
**REHEARSED — PASS:** Gate 7 $25 floor unchanged (24.99 fail / 25.00 pass); Gate 8 fails closed on unverifiable TVL (`liquidity_unverifiable`). VPS gate histogram: `__`.

## K. RPC resolution
**REHEARSED — PASS:** precedence `ARBICORE_RPC_URL_BASE` > `ARBICORE_RPC_URL` > legacy. You confirmed live RPC = `ARBICORE_RPC_URL` (Base Alchemy). VPS resolved endpoint host (presence only, no secret): `__`.

## L. PaperRunner verification
`_fetch_opps` filters to `LEARNING_ELIGIBLE_PROVENANCE={REAL,VERIFIED_REAL}` — **unit-verified PASS** (`test_paper_runner_filters_to_real_provenance`). VPS: confirm PaperRunner log shows no SIMULATED intake `__`.

## M. Rollback readiness
Prepared: previous image tag redeploy; flag toggles (`ARBICORE_CANONICAL_STRICT_PROVENANCE=false`, `ARBICORE_TVL_PROVIDER=sentinel`); `mongodump` restore path. **REHEARSED — flags proven to change behavior.** VPS previous tag on hand: `__`.

## N. Unexpected issues
- Local rehearsal required `JWT_SECRET` to be set for `/api/auth/*` (500 without it) — ensure it is present in the VPS backend env (it already is in production).
- None affecting T0 logic. No regressions (80 existing + 19 T0 unit tests pass).

## O. Explicit T0 PASS/FAIL
- **Code + config correctness (rehearsed with prod flag): PASS** for all 11 verification items.
- **VPS deployment: PENDING OPERATOR EXECUTION** (I cannot reach the VPS). Fill A/B/C/E/I/K/L blanks from your run to close.

**STOP — awaiting your next authorization. No T1/T2 started.**
