"""Single source of truth for BDAG buy-price resolution (Phase E4.6.1).

Precedence (identical everywhere): active position cost basis → manual override
→ live portal feed → manual fallback. Consumed by collector/evaluation (which
feed the opportunity widget, shadow runner & certification), the production
ledger, and the arbitrage intelligence engine — so every layer resolves the buy
price the same way. READ-ONLY: no execution, no fund movement.

resolve_sync() returns the winning price PLUS a full transparency chain showing
every candidate source, its value/timestamp/age, which one won, and why.
"""
from datetime import datetime, timezone

from services import db
from services.portal_price import portal_price

PRECEDENCE = ["captured_quote", "position", "manual_override", "portal", "manual_fallback"]


def _captured_quote_candidate(qty):
    """Synchronous accessor for the latest fresh captured quote (set by resolve())."""
    return _captured_quote_candidate.cache or {
        "source": "captured_quote", "label": "Captured Executable Quote (operator-attested, fresh)",
        "value": None, "qty": qty, "timestamp": None, "available": False,
        "detail": "no fresh capture yet — paste userscript / use manual form"}
_captured_quote_candidate.cache = None


def _age_s(iso):
    if not iso:
        return None
    try:
        return round((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def resolve_sync(route: dict, pos: dict | None) -> dict:
    mb = route.get("manual_buy") or {}
    qty = mb.get("qty")
    is_bdag = (route.get("purchase") or {}).get("asset") == "BDAG"
    pf = portal_price.status_brief()  # {bdag_price, stale, fetched_at, source, ...}

    candidates = [
        _captured_quote_candidate(qty),
        {"source": "position", "label": "Position Cost Basis",
         "value": (pos or {}).get("buy_price"), "qty": (pos or {}).get("qty", qty),
         "timestamp": (pos or {}).get("created_at"),
         "available": bool(pos and pos.get("buy_price")),
         "detail": (f"active position {pos['id'][:8]} ({pos.get('status')})"
                    if pos and pos.get("id") else "no active (non-settled) position")},
        {"source": "manual_override", "label": "Manual Override",
         "value": mb.get("price") if mb.get("override") else None, "qty": qty,
         "timestamp": route.get("updated_at"),
         "available": bool(mb.get("override") and mb.get("price") is not None),
         "detail": "route.manual_buy.override " + ("ON" if mb.get("override") else "OFF")},
        {"source": "portal", "label": "Live Portal Feed",
         "value": (pf["bdag_price"] if (is_bdag and not pf["stale"]) else None), "qty": qty,
         "timestamp": pf["fetched_at"],
         "available": (is_bdag and not pf["stale"] and pf["bdag_price"] is not None),
         "detail": (pf["source"] + (" — STALE" if pf["stale"] else "")
                    + ("" if is_bdag else " — non-BDAG route"))},
        {"source": "manual_fallback", "label": "Manual Fallback",
         "value": mb.get("price"), "qty": qty, "timestamp": route.get("updated_at"),
         "available": mb.get("price") is not None,
         "detail": "route.manual_buy.price (stored, no override flag)"},
    ]

    winner = next((c for c in candidates if c["available"]), None)
    for c in candidates:
        c["age_s"] = _age_s(c.get("timestamp"))
        c["won"] = bool(winner and c["source"] == winner["source"])
        c["reason"] = ("highest-precedence available source" if c["won"]
                       else "not available" if not c["available"]
                       else "lower precedence — a higher source won")

    return {
        "price": (winner or {}).get("value"),
        "qty": (winner or {}).get("qty", qty),
        "source": (winner or {}).get("source"),
        "source_label": (winner or {}).get("label"),
        "timestamp": (winner or {}).get("timestamp"),
        "age_s": (winner or {}).get("age_s"),
        "chain": candidates,
        "precedence": PRECEDENCE,
    }


async def active_position(route_id: str):
    return await db.positions_col.find_one(
        {"route_id": route_id, "status": {"$nin": ["SETTLED"]}}, {"_id": 0},
        sort=[("created_at", -1)])


async def resolve(route: dict) -> dict:
    # Inject latest captured executable quote (PRIMARY when fresh)
    from services.execution import quote_capture
    latest = await quote_capture.latest()
    qty = (route.get("manual_buy") or {}).get("qty")
    is_bdag = (route.get("purchase") or {}).get("asset") == "BDAG"
    _captured_quote_candidate.cache = {
        "source": "captured_quote",
        "label": "Captured Executable Quote (operator-attested, fresh ≤ 300s)",
        "value": (latest.get("effective_price") if (is_bdag and latest.get("available")
                                                    and latest.get("fresh")) else None),
        "qty": qty,
        "timestamp": latest.get("created_at"),
        "available": bool(is_bdag and latest.get("available") and latest.get("fresh")),
        "detail": (("source=" + (latest.get("source") or "—") + ", age=" + str(latest.get("age_s")) + "s")
                   if latest.get("available")
                   else "no fresh capture yet"),
    }
    try:
        return resolve_sync(route, await active_position(route["id"]))
    finally:
        _captured_quote_candidate.cache = None


FRESH_PRECEDENCE = ["captured_quote", "manual_override", "portal", "manual_fallback"]


def select_fresh(resolution: dict) -> dict | None:
    chain = resolution.get("chain") or []
    for src in FRESH_PRECEDENCE:
        c = next((x for x in chain if x["source"] == src and x["available"]), None)
        if c:
            return c
    return None


def select_position(resolution: dict) -> dict | None:
    chain = resolution.get("chain") or []
    return next((x for x in chain if x["source"] == "position" and x["available"]), None)


def as_fresh_resolution(resolution: dict) -> dict:
    """Re-orient a full resolution around the FRESH-cycle winner (live swap),
    excluding held-position cost basis. Same shape; chain 'won' re-marked so the
    transparency view shows the source actually used for execution decisions."""
    fresh = select_fresh(resolution)
    chain = []
    for c in resolution.get("chain") or []:
        cc = dict(c)
        cc["won"] = bool(fresh and c["source"] == fresh["source"])
        if c["source"] == "position":
            cc["reason"] = "excluded from fresh-cycle pricing (held-position cost basis is informational only)"
        elif cc["won"]:
            cc["reason"] = "highest-precedence available FRESH source (live swap basis)"
        elif not c["available"]:
            cc["reason"] = "not available"
        else:
            cc["reason"] = "lower precedence — a higher fresh source won"
        chain.append(cc)
    return {
        "price": (fresh or {}).get("value"), "qty": (fresh or {}).get("qty"),
        "source": (fresh or {}).get("source"), "source_label": (fresh or {}).get("label"),
        "timestamp": (fresh or {}).get("timestamp"), "age_s": (fresh or {}).get("age_s"),
        "chain": chain, "precedence": FRESH_PRECEDENCE, "model": "fresh_cycle",
    }
