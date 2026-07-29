# arbicore-x-deploy — Production Realignment Bundle (auto-detecting)

Non-destructive, in-place upgrade of the VPS backend to the **audited ArbiCore X build
(0.1.0)**. The MongoDB container and its data volume are **preserved untouched**; only
the backend container is replaced.

This bundle supersedes the older manual `arbicore-x-prod-bundle/` (which required the
operator to fill placeholders for the backend/Mongo container names and Docker network).
Here, **everything is auto-detected** from the live VPS by `steps/00_detect_env.sh` —
which eliminates the two operator-confirmation findings (A and B) from
`/audit/14_dry_run_verification.md`.

## Layout

```
arbicore-x-deploy/
├── lib/
│   └── common.sh                # shared helpers (logging, fail-fast, mongo shell pick)
├── steps/                       # numbered execution order; each step is idempotent
│   ├── 00_detect_env.sh         # auto-detect backend/mongo/network/env -> writes deploy.env
│   ├── 01_preflight.sh          # read-only sanity gate
│   ├── 02_backup.sh             # mandatory mongodump + baseline counts + OpenAPI snapshot
│   ├── 03_index_audit.sh        # read-only index conflict report
│   ├── 04_precutover_cleanup.sh # OPT-IN (--confirm) trim of expired discovery candidates
│   ├── 05_build.sh              # docker build of the new image (old keeps serving)
│   ├── 06_cutover.sh            # stop OLD, start NEW, health-gate (auto-rollback on fail)
│   ├── 09_canary_probe.sh       # read-only ~60s canary, auto-rollback on threshold breach
│   ├── 10_validate.sh           # post-cutover acceptance checks (read-only)
│   ├── 11_snapshot.sh           # point-in-time counts + scanner state
│   └── 99_rollback.sh           # restart OLD (functional rollback; Mongo never touched)
├── compose/
│   └── docker-compose.prod.yml  # backend service ONLY (no mongo service)
├── backend/
│   ├── Dockerfile               # production-pinned image
│   ├── .dockerignore
│   └── README.md                # how to stage the audited source
└── mongo/                       # mongosh/mongo JS executed via docker exec
    ├── 01_index_audit.js
    ├── 02_precutover_cleanup.js
    └── 04_validate.js
```

## Non-negotiable invariants

These are enforced by the scripts themselves — not by operator discipline:

- **Mongo is never created, dropped, restored, or otherwise touched.**
  This compose has no `mongo` service. No script calls `mongorestore --drop` or
  `db.dropDatabase()` or any `.drop()` / `deleteMany({})` on durable collections.
- **OLD backend container is stopped, never removed.** Rollback is just
  `docker start <old>` — instantaneous, no data motion.
- **The two currently-running scanners (`cex_arb`, `funding_arb`) are preserved**
  via env flags baked into `backend/.env` by step 00.
- **The only deletion path is opt-in:** `04_precutover_cleanup.sh --confirm`,
  scoped to expired rows in `arbicore_discovery_candidates` (a transient queue).

## Quick start

See `EXECUTION_ORDER.md` for the complete play-by-play. Short version:

```bash
cd arbicore-x-deploy
# 0. Stage the audited backend source into ./backend/ (see backend/README.md)
steps/00_detect_env.sh        # auto-detect VPS env
steps/01_preflight.sh         # read-only sanity
steps/02_backup.sh            # mandatory mongodump
steps/03_index_audit.sh       # read-only index check
# (optional) steps/04_precutover_cleanup.sh --confirm
steps/05_build.sh             # build new image (old still serving)
steps/06_cutover.sh           # the only downtime window (seconds)
steps/09_canary_probe.sh      # read-only ~60s canary; auto-rollback on threshold
steps/10_validate.sh          # acceptance checks
steps/11_snapshot.sh          # observability snapshot
# if anything is wrong:
steps/99_rollback.sh
```

A convenience `Makefile` is provided: `make preflight | backup | build | cutover | canary | validate | snapshot | rollback`.

## Provenance & related audit artifacts

This bundle is the executable counterpart of:

- `/audit/12_production_realignment_deployment_plan.md`
- `/audit/13_production_readiness_report.md`
- `/audit/14_dry_run_verification.md`

Findings A (backend container collision) and B (Mongo container/network reconciliation)
from doc 14 are resolved automatically by `steps/00_detect_env.sh`.
