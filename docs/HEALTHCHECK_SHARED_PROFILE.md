# Shared-Profile Healthcheck — Backend Probe Design (audit 2026-06)

## Question
`scripts/healthcheck.sh` (shared profile) reported:
```
backend http://127.0.0.1:8101/api/ -> 000
```
even though the stack is healthy and `https://<domain>/api/` returns 200.
`docker port arbicore-x-backend` returns nothing → **no host port published.**

## Determination (from the compose files + frozen architecture)

- **Canonical shared compose** (`deployment/compose/docker-compose.shared.yml`)
  publishes the backend on **loopback only**:
  `"${BACKEND_HOST_BIND:-127.0.0.1}:${BACKEND_HOST_PORT:-8101}:8001"`.
- **This production VPS publishes no backend host port at all** — by design.
  Per `docs/DEPLOYMENT_ARCHITECTURE_FROZEN.md`, the backend is fronted by the
  **peer Caddy** reverse proxy, which reaches it **over the shared Docker
  network (`vqb-network`) by container name** — not via a published host port.
- Therefore the old probe (`http://127.0.0.1:8101/api/`) tested a port that
  does not exist on this host → deterministic `000`. That was a **healthcheck
  bug, not a deployment defect.**

## Decision: do NOT expose a host port

Exposing `8101` would change the deployment architecture and require a manual
VPS change — both explicitly out of scope. Instead the shared-profile probe
now uses signals that need no published port:

1. **Authoritative — in-container liveness (Docker-network direct):**
   `docker exec arbicore-x-backend curl -fs http://127.0.0.1:8001/api/`
   This is the exact liveness check the compose healthcheck runs. It passes
   whether or not any host port is published.
2. **End-to-end — through the peer Caddy proxy** (only when `DOMAIN` is set):
   `curl https://$DOMAIN/api/` → validates the real operator/browser path.
3. **Optional — loopback host-port probe:** run **only** when the backend
   actually publishes a port (`docker port ... 8001/tcp` non-empty). Skipped
   with an informational note when unpublished (the default here) — it can
   never again produce a false `000` failure.

All three probes are **read-only**. No trading mode, capital, kill-switch, or
governance state is touched — SHADOW posture is unaffected.

## Expected output on this VPS after the fix
```
OK    backend /api/ (in-container 127.0.0.1:8001) -> 200
OK    backend via Caddy https://arbicorex.coinnike.com/api/ -> 200   # if DOMAIN set
note  backend publishes no host port (by design on this VPS) — skipping loopback host-port probe
```
To enable probe #2, ensure `DOMAIN=arbicorex.coinnike.com` is present in the
env the script sources (`.env` / `.env.shared`). It is optional — probe #1 is
the authoritative pass/fail.

## Scope
Only `scripts/healthcheck.sh` (shared HTTP-probe block) changed. No compose,
no VPS, no application code, no governance change.
