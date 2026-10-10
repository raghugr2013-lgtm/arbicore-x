# R3 backup prerequisite correction

**UTC:** `2026-10-10T10:12:34Z` – `2026-10-10T10:16:35Z`  
**Verdict after correction + validation:** see `R3_APPLY_READINESS_VERDICT.md`

## Problem

§C.3 previously ran `mongodump` without authentication. Live `factory-mongo` has `security.authorization: enabled`. Probe result: `(Unauthorized) Command listCollections requires authentication`.

## Credential mechanism (approved)

Use credentials **already present** in the `factory-mongo` container environment:

- `MONGO_INITDB_ROOT_USERNAME` (= `root`)
- `MONGO_INITDB_ROOT_PASSWORD` (present; value never printed)

Expand them **inside** `docker exec factory-mongo sh -c '…'` so the password never appears on the host command line or shell history.

Do **not** pass `-p` / `--password` as a host-argv literal.

## Corrected backup command

See updated [`R3_DECISION_PACKAGE.md`](R3_DECISION_PACKAGE.md) §C.3 step 1.  
Original preserved at: [`R3_DECISION_PACKAGE.md.pre-backup-correction-20261010T101234Z`](R3_DECISION_PACKAGE.md.pre-backup-correction-20261010T101234Z)

## Validation performed (non-mutating)

| Check | Result |
|---|---|
| Authenticated `mongodump --db=arbicore_x --gzip` | **PASS** (~3.5 min) |
| Archive path | `/home/raghu/arbicore_backups/r3_backup_validation_20261010T101234Z/arbicore_x_20261010T101234Z.archive.gz` |
| Size | 462 853 739 bytes |
| Mode | `0600` |
| `gzip -t` | **PASS** |
| Collections finished in dump log | **56** `done dumping` lines incl. `arbicore_discovery_candidates` (3 921 188 docs) |
| `mongorestore --dryRun` (same in-container auth) | completed; **0 Unauthorized**; no DB writes |
| App state / users / URI | **unchanged** |

Evidence: `backup_validation_meta.json`, `backup_validation_mongodump.txt`, `backup_validation_mongorestore_dryrun.txt`

## Note on dryRun document count

`mongorestore --dryRun` reported `0 document(s) restored` (tool behaviour for dry-run). Coverage is attested from **mongodump completion lines**, not dry-run counts.
