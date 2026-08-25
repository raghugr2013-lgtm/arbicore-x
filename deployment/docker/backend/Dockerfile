# ArbiCore X — Production Backend Dockerfile
# Pinned baseline: Python 3.11-slim, FastAPI 0.110.1, Motor 3.3.1.
# Non-root runtime user (uid 1001). No secrets in image — .env mounted at runtime via env_file.
# Provenance labels (arbicore.gitsha, arbicore.schema) applied at build time.
#
# Build context: REPO ROOT (v1.0.1+ — was `app/backend/` in v1.0.0).
# This lets the Dockerfile COPY `deployment/docker/backend/requirements.prod.txt`
# directly, without any runtime-swap trickery. Works uniformly for greenfield
# and shared-infrastructure profiles.

FROM python:3.11-slim AS runtime

ARG GITSHA=unknown
ARG SCHEMA=v1
ARG GITTAG=unknown
ARG BUILD_TIME=unset
ARG APP_VERSION=unset
ARG IMAGE_DIGEST=unset
ARG IMAGE_REF=unset

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARBICORE_GIT_SHA=${GITSHA} \
    ARBICORE_GIT_TAG=${GITTAG} \
    ARBICORE_BUILD_TIME=${BUILD_TIME} \
    ARBICORE_VERSION=${APP_VERSION} \
    ARBICORE_IMAGE_DIGEST=${IMAGE_DIGEST} \
    ARBICORE_IMAGE_REF=${IMAGE_REF} \
    ARBICORE_ENV=production

# Minimal OS deps: curl for the compose healthcheck; build-essential purged after pip install.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PRODUCTION python deps. This file is the single source of truth for
# what ships in production images — it never contains emergentintegrations,
# litellm, or any dev-only tooling.
COPY deployment/docker/backend/requirements.prod.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
 && apt-get purge -y build-essential \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Copy the audited backend source. .dockerignore excludes .env, caches, .git.
COPY app/backend/ /app/

# Stamp deployment identity into the image so GET /api/arbicore/version reports
# real Git SHA / tag / build time / version even without .git (env ARGs feed it).
RUN python -m scripts.gen_build_info || true

# Non-root runtime user.
RUN useradd --create-home --shell /bin/bash --uid 1001 arbicore \
 && chown -R arbicore:arbicore /app
USER arbicore

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD curl -fs http://127.0.0.1:8001/api/ || exit 1

# Provenance labels — read by the deployment manifest.
LABEL arbicore.gitsha=${GITSHA} \
      arbicore.schema=${SCHEMA} \
      arbicore.role=backend

# server.py uses load_dotenv(ROOT_DIR/.env) — .env is mounted at run time via env_file.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
