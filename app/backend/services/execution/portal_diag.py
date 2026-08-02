"""Phase E4.6.1 — Portal Feed Diagnostic (READ-ONLY; does NOT modify feed).

Audits the BlockDAG portal price connector: live endpoint, raw payload sample,
poll cadence, cache age, 24h value history, staleness evidence, and a comparison
vs the live swap UI value reported by the operator. No behavior change.
"""
from datetime import datetime, timedelta, timezone

import httpx

from services import db
from services.portal_price import (GETINFO_URL, POLL_EVERY_S, STALE_AFTER_S,
                                   portal_price)

# Floors below which a 2026 reference price is implausibly low → strong stale signal.
PLAUSIBLE_2026_FLOOR = {"BTC": 90000, "ETH": 2500, "BNB": 500, "SOL": 90}
SWAP_UI_URL = "https://purchase3.blockdag.network/swap"
OPERATOR_REPORTED_SWAP_PRICE = 3.6e-05


async def report() -> dict:
    st = await portal_price.status()

    raw, raw_err = None, None
    try:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "arbicore-diag"}) as c:
            r = await c.get(GETINFO_URL)
            raw = r.json().get("data") or {}
    except Exception as e:
        raw_err = str(e)[:200]

    coin = (raw or {}).get("coinPrices") or st.get("coin_prices") or {}
    stale_evidence = []
    for sym, floor in PLAUSIBLE_2026_FLOOR.items():
        v = coin.get(sym)
        if v is not None and v < floor:
            stale_evidence.append(
                f"coinPrices.{sym}=${v:,.0f} is implausibly low for 2026 (< ${floor:,}) "
                f"→ reference market prices in the feed are stale/frozen")

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    snaps = await db.portal_price_snapshots.find(
        {"created_at": {"$gte": since}}, {"_id": 0, "ts": 1, "bdag_price": 1},
        sort=[("created_at", 1)]).to_list(5000)
    prices = [s["bdag_price"] for s in snaps if s.get("bdag_price") is not None]

    cache_age = None
    if st.get("fetched_at"):
        try:
            cache_age = round((datetime.now(timezone.utc)
                               - datetime.fromisoformat(st["fetched_at"])).total_seconds(), 1)
        except (ValueError, TypeError):
            cache_age = None

    api_price = (raw or {}).get("bdagPrice") if raw else st.get("bdag_price")
    delta_vs_swap = (round((api_price - OPERATOR_REPORTED_SWAP_PRICE)
                           / OPERATOR_REPORTED_SWAP_PRICE * 100, 2)
                     if api_price else None)

    recommendation = [
        "Treat the portal `getInfo.bdagPrice` as advisory/lowest-priority until a live, "
        "verifiable swap price source is wired (it is the last in the precedence chain anyway).",
        "Keep the active-position / manual-override basis authoritative for GO decisions (now consistent across all layers).",
        "Add a freshness/sanity guard: if coinPrices look stale OR |api − manual/position| exceeds a band, "
        "flag the portal source and exclude it from GO gating.",
        f"Investigate the real swap quote at {SWAP_UI_URL} (JS app) — its effective rate (~{OPERATOR_REPORTED_SWAP_PRICE}) "
        f"differs from getInfo ({api_price}); likely bonus tokens or a non-live presale value.",
    ]

    return {
        "phase": "E4.6.1 — Portal Feed Diagnostic (read-only)",
        "endpoint": GETINFO_URL,
        "poll_frequency_s": POLL_EVERY_S,
        "stale_after_s": STALE_AFTER_S,
        "cache": {
            "bdag_price": st.get("bdag_price"), "fetched_at": st.get("fetched_at"),
            "age_s": cache_age, "stale": st.get("stale"),
            "poll_count": st.get("poll_count"), "consecutive_failures": st.get("consecutive_failures"),
            "last_error": st.get("last_error"),
        },
        "raw_payload_sample": {
            "bdag_price": api_price, "wallet_address": (raw or {}).get("walletAddress"),
            "coin_prices_sample": {k: coin.get(k) for k in ("BTC", "ETH", "BNB", "SOL")},
            "fetch_error": raw_err,
        },
        "value_history_24h": {
            "samples": len(prices),
            "distinct_values": sorted(set(prices)),
            "min": min(prices) if prices else None, "max": max(prices) if prices else None,
            "first": prices[0] if prices else None, "last": prices[-1] if prices else None,
            "series_tail": [{"ts": s["ts"], "price": s["bdag_price"]} for s in snaps[-12:]],
        },
        "swap_ui_comparison": {
            "reference_url": SWAP_UI_URL,
            "operator_reported_swap_price": OPERATOR_REPORTED_SWAP_PRICE,
            "api_bdag_price": api_price,
            "delta_pct_api_vs_swap": delta_vs_swap,
            "note": "Positive delta = portal API value is HIGHER than the live swap UI value.",
        },
        "stale_evidence": stale_evidence,
        "stale_verdict": ("STALE/UNRELIABLE" if stale_evidence else "no obvious staleness in reference prices"),
        "recommendation": recommendation,
        "note": "Read-only diagnostic. Portal-feed behavior NOT modified (per instruction).",
    }
