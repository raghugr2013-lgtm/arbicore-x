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


# ---------------------------------------------------------------------------
# UI v2 · Slice 1 preview endpoints — universal opportunity feed + detail.
# Pod-local stubs; canonical implementation lives in arbicore/routes/*.
# ---------------------------------------------------------------------------

_V2_OPPS = [
    {"id": "opp-001", "opportunity_type": "CEX_ARBITRAGE", "subject_id": "ETH-USDT",
     "chain": "ethereum", "confidence": 0.87, "safety": 0.94, "status": "CANDIDATE",
     "verdict": "GO", "route": "binance:ETH-USDT → kucoin:ETH-USDT",
     "spread_bps": 18.4, "depth_usd": 4_200_000, "return_low": 0.0035, "return_high": 0.0062,
     "created_at": None, "age_s": 4},
    {"id": "opp-002", "opportunity_type": "DEX_ARBITRAGE", "subject_id": "WETH/USDC",
     "chain": "arbitrum", "confidence": 0.79, "safety": 0.88, "status": "CANDIDATE",
     "verdict": "GO", "route": "uniswap-v3:WETH/USDC → sushiswap:WETH/USDC",
     "spread_bps": 12.4, "depth_usd": 1_800_000, "return_low": 0.0028, "return_high": 0.0051,
     "created_at": None, "age_s": 8},
    {"id": "opp-003", "opportunity_type": "FUNDING_ARBITRAGE", "subject_id": "SOL-PERP",
     "chain": "solana", "confidence": 0.71, "safety": 0.82, "status": "CANDIDATE",
     "verdict": "SOFT_NO", "route": "bybit:SOL-PERP short + spot long",
     "spread_bps": 8.1, "depth_usd": 900_000, "return_low": 0.0018, "return_high": 0.0037,
     "created_at": None, "age_s": 22},
    {"id": "opp-004", "opportunity_type": "CEX_ARBITRAGE", "subject_id": "BTC-USDT",
     "chain": "bitcoin", "confidence": 0.65, "safety": 0.91, "status": "CANDIDATE",
     "verdict": "GO", "route": "binance:BTC-USDT → okx:BTC-USDT",
     "spread_bps": 6.2, "depth_usd": 12_500_000, "return_low": 0.0014, "return_high": 0.0028,
     "created_at": None, "age_s": 31},
    {"id": "opp-005", "opportunity_type": "LAUNCH_ARBITRAGE", "subject_id": "NEW-TOKEN",
     "chain": "solana", "confidence": 0.58, "safety": 0.60, "status": "CANDIDATE",
     "verdict": "SOFT_NO", "route": "raydium:NEW → jupiter:NEW",
     "spread_bps": 24.0, "depth_usd": 120_000, "return_low": 0.0041, "return_high": 0.0091,
     "created_at": None, "age_s": 45},
    {"id": "opp-006", "opportunity_type": "CROSS_CHAIN_ARBITRAGE", "subject_id": "USDC",
     "chain": "ethereum→arbitrum", "confidence": 0.74, "safety": 0.86, "status": "CANDIDATE",
     "verdict": "GO", "route": "eth:USDC → arb:USDC (stargate)",
     "spread_bps": 4.1, "depth_usd": 3_400_000, "return_low": 0.0009, "return_high": 0.0021,
     "created_at": None, "age_s": 58},
    {"id": "opp-007", "opportunity_type": "FLASH_LOAN_ARBITRAGE", "subject_id": "MATIC/USDC",
     "chain": "polygon", "confidence": 0.61, "safety": 0.72, "status": "APPROVED",
     "verdict": "GO", "route": "aave-flash → quickswap → sushiswap → aave-repay",
     "spread_bps": 14.8, "depth_usd": 780_000, "return_low": 0.0026, "return_high": 0.0058,
     "created_at": None, "age_s": 118},
    {"id": "opp-008", "opportunity_type": "DEX_ARBITRAGE", "subject_id": "WETH/USDT",
     "chain": "base", "confidence": 0.42, "safety": 0.55, "status": "CANDIDATE",
     "verdict": "HARD_NO", "route": "uniswap-v3:WETH/USDT (safety gate failed)",
     "spread_bps": 3.1, "depth_usd": 240_000, "return_low": 0.0007, "return_high": 0.0018,
     "created_at": None, "age_s": 210},
]


def _hydrate_opps():
    now = _iso_now()
    for o in _V2_OPPS:
        if o["created_at"] is None:
            o["created_at"] = now
    return _V2_OPPS


@api_router.get("/arbicore/opportunities")
async def v2_opportunities_list(
    family: Optional[str] = None,
    chain: Optional[str] = None,
    verdict: Optional[str] = None,
    min_confidence: float = 0.0,
    limit: int = 100,
) -> Dict[str, Any]:
    items = _hydrate_opps()
    out = []
    for o in items:
        if family and family != "ALL" and o["opportunity_type"] != family:
            continue
        if chain and chain != "ALL" and o["chain"] != chain:
            continue
        if verdict and verdict != "ALL" and o["verdict"] != verdict:
            continue
        if o["confidence"] < min_confidence:
            continue
        out.append(o)
    return {"items": out[:limit], "total": len(out), "generated_at": _iso_now()}


@api_router.get("/arbicore/opportunities/{opp_id}")
async def v2_opportunity_detail(opp_id: str) -> Dict[str, Any]:
    items = _hydrate_opps()
    match = next((o for o in items if o["id"] == opp_id), None)
    if not match:
        return {"error": "not_found", "id": opp_id}
    return {
        **match,
        "reasoning": {
            "confidence_breakdown": [
                {"factor": "Regime (CALM)", "delta": +4, "notes": "Low volatility supports the route."},
                {"factor": "Route historical win-rate", "delta": +6, "notes": "42 trials, 64% win rate."},
                {"factor": "Freshness", "delta": +2, "notes": f"Quote {match['age_s']}s old."},
                {"factor": "Depth", "delta": +3, "notes": f"${match['depth_usd']:,} available."},
                {"factor": "Safety score", "delta": -1 if match["safety"] < 0.8 else +2,
                 "notes": f"Safety = {int(match['safety']*100)}."},
            ],
            "gates_passed": ["spread_min", "depth_min", "freshness_max", "safety_min"] if match["verdict"] != "HARD_NO" else ["spread_min"],
            "gates_dropped": [] if match["verdict"] == "GO" else ["safety_min"],
        },
        "verification": {
            "quote_source": "userscript_v2" if match["opportunity_type"].startswith("CEX") else "on_chain_rpc",
            "last_verified_at": _iso_now(),
            "fresh_window_s": 15,
            "stale": match["age_s"] > 15,
        },
        "quote": {
            "buy_venue": match["route"].split("→")[0].strip() if "→" in match["route"] else match["route"],
            "sell_venue": match["route"].split("→")[-1].strip() if "→" in match["route"] else "-",
            "buy_price": 3421.55,
            "sell_price": 3428.10,
            "size_usd": 25_000,
            "estimated_gas_usd": 4.20 if match["chain"] != "bitcoin" else 0,
        },
        "sizing": {
            "recommended_usd": min(match["depth_usd"] * 0.05, 50_000),
            "max_usd": min(match["depth_usd"] * 0.10, 100_000),
            "min_usd": 1_000,
        },
        "evidence": {
            "cycle_id": None,
            "download_endpoint": f"/api/arbicore/opportunities/{opp_id}/evidence",
            "attachments": [],
        },
    }


@api_router.post("/arbicore/opportunities/{opp_id}/approve")
async def v2_opportunity_approve(opp_id: str) -> Dict[str, Any]:
    items = _hydrate_opps()
    match = next((o for o in items if o["id"] == opp_id), None)
    if match:
        match["status"] = "APPROVED"
    return {"ok": True, "id": opp_id, "status": "APPROVED", "generated_at": _iso_now()}


@api_router.post("/arbicore/opportunities/{opp_id}/reject")
async def v2_opportunity_reject(opp_id: str) -> Dict[str, Any]:
    items = _hydrate_opps()
    match = next((o for o in items if o["id"] == opp_id), None)
    if match:
        match["status"] = "REJECTED"
    return {"ok": True, "id": opp_id, "status": "REJECTED", "generated_at": _iso_now()}


# ---------------------------------------------------------------------------
# UI v2 · Slice 2 preview endpoints — Discovery + Intelligence.
# Pod-local stubs; canonical implementations added in
# app/backend/arbicore/routes/dashboard.py alongside Slice 1.
# ---------------------------------------------------------------------------

_V2_DISCOVERY = [
    {"id": "cand-001", "asset": "PENDLE", "kind": "asset", "chain": "ethereum",
     "source": "twitter:@messaricrypto", "score": 0.82, "status": "NEW",
     "why": "Repeated mention across 4 curated sources in last 48h.",
     "signals": ["mention_burst", "unusual_volume", "narrative:LRT"], "seen_at": None},
    {"id": "cand-002", "asset": "TIA", "kind": "asset", "chain": "celestia",
     "source": "coingecko:trending", "score": 0.71, "status": "NEW",
     "why": "Trending +38% pageviews, whale accumulation on Osmosis.",
     "signals": ["trending", "whale_accumulation"], "seen_at": None},
    {"id": "cand-003", "asset": "kucoin:MOODENG-USDT", "kind": "venue_pair", "chain": "kucoin",
     "source": "listings:new", "score": 0.64, "status": "WATCHING",
     "why": "New CEX listing pair, high early spread.",
     "signals": ["new_listing", "spread_open"], "seen_at": None},
    {"id": "cand-004", "asset": "berachain", "kind": "chain", "chain": "berachain",
     "source": "github:activity", "score": 0.58, "status": "NEW",
     "why": "Mainnet imminent; RPC endpoints reachable.",
     "signals": ["mainnet_soon", "rpc_up"], "seen_at": None},
    {"id": "cand-005", "asset": "ORDI", "kind": "asset", "chain": "bitcoin",
     "source": "twitter:@onchainedge", "score": 0.44, "status": "DISMISSED",
     "why": "Dismissed 6d ago — low liquidity across venues.",
     "signals": ["low_liquidity"], "seen_at": None},
    {"id": "cand-006", "asset": "sushiswap:WETH-USDT (base)", "kind": "venue_pair", "chain": "base",
     "source": "onchain:pool_scan", "score": 0.69, "status": "NEW",
     "why": "New Sushi pool with $3.2M TVL on Base.",
     "signals": ["new_pool", "tvl_ok"], "seen_at": None},
    {"id": "cand-007", "asset": "hyperliquid:BTC-PERP", "kind": "venue_pair", "chain": "hyperliquid",
     "source": "funding:screener", "score": 0.77, "status": "PROMOTED",
     "why": "Extreme funding rate divergence vs Binance funding.",
     "signals": ["funding_divergence"], "seen_at": None},
]


def _hydrate_discovery():
    now = _iso_now()
    for c in _V2_DISCOVERY:
        if c["seen_at"] is None:
            c["seen_at"] = now
    return _V2_DISCOVERY


@api_router.get("/arbicore/discovery/candidates")
async def v2_discovery_candidates(status: Optional[str] = None, kind: Optional[str] = None,
                                   min_score: float = 0.0, limit: int = 100) -> Dict[str, Any]:
    items = _hydrate_discovery()
    out = []
    for c in items:
        if status and status != "ALL" and c["status"] != status:
            continue
        if kind and kind != "ALL" and c["kind"] != kind:
            continue
        if c["score"] < min_score:
            continue
        out.append(c)
    stats = {
        "total": len(items),
        "new": sum(1 for c in items if c["status"] == "NEW"),
        "watching": sum(1 for c in items if c["status"] == "WATCHING"),
        "promoted": sum(1 for c in items if c["status"] == "PROMOTED"),
        "dismissed": sum(1 for c in items if c["status"] == "DISMISSED"),
    }
    return {"items": out[:limit], "total": len(out), "stats": stats, "generated_at": _iso_now()}


@api_router.post("/arbicore/discovery/candidates/{cand_id}/action")
async def v2_discovery_action(cand_id: str, action: str) -> Dict[str, Any]:
    items = _hydrate_discovery()
    match = next((c for c in items if c["id"] == cand_id), None)
    if match:
        mapping = {"watch": "WATCHING", "promote": "PROMOTED", "dismiss": "DISMISSED", "reset": "NEW"}
        match["status"] = mapping.get(action.lower(), match["status"])
    return {"ok": True, "id": cand_id, "status": match["status"] if match else None, "generated_at": _iso_now()}


@api_router.get("/arbicore/intelligence/recommendations")
async def v2_recommendations() -> Dict[str, Any]:
    return {
        "top_routes": [
            {"route": "binance:ETH-USDT → kucoin:ETH-USDT", "win_rate": 0.68, "trials": 128, "mean_roi": 0.0031},
            {"route": "uniswap-v3:WETH/USDC → sushiswap:WETH/USDC", "win_rate": 0.61, "trials": 89, "mean_roi": 0.0022},
            {"route": "binance:BTC-USDT → okx:BTC-USDT", "win_rate": 0.72, "trials": 214, "mean_roi": 0.0018},
            {"route": "bybit:SOL-PERP short + spot long", "win_rate": 0.54, "trials": 46, "mean_roi": 0.0014},
            {"route": "aave-flash → quickswap → sushiswap (MATIC)", "win_rate": 0.49, "trials": 22, "mean_roi": 0.0026},
        ],
        "top_chains": [
            {"chain": "ethereum", "opps_24h": 41, "avg_confidence": 0.73, "avg_safety": 0.86},
            {"chain": "arbitrum", "opps_24h": 32, "avg_confidence": 0.68, "avg_safety": 0.82},
            {"chain": "solana", "opps_24h": 27, "avg_confidence": 0.61, "avg_safety": 0.71},
            {"chain": "base", "opps_24h": 18, "avg_confidence": 0.65, "avg_safety": 0.79},
        ],
        "top_entities": [
            {"entity": "binance", "kind": "venue", "score": 0.91},
            {"entity": "uniswap-v3", "kind": "venue", "score": 0.87},
            {"entity": "ETH-USDT", "kind": "market", "score": 0.83},
            {"entity": "WETH/USDC", "kind": "market", "score": 0.78},
        ],
        "generated_at": _iso_now(),
    }


@api_router.get("/arbicore/intelligence/decisions")
async def v2_decisions(verdict: Optional[str] = None, family: Optional[str] = None,
                        min_confidence: float = 0.0, limit: int = 100) -> Dict[str, Any]:
    log = [
        {"id": "dec-001", "opp_id": "opp-001", "asset": "ETH-USDT", "family": "CEX_ARBITRAGE",
         "verdict": "GO", "confidence": 0.87, "regime": "CALM",
         "top_factors": ["+6 route history", "+4 regime CALM", "+3 depth"],
         "at": _iso_now()},
        {"id": "dec-002", "opp_id": "opp-002", "asset": "WETH/USDC", "family": "DEX_ARBITRAGE",
         "verdict": "GO", "confidence": 0.79, "regime": "CALM",
         "top_factors": ["+5 route history", "+3 regime CALM", "-1 gas volatility"],
         "at": _iso_now()},
        {"id": "dec-003", "opp_id": "opp-003", "asset": "SOL-PERP", "family": "FUNDING_ARBITRAGE",
         "verdict": "SOFT_NO", "confidence": 0.71, "regime": "CALM",
         "top_factors": ["-3 safety (venue drift)", "+2 spread", "-1 funding vol"],
         "at": _iso_now()},
        {"id": "dec-004", "opp_id": "opp-008", "asset": "WETH/USDT (base)", "family": "DEX_ARBITRAGE",
         "verdict": "HARD_NO", "confidence": 0.42, "regime": "CALM",
         "top_factors": ["-6 safety_min gate", "-3 depth_min gate"],
         "at": _iso_now()},
        {"id": "dec-005", "opp_id": "opp-004", "asset": "BTC-USDT", "family": "CEX_ARBITRAGE",
         "verdict": "GO", "confidence": 0.65, "regime": "CALM",
         "top_factors": ["+4 route history", "+2 depth", "-2 fresh window"],
         "at": _iso_now()},
        {"id": "dec-006", "opp_id": "opp-007", "asset": "MATIC/USDC", "family": "FLASH_LOAN_ARBITRAGE",
         "verdict": "GO", "confidence": 0.61, "regime": "CALM",
         "top_factors": ["+3 flash-fee coverage", "+2 route history"],
         "at": _iso_now()},
    ]
    out = []
    for d in log:
        if verdict and verdict != "ALL" and d["verdict"] != verdict:
            continue
        if family and family != "ALL" and d["family"] != family:
            continue
        if d["confidence"] < min_confidence:
            continue
        out.append(d)
    return {"items": out[:limit], "total": len(out), "generated_at": _iso_now()}

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