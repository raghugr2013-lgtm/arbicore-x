# ArbiCore X — VPS Deployment Package

Static deployment artifacts. **No application/feature/architecture changes.**
Initial mode is **SHADOW**; **LIMITED_LIVE and FULL_AUTOMATION stay operator-gated**
and are never auto-activated. Never place a private key, vault secret, RPC API
key, or credential in source, logs, or generated files.

Files in this package:
- `.env.backend.example`, `.env.frontend.example` — keys only, no values
- `systemd/arbicore-backend.service`, `systemd/arbicore-frontend.service`
- `supervisor/arbicore.conf` (alternative to systemd)
- `nginx/arbicore.conf` (reverse proxy + TLS)

---

## 1. System prerequisites
```
# Base packages
sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv \
    build-essential curl git nginx
# Node (for the frontend build + serve) — use nodejs 20 LTS
# MongoDB 6/7 (local or managed URI)
sudo useradd -r -m -s /bin/bash arbicore   # dedicated service user
sudo mkdir -p /var/log/arbicore && sudo chown arbicore:arbicore /var/log/arbicore
```

## 2. Backend install
```
cd /app/app/backend
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
# Emergent integrations (if used):
./venv/bin/pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
cp /app/deploy/.env.backend.example ./.env    # then FILL values (see section 7)
```

## 3. Frontend build
```
cd /app/app/frontend
cp /app/deploy/.env.frontend.example ./.env   # set REACT_APP_BACKEND_URL to the https origin
yarn install
yarn build                                    # produces ./build (served on :3000)
```

## 4. Foundry / Anvil (REQUIRED for FORK_VALIDATION)
```
# Install as the arbicore user so anvil is on the service PATH.
sudo -u arbicore bash -lc 'curl -L https://foundry.paradigm.xyz | bash'
sudo -u arbicore bash -lc 'source ~/.bashrc && ~/.foundry/bin/foundryup'
sudo -u arbicore bash -lc '~/.foundry/bin/anvil --version'   # verify
# The systemd unit sets PATH to include /home/arbicore/.foundry/bin.
# NOTE: a manual /usr/local/bin symlink is NOT persistent — rely on PATH instead.
```

## 5. Start services
### Option A — systemd
```
sudo cp /app/deploy/systemd/arbicore-backend.service /etc/systemd/system/
sudo cp /app/deploy/systemd/arbicore-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arbicore-backend arbicore-frontend
```
### Option B — supervisor
```
sudo cp /app/deploy/supervisor/arbicore.conf /etc/supervisor/conf.d/
sudo supervisorctl reread && sudo supervisorctl update
```
### Manual (dev/foreground) startup commands
```
# Backend:  cd /app/app/backend && ./venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 --workers 2
# Frontend: cd /app/app/frontend && npx serve -s build -l 3000
```

## 6. Reverse proxy + TLS
```
sudo cp /app/deploy/nginx/arbicore.conf /etc/nginx/sites-available/arbicore
sudo ln -sf /etc/nginx/sites-available/arbicore /etc/nginx/sites-enabled/arbicore
sudo certbot --nginx -d your-domain.tld     # issues + wires TLS
sudo nginx -t && sudo systemctl reload nginx
```

## 7. Secrets & configuration to enter MANUALLY on the VPS
Set these in `/app/app/backend/.env` (values NEVER in git/chat/logs):

| Key | Type | Notes |
|-----|------|-------|
| `MONGO_URL`, `DB_NAME` | config | Mongo connection; keep `DB_NAME` key name |
| `VAULT_KEY` | **secret** | NEW Fernet key: `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `JWT_SECRET` / `ARBICORE_JWT_SECRET` | **secret** | random 32+ bytes |
| `ARBICORE_ADMIN_USER`, `ARBICORE_ADMIN_PASS` | **secret** | operator login |
| `ARBICORE_RPC_URL` | **secret** | dedicated low-latency Base RPC (Alchemy/QuickNode) |
| `ARBICORE_ARCHIVE_RPC_URL` | **secret** | archive-capable Base RPC (fork replay) |
| `ARBICORE_ETHERSCAN_API_KEY` | **secret** (optional) | Etherscan V2, Base chainid 8453 |
| `ARBICORE_GAS_WALLET_ADDRESS` | public | gas/execution wallet ADDRESS only |
| `ARBICORE_EXECUTOR_ADDRESS_BASE` | public | deployed executor ADDRESS only |
| `ARBICORE_SHADOW_CERT_ENABLED=true`, `..._CYCLE_S=60` | config | shadow cert |
| `ARBICORE_SCANNER_AUTOSTART=true` | config | SHADOW discovery only |
| `ARBICORE_AUTOEXEC_AUTOSTART=false`, `ARBICORE_RUNTIME_AUTOSTART=false` | **safety** | MUST be false at deploy |
| `CORS_ORIGINS` | config | your https origin |

Frontend `/app/app/frontend/.env`: `REACT_APP_BACKEND_URL` = external https origin.

**Execution signer** — do NOT put the private key in env. After boot, ingest it once
into the encrypted vault (operator-auth), never echoed:
```
POST /api/arbicore/engine/settings/signer   body: {"private_key":"<64-hex>","label":"exec-signer"}
```

## 8. Production health-check commands
```
API=https://your-domain.tld
# Backend up
curl -s -o /dev/null -w "%{http_code}\n" $API/api/            # expect 200/redirect
# Auth required (anon must be 401)
curl -s -o /dev/null -w "%{http_code}\n" $API/api/arbicore/engine/readiness-matrix   # expect 401
# Login (operator) then check gates:
curl -s -c cj.txt -X POST $API/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"<ADMIN_USER>","password":"<ADMIN_PASS>"}' -o /dev/null
curl -s -b cj.txt $API/api/arbicore/engine/readiness-matrix | \
  python3 -c "import sys,json;d=json.load(sys.stdin);m=d['modes'];print('mode',d['current_mode'],'| LL',m['LIMITED_LIVE']['can_activate'],'| FA',m['FULL_AUTOMATION']['can_activate'],'| overall',d['overall_status'])"
# Foundry present
sudo -u arbicore ~/.foundry/bin/anvil --version
```

## 9. Post-deployment smoke-test checklist (Phase B — run ON the VPS)
- [ ] Backend + frontend reachable via https; nginx `/api` → :8001, `/` → :3000
- [ ] Anonymous requests to `/api/arbicore/*` return **401**
- [ ] Operator login succeeds; readiness matrix returns `current_mode=SHADOW`,
      `LIMITED_LIVE.can_activate=false`, `FULL_AUTOMATION.can_activate=false`
- [ ] `GET /api/arbicore/engine/executor-abi` → entrypoint `execute(address[],uint256[],bytes)`,
      owner == gas wallet, router = UniV3 SwapRouter02, vault = Balancer V2
- [ ] Signer ingested into vault → `GET /api/arbicore/engine/settings/signer`
      shows `present=true`, `matches_expected=true`, **no key in response**
- [ ] `POST /api/arbicore/engine/run-fork-validation` (with archive RPC) → `ran=true, passed=true`
- [ ] Scanner running in SHADOW; `POST /api/arbicore/engine/scan-once` returns opportunities with
      `execution_capability` (EXECUTABLE_UNIV3 vs NON_EXECUTABLE_BY_CURRENT_EXECUTOR); `would_execute`
      only true if a route genuinely passes the full pipeline + atomic sim
- [ ] No secret (private key / RPC key / vault key) appears in logs or any API response
- [ ] RPC latency / rate-limit / quote-coverage check on the production RPC
- [ ] 24–48h continuous SHADOW soak (persistence, uptime, auto-restart)

## 10. Go-live (manual, operator only)
Do NOT activate any live mode from tooling. LIMITED_LIVE remains locked until a
genuinely profitable EXECUTABLE_UNIV3 route passes the full pipeline **and** a
passing atomic simulation under real conditions — then the operator manually
switches modes. FULL_AUTOMATION stays gated after that.
