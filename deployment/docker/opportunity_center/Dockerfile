# =============================================================================
#  ArbiCore X — Opportunity Center (analytics UI, Vite) Dockerfile
#
#  Build context: REPO ROOT (see deployment/compose/docker-compose.yml).
#  The compose file sets:
#      context: ../..
#      dockerfile: deployment/docker/opportunity_center/Dockerfile
#  so that this Dockerfile can COPY both the application source at
#  app/opportunity_center/ and the nginx SPA config at
#  deployment/docker/opportunity_center/ from a single context.
#
#  Package-manager selection: symmetric with the frontend Dockerfile —
#  prefers yarn.lock, falls back to npm ci, then npm install.
# =============================================================================

# ---------- Stage 1: build ---------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

COPY app/opportunity_center/package.json \
     app/opportunity_center/yarn.lock* \
     app/opportunity_center/package-lock.json* \
     ./

RUN corepack enable \
 && if   [ -f yarn.lock         ]; then yarn install --frozen-lockfile ; \
    elif [ -f package-lock.json ]; then npm ci                          ; \
    else                                npm install                     ; \
    fi

COPY app/opportunity_center/ ./

RUN if   [ -f yarn.lock ]; then yarn build ; \
    else                        npm run build ; \
    fi

# ---------- Stage 2: serve ---------------------------------------------------
FROM nginx:1.25-alpine AS runtime

COPY deployment/docker/opportunity_center/nginx-spa.conf /etc/nginx/conf.d/default.conf

# Vite output directory is `dist/` (differs from CRA's `build/`)
COPY --from=build /app/dist /usr/share/nginx/html

USER 101

EXPOSE 80

LABEL arbicore.role="opportunity_center" \
      arbicore.schema="v1" \
      arbicore.profile="greenfield"

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1
