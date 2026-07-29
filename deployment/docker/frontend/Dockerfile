# =============================================================================
#  ArbiCore X — Frontend (operator UI, CRA/craco) Dockerfile
#
#  Build context: REPO ROOT (see deployment/compose/docker-compose.yml).
#  The compose file sets:
#      context: ../..
#      dockerfile: deployment/docker/frontend/Dockerfile
#  so that this Dockerfile can COPY both the application source at
#  app/frontend/ and the nginx SPA config at deployment/docker/frontend/
#  from a single context.
#
#  Package-manager selection: yarn.lock is preferred (matches package.json's
#  declared `packageManager: yarn@1.22.22`) but is optional; the build falls
#  back to `npm ci` (when package-lock.json is present) then to `npm install`.
# =============================================================================

# ---------- Stage 1: build ---------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# Copy manifest + any lockfile that happens to be present. The glob patterns
# (`yarn.lock*`, `package-lock.json*`) are permitted by Docker because at
# least one match is guaranteed (`app/frontend/package.json`), so the COPY
# succeeds whether or not the lockfiles exist in a clean checkout.
COPY app/frontend/package.json \
     app/frontend/yarn.lock* \
     app/frontend/package-lock.json* \
     ./

# Conditional install: prefer the pinned lock, fall back safely. Corepack is
# enabled so the `packageManager` field in package.json (yarn@1.22.22) is
# honored when yarn.lock is present.
RUN corepack enable \
 && if   [ -f yarn.lock         ]; then yarn install --frozen-lockfile ; \
    elif [ -f package-lock.json ]; then npm ci                          ; \
    else                                npm install                     ; \
    fi

# Copy the rest of the frontend source and build. Any node_modules, build/,
# .env, or coverage artifacts inside app/frontend/ are excluded by the
# repo-root .dockerignore so we always start from a clean state.
COPY app/frontend/ ./

RUN if   [ -f yarn.lock ]; then yarn build ; \
    else                        npm run build ; \
    fi

# ---------- Stage 2: serve ---------------------------------------------------
FROM nginx:1.25-alpine AS runtime

# The SPA nginx config lives in the deployment tree and is reachable because
# the build context is the repo root, not app/frontend/.
COPY deployment/docker/frontend/nginx-spa.conf /etc/nginx/conf.d/default.conf

# CRA/craco output directory is `build/`
COPY --from=build /app/build /usr/share/nginx/html

# nginx image ships an unprivileged `nginx` user (uid 101) via the alpine base.
# Confirm non-root at runtime (arbicore invariant #3 in DEPLOYMENT_MANIFEST §10).
USER 101

EXPOSE 80

# Provenance labels
LABEL arbicore.role="frontend" \
      arbicore.schema="v1" \
      arbicore.profile="greenfield"

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1
