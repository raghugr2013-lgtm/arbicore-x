# Audited ArbiCore X backend image.
# Pinned to the MANIFEST baseline: Python 3.11-slim, FastAPI 0.110.1, Motor 3.3.1, httpx 0.28.1.
# Bundles pinned Foundry/Anvil v1.7.1 (SHA256-verified) for the T2 REVM fork
# simulation backend — SHADOW-only, never signs/broadcasts.
# Built only via compose so labels/context match the deployment manifest exactly.
# Version/commit identity is injected via build.args (GITSHA/GITTAG/APP_VERSION)
# and the compose IMAGE_TAG derives from the repo VERSION + short SHA (unambiguous).
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

# ---------------------------------------------------------------------------
# Pinned Foundry / Anvil runtime (T2 REVM fork simulation backend)
# ---------------------------------------------------------------------------
# The T2 searcher's RevmForkBackend uses `anvil --fork-url` for LOCAL, READ-ONLY
# state simulation (eth_call against a forked Base state). SHADOW-only: anvil is
# NEVER used to sign or broadcast a transaction. Pinned to v1.7.1 (== the VPS
# host's anvil) and SHA256-verified so the image is byte-reproducible and
# production-safe. Only the `anvil` binary is extracted to keep the image lean.
ARG FOUNDRY_VERSION=v1.7.1
ARG FOUNDRY_SHA256=cf7e688ed0c4c48adffca788b496076e31060b67ac5afe1e43dbb5499c20c88b
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    if [ "$arch" != "amd64" ]; then \
      echo "Foundry pin only provisioned for amd64 (VPS target); got '$arch'" >&2; \
      exit 1; \
    fi; \
    url="https://github.com/foundry-rs/foundry/releases/download/${FOUNDRY_VERSION}/foundry_${FOUNDRY_VERSION}_linux_amd64.tar.gz"; \
    curl -fsSL "$url" -o /tmp/foundry.tar.gz; \
    echo "${FOUNDRY_SHA256}  /tmp/foundry.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/foundry.tar.gz -C /usr/local/bin anvil; \
    rm -f /tmp/foundry.tar.gz; \
    chmod 755 /usr/local/bin/anvil; \
    anvil --version

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
