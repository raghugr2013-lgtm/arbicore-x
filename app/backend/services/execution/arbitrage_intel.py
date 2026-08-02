"""E4.6 Part A — BDAG Arbitrage Intelligence Engine (READ-ONLY, no execution).

Composes the existing live order book + verified fee model into a single
decision surface that answers:
  • how much BDAG to buy
  • which buyer (bid) levels can be sold to profitably
  • the weighted average expected sell price (VWAP across multiple levels)
  • expected profit after ALL fees and slippage
  • the safest capital size per cycle

Sub-engines: Break-Even, Profitable Liquidity, Order-Book Consumption Simulator,
Liquidity-Aware Position Sizing, Smart Exit, Buyer Stability, GO/WAIT/NO-GO.

It NEVER assumes a single sell price — it simulates selling across the live bid
ladder and computes the weighted execution price. Liquidity utilization is
configurable (25/50/75/100%). No fund movement, no orders.
"""
import statistics

from engines.spread import vwap_for_qty
from services import db
from services.collector import collector
from services.execution import buy_price as bp_resolver
from services.execution import config, venue_registry
from services.execution.fees import get_fees, taker_pct, usdt_withdrawal_usd

UTILIZATIONS = [25, 50, 75, 100]


def _fill_ladder(bids, qty):
    """Walk the bid ladder selling `qty`; return per-level fills + VWAP."""
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
    exhausted = filled < qty * 0.999
    return fills, filled, vwap, exhausted


def _cycle_economics(sell_qty, buy_price, vwap, taker, fees, venue):
    """Full per-cycle accounting for selling `sell_qty` BDAG at `vwap`."""
    transfer_base = fees["bdag_transfer_fee_base"]
    gas = fees["purchase_gas_usd"]
    usdt_wd = usdt_withdrawal_usd(fees, venue)
    buy_qty = sell_qty + transfer_base                     # must buy a touch more to cover transfer gas
    investment = buy_qty * buy_price + gas
    gross_proceeds = sell_qty * vwap
    trading_fee = gross_proceeds * taker / 100
    wallet_received = gross_proceeds - trading_fee - usdt_wd
    net_profit = wallet_received - investment
    roi = (net_profit / investment * 100) if investment > 0 else None
    return {
        "sell_qty_base": round(sell_qty, 4), "buy_qty_base": round(buy_qty, 4),
        "investment_usd": round(investment, 4), "weighted_sell_price": round(vwap, 8),
        "gross_proceeds_usd": round(gross_proceeds, 4),
        "trading_fee_usd": round(trading_fee, 4), "withdrawal_fee_usd": round(usdt_wd, 4),
        "gas_fee_usd": round(gas, 4), "transfer_fee_base": transfer_base,
        "wallet_received_usd": round(wallet_received, 4),
        "net_profit_usd": round(net_profit, 4),
        "roi_pct": round(roi, 3) if roi is not None else None,
    }


def _max_safe_size(bids, prof_base, buy_price, taker, fees, venue, min_roi):
    """Largest sellable size whose net ROI still clears the floor (ROI ↓ as size ↑).

    'Maximum safe buy size before profitability degrades' — binary-searched over
    the profitable bid depth. Returns None if even a tiny clip is below floor."""
    if prof_base <= 0 or not bids or not buy_price:
        return None

    def roi_at(q):
        _, filled, vwap, _ = _fill_ladder(bids, q)
        if not vwap or filled <= 0:
            return None
        return _cycle_economics(filled, buy_price, vwap, taker, fees, venue)["roi_pct"]

    if (roi_at(prof_base * 0.01) or -1) < min_roi:
        return None
    r_full = roi_at(prof_base)
    if r_full is not None and r_full >= min_roi:
        best_q = prof_base
    else:
        lo, hi = 0.0, prof_base
        for _ in range(48):
            mid = (lo + hi) / 2
            r = roi_at(mid)
            if r is not None and r >= min_roi:
                lo = mid
            else:
                hi = mid
        best_q = lo
    _, filled, vwap, exhausted = _fill_ladder(bids, best_q)
    econ = _cycle_economics(filled, buy_price, vwap, taker, fees, venue)
    return {"max_safe_sell_qty_base": round(filled, 4),
            "max_safe_buy_usd": econ["investment_usd"],
            "weighted_sell_price": econ["weighted_sell_price"],
            "roi_pct": econ["roi_pct"], "book_exhausted": exhausted}


async def _select_sell_venue(route, rcache):
    """Prefer a gate-open venue by registry role; fall back to best live bid."""
    role_map = await venue_registry.get_role_map()
    candidates = []
    for ex in (route.get("comparison_exchanges") or [route["exit"]["exchange"]]):
        m = rcache.get(ex) or {}
        ob = m.get("orderbook")
        if not (ob and ob.get("bids")):
            continue
        gate = (m.get("fee") or {}).get("deposit_enabled")
        candidates.append({"venue": ex, "best_bid": ob["bids"][0][0],
                           "gate_open": gate is not False, "role": role_map.get(ex, "watch"),
                           "bids": ob["bids"]})
    if not candidates:
        return None
    role_rank = {"primary": 0, "backup": 1, "watch": 2, "disabled": 3}
    # Best execution: among gate-open venues pick the highest bid; role only breaks ties.
    candidates.sort(key=lambda c: (not c["gate_open"], -c["best_bid"], role_rank.get(c["role"], 9)))
    return candidates[0]


async def _buyer_stability(route_id, venue):
    snaps = await db.orderbook_snapshots.find(
        {"route_id": route_id, "exchange": venue}, {"_id": 0, "derived": 1, "ts": 1, "created_at": 1},
        sort=[("created_at", -1)]).to_list(24)
    bids_series = [s.get("derived", {}).get("best_bid") for s in snaps
                   if s.get("derived", {}).get("best_bid")]
    depth_series = [s.get("derived", {}).get("bid_depth_quote_2pct") for s in snaps
                    if s.get("derived", {}).get("bid_depth_quote_2pct")]

    def _cv(xs):
        if len(xs) < 2:
            return None
        m = statistics.mean(xs)
        return round(statistics.pstdev(xs) / m * 100, 3) if m else None

    cv_bid = _cv(bids_series)
    cv_depth = _cv(depth_series)
    if cv_bid is None:
        label = "insufficient_history"
    elif cv_bid < 0.5 and (cv_depth is None or cv_depth < 25):
        label = "STABLE"
    elif cv_bid < 2.0:
        label = "MODERATE"
    else:
        label = "VOLATILE"
    return {
        "samples": len(snaps), "best_bid_cv_pct": cv_bid, "depth_cv_pct": cv_depth,
        "avg_depth_quote_2pct": round(statistics.mean(depth_series), 2) if depth_series else None,
        "label": label,
        "note": "Coefficient of variation of best bid & 2% bid depth over recent snapshots.",
    }


def _reference_econ(bids, buy_price, taker, fees, venue, cap_usd):
    """Representative fresh-cycle economics at the cert-cap notional regardless of
    profitability — so a fresh ROI number (even if negative) can be shown instead
    of a blank. Does NOT change the GO/WAIT/NO_GO verdict (that uses profitable depth)."""
    if not buy_price or not bids or not cap_usd:
        return None
    total_base = sum(q for _, q in bids)
    qty = min(cap_usd / buy_price, total_base)
    if qty <= 0:
        return None
    _, filled, vwap, _ = _fill_ladder(bids, qty)
    if not vwap:
        return None
    return _cycle_economics(filled, buy_price, vwap, taker, fees, venue)


def _position_roi(bids, position_price, taker, fees, venue, cap_usd):
    """Existing Position ROI — liquidate already-held BDAG (cost basis) into the
    live book. Independent of fresh-cycle viability; sized to the lesser of the
    cap notional and the profitable depth at the position's break-even."""
    if not position_price or not bids:
        return None
    be = position_price / (1 - taker / 100)
    prof_base = sum(q for p, q in bids if p >= be)
    if prof_base <= 0:
        return None
    cap_qty = (cap_usd / position_price) if (cap_usd and position_price) else 0
    qty = min(cap_qty, prof_base) if cap_qty else prof_base
    _, filled, vwap, _ = _fill_ladder(bids, qty)
    if not vwap:
        return None
    return _cycle_economics(filled, position_price, vwap, taker, fees, venue)


def _executable_sizing(limits, recommended, max_safe_buy):
    """Reconcile the CERTIFIED per-cycle size with the REAL minimum purchase the
    BlockDAG Live Swap will accept. A recommendation below the live-swap minimum
    is not actionable — the smallest placeable live cycle is the minimum itself,
    so the sizing engine never recommends a size that cannot actually be placed."""
    cert_size = limits["max_cycle_usd"]
    min_exec = limits.get("min_executable_purchase_usd") or 0
    rec_capped = (recommended or {}).get("investment_usd")
    msb = (max_safe_buy or {}).get("max_safe_buy_usd")
    base = rec_capped if rec_capped is not None else cert_size
    actual = max(base, min_exec) if min_exec else base
    placeable = True if not min_exec else (msb is None or min_exec <= msb + 1e-9)
    min_over_cap = bool(min_exec and min_exec > cert_size + 1e-9)
    notes = []
    if min_over_cap:
        notes.append(f"BlockDAG Live Swap minimum ${min_exec} EXCEEDS the ${cert_size} certification cap — a live "
                     f"cycle cannot be both ≥ the swap minimum and ≤ the certified size. Raise the certification "
                     f"cap (with evidence) before any live execution.")
    if rec_capped is not None and min_exec and rec_capped < min_exec - 1e-9:
        notes.append(f"Certified recommendation ${rec_capped} is below the ${min_exec} live-swap minimum — not "
                     f"actionable; smallest placeable cycle is ${min_exec}.")
    if not placeable:
        notes.append(f"Profitable depth supports only ~${msb}; the ${min_exec} live-swap minimum cannot be placed "
                     f"profitably at the current book.")
    return {
        "certification_size_usd": cert_size,
        "min_executable_size_usd": min_exec or None,
        "min_executable_source": "BlockDAG Live Swap minimum purchase",
        "certified_recommendation_usd": rec_capped,
        "actual_executable_recommendation_usd": round(actual, 2) if actual is not None else None,
        "actionable": bool(actual is not None and placeable and not min_over_cap),
        "exceeds_certification_cap": bool(actual is not None and actual > cert_size + 1e-9),
        "min_exceeds_certification_cap": min_over_cap,
        "placeable_within_profitable_depth": placeable,
        "notes": notes,
    }


def _dual_roi_unavailable(resolution, position_price):
    return {
        "authority": "fresh_cycle",
        "fresh_cycle": {
            "label": "Fresh Cycle ROI", "is_execution_authority": True,
            "available": resolution.get("price") is not None,
            "buy_price": resolution.get("price"), "buy_source": resolution.get("source_label"),
            "roi_pct": None, "net_profit_usd": None, "verdict": "NO_GO",
            "purpose": "Evaluate whether a brand-new cycle is profitable right now (buy at the live swap price)."},
        "existing_position": {
            "label": "Existing Position ROI", "is_execution_authority": False,
            "available": position_price is not None,
            "buy_price": position_price, "buy_source": "Position Cost Basis",
            "roi_pct": None, "net_profit_usd": None,
            "purpose": "Evaluate liquidation of already-held BDAG (informational only)."},
        "note": "Fresh cycle unavailable — a new cycle cannot be evaluated without a fresh live-swap buy price. "
                "Existing Position ROI is informational and never authorizes a new cycle.",
    }


async def analyze(route_id: str, size_usd: float = None, utilization_pct: int = 75) -> dict:
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        return {"route_id": route_id, "available": False, "note": "route not found"}
    rcache = collector.cache.get(route_id, {})
    full_resolution = await bp_resolver.resolve(route)
    # FRESH CYCLE is the execution authority: buy at the live swap price (NOT the
    # held-position cost basis). Position cost basis is computed separately, for info.
    resolution = bp_resolver.as_fresh_resolution(full_resolution)
    buy_price = resolution["price"]
    position_cand = bp_resolver.select_position(full_resolution)
    position_price = (position_cand or {}).get("value")

    sel = await _select_sell_venue(route, rcache)
    if not sel or buy_price is None:
        reason = ("no fresh live-swap buy price (portal stale / unavailable)" if sel
                  else "no live order book")
        # Resolve effective fees so the measured BDAG transfer fee is observable
        # even when the route is unavailable (transparency over Fresh ROI inputs).
        _fees = await get_fees()
        from services.execution import bdag_transfers as _bdag_transfers
        _eff = await _bdag_transfers.effective_transfer_fee_bdag(_fees["bdag_transfer_fee_base"])
        _venue_for_fees = (sel or {}).get("venue")
        return {"route_id": route_id, "available": False,
                "buy_price": buy_price, "buy_price_source": resolution["source"],
                "buy_price_resolution": resolution, "position_buy_price": position_price,
                "sell_venue": _venue_for_fees,
                "dual_roi": _dual_roi_unavailable(resolution, position_price),
                "fees_used": {
                    "trading_fee_pct": taker_pct(_fees, _venue_for_fees),
                    "purchase_gas_usd": _fees["purchase_gas_usd"],
                    "usdt_withdrawal_fee_usd": usdt_withdrawal_usd(_fees, _venue_for_fees),
                    "bdag_transfer_fee_base": _eff["value"],
                    "bdag_transfer_fee_source": _eff["source"],
                    "bdag_transfer_fee_evidence_count": _eff["evidence_count"],
                },
                "note": f"unavailable — {reason}", "verdict": "NO_GO",
                "verdict_reasons": [f"Missing fresh buy price or live bid ladder ({reason})"]}

    venue, bids = sel["venue"], sel["bids"]
    fees = await get_fees()
    # Replace the hardcoded BDAG transfer-fee assumption with the measured
    # rolling average whenever evidence exists. The Fresh Cycle ROI authority,
    # gate logic, and interlock are unchanged — only the consumed value moves
    # from assumption → evidence-based.
    from services.execution import bdag_transfers as _bdag_transfers
    eff_transfer = await _bdag_transfers.effective_transfer_fee_bdag(fees["bdag_transfer_fee_base"])
    fees = {**fees, "bdag_transfer_fee_base": eff_transfer["value"],
            "bdag_transfer_fee_source": eff_transfer["source"],
            "bdag_transfer_fee_evidence_count": eff_transfer["evidence_count"]}
    taker = taker_pct(fees, venue)
    cfg = await config.get_config()
    limits = cfg["limits"]
    min_roi = limits["min_net_spread_pct"]

    # --- Break-Even Engine (per-unit marginal break-even sell price) ---
    # Net of taker fee; fixed fees (gas + withdrawal) handled in full economics below.
    be_marginal = buy_price / (1 - taker / 100)
    best_bid = bids[0][0]
    be_cushion_pct = round((best_bid - be_marginal) / be_marginal * 100, 3) if be_marginal else None

    # --- Profitable Liquidity Engine (which buyer levels clear break-even) ---
    profitable_levels, prof_base, prof_quote = [], 0.0, 0.0
    for price, q in bids:
        lvl = {"price": price, "qty": round(q, 6), "quote": round(price * q, 4),
               "profitable": price >= be_marginal}
        if lvl["profitable"]:
            prof_base += q
            prof_quote += price * q
        profitable_levels.append(lvl)
    prof_base = round(prof_base, 6)

    # --- Order-Book Consumption Simulator across utilization tiers ---
    sims = []
    for u in UTILIZATIONS:
        sell_qty = prof_base * u / 100
        if sell_qty <= 0:
            sims.append({"utilization_pct": u, "feasible": False,
                         "note": "no profitable depth"})
            continue
        fills, filled, vwap, exhausted = _fill_ladder(bids, sell_qty)
        if vwap is None:
            sims.append({"utilization_pct": u, "feasible": False, "note": "book too thin"})
            continue
        econ = _cycle_economics(filled, buy_price, vwap, taker, fees, venue)
        # cap to certification per-cycle size
        capped = econ["investment_usd"] > limits["max_cycle_usd"]
        sims.append({"utilization_pct": u, "feasible": True, "fills": fills,
                     "book_exhausted": exhausted, "exceeds_cert_cap": capped, **econ})

    # --- Liquidity-Aware Position Sizing + Smart Exit (at chosen utilization) ---
    util = utilization_pct if utilization_pct in UTILIZATIONS else 75
    chosen = next((s for s in sims if s["utilization_pct"] == util and s.get("feasible")), None)
    # honor certification cap → safe capital size
    safe = None
    if chosen:
        safe = dict(chosen)
        if chosen["investment_usd"] > limits["max_cycle_usd"]:
            scale = limits["max_cycle_usd"] / chosen["investment_usd"]
            q2 = chosen["sell_qty_base"] * scale
            _, filled2, vwap2, _ = _fill_ladder(bids, q2)
            if vwap2:
                safe = {"utilization_pct": util, "capped_to_cert_max": True,
                        **_cycle_economics(filled2, buy_price, vwap2, taker, fees, venue)}

    # --- Existing Position ROI (informational): liquidate held BDAG at the cost
    # basis, sold into the SAME live book. Computed independently of fresh-cycle
    # viability so it can be shown side-by-side even when a fresh cycle is NO_GO. ---
    existing_position_econ = _position_roi(
        bids, position_price, taker, fees, venue, limits["max_cycle_usd"])

    # --- optional: economics at an exact requested investment ---
    at_requested = None
    if size_usd and buy_price > 0:
        rq = size_usd / buy_price
        f3, filled3, vwap3, ex3 = _fill_ladder(bids, rq)
        if vwap3:
            at_requested = {"requested_usd": round(size_usd, 2), "book_exhausted": ex3,
                            **_cycle_economics(filled3, buy_price, vwap3, taker, fees, venue)}

    stability = await _buyer_stability(route_id, venue)

    # --- Maximum Safe Buy Size + ROI curve over profitable-liquidity depth ---
    max_safe_buy = {
        "max_profitable_liquidity_base": prof_base,
        "max_profitable_liquidity_quote": round(prof_quote, 2),
        "floor_pct": min_roi,
        "cert_max_usd": limits["max_cycle_usd"],
        "roi_curve": [
            {"depth_pct": s["utilization_pct"], "investment_usd": s["investment_usd"],
             "weighted_sell_price": s["weighted_sell_price"], "roi_pct": s["roi_pct"],
             "exceeds_cert_cap": s.get("exceeds_cert_cap", False)}
            for s in sims if s.get("feasible")],
        "cert_capped_recommendation": safe,
    }
    _ms = _max_safe_size(bids, prof_base, buy_price, taker, fees, venue, min_roi)
    if _ms:
        max_safe_buy.update({
            "max_safe_buy_usd": _ms["max_safe_buy_usd"],
            "max_safe_sell_qty_base": _ms["max_safe_sell_qty_base"],
            "weighted_sell_price_at_max": _ms["weighted_sell_price"],
            "roi_at_max_safe_pct": _ms["roi_pct"],
            "degrades_note": f"Beyond ~${_ms['max_safe_buy_usd']} the next bid levels pull net ROI "
                             f"below the {min_roi}% floor. Certification caps live size to "
                             f"${limits['max_cycle_usd']}.",
        })
    else:
        max_safe_buy["max_safe_buy_usd"] = None
        max_safe_buy["degrades_note"] = "No size clears the net-ROI floor at the current book/buy price."

    # --- GO / WAIT / NO-GO Engine ---
    reasons = []
    roi = (chosen or {}).get("roi_pct")
    if not chosen or roi is None or roi <= 0:
        verdict = "NO_GO"
        reasons.append("No profitable sell size at chosen utilization (net ROI ≤ 0 after all fees).")
    else:
        soft = []
        if roi < min_roi:
            soft.append(f"Net ROI {roi}% below min spread floor {min_roi}%.")
        if stability["label"] == "VOLATILE":
            soft.append("Buyer levels are VOLATILE (unstable bid book).")
        if (chosen or {}).get("book_exhausted"):
            soft.append("Bid ladder exhausted at this size — insufficient depth.")
        if prof_quote < limits["max_cycle_usd"]:
            soft.append(f"Profitable depth (${round(prof_quote,2)}) is thin vs cap ${limits['max_cycle_usd']}.")
        if soft:
            verdict, reasons = "WAIT", soft
        else:
            verdict = "GO"
            reasons.append(f"Net ROI {roi}% ≥ floor {min_roi}% with stable, sufficient buyer depth.")

    # --- Dual ROI: FRESH CYCLE (execution authority) vs EXISTING POSITION (info) ---
    fresh_display = safe or _reference_econ(bids, buy_price, taker, fees, venue, limits["max_cycle_usd"])
    dual_roi = {
        "authority": "fresh_cycle",
        "fresh_cycle": {
            "label": "Fresh Cycle ROI", "is_execution_authority": True,
            "available": buy_price is not None,
            "buy_price": round(buy_price, 8) if buy_price else None,
            "buy_source": resolution.get("source_label"),
            "sell_price": best_bid, "weighted_sell_price": (fresh_display or {}).get("weighted_sell_price"),
            "roi_pct": (fresh_display or {}).get("roi_pct"), "net_profit_usd": (fresh_display or {}).get("net_profit_usd"),
            "verdict": verdict, "profitable_size_exists": safe is not None,
            "purpose": "Evaluate whether a brand-new cycle is profitable right now (buy at the live swap price).",
        },
        "existing_position": {
            "label": "Existing Position ROI", "is_execution_authority": False,
            "available": bool(existing_position_econ),
            "buy_price": round(position_price, 8) if position_price else None,
            "buy_source": "Position Cost Basis",
            "sell_price": best_bid, "weighted_sell_price": (existing_position_econ or {}).get("weighted_sell_price"),
            "roi_pct": (existing_position_econ or {}).get("roi_pct"),
            "net_profit_usd": (existing_position_econ or {}).get("net_profit_usd"),
            "purpose": "Evaluate liquidation of already-held BDAG (informational only).",
        },
        "note": "The Opportunity Gate, Safety Interlock and all execution decisions use FRESH CYCLE ROI only. "
                "Existing Position ROI is informational and never authorizes a new cycle.",
    }

    return {
        "route_id": route_id, "route_name": route.get("name"), "available": True,
        "buy_price": round(buy_price, 8), "buy_price_source": resolution["source"],
        "buy_price_resolution": resolution, "position_buy_price": position_price,
        "dual_roi": dual_roi,
        "sell_venue": venue, "sell_venue_role": sel["role"], "gate_open": sel["gate_open"],
        "best_bid": best_bid, "taker_fee_pct": taker,
        "fees_used": {
            "trading_fee_pct": taker,
            "purchase_gas_usd": fees["purchase_gas_usd"],
            "usdt_withdrawal_fee_usd": usdt_withdrawal_usd(fees, venue),
            "bdag_transfer_fee_base": fees["bdag_transfer_fee_base"],
            "bdag_transfer_fee_source": fees.get("bdag_transfer_fee_source"),
            "bdag_transfer_fee_evidence_count": fees.get("bdag_transfer_fee_evidence_count", 0),
        },
        "break_even": {"marginal_sell_price": round(be_marginal, 8),
                       "cushion_vs_best_bid_pct": be_cushion_pct,
                       "note": "Marginal break-even sell price (net of taker fee). Bids at/above this are profitable."},
        "profitable_liquidity": {"profitable_base": prof_base, "profitable_quote": round(prof_quote, 2),
                                 "total_levels": len(bids),
                                 "profitable_levels": sum(1 for l in profitable_levels if l["profitable"])},
        "levels": profitable_levels[:25],
        "utilization_sims": sims,
        "recommended": safe,
        "max_safe_buy": max_safe_buy,
        "chosen_utilization_pct": util,
        "at_requested_size": at_requested,
        "buyer_stability": stability,
        "verdict": verdict, "verdict_reasons": reasons,
        "limits": {"max_cycle_usd": limits["max_cycle_usd"], "min_net_spread_pct": min_roi,
                   "min_executable_purchase_usd": limits.get("min_executable_purchase_usd")},
        "executable_sizing": _executable_sizing(limits, safe, max_safe_buy),
        "note": "Read-only BDAG arbitrage intelligence. Multi-level VWAP simulation; no single-price "
                "assumption. No orders, no fund movement.",
    }
