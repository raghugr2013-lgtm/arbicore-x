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

# Prepare the alpine base for unprivileged operation:
#   * cache/log dirs writable by the nginx user (uid 101)
#   * PID file redirected to /tmp so /var/run is not needed
#   * error_log to stderr so /var/log/nginx write is not needed at boot
# These make `USER 101` work reliably across nginx:1.25-alpine base image variants.
RUN mkdir -p /var/cache/nginx/client_temp /var/cache/nginx/proxy_temp \
             /var/cache/nginx/fastcgi_temp /var/cache/nginx/uwsgi_temp \
             /var/cache/nginx/scgi_temp /var/log/nginx \
 && chown -R 101:101 /var/cache/nginx /var/log/nginx /usr/share/nginx/html /etc/nginx/conf.d \
 && sed -i 's|^\(pid\s\+\).*|\1/tmp/nginx.pid;|; s|^\(error_log\s\+\).*|\1/dev/stderr warn;|' /etc/nginx/nginx.conf

USER 101

EXPOSE 80

# Provenance labels
LABEL arbicore.role="frontend" \
      arbicore.schema="v1" \
      arbicore.profile="greenfield"

# Healthcheck uses 127.0.0.1 (not localhost) — alpine minimal /etc/hosts
# may not resolve "localhost". This is a defense-in-depth default; the
# compose file also carries an equivalent healthcheck (compose wins at runtime).
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1
