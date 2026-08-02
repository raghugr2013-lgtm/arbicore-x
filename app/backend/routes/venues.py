"""Venue Monitoring Layer — read-only observational endpoints.

Surfaces health/depth/prices/status/readiness/alerts for the 5 monitored venues.
NEVER modifies the proposal engine or Approval Mode state.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import db
from services.auth import require_auth
from services.venue_monitor import venue_monitor
from services.venue_monitor import connectors

router = APIRouter(prefix="/api/venues", tags=["venues"],
                   dependencies=[Depends(require_auth)])


SUPPORTED = list(connectors.VENUE_FETCHERS.keys())


def _check_venue(ex: str):
    if ex not in SUPPORTED:
        raise HTTPException(status_code=404, detail=f"venue '{ex}' not monitored")


@router.get("/status")
async def status():
    """Worker status + list of monitored venues."""
    return await venue_monitor.status()


@router.get("/health")
async def list_health():
    """Latest health snapshot for every monitored venue."""
    docs = await db.db.venue_health.find({}, {"_id": 0}).to_list(20)
    return {"venues": docs, "count": len(docs)}


@router.get("/health/{ex}")
async def get_health(ex: str):
    _check_venue(ex)
    doc = await db.db.venue_health.find_one({"exchange": ex}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="no snapshot yet")
    return doc


@router.get("/prices/{ex}")
async def get_prices(ex: str, limit: int = 60):
    _check_venue(ex)
    cur = db.db.venue_prices.find({"exchange": ex}, {"_id": 0, "ts_dt": 0}).sort("ts_ts", -1).limit(min(max(limit, 1), 1000))
    rows = await cur.to_list(limit)
    return {"exchange": ex, "rows": rows, "count": len(rows)}


@router.get("/depth/{ex}")
async def get_depth(ex: str):
    _check_venue(ex)
    doc = await db.db.venue_depth.find_one({"exchange": ex}, {"_id": 0, "ts_dt": 0},
                                           sort=[("ts_ts", -1)])
    if not doc:
        raise HTTPException(status_code=404, detail="no depth snapshot yet")
    return doc


@router.get("/status-history/{ex}")
async def get_status_history(ex: str, limit: int = 50):
    _check_venue(ex)
    cur = db.db.venue_status_history.find({"exchange": ex}, {"_id": 0, "ts_dt": 0}).sort("ts_ts", -1).limit(min(max(limit, 1), 500))
    rows = await cur.to_list(limit)
    return {"exchange": ex, "rows": rows}


@router.get("/readiness")
async def list_readiness():
    """Per-venue readiness summary across all monitored venues."""
    docs = await db.db.venue_health.find({}, {"_id": 0, "exchange": 1, "full_cycle_ready": 1,
                                              "health_score": 1, "readiness": 1,
                                              "last_check_at": 1, "status": 1}).to_list(20)
    return {"venues": docs}


@router.get("/readiness/{ex}")
async def get_readiness(ex: str):
    _check_venue(ex)
    doc = await db.db.venue_health.find_one({"exchange": ex}, {"_id": 0, "exchange": 1,
                                                                "full_cycle_ready": 1,
                                                                "health_score": 1,
                                                                "readiness": 1,
                                                                "status": 1,
                                                                "derived": 1,
                                                                "last_check_at": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="no snapshot yet")
    return doc


@router.get("/alerts")
async def list_alerts(limit: int = 50, unacknowledged_only: bool = False):
    q = {"acknowledged": False} if unacknowledged_only else {}
    cur = db.db.venue_alerts.find(q, {"_id": 0, "ts_dt": 0}).sort("ts_ts", -1).limit(min(max(limit, 1), 500))
    rows = await cur.to_list(limit)
    return {"alerts": rows}


class AckBody(BaseModel):
    ts_ts: int
    exchange: str


@router.post("/alerts/acknowledge")
async def acknowledge_alert(body: AckBody):
    res = await db.db.venue_alerts.update_one(
        {"ts_ts": body.ts_ts, "exchange": body.exchange},
        {"$set": {"acknowledged": True}})
    return {"updated": res.modified_count}


class IntelligenceBody(BaseModel):
    exchange: str
    deposit_credit_verified: bool | None = None
    withdraw_credit_verified: bool | None = None
    notes: str | None = None


@router.post("/intelligence")
async def upsert_intelligence(body: IntelligenceBody):
    """Operator manual flags — used by the readiness scorer for the
    'deposit_crediting_verified' check (cannot be verified automatically
    without actually depositing; operator confirms after a successful
    real-world test)."""
    _check_venue(body.exchange)
    update = {"exchange": body.exchange}
    if body.deposit_credit_verified is not None:
        update["deposit_credit_verified"] = body.deposit_credit_verified
    if body.withdraw_credit_verified is not None:
        update["withdraw_credit_verified"] = body.withdraw_credit_verified
    if body.notes is not None:
        update["notes"] = body.notes
    await db.db.venue_intelligence.update_one(
        {"exchange": body.exchange}, {"$set": update}, upsert=True)
    return await db.db.venue_intelligence.find_one({"exchange": body.exchange}, {"_id": 0})


@router.post("/refresh")
async def force_refresh():
    """One-shot: triggers a venue poll out-of-band. Useful for testing."""
    await venue_monitor._run_once()  # noqa: SLF001
    return {"refreshed_at": (await venue_monitor.status())["last_run_at"]}
