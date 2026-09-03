# `deployment/` — Deployment infrastructure

Everything needed to run ArbiCore X in production. Independent of the application: this tree consumes `app/`, it never modifies it.

## Layout

```
deployment/
├── docker/                Dockerfiles + build-time assets, indexed by service
│   ├── backend/           Dockerfile + Dockerfile.validation + .dockerignore + requirements.prod.txt + requirements.test.txt + requirements.dev.txt
│   ├── frontend/          Dockerfile + nginx-spa.conf (CRA -> nginx-alpine)
│   └── opportunity_center/  Dockerfile + nginx-spa.conf (Vite -> nginx-alpine)
│
├── compose/               Compose files, indexed by profile
│   ├── docker-compose.yml           DEFAULT — greenfield 6-service stack
│   ├── docker-compose.shared.yml    OPTIONAL — shared-infrastructure profile
│   ├── .env.shared.example          Env template for the shared-infra profile
│   └── README.md                    Profile selection guide
│
├── nginx/                 Reverse-proxy assets (shared across profiles)
│   ├── nginx.conf                   Main config (worker + http block)
│   ├── conf.d/arbicore-x.conf.template  Site config, envsubst-templated by ${DOMAIN}
│   └── snippets/                    HSTS + CSP + Mozilla Intermediate TLS + gzip
│
├── ssl/                   Let's Encrypt lifecycle
│   ├── init-letsencrypt.sh          First-run cert issuance (staging -> prod flip)
│   ├── renew.sh                     Renewal (also runs inside certbot container loop)
│   └── cronjob.example
│
├── backups/               Data safety
│   ├── backup.sh                    mongodump archive+gzip
│   ├── backup-cron.sh               Rotation + optional off-host rclone push
│   └── restore.sh                   mongorestore (interactive confirm)
│
├── monitoring/            Observability + probes
│   ├── healthcheck.sh               Internal (called by scripts/healthcheck.sh)
│   ├── uptime-probe.sh              External-style TLS + HTTP probe
│   ├── snapshot.sh                  Point-in-time Mongo census (JSON)
│   ├── shadow_start.sh              Data-collection window start
│   └── shadow_abort.sh              Window abort + final capture
│
└── upgrade/               In-place backend upgrade toolkit (SHA-locked audit heritage)
    ├── README.md, EXECUTION_ORDER.md, Makefile
    ├── backend/, compose/, lib/, mongo/, steps/
```

## Deployment profiles

**Greenfield (default).** Fresh Ubuntu VPS. Owns everything: mongo, backend, both frontends, nginx, certbot. `deployment/compose/docker-compose.yml`. Invoke via `make install` (repo root).

**Upgrade toolkit.** Backend-only in-place upgrade with canary + rollback. `deployment/upgrade/`. Invoke via `make upgrade` (safe, stops before cutover) or `make upgrade-full`.

**Shared-infrastructure (optional).** Multi-tenant deployment behind a peer reverse proxy (e.g., Caddy). No owned mongo/nginx/certbot. `deployment/compose/docker-compose.shared.yml` + `deployment/compose/.env.shared.example`. See [`../docs/SHARED_INFRASTRUCTURE.md`](../docs/SHARED_INFRASTRUCTURE.md).

## Adding a new profile

New profiles are additive and require an ADR added to `docs/ARCHITECTURE.md`. See `../CONTRIBUTING.md` §4.

## Invariants

- Every service in every compose has a healthcheck, resource limits, and log caps.
- Every image runs as a non-root user.
- No secrets in images — `.env` is mounted at runtime.
- No hard-coded domains — everything domain-scoped goes through `${DOMAIN}` and `envsubst`.
- Mongo data lives in the named volume `arbicore-x-mongo-data` — never a fresh host directory. `scripts/install.sh` refuses to install on top of an existing volume.
