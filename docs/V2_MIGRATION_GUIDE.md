# ArbiCore X v2.0.0 — VPS Migration Guide

**Audience:** operators deploying `arbicore-x@v2.0.0` onto a Contabo VPS (or any Ubuntu 22.04 host).
**Prerequisites:** the VPS already runs a prior `arbicore-x` deploy (v1.0.x) *or* is a fresh Ubuntu 22.04 host.
**Deliverable:** a healthy v2.0.0 stack that keeps existing runtime data (Mongo, secrets, TLS certificates) and adds the UI v2 + Wave 6 + Phase 7–10 features.

**Rule of thumb:** _no application code is copied from the existing VPS._ Only runtime configuration migrates. The canonical repository IS the application.

---

## 1. What migrates from the VPS, what does not

| Artifact | Migrate? | Source location on VPS |
|---|---|---|
| **`.env`** — the operator-created environment file | ✅ **YES** | `/opt/arbicore-x/.env` |
| **VAULT_KEY / JWT_SECRET / MONGO auth keys** (from `.env`) | ✅ YES (they're in `.env`) | same |
| **TLS certificates** (`certbot/live/${DOMAIN}/`, `certbot/archive/${DOMAIN}/`, `renewal/`) | ✅ YES | Docker volume `arbicore-x-certbot-etc` |
| **MongoDB data** (opportunities, evidence bundles, wallets, plans, etc.) | ✅ YES (optional — you can start fresh) | Docker volume `arbicore-x-mongo-data` |
| **Wallet secret material** (secret registry entries) | ✅ YES | Mongo collection `arbicore_secrets` (contained in mongo volume) |
| **Wallet registry** (registered burner, gas, execution wallets) | ✅ YES | Mongo collection `arbicore_wallet_registry` |
| **Network config** (RPC URLs, chain IDs) | ✅ YES | Mongo collection `arbicore_network_config` |
| Application code (`app/backend`, `app/frontend`, `app/opportunity_center`) | ❌ NO — comes from this repo | — |
| Deployment infrastructure (`deployment/`, `scripts/`) | ❌ NO — comes from this repo | — |
| Docker images | ❌ NO — will be rebuilt from `Dockerfile`s in this repo | — |
| Prior test reports (`test_reports/`, `test_result.md`) | ❌ NO | Local to prior sessions |

---

## 2. Migration flow (upgrade path from v1.0.x on same VPS)

### 2.1 Preflight snapshot (5 minutes)

```bash
# On the VPS, in the current arbicore-x directory
cd /opt/arbicore-x

# Take an authoritative backup — mongodump + config bundle
make backup                # writes backups/arbicore-x_YYYYMMDD_HHMMSS.archive.gz

# Snapshot the .env
cp .env .env.pre-v2.backup

# Snapshot mongo volume metadata (does NOT copy the data itself — volume stays put)
docker volume inspect arbicore-x-mongo-data > /root/mongo-volume.info.json

# Snapshot certbot volumes (they'll be re-attached after upgrade)
docker volume inspect arbicore-x-certbot-etc > /root/certbot-etc.info.json
docker volume inspect arbicore-x-certbot-www > /root/certbot-www.info.json
```

### 2.2 Bring the stack down

```bash
# Stop and remove containers, PRESERVE volumes (default docker compose down behavior)
docker compose -f deployment/compose/docker-compose.yml down

# Verify: containers gone, volumes preserved
docker volume ls | grep arbicore-x   # expected: mongo-data, certbot-etc, certbot-www, logs
docker ps -a | grep arbicore-x       # expected: no rows
```

### 2.3 Swap in the canonical v2.0.0 tree

```bash
# Move the old tree aside (keep for rollback)
sudo mv /opt/arbicore-x /opt/arbicore-x-v1.0.2

# Clone the canonical v2.0.0 tree
cd /opt
sudo git clone https://github.com/raghugr2013-lgtm/arbicore-x.git   # or your fork/private URL
cd arbicore-x
sudo git checkout v2.0.0
sudo chown -R $USER:$USER .

# Sanity check
cat VERSION       # expected: 2.0.0
git describe --tags   # expected: v2.0.0
```

### 2.4 Migrate runtime configuration

**`.env`** — copy the old file, then reconcile with the v2.0.0 template:

```bash
cp /opt/arbicore-x-v1.0.2/.env .env
chmod 600 .env
diff .env .env.production.example | head -40
# Any new required vars in v2.0.0 template will appear here — add them to .env
```

**Two additive vars in v2.0.0** (both **optional**; only relevant for flash-loan operators):

- `ARBICORE_RPC_URL` — the operator's private RPC URL (Alchemy/QuickNode/Ankr). Leave unset to keep SHADOW mode.
- `ARBICORE_EXECUTOR_ADDRESS_BASE` — address of the deployed `FlashLoanReceiver` contract on Base. Leave unset until the operator has deployed one.

If either was already set by an operator during Phase 10 walkthroughs, the Phase 10.10 env-sync shim ensures they are already persisted in the Mongo `arbicore_network_config` collection, and the merged server will resurface them at startup.

### 2.5 Bring up v2.0.0 against the existing volumes

The named volumes already exist. `docker compose up` will re-attach them:

```bash
make install    # 9-phase installer — v2.0.0 detects existing mongo volume and skips seed
```

Expected behavior:

- Phase 1 (preflight): ✅ passes
- Phase 2 (refuse-if-exists guard): ⚠ TRIGGERS because `arbicore-x-mongo` container was removed but the volume `arbicore-x-mongo-data` still exists. **This is the correct behavior for a migration.** Bypass with `SKIP_VOLUME_GUARD=1 make install`.
- Phase 3 (mongo): ✅ starts against the preserved volume; all collections intact
- Phase 4–5 (backend, frontend, opportunity_center): ✅ image rebuild pulls source from v2.0.0 tree
- Phase 6 (nginx): ✅ starts; certbot volumes are already attached
- Phase 7 (Let's Encrypt): ⏭ **SKIPPED** — existing certificates in `arbicore-x-certbot-etc` are honored; only renewal loop runs
- Phase 8–9 (health): ✅ all green

### 2.6 Verify

```bash
# Aggregate health
make healthcheck

# Frontend v2 loads
curl -Is https://${DOMAIN}/ | head -3
# Look for HTTP/2 200 and cache-control on the SPA

# UI v2 assets bundled (regression guard — v1.0.2 fingerprint MUST be absent)
docker exec arbicore-x-frontend sh -c "find /usr/share/nginx/html -name '*.js' | head -1 | xargs cat | grep -c 'void 0.*api'"
# expected: 0 (regression fixed in v1.0.2 stays fixed in v2.0.0)

# Backend responds
curl -s https://${DOMAIN}/api/ | jq .

# Flash-loan operator page loads
curl -Is https://${DOMAIN}/v2/flash-loan | head -3

# Journey page loads
curl -Is https://${DOMAIN}/v2/journey | head -3

# Legacy UI fallback (feature flag OFF)
curl -Is https://${DOMAIN}/  | head -3   # still shows legacy CRA until ?ui_v2=1
```

### 2.7 Flip UI v2 to production

```bash
# In .env
UI_V2_ENABLED=true            # backend flag — surfaces feature in /api/system/status
REACT_APP_ENABLE_UI_V2=true   # frontend build-time flag — v2 is default at /
```

Rebuild the frontend image only:

```bash
docker compose -f deployment/compose/docker-compose.yml up -d --no-deps --build frontend
```

### 2.8 Rollback (5 minutes if anything breaks)

```bash
# Stop v2.0.0
docker compose -f deployment/compose/docker-compose.yml down

# Restore v1.0.2 tree
sudo mv /opt/arbicore-x /opt/arbicore-x-v2.0.0.failed
sudo mv /opt/arbicore-x-v1.0.2 /opt/arbicore-x
cd /opt/arbicore-x

# Re-attach volumes and bring back up
docker compose -f deployment/compose/docker-compose.yml up -d
make healthcheck
```

Volumes were never dropped, so no data loss. TLS certs are still valid.

---

## 3. Fresh VPS install (no prior arbicore-x)

If this is a brand-new Ubuntu 22.04 VPS with no prior deploy, the flow simplifies dramatically. Follow `docs/INSTALL.md` — the standard 9-phase installer will:

1. Create fresh named volumes
2. Bootstrap Mongo with empty collections
3. Build all four images from source in this repo
4. Issue fresh TLS certificates
5. Bring up 6 services

Bootstrap `.env` needs **only these five variables** (all others default sensibly or can be configured via the UI after boot):

```
DOMAIN=arbicore.yourdomain.com
LETSENCRYPT_EMAIL=you@yourdomain.com
MONGO_URL=mongodb://mongo:27017
DB_NAME=arbicore_x_prod
CORS_ORIGINS=https://arbicore.yourdomain.com
VAULT_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
REACT_APP_BACKEND_URL=https://arbicore.yourdomain.com
```

After the first successful boot, the operator uses the UI to configure network, wallets, secrets, and per-strategy execution modes. Nothing else touches `.env`.

---

## 4. What's new in v2.0.0 (operator-visible)

- **UI v2** — new left-rail navigation, Home / Discovery / Opportunities / Portfolio / Intelligence / Operations / Settings sections, obsidian + amber design language
- **Flash Loan Operator page** (`/v2/flash-loan`) — one-page cockpit for LIMITED_LIVE flash-loan validation
- **Flash Loan Journey** (`/v2/journey`) — stage tracker for the operator walkthrough
- **Execution certification pipeline** — 6-gate ladder (kill switch → mode → capital → secret → preflight → operator confirm)
- **Persistent network config → env shim** (Phase 10.10) — RPC URLs, executor addresses, chain IDs configurable from UI and survive restarts
- **Revert decoder** — preflight reverts surface both raw hex and human-readable cause (UniV3 V3TooLittleReceived, Balancer NotAuthorized, etc.)
- **Opportunity Journal** — every opportunity's lifecycle is appended to an immutable ledger
- **Learning Ledger** — bridges Journal → CalibrationWorker → AdaptiveWeights (dormant until operator opts in)
- **Continuous Discovery** — 60-second cadence scan against a configurable universe (defaults to Base WETH/USDC)
- **Preflight revert `debug_traceCall` fallback** — when public RPC omits `error.data`, the merged server replays the call under `debug_traceCall` to recover the selector

## 5. What's dormant in v2.0.0 (activate later)

Dormant modules ship in-tree but are not wired into `server.py`. Each activation is a self-contained follow-up wave:

- `arbicore/scanner/`, `arbicore/scanners/` — the legacy D-1…D-6 scanner tree
- `arbicore/intel/`, `arbicore/intelligence/` — regime classifier, cross-chain intel
- `arbicore/shadow/`, `arbicore/runtime/` — Wave-1 shadow observation runtime
- `backend/routes/{auth,execution,observation,portal,portfolio,vault,venues,alerts}.py`
- `backend/services/*` (13 services)
- `backend/connectors/*` (13 exchange connectors + evm_wallet)
- `backend/core/`, `backend/engines/`, `backend/diagnostics/`

45 test files corresponding to these modules live under `backend/tests/_pending_scanner_activation/` (excluded from the default regression). When a wave activates a module cluster, its tests move back to `backend/tests/`.

---

## 6. Regression suite (verified before this release)

```
$ pytest tests/ -n 2 --dist loadscope

1442 passed, 76 skipped, 0 failed in 13.60s
```

Categories:
- 599 UI-v2-slice tests (Wave 6A–E + Phase 7–10) — 100 % green
- 843 canonical tests (v1.0.2 slice that survives the merged server) — 100 % green
- 76 skipped tests — feature-flag-gated or intentionally skipped

---

## 7. Support

- File issues against the canonical repository (`raghugr2013-lgtm/arbicore-x`)
- Consult `docs/TROUBLESHOOTING.md` for common upgrade-time failures
- The two legacy source repositories (`arbicore-x` v1.0.2 and `Arbicorex-ui-v2-slice-02`) are frozen and read-only from v2.0.0 onward

_End of migration guide._
