# Audited ArbiCore X backend image (0.1.0).
# Pinned to the MANIFEST baseline: Python 3.11-slim, FastAPI 0.110.1, Motor 3.3.1, httpx 0.28.1.
# Built only via compose so labels/context match the deployment manifest exactly.
FROM python:3.11-slim AS runtime

# Deployment identity (Stage 2) — supplied by compose build.args from
# compose/.env (written by steps/00_detect_env.sh). Exported to runtime env so
# GET /api/arbicore/version reports the real Git SHA / build metadata.
ARG GITSHA=unknown
ARG GITTAG=unknown
ARG BUILD_TIME=unset
ARG APP_VERSION=unset

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARBICORE_GIT_SHA=${GITSHA} \
    ARBICORE_GIT_TAG=${GITTAG} \
    ARBICORE_BUILD_TIME=${BUILD_TIME} \
    ARBICORE_VERSION=${APP_VERSION} \
    ARBICORE_ENV=production

# Minimal OS deps: curl for the compose healthcheck; build-essential only at install-time.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache layer)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
 && apt-get purge -y build-essential \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Copy the audited source. .env is intentionally NOT copied -> mounted via env_file at runtime
# so secrets never end up in the image. .dockerignore enforces this.
COPY . /app

# Non-root runtime user
RUN useradd --create-home --shell /bin/bash --uid 1001 arbicore \
 && chown -R arbicore:arbicore /app
USER arbicore

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fs http://localhost:8001/api/ || exit 1

# server.py uses load_dotenv(ROOT_DIR/.env) — .env is mounted via env_file at run time.
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
