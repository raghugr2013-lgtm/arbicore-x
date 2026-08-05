# v2.11 Deployment Fix — `factory-mongo` DNS Resolution + Startup Blocking

**Date**: 2026-08-05
**Applies to**: `hotfix/canonical-v2.11` / tag `v2.11` and later
**Severity**: Deployment blocker on shared-infrastructure profile
**Fix commits**: (this doc), `<startup-resilience-hash>` in `calibration_worker.py` + `adaptive_weights_worker.py`

---

## Symptom

Backend container process stays alive but `docker logs arbicore-x-backend` shows:

```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
... 30 seconds of silence ...
pymongo.errors.ServerSelectionTimeoutError:
    factory-mongo:27017: [Errno -3] Temporary failure in name resolution
```

`Application startup complete.` is never emitted → Uvicorn never binds → all HTTP traffic times out.

---

## Root Cause

Two independent issues layered together:

### 1. Docker network mismatch

The backend was started via the **shared-infrastructure** compose profile (`deployment/compose/docker-compose.shared.yml`), which attaches to an external network named by `${NETWORK_NAME}` and connects to Mongo via `${MONGO_HOST}` (default: `factory-mongo`).

On this VPS:
- `factory-mongo` container lives on the `vqb-network` Docker network.
- The backend container was attached to `arbicore-x-net` (either via the default fallback `NETWORK_NAME:-arbicore-x-net` at line 63 of `docker-compose.shared.yml`, or via a mis-baked `.env.shared`).

Docker DNS is **network-scoped**: a container can only resolve container names on networks it is attached to. So `factory-mongo` was unreachable — not because Mongo was down, but because the backend was on the wrong network.

### 2. Startup blocked on Mongo

`CalibrationWorker.start()` (called from an `@app.on_event("startup")` handler in `server.py`) awaited two blocking Mongo calls **before** creating the background loop task:

```python
async def start(self) -> None:
    if self._running:
        return
    await self._repo.ensure_indexes()      # blocks 30 s on DNS failure
    await self._warm_start_cache()         # blocks another 30 s
    self._stop_event = asyncio.Event()
    self._running = True
    self._task = asyncio.create_task(self._loop(), ...)
```

Because Uvicorn's startup phase awaits every `@app.on_event("startup")` handler sequentially, a single unreachable Mongo call stalled Uvicorn indefinitely (technically for `serverSelectionTimeoutMS`, defaulting to 30 s per call, then the same again for the next handler). The API never came up.

`AdaptiveWeightsWorker.start()` had the same pattern.

---

## Fix — Minimal, No Architectural Changes

### Fix A · Deployment (choose one)

**Operator decision required** — which Mongo owns the ArbiCore data on this VPS?

| Option | When to use | Change |
|---|---|---|
| **A1. Backend joins `vqb-network`** (recommended if the ArbiCore data is in `factory-mongo`) | ArbiCore has been sharing `factory-mongo` all along; the `arbicore-x-mongo` on `arbicore-x-net` is empty or unused. | In `deployment/compose/.env.shared`: set `NETWORK_NAME=vqb-network`. Keep `MONGO_HOST=factory-mongo`. |
| **A2. Use `arbicore-x-mongo`** on the current `arbicore-x-net` | ArbiCore has its own greenfield Mongo and `factory-mongo` was legacy config. | In `deployment/compose/.env.shared`: keep `NETWORK_NAME=arbicore-x-net`. Set `MONGO_HOST=arbicore-x-mongo` (or `MONGO_URL=mongodb://arbicore-x-mongo:27017`). Consider switching to the greenfield profile (`docker-compose.yml`) instead. |
| **A3. Multi-attach the backend to both networks** | You want the backend co-tenanted with two peer stacks — rare. | Add a second entry under the backend's `networks:` in `docker-compose.shared.yml` and declare both externals. |

**Verification steps** for any option:

```bash
# 1. Confirm Mongo is on the network you're about to join.
docker network inspect vqb-network | grep -A1 mongo

# 2. Confirm the network exists before compose up.
docker network inspect ${NETWORK_NAME}   # must exit 0

# 3. After compose up, verify DNS from inside the backend container.
docker exec arbicore-x-backend getent hosts ${MONGO_HOST}   # must print an IP

# 4. Verify Mongo handshake.
docker exec arbicore-x-backend python -c "\
from motor.motor_asyncio import AsyncIOMotorClient; import asyncio, os; \
c = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=5000); \
print(asyncio.get_event_loop().run_until_complete(c.admin.command('ping')))"
```

### Fix B · Startup Resilience (in code — already committed)

Both `CalibrationWorker.start` and `AdaptiveWeightsWorker.start` no longer block on Mongo. Boot-time init is deferred into the background task:

```python
async def start(self) -> None:
    """Non-blocking start — Uvicorn boot is never gated on Mongo."""
    if self._running:
        return
    self._stop_event = asyncio.Event()
    self._running = True
    self._task = asyncio.create_task(self._run_with_init(), name="...")

async def _run_with_init(self) -> None:
    try:
        await self._repo.ensure_indexes()
    except Exception as exc:
        logger.warning("ensure_indexes deferred (will retry on tick): %s", exc)
    try:
        await self._warm_start_cache()
    except Exception as exc:
        logger.warning("warm_start_cache deferred (will retry on tick): %s", exc)
    await self._loop()
```

**Effect**:
- Uvicorn always completes startup within ~1 s regardless of Mongo state.
- If Mongo is unreachable at boot, the worker logs a WARNING (not a startup failure), and its existing `_loop` backoff ladder handles retry on the next tick.
- If Mongo comes online later (e.g. after a network fix), the worker recovers on its own — no restart required.
- The API surface goes live immediately; Mongo-dependent endpoints will return their canonical empty states (Slice 3 activation contract) until connectivity is restored.

---

## Rollout

1. Apply Fix A on the VPS: correct `.env.shared` and `docker network` topology.
2. Redeploy v2.11: `docker compose --env-file .env.shared -f docker-compose.shared.yml up -d`.
3. Confirm `Application startup complete.` appears in `docker logs arbicore-x-backend` within ~2 s.
4. `curl -fs http://127.0.0.1:${BACKEND_HOST_PORT}/api/` returns 200.
5. Confirm the two background workers reach steady state (should log a promoted/kept status within ~1 tick interval).

---

## Regression Guard

The two `start()` refactors are behaviour-preserving on the happy path (Mongo reachable at boot). To verify:

```python
# Both must return within 100ms even when Mongo is unreachable.
from arbicore.learning.concrete.calibration_worker import CalibrationWorker
w = CalibrationWorker(unreachable_db, calibrator, repo, cfg)
import time; t0 = time.time(); await w.start(); assert time.time() - t0 < 0.5
```

`AsyncIOMotorClient`'s `serverSelectionTimeoutMS` is left at its default (30 s) intentionally: individual worker ticks will time out and log a warning, but the API surface remains live throughout.
