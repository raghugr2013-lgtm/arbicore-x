from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


# ---------------------------------------------------------------------------
# UI v2 · Slice 0 preview endpoints (pod-local stubs that mirror the canonical
# shapes in app/backend/arbicore/routes/dashboard.py). Real implementation
# lives in the canonical repo; these stubs exist only so the Emergent preview
# renders the /v2 Home cards with realistic sample data.
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@api_router.get("/arbicore/dashboard/pulse")
async def v2_pulse() -> Dict[str, Any]:
    return {
        "regime": {
            "regime": "CALM",
            "tags": ["low_volatility"],
            "confidence": 0.82,
            "source": "preview-stub",
            "observed_at": _iso_now(),
        },
        "opportunity_vitals": {
            "total": 14,
            "by_family": {"CEX_ARBITRAGE": 6, "DEX_ARBITRAGE": 4, "FUNDING_ARBITRAGE": 3, "LAUNCH_ARBITRAGE": 1},
            "by_status": {"CANDIDATE": 12, "APPROVED": 2},
        },
        "route_learning": {"tracked_routes": 47},
        "scanner_status": {"endpoint": "/api/arbicore/scanners", "detail": "per-family scanner status"},
        "venue_readiness": {"endpoint": "/api/venues/status", "detail": "venue readiness registry"},
        "feed_freshness": {"endpoint": "/api/execution/portal/diagnostic", "detail": "portal feed freshness"},
        "interlock": {"endpoint": "/api/execution/interlock", "detail": "safety interlock status"},
        "deployable_capital": {"endpoint": "/api/portfolio/deployable", "detail": "deployable capital"},
        "anomalies": [],
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/dashboard/deck")
async def v2_deck(limit: int = 5) -> Dict[str, Any]:
    fresh = [
        {"id": "opp-001", "opportunity_type": "CEX_ARBITRAGE", "subject_id": "ETH-USDT",
         "chain": "ethereum", "confidence": 0.87, "status": "CANDIDATE", "created_at": _iso_now()},
        {"id": "opp-002", "opportunity_type": "DEX_ARBITRAGE", "subject_id": "WETH/USDC",
         "chain": "arbitrum", "confidence": 0.79, "status": "CANDIDATE", "created_at": _iso_now()},
        {"id": "opp-003", "opportunity_type": "FUNDING_ARBITRAGE", "subject_id": "SOL-PERP",
         "chain": "solana", "confidence": 0.71, "status": "CANDIDATE", "created_at": _iso_now()},
        {"id": "opp-004", "opportunity_type": "CEX_ARBITRAGE", "subject_id": "BTC-USDT",
         "chain": "bitcoin", "confidence": 0.65, "status": "CANDIDATE", "created_at": _iso_now()},
        {"id": "opp-005", "opportunity_type": "LAUNCH_ARBITRAGE", "subject_id": "NEW-TOKEN",
         "chain": "solana", "confidence": 0.58, "status": "CANDIDATE", "created_at": _iso_now()},
    ][:max(1, min(limit, 20))]
    return {
        "pending_approvals": [],
        "pending_approvals_total": 0,
        "fresh_opportunities": fresh,
        "fresh_opportunities_total": len(fresh),
        "requires_attention": [],
        "requires_attention_total": 0,
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/opportunities/summary")
async def v2_opportunities_summary(window_hours: int = 24, max_scan: int = 1000) -> Dict[str, Any]:
    return {
        "total": 14,
        "by_family": {"CEX_ARBITRAGE": 6, "DEX_ARBITRAGE": 4, "FUNDING_ARBITRAGE": 3, "LAUNCH_ARBITRAGE": 1},
        "by_chain": {"ethereum": 5, "arbitrum": 3, "solana": 4, "bitcoin": 2},
        "by_status": {"CANDIDATE": 12, "APPROVED": 2},
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/roi-probability")
async def v2_roi_probability(route_id: str) -> Dict[str, Any]:
    return {
        "route_id": route_id,
        "sample_size": 42,
        "win_rate": 0.643,
        "realized_outcome_mean": 0.012,
        "realized_outcome_sum": 0.517,
        "last_outcome_at": _iso_now(),
        "generated_at": _iso_now(),
    }


@api_router.get("/system/status")
async def v2_system_status() -> Dict[str, Any]:
    return {
        "features": {"ui_v2": True},
        "preview": True,
        "generated_at": _iso_now(),
    }

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()