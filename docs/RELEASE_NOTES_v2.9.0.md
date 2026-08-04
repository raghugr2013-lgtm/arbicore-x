# ArbiCore X v2.9.0 — Production Operations Toolkit

**Release date:** 2026-08-04
**Milestone:** Operator automation — no runtime changes.
**Mode:** OBSERVE / PAPER · Kill switch ENGAGED (unchanged)

## Summary

Ships **`arbictl`** — a single-file Python CLI that turns every
operator task into one command. Zero new runtime code. Zero
config-file mutations. Every subcommand is idempotent and read-only
against the running deployment (the two exceptions — `deploy` and
`upgrade` — restart supervisor as their side effect).

## What ships

Files added:
- `ops/arbictl.py`   — CLI (500 LOC, stdlib + `httpx`)
- `ops/arbictl`      — shell bootstrap (ensures `httpx` is installed)
- `docs/OPERATIONS_GUIDE.md` — operator handbook

Nothing in `arbicore/`, `backend/server.py`, or the frontend changes.
All runtime endpoints are the same as v2.8.0.

## Subcommands

| Command | Effect |
|---|---|
| `arbictl version` | Print repo version + live API status |
| `arbictl preflight` | 11-step readiness table (mongo · supervisorctl · api · `/preflight` · registry · scanners · safety · daily writer · runtime config) |
| `arbictl dashboard` | System-at-a-glance (safety · providers · scanners · MID · daily writer · readiness score · anomalies) |
| `arbictl validate-start --days 7` | Refuse-if-unsafe kick-off. Records `validation_run.json`. |
| `arbictl snapshot` | Pull 13 endpoints into `<evidence>/<TS>/*.json` + manifest |
| `arbictl evidence-pack` | Bundle every snapshot into one tarball |
| `arbictl deploy --tag <t> [--checksum ...]` | Safe deploy: verify SHASUMS → backup marker → `git checkout` → restart → wait → preflight |
| `arbictl upgrade --tag <t>` | Same as deploy but stashes `LAST_KNOWN_GOOD` for rollback |
| `arbictl rollback` | Instant restore of the previous validated release |

## Live smoke-test evidence (this build)

```
$ arbictl preflight
  [PASS]  mongo binary                  installed
  [PASS]  supervisorctl                 found
  [PASS]  backend api                   http://localhost:8001
  [PASS]  preflight endpoint            passed=10/10
  [PASS]  provider registry             providers=47
  [PASS]  live_market scanner           running=True
  [PASS]  cross scanners                cex_dex=True dex_dex=True
  [PASS]  kill switch engaged           True
  [PASS]  live execution disabled       live_exec=False
  [PASS]  daily summary writer          running=True
  [PASS]  runtime config                loaded
✔ preflight PASSED — 11/11

$ arbictl dashboard
safety      : kill=True  live_exec=False
providers   : 47/47 HEALTHY
scanners    :
  live_market           RUNNING  iter=36  emitted=72
  cex_dex               RUNNING  iter=22  emitted=0
  dex_dex               RUNNING  iter=22  emitted=0
opportunities in MID: 655
daily writer: running=True  run_id=run_20260804_1113
readiness   : B  score=0.804  verdict=READY WITH MINOR TUNING
anomalies   : none

$ arbictl snapshot
snapshot written to /tmp/arbi_ev/20260804T112158Z — 13 ok, 0 failed

$ arbictl evidence-pack
✔ evidence pack: /tmp/arbi_out/arbicore_evidence_20260804T112159Z.tar.gz
```

## Safety refusals

- `validate-start` refuses if `preflight` fails.
- `validate-start` refuses if `kill_switch.engaged=false`.
- `validate-start` refuses if `live_execution_enabled=true`.
- `deploy` runs preflight after restart; **non-zero exit if preflight fails**.
- `rollback` requires `LAST_KNOWN_GOOD` — errors clean if missing.

## Constraints held

- ✅ Reuses existing endpoints only
- ✅ No new market features
- ✅ No safety changes
- ✅ No runtime behaviour changes
- ✅ Backward compatible (still works with v2.5/v2.6/v2.7/v2.8 deployments)

## Deliverables

- `arbicore-x-v2.9.0.bundle`
- `arbicore-x-v2.9.0.tar.gz`
- `arbicore-x-v2.9.0.SHASUMS`
- `RELEASE_NOTES_v2.9.0.md`
- `OPERATIONS_GUIDE.md`
- Git tag `v2.9.0`

## Objective satisfied

> "A single operator should be able to deploy a release, verify
> readiness, start a validation run, monitor system health, collect
> daily evidence, generate the final evidence package, upgrade safely,
> and roll back safely — without needing custom manual procedures."

Every one of those verbs is now one `arbictl <verb>` call.
