from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import registry
from core.errors import ConnectorError, SymbolNotListed
from core.models import DEFAULT_RISK_PROFILE, DEFAULT_SIM_CONFIG, new_id, now_iso
from engines.economics import episodes as _episodes, final_episode as _final_episode, \
    summary as _econ_summary
from services import db, discovery
from services.auth import require_auth
from services.collector import collector
from services.portal_price import portal_price
from services.ws_manager import ws_manager

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

POSITION_STATUSES = ["BOUGHT", "IN_WALLET", "TRANSFERRING", "ON_EXCHANGE", "SOLD", "SETTLED"]


def _age_s(ts_iso):
    if not ts_iso:
        return None
    try:
        return round((datetime.now(timezone.utc) - datetime.fromisoformat(ts_iso)).total_seconds(), 1)
    except ValueError:
        return None


# ---------------- connectors ----------------

@router.get("/connectors")
async def list_connectors():
    return {"exchanges": registry.available(),
            "wallets": [{"key": "evm_watch", "name": "EVM Watch-Only", "kind": "wallet",
                         "capabilities": {"watch_only": True, "private_keys": "never"}}]}


# ---------------- routes ----------------

class RouteCreate(BaseModel):
    name: str
    exit_exchange: str = "xt"
    base: str = "BDAG"
    quote: str = "USDT"
    asset_network: str = "BLOCKDAG"
    funding_coin: str = "BNB"
    funding_network: str = "BSC"
    mode: str = "live"


@router.get("/routes")
async def list_routes():
    return await db.routes_col.find({}, {"_id": 0}).to_list(50)


@router.post("/routes")
async def create_route(body: RouteCreate):
    route = {
        "id": new_id(), "name": body.name, "active": True, "mode": body.mode,
        "funding": {"coin": body.funding_coin, "network": body.funding_network},
        "purchase": {"asset": body.base, "network": body.asset_network, "venue": "manual"},
        "wallet": {"connector": "evm_watch", "address": "", "label": ""},
        "exit": {"exchange": body.exit_exchange, "base": body.base, "quote": body.quote},
        "comparison_exchanges": ["xt", "mexc", "gate", "bitmart"],
        "settlement": {"coin": body.funding_coin, "network": body.funding_network,
                       "conversion_path": [f"{body.quote}/{body.funding_coin}"]},
        "manual_buy": {"price": None, "qty": None},
        "risk_profile": DEFAULT_RISK_PROFILE,
        "sim_config": DEFAULT_SIM_CONFIG,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.routes_col.insert_one(dict(route))
    await collector.reload_route(route["id"])
    route.pop("_id", None)
    return route


@router.get("/routes/{route_id}")
async def get_route(route_id: str):
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(404, "Route not found")
    return route


@router.patch("/routes/{route_id}")
async def patch_route(route_id: str, body: dict):
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(404, "Route not found")
    allowed_top = {"name", "mode", "active", "comparison_exchanges", "wallet"}
    allowed_merge = {"manual_buy", "risk_profile", "sim_config", "exit", "funding", "settlement", "purchase"}
    updates = {}
    for k, v in body.items():
        if k in allowed_top:
            updates[k] = v
        elif k in allowed_merge and isinstance(v, dict):
            updates[k] = {**route.get(k, {}), **v}
    if not updates:
        raise HTTPException(400, "No valid fields to update")
    updates["updated_at"] = now_iso()
    await db.routes_col.update_one({"id": route_id}, {"$set": updates})
    needs_reload = any(k in body for k in ("mode", "exit", "comparison_exchanges", "active", "sim_config"))
    if needs_reload:
        await collector.reload_route(route_id)
    return await db.routes_col.find_one({"id": route_id}, {"_id": 0})


# ---------------- dashboard aggregate ----------------

@router.get("/routes/{route_id}/snapshot")
async def route_snapshot(route_id: str):
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(404, "Route not found")
    rcache = collector.cache.get(route_id, {})
    primary = route["exit"]["exchange"]
    buy_price = (route.get("manual_buy") or {}).get("price")

    evaluation = rcache.get("_evaluation")
    if evaluation and evaluation.get("inputs", {}).get("buy_price"):
        buy_price = evaluation["inputs"]["buy_price"]

    comparison = []
    for ex in route.get("comparison_exchanges", []):
        e = rcache.get(ex, {})
        t = e.get("ticker")
        fee = e.get("fee")
        comp = {
            "exchange": ex,
            "primary": ex == primary,
            "listed": e.get("listed"),
            "last": t.get("last") if t else None,
            "bid": t.get("bid") if t else None,
            "ask": t.get("ask") if t else None,
            "volume_24h_quote": t.get("volume_24h_quote") if t else None,
            "ticker_age_s": _age_s(t.get("ts")) if t else None,
            "gross_spread_pct": ((t["last"] - buy_price) / buy_price * 100)
            if (t and buy_price) else None,
            "deposit_enabled": fee.get("deposit_enabled") if fee else None,
            "withdraw_enabled": fee.get("withdraw_enabled") if fee else None,
            "source": t.get("source") if t else None,
            "error": e.get("last_error"),
        }
        comparison.append(comp)

    ob = rcache.get(primary, {}).get("orderbook")
    orderbook = None
    if ob:
        orderbook = {"exchange": primary, "bids": ob["bids"][:15], "asks": ob["asks"][:15],
                     "ts": ob["ts"], "age_s": _age_s(ob["ts"]), "source": ob.get("source")}

    history = await db.evaluations.find(
        {"route_id": route_id}, {"_id": 0, "ts": 1, "spread.net_pct": 1, "spread.gross_pct": 1,
                                 "scores.overall": 1, "verdict": 1},
        sort=[("ts", -1)], limit=72).to_list(72)
    history.reverse()

    exchanges_status = {}
    for ex in route.get("comparison_exchanges", []):
        e = rcache.get(ex, {})
        t, o = e.get("ticker"), e.get("orderbook")
        exchanges_status[ex] = {
            "listed": e.get("listed"),
            "ticker_age_s": _age_s(t.get("ts")) if t else None,
            "depth_age_s": _age_s(o.get("ts")) if o else None,
            "last_error": e.get("last_error"),
        }

    return {
        "route": route,
        "evaluation": evaluation,
        "comparison": comparison,
        "orderbook": orderbook,
        "portal_price": portal_price.status_brief(),
        "spread_history": [
            {"ts": h["ts"], "net_pct": h.get("spread", {}).get("net_pct"),
             "gross_pct": h.get("spread", {}).get("gross_pct"),
             "overall": h.get("scores", {}).get("overall"), "verdict": h.get("verdict")}
            for h in history],
        "system": {
            "exchanges": exchanges_status,
            "networks": collector.network_health,
            "websockets": ws_manager.status(),
            "events": list(collector.events)[:40],
            "mode": route.get("mode"),
        },
    }


@router.get("/routes/{route_id}/evaluations")
async def route_evaluations(route_id: str, limit: int = 50):
    return await db.evaluations.find({"route_id": route_id}, {"_id": 0},
                                     sort=[("ts", -1)], limit=min(limit, 200)).to_list(min(limit, 200))


# ---------------- Opportunity Replay Engine ----------------

@router.get("/routes/{route_id}/replay")
async def replay(route_id: str, hours: float = 24):
    """Historical route validation: replays stored evaluations over a window."""
    hours = max(0.5, min(hours, 72))
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(404, "Route not found")
    cutoff = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - hours * 3600, tz=timezone.utc).isoformat()
    docs = await db.evaluations.find(
        {"route_id": route_id, "ts": {"$gte": cutoff}},
        {"_id": 0, "ts": 1, "verdict": 1, "exchange": 1, "spread.net_pct": 1,
         "scores.overall": 1, "gates.id": 1, "gates.passed": 1},
    ).sort("ts", 1).to_list(30000)

    counts = {"GO": 0, "WAIT": 0, "NO_GO": 0}
    gate_failures = {}
    nets, overalls = [], []
    blocked = 0
    min_net = route.get("risk_profile", {}).get("min_net_spread_pct", 2.0)
    for d in docs:
        counts[d["verdict"]] = counts.get(d["verdict"], 0) + 1
        failed = [g["id"] for g in d.get("gates", []) if not g["passed"]]
        for g in failed:
            gate_failures[g] = gate_failures.get(g, 0) + 1
        net = (d.get("spread") or {}).get("net_pct")
        if net is not None:
            nets.append(net)
        ov = (d.get("scores") or {}).get("overall")
        if ov is not None:
            overalls.append(ov)
        if failed == ["G1_DEPOSIT"] and net is not None and net >= min_net:
            blocked += 1

    total = len(docs)
    n_buckets = 96
    timeline = []
    if total:
        step = max(total // n_buckets, 1)
        for i in range(0, total, step):
            chunk = docs[i:i + step]
            cn = [c.get("spread", {}).get("net_pct") for c in chunk if c.get("spread", {}).get("net_pct") is not None]
            co = [c.get("scores", {}).get("overall") for c in chunk if c.get("scores", {}).get("overall") is not None]
            timeline.append({
                "ts": chunk[-1]["ts"], "verdict": chunk[-1]["verdict"],
                "net_pct": round(sum(cn) / len(cn), 3) if cn else None,
                "overall": round(sum(co) / len(co), 1) if co else None,
            })

    def stats(vals):
        return {"min": round(min(vals), 3), "max": round(max(vals), 3),
                "avg": round(sum(vals) / len(vals), 3), "last": round(vals[-1], 3)} if vals else None

    return {
        "route_id": route_id, "hours": hours, "evaluations_count": total,
        "verdict_counts": counts,
        "verdict_pct": {k: round(v / total * 100, 1) if total else 0 for k, v in counts.items()},
        "net_spread": stats(nets), "overall_score": stats(overalls),
        "gate_failures": gate_failures,
        "blocked_opportunity": {
            "evaluations": blocked,
            "approx_minutes": round(blocked * 10 / 60, 1),
            "note": f"windows where ONLY the deposit gate blocked a net spread ≥ {min_net}% (10s eval cadence)",
        },
        "timeline": timeline,
    }


# ---------------- Opportunity Economics (Sprint 3; primitives in engines/economics.py) ----------------

@router.get("/routes/{route_id}/economics")
async def economics(route_id: str, hours: float = 24):
    """Raw spread opportunities (spread-only) vs executable ones (all gates pass)."""
    hours = max(0.5, min(hours, 72))
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(404, "Route not found")
    min_net = route.get("risk_profile", {}).get("min_net_spread_pct", 2.0)
    cutoff = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - hours * 3600, tz=timezone.utc).isoformat()
    docs = await db.evaluations.find(
        {"route_id": route_id, "ts": {"$gte": cutoff}, "mode": route.get("mode", "live")},
        {"_id": 0, "ts": 1, "verdict": 1, "spread.net_pct": 1, "capacity.recommended": 1,
         "inputs.buy_price": 1, "gates.id": 1, "gates.passed": 1},
    ).sort("ts", 1).to_list(30000)

    raw_eps = [_final_episode(e) for e in _episodes(
        docs, lambda d: (d.get("spread") or {}).get("net_pct") is not None
        and d["spread"]["net_pct"] >= min_net)]
    exec_eps = [_final_episode(e) for e in _episodes(docs, lambda d: d.get("verdict") == "GO")]

    raw_sum = _econ_summary(raw_eps)
    exec_sum = _econ_summary(exec_eps)

    gate_blockage = {}
    for e in raw_eps:
        if e["had_go"]:
            continue
        for g, c in e["gate_fails"].items():
            gate_blockage[g] = round(gate_blockage.get(g, 0) + c * 10 / 60, 1)

    capture = None
    if raw_sum["total_minutes"]:
        capture = round(exec_sum["total_minutes"] / raw_sum["total_minutes"] * 100, 1)

    recent = [{k: e[k] for k in ("start", "end", "duration_min", "avg_net_pct", "peak_net_pct",
                                 "avg_recommended", "est_profit_quote", "had_go")}
              for e in raw_eps[-12:]][::-1]

    return {"route_id": route_id, "hours": hours, "evaluations": len(docs),
            "min_net_spread_pct": min_net, "raw": raw_sum, "executable": exec_sum,
            "capture_ratio_pct": capture, "gate_blockage": gate_blockage,
            "recent_episodes": recent}


# ---------------- Capability Registry (Sprint 3) ----------------

@router.get("/capabilities")
async def capabilities(currency: Optional[str] = None):
    q = {"currency": currency.upper()} if currency else {}
    return await db.capabilities_col.find(q, {"_id": 0}).sort("exchange", 1).to_list(100)


@router.get("/capabilities/history")
async def capabilities_history(exchange: Optional[str] = None, limit: int = 50):
    q = {"exchange": exchange} if exchange else {}
    return await db.capability_history.find(q, {"_id": 0}, sort=[("ts", -1)]).to_list(min(limit, 200))


# ---------------- Treasury ----------------

_conv_cache = {}


async def _conversion_rate(coin: str, quote: str = "USDT"):
    import time as _t
    key = f"{coin}/{quote}"
    hit = _conv_cache.get(key)
    if hit and _t.time() - hit[1] < 60:
        return hit[0]
    for ex in ("gate", "mexc", "xt"):
        try:
            t = await registry.resolve(ex, "live").get_ticker(coin, quote)
            _conv_cache[key] = (t.last, _t.time())
            return t.last
        except (SymbolNotListed, ConnectorError, KeyError, Exception):
            continue
    return None


@router.get("/treasury/{route_id}")
async def treasury(route_id: str):
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(404, "Route not found")
    ledger = await db.treasury_col.find({"route_id": route_id}, {"_id": 0},
                                        sort=[("ts", -1)]).to_list(200)
    positions = await db.positions_col.find({"route_id": route_id}, {"_id": 0}).to_list(200)

    cost = sum(p["buy_price"] * p["qty"] for p in positions)
    proceeds = sum((p.get("sell") or {}).get("proceeds_quote") or 0 for p in positions)
    realized = sum(p.get("realized_pnl_quote") or 0 for p in positions)
    open_pos = [p for p in positions if p["status"] not in ("SOLD", "SETTLED")]
    open_qty = sum(p["qty"] for p in open_pos)
    open_cost = sum(p["buy_price"] * p["qty"] for p in open_pos)
    primary = route["exit"]["exchange"]
    ob = collector.cache.get(route_id, {}).get(primary, {}).get("orderbook")
    best_bid = ob["bids"][0][0] if ob and ob.get("bids") else None
    open_value = open_qty * best_bid if best_bid else None

    settle_coin = route["settlement"]["coin"]
    rate = await _conversion_rate(settle_coin)
    taker = 0.2
    fixed = route.get("risk_profile", {}).get("fixed_fees_quote", 1.0)
    unsettled_proceeds = sum((p.get("sell") or {}).get("proceeds_quote") or 0
                             for p in positions if p["status"] == "SOLD")
    conversion = {
        "pair": f"{settle_coin}/USDT", "rate": rate, "taker_fee_pct": taker,
        "est_fixed_fee_quote": fixed,
        "unsettled_proceeds_quote": unsettled_proceeds,
        "est_settlement_amount": round((unsettled_proceeds * (1 - taker / 100) - fixed) / rate, 6)
        if (rate and unsettled_proceeds > fixed) else None,
        "path": route["settlement"].get("conversion_path"),
    }
    return {
        "summary": {
            "cost_quote": round(cost, 2), "proceeds_quote": round(proceeds, 2),
            "realized_pnl_quote": round(realized, 2),
            "open_qty": open_qty, "open_cost_quote": round(open_cost, 2),
            "open_value_quote": round(open_value, 2) if open_value is not None else None,
            "unrealized_pnl_quote": round(open_value - open_cost, 2) if open_value is not None else None,
            "positions": len(positions), "open_positions": len(open_pos),
        },
        "funding": route["funding"], "settlement": route["settlement"],
        "conversion": conversion,
        "ledger": ledger,
    }


# ---------------- Exchange Discovery Service ----------------

@router.post("/discovery/scan")
async def discovery_scan(asset: str = "BDAG", quote: str = "USDT"):
    return await discovery.scan(asset, quote, emit=collector.event)


@router.get("/discovery/latest")
async def discovery_latest(asset: str = "BDAG"):
    doc = await db.discoveries_col.find_one({"asset": asset}, {"_id": 0}, sort=[("ts", -1)])
    if not doc:
        return {"asset": asset, "ts": None, "venues": [], "sources": {}, "new_findings": [],
                "note": "no scan yet — POST /api/discovery/scan to run one"}
    return doc


# ---------------- positions ----------------

class PositionCreate(BaseModel):
    route_id: str
    buy_price: float
    qty: float
    funding_cost: Optional[dict] = None
    tx_hash: Optional[str] = None
    notes: Optional[str] = None


@router.get("/positions")
async def list_positions(route_id: Optional[str] = None):
    q = {"route_id": route_id} if route_id else {}
    return await db.positions_col.find(q, {"_id": 0}, sort=[("created_at", -1)]).to_list(100)


@router.post("/positions")
async def create_position(body: PositionCreate):
    if body.buy_price <= 0 or body.qty <= 0:
        raise HTTPException(400, "buy_price and qty must be positive")
    pos = {
        "id": new_id(), "route_id": body.route_id, "status": "BOUGHT",
        "buy_price": body.buy_price, "qty": body.qty,
        "funding_cost": body.funding_cost, "tx_hash": body.tx_hash, "notes": body.notes,
        "bought_at": now_iso(), "sell": None, "settlement": None, "realized_pnl_quote": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.positions_col.insert_one(dict(pos))
    await db.treasury_col.insert_one({
        "id": new_id(), "route_id": body.route_id, "position_id": pos["id"], "ts": now_iso(),
        "leg": "purchase", "asset": "asset", "qty": body.qty,
        "quote_value": round(body.buy_price * body.qty, 2),
        "notes": "manual buy recorded",
    })
    await collector.event("info", "position", f"Manual buy recorded: {body.qty:,.0f} @ {body.buy_price}",
                          route_id=body.route_id)
    pos.pop("_id", None)
    return pos


@router.patch("/positions/{position_id}")
async def patch_position(position_id: str, body: dict):
    pos = await db.positions_col.find_one({"id": position_id}, {"_id": 0})
    if not pos:
        raise HTTPException(404, "Position not found")
    updates = {}
    if "status" in body:
        if body["status"] not in POSITION_STATUSES:
            raise HTTPException(400, f"Invalid status; allowed: {POSITION_STATUSES}")
        updates["status"] = body["status"]
    for k in ("sell", "settlement", "notes", "tx_hash"):
        if k in body:
            updates[k] = body[k]
    sell = updates.get("sell", pos.get("sell"))
    if sell and sell.get("proceeds_quote") is not None:
        updates["realized_pnl_quote"] = sell["proceeds_quote"] - pos["buy_price"] * pos["qty"]
    updates["updated_at"] = now_iso()
    await db.positions_col.update_one({"id": position_id}, {"$set": updates})
    new_status = updates.get("status")
    if new_status == "SOLD" and sell:
        await db.treasury_col.insert_one({
            "id": new_id(), "route_id": pos["route_id"], "position_id": position_id, "ts": now_iso(),
            "leg": "sell", "asset": "asset", "qty": sell.get("qty", pos["qty"]),
            "quote_value": round(sell.get("proceeds_quote", 0), 2),
            "notes": f"sold @ {sell.get('price')}",
        })
    if new_status == "SETTLED":
        settlement = updates.get("settlement", pos.get("settlement")) or {}
        await db.treasury_col.insert_one({
            "id": new_id(), "route_id": pos["route_id"], "position_id": position_id, "ts": now_iso(),
            "leg": "settlement", "asset": settlement.get("coin", "settlement"),
            "qty": settlement.get("amount"),
            "quote_value": settlement.get("quote_value"),
            "notes": "settled to funding coin" if settlement else "settled (no conversion details)",
        })
    if "status" in updates:
        await collector.event("info", "position", f"Position → {updates['status']}", route_id=pos["route_id"])
    return await db.positions_col.find_one({"id": position_id}, {"_id": 0})


# ---------------- transfers ----------------

class TransferCreate(BaseModel):
    route_id: str
    position_id: Optional[str] = None
    leg: str = "wallet→exchange"
    network_key: str = "BLOCKDAG"
    asset: str = "BDAG"
    qty: float
    tx_hash: Optional[str] = None
    sent_at: Optional[str] = None
    credited_at: Optional[str] = None
    status: str = "pending"
    notes: Optional[str] = None


@router.get("/transfers")
async def list_transfers(route_id: Optional[str] = None):
    q = {"route_id": route_id} if route_id else {}
    return await db.transfers_col.find(q, {"_id": 0}, sort=[("created_at", -1)]).to_list(100)


@router.post("/transfers")
async def create_transfer(body: TransferCreate):
    doc = body.model_dump()
    doc.update(id=new_id(), created_at=now_iso())
    doc["sent_at"] = doc.get("sent_at") or now_iso()
    if doc.get("credited_at"):
        try:
            d1 = datetime.fromisoformat(doc["sent_at"])
            d2 = datetime.fromisoformat(doc["credited_at"])
            doc["duration_s"] = (d2 - d1).total_seconds()
            doc["status"] = "complete"
        except ValueError:
            pass
    await db.transfers_col.insert_one(dict(doc))
    collector._has_transfer_history[body.route_id] = None  # invalidate cache
    doc.pop("_id", None)
    return doc


# ---------------- system ----------------

@router.get("/system/status")
async def system_status():
    routes = await db.routes_col.find({"active": True}, {"_id": 0, "id": 1, "name": 1, "mode": 1}).to_list(50)
    return {
        "routes": routes,
        "networks": collector.network_health,
        "websockets": ws_manager.status(),
        "events": list(collector.events),
        "connectors": registry.available(),
    }
