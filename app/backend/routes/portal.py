"""Phase E1 — Portal price endpoints (READ-ONLY).
Live BlockDAG portal swap price + historical series. No execution."""
from typing import Optional

from fastapi import APIRouter, Depends

from services import db
from services.auth import require_auth
from services.portal_price import portal_price

router = APIRouter(prefix="/api/portal", tags=["portal"], dependencies=[Depends(require_auth)])


@router.get("/price")
async def portal_price_status():
    return await portal_price.status()


@router.get("/price/history")
async def portal_price_history(hours: int = 24, limit: int = 500):
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    docs = await db.portal_price_snapshots.find(
        {"ts": {"$gte": cutoff}},
        {"_id": 0, "ts": 1, "bdag_price": 1},
        sort=[("ts", -1)]).to_list(limit)
    docs.reverse()
    return {"hours": hours, "points": docs, "count": len(docs)}


@router.post("/price/refresh")
async def portal_price_refresh():
    ok = await portal_price.refresh()
    return {"ok": ok, "bdag_price": portal_price.bdag_price,
            "fetched_at": portal_price.fetched_at, "last_error": portal_price.last_error}
