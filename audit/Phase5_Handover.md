# Phase 5 — Handover: Publish and Deploy

**Repository state:** ✅ Certified. Ready for publication.
**Version:** `v1.0.0`
**HEAD:** `23cbfe8` on `main`
**Tag:** `v1.0.0` (annotated)
**Files:** 629 (629 tracked, 0 dangling git objects, `git fsck --full --strict` = clean)
**Intended destination:** `raghugr2013-lgtm/arbicore-x` (**private**)

---

## Publication packages (both prepared for you)

Two artifacts are ready under `/app/` — pick whichever you prefer:

| File | Size | SHA-256 | Notes |
|---|---|---|---|
| `/app/arbicore-x-v1.0.0.tar.gz` | 2.6 MB | `c6f5a3c61630ecd6978bcd73eac6f098631985f1ad72e94fe45192a503c8e625` | Full tree including `.git/` — extract, `cd`, add remote, push. **Recommended.** |
| `/app/arbicore-x-v1.0.0.bundle` | 1.4 MB | `d12d28a4a7733897995274bddd160cd5844f1929d4e28f5c6eac4c002cd91c39` | Native git bundle — smaller, git-only, no working tree. `git clone` it. |
| `/app/arbicore-x-v1.0.0.SHASUMS` | tiny | — | Combined checksum file for both artifacts. |

Verify integrity after downloading:
```bash
sha256sum -c arbicore-x-v1.0.0.SHASUMS
```

---

## Why "Save to GitHub" is not the mechanism here

The Emergent "Save to GitHub" feature saves the entire `/app/` workspace to your connected repositories. It cannot target a subdirectory like `/app/canonical_repo/`, and it cannot create a brand-new repository under a name you choose. Since the canonical repo lives at `/app/canonical_repo/` and needs to publish to a **new** private repository named `arbicore-x`, we use the download-and-push path instead — as confirmed by the platform.

The `/app/canonical_repo/` tree stays exactly as-is; the two artifacts above are just packaged forms of it for easy download.

---

## Publication procedure (~5 minutes total)

### Step 1 — Download the packages
Use the **Download Code** feature in the Emergent chat interface. Once downloaded, look in the archive for:
- `arbicore-x-v1.0.0.tar.gz` (recommended)
- `arbicore-x-v1.0.0.bundle` (alternative)
- `arbicore-x-v1.0.0.SHASUMS`

Optionally verify:
```bash
sha256sum -c arbicore-x-v1.0.0.SHASUMS
# expected: both files: OK
```

### Step 2 — Create the empty GitHub repository
1. Go to https://github.com/new
2. **Owner:** `raghugr2013-lgtm`
3. **Repository name:** `arbicore-x`
4. **Description:** *"Canonical repository for the ArbiCore X platform. Single source of truth for application, deployment, and operations."*
5. **Visibility:** **Private**
6. ⚠️ **Do NOT initialize** with README, `.gitignore`, or license — the repo already has a commit.
7. Click **Create repository**.

GitHub will show you a "quick setup" page. Ignore it and use the commands below.

### Step 3a — Push from the tar.gz archive (recommended)
On your workstation:
```bash
# Extract
tar -xzf arbicore-x-v1.0.0.tar.gz
cd canonical_repo/

# Sanity check
git log --oneline --decorate
# expected: 23cbfe8 (HEAD -> main, tag: v1.0.0) canonical: initial v1.0.0

git tag
# expected: v1.0.0

# Add the remote and push
git remote add origin https://github.com/raghugr2013-lgtm/arbicore-x.git
git push -u origin main
git push origin v1.0.0
```

Rename the directory afterward if you like: `mv canonical_repo arbicore-x`.

### Step 3b — Push from the git bundle (alternative)
```bash
git clone arbicore-x-v1.0.0.bundle arbicore-x
cd arbicore-x
git remote set-url origin https://github.com/raghugr2013-lgtm/arbicore-x.git
git push -u origin main
git push origin v1.0.0
```

### Step 4 — Verify on GitHub
- Repo URL should be reachable at `https://github.com/raghugr2013-lgtm/arbicore-x`
- `main` branch shows 1 commit: `23cbfe8 canonical: initial v1.0.0`
- Tag `v1.0.0` shows on the "Releases" side panel
- File count matches: **629 files**
- Repo size matches: **~6 MB**

### Step 5 — Cut a GitHub Release (optional but recommended)
On the GitHub repo page → **Releases** → **Draft a new release**:
- **Choose a tag:** select existing `v1.0.0`
- **Title:** `v1.0.0 — First canonical baseline`
- **Notes:**
  ```
  First canonical release of ArbiCore X.

  - Application fully absorbed from the legacy `ArbiCoreX-V01` repo (backend + frontend + opportunity_center + tests).
  - Deployment infrastructure absorbed from the legacy `arbicore-x-vps-bundle` repo (docker / compose / nginx / ssl / backups / monitoring / upgrade toolkit).
  - Frontend reproducibility (yarn.lock, .npmrc) canonical from day one.
  - Nested bundle layout flattened; RC lineage retired; historical session artefacts excluded.
  - Legacy `/api/arbicore/release/{manifest,bundle}` endpoints retired to structured stubs; API surface preserved.
  - Anti-fragmentation governance documented in CONTRIBUTING.md, docs/REPOSITORY_PHILOSOPHY.md, docs/ROADMAP.md.

  Certified by Phase 4 static validation (see docs/CANONICAL_CERTIFICATION.md).
  Runtime certification will be recorded after the first successful deploy on the target Contabo VPS.
  ```
- **Publish release**.

### Step 6 — Archive the legacy repos (optional)
On GitHub, for both legacy repos:
- `raghugr2013-lgtm/ArbiCoreX-V01` → Settings → **Archive this repository**
- `raghugr2013-lgtm/arbicore-x-vps-bundle` → Settings → **Archive this repository**

Archiving is reversible and clearly marks them as read-only historical references, which matches the migration model (`docs/MIGRATION_SUMMARY.md` §6 already points at them for historical context).

---

## Post-publication — Deployment Checklist for a Fresh Contabo VPS

This is the runtime-certification path we deferred from Phase 4. Execute on your target Contabo VPS (fresh Ubuntu 22.04 install). Every step has an expected outcome — if any step deviates, halt and inspect.

### 0. Prerequisites on the VPS
```bash
# Update
sudo apt-get update && sudo apt-get -y upgrade

# Docker Engine + compose v2 (skip if already installed)
curl -fsSL https://get.docker.com | sudo sh
sudo apt-get install -y docker-compose-plugin

# Verify
docker version
docker compose version         # expected: v2.x
df -h /                        # expected: >= 40 GB free
```

### 1. Clone the canonical repo
```bash
sudo mkdir -p /opt && cd /opt
sudo git clone https://github.com/raghugr2013-lgtm/arbicore-x.git
sudo chown -R $USER:$USER arbicore-x
cd arbicore-x

# Verify the tagged version
git describe --tags
# expected: v1.0.0
cat VERSION
# expected: 1.0.0
```

### 2. Configure `.env`
```bash
cp .env.production.example .env
$EDITOR .env
```

**Minimum required keys** (`scripts/install.sh` enforces these):
- `DOMAIN` — your FQDN (e.g., `arbicore.yourdomain.com`)
- `LETSENCRYPT_EMAIL` — your contact address
- `JWT_SECRET` — 32+ random chars: `openssl rand -hex 32`
- `VAULT_KEY` — 32+ random chars: `openssl rand -hex 32`
- `MONGO_URL` — `mongodb://mongo:27017`
- `DB_NAME` — `arbicore_x_prod`
- `CORS_ORIGINS` — your public URL (e.g., `https://arbicore.yourdomain.com`)
- `REACT_APP_BACKEND_URL` — same as above (used as a build-arg for the frontend)
- `LETSENCRYPT_MODE` — leave at `staging` for the first run

```bash
chmod 600 .env
make env-check
# expected: all required vars OK
```

### 3. Run the guarded installer
```bash
make install
```

Follow the 9-phase output. Expected sequence:
1. preflight → docker CLI + compose available, disk OK, ports 80/443 free, `.env` validated
2. refuse-if-exists guard → no prior stack found
3. mongo → healthy
4. backend → build + healthy (staging `requirements.prod.txt` swap is automatic)
5. frontend + opportunity_center → build + healthy
6. nginx → boots on :80 (HTTP-only mode for ACME challenge)
7. Let's Encrypt (staging) → cert issued
8. nginx reload → TLS active
9. healthcheck → all containers healthy + nginx `/nginx-health` returns 200

Expected total time: 5–10 minutes on first install (image pulls + node build dominate).

### 4. Verify in a browser
- `https://${DOMAIN}` → operator UI loads (browser will warn about the staging cert — expected)
- `https://${DOMAIN}/opportunity-center/` → analytics UI loads
- `https://${DOMAIN}/api/` → returns JSON `{"status":"ok",...}`

### 5. Flip Let's Encrypt to production
```bash
$EDITOR .env
# change LETSENCRYPT_MODE=staging → LETSENCRYPT_MODE=prod

./deployment/ssl/init-letsencrypt.sh
docker compose -f deployment/compose/docker-compose.yml restart nginx
```
Reload the site in your browser — the cert should now be trusted (green padlock).

### 6. Wire up cron
```bash
sudo bash -c 'cat /opt/arbicore-x/deployment/ssl/cronjob.example >> /etc/crontab'

sudo tee -a /etc/crontab <<'EOF'
0 3 * * * root /opt/arbicore-x/deployment/backups/backup-cron.sh >>/var/log/arbicore-x/backup.log 2>&1
EOF
sudo mkdir -p /var/log/arbicore-x && sudo chmod 755 /var/log/arbicore-x
```

### 7. Backup + restore round-trip test (validates R-6)
```bash
make backup
ls -la backups/               # expected: one arbicore-x_YYYYMMDD_HHMMSS.archive.gz

# Optional restore round-trip (drops + reloads the current DB — do this only on a fresh install)
make restore ARCHIVE=backups/arbicore-x_YYYYMMDD_HHMMSS.archive.gz
make healthcheck              # expected: all green
```

### 8. Enable scanners (opt-in, per family)
Every `ARBICORE_SCANNER_*_ARB=false` in `.env` disables one scanner family. Flip individual scanners to `true` as you validate them:
```bash
$EDITOR .env
# e.g., ARBICORE_SCANNER_D1_ARB=true

docker compose -f deployment/compose/docker-compose.yml restart backend
```

### 9. First-week runbook
- Watch `make logs SERVICE=backend` for any startup errors.
- Confirm at least one successful backup lands in `backups/`.
- Confirm `certbot` renewal loop is running: `docker logs arbicore-x-certbot 2>&1 | tail`.
- Confirm scanners you enabled are producing opportunities in the operator UI.
- Confirm `make healthcheck` passes daily.

### 10. Certify Runtime
Once R-1 through R-8 from `docs/CANONICAL_CERTIFICATION.md` §3 pass on your VPS:
- On GitHub, edit the `v1.0.0` release notes to append: *"Runtime certified on Contabo VPS ${DOMAIN} on YYYY-MM-DD."*
- The canonical repository is now the operational source of truth. All future changes originate here.

---

## What to do if something fails on the VPS

- **`make install` fails at phase 4 (backend build)** → check `docker compose -f deployment/compose/docker-compose.yml logs backend`. Most likely a Python package unavailable at the pinned version — file a PATCH-level fix in the canonical repo per `docs/ROADMAP.md` §2.
- **`make install` fails at phase 7 (cert issuance)** → `.well-known/acme-challenge` reachability. Verify DNS points at the VPS, and port 80 is open. See `docs/SSL.md`.
- **`make healthcheck` shows unhealthy containers after install** → `docker inspect --format='{{json .State.Health}}' <container>` shows the failing probe. See `docs/TROUBLESHOOTING.md`.
- **Anything unexpected** → capture `docker compose -f deployment/compose/docker-compose.yml logs > /tmp/compose.log` and open an issue on the canonical repo.

---

## Handover: what has been done

- ✅ Phase 1 exploration → `/app/audit/Deployment_Architecture_Understanding.md`
- ✅ Phase 2 design → `/app/audit/Canonical_Repository_Design.md`
- ✅ Phase 3 build → `/app/canonical_repo/` at HEAD `23cbfe8`, tag `v1.0.0`, 629 files, clean single-commit history
- ✅ Phase 4 static validation → 2 remediation cycles, 0 open findings, certification recorded in `docs/CANONICAL_CERTIFICATION.md` and `/app/audit/Static_Validation_Report.md`
- ✅ Phase 5 preparation → publication artifacts under `/app/`, download-and-push procedure above

## Handover: what remains for you

- ☐ Download the publication package (Step 1 above)
- ☐ Create the private GitHub repo `raghugr2013-lgtm/arbicore-x` (Step 2)
- ☐ Push (Step 3)
- ☐ Verify on GitHub (Step 4)
- ☐ Optional: cut GitHub release for `v1.0.0` (Step 5)
- ☐ Optional: archive the two legacy repositories (Step 6)
- ☐ Run the VPS deployment procedure (Steps 0–10 above) on your Contabo VPS
- ☐ Once R-1 through R-8 pass, append "Runtime certified" to the release notes

## Repository intent

From this point forward:
- **All future development happens in this repository.**
- **All future releases originate from this repository** (`git tag` + GitHub release; no side-loaded bundles).
- **All future deployments deploy from this repository** (`git clone` + `make install`).
- **The two legacy repositories are historical references only.**

Standing rules held to the end:
- Read-only on all source materials throughout Phases 1–4.
- No writes to any remote GitHub repository from this environment.
- No new repository created from this environment — you create the target repo yourself in Step 2.
- No bundle generation beyond the two local publication packages above.

Standing by for questions or a resume if any step above surfaces issues.
