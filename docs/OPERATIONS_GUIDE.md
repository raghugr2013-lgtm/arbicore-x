# ArbiCore X — Operations Guide (v2.9.1)

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

### httpx runtime dependency (v2.9.1 change)

`arbictl` depends on the `httpx` Python module.

**v2.9.0 and earlier** installed `httpx` at runtime via `pip install httpx`.
This breaks on Ubuntu 24.04 (PEP 668 "externally-managed-environment") and
is unsafe on production hosts.

**v2.9.1 onwards** never runs `pip install` at runtime. Instead, the bash
wrapper (`ops/arbictl`) discovers a Python interpreter that already has
`httpx` available. Discovery order:

1. `$ARBICTL_PYTHON` — operator override
2. `$ARBICTL_VENV/bin/python` — operator-created venv
3. `${REPO}/.venv/bin/python` — project-local venv
4. `${REPO}/venv/bin/python` — alternate venv name
5. `/app/venv/bin/python` — compose backend image venv
6. `python3` — system Python (must already have httpx)

Provision `httpx` OUT-OF-BAND once, using any of:

```bash
# a) system package (Debian/Ubuntu 24)
sudo apt-get install -y python3-httpx

# b) project venv (preferred on VPS hosts)
python3 -m venv /app/canonical_repo/.venv
/app/canonical_repo/.venv/bin/pip install httpx

# c) reuse the backend container venv (Docker compose profile)
export ARBICTL_PYTHON=/app/venv/bin/python
```

If none of the candidates has `httpx`, `arbictl` exits `3` with an
actionable message. It will never touch the system Python or require
`--break-system-packages`.

Global flags (env-overridable):

| Flag / env | Default | Purpose |
|---|---|---|
| `--base` / `ARBICTL_BASE_URL` | `http://localhost:8001` | backend URL |
| `--repo` / `ARBICTL_REPO` | `/app/canonical_repo` | git repo path |
| `--releases` / `ARBICTL_RELEASES` | `/app/releases` | release bundle dir |
| `--evidence` / `ARBICTL_EVIDENCE` | `/var/lib/arbicore/evidence` | daily snapshot root |
| `--backup` / `ARBICTL_BACKUP` | `/var/lib/arbicore/backups` | deploy backups |
| `ARBICTL_PYTHON` | `python3` | interpreter override (wrapper only) |
| `ARBICTL_VENV` | *(unset)* | path to an existing venv (wrapper only) |

## Deployment

```bash
# safe deploy (fetches tag, restarts services, waits for backend,
# runs preflight — fails clean if any step breaks)
arbictl deploy --tag v2.9.1 \
  --checksum /app/releases/v2.9.1/arbicore-x-v2.9.1.SHASUMS
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
| `arbictl` exits with `httpx is not available` | Provision `httpx` out-of-band — see the "httpx runtime dependency" section above. Never use `--break-system-packages`. |
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
