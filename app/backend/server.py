import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from api import router as api_router  # noqa: E402
from connectors import register_all  # noqa: E402
from routes.alerts import router as alerts_router  # noqa: E402
from routes.auth import router as auth_router  # noqa: E402
from routes.execution import router as execution_router  # noqa: E402
from routes.observation import router as observation_router  # noqa: E402
from routes.portal import router as portal_router  # noqa: E402
from routes.portfolio import router as portfolio_router  # noqa: E402
from routes.vault import router as vault_router  # noqa: E402
from services import db  # noqa: E402
from services.auth import require_auth  # noqa: E402
from services.balances import balance_service  # noqa: E402
from services.collector import collector  # noqa: E402
from services.execution import config as exec_config  # noqa: E402
from services.execution import fees as exec_fees  # noqa: E402
from services.execution import venue_registry as exec_venues  # noqa: E402
from services.execution import exchange_intelligence as exec_exchange_intel  # noqa: E402
from services.execution import permanent_ledger as exec_perm_ledger  # noqa: E402
from services.execution.opportunity_gate import opportunity_monitor  # noqa: E402
from services.execution.fund_tracker import fund_tracker  # noqa: E402
from services.execution.integration_monitor import integration_monitor  # noqa: E402
from services.execution.shadow import shadow_runner  # noqa: E402
from services.execution.campaign import shadow_campaign  # noqa: E402
from services.execution.drift_runner import drift_runner  # noqa: E402
from services.execution.approval_workflow import ensure_indexes as _approval_indexes  # noqa: E402
from services.execution.approval_proposer import approval_proposer  # noqa: E402
from services.venue_monitor import venue_monitor  # noqa: E402
from routes.venues import router as venues_router  # noqa: E402
from services.observation import observation  # noqa: E402
from services.portal_price import portal_price  # noqa: E402
from services.seed import seed  # noqa: E402

# ArbiCore X (Phase B + C Wave 1) — read-only foundation router + composition root
from arbicore.routes import arbicore_router  # noqa: E402
from arbicore.routes.scanners import router as arbicore_scanners_router  # noqa: E402
from arbicore.routes.opportunity_center import router as arbicore_opportunity_center_router  # noqa: E402
from arbicore.runtime.composition import (  # noqa: E402
    initialise_arbicore_runtime,
    shutdown_arbicore_runtime,
)

DOCS_DIR = ROOT_DIR.parent / 'docs'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_all()
    await db.ensure_indexes()
    await seed()
    await exec_venues.ensure_seeded()
    await exec_config.ensure_seeded()
    await exec_fees.ensure_seeded()
    from services.execution import bdag_transfers as exec_bdag_transfers
    await exec_bdag_transfers.ensure_seeded()
    from services.execution import quote_capture as exec_quote_capture
    await exec_quote_capture.ensure_indexes()
    from services.execution import arbitrage_cycles as exec_cycles
    await exec_cycles.ensure_indexes()
    from services.execution import wallet_observer as exec_observer
    await exec_observer.ensure_indexes()
    await exec_observer.poller.start()
    await exec_exchange_intel.ensure_seeded()
    await collector.start()
    await balance_service.start()
    await observation.start()
    await portal_price.start()
    await fund_tracker.start()
    await shadow_runner.start()
    await integration_monitor.start()
    await shadow_campaign.start_monitor()
    await exec_perm_ledger.backfill()
    await opportunity_monitor.start_monitor()
    await drift_runner.start()
    await _approval_indexes()
    await approval_proposer.start()
    await venue_monitor.start()
    # ArbiCore X Phase B — initialise after existing services. Adds no worker.
    _arbicore_wiring = await initialise_arbicore_runtime()
    logger.info("ArbiCore X Phase B wired: %s", {
        "collections": len(_arbicore_wiring.get("indexes", {}).get("collections", [])),
        "ttl_indexes": len(_arbicore_wiring.get("indexes", {}).get("ttl_indexes", [])),
    })
    logger.info("ArbiCore backend started (observation + E1 portal + E2 scaffold + E3 shadow + E4 integration prep + E4.5 campaign + drift analyzer + approval workflow + approval proposer + venue monitor + arbicore_x phase B)")
    yield
    await shutdown_arbicore_runtime()
    await venue_monitor.stop()
    await approval_proposer.stop()
    await drift_runner.stop()
    await opportunity_monitor.stop_monitor()
    await shadow_campaign.stop_monitor()
    await integration_monitor.stop()
    await shadow_runner.stop()
    await fund_tracker.stop()
    await portal_price.stop()
    await observation.stop()
    await balance_service.stop()
    await collector.stop()
    from services.execution import wallet_observer as exec_observer
    await exec_observer.poller.stop()
    db.client.close()


app = FastAPI(title="ArbiCore", lifespan=lifespan)

docs_router = APIRouter(prefix="/api")


def load_manifest():
    with open(DOCS_DIR / 'manifest.json', 'r') as f:
        return json.load(f)


@docs_router.get("/")
async def root():
    return {"service": "ArbiCore", "phase": "Sprint 5 — Observation Phase", "status": "LIVE"}


@docs_router.get("/docs-package", dependencies=[Depends(require_auth)])
async def docs_package():
    manifest = load_manifest()
    return {
        "package": manifest["package"], "version": manifest["version"],
        "status": manifest["status"], "phase": manifest["phase"],
        "documents": [{"id": d["id"], "title": d["title"], "section": d["section"], "order": d["order"]}
                      for d in sorted(manifest["documents"], key=lambda x: x["order"])],
    }


@docs_router.get("/docs-package/{doc_id}", dependencies=[Depends(require_auth)])
async def doc_content(doc_id: str):
    manifest = load_manifest()
    entry = next((d for d in manifest["documents"] if d["id"] == doc_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Document not found")
    path = DOCS_DIR / entry["file"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document file missing")
    return {"id": entry["id"], "title": entry["title"], "section": entry["section"], "content": path.read_text()}



# ---- Public Quote Capture endpoint (header-key auth for cross-origin userscript) ----
from fastapi import Header
from services.execution import quote_capture as _qc
from pydantic import BaseModel as _BM


class _PublicQuoteIn(_BM):
    input_amount: float
    bdag_allocated: float
    input_token: str = "USDT"
    source: str = "userscript"
    raw: dict = None
    note: str = None


@docs_router.post("/public/quote-capture")
async def public_quote_capture(body: _PublicQuoteIn,
                               x_arbicore_quote_key: str = Header(None)):
    expected = os.environ.get("ARBICORE_QUOTE_CAPTURE_KEY", "")
    if not expected or x_arbicore_quote_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-ArbiCore-Quote-Key")
    try:
        return await _qc.record(input_amount=body.input_amount,
                                bdag_allocated=body.bdag_allocated,
                                input_token=body.input_token or "USDT",
                                source=body.source or "userscript",
                                raw=body.raw, note=body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@docs_router.get("/public/quote-capture/health")
async def public_quote_capture_health():
    """No-auth heartbeat so the userscript can verify connectivity."""
    return {"ok": True, "service": "arbicore-quote-capture", "fresh_window_s": _qc.FRESH_S}


@docs_router.post("/public/quote-capture-batch")
async def public_quote_capture_batch(body: dict,
                                     x_arbicore_quote_key: str = Header(None)):
    """Userscript v2 multi-size verified-quote batch ingestion."""
    expected = os.environ.get("ARBICORE_QUOTE_CAPTURE_KEY", "")
    if not expected or x_arbicore_quote_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-ArbiCore-Quote-Key")
    from services.execution import approval_workflow as _aw
    captures = body.get("captures") or []
    if not isinstance(captures, list) or not captures:
        raise HTTPException(status_code=400, detail="captures: non-empty list required")
    # Also feed each capture into the existing single-shot recorder so the
    # buy_price authority chain still sees the freshest quote (preserves the
    # established precedence).
    for c in captures:
        try:
            inp = float(c.get("size_usd"))
            bdag = float(c.get("bdag_quoted") or 0) or None
            if bdag and bdag > 0:
                await _qc.record(input_amount=inp, bdag_allocated=bdag,
                                 input_token="USDT", source=c.get("source") or "userscript_v2",
                                 raw=c.get("raw"), note=f"batch_size_{int(inp)}")
        except (TypeError, ValueError):
            continue
    return await _aw.consume_batch(captures)



app.include_router(docs_router)
app.include_router(auth_router)
app.include_router(vault_router)
app.include_router(alerts_router)
app.include_router(portfolio_router)
app.include_router(observation_router)
app.include_router(portal_router)
app.include_router(execution_router)
app.include_router(venues_router)
app.include_router(arbicore_router)
app.include_router(arbicore_scanners_router)
app.include_router(arbicore_opportunity_center_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
