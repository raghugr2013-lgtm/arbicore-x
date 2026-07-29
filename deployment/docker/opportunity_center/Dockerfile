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

# Prepare the alpine base for unprivileged operation — see the frontend
# Dockerfile for the full rationale. Same treatment applied here.
RUN mkdir -p /var/cache/nginx/client_temp /var/cache/nginx/proxy_temp \
             /var/cache/nginx/fastcgi_temp /var/cache/nginx/uwsgi_temp \
             /var/cache/nginx/scgi_temp /var/log/nginx \
 && chown -R 101:101 /var/cache/nginx /var/log/nginx /usr/share/nginx/html /etc/nginx/conf.d \
 && sed -i 's|^\(pid\s\+\).*|\1/tmp/nginx.pid;|; s|^\(error_log\s\+\).*|\1/dev/stderr warn;|' /etc/nginx/nginx.conf

USER 101

EXPOSE 80

LABEL arbicore.role="opportunity_center" \
      arbicore.schema="v1" \
      arbicore.profile="greenfield"

# Healthcheck uses 127.0.0.1 (not localhost). The compose file overrides this
# at runtime; this default is here for defense-in-depth.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1
