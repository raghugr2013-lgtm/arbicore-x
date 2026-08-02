# ArbiCore X — INSTALL.md (Greenfield Fresh-VPS Install)

**Target:** fresh Ubuntu 22.04 / 24.04 LTS or Debian 12 VPS with a public IP and DNS.
**Outcome:** ArbiCore X reachable on `https://${DOMAIN}` with a valid Let's Encrypt certificate.
**Time budget:** < 30 minutes end to end.

---

## 0. Prerequisites (verify before starting)

- [ ] VPS: 2 vCPU / 4 GB RAM / ≥ 40 GB SSD (recommended: 4 vCPU / 8 GB RAM)
- [ ] OS: Ubuntu 22.04+ or Debian 12
- [ ] DNS: `${DOMAIN}` A/AAAA record points at the VPS public IP
- [ ] Firewall: ports 22, 80, 443 open (via `ufw` or provider console)
- [ ] Root or sudo access

## 1. Install Docker

```bash
# On the VPS (as root or via sudo)
apt-get update
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# Verify
docker --version && docker compose version
```

For Debian 12: replace `ubuntu` with `debian` in the two commands above.

## 2. Copy the bundle to the VPS

```bash
# On your workstation
scp -r arbicore-x-vps-bundle root@your-vps:/opt/arbicore-x
```

Or if you're pulling from GitHub on the VPS itself:

```bash
git clone https://github.com/raghugr2013-lgtm/ArbiCoreX-V01 /opt/arbicore-x-src
# ...then generate the bundle per DEPLOYMENT_MANIFEST.md, or copy this bundle from artifacts.
```

## 3. Configure secrets

```bash
cd /opt/arbicore-x
cp .env.production.example .env

# Generate two random 64-hex-char secrets
JWT=$(openssl rand -hex 32)
VAULT=$(openssl rand -hex 32)

# Edit .env — fill DOMAIN, LETSENCRYPT_EMAIL, and:
#   JWT_SECRET=<paste JWT>
#   VAULT_KEY=<paste VAULT>
#   HELIUS_API_KEY=<from helius.dev>
#   LIFI_API_KEY=<from li.fi>
$EDITOR .env

chmod 600 .env
```

Required fields checklist:

- [ ] `DOMAIN` (e.g. `arbicore.example.com`)
- [ ] `LETSENCRYPT_EMAIL` (a real inbox for expiry warnings)
- [ ] `LETSENCRYPT_MODE=staging` (first run — flip to `prod` in step 7)
- [ ] `JWT_SECRET` (≥ 32 chars, random)
- [ ] `VAULT_KEY` (≥ 32 chars, random)
- [ ] `HELIUS_API_KEY`
- [ ] `LIFI_API_KEY`
- [ ] Verify `CORS_ORIGINS=https://${DOMAIN}` (no wildcards in prod)

## 4. Verify DNS

```bash
dig +short "$(grep '^DOMAIN=' .env | cut -d= -f2)"
# Must return the VPS public IP.
```

If empty or wrong, fix DNS first — `certbot` will fail otherwise.

## 5. Run the installer

```bash
./scripts/install.sh
```

What it does (from `scripts/install.sh`):

1. Preflight: docker, disk ≥ 40 GB, ports 80+443 free, `.env` validated.
2. Refuse-if-exists: aborts if an old `arbicore-x-mongo` container OR volume exists.
3. Boot Mongo → wait healthy.
4. Build + boot backend → wait healthy (uses `requirements.prod.txt`, non-root uid 1001).
5. Build + boot frontend + opportunity_center → wait healthy.
6. Start nginx (HTTP only for ACME).
7. Issue Let's Encrypt cert (staging by default).
8. Reload nginx to activate TLS.
9. Run `healthcheck.sh`.

## 6. Verify

```bash
./scripts/healthcheck.sh
```

Manually:

```bash
curl -sk https://${DOMAIN}/api/                     # {"message":"..."} 200
curl -sk https://${DOMAIN}/                         # HTML for operator UI
curl -sk https://${DOMAIN}/opportunity-center/      # HTML for analytics UI
```

Open `https://${DOMAIN}` in a browser. You should see the ArbiCore terminal login page.

If the certificate warning says "Staging" or "Not secure" — that's expected on the first run. Proceed to step 7.

## 7. Flip from staging → production certs

Only after step 6 is green:

```bash
sed -i 's/^LETSENCRYPT_MODE=.*/LETSENCRYPT_MODE=prod/' .env

# Delete the staging cert and re-issue a real one
docker exec arbicore-x-certbot certbot delete --cert-name "$(grep '^DOMAIN=' .env | cut -d= -f2)" --non-interactive
./deployment/ssl/init-letsencrypt.sh
docker compose -f deployment/compose/docker-compose.yml restart nginx
```

Verify:

```bash
echo | openssl s_client -servername $(grep '^DOMAIN=' .env | cut -d= -f2) \
  -connect $(grep '^DOMAIN=' .env | cut -d= -f2):443 2>/dev/null | grep issuer=
# Expect: issuer=C=US, O=Let's Encrypt, CN=R3    (not "STAGING")
```

## 8. Configure recurring jobs

### 8a. Cert renewal

```bash
mkdir -p /var/log/arbicore-x
cat deployment/ssl/cronjob.example >> /etc/crontab
systemctl reload cron
```

### 8b. Nightly backup

```bash
cat >> /etc/crontab <<'CRON'
# ArbiCore X — nightly Mongo backup at 03:00 UTC
0 3 * * * root /opt/arbicore-x/deployment/backups/backup-cron.sh >>/var/log/arbicore-x/backup.log 2>&1
CRON
systemctl reload cron
```

Optional off-host push: set `BACKUP_RCLONE_REMOTE=<remote:bucket/path>` in `.env` and install rclone on the host.

## 9. Post-install checklist

- [ ] `./scripts/healthcheck.sh` → GREEN
- [ ] `https://${DOMAIN}` loads the operator UI over TLS (production, not staging)
- [ ] `docker ps` shows 5 containers healthy (mongo, backend, frontend, opportunity_center, nginx) + certbot running
- [ ] Cron jobs installed for cert renewal + nightly backup
- [ ] `.env` chmod 600 and not committed anywhere
- [ ] `docs/OPERATIONS.md` reviewed for daily runbook

Congratulations — the greenfield install is complete. See `docs/OPERATIONS.md` for daily operations.

---

## Troubleshooting

If step 5 fails, see `docs/TROUBLESHOOTING.md`. Common causes:

- `preflight FAIL: DOMAIN missing` → step 3 not completed
- `nginx -t failed` at step 6 → cert not yet issued; script will retry in step 7
- `backend not healthy after 90s` → check `docker compose logs backend`; usually a bad Mongo URL or missing API key
- `certbot: rate limited` → you exceeded Let's Encrypt production limits; wait or use staging mode
