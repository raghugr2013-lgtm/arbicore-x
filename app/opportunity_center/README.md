# ArbiCore X — Opportunity Center

Operator-facing UI for ArbiCore X. **Separate artefact from the frozen UIC frontend** (`/app/frontend`, supervisor-FATAL by design — do not modify).

## Scope (Phase 1 — this scaffold)

- 5 read-only pages: **Home**, **Opportunities**, **Wallet Intelligence**, **Analytics**, **System Health**
- Auth wired against existing `/api/auth/login` (cookie-based JWT)
- React 18 + Vite 5 + TailwindCSS + TanStack Query + Recharts + react-router v6
- Reads ONLY from existing `/api/arbicore/...` endpoints (no write paths)

## Out of scope (do **not** add in Phase 1)

- Verifier / gate / threshold / economics / scanner_config edits
- D-6.2, D-4.7, watchdog touch
- UIC frontend (`/app/frontend`) reactivation
- Opportunity Detail (Phase 2), Analytics visualisations (Phase 3)

## Run locally (preview environment)

```bash
cd /app/opportunity_center
yarn install
yarn dev   # → http://localhost:3100
```

Vite dev server proxies `/api/*` → `VITE_BACKEND_URL` (default `http://localhost:8001`).

## Build for production

```bash
yarn build
yarn preview
```

The `dist/` artefact is a static SPA — deploy to nginx/Caddy on the VPS, or to Vercel/Netlify with a CORS rewrite.

## Environment

`.env` (local; copy from `.env.example`):
```
VITE_BACKEND_URL=https://arbicore-x.example.com
```

In the preview container, leave `VITE_BACKEND_URL` unset to use the localhost proxy.

## Backend dependency

Requires the following routes (all already implemented in `/app/backend/arbicore/routes/`):

| Page | Route | Status |
|---|---|:---:|
| Home | `GET /api/arbicore/health` | existing |
| Home | `GET /api/arbicore/opportunities` | existing |
| Opportunities | `GET /api/arbicore/opportunities?type=&status=&limit=` | existing |
| Wallet Intelligence | `GET /api/arbicore/wallets` | new (Phase 1) |
| Wallet Intelligence | `POST /api/arbicore/wallets/get_many` | new (Phase 1) |
| Analytics | `GET /api/arbicore/analytics/timeseries` | new (Phase 1) |
| Analytics | `GET /api/arbicore/analytics/funnel` | new (Phase 1) |
| Analytics | `GET /api/arbicore/discovery_candidates/stats` | new (Phase 1) |
| System Health | `GET /api/arbicore/system/collections` | new (Phase 1) |
| System Health | `GET /api/arbicore/audit_log` | new (Phase 1) |
| System Health | `GET /api/arbicore/scanners/...` (existing) | existing |

## Frozen invariants

This UI is **read-only**. The codebase enforces:
- No `POST /api/arbicore/*` calls except `/wallets/get_many` (which is a pure read query — no DB mutation).
- No mutation of thresholds, verifier, economics, or scanner_config.
- No imports from or wiring into `/app/frontend`.
