# EXECUTION_ORDER — ArbiCore X Production Realignment

Each step is **idempotent** and stops the chain on the first failure. Nothing past
`02_backup.sh` runs without an explicit operator command, so you can pause/resume.

## Pre-flight (on operator workstation, not on VPS)

1. Copy this entire `arbicore-x-deploy/` directory to the VPS, e.g. under
   `/opt/arbicore-x/deploy/`.
2. Copy the **audited backend source** into `arbicore-x-deploy/backend/`
   (see `backend/README.md` for what must be present).
3. Ensure the operator account on the VPS has Docker access (`docker ps` works).

## On the VPS

| # | Command                                          | What it does                                                                                                | Destructive? |
|---|---------------------------------------------------|-------------------------------------------------------------------------------------------------------------|--------------|
| 0 | `steps/00_detect_env.sh`                          | Auto-detects backend + mongo containers, network, env from the LIVE stack. Writes `deploy.env`, `compose/.env`, `backend/.env` (chmod 600). | No |
| 1 | `steps/01_preflight.sh`                           | Confirms old backend running, Mongo reachable on the detected network, DB non-empty, no name collision, audited source staged. | No |
| 2 | `steps/02_backup.sh`                              | **Mandatory.** `mongodump --gzip` + baseline `arbicore_*` counts + OpenAPI snapshot. Aborts if archive is suspiciously small. | No |
| 3 | `steps/03_index_audit.sh`                         | Read-only index check; flags any unexpected index names that could cause `IndexOptionsConflict` on boot.    | No |
| 4 | `steps/04_precutover_cleanup.sh --confirm`        | **OPT-IN.** Trims expired rows in `arbicore_discovery_candidates` only (transient queue). Refuses to run without `--confirm`. | Bounded, queue-only |
| 5 | `steps/05_build.sh`                               | Builds the new image via compose. Old backend keeps serving traffic.                                       | No |
| 6 | `steps/06_cutover.sh`                             | **The only downtime window (seconds).** Stops OLD (preserves the container), `compose up -d` NEW, health-gates `/api/` + `/api/arbicore/*`. Auto-rolls back on failure. | Backend swap only; Mongo never touched |
| 9 | `steps/09_canary_probe.sh`                        | **Read-only** ~60s probe loop on the NEW backend. Threshold-driven (`MAX_CONSEC=3`, `MAX_PCT=20%`). On breach: invokes `99_rollback.sh` automatically. | No |
| 10| `steps/10_validate.sh`                            | Post-cutover acceptance: 6 scanner_config docs, 6 scanner_state docs, `cex_arb`+`funding_arb` enabled, TTL indexes present, durable counts vs pre-cutover delta. | No |
| 11| `steps/11_snapshot.sh`                            | Point-in-time observability snapshot. Repeat at any time.                                                  | No |
| ⌫ | `steps/99_rollback.sh`                            | `compose down` NEW, `docker start` OLD. Mongo never touched -> data intact.                                | No |

Gap at 07/08 is intentional reserved space for future intermediate steps (e.g.,
post-stable cleanup, image-promotion step).

## Decision points

- **After step 3 (`03_index_audit.sh`)**: if it flags any `REVIEW:` lines, inspect
  `${LOG_DIR}/index_audit_*.log` and decide whether to manually
  `db.<coll>.dropIndex("<name>")` before continuing. The new boot will rebuild the
  index correctly.
- **Before step 4 (`04_precutover_cleanup.sh`)**: this is the *only* deletion in the
  whole sequence and it is opt-in. The realignment itself does **not** require it; it
  only trims an expired backlog to reduce ongoing IO load. Skip it for a maximally
  conservative first realignment.
- **After step 6 (`06_cutover.sh`)**: the cutover script already health-gates `/api/`
  and `/api/arbicore/*` once. The canary in step 9 is the *short-window* sustained
  check — three layers of safety total (cutover gate + canary probe + validate).
- **After step 10 (`10_validate.sh`)**: if it prints `VALIDATION RED`, run
  `99_rollback.sh`, inspect `${LOG_DIR}/validate_*.log`, and reconvene before the next
  attempt.

## Canary tuning (step 9)

All env-overridable; safe defaults shown:

| Var                       | Default | Purpose                                                                  |
|---------------------------|---------|--------------------------------------------------------------------------|
| `CANARY_DURATION_SECS`    | 60      | Total probe window.                                                      |
| `CANARY_INTERVAL_SECS`    | 2       | Sleep between probes.                                                    |
| `CANARY_MAX_CONSEC_FAIL`  | 3       | Abort after N back-to-back failed iterations.                            |
| `CANARY_MAX_FAIL_PCT`     | 20      | Abort if failure rate across the window > this %.                        |
| `CANARY_AUTO_ROLLBACK`    | yes     | Set `no` to fail loud without auto-invoking rollback (manual recovery).  |
| `ARBICORE_TOKEN`          | unset   | Optional bearer to also exercise `/api/arbicore/health`.                 |

The canary probes ONLY GET endpoints: `/api/`, `/openapi.json`, and (token-gated)
`/api/arbicore/health`. No writes, no config changes, no scanner state changes.

## Expected outputs by directory

- `${BACKUP_DIR}` (default `/opt/arbicore-x/backups`):
  `preupgrade_<db>_<ts>.archive.gz`, `counts_pre_<ts>.tsv`, `openapi_pre_<ts>.json`
- `${LOG_DIR}` (default `/opt/arbicore-x/logs`):
  `index_audit_<ts>.log`, `precutover_cleanup_<ts>.log`, `old_backend_state_<ts>.json`,
  `canary_<ts>.log`, `validate_<ts>.log`, `counts_post_<ts>.tsv`, `snapshot_<ts>.txt`
- Bundle root:
  `deploy.env`, `compose/.env`, `backend/.env`, `.last_backup`

## Auto-rollback envelopes

There are now **two** auto-rollback paths, both ending at the same `99_rollback.sh`:

1. **Inside cutover** (`06_cutover.sh`): traps `ERR` between "stop OLD" and "NEW
   `/api/arbicore/*` visible". On failure: `compose down`, `docker start` OLD, exit
   non-zero. ~30–60s downtime envelope.
2. **In the canary** (`09_canary_probe.sh`): on threshold breach within the 60s
   window, invokes `99_rollback.sh` (unless `CANARY_AUTO_ROLLBACK=no`). The OLD
   container is still present and stopped — no data motion required.

Mongo is never touched in either path.

## After a successful realignment

- The OLD backend container is left in a `stopped` state on the VPS for one full retention
  window (operator-defined; ≥ 72h recommended). It can be removed manually with
  `docker rm <old>` only after you're satisfied with the NEW build.
- The pre-cutover archive in `${BACKUP_DIR}` is the disaster-recovery anchor. Move it
  off-host (or to your normal backup channel) once the realignment is confirmed stable.
