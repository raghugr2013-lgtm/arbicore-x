"""BlockDAG Buy-Price Source Audit (READ-ONLY).

Concurrently polls every reachable BlockDAG buy-price source, compares them
side-by-side, identifies which one ArbiCore actually consumes for Fresh-Cycle
ROI, and explains why. Also persists operator-recorded EMPIRICAL test quotes
(e.g. "$50 USDT → N BDAG received → effective price = 50/N") so the operator
can pin the actual UI-displayed price against every other source.

No purchases, no fund movement, no execution. Pure source-level transparency.
"""
import asyncio
import logging
import statistics
from datetime import datetime, timezone

import httpx

from core.models import new_id, now_iso
from services import db
from services.execution import buy_price as bp_resolver
from services.portal_price import portal_price

logger = logging.getLogger("buy_price_audit")

EMPIRICAL_COLL = "buy_price_empirical_quotes"

# Sources the swap page (purchase3.blockdag.network/swap) actually hits.
SOURCES = [
    {
        "id": "sw_api_getinfo",
        "label": "sw-api/getInfo · bdagPrice (Live Swap API)",
        "url": "https://sw-api.blockdag.network/getInfo",
        "type": "api",
        "consumed_by_arbicore": True,
        "extract": "data.bdagPrice",
    },
    {
        "id": "public_current_price",
        "label": "api.blockdagnetwork.io · current_price (Public Reference)",
        "url": "https://api.blockdagnetwork.io/api/v2/base/public/current_price",
        "type": "api",
        "consumed_by_arbicore": False,
        "extract": "price",
    },
    {
        "id": "presale_root",
        "label": "preapi/root · coin.tokenPrice (Presale Stage API)",
        "url": "https://preapi.blockdag.network/root",
        "type": "api",
        "consumed_by_arbicore": False,
        "extract": "coin.tokenPrice",
    },
]

CRITICAL_PCT = 5.0   # |Δ| ≥ 5% vs sw-api/getInfo = critical mismatch flag
REQUEST_TIMEOUT_S = 12


async def _fetch_one(client: httpx.AsyncClient, src: dict) -> dict:
    started = datetime.now(timezone.utc)
    try:
        r = await client.get(src["url"], headers={
            "User-Agent": "ArbiCore/audit (read-only price discovery)",
            "Referer": "https://purchase3.blockdag.network/",
        })
        ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 1)
        r.raise_for_status()
        payload = r.json()
        # extract nested path like "data.bdagPrice" or "coin.tokenPrice"
        value = payload
        for key in src["extract"].split("."):
            value = value.get(key) if isinstance(value, dict) else None
            if value is None:
                break
        try:
            price = float(value) if value is not None else None
        except (TypeError, ValueError):
            price = None
        extras = {}
        if src["id"] == "presale_root":
            coin = (payload or {}).get("coin") or {}
            extras["stage"] = coin.get("stage")
            extras["next_stage_price"] = coin.get("nextStageTokenPrice")
            ob = (payload or {}).get("coin", {}).get("orderBook") or payload.get("orderBook") or []
            if ob:
                latest = ob[:5]
                eff = []
                for o in latest:
                    try:
                        usd = float(o.get("pay_usd_amount") or 0)
                        bdag = float(o.get("bought_token_amount") or 0)
                        if usd > 0 and bdag > 0:
                            eff.append(usd / bdag)
                    except (TypeError, ValueError):
                        continue
                if eff:
                    extras["implied_price_from_latest_orders"] = round(statistics.mean(eff), 12)
                    extras["latest_orders_sample"] = latest[:3]
        return {
            "id": src["id"], "label": src["label"], "url": src["url"],
            "value": price, "consumed_by_arbicore": src["consumed_by_arbicore"],
            "timestamp": now_iso(), "latency_ms": ms,
            "ok": price is not None and price > 0, "error": None,
            "extras": extras or None,
            "extract_path": src["extract"],
        }
    except Exception as e:
        return {
            "id": src["id"], "label": src["label"], "url": src["url"],
            "value": None, "consumed_by_arbicore": src["consumed_by_arbicore"],
            "timestamp": now_iso(), "latency_ms": None,
            "ok": False, "error": str(e)[:200], "extras": None,
            "extract_path": src["extract"],
        }


async def _fetch_live_sources() -> list:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        return await asyncio.gather(*(_fetch_one(client, s) for s in SOURCES))


async def _bdag_route():
    return (await db.routes_col.find_one(
        {"purchase.asset": "BDAG", "exit.exchange": "coinstore"}, {"_id": 0})
            or await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0}))


async def _position_cost_basis(route):
    if not route:
        return None
    pos = await bp_resolver.active_position(route["id"])
    if not pos:
        return None
    return {
        "id": pos.get("id"), "buy_price": pos.get("buy_price"),
        "qty": pos.get("qty"), "status": pos.get("status"),
        "created_at": pos.get("created_at"),
    }


async def record_empirical(investment_usd: float, bdag_received: float,
                           pay_token: str = "USDT", note: str = None,
                           reported_ui_price: float = None,
                           source: str = "operator_test") -> dict:
    if investment_usd <= 0 or bdag_received <= 0:
        raise ValueError("investment_usd and bdag_received must both be > 0")
    effective_price = round(investment_usd / bdag_received, 12)
    doc = {
        "id": new_id(),
        "investment_usd": float(investment_usd),
        "bdag_received": float(bdag_received),
        "effective_price": effective_price,
        "pay_token": pay_token,
        "reported_ui_price": (float(reported_ui_price) if reported_ui_price is not None else None),
        "source": source,
        "note": note,
        "created_at": now_iso(),
    }
    await db.db[EMPIRICAL_COLL].insert_one(dict(doc))
    return doc


async def list_empirical(limit: int = 20) -> list:
    return await db.db[EMPIRICAL_COLL].find({}, {"_id": 0},
                                            sort=[("created_at", -1)]).to_list(max(1, min(limit, 200)))


async def _empirical_summary() -> dict:
    docs = await list_empirical(20)
    if not docs:
        return {"count": 0, "avg_effective_price": None, "median_effective_price": None,
                "latest_effective_price": None, "latest_ui_price": None,
                "first_at": None, "last_at": None}
    eff = [d["effective_price"] for d in docs]
    ui = [d["reported_ui_price"] for d in docs if d.get("reported_ui_price")]
    return {
        "count": len(docs),
        "avg_effective_price": round(statistics.mean(eff), 12),
        "median_effective_price": round(statistics.median(eff), 12),
        "min_effective_price": min(eff), "max_effective_price": max(eff),
        "latest_effective_price": docs[0]["effective_price"],
        "latest_ui_price": ui[0] if ui else None,
        "first_at": docs[-1].get("created_at"),
        "last_at": docs[0].get("created_at"),
        "samples": docs,
    }


def _pct_diff(a, b):
    if a is None or b is None or b == 0:
        return None
    return round((a - b) / b * 100, 3)


async def build() -> dict:
    """Side-by-side audit of every reachable BlockDAG buy-price source."""
    route = await _bdag_route()
    live = await _fetch_live_sources()
    pf = portal_price.status_brief()
    position = await _position_cost_basis(route)
    empirical = await _empirical_summary()

    # Identify the price ArbiCore actually consumes for Fresh-Cycle ROI.
    # This mirrors `arbitrage_intel.analyze()` → `bp_resolver.as_fresh_resolution()`.
    arbicore_resolution = None
    if route:
        full = await bp_resolver.resolve(route)
        arbicore_resolution = bp_resolver.as_fresh_resolution(full)
    arbicore_price = (arbicore_resolution or {}).get("price")
    arbicore_source = (arbicore_resolution or {}).get("source_label")

    # The 5 prices the operator brief asks for, in order.
    sw_api = next((s for s in live if s["id"] == "sw_api_getinfo"), {})
    public_ref = next((s for s in live if s["id"] == "public_current_price"), {})
    presale = next((s for s in live if s["id"] == "presale_root"), {})

    primary = [
        {"slot": 1, "label": "Live Swap UI (purchase3.blockdag.network/swap)",
         "value": empirical.get("latest_ui_price"),
         "source_url": "https://purchase3.blockdag.network/swap",
         "timestamp": empirical.get("last_at"),
         "note": ("Wallet-gated — cannot fetch programmatically. Operator records what the UI displays "
                  "alongside each empirical $X test (see Empirical Quotes panel)."
                  if empirical.get("latest_ui_price") is None
                  else "Recorded by operator from the swap UI during the latest empirical test."),
         "type": "operator_attested",
         "used_for_roi": False},
        {"slot": 2, "label": "sw-api/getInfo · bdagPrice (Live Swap API)",
         "value": sw_api.get("value"), "source_url": sw_api.get("url"),
         "timestamp": sw_api.get("timestamp"), "latency_ms": sw_api.get("latency_ms"),
         "ok": sw_api.get("ok"), "type": "live_api",
         "used_for_roi": True,
         "note": "Live JSON quote returned by the swap portal’s public API. Polled every 60s by the "
                 "portal_price service and cached as the Portal Feed used by ArbiCore."},
        {"slot": 3, "label": "Portal Feed (ArbiCore cache · sw-api/getInfo)",
         "value": pf.get("bdag_price"), "source_url": pf.get("source"),
         "timestamp": pf.get("fetched_at"),
         "age_s": bp_resolver._age_s(pf.get("fetched_at")),
         "stale": pf.get("stale"), "type": "cached_api",
         "used_for_roi": (arbicore_source == "Live Portal Feed"),
         "note": ("Cached copy of sw-api/getInfo. Considered stale after 300s. "
                  "STALE = excluded from buy-price resolution." if pf.get("stale")
                  else "Fresh cache — this is what arbitrage_intel actually reads.")},
        {"slot": 4, "label": "Position Cost Basis (active BDAG position)",
         "value": (position or {}).get("buy_price"),
         "source_url": None, "timestamp": (position or {}).get("created_at"),
         "type": "ledger_position",
         "used_for_roi": False,
         "note": ("Active position id={id} status={s} qty={q}".format(
                     id=(position or {}).get("id", "—")[:8], s=(position or {}).get("status"),
                     q=(position or {}).get("qty"))
                  if position else "No active (non-settled) BDAG position. INFORMATIONAL ONLY — "
                                  "never used for Fresh-Cycle ROI (it’s for Existing-Position ROI).")},
        {"slot": 5, "label": "Effective Executable Price (empirical · operator test)",
         "value": empirical.get("latest_effective_price"),
         "source_url": None,
         "timestamp": empirical.get("last_at"),
         "type": "operator_attested",
         "used_for_roi": False,
         "note": ("Latest test: ${inv} → {bd} BDAG ⇒ ${ep}/BDAG. Average over last {n} tests: ${avg}."
                  .format(inv=empirical.get("samples", [{}])[0].get("investment_usd"),
                          bd=empirical.get("samples", [{}])[0].get("bdag_received"),
                          ep=empirical.get("latest_effective_price"),
                          n=empirical.get("count"),
                          avg=empirical.get("avg_effective_price"))
                  if empirical.get("count") else
                  "No empirical tests yet. Use the form below: input the USDT amount you paid and the "
                  "exact BDAG amount the wallet received. We compute the effective price.")},
    ]

    # Extra observability — secondary sources (not in the 5 mandated slots, but visible).
    secondary = [
        {"label": "api.blockdagnetwork.io · current_price (Public Reference)",
         "value": public_ref.get("value"), "source_url": public_ref.get("url"),
         "timestamp": public_ref.get("timestamp"), "latency_ms": public_ref.get("latency_ms"),
         "ok": public_ref.get("ok"), "type": "live_api",
         "note": "Marketing / public index. Not consumed by ArbiCore. Surfaced for cross-check only."},
        {"label": "preapi/root · coin.tokenPrice (Presale Stage API)",
         "value": presale.get("value"), "source_url": presale.get("url"),
         "timestamp": presale.get("timestamp"), "latency_ms": presale.get("latency_ms"),
         "ok": presale.get("ok"), "type": "live_api",
         "extras": presale.get("extras"),
         "note": ("Presale stage data. tokenPrice is the per-presale-token unit. "
                  "Implied price from latest orderBook entries ≈ {0}".format(
                     (presale.get("extras") or {}).get("implied_price_from_latest_orders"))
                  if (presale.get("extras") or {}).get("implied_price_from_latest_orders")
                  else "Presale stage data — not consumed by ArbiCore.")},
    ]

    # --- Mismatch detection ---------------------------------------------------
    ref = sw_api.get("value")
    discrepancies = []
    for row in primary + secondary:
        v = row.get("value")
        if v is None or v == ref:
            continue
        diff = _pct_diff(v, ref)
        if diff is None:
            continue
        sev = "critical" if abs(diff) >= CRITICAL_PCT else "informational"
        discrepancies.append({
            "vs": "sw-api/getInfo · bdagPrice",
            "source": row["label"],
            "source_value": v,
            "ref_value": ref,
            "delta_pct": diff,
            "severity": sev,
        })

    ui_vs_api_delta = next((d["delta_pct"] for d in discrepancies
                            if "Live Swap UI" in d["source"]), None)
    arbicore_explanation = _explain_arbicore_pick(arbicore_resolution, sw_api, position, pf)

    return {
        "phase": "BlockDAG Buy-Price Source Audit (read-only)",
        "generated_at": now_iso(),
        "route_id": (route or {}).get("id"),
        "route_name": (route or {}).get("name"),
        "primary_sources": primary,
        "secondary_sources": secondary,
        "price_used_for_roi": {
            "value": arbicore_price,
            "source": arbicore_source,
            "explanation": arbicore_explanation,
            "buy_price_resolution": arbicore_resolution,
        },
        "discrepancies": discrepancies,
        "discrepancy_summary": {
            "critical_count": sum(1 for d in discrepancies if d["severity"] == "critical"),
            "informational_count": sum(1 for d in discrepancies if d["severity"] == "informational"),
            "ui_vs_sw_api_pct": ui_vs_api_delta,
            "ui_vs_sw_api_severity": ("critical" if (ui_vs_api_delta is not None
                                                    and abs(ui_vs_api_delta) >= CRITICAL_PCT)
                                       else ("informational" if ui_vs_api_delta is not None else None)),
        },
        "empirical_quotes": empirical,
        "note": ("Wallet-gated UI: the Live Swap UI price cannot be fetched programmatically. "
                 "Record it via the empirical-test form below — that pins the actual UI-displayed "
                 "price against every other source. No purchases, no fund movement."),
    }


def _explain_arbicore_pick(resolution, sw_api, position, pf):
    if not resolution:
        return "No BDAG route configured. ArbiCore would refuse to evaluate."
    chain = (resolution.get("chain") or [])
    won = next((c for c in chain if c.get("won")), None)
    pos_excluded = next((c for c in chain if c["source"] == "position"), None)
    bits = []
    bits.append("ArbiCore consumes the FRESH-CYCLE buy-price resolution (which excludes the held-position "
                "cost basis by design — Existing-Position ROI is informational only).")
    bits.append("Precedence: " + " → ".join(resolution.get("precedence") or []))
    if won and won["source"] == "portal":
        bits.append("Winner: **Live Portal Feed** (sw-api/getInfo @ {pt}, age {a}s, stale={st}) — the live "
                    "API quote is the only freshly-available source with sub-300s freshness, no manual override "
                    "is set, and a manual fallback would only kick in if the live API failed."
                    .format(pt=pf.get("fetched_at"), a=bp_resolver._age_s(pf.get("fetched_at")),
                            st=pf.get("stale")))
    elif won and won["source"] == "manual_override":
        bits.append("Winner: **Manual Override** — operator explicitly pinned this buy price; live feed is "
                    "ignored until override is cleared.")
    elif won and won["source"] == "manual_fallback":
        bits.append("Winner: **Manual Fallback** — live feed unavailable, falling back to the stored "
                    "manual_buy.price on the route.")
    else:
        bits.append("No winner — no available source. Fresh-Cycle ROI is unavailable.")
    if pos_excluded and pos_excluded.get("available"):
        bits.append("Position Cost Basis IS available but explicitly EXCLUDED from Fresh-Cycle pricing "
                    "(it would inflate ROI by ignoring the real cost of replacing the position).")
    return "\n".join("- " + b for b in bits)


async def status() -> dict:
    return await build()
