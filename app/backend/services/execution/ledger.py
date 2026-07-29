"""E4.6 Part B — Production Ledger & Profit Accounting (shadow-derived, READ-ONLY).

Builds a full, spreadsheet-style accounting record for every recorded SHADOW
cycle: investment → portal buy → BDAG acquired → gas/transfer → exchange deposit
qty → sell fills (MODELED across the live bid ladder) → trading fee → withdrawal
fee → wallet received → net profit → ROI. Aggregates daily / weekly / monthly
PnL and exports CSV + JSON.

Sell fills are MODELED by replaying each cycle's quantity through the live order
book at compute time (or, if the venue book is unavailable, from the cycle's
recorded realized spread). Clearly labelled per row. No real fills, no fund
movement — shadow evidence only.
"""
import csv
import io
from datetime import datetime

from engines.spread import vwap_for_qty
from services import db
from services.collector import collector
from services.execution.fees import get_fees, taker_pct, usdt_withdrawal_usd

LEDGER_FIELDS = [
    "cycle_id", "completed_at", "route_name", "sell_venue", "investment_usd",
    "portal_buy_price", "bdag_acquired", "gas_fee_usd", "transfer_fee_base",
    "exchange_deposit_qty", "weighted_sell_price", "fill_levels", "gross_proceeds_usd",
    "trading_fee_usd", "withdrawal_fee_usd", "wallet_received_usd",
    "net_profit_usd", "roi_pct", "fills_source",
]


def _fill_ladder(bids, qty):
    fills, filled, cost = [], 0.0, 0.0
    for price, q in bids:
        if filled >= qty - 1e-12:
            break
        take = min(q, qty - filled)
        if take <= 0:
            continue
        filled += take
        cost += take * price
        fills.append({"price": price, "qty": round(take, 6), "quote": round(take * price, 4)})
    vwap = cost / filled if filled > 0 else None
    return fills, filled, vwap


def _completed_at(c):
    for h in reversed(c.get("history", [])):
        if h.get("state") == "COMPLETE":
            return h.get("ts")
    return c.get("updated_at")


async def _ledger_entry(c, fees):
    venue = c.get("sell_venue") or "—"
    taker = taker_pct(fees, venue)
    buy_price = c.get("buy_price_at_open") or c.get("bdag_price")
    investment = c.get("size_usd") or 0.0
    bdag_acquired = c.get("qty_base") or (investment / buy_price if buy_price else 0.0)
    transfer_base = fees["bdag_transfer_fee_base"]
    gas = fees["purchase_gas_usd"]
    usdt_wd = usdt_withdrawal_usd(fees, venue)
    deposit_qty = max(bdag_acquired - transfer_base, 0.0)

    # MODELED sell — replay deposit_qty through the live bid ladder of the sell venue.
    rcache = collector.cache.get(c.get("route_id"), {})
    ob = (rcache.get(venue) or {}).get("orderbook")
    fills, source = [], None
    vwap = None
    if ob and ob.get("bids"):
        fills, filled, vwap = _fill_ladder(ob["bids"], deposit_qty)
        if vwap is not None and filled >= deposit_qty * 0.999:
            source = "modeled_live_book"
        else:
            vwap = None
    if vwap is None:
        # fallback: use the cycle's recorded realized spread to imply a sell price
        rn = c.get("realized_net_pct")
        if rn is not None and buy_price:
            vwap = buy_price * (1 + rn / 100)
        else:
            vwap = (ob["bids"][0][0] if (ob and ob.get("bids")) else buy_price)
        fills = [{"price": round(vwap, 8), "qty": round(deposit_qty, 6),
                  "quote": round(vwap * deposit_qty, 4)}]
        source = "modeled_recorded_spread"

    gross = deposit_qty * vwap
    trading_fee = gross * taker / 100
    wallet_received = gross - trading_fee - usdt_wd
    net_profit = wallet_received - (bdag_acquired * buy_price + gas) if buy_price else None
    roi = (net_profit / investment * 100) if (net_profit is not None and investment) else None

    return {
        "cycle_id": c["id"], "completed_at": _completed_at(c),
        "route_name": c.get("route_name"), "sell_venue": venue,
        "investment_usd": round(investment, 4),
        "portal_buy_price": round(buy_price, 8) if buy_price else None,
        "bdag_acquired": round(bdag_acquired, 4),
        "gas_fee_usd": round(gas, 4), "transfer_fee_base": transfer_base,
        "exchange_deposit_qty": round(deposit_qty, 4),
        "weighted_sell_price": round(vwap, 8) if vwap else None,
        "fills": fills, "fill_levels": len(fills),
        "gross_proceeds_usd": round(gross, 4),
        "trading_fee_usd": round(trading_fee, 4),
        "withdrawal_fee_usd": round(usdt_wd, 4),
        "wallet_received_usd": round(wallet_received, 4),
        "net_profit_usd": round(net_profit, 4) if net_profit is not None else None,
        "roi_pct": round(roi, 3) if roi is not None else None,
        "recorded_realized_pnl_usd": c.get("realized_shadow_pnl_quote"),
        "fills_source": source,
    }


def _period_keys(iso):
    try:
        d = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None, None, None
    iso_year, iso_week, _ = d.isocalendar()
    return d.strftime("%Y-%m-%d"), f"{iso_year}-W{iso_week:02d}", d.strftime("%Y-%m")


def _aggregate(entries):
    daily, weekly, monthly = {}, {}, {}
    for e in entries:
        day, week, month = _period_keys(e["completed_at"])
        np_ = e["net_profit_usd"] or 0
        inv = e["investment_usd"] or 0
        for bucket, key in ((daily, day), (weekly, week), (monthly, month)):
            if key is None:
                continue
            g = bucket.setdefault(key, {"period": key, "cycles": 0, "investment_usd": 0.0,
                                        "net_profit_usd": 0.0})
            g["cycles"] += 1
            g["investment_usd"] = round(g["investment_usd"] + inv, 4)
            g["net_profit_usd"] = round(g["net_profit_usd"] + np_, 4)
    def _finish(b):
        rows = sorted(b.values(), key=lambda r: r["period"])
        for r in rows:
            r["roi_pct"] = round(r["net_profit_usd"] / r["investment_usd"] * 100, 3) if r["investment_usd"] else None
        return rows
    return _finish(daily), _finish(weekly), _finish(monthly)


async def build_ledger(limit: int = 1000) -> dict:
    fees = await get_fees()
    cycles = await db.execution_cycles.find(
        {"mode": "shadow", "state": "COMPLETE"}, {"_id": 0},
        sort=[("created_at", -1)]).to_list(limit)
    entries = [await _ledger_entry(c, fees) for c in cycles]
    daily, weekly, monthly = _aggregate(entries)
    total_net = round(sum(e["net_profit_usd"] or 0 for e in entries), 4)
    total_inv = round(sum(e["investment_usd"] or 0 for e in entries), 4)
    total_fees = round(sum((e["gas_fee_usd"] or 0) + (e["trading_fee_usd"] or 0)
                           + (e["withdrawal_fee_usd"] or 0)
                           + (e["transfer_fee_base"] or 0) * (e["portal_buy_price"] or 0)
                           for e in entries), 4)
    return {
        "phase": "E4.6 — Production Ledger (shadow-derived, modeled fills)",
        "fees_used": fees,
        "summary": {
            "cycles": len(entries), "total_investment_usd": total_inv,
            "total_net_profit_usd": total_net,
            "total_fees_usd": total_fees,
            "overall_roi_pct": round(total_net / total_inv * 100, 3) if total_inv else None,
            "avg_net_per_cycle_usd": round(total_net / len(entries), 4) if entries else None,
        },
        "entries": entries,
        "daily_pnl": daily, "weekly_pnl": weekly, "monthly_pnl": monthly,
        "note": "Shadow-derived accounting. Sell fills are MODELED (live book or recorded spread). "
                "No real fills, no fund movement.",
    }


async def export_csv(limit: int = 1000) -> str:
    led = await build_ledger(limit)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=LEDGER_FIELDS, extrasaction="ignore")
    w.writeheader()
    for e in led["entries"]:
        w.writerow(e)
    # trailing aggregate rows
    buf.write("\n# DAILY PnL\nperiod,cycles,investment_usd,net_profit_usd,roi_pct\n")
    for r in led["daily_pnl"]:
        buf.write(f"{r['period']},{r['cycles']},{r['investment_usd']},{r['net_profit_usd']},{r['roi_pct']}\n")
    return buf.getvalue()
