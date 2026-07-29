"""Operator Console — single-purpose human-in-the-loop trading workspace
(READ-ONLY, NON-EXECUTING).

Composes existing read-only services into the five console sections the
operator needs to make a real trading decision:

  1. LIVE OPPORTUNITY MONITOR
     • captured executable BDAG price (PRIMARY) — from quote_capture
     • Coinstore best bid, order-book depth, gross/net spread % — from arbitrage_intel
     • net profit $ and risk-adjusted profit at a default test size
  2. CYCLE RISK ENGINE
     • avg / worst observed cycle duration — from arbitrage_cycles
     • current market volatility (buyer-stability CV) — from arbitrage_intel
     • drift risk estimate over expected cycle duration
     • LOW / MEDIUM / HIGH risk level
  3. OPPORTUNITY VERDICT
     • NOT TRADEABLE / TRADEABLE / HIGH CONFIDENCE + reasons
  4. QUOTE VERIFICATION
     • fresh capture age vs freshness window — from quote_capture
  5. HITL ACTIONS
     • OPEN SWAP PAGE / VERIFY QUOTE / EXECUTE TRADE
       (workflow helper URLs only — no signing, no submission)

NO execution. NO transaction signing. NO fund movement.
"""
from core.models import now_iso
from services import db
from services.execution import (arbitrage_cycles, arbitrage_intel, cycle_timing, opportunity_gate,
                                quote_capture)

DEFAULT_SIZE_USD = 50.0
SWAP_PAGE_URL = "https://purchase3.blockdag.network/swap"
COINSTORE_BDAG_URL = "https://www.coinstore.com/spot/BDAG-USDT"
DRIFT_PCT_PER_S_FLOOR = 0.0001  # 0.01 %/s → cap so a single jittery snapshot doesn't dominate


def _risk_level(drift_pct: float | None, stability_label: str | None) -> str:
    """Combine drift estimate + buyer-stability label into LOW/MEDIUM/HIGH."""
    if drift_pct is None or stability_label is None:
        return "MEDIUM"
    if stability_label == "VOLATILE" or drift_pct >= 2.0:
        return "HIGH"
    if stability_label == "MODERATE" or drift_pct >= 0.75:
        return "MEDIUM"
    return "LOW"


def _spreads(captured_price: float | None, best_bid: float | None,
             taker_pct: float | None, total_fees_usd: float | None,
             investment_usd: float) -> dict:
    if not (captured_price and best_bid and best_bid > 0):
        return {"gross_spread_pct": None, "net_spread_pct": None,
                "net_profit_usd": None}
    gross_pct = round((best_bid - captured_price) / captured_price * 100, 4)
    # net spread accounts for taker fee + fixed fees as a % of investment
    fee_pct = taker_pct or 0.0
    fixed_pct = ((total_fees_usd or 0.0) / investment_usd * 100) if investment_usd else 0.0
    net_pct = round(gross_pct - fee_pct - fixed_pct, 4)
    return {"gross_spread_pct": gross_pct, "net_spread_pct": net_pct,
            "taker_fee_pct_used": fee_pct,
            "fixed_fees_pct_of_investment": round(fixed_pct, 4)}


async def _route_id() -> str | None:
    route = await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0, "id": 1})
    return (route or {}).get("id")


async def build(investment_usd: float = DEFAULT_SIZE_USD) -> dict:
    investment_usd = float(investment_usd or DEFAULT_SIZE_USD)

    # ---- Pull every primary signal in parallel via existing services ----
    cap = await quote_capture.latest()
    rid = await _route_id()
    intel = await arbitrage_intel.analyze(rid, size_usd=investment_usd) if rid else {"available": False}
    gate = await opportunity_gate.evaluate(rid) if rid else {"available": False, "gate_verdict": "NO_GO"}
    cycle_stats = await arbitrage_cycles.stats()

    # ---- 1. Live Opportunity Monitor ----
    captured_price = cap.get("effective_price") if cap.get("available") else None
    capture_fresh = bool(cap.get("fresh"))
    best_bid = intel.get("best_bid")
    prof_liq = intel.get("profitable_liquidity") or {}
    taker = intel.get("taker_fee_pct")

    # Use the existing executable-economics block (already at the requested size)
    at_req = intel.get("at_requested_size") or {}
    fees_total = (at_req.get("trading_fee_usd") or 0) + (at_req.get("withdrawal_fee_usd") or 0) + \
                 (at_req.get("gas_fee_usd") or 0)
    bdag_transfer_usd = ((intel.get("fees_used") or {}).get("bdag_transfer_fee_base") or 0) * \
                        (intel.get("buy_price") or 0)
    fees_total += bdag_transfer_usd
    spread = _spreads(captured_price, best_bid, taker, fees_total, investment_usd)

    # net profit at the captured price (PRIMARY) when available, else fall through
    net_profit_at_size = None
    if captured_price and best_bid and at_req.get("sell_qty_base"):
        # replicate the same shape arbitrage_intel uses, but using the captured price
        bdag_bought = max(0.0, investment_usd - (at_req.get("gas_fee_usd") or 0)) / captured_price
        bdag_after_transfer = max(0.0, bdag_bought - ((intel.get("fees_used") or {}).get("bdag_transfer_fee_base") or 0))
        sell_unit = at_req.get("weighted_sell_price") or best_bid
        gross_proceeds = bdag_after_transfer * sell_unit
        trading_fee = gross_proceeds * (taker or 0) / 100
        net_profit_at_size = round(gross_proceeds - trading_fee - (at_req.get("withdrawal_fee_usd") or 0)
                                   - investment_usd, 4)

    monitor = {
        "investment_usd": investment_usd,
        "captured_bdag_price": captured_price,
        "captured_price_source": cap.get("source") if cap.get("available") else None,
        "captured_price_age_s": cap.get("age_s"),
        "coinstore_best_bid": best_bid,
        "coinstore_orderbook_depth_quote": prof_liq.get("profitable_quote"),
        "coinstore_orderbook_depth_base": prof_liq.get("profitable_base"),
        "coinstore_total_levels": prof_liq.get("total_levels"),
        "venue": intel.get("sell_venue"),
        "gross_spread_pct": spread["gross_spread_pct"],
        "net_spread_pct": spread["net_spread_pct"],
        "net_profit_usd": net_profit_at_size,
    }

    # ---- 2. Cycle Risk Engine ----
    # Pull the real historical drift + duration from cycle_timing — replaces
    # the old buyer-stability CV proxy.
    timing = await cycle_timing.aggregate_only()
    durations = (timing.get("total_duration_s") or {})
    avg_dur = durations.get("avg")
    worst_dur = durations.get("worst")
    drift_dist = (timing.get("drift_distribution_pct") or {})
    end_drift = (drift_dist.get("end_drift_pct") or {})
    worst_drift = (drift_dist.get("worst_drift_pct") or {})
    # expected drift: average end-of-cycle bid drift across history.
    drift_estimate_pct = end_drift.get("avg")
    # If we don't have cycle history yet, fall back to buyer stability CV.
    stability = intel.get("buyer_stability") or {}
    if drift_estimate_pct is None and stability.get("best_bid_cv_pct") is not None:
        drift_estimate_pct = round(stability["best_bid_cv_pct"], 3)
    risk_level = _risk_level(drift_estimate_pct, stability.get("label"))

    # Forecast risk-adjusted profit (only when we have inputs)
    forecast = None
    if captured_price and best_bid and investment_usd:
        forecast = cycle_timing.forecast(
            captured_price=captured_price, best_bid=best_bid,
            investment_usd=investment_usd,
            drift_agg=drift_dist, duration_block=durations,
            taker_fee_pct=(taker or 0),
            bdag_transfer_fee_base=((intel.get("fees_used") or {}).get("bdag_transfer_fee_base") or 0),
        )
    risk_adjusted_profit = (forecast or {}).get("risk_adjusted_profit_avg_usd")
    prob_disappears = (forecast or {}).get("probability_profit_disappears")

    risk = {
        "closed_cycles_observed": timing.get("closed_cycles_used", 0),
        "avg_cycle_duration_s": avg_dur,
        "worst_cycle_duration_s": worst_dur,
        "median_cycle_duration_s": durations.get("median"),
        "p95_cycle_duration_s": durations.get("p95"),
        "buyer_stability_label": stability.get("label"),
        "best_bid_cv_pct": stability.get("best_bid_cv_pct"),
        "depth_cv_pct": stability.get("depth_cv_pct"),
        "drift_estimate_pct_over_cycle": drift_estimate_pct,
        "historical_worst_drift_pct": worst_drift.get("worst"),
        "historical_p5_worst_drift_pct": worst_drift.get("p5"),
        "risk_level": risk_level,
        "risk_adjusted_profit_usd": risk_adjusted_profit,
        "probability_profit_disappears": prob_disappears,
        "forecast": forecast,
        "stage_durations_s": timing.get("stage_durations_s"),
        "note": ("Risk metrics now use REAL historical cycle durations + drift "
                 "(measured against Coinstore best_bid orderbook history). Fallback "
                 "to buyer-stability CV only when no closed cycles exist."),
    }

    # ---- 4. Quote Verification ----
    quote_v = {
        "available": cap.get("available", False),
        "fresh": capture_fresh,
        "age_s": cap.get("age_s"),
        "fresh_window_s": cap.get("fresh_window_s") or 300,
        "captured_at": cap.get("created_at"),
        "source": cap.get("source"),
        "input_amount": cap.get("input_amount"),
        "bdag_allocated": cap.get("bdag_allocated"),
        "effective_price": captured_price,
        "note": ("No opportunity is executable until a fresh wallet-connected quote exists. "
                 "Re-run the capture bookmarklet (or use the manual form) every 5 minutes."),
    }

    # ---- 3. Opportunity Verdict ----
    reasons = []
    if not capture_fresh:
        reasons.append("No fresh wallet-connected quote (capture is missing or > 5 min old)")
    if not intel.get("available"):
        reasons.append("No live order book / buy price for the BDAG route")
    if monitor["net_spread_pct"] is None or monitor["net_spread_pct"] <= 0:
        reasons.append("Net spread is non-positive after fees")
    if at_req and not at_req.get("roi_pct", None) and intel.get("available"):
        # net profit not computable at this size
        pass
    if intel.get("available") and (intel.get("recommended") or {}).get("roi_pct", -1) is not None:
        if (intel["recommended"] or {}).get("roi_pct", 0) <= 0 and "Net spread is non-positive after fees" not in reasons:
            reasons.append("Recommended cycle ROI ≤ 0 at current depth")

    if reasons:
        verdict = "NOT_TRADEABLE"
    else:
        # baseline TRADEABLE: fresh quote, positive net spread, intel available
        if (gate.get("gate_verdict") == "GO" and risk_level == "LOW"
                and stability.get("label") in ("STABLE", "MODERATE")
                and (monitor["net_spread_pct"] or 0) >= 2.0):
            verdict = "HIGH_CONFIDENCE"
            reasons = [f"Fresh quote + net spread {monitor['net_spread_pct']}% ≥ 2% + LOW risk + gate GO"]
        else:
            verdict = "TRADEABLE"
            soft = []
            if gate.get("gate_verdict") != "GO":
                soft.append(f"opportunity gate verdict is {gate.get('gate_verdict')}")
            if risk_level != "LOW":
                soft.append(f"risk level {risk_level} (cycle drift estimate {drift_estimate_pct or '—'}%)")
            if (monitor["net_spread_pct"] or 0) < 2.0:
                soft.append(f"net spread {monitor['net_spread_pct']}% below 2% confidence floor")
            reasons = ([f"Fresh quote + positive net spread {monitor['net_spread_pct']}%"]
                       + ([("not high-confidence: " + "; ".join(soft))] if soft else []))

    verdict_block = {
        "verdict": verdict, "reasons": reasons,
        "definitions": {
            "NOT_TRADEABLE": "Hard blockers — quote stale, no live book, or net spread ≤ 0.",
            "TRADEABLE":     "Fresh quote + positive net spread, but at least one confidence "
                             "condition is not satisfied.",
            "HIGH_CONFIDENCE": "Fresh quote, net spread ≥ 2%, opportunity gate GO, LOW risk, "
                               "stable buyer liquidity.",
        },
    }

    # ---- 5. Human-in-the-Loop Actions ----
    quote_age_s = cap.get("age_s")
    actions = {
        "open_swap_page": {
            "label": "OPEN SWAP PAGE",
            "enabled": True,
            "url": SWAP_PAGE_URL,
            "note": "Opens the BlockDAG Live Swap page in a new tab. No automation runs.",
        },
        "verify_quote": {
            "label": "VERIFY QUOTE",
            "enabled": True,
            "url": None,
            "note": ("Re-run the Quote Capture bookmarklet on the swap page to refresh the "
                     "captured executable price (or use the manual form). Verdict re-renders."),
        },
        "execute_trade": {
            "label": "EXECUTE TRADE",
            "enabled": (verdict == "HIGH_CONFIDENCE" and capture_fresh
                        and (quote_age_s or 1e9) < (cap.get("fresh_window_s") or 300)),
            "url": SWAP_PAGE_URL,
            "note": ("Workflow helper only — opens the swap page so the operator can sign the "
                     "transaction in their own wallet. ArbiCore NEVER signs or submits."),
        },
        "open_coinstore": {
            "label": "OPEN COINSTORE",
            "enabled": True,
            "url": COINSTORE_BDAG_URL,
            "note": "Operator opens the Coinstore BDAG/USDT order book to manually place the sell order.",
        },
    }

    return {
        "phase": "Operator Console (human-in-the-loop, read-only)",
        "generated_at": now_iso(),
        "monitor": monitor,
        "risk": risk,
        "verdict": verdict_block,
        "quote_verification": quote_v,
        "actions": actions,
        "historical_drift": await _historical_drift_block(),
        "guardrails": {
            "execution_enabled": False, "wallet_enabled": False,
            "transaction_signing": False, "autonomous_execution": False,
            "fund_movement": False,
            "note": "Operator remains the final authority. ArbiCore never signs, submits, or moves funds.",
        },
        "links": {
            "swap_page": SWAP_PAGE_URL,
            "coinstore_bdag": COINSTORE_BDAG_URL,
        },
    }


# ---- Historical Drift block (additive, read-only, never affects verdict) ----
async def _historical_drift_block() -> dict:
    """Compact projection of the latest drift_analysis_cache for the operator
    console. Parallel intelligence layer — does NOT modify verdict, buy-price
    authority, quote capture, or any execution decision. Returns minimal
    fields the operator needs at a glance."""
    try:
        from services.execution import drift_runner as drift_runner_mod
        doc = await drift_runner_mod.latest(symbol="BDAGUSDT", venue="coinstore")
        if not doc:
            return {"available": False,
                    "note": "no drift snapshot yet — POST /api/execution/drift-analysis/run to compute"}
        dur = doc.get("cycle_duration_map") or {}
        expected_s = dur.get("current_expected_cycle_s") or 600
        row = (dur.get("rows") or {}).get(str(expected_s)) or {}
        cap = doc.get("opportunity_capacity") or {}
        regime = doc.get("regime") or {}
        rscore = doc.get("risk_score") or {}
        liq = doc.get("liquidity_survivability") or {}
        return {
            "available": True,
            "computed_at": doc.get("computed_at"),
            "regime": regime.get("label"),
            "opportunity_survival_prob_at_expected_cycle":
                row.get("combined_survival_prob"),
            "price_survival_prob_at_expected_cycle": row.get("price_survival_prob"),
            "liquidity_survival_prob_at_expected_cycle":
                row.get("liquidity_survival_prob"),
            "expected_cycle_s": expected_s,
            "buyer_disappearance_prob_at_expected_cycle":
                (liq.get("buyer_disappearance_prob") or {}).get(str(expected_s)),
            "expected_drift_pct": (rscore.get("components") or {}).get("expected_drift_pct"),
            "p95_drift_pct": (rscore.get("components") or {}).get("p95_drift_pct"),
            "risk_label": rscore.get("label"),
            "risk_score_0_100": rscore.get("score_0_100"),
            "risk_adjusted_profit_pct": rscore.get("risk_adjusted_profit_pct"),
            "opportunity_capacity_score_0_100": cap.get("opportunity_capacity_score_0_100"),
            "max_buy_usd": cap.get("max_buy_usd"),
            "recommended_buy_usd": cap.get("recommended_buy_usd"),
            "min_buy_usd": cap.get("min_buy_usd"),
            "feasible": cap.get("feasible"),
            "model_kind": (doc.get("model") or {}).get("kind"),
            "note": ("Parallel intelligence layer. Historical-prior model. "
                     "Does not modify verdict; advisory only until cycles calibrate."),
        }
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": str(e)[:200],
                "note": "drift block error — verdict unaffected"}
