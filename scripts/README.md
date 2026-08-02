# ArbiCore X — scripts/

Operator-side automation for greenfield installs, upgrades, health probes,
backup/restore, and **deployment verification** (v1.0.2+).

## Deployment verification

`verify-deployment.sh` is the canonical post-deployment sanity harness. It
runs the 8-category verification matrix and must pass before any release
is declared production-ready.

### Categories

1. **Backend health** — container running, docker healthcheck healthy, `/api/` returns 200
2. **Frontend HTTP 200** — operator UI SPA reachable, `<div id="root">` present, JS bundle referenced
3. **Opportunity Center HTTP 200** — analytics SPA reachable (or `/healthz` on container)
4. **Bundle verification** — compiled bundle contains configured domain, zero `void 0` refs (the exact v1.0.1 regression guard)
5. **Browser runtime** — login page renders, no uncaught JavaScript exceptions
6. **API connectivity** — `/api/auth/status` returns `200 application/json` (not HTML fallback)
7. **Successful login** — `POST /api/auth/login` returns 200 + session, `/api/auth/me` identifies the user
8. **Dashboard render** — authenticated navigation to `/` mounts the Terminal dashboard

Categories 5 and 8 require Playwright. If Playwright is unavailable the
script marks them SKIP and continues; SKIP does not fail the run.

### One-time setup on the VPS

Playwright and its browser download only need to be installed once per
host (or CI runner). This step is intentionally outside any production
Docker image — verification runs from the host, not from a container.

```bash
cd $REPO_ROOT/scripts
npm install              # installs playwright
npx playwright install chromium
```

If you skip this step, the script still runs — it just marks the two
browser-based checks as SKIP and prints a manual verification hint.

### Running

```bash
# Full run against a shared-infrastructure deployment:
scripts/verify-deployment.sh \
    --domain https://arbicore.example.com \
    --profile shared \
    --admin-user admin \
    --admin-pass "$ADMIN_PASS"

# Shell/API-only (skip Playwright), suitable for CI without a browser:
scripts/verify-deployment.sh \
    --domain https://arbicore.example.com \
    --profile shared --skip-browser

# Machine-readable JSON output for pipelines:
scripts/verify-deployment.sh \
    --domain https://arbicore.example.com \
    --profile shared \
    --json /tmp/verify-result.json
```

### Exit codes

- `0` — all checks PASS (SKIP does NOT fail the run)
- `1` — one or more checks FAILED
- `2` — invalid arguments or preflight failure (e.g. `docker` missing)

### When to run it

**Every** production deployment. Post-install, post-upgrade,
post-rollback, and once a week as a heartbeat if you have automation
capacity. It is completely read-only against the deployment — safe to
run at any time.

### Where results go

- Standard out: coloured PASS/FAIL/SKIP report with per-check context
- `--json PATH`: pipeline-friendly summary (counts + list of failed check descriptions)
- `/tmp/verify_*.{json,txt,html}`: raw per-check artifacts (bundle
  fingerprints, response bodies) for post-mortem inspection

### Files

- `verify-deployment.sh` — the shell harness (categories 1–4, 6, 7)
- `verify-browser.mjs` — Playwright helper for categories 5 and 8
- `package.json` — declares the Playwright dependency (host-side only)
