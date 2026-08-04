# ArbiCore X v2.9.1 — Maintenance Release

**Release date:** 2026-08-04
**Type:** Maintenance only — deployment / packaging / tooling.
**Mode:** OBSERVE / PAPER · Kill switch ENGAGED (unchanged).
**Runtime behaviour:** **UNCHANGED** from v2.9.0.

## Why this release exists

Three deployment blockers were surfacing on real-world clones of v2.9.0:

1. **Windows checkout failure** — Git refused to check out the repo on
   Windows because `app/backend/arbicore/providers/aux.py` collides with
   the reserved device name `AUX`.
2. **Frontend build failure on fresh deployments** —
   `REACT_APP_BACKEND_URL` was labelled `# OPTIONAL` in the environment
   template but the compose files and Dockerfile hard-fail when it is
   empty. Fresh deployments therefore crashed at the first
   `docker compose build`.
3. **`arbictl` broke on Ubuntu 24 (PEP 668)** — the shell wrapper ran
   `pip install httpx` at runtime, which the system-wide interpreter now
   refuses. `--break-system-packages` is unacceptable on production
   hosts.

v2.9.1 fixes all three without changing product behaviour.

## What changed

### 1. Windows-safe module name

- `app/backend/arbicore/providers/aux.py` → `aux_providers.py`
- The single internal import (`app/backend/arbicore/providers/bootstrap.py`)
  now imports from `.aux_providers`.
- Verified with a repo-wide scan: no other reserved names
  (`CON`, `PRN`, `NUL`, `COM1..9`, `LPT1..9`) exist.

### 2. `REACT_APP_BACKEND_URL` promoted to REQUIRED

- `.env.example` now labels it `# REQUIRED` with an explanation of the
  compile-time-baking gotcha (CRA/Vite replace `process.env.REACT_APP_*`
  at build time; empty values produce black-screen operator UIs).
- `scripts/install.sh` gates on it in the pre-flight (line-level
  `:?`-style refusal). Fails fast with an actionable error before any
  Docker layer is built.
- No compose or Dockerfile changes were needed — both were already
  hard-failing on empty; the missing piece was the `.env` contract +
  installer gate.

### 3. `arbictl` — zero runtime installs

- `ops/arbictl` (bash wrapper) no longer runs `pip install`. It discovers
  a Python interpreter that already has `httpx` available, from a
  documented candidate list (operator override → operator venv → project
  venv `.venv/` or `venv/` → `/app/venv/` → `python3`).
- If none of the candidates has `httpx`, `arbictl` exits `3` with an
  actionable message listing four out-of-band ways to provision it
  (`apt install python3-httpx`, project venv, operator venv, backend
  container venv). It never touches the system Python.
- `ops/arbictl.py` no longer suggests `pip install httpx` on ImportError;
  it mirrors the wrapper's guidance instead.
- Two new env-vars: `ARBICTL_PYTHON` (interpreter override) and
  `ARBICTL_VENV` (venv override).

### 4. Documentation

- `docs/OPERATIONS_GUIDE.md` — new "httpx runtime dependency" section
  explaining the v2.9.0 → v2.9.1 change and the four provisioning paths.
- `docs/DEPLOYMENT_CHECKLIST.md` — rewritten for v2.9.1, includes:
  Windows clone note, PEP-668 httpx step, `REACT_APP_BACKEND_URL` as
  REQUIRED, `arbictl deploy` one-liner, `arbictl rollback` procedure.

## What did **not** change

- `arbicore/` runtime code — unchanged.
- `backend/server.py` and every FastAPI route — unchanged.
- Frontend components, styling, routes — unchanged.
- Scanner behaviour, safety defaults, provider registry — unchanged.
- MID schema, evidence exporter, daily-summary writer — unchanged.
- Docker compose service topology — unchanged.

## Regression posture

- Every existing test that references
  `app.backend.arbicore.providers.bootstrap.*` continues to import
  successfully; the rename is transparent to the module's public API.
- No new tests were added (maintenance-only).

## Constraints held

- ✅ No new features
- ✅ No new scanners / providers
- ✅ No UI work
- ✅ No execution-logic changes
- ✅ No new APIs
- ✅ No safety changes
- ✅ Backward compatible with v2.5–v2.9.0 data

## Verification matrix

| Concern | Status |
|---|---|
| Windows checkout (`aux.py` collision) | ✅ file renamed; verified no reserved names remain |
| Import graph | ✅ single reference updated in `providers/bootstrap.py` |
| Docker frontend build (`REACT_APP_BACKEND_URL` empty) | ✅ Dockerfile + compose already hard-fail; `.env.example` + `install.sh` now gate up-front |
| `arbictl` on Ubuntu 24 (PEP 668) | ✅ no runtime `pip install`; interpreter-discovery only |
| `arbictl` on legacy hosts (v2.9.0 compat) | ✅ `python3` still the last-resort candidate |
| Kill switch default | ✅ still `engaged=true` |
| Live execution default | ✅ still `false` |
| Backward compat with v2.9.0 MID data | ✅ no schema changes |

## Deliverables

- `arbicore-x-v2.9.1.tar.gz`
- `arbicore-x-v2.9.1.SHASUMS`
- `docs/RELEASE_NOTES_v2.9.1.md` (this file)
- Updated `docs/OPERATIONS_GUIDE.md`
- Updated `docs/DEPLOYMENT_CHECKLIST.md`
- Git tag `v2.9.1`

## Upgrade path from v2.9.0

```bash
# 1) pull the new tag
git fetch --tags
git checkout v2.9.1

# 2) (Ubuntu 24 only) provision httpx once
sudo apt-get install -y python3-httpx
#   — or —
python3 -m venv .venv && .venv/bin/pip install httpx

# 3) update REACT_APP_BACKEND_URL in .env (if you skipped it in v2.9.0)
$EDITOR .env

# 4) redeploy
arbictl deploy --tag v2.9.1 \
  --checksum /app/releases/v2.9.1/arbicore-x-v2.9.1.SHASUMS
```

If your v2.9.0 `.env` already had `REACT_APP_BACKEND_URL` set, no `.env`
changes are needed — the label change is documentation-only.
