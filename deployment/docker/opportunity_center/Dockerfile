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

# ---------------------------------------------------------------------------
# BUILD-TIME ENVIRONMENT (Vite compile-time binding)
#
# Vite replaces `import.meta.env.VITE_*` references at COMPILE TIME (via
# esbuild define). Whatever value VITE_BACKEND_URL holds during `yarn build`
# is BAKED into the static JS bundle. An empty value produces a broken
# bundle that dies at runtime with a black screen — same failure mode as
# CRA with an unbaked REACT_APP_BACKEND_URL. See docs/releases/v1.0.2.md.
#
# We declare the ARG, HARD-FAIL if empty, and promote to ENV so the build
# picks it up.
# ---------------------------------------------------------------------------
ARG VITE_BACKEND_URL
ARG GITSHA=unknown

RUN if [ -z "$VITE_BACKEND_URL" ]; then \
      echo "" >&2; \
      echo "============================================================" >&2; \
      echo "  BUILD FAILED: VITE_BACKEND_URL is required but empty." >&2; \
      echo "============================================================" >&2; \
      echo "  Vite bakes this variable into the JS bundle at compile time." >&2; \
      echo "  An empty value produces a broken bundle (black screen at runtime)." >&2; \
      echo "" >&2; \
      echo "  Pass it via docker-compose:" >&2; \
      echo "      build:" >&2; \
      echo "        args:" >&2; \
      echo "          VITE_BACKEND_URL: https://your.domain.tld" >&2; \
      echo "" >&2; \
      echo "  Or via docker build directly:" >&2; \
      echo "      docker build --build-arg VITE_BACKEND_URL=https://your.domain.tld ..." >&2; \
      echo "============================================================" >&2; \
      exit 1; \
    fi

ENV VITE_BACKEND_URL=$VITE_BACKEND_URL \
    GITSHA=$GITSHA

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

# ---------------------------------------------------------------------------
# POST-BUILD SANITY CHECK (defense-in-depth regression guard)
#
# Vite emits references to import.meta.env directly. If a build somehow
# produces "undefined/api" in dist/, fail fast rather than shipping a
# black-screen artifact.
# ---------------------------------------------------------------------------
RUN if grep -rqE '"".concat\(void 0,"/api"\)|undefined/api' dist/assets/ 2>/dev/null; then \
      echo "" >&2; \
      echo "============================================================" >&2; \
      echo "  BUILD FAILED: compiled bundle contains undefined API base." >&2; \
      echo "============================================================" >&2; \
      echo "  Detected undefined/api reference in dist/assets/." >&2; \
      echo "  VITE_BACKEND_URL was likely not propagated to the build." >&2; \
      echo "  Rebuild with --no-cache and verify the build arg is set." >&2; \
      echo "============================================================" >&2; \
      exit 1; \
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
