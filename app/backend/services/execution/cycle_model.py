"""Real Arbitrage Cycle Model (READ-ONLY).

Composes the existing arbitrage_intel + price_verification + bdag_transfers
outputs into the EXACT operator workflow:

    USDT/BNB → BlockDAG Live Swap → Receive BDAG → Transfer BDAG to Coinstore
    → Sell BDAG → Receive USDT → Withdraw USDT (BEP20) → Wallet Receives USDT

with the full Executable Opportunity Calculation:
  Buy Price Used / Sell Price Used / Weighted Sell Price / Fees Used (per-leg)
  → Gross Profit / Total Fees / Net Profit / ROI %.

No execution, no orders, no fund movement. Pure transparency.
"""
from core.models import now_iso
from services import db
from services.execution import (arbitrage_intel, bdag_transfers, opportunity_gate,
                                price_verification)
from services.execution.fees import get_effective_fees, taker_pct, usdt_withdrawal_usd


async def _resolve_bdag_route(route_id=None):
    if route_id:
        return await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    # prefer a Coinstore-exit BDAG route, else any BDAG route
    r = await db.routes_col.find_one(
        {"purchase.asset": "BDAG", "exit.exchange": "coinstore"}, {"_id": 0})
    return r or await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0})


def _round(v, n=6):
    if v is None:
        return None
    try:
        return round(float(v), n)
    except (TypeError, ValueError):
        return None


async def build(route_id=None) -> dict:
    route = await _resolve_bdag_route(route_id)
    if not route:
        return {"available": False, "note": "No BDAG route configured."}
    rid = route["id"]
    intel = await arbitrage_intel.analyze(rid)
    pv = await price_verification.build(rid)
    gate = await opportunity_gate.evaluate(rid)
    fees = await get_effective_fees()
    transfer_ev = await bdag_transfers.rolling_average()

    venue = intel.get("sell_venue") or "coinstore"
    buy_price = intel.get("buy_price")
    best_bid = intel.get("best_bid")
    rec = intel.get("recommended") or {}
    weighted_sell = rec.get("weighted_sell_price")
    market = pv.get("market_data") or {}
    dual_roi = intel.get("dual_roi") or {
        "authority": "fresh_cycle",
        "note": "Fresh Cycle ROI is the sole execution authority.",
    }

    # --- Executable Opportunity Calculation ----------------------------------
    taker = taker_pct(fees, venue)
    usdt_wd = usdt_withdrawal_usd(fees, venue)
    transfer_base = fees["bdag_transfer_fee_base"]
    purchase_gas = fees["purchase_gas_usd"]

    investment = rec.get("investment_usd")
    bdag_bought = rec.get("buy_qty_base")
    bdag_sold = rec.get("sell_qty_base")
    gross_proceeds = rec.get("gross_proceeds_usd")
    trading_fee = rec.get("trading_fee_usd")
    net_profit = rec.get("net_profit_usd")
    wallet_received = rec.get("wallet_received_usd")

    total_fees_usd = None
    if trading_fee is not None:
        # convert transfer-gas-in-BDAG into USD using the live swap buy price
        transfer_fee_usd = (transfer_base or 0) * (buy_price or 0)
        total_fees_usd = round(
            (trading_fee or 0) + (usdt_wd or 0) + (purchase_gas or 0) + transfer_fee_usd, 6)
    else:
        transfer_fee_usd = None

    executable_calculation = {
        "available": rec.get("roi_pct") is not None,
        "buy_price_used": _round(buy_price, 8),
        "buy_source": (intel.get("buy_price_resolution") or {}).get("source_label")
        or intel.get("buy_price_source"),
        "sell_price_used": _round(best_bid, 8),
        "sell_source": f"{venue.upper()} Best Bid" if venue else None,
        "weighted_sell_price": _round(weighted_sell, 8),
        "weighted_sell_source": "Multi-level VWAP across consumed bid levels",
        "fees_used": {
            "swap_fee_usd": 0.0,                # BlockDAG swap contract takes no extra fee beyond BSC gas
            "purchase_gas_usd": _round(purchase_gas, 6),
            "bdag_transfer_fee_bdag": _round(transfer_base, 9),
            "bdag_transfer_fee_usd": _round(transfer_fee_usd, 6),
            "trading_fee_usd": _round(trading_fee, 6),
            "trading_fee_pct": taker,
            "usdt_withdrawal_fee_usd": _round(usdt_wd, 6),
            "other_fees_usd": 0.0,
            "bdag_transfer_fee_evidence": fees.get("bdag_transfer_fee_source"),
        },
        "gross_profit_usd": _round((gross_proceeds or 0) - (investment or 0), 6)
        if (gross_proceeds is not None and investment is not None) else None,
        "total_fees_usd": _round(total_fees_usd, 6),
        "net_profit_usd": _round(net_profit, 6),
        "roi_pct": rec.get("roi_pct"),
        "investment_usd": _round(investment, 6),
        "wallet_received_usd": _round(wallet_received, 6),
        "size_basis": ("cert-capped recommendation" if rec.get("capped_to_cert_max")
                       else (f"{rec.get('utilization_pct')}% of profitable depth"
                             if rec.get("utilization_pct") else None)),
    }

    # --- Step-by-step cycle ladder -------------------------------------------
    bdag_after_transfer = (bdag_bought - (transfer_base or 0)) if bdag_bought else None
    steps = [
        {"step": 1, "leg": "Operator capital",
         "in": {"asset": "USDT/BNB on wallet", "amount_usd": _round(investment, 6)},
         "out": {"asset": "USDT/BNB ready to swap", "amount_usd": _round(investment, 6)},
         "fees": {"purchase_gas_usd": _round(purchase_gas, 6)},
         "source": "Operator wallet (read-only — no fund movement)"},
        {"step": 2, "leg": "BlockDAG Live Swap",
         "in": {"asset": "USDT/BNB", "amount_usd": _round((investment or 0) - (purchase_gas or 0), 6)},
         "out": {"asset": "BDAG (in wallet)", "amount_bdag": _round(bdag_bought, 6),
                 "price_used_usd_per_bdag": _round(buy_price, 8)},
         "fees": {"swap_fee_usd": 0.0, "purchase_gas_usd": _round(purchase_gas, 6)},
         "source": "purchase3.blockdag.network/swap (sw-api/getInfo)"},
        {"step": 3, "leg": "Transfer BDAG to Coinstore (BDAG network)",
         "in": {"asset": "BDAG (in wallet)", "amount_bdag": _round(bdag_bought, 6)},
         "out": {"asset": "BDAG (at Coinstore)", "amount_bdag": _round(bdag_after_transfer, 6)},
         "fees": {"bdag_transfer_fee_bdag": _round(transfer_base, 9),
                  "bdag_transfer_fee_usd": _round(transfer_fee_usd, 6),
                  "evidence": fees.get("bdag_transfer_fee_source"),
                  "evidence_count": transfer_ev.get("count")},
         "constraints": {"coinstore_min_deposit_bdag": 3703,
                         "meets_minimum": (bdag_after_transfer is not None
                                           and bdag_after_transfer >= 3703)},
         "source": "BDAG network — measured rolling average of real transfers"},
        {"step": 4, "leg": "Sell BDAG on Coinstore",
         "in": {"asset": "BDAG (at Coinstore)", "amount_bdag": _round(bdag_sold, 6)},
         "out": {"asset": "USDT (Coinstore balance)", "amount_usd": _round(gross_proceeds, 6)},
         "fees": {"trading_fee_usd": _round(trading_fee, 6), "trading_fee_pct": taker,
                  "weighted_sell_price": _round(weighted_sell, 8),
                  "best_bid_used": _round(best_bid, 8)},
         "source": "Coinstore BDAG/USDT live order book (multi-level VWAP)"},
        {"step": 5, "leg": "Withdraw USDT (BEP20) to wallet",
         "in": {"asset": "USDT (Coinstore balance)",
                "amount_usd": _round((gross_proceeds or 0) - (trading_fee or 0), 6)},
         "out": {"asset": "USDT (in wallet)", "amount_usd": _round(wallet_received, 6)},
         "fees": {"usdt_withdrawal_fee_usd": _round(usdt_wd, 6),
                  "network": "BEP20"},
         "source": "Coinstore USDT withdrawal page (operator-verified)"},
        {"step": 6, "leg": "Wallet receives USDT",
         "in": {"asset": "USDT (wallet)", "amount_usd": _round(wallet_received, 6)},
         "out": {"asset": "USDT (wallet)", "amount_usd": _round(wallet_received, 6),
                 "net_profit_usd": _round(net_profit, 6),
                 "roi_pct": rec.get("roi_pct")},
         "fees": {}, "source": "Operator wallet (terminal point)"},
    ]

    return {
        "phase": "Real Arbitrage Cycle Model (read-only)",
        "generated_at": now_iso(),
        "available": rec.get("roi_pct") is not None,
        "route_id": rid, "route_name": route.get("name"), "sell_venue": venue,
        "blockdag_live_swap": pv.get("blockdag_live_swap"),
        "coinstore_market_intel": {
            **market,
            "weighted_sell_price": _round(weighted_sell, 8),
            "total_executable_liquidity_usd": (market or {}).get("total_profitable_bid_depth_usd"),
            "total_executable_liquidity_base": (market or {}).get("total_profitable_bid_depth_base"),
        },
        "executable_opportunity_calculation": executable_calculation,
        "dual_roi": dual_roi,
        "cycle_steps": steps,
        "verdict": gate.get("gate_verdict"),
        "verdict_reasons": gate.get("reasons"),
        "freshness": gate.get("freshness"),
        "executable_sizing": intel.get("executable_sizing"),
        "fee_evidence": {
            "bdag_transfer_source": fees.get("bdag_transfer_fee_source"),
            "bdag_transfer_evidence_count": fees.get("bdag_transfer_fee_evidence_count"),
            "trading_fee_source": "Coinstore — operator-verified (Exchange Sourced)",
            "usdt_withdrawal_source": "Coinstore — operator-verified (Exchange Sourced)",
            "deposit_fee_source": "Coinstore — operator-verified, 4,000 BDAG deposit confirmed (Exchange Sourced)",
        },
        "note": "Read-only end-to-end cycle. The Safety Interlock, Fresh ROI authority, and Opportunity Gate logic "
                "are unchanged — this layer only EXPOSES the values they consume. No execution, no fund movement.",
    }
