"""Observation Recorder endpoints (Sprint 5) — PURE DATA CAPTURE, read-only.
No execution, no trading, no transfers."""
from fastapi import APIRouter, Depends

from services.auth import require_auth
from services.observation import observation

router = APIRouter(prefix="/api/observation", tags=["observation"],
                   dependencies=[Depends(require_auth)])


@router.get("/status")
async def observation_status():
    return await observation.status()


@router.post("/snapshot")
async def observation_snapshot():
    n = await observation.snapshot_now()
    return {"ok": True, "documents": n,
            "message": f"Readiness snapshot captured ({n} venue docs)"}
