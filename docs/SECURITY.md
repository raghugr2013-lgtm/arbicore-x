# ArbiCore X — SECURITY.md

## 1. Threat model (at-a-glance)

| Actor | Objective | Primary defence |
|---|---|---|
| Internet attacker | Steal secrets, hijack account, DoS | TLS + HSTS + strict CORS + login rate limit + JWT + non-root containers |
| Compromised container | Escalate host | Non-root uid 1001 in backend, read-only bind mounts, capability drop (compose default) |
| Ex-employee | Access historical data | JWT rotation, credential vault rotation, off-host encrypted backup, cert revocation |
| Cloud/VPS provider | Read data at rest | Encrypt-at-rest on the backup archive (age/gpg — §8) + encrypt disk (provider-level) |
| Supply-chain (pip/npm) | Backdoor the image | Version pinning + `requirements.prod.txt` grep-verified (no litellm/emergent) + optional trivy/scout scan |

## 2. Network posture

- Only ports 80 + 443 published to the internet (from `docker-compose.yml`).
- Everything else is on the private `arbicore-x-net` compose network:
  - `mongo:27017` — reachable ONLY from `backend` (never exposed on host)
  - `backend:8001` — reachable ONLY from `nginx`
  - `frontend:80`, `opportunity_center:80` — reachable ONLY from `nginx`
- Recommended host firewall (`ufw`):
  ```
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
  ```
- SSH: use key-based auth only, disable password auth, disable root login (change `PermitRootLogin no` in `/etc/ssh/sshd_config`).

## 3. TLS + HTTP security

See `docs/SSL.md`. Key knobs:

- **TLSv1.2 + TLSv1.3 only** (weaker versions disabled)
- **HSTS**: `max-age=31536000; includeSubDomains`
- **CSP**: baseline in `snippets/security_headers.conf` — tighten `connect-src` to production origins after the API surface stabilises
- **Rate limits**:
  - `/api/*`: 20 req/s + burst 40 per source IP
  - `/api/auth/login`: 5 req/min + burst 10 per source IP (brute-force defence)
- **OCSP stapling**: on

## 4. CORS

- Production `.env.production.example` sets `CORS_ORIGINS=https://${DOMAIN}` — no wildcards.
- Never ship `CORS_ORIGINS=*` in production. It's only permitted in `.env.development.example`.
- Verify:
  ```bash
  curl -sk -H "Origin: https://evil.example" https://${DOMAIN}/api/ -I | grep -i access-control-allow-origin
  # Expect NO header (blocked) or exactly the whitelisted origin — NOT https://evil.example.
  ```

## 5. Secret handling

- `.env` is mounted via `env_file` at compose run time. **Never** copied into images (`.dockerignore` enforces this).
- Bundle root `.env` MUST be `chmod 600`. `install.sh` will refuse to run if it isn't.
- Rotate `JWT_SECRET`, `VAULT_KEY` before production. Both must be ≥ 32 chars, cryptographically random:
  ```
  openssl rand -hex 32
  ```
- API keys (`HELIUS_API_KEY`, `LIFI_API_KEY`) — rotate at the provider dashboard whenever a person leaves the team.
- Backup archives are unencrypted by default — see §8.

## 6. Container hardening

- All app images run as **non-root**:
  - `backend`: uid 1001 (`arbicore` user)
  - `frontend`, `opportunity_center`: uid 101 (`nginx` user in nginx-alpine)
- `.dockerignore` excludes `.env`, `__pycache__`, `.git`, `node_modules`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`
- No shell in production images (nginx-alpine + slim-based backend)
- Docker's default capability drop applies (no `--privileged`, no `--cap-add`)
- Optional (highly recommended): image scan
  ```bash
  docker scout cves arbicore-x-backend:0.1.0
  # or
  trivy image arbicore-x-backend:0.1.0
  ```

## 7. Auth

- Session model: JWT in an HttpOnly + Secure + SameSite cookie (see `app/backend/services/auth.py`)
- Password hashing: bcrypt (already pinned in `requirements.prod.txt` at `bcrypt==4.1.3`)
- Admin bootstrap: `app/backend/reset_admin.py` — run once via `docker compose exec backend python reset_admin.py`

## 8. Backup encryption (recommended)

Archives contain full DB. Encrypt before storing off-host:

```bash
apt-get install -y age
# Generate a keypair, store the PRIVATE key OFF-HOST
age-keygen -o /root/backup.key    # then move this file off the VPS
grep public /root/backup.key > /etc/arbicore-x/backup-recipients.txt

# Encrypt each archive
for f in /opt/arbicore-x/backups/*.archive.gz; do
  age -R /etc/arbicore-x/backup-recipients.txt -o "${f}.age" < "$f" && rm "$f"
done
```

## 9. Audit log

The backend already writes `arbicore_audit_log` (TTL 90 d — see audit doc 13 §4). Additionally:

- nginx access + error logs: `docker compose logs nginx` (retained via `json-file` driver, capped at 500 MB per service)
- Host: syslog + auth.log for SSH sessions

Optional: ship logs off-host via `syslog-ng`, `vector`, or `promtail` → Loki / DataDog / Elastic.

## 10. Update cadence

| Component | Cadence | How |
|---|---|---|
| Application (backend, frontends) | On release | `docs/UPGRADE.md` (realignment path) |
| Base images (python:3.11-slim, node:20-alpine, nginx:1.25-alpine, mongo:4.4) | Quarterly | Rebuild + realignment upgrade |
| Certbot | Auto-renews certs; image itself pinned to `latest` | Trigger rebuild if a CVE is published |
| Host OS | Monthly | `apt-get update && apt-get upgrade` + reboot |
| Docker Engine | On security advisories | `apt-get install --only-upgrade docker-ce` |

## 11. Incident response

If you suspect a compromise:

1. **Do not** immediately delete. Preserve for forensics.
2. Snapshot: `./deployment/backups/backup.sh` (Mongo dump).
3. `docker compose pause backend frontend opportunity_center nginx` (freeze without terminating).
4. Rotate secrets: new `JWT_SECRET`, new `VAULT_KEY`, new API keys at providers.
5. Review logs: `docker compose logs --since 24h > /tmp/incident-$(date +%s).log`.
6. Restore from a KNOWN-CLEAN backup (see `docs/BACKUP_RESTORE.md §7`).
