"""Executable Quote Capture (READ-ONLY).

Pre-trade BDAG-allocation captures from a real connected-wallet swap UI session
— stored, ranked, and surfaced as the PRIMARY buy-price authority for ArbiCore.

How captures arrive:
  • Operator pastes a one-line bookmarklet into the swap page console after
    connecting their wallet (see QuoteCapturePanel for the snippet). The
    bookmarklet hooks fetch + XHR + WebSocket + the React store and POSTs every
    detected BDAG-quote payload to /api/execution/quote-capture.
  • OR the operator types the values into the manual capture form directly.

Stored shape:
  { id, input_amount, input_token, bdag_allocated, effective_price,
    timestamp, source, raw, note, created_at }

source is operator-supplied / bookmarklet-supplied — typical values:
  - swap_ui_state_observed
  - swap_ui_websocket
  - swap_ui_api_response
  - swap_ui_pre_signature_payload
  - manual_screenshot

No execution. No signing. No fund movement.
"""
import statistics
from datetime import datetime, timezone

from core.models import new_id, now_iso
from services import db

COLL = "executable_quote_captures"
FRESH_S = 300                  # 5 min → captured quote considered authoritative
ROLLING_WINDOW = 20            # samples used for stats / averaging


async def ensure_indexes():
    await db.db[COLL].create_index([("created_at", -1)])
    await db.db[COLL].create_index([("input_amount", 1), ("created_at", -1)])


async def record(input_amount: float, bdag_allocated: float,
                 input_token: str = "USDT", source: str = "manual",
                 raw: dict = None, note: str = None) -> dict:
    if input_amount is None or input_amount <= 0:
        raise ValueError("input_amount must be > 0")
    if bdag_allocated is None or bdag_allocated <= 0:
        raise ValueError("bdag_allocated must be > 0")
    effective_price = round(float(input_amount) / float(bdag_allocated), 12)
    doc = {
        "id": new_id(),
        "input_amount": float(input_amount),
        "input_token": (input_token or "USDT").upper(),
        "bdag_allocated": float(bdag_allocated),
        "effective_price": effective_price,
        "source": source or "manual",
        "raw": raw,
        "note": note,
        "created_at": now_iso(),
    }
    await db.db[COLL].insert_one(dict(doc))
    return doc


async def list_captures(limit: int = 50) -> list:
    return await db.db[COLL].find({}, {"_id": 0},
                                  sort=[("created_at", -1)]).to_list(max(1, min(limit, 500)))


def _age_s(iso_str):
    if not iso_str:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso_str)).total_seconds()
    except (ValueError, TypeError):
        return None


async def latest() -> dict:
    docs = await db.db[COLL].find({}, {"_id": 0},
                                  sort=[("created_at", -1)]).to_list(1)
    if not docs:
        return {"available": False, "note": "No executable-quote captures recorded yet."}
    d = docs[0]
    age = _age_s(d["created_at"])
    return {
        "available": True,
        "fresh": age is not None and age <= FRESH_S,
        "age_s": round(age, 1) if age is not None else None,
        "fresh_window_s": FRESH_S,
        **d,
    }


async def rolling_summary() -> dict:
    docs = await db.db[COLL].find({}, {"_id": 0},
                                  sort=[("created_at", -1)]).to_list(ROLLING_WINDOW)
    if not docs:
        return {"count": 0, "rolling_window": ROLLING_WINDOW}
    eff = [d["effective_price"] for d in docs]
    return {
        "count": len(docs),
        "rolling_window": ROLLING_WINDOW,
        "avg_effective_price": round(statistics.mean(eff), 12),
        "median_effective_price": round(statistics.median(eff), 12),
        "min_effective_price": min(eff), "max_effective_price": max(eff),
        "stdev": round(statistics.pstdev(eff), 12) if len(eff) > 1 else 0.0,
        "first_at": docs[-1]["created_at"], "last_at": docs[0]["created_at"],
    }


async def status() -> dict:
    return {
        "phase": "Executable Quote Capture (read-only, observe-only)",
        "generated_at": now_iso(),
        "latest": await latest(),
        "rolling": await rolling_summary(),
        "recent_captures": await list_captures(20),
        "fresh_window_s": FRESH_S,
        "note": ("Operator pastes the bookmarklet into the swap page after wallet connection — "
                 "every detected pre-trade quote is POSTed here. No execution, no signing."),
    }
