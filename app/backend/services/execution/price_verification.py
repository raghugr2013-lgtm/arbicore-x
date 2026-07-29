"""Price Verification & Calculation Transparency (READ-ONLY).

Exposes every input and intermediate value behind an opportunity calculation so
the operator can INDEPENDENTLY verify each number against the real-world sources
(the BlockDAG Live Swap + the sell-venue order book) BEFORE trusting any future
execution decision.

Composes existing read-only engines only (arbitrage intel, opportunity gate,
safety interlock, the buy-price resolver, the portal price feed, and the live
order book). NO execution, no orders, no API keys, no wallet, no fund movement.
"""
from datetime import datetime, timezone

from core.models import now_iso
from services import db
from services.collector import collector
from services.portal_price import portal_price
from services.execution import arbitrage_intel, opportunity_gate, safety_interlock

# Public reference pages the operator can open to verify each number by hand.
VENUE_URLS = {
    "coinstore": "https://www.coinstore.com/spot/BDAGUSDT",
    "bitmart": "https://www.bitmart.com/trade/en-US?symbol=BDAG_USDT",
    "xt": "https://www.xt.com/en/trade/bdag_usdt",
}
LIVE_SWAP_URL = "https://purchase3.blockdag.network/swap"
LIVE_SWAP_API = "https://sw-api.blockdag.network/getInfo"


def _age_s(iso):
    if not iso:
        return None
    try:
        return round((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


async def _bdag_route(route_id=None):
    if route_id:
        return await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    return await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0})


async def _order_book_block(route_id, venue):
    rcache = collector.cache.get(route_id, {})
    m = rcache.get(venue) or {}
    ob = m.get("orderbook") or {}
    bids = ob.get("bids") or []
    asks = ob.get("asks") or []
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    spread = (best_ask - best_bid) if (best_bid and best_ask) else None
    spread_pct = round(spread / best_bid * 100, 4) if (spread is not None and best_bid) else None
    total_bid_quote = round(sum(p * q for p, q in bids), 2) if bids else None
    total_ask_quote = round(sum(p * q for p, q in asks), 2) if asks else None
    snap = await db.orderbook_snapshots.find_one(
        {"route_id": route_id, "exchange": venue}, {"_id": 0, "created_at": 1, "ts": 1},
        sort=[("created_at", -1)])
    ob_ts = (snap or {}).get("created_at") or (snap or {}).get("ts")
    return {
        "best_bid": best_bid, "best_ask": best_ask,
        "spread": round(spread, 10) if spread is not None else None, "spread_pct": spread_pct,
        "total_bid_depth_quote_usd": total_bid_quote, "total_ask_depth_quote_usd": total_ask_quote,
        "order_book_timestamp": ob_ts, "data_age_s": _age_s(ob_ts),
        "source": m.get("source"), "levels_bid": len(bids), "levels_ask": len(asks),
    }


def _decision_explanation(gate, interlock):
    gv = gate.get("gate_verdict")
    passed = [c["label"] for c in (gate.get("conditions") or []) if c["passed"]]
    failed = [c["label"] for c in (gate.get("conditions") or []) if not c["passed"]]
    lines = []
    if gv == "GO":
        lines.append("GO because: " + "; ".join(passed))
    elif gv == "WAIT":
        lines.append("WAIT — the opportunity exists but: " + "; ".join(failed or ["a soft condition is unmet"]))
    else:
        lines.append("NO_GO because: " + "; ".join(failed or ["no profitable surface at the current book"]))
    iv = interlock.get("verdict")
    if iv != "READY":
        reasons = (interlock.get("blocked_reasons") or []) + (interlock.get("wait_reasons") or [])
        lines.append(f"Safety Interlock {iv}: " + "; ".join(reasons or ["not READY"]))
    else:
        lines.append("Safety Interlock READY.")
    return lines


async def build(route_id=None) -> dict:
    route = await _bdag_route(route_id)
    if not route:
        return {"available": False, "note": "No BDAG route configured."}
    rid = route["id"]
    intel = await arbitrage_intel.analyze(rid)
    gate = await opportunity_gate.evaluate(rid)
    interlock = await safety_interlock.evaluate(rid)
    portal = await portal_price.status()

    venue = intel.get("sell_venue") or gate.get("venue")
    ob = await _order_book_block(rid, venue) if venue else {}

    # --- 1. BlockDAG Live Swap ---
    live_swap = {
        "current_live_swap_price": portal.get("bdag_price"),
        "source_url": LIVE_SWAP_URL,
        "api_source": LIVE_SWAP_API,
        "source_identifier": "sw-api/getInfo",
        "timestamp": portal.get("fetched_at"),
        "data_age_s": _age_s(portal.get("fetched_at")),
        "stale": portal.get("stale"),
        "note": ("The BlockDAG Portal API (sw-api/getInfo) serves the same live BDAG swap quote shown at "
                 "purchase3.blockdag.network/swap."),
    }

    # --- 2. Sell-venue (e.g. Coinstore) market data ---
    rec = intel.get("recommended") or {}
    weighted_sell = rec.get("weighted_sell_price")
    prof = intel.get("profitable_liquidity") or {}
    market = {
        "venue": venue, "venue_label": (venue or "").upper(),
        "reference_url": VENUE_URLS.get(venue),
        "best_bid": ob.get("best_bid"), "best_ask": ob.get("best_ask"),
        "bid_ask_spread": ob.get("spread"), "bid_ask_spread_pct": ob.get("spread_pct"),
        "total_profitable_bid_depth_usd": prof.get("profitable_quote"),
        "total_profitable_bid_depth_base": prof.get("profitable_base"),
        "total_bid_depth_usd": ob.get("total_bid_depth_quote_usd"),
        "total_ask_depth_usd": ob.get("total_ask_depth_quote_usd"),
        "weighted_average_sell_price_used": weighted_sell,
        "order_book_timestamp": ob.get("order_book_timestamp"),
        "data_age_s": ob.get("data_age_s"),
        "data_source": ob.get("source"),
        "note": ("Profitable bid depth = sum of bids at/above the break-even sell price; the sell leg consumes "
                 "bids only (ask depth shown for reference)."),
    }

    # --- 3. Calculation transparency ---
    res = intel.get("buy_price_resolution") or {}
    calc = {
        "buy_price_used": intel.get("buy_price"),
        "buy_source_used": res.get("source_label") or intel.get("buy_price_source"),
        "buy_source_key": intel.get("buy_price_source"),
        "sell_price_used": ob.get("best_bid"),
        "sell_source_used": f"{(venue or '').upper()} Best Bid" if venue else None,
        "weighted_average_sell_price_used": weighted_sell,
        "weighted_sell_note": ("Weighted average across every bid level actually consumed at the recommended size "
                               "(multi-level VWAP — never a single-price assumption)."),
    }

    # --- 4. Full profitability trace (at the recommended / cert-capped size) ---
    if rec:
        trace = {
            "available": True,
            "size_basis": ("cert-capped recommended" if rec.get("capped_to_cert_max")
                           else f"{rec.get('utilization_pct')}% of profitable depth"),
            "capital_input_usd": rec.get("investment_usd"),
            "bdag_acquired_base": rec.get("buy_qty_base"),
            "bdag_sold_base": rec.get("sell_qty_base"),
            "trading_fees_usd": rec.get("trading_fee_usd"),
            "transfer_fees_bdag": rec.get("transfer_fee_base"),
            "gas_fee_usd": rec.get("gas_fee_usd"),
            "withdrawal_fees_usd": rec.get("withdrawal_fee_usd"),
            "gross_proceeds_usd": rec.get("gross_proceeds_usd"),
            "net_proceeds_usd": rec.get("wallet_received_usd"),
            "net_profit_usd": rec.get("net_profit_usd"),
            "roi_pct": rec.get("roi_pct"),
        }
    else:
        trace = {"available": False, "note": "No profitable size at the current book/buy price."}

    # --- 5. Source comparison (all buy-price candidates; WINNER identified) ---
    candidates = res.get("chain") or []
    source_comparison = {
        "precedence": res.get("precedence"),
        "winner_source": res.get("source"),
        "winner_label": res.get("source_label"),
        "candidates": [
            {"source": c["source"], "label": c["label"], "value": c["value"],
             "available": c["available"], "winner": c.get("won"),
             "timestamp": c.get("timestamp"), "age_s": c.get("age_s"),
             "detail": c.get("detail"), "reason": c.get("reason")}
            for c in candidates],
        "note": "WINNER = the highest-precedence AVAILABLE source; it is the buy price actually used above.",
    }

    # --- 6. Opportunity decision trace ---
    decision = {
        "gate_verdict": gate.get("gate_verdict"),
        "gate_reasons": gate.get("reasons"),
        "conditions": [{"key": c["key"], "label": c["label"], "passed": c["passed"], "detail": c["detail"]}
                       for c in (gate.get("conditions") or [])],
        "interlock_verdict": interlock.get("verdict"),
        "interlock_blocked_reasons": interlock.get("blocked_reasons"),
        "interlock_wait_reasons": interlock.get("wait_reasons"),
        "explanation": _decision_explanation(gate, interlock),
    }

    return {
        "phase": "Price Verification & Calculation Transparency (read-only)",
        "available": True, "generated_at": now_iso(),
        "route_id": rid, "route_name": route.get("name"), "sell_venue": venue,
        "executable_sizing": intel.get("executable_sizing"),
        "dual_roi": intel.get("dual_roi"),
        "freshness": gate.get("freshness"),
        "blockdag_live_swap": live_swap,
        "market_data": market,
        "calculation_transparency": calc,
        "profitability_trace": trace,
        "source_comparison": source_comparison,
        "decision_trace": decision,
        "note": ("Every value here is independently verifiable against the BlockDAG Live Swap and the sell-venue "
                 "order book. Read-only — no execution, no orders, no fund movement."),
    }
