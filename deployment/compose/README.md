# `deployment/compose/` — Profile selection guide

## Which compose file should I use?

| Situation | Compose file | Invoke via |
|---|---|---|
| Fresh Ubuntu VPS, nothing else installed, ArbiCore X owns ports 80/443 | `docker-compose.yml` (greenfield, **default**) | `make install` (repo root) |
| Existing multi-tenant VPS with a peer reverse proxy (e.g., Caddy) that already terminates TLS | `docker-compose.shared.yml` (shared-infrastructure) | Manually — see [`../../docs/SHARED_INFRASTRUCTURE.md`](../../docs/SHARED_INFRASTRUCTURE.md) |
| Upgrading an existing ArbiCore X backend in place | *(not this directory — use `deployment/upgrade/`)* | `make upgrade` |

## Env templates

- **Greenfield** consumes the repo-root `.env` (copy from `.env.example` or `.env.production.example` or `.env.development.example`).
- **Shared-infrastructure** consumes an additional wiring template `deployment/compose/.env.shared.example`.

## Compatibility

| Requirement | Greenfield | Shared |
|---|:-:|:-:|
| Fresh VPS | ✅ | ❌ |
| Peer stack already on the VPS | ❌ | ✅ |
| Owns Docker network | ✅ | ❌ (attaches by name) |
| Owns MongoDB | ✅ | ❌ (connects via `MONGO_HOST`) |
| Owns reverse proxy | ✅ (nginx) | ❌ (peer Caddy) |
| Owns TLS (Certbot) | ✅ | ❌ (peer owns TLS) |
| Publishes public ports 80/443 | ✅ | ❌ (loopback only) |
| Multi-tenant on one VPS | ❌ | ✅ (prefix container names + host ports per tenant) |

## Files in this directory

- `docker-compose.yml` — greenfield default
- `docker-compose.shared.yml` — shared-infrastructure profile
- `.env.shared.example` — env wiring for the shared profile (host / port / URL / DB name / network alias / image tags / resource limits / optional Caddy labels)
- `README.md` — this file

Nothing else belongs here. New profiles get their own compose file + `README.md` section here + a new dedicated profile guide under `docs/`.
