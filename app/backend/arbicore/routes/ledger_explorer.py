"""Read-only Opportunity Ledger explorer and Excel export.

Research surface. No scanner, execution, wallet, signing, or broadcast routes.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from services.auth import require_auth

from ..opportunity_ledger.export_xlsx import build_workbook
from ..opportunity_ledger.store import (
    list_opportunities,
    list_runs,
    load_rows,
    opportunity_detail,
    run_summary,
)
from ..runtime.composition import get_db

router = APIRouter(prefix="/api/arbicore/ledger", tags=["opportunity-ledger"])


def _db():
    return get_db()


@router.get("/runs", dependencies=[Depends(require_auth)])
async def ledger_runs():
    return await list_runs(_db())


@router.get("/runs/{run_id}/summary", dependencies=[Depends(require_auth)])
async def ledger_run_summary(run_id: str):
    summary = await run_summary(_db(), run_id)
    if summary is None:
        raise HTTPException(status_code=404, detail={"error": "run_not_found", "run_id": run_id})
    return summary


@router.get("/opportunities", dependencies=[Depends(require_auth)])
async def ledger_opportunities(
    run_id: str = Query(...),
    chain: Optional[str] = None,
    family: Optional[str] = None,
    provider: Optional[str] = None,
    bundle: Optional[str] = None,
    gate_7: Optional[str] = None,
    net_min: Optional[float] = None,
    net_max: Optional[float] = None,
    ts_from: Optional[str] = None,
    ts_to: Optional[str] = None,
    sort: str = "net",
    order: str = "desc",
    page: int = 1,
    page_size: int = 25,
):
    if bundle not in (None, "", "backed", "decision_only"):
        raise HTTPException(status_code=400, detail="bundle must be backed or decision_only")
    try:
        return await list_opportunities(
            _db(),
            run_id=run_id,
            chain=chain or None,
            family=family or None,
            provider=provider or None,
            bundle=bundle or None,
            gate_7=gate_7 or None,
            net_min=net_min,
            net_max=net_max,
            ts_from=ts_from,
            ts_to=ts_to,
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/opportunities/{ledger_id}", dependencies=[Depends(require_auth)])
async def ledger_opportunity(ledger_id: str):
    row = await opportunity_detail(_db(), ledger_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "ledger_id": ledger_id})
    return row


@router.get("/runs/{run_id}/export", dependencies=[Depends(require_auth)])
async def ledger_export(run_id: str):
    rows = await load_rows(_db(), run_id)
    if not rows:
        raise HTTPException(status_code=404, detail={"error": "run_not_found", "run_id": run_id})
    payload = build_workbook(rows)
    filename = f"opportunity_ledger_{run_id}.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
