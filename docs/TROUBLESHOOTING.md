# ArbiCore X — TROUBLESHOOTING.md

Common failure modes, ordered by frequency.

## 1. `install.sh` fails at preflight

| Message | Cause | Fix |
|---|---|---|
| `.env not found` | Didn't `cp .env.production.example .env` | Do that; then edit. |
| `DOMAIN missing in .env` | Empty `DOMAIN` line | Set to your real FQDN (no scheme/no trailing slash). |
| `JWT_SECRET must be >= 32 chars` | Left blank or short | `openssl rand -hex 32` → paste. |
| `insufficient disk (need >=40 GB, have N GB)` | VPS too small | Resize the VPS or attach a data disk. |
| `port 80 already in use` | Something else is bound | `ss -ltn` shows the offender; stop/uninstall it. |

## 2. `install.sh` fails at "refuse-if-exists"

```
arbicore-x-mongo container exists — this is not a greenfield install.
```

You already have an ArbiCore X stack. Do NOT run `install.sh` — use the realignment path:

```bash
./scripts/upgrade.sh safe
```

If you genuinely want to wipe and reinstall (⚠ destroys data):

```bash
cd deployment/compose && docker compose down
docker volume rm arbicore-x-mongo-data arbicore-x-logs \
                 arbicore-x-certbot-etc arbicore-x-certbot-www
# NOW install.sh will pass the guard.
```

## 3. Backend "not healthy after 90s"

```
docker compose logs backend | tail -100
```

Look for:

- `KeyError: 'MONGO_URL'` → `.env` missing or not mounted; check `env_file` in compose.
- `pymongo.errors.ServerSelectionTimeoutError` → Mongo not reachable; check `depends_on: mongo` + Mongo healthcheck.
- `ModuleNotFoundError: No module named X` → wrong `requirements.txt`; `install.sh` may have failed to swap in `requirements.prod.txt`. Verify:
  ```bash
  head -5 app/backend/requirements.txt.orig    # should be intact
  head -10 deployment/docker/backend/requirements.prod.txt    # should start with the header comment
  ```
- `bcrypt` version mismatch → the frozen pin (`bcrypt==4.1.3`) may need to match `passlib` — never upgrade `bcrypt` alone.

## 4. Nginx fails: "cannot load certificate"

Cert files don't exist yet. This is EXPECTED on the very first boot before `init-letsencrypt.sh` runs. `install.sh` handles it. If you hit it outside the installer:

```bash
./deployment/ssl/init-letsencrypt.sh
docker compose restart nginx
```

If certs really are missing after issuance succeeded, check the certbot volume:

```bash
docker volume inspect arbicore-x-certbot-etc | grep Mountpoint
ls -la <mountpoint>/live/${DOMAIN}/
```

## 5. Certbot fails: "invalid response"

- Verify DNS: `dig +short ${DOMAIN}` must return the VPS IP.
- Verify the ACME path is reachable:
  ```bash
  echo "test" | docker exec -i arbicore-x-certbot tee /var/www/certbot/.well-known/acme-challenge/test >/dev/null
  curl -s http://${DOMAIN}/.well-known/acme-challenge/test
  # → should print "test"
  ```
- If the path is 404, nginx isn't serving the ACME location. Check `deployment/nginx/conf.d/arbicore-x.conf.template` has the `/.well-known/acme-challenge/` block on the :80 server.

## 6. Certbot rate limited

```
Error creating new order :: too many certificates already issued for exact set of domains
```

- Immediate mitigation: use staging mode until the issue is fixed. `LETSENCRYPT_MODE=staging` in `.env`.
- Long-term: don't loop on failed cert issuance. Fix the underlying issue (DNS, nginx routing) first, then attempt ONE prod issuance.

## 7. "MONGO Sizing" pain / can't boot mongo

`mongo:4.4` runs without AVX. If your VPS is genuinely modern and you want 6.0/7.0:

```bash
grep -o avx /proc/cpuinfo | head -1
# 'avx' → your CPU supports AVX; you can override:
sed -i 's|^MONGO_IMAGE=.*|MONGO_IMAGE=mongo:7.0|' /opt/arbicore-x/.env
docker compose down mongo && docker compose up -d mongo
```

If nothing printed, keep `mongo:4.4` — attempting `mongo:5.0+` will silently `Illegal instruction (core dumped)`.

## 8. Frontend loads but API calls fail

- Browser console shows `CORS blocked` → check `CORS_ORIGINS=https://${DOMAIN}` (no trailing slash, no wildcard mismatch).
- Browser console shows 404 on `/api/*` → check nginx routing: `curl -sk https://${DOMAIN}/api/ -I`.
- Browser shows a different `REACT_APP_BACKEND_URL` than expected → the frontend Dockerfile ARG was baked wrong. Rebuild:
  ```bash
  cd deployment/compose
  docker compose build --no-cache frontend
  docker compose up -d --force-recreate frontend
  ```

## 9. Login fails: "Invalid credentials" for the very first login

Admin isn't seeded yet. Run:

```bash
docker compose exec backend python reset_admin.py
```

Follow the prompts.

## 10. Backend crashes on boot with `bcrypt` errors

The `.env` file has a `$` in `JWT_SECRET` or `VAULT_KEY` (or another env var). Shell interpolation may have corrupted the value. Fix:

- Use only `[A-Za-z0-9_-]` characters in secrets (bcrypt values do NOT need special chars).
- Or single-quote the value in `.env`:
  ```
  JWT_SECRET='abc$xyz'
  ```

## 11. High CPU on `arbicore-x-mongo` after upgrade

Expected during the one-time TTL reap of stale `discovery_candidates` (see audit doc 13 §4). It settles within minutes.

If it doesn't settle, run the opt-in cleanup:

```bash
cd deployment/upgrade
make cleanup    # requires --confirm
```

## 12. Realignment: canary auto-rollback triggered

Read the canary log:

```bash
ls -1t /opt/arbicore-x/logs/canary_*.log | head -1 | xargs cat
```

The final lines show the exact endpoint that failed. If `/api/` was 502 → the NEW image failed to start (check `docker compose logs backend`). If `/api/arbicore/*` missing → wrong build was deployed (`arbicore/routes/` not included).

## 13. Realignment: `IndexOptionsConflict` on NEW backend boot

`03_index_audit.sh` should have caught this. If it slipped through:

```bash
docker exec -i arbicore-x-mongo mongo --quiet arbicore_x_prod
> db.<coll>.dropIndex("<conflicting_index_name>")
> exit
```

Then let the NEW backend rebuild the index on next boot.

## 14. Realignment: `.env` parity failure at step 00

```
ENV PARITY FAIL — OLD application vars not copied: X
```

Means an application env var name in the OLD container doesn't match any allow-list rule in `00_detect_env.sh`. Options:

- Add the name to the allow-list (edit `00_detect_env.sh` `APP_EXPLICIT_RE`, then re-run) — **only** if you can justify the naming.
- Or manually append `X=...` to `arbicore-x-deploy/backend/.env` after step 00, and re-run `01_preflight`.

## 15. "Container is unhealthy" but the app works

The healthcheck may be probing the wrong path. Verify:

```bash
docker inspect arbicore-x-backend -f '{{json .Config.Healthcheck}}' | jq
```

Should be `curl -fs http://localhost:8001/api/`. If your build changed the base API path, update the compose healthcheck accordingly.

---

## Diagnostic bundle for support

If you need to escalate, collect:

```bash
mkdir -p /tmp/arbicore-x-diag && cd /tmp/arbicore-x-diag
docker ps -a > docker_ps.txt
docker compose -f /opt/arbicore-x/deployment/compose/docker-compose.yml logs --tail=500 > compose_logs.txt
docker compose -f /opt/arbicore-x/deployment/compose/docker-compose.yml config > compose_config.txt
cp /opt/arbicore-x/.env env_redacted.txt
sed -i 's/\(SECRET\|KEY\|PASSWORD\|TOKEN\).*=.*/\1=REDACTED/' env_redacted.txt
tar -czf ../arbicore-x-diag.tar.gz .
```

Attach `arbicore-x-diag.tar.gz` to any support request. It contains no secrets (`.env` is redacted before packing).
