"""Strategy IR ingestion — admin-authenticated, NON-EXECUTABLE.

Reuses the existing ArbiCore auth (`require_auth`, single-admin). No endpoint here
can set execution mode, touch the kill switch, authorize a signer, or broadcast —
it only stores research candidates for the existing downstream pipeline to evaluate.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from arbicore.strategy_ir.schema import StrategyIR, StrategyIRValidationError
from arbicore.strategy_ir import registry as ir_registry
from arbicore.strategy_ir.adapter import candidate_to_opportunity_hypothesis
from services.auth import require_auth

router = APIRouter(prefix="/api/strategy", tags=["strategy-ir"])
_logger = logging.getLogger("arbicore.strategy_ir.ingest")


def require_admin(user: dict = Depends(require_auth)) -> dict:
    if (user or {}).get("role") != "admin":
        raise HTTPException(403, "Admin privilege required")
    return user


@router.post("/candidates")
async def ingest_candidate(ir: StrategyIR, user: dict = Depends(require_admin)):
    """Ingest a Strategy IR as a non-executable candidate."""
    try:
        ir.validate_non_executable()
    except StrategyIRValidationError as exc:
        # F4: log the specific violation server-side; return a generic reason so
        # the response never echoes a caller-supplied key name/path.
        _logger.warning("strategy candidate rejected (non-executable contract): %s", exc)
        raise HTTPException(422, "Strategy IR rejected: non-permitted execution/"
                                 "authorization content")
    try:
        ir.validate_provenance_policy()
    except StrategyIRValidationError as exc:
        # Provenance-policy messages are safe (no alpha) and actionable.
        raise HTTPException(422, str(exc))
    result = await ir_registry.register(ir)
    # F3: fingerprint is identity; keep it out of INFO logs (DEBUG only).
    _logger.debug("strategy candidate ingested fp=%s v=%s by=%s duplicate=%s state=%s",
                  result["strategy_fingerprint"], result["strategy_version"],
                  user.get("username"), result["duplicate"],
                  result["lifecycle_state"])
    return {**result, "executable": False}


@router.get("/candidates")
async def list_candidates(limit: int = 100, user: dict = Depends(require_admin)):
    return {"candidates": await ir_registry.list_candidates(limit=limit)}


@router.get("/registry/{strategy_id}")
async def get_registry_entry(strategy_id: str, user: dict = Depends(require_admin)):
    entry = await ir_registry.get_registry_entry(strategy_id)
    if not entry:
        raise HTTPException(404, "strategy not found")
    return entry


@router.post("/candidates/{strategy_id}/preview-hypothesis")
async def preview_hypothesis(strategy_id: str, user: dict = Depends(require_admin)):
    """Return the opportunity-hypothesis the adapter would emit — for operator
    inspection only. It is explicitly non-executable and must pass the existing
    downstream gates before it could ever become an opportunity."""
    entry = await ir_registry.get_registry_entry(strategy_id)
    if not entry:
        raise HTTPException(404, "strategy not found")
    cand = await ir_registry.get_candidate(strategy_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    if cand.get("lifecycle_state") == ir_registry.LIFECYCLE_QUARANTINED:
        raise HTTPException(409, "strategy is quarantined (restricted/proprietary) — "
                                 "not eligible for hypothesis preview until cleared")
    ir = StrategyIR(**{k: cand[k] for k in cand if k in StrategyIR.model_fields})
    return {"hypothesis": candidate_to_opportunity_hypothesis(ir),
            "note": "NON-EXECUTABLE; must pass existing discovery/economics/"
                    "simulation/evidence gates independently."}
