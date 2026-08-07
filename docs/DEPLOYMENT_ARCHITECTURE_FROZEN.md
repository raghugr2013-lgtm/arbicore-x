# ArbiCore X — Deployment Architecture · FROZEN

**Effective**: 2026-08-05
**Status**: FROZEN — do not change without an explicit architectural review.

---

## Canonical facts (VPS-verified, 2026-08-05)

1. **`factory-mongo` is the canonical ArbiCore production database.**
   - Contains `arbicore_x` database with the canonical collections:
     `auth_users`, `arbicore_opportunities`, `arbicore_opportunity_journal`,
     `calibration_models`, `adaptive_weights`, `capital_policy_audit`,
     `kill_switch_audit`, `wallet_registry`, `entity_registry`,
     `execution_plans`, `evidence_bundles`, `execution_mode_audit`, `mid_events`.
   - Runs on the `vqb-network` Docker network alongside the Strategy Factory peer stack.

2. **`arbicore-x-mongo` is NOT the canonical store.**
   - It exists on `arbicore-x-net` but is not the primary database.
   - Do **not** treat it as an alternative in production. Any documentation
     recommending it as a default has been superseded.

3. **All four components — backend, frontend, Opportunity Center, Strategy Factory — are healthy and reach `factory-mongo`.**
   - The existing connectivity path works. It is codified in whatever runtime
     network attachments are in place on the VPS today.
   - The Docker network topology is a **documentation task** — not a blocker.

---

## Deployment profile of record

| Item | Value |
|---|---|
| Compose profile | `deployment/compose/docker-compose.shared.yml` |
| Env file | `deployment/compose/.env.shared` (chmod 600) |
| Canonical database | `factory-mongo` (host `factory-mongo`, port `27017`) |
| Docker network of Mongo | `vqb-network` |
| DB name | `arbicore_x` |
| `MONGO_URL` (in `.env.shared`) | `mongodb://<user>:<pass>@factory-mongo:27017/?authSource=admin` if auth is on, else `mongodb://factory-mongo:27017` |
| Backend network(s) | as-is (verified reachable — do not disturb) |
| Backend health signal | `docker logs arbicore-x-backend \| grep 'Application startup complete.'` + `curl -fsS http://127.0.0.1:${BACKEND_HOST_PORT:-8101}/api/` returns 200 |

> **Networking note (additive — no frozen rule changed).** The peer **Caddy**
> reverse proxy runs on `vqb-network` and resolves upstreams by container name.
> Any Caddy-fronted ArbiCore service must therefore be attached to
> `vqb-network`. In the shared profile that is automatic (all services share
> one network). If the **greenfield** `docker-compose.yml` is in use instead,
> `backend`, `frontend`, and `opportunity_center` are now all dual-homed on
> `arbicore-x-net` + `vqb-network` so Caddy never 502s — see
> `docs/HOTFIX_FRONTEND_VQB_NETWORK_ATTACH.md`. This is documentation of the
> existing runtime attachments; it does not alter the profile of record.

---

## What NOT to do

- **Do NOT run** `docker-compose.yml` (the greenfield profile) on this VPS. It would provision a fresh `arbicore-x-mongo` on `arbicore-x-net` that is NOT the canonical database.
- **Do NOT migrate** ArbiCore data out of `factory-mongo`. There is no operational reason to move it.
- **Do NOT `docker network disconnect`** the backend from any network it is currently attached to. The existing attachments are the reason the backend can reach `factory-mongo`.
- **Do NOT investigate the Docker networking further** unless it causes a production regression. If the backend suddenly loses connectivity, refer to the audit playbook at `docs/DEPLOY_v2.11.3_VPS_AUDIT_PLAYBOOK.md` before making changes.

---

## What to do on the next deploy

1. Pull the latest `main`.
2. Rebuild only if code changed: `docker compose --env-file .env.shared -f docker-compose.shared.yml build backend opportunity-center`.
3. Restart with `docker compose --env-file .env.shared -f docker-compose.shared.yml up -d`.
4. Verify:
   ```bash
   docker logs arbicore-x-backend --since 2m | grep -E 'BOOT:|Application startup complete'
   curl -fsS http://127.0.0.1:${BACKEND_HOST_PORT:-8101}/api/
   curl -fsS -c /tmp/c -X POST http://127.0.0.1:${BACKEND_HOST_PORT:-8101}/api/auth/login \
     -H 'Content-Type: application/json' -d '{"username":"<admin>","password":"<pw>"}'
   ```

If BOOT lines are missing or `Application startup complete.` is absent, apply the boot-instrumentation diagnosis flow from `docs/DEPLOY_v2.11.3_MONGO_DECISION.md`.

---

## Superseded documents

The following remain in the repo for historical reference. They describe the pre-freeze options and are **no longer prescriptive**:

- `docs/DEPLOY_v2.11_FIX.md` (v2.11.1 startup-resilience notes — still accurate)
- `docs/DEPLOY_v2.11.3_MONGO_DECISION.md` (Path A vs Path B decision matrix — **Path B is now the frozen choice**)
- `docs/DEPLOY_v2.11.3_VPS_AUDIT_PLAYBOOK.md` (audit commands — keep as diagnostic reference)

Read them if you're re-diagnosing an outage; do **not** treat their "Recommendation" sections as current architecture.

---

## Next engineering priorities (post-freeze)

Deployment is stable. The v2.11.x hotfixes (v2.11.1 non-blocking workers · v2.11.2 boot instrumentation · v2.11.3 compose fail-fast guards) remain in effect as defence-in-depth.

Sprint queue:

1. **Slice 5** — Dashboard Canonicalization
2. **Slice 6** — Portfolio Activation
3. **Slice 7** — Operations Activation
4. **Executor Contract** — deploy on `base`, verify on Basescan
5. **Paper Validation** — accumulate shadow cycles against `factory-mongo`
6. **Shadow Certification** — reach the 20-cycle threshold with `SAFE_TO_ADVANCE`
7. **Limited Live** — first Balancer-flash-loan campaign
8. **Autonomous Execution** — post Limited-Live sign-off
