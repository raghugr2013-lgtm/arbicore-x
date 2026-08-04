# ArbiCore X — Operations Guide (v2.9.0)

Every operator task is now one command via **`arbictl`**.

## Install

The toolkit lives at `/app/canonical_repo/ops/arbictl`. Add it to PATH:

```bash
ln -sf /app/canonical_repo/ops/arbictl /usr/local/bin/arbictl
```

Verify:

```bash
arbictl version
```

`arbictl` only depends on `httpx`. The bootstrap wrapper installs it
automatically on first use.

Global flags (env-overridable):

| Flag / env | Default | Purpose |
|---|---|---|
| `--base` / `ARBICTL_BASE_URL` | `http://localhost:8001` | backend URL |
| `--repo` / `ARBICTL_REPO` | `/app/canonical_repo` | git repo path |
| `--releases` / `ARBICTL_RELEASES` | `/app/releases` | release bundle dir |
| `--evidence` / `ARBICTL_EVIDENCE` | `/var/lib/arbicore/evidence` | daily snapshot root |
| `--backup` / `ARBICTL_BACKUP` | `/var/lib/arbicore/backups` | deploy backups |

## Deployment

```bash
# safe deploy (fetches tag, restarts services, waits for backend,
# runs preflight — fails clean if any step breaks)
arbictl deploy --tag v2.9.0 \
  --checksum /app/releases/v2.9.0/arbicore-x-v2.9.0.SHASUMS
```

The `--checksum` flag runs `sha256sum -c` against the shipped SHASUMS
file before touching the repo. Skip it during dev, keep it for
production.

## Upgrades and rollback

```bash
# upgrade (records LAST_KNOWN_GOOD before deploying the new tag)
arbictl upgrade --tag v2.10.0 --checksum ...

# instant rollback to whatever LAST_KNOWN_GOOD points at
arbictl rollback
```

Both commands run through the same `deploy` pipeline (checkout →
restart → wait → preflight). If preflight fails after a rollback the
platform still holds — the previous release is a checkout away.

## Preflight & dashboard

```bash
arbictl preflight     # 11-step readiness table
arbictl dashboard     # system at a glance (safety, providers, scanners,
                      # MID, daily writer, readiness score, anomalies)
```

Run `arbictl dashboard` at the start of every shift.

## Validation run

```bash
# one-command start (refuses if preflight fails, kill switch open, or
# live_execution_enabled=true)
arbictl validate-start --days 7

# daily during the run
arbictl snapshot      # writes /var/lib/arbicore/evidence/<TS>/*.json

# at the end
arbictl evidence-pack # bundles every snapshot to a single tar.gz
```

The snapshot exporter pulls 13 endpoints:
`validation/summary`, `validation/last_daily`, `providers/status`,
`scanners/cross/status`, `live/status`, `live/prices`, `memory/summary`,
`observability`, `safety/status`, `config/runtime`,
`postvalidation/readiness_score`, `postvalidation/recommendations`,
`postvalidation/executive_summary`.

## Monitoring

- CLI at-a-glance: `arbictl dashboard`
- UI at-a-glance:  open `$BASE/dashboard`
- One-line health check: `arbictl preflight | tail -1`

## Post-validation review

Everything is served by v2.8.0:

```bash
curl -s $BASE/api/arbicore/postvalidation/report            > report.json
curl -s $BASE/api/arbicore/postvalidation/recommendations   > recs.json
curl -s $BASE/api/arbicore/postvalidation/readiness_score   > score.json
curl -s $BASE/api/arbicore/postvalidation/executive_summary > exec.json
```

`arbictl snapshot` already includes the last three of these.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `arbictl preflight` fails on `kill switch engaged=False` | Someone disengaged the kill switch. Re-engage via `POST /safety/kill/engage` — `arbictl validate-start` refuses to run until it's back on. |
| `arbictl deploy` fails on checksum verify | You shipped the wrong file — pull the correct SHASUMS from `/app/releases/<tag>/`. |
| `snapshot` reports > 0 failed endpoints | Backend not fully up. Wait 15s and re-run. |
| `evidence-pack` says no evidence dir | `arbictl validate-start` was never run. Start the run first. |
| Rollback failed | `LAST_KNOWN_GOOD` file missing — checkout the previous tag manually (`git checkout v2.7.0 && sudo supervisorctl restart backend`). |

## Daily operator playbook (validation run)

Morning check:

```bash
arbictl dashboard
arbictl preflight
```

Evening archive:

```bash
arbictl snapshot
```

That's it. The daily-summary writer inside the running app (v2.7.0) is
the primary evidence source — the CLI snapshot is a backup that also
captures the runtime config + registry state at that moment.

## Post-run archive

```bash
arbictl evidence-pack --out /root/final_run/
# → /root/final_run/arbicore_evidence_<TS>.tar.gz
```

Send that file to review. Nothing else is needed for the go/no-go
decision on Stage 6.
