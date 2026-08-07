# Hotfix — Frontend / Opportunity Center Network Attachment (`vqb-network`)

## Summary

Production returned **HTTP 502** through the public domain even though every
ArbiCore X container was healthy.

**Root cause (Docker per-network DNS):**
- The peer **Caddy** reverse proxy runs on `vqb-network`.
- `arbicore-x-backend` was attached to **both** `arbicore-x-net` and
  `vqb-network` (from the v2.11.9 backend hotfix), so Caddy could resolve it.
- `arbicore-x-frontend` was attached to **only** `arbicore-x-net`.
- Docker DNS is per-network, so Caddy (on `vqb-network`) could not resolve
  `arbicore-x-frontend` → it failed the upstream lookup and returned 502.

**Manual fix that restored production (temporary):**
```bash
docker network connect vqb-network arbicore-x-frontend
docker restart arbicore-x-frontend
docker restart caddy
```

**Permanent fix (this change):** dual-home the Caddy-fronted SPAs in the
canonical compose so a plain `docker compose up -d` never needs the manual
`docker network connect` again.

## Files changed

`deployment/compose/docker-compose.yml`
- `frontend.networks`: added `- vqb-network` (keeps `- arbicore-x-net`).
- `opportunity_center.networks`: added `- vqb-network` (keeps
  `- arbicore-x-net`) — the analytics SPA is also served through the peer
  Caddy, so it needs the same reachability and is fixed pre-emptively.
- Inline comments updated on both services + the top-level `networks:` block
  to document the dual-homing and why it is a NO-OP on greenfield hosts.
- `backend` was already dual-homed (v2.11.9) — unchanged.

`scripts/healthcheck.sh`
- Added a greenfield **Caddy attachment guard**: when `vqb-network` exists on
  the host, the script asserts that `arbicore-x-backend`,
  `arbicore-x-frontend`, and `arbicore-x-opportunity-center` are each attached
  to it, and FAILS loudly (with the exact recreate command) if not. Skipped on
  hosts without `vqb-network`.

`docs/TROUBLESHOOTING.md`
- New section **16** documenting the 502 symptom, diagnosis, and permanent fix.

No application code, business logic, trading mode, or data was touched.

## Why dual-homing is safe everywhere

- **Shared-tenancy VPS (production):** required — Caddy on `vqb-network` can now
  resolve the SPAs by container name.
- **Greenfield host (bundled nginx only):** the extra `vqb-network` attachment
  is unused; the bundled `nginx` still reaches the SPAs over `arbicore-x-net`.
  Attaching to an external network with no consumer is a harmless no-op.
- `vqb-network` is declared `external: true` — ArbiCore X never creates it. On a
  host without the peer stack, create a placeholder or drop the `- vqb-network`
  lines (see the compose top-level `networks:` comment).

## Redeploy (permanent fix, run on the VPS)

```bash
cd /opt/arbicore-x
git fetch --all && git checkout main && git pull --ff-only
git log -1 --oneline

# vqb-network must exist (peer stack owns it). Placeholder if missing:
docker network inspect vqb-network >/dev/null 2>&1 || \
  docker network create --driver bridge vqb-network

# Recreate the two newly dual-homed services (compose does not always detect
# network-list additions without --force-recreate).
docker compose -f deployment/compose/docker-compose.yml up -d \
  --force-recreate --no-deps frontend opportunity_center

# Let Caddy re-resolve upstreams.
docker restart caddy
```

## Verify

```bash
# 1. Both SPAs on BOTH networks:
for c in arbicore-x-frontend arbicore-x-opportunity-center; do
  echo -n "$c: "
  docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c"
done
#    Expected each line: arbicore-x-net vqb-network

# 2. Automated guard (fails if any Caddy-fronted service is single-homed):
scripts/healthcheck.sh

# 3. Public route no longer 502s:
curl -s -o /dev/null -w '%{http_code}\n' https://<your-domain>/            # 200
curl -s -o /dev/null -w '%{http_code}\n' https://<your-domain>/api/        # 200
```

## Rollback

Networking-only change; no data at risk.
```bash
git revert HEAD --no-edit
docker compose -f deployment/compose/docker-compose.yml up -d \
  --force-recreate --no-deps frontend opportunity_center
docker restart caddy
```
