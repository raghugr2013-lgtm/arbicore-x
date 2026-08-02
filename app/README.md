# `app/` — Application source

This tree contains the ArbiCore X application code and its tests. It is the *only* place application code lives. It never references anything outside its own subtree.

## Layout

```
app/
├── backend/               FastAPI application on Python 3.11
│   ├── arbicore/          Scanner core (D-1 through D-6 families, intel, runtime, data, models, routes)
│   ├── connectors/        Exchange + wallet connectors (bitmart, coinstore, gate, mexc, xt, sim, evm_wallet, ...)
│   ├── core/, engines/, diagnostics/, routes/, services/, scripts/
│   ├── tests/             pytest suite (~200 files, D-1…D-6 scanner families + wave endpoints)
│   ├── conftest.py, server.py, reset_admin.py, requirements.txt
├── frontend/              Operator UI — CRA + CRACO + Tailwind + shadcn/ui
│   ├── src/, public/, plugins/
│   ├── package.json       yarn 1.22.22 (declared as packageManager)
│   ├── yarn.lock          canonical lockfile — required for reproducible builds
│   ├── .npmrc             legacy-peer-deps=true (npm fallback safety net)
│   ├── craco.config.js, tailwind.config.js, postcss.config.js
│   ├── components.json, jsconfig.json
└── opportunity_center/    Analytics UI — Vite + React + Tailwind
    ├── src/, index.html
    ├── package.json, vite.config.js
    └── postcss.config.js, tailwind.config.js
```

## How the application is consumed

- The **backend** image is built with `app/backend/` as its Docker context. See `deployment/docker/backend/Dockerfile`.
- The **frontend** image is built with the *repo root* as its Docker context so the Dockerfile can COPY both `app/frontend/` and `deployment/docker/frontend/nginx-spa.conf`. See `deployment/docker/frontend/Dockerfile`.
- The **opportunity_center** image uses the same pattern.
- `app/backend/arbicore/intel/launch/labels.json` is bind-mounted read-only into the running backend container so operators can hot-edit curated wallet labels without a rebuild.

## Absolute rules

- **The application MUST NEVER reference `deployment/`, `scripts/`, or `docs/`.** If a code path needs a value that varies by deployment, it comes from an env variable — nothing else.
- Any change to `app/backend/requirements.txt` must be reflected in `deployment/docker/backend/requirements.prod.txt` (production-scoped, dev tools excluded) and `deployment/docker/backend/requirements.dev.txt`.
- Any new env variable read by the application must appear in every relevant `.env.*.example` at the repo root.

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the full engineering standards.
