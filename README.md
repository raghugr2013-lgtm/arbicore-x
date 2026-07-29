# ArbiCore X

The single canonical repository for the ArbiCore X platform — application, deployment infrastructure, operator tooling, and documentation in one place. A fresh clone contains everything required to develop, build, test, deploy, upgrade, operate, monitor, back up, and restore the system.

**Version:** `v1.0.0` · **License:** Proprietary — All Rights Reserved

---

## What this repo is

- **`app/`** — the application: FastAPI backend, React operator UI, and the Vite-based Opportunity Center analytics UI.
- **`deployment/`** — everything infrastructural: Dockerfiles, compose files, nginx reverse proxy, Let's Encrypt SSL, Mongo backups, monitoring probes, and the in-place upgrade toolkit.
- **`scripts/`** — the small handful of operator-facing entrypoints (`install.sh`, `upgrade.sh`, `healthcheck.sh`, `backup.sh`, `restore.sh`).
- **`docs/`** — operational documentation. Start with `docs/INSTALL.md` and `docs/OPERATIONS.md`.

The application never references deployment. Deployment consumes the application. Both live here but stay in strict logical separation. See [`docs/REPOSITORY_PHILOSOPHY.md`](docs/REPOSITORY_PHILOSOPHY.md).

---

## Quick start (Ubuntu 22.04 VPS)

```bash
# Prerequisites: Docker Engine >= 24.0 and docker compose v2 already installed.
git clone https://github.com/raghugr2013-lgtm/arbicore-x.git /opt/arbicore-x
cd /opt/arbicore-x

# 1. Configure secrets (fill in DOMAIN, LETSENCRYPT_EMAIL, JWT_SECRET, VAULT_KEY, ...)
cp .env.production.example .env
$EDITOR .env
chmod 600 .env

# 2. Install (guarded 9-phase greenfield installer)
make install

# 3. Verify
make healthcheck
```

Full step-by-step: [`docs/INSTALL.md`](docs/INSTALL.md).

---

## Day-2 operations

Everything an operator ever runs is a `make` target. See `make help` for the full list.

| Task | Command |
|---|---|
| Start / stop / restart | `make up`, `make down`, `make restart` |
| Tail logs | `make logs` or `make logs SERVICE=backend` |
| Status | `make status` |
| Aggregate healthcheck | `make healthcheck` |
| Snapshot backup | `make backup` |
| Restore | `make restore ARCHIVE=./backups/2026-…archive.gz` |
| Safe upgrade | `make upgrade` (stops for review before cutover) |
| Full upgrade | `make upgrade-full` |
| Rollback last upgrade | `make rollback` |
| Backend test suite | `make test-backend` |
| Env sanity check | `make env-check` |

Details: [`docs/OPERATIONS.md`](docs/OPERATIONS.md), [`docs/UPGRADE.md`](docs/UPGRADE.md), [`docs/ROLLBACK.md`](docs/ROLLBACK.md), [`docs/BACKUP_RESTORE.md`](docs/BACKUP_RESTORE.md), [`docs/SSL.md`](docs/SSL.md), [`docs/SECURITY.md`](docs/SECURITY.md), [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

---

## Deployment profiles

- **Greenfield** (default) — full 6-service stack on a fresh VPS (`mongo`, `backend`, `frontend`, `opportunity_center`, `nginx`, `certbot`). This is what `make install` does. Compose file: `deployment/compose/docker-compose.yml`.
- **Upgrade toolkit** — SHA-locked, audited in-place backend upgrade with canary + rollback. `deployment/upgrade/`. Invoked via `make upgrade` / `make upgrade-full` / `make rollback`.
- **Shared-infrastructure** (optional, multi-tenant peer) — attaches to an external network; no owned mongo/nginx/certbot. Compose file: `deployment/compose/docker-compose.shared.yml`. Guide: [`docs/SHARED_INFRASTRUCTURE.md`](docs/SHARED_INFRASTRUCTURE.md).

---

## Repository map

```
arbicore-x/
├── app/                        Application (backend + frontend + opportunity_center)
├── deployment/                 Infrastructure (docker/, compose/, nginx/, ssl/, backups/, monitoring/, upgrade/)
├── scripts/                    Operator entrypoints (install/upgrade/healthcheck/backup/restore)
├── docs/                       Operational documentation
├── Makefile                    Operator convenience wrapper
├── .env.example                Canonical environment template (fill and rename to .env)
├── .env.production.example     Prod-locked template
├── .env.development.example    Dev-permissive template
├── LICENSE                     Proprietary — All Rights Reserved
├── CONTRIBUTING.md             Contribution standards (folder / naming / docs / review)
├── VERSION                     1.0.0
└── README.md                   This file
```

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for folder organization, naming conventions, deployment-change rules, Docker-update rules, configuration management, review requirements, and the anti-fragmentation principles that keep this repo clean.

---

## Provenance

This repository was created as the canonical, self-contained successor to two legacy repositories which now serve only as historical references. See [`docs/MIGRATION_SUMMARY.md`](docs/MIGRATION_SUMMARY.md) for the full migration record and [`docs/EXCLUSIONS.md`](docs/EXCLUSIONS.md) for what was intentionally omitted and why.
