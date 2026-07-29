"""Executable Quote Resolver (READ-ONLY).

Three-source quote resolution layer designed to produce the SAME price the
operator sees on the BlockDAG Live Swap screen and that actual swaps settle at.

Sources (in default precedence order):
  A. EXECUTED PRICE HISTORY  ← rolling average of operator-recorded executed
                                swaps (the buy_price_empirical_quotes collection).
                                Authoritative when ≥ MIN_EXECUTED_SAMPLES exist.
  B. LIVE SWAP UI QUOTE      ← live call to live-price.blockdag.network/bdag-price
                                (the dedicated price endpoint the swap UI itself
                                calls — discovered via network inspection of
                                purchase3.blockdag.network/swap).
  C. SW-API FALLBACK         ← sw-api.blockdag.network/getInfo · bdagPrice via
                                the existing portal_price cache.

A SECONDARY OBSERVATION (presale orderBook implied price) is surfaced for
cross-check only; it is NOT in the precedence chain because the orderBook is
denominated in presale token units, not the settlement BDAG seen at Coinstore.

No execution, no orders, no fund movement. This resolver is consumed by the
new /executable-quote endpoint and the read-only UI panel. The existing
arbitrage_intel buy-price resolver is UNCHANGED — wiring this resolver into
Fresh-Cycle ROI is a deliberate, operator-initiated step.
"""
import asyncio
import logging
import statistics
from datetime import datetime, timezone

import httpx

from core.models import now_iso
from services import db
from services.execution.buy_price_audit import list_empirical
from services.portal_price import portal_price

logger = logging.getLogger("executable_quote")

LIVE_SWAP_UI_URL = "https://live-price.blockdag.network/bdag-price"
PRESALE_ORDERBOOK_URL = "https://preapi.blockdag.network/root"
REQUEST_TIMEOUT_S = 10

MIN_EXECUTED_SAMPLES = 3      # need ≥ N empirical samples before authoritative
EXECUTED_ROLLING_WINDOW = 20  # rolling avg over latest N

PRECEDENCE = ["executed_history", "live_swap_ui", "sw_api_fallback"]


async def _fetch_live_swap_ui(client: httpx.AsyncClient) -> dict:
    started = datetime.now(timezone.utc)
    try:
        r = await client.get(LIVE_SWAP_UI_URL, headers={
            "User-Agent": "ArbiCore/audit (read-only price discovery)",
            "Referer": "https://purchase3.blockdag.network/",
        })
        ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 1)
        r.raise_for_status()
        payload = r.json()
        price = (payload.get("data") or {}).get("BDAG") if isinstance(payload, dict) else None
        return {
            "ok": price is not None and price > 0,
            "value": float(price) if price is not None else None,
            "url": LIVE_SWAP_UI_URL,
            "endpoint_label": "live-price.blockdag.network/bdag-price",
            "discovery": "Identified via XHR/fetch capture on purchase3.blockdag.network/swap — "
                         "this is the dedicated price endpoint the Live Swap UI itself calls.",
            "raw_fetched_at": payload.get("fetchedAt"),
            "fetched_at": now_iso(),
            "latency_ms": ms,
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "value": None, "url": LIVE_SWAP_UI_URL,
                "endpoint_label": "live-price.blockdag.network/bdag-price",
                "discovery": "Identified via XHR/fetch capture on purchase3.blockdag.network/swap.",
                "fetched_at": now_iso(), "latency_ms": None, "error": str(e)[:200]}


async def _fetch_presale_orderbook(client: httpx.AsyncClient) -> dict:
    try:
        r = await client.get(PRESALE_ORDERBOOK_URL, headers={
            "User-Agent": "ArbiCore/audit", "Referer": "https://purchase3.blockdag.network/"})
        r.raise_for_status()
        payload = r.json()
        coin = (payload or {}).get("coin") or {}
        ob = coin.get("orderBook") or payload.get("orderBook") or []
        eff = []
        sample = []
        for o in ob[:20]:
            try:
                usd = float(o.get("pay_usd_amount") or 0)
                bdag = float(o.get("bought_token_amount") or 0)
                if usd > 0 and bdag > 0:
                    eff.append(usd / bdag)
                    sample.append({
                        "pay_usd_amount": usd, "bought_token_amount": bdag,
                        "effective_price": round(usd / bdag, 12),
                    })
            except (TypeError, ValueError):
                continue
        return {
            "ok": bool(eff),
            "implied_price_from_latest_orders": round(statistics.mean(eff), 12) if eff else None,
            "sample_count": len(eff),
            "stage": coin.get("stage"),
            "token_price": coin.get("tokenPrice"),
            "next_stage_token_price": coin.get("nextStageTokenPrice"),
            "samples": sample[:5],
            "url": PRESALE_ORDERBOOK_URL,
            "fetched_at": now_iso(),
            "note": ("Presale orderBook implied price. Denominated in presale-token units rather than the "
                     "settlement BDAG seen at Coinstore — useful as a cross-check, NOT in the precedence "
                     "chain because of the denomination delta."),
        }
    except Exception as e:
        return {"ok": False, "url": PRESALE_ORDERBOOK_URL,
                "implied_price_from_latest_orders": None, "samples": [],
                "fetched_at": now_iso(), "error": str(e)[:200]}


async def _executed_history() -> dict:
    docs = await list_empirical(EXECUTED_ROLLING_WINDOW)
    eff = [d["effective_price"] for d in docs if isinstance(d.get("effective_price"), (int, float))]
    if not eff:
        return {
            "ok": False, "value": None, "count": 0,
            "rolling_window": EXECUTED_ROLLING_WINDOW,
            "samples": [],
            "label": "Executed Price History (rolling avg, operator-attested executed swaps)",
            "note": ("No executed-swap samples recorded yet. Record at least {0} via "
                     "POST /api/execution/buy-price-audit/empirical (or the panel form) before this "
                     "source becomes authoritative.".format(MIN_EXECUTED_SAMPLES)),
            "fetched_at": now_iso(),
        }
    return {
        "ok": True,
        "value": round(statistics.mean(eff), 12),
        "median": round(statistics.median(eff), 12),
        "min": min(eff), "max": max(eff),
        "stdev": round(statistics.pstdev(eff), 12) if len(eff) > 1 else 0.0,
        "count": len(eff),
        "rolling_window": EXECUTED_ROLLING_WINDOW,
        "latest_at": docs[0].get("created_at"),
        "first_at": docs[-1].get("created_at"),
        "label": "Executed Price History (rolling avg, operator-attested executed swaps)",
        "samples": [{
            "investment_usd": d.get("investment_usd"),
            "bdag_received": d.get("bdag_received"),
            "effective_price": d.get("effective_price"),
            "reported_ui_price": d.get("reported_ui_price"),
            "created_at": d.get("created_at"),
        } for d in docs[:5]],
        "note": ("Settles ROI math at the same price actual swaps land at. Authoritative when "
                 "count ≥ {0}.".format(MIN_EXECUTED_SAMPLES)),
        "fetched_at": now_iso(),
    }


async def _sw_api_fallback() -> dict:
    """sw-api/getInfo via the existing portal_price cache (untouched)."""
    pf = portal_price.status_brief()
    return {
        "ok": pf.get("bdag_price") is not None,
        "value": pf.get("bdag_price"),
        "fetched_at": pf.get("fetched_at"),
        "stale": pf.get("stale"),
        "source_url": pf.get("source"),
        "label": "sw-api/getInfo · bdagPrice (Portal Feed cache · fallback)",
        "note": ("Same numerical value as the live-swap-ui endpoint. ArbiCore currently consumes this "
                 "for Fresh-Cycle ROI. The contract applies a bonus on top that this API does NOT expose, "
                 "so Fresh ROI is conservatively under-estimated when this is the consumed source."),
    }


def _pct_diff(a, b):
    if a is None or b is None or b == 0:
        return None
    return round((a - b) / b * 100, 3)


def _resolve(executed, live, swapi):
    """Walk the precedence chain and pick the authoritative source."""
    chain = []
    chosen = None
    if executed.get("ok") and executed.get("count", 0) >= MIN_EXECUTED_SAMPLES:
        chain.append({
            "source": "executed_history", "won": True, "available": True,
            "value": executed["value"], "count": executed["count"],
            "reason": ("≥{0} executed-swap samples available — rolling average is authoritative "
                       "because it reflects the actual settlement price the wallet experiences "
                       "(includes the contract-side bonus the API does not expose)."
                       .format(MIN_EXECUTED_SAMPLES)),
        })
        chosen = {"source": "executed_history", "value": executed["value"]}
    else:
        chain.append({
            "source": "executed_history", "won": False,
            "available": executed.get("ok"),
            "value": executed.get("value"), "count": executed.get("count", 0),
            "reason": ("Insufficient executed-swap samples (have {0}, need ≥{1}) — falling through."
                       .format(executed.get("count", 0), MIN_EXECUTED_SAMPLES)),
        })
        if live.get("ok"):
            chain.append({
                "source": "live_swap_ui", "won": True, "available": True,
                "value": live["value"],
                "reason": ("Live UI quote endpoint healthy. NOTE: this returns the same API price as "
                           "sw-api (no contract bonus baked in), so Fresh-Cycle ROI will UNDER-estimate "
                           "real profitability by the contract bonus margin until enough executed "
                           "samples are recorded."),
            })
            chosen = {"source": "live_swap_ui", "value": live["value"]}
        else:
            chain.append({
                "source": "live_swap_ui", "won": False,
                "available": False, "value": None,
                "reason": "Live UI quote endpoint unavailable — falling through.",
            })
            if swapi.get("ok") and not swapi.get("stale"):
                chain.append({
                    "source": "sw_api_fallback", "won": True, "available": True,
                    "value": swapi["value"],
                    "reason": "sw-api fallback (Portal Feed cache) — fresh.",
                })
                chosen = {"source": "sw_api_fallback", "value": swapi["value"]}
            else:
                chain.append({
                    "source": "sw_api_fallback", "won": False,
                    "available": swapi.get("ok"), "value": swapi.get("value"),
                    "reason": "sw-api cache stale or unavailable. No authoritative price.",
                })
    return chosen, chain


async def resolve() -> dict:
    """Single-pass resolution. Returns the authoritative quote + the full chain."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        live_task = _fetch_live_swap_ui(client)
        presale_task = _fetch_presale_orderbook(client)
        executed_task = _executed_history()
        swapi_task = _sw_api_fallback()
        live, presale, executed, swapi = await asyncio.gather(
            live_task, presale_task, executed_task, swapi_task)

    chosen, chain = _resolve(executed, live, swapi)

    # Side-by-side comparison vs the chosen authoritative price.
    ref = (chosen or {}).get("value")
    comparison = []
    for s, src in (("executed_history", executed), ("live_swap_ui", live),
                   ("sw_api_fallback", swapi)):
        comparison.append({
            "source": s,
            "label": src.get("label") or src.get("endpoint_label") or s,
            "value": src.get("value"),
            "delta_pct_vs_authoritative": _pct_diff(src.get("value"), ref),
            "available": bool(src.get("ok")),
            "is_authoritative": (chosen or {}).get("source") == s,
            "fetched_at": src.get("fetched_at"),
        })

    # Effective price from "completed swaps" — the operator-attested rolling avg.
    effective_from_completed_swaps = executed.get("value") if executed.get("ok") else None

    return {
        "phase": "Executable Quote Resolver (read-only, three-source)",
        "generated_at": now_iso(),
        "authoritative": chosen,
        "authoritative_explanation": (
            chain[-1]["reason"] if chain else "No authoritative price."),
        "precedence": PRECEDENCE,
        "chain": chain,
        "sources": {
            "executed_history": executed,
            "live_swap_ui": live,
            "sw_api_fallback": swapi,
        },
        "side_by_side": comparison,
        "secondary_observation": {
            "label": "preapi/root · orderBook implied price (cross-check only)",
            **presale,
        },
        "effective_price_from_completed_swaps": effective_from_completed_swaps,
        "consumed_by_arbicore_for_roi": False,
        "consumed_by_arbicore_note": (
            "ArbiCore's Fresh-Cycle ROI continues to consume the sw-api Portal Feed (precedence "
            "unchanged in arbitrage_intel). This resolver is exposed READ-ONLY for the operator to "
            "verify that Executed Price History is reliable before any wiring change."),
        "thresholds": {
            "min_executed_samples_for_authoritative": MIN_EXECUTED_SAMPLES,
            "executed_rolling_window": EXECUTED_ROLLING_WINDOW,
        },
        "note": ("Sources A and B sit at the same numeric value because the swap UI's price endpoint "
                 "exposes the API-base price; the ~10% bonus the operator observes empirically is "
                 "applied by the swap contract itself, not the API. Only Executed Price History "
                 "captures the true settlement price."),
    }
