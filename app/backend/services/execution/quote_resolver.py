"""Pre-Trade Quote Resolver (READ-ONLY, NON-COMMITTING).

Given a test amount (USDT/BNB), returns the BDAG allocation ArbiCore predicts
the swap contract would deliver, the effective executable price, the resulting
ROI economics, and a READY / WAIT verdict — WITHOUT signing or submitting any
transaction.

THREE STRATEGIES (pluggable; first-wins precedence):

  A. EXECUTED-CALIBRATION (ACTIVE)
     Calibrates a `bonus_factor` from operator-recorded executed swaps
     (rolling-average effective price ÷ live API base price). Predicts the
     allocation by applying the inverse factor to the live API base.
     Production-grade when ≥ MIN_CALIB_SAMPLES samples exist.

  B. ETH_CALL CONTRACT PREVIEW (STUB)
     EVM swap contracts expose a `view`-function (typical names:
     getAmountsOut, previewSwap, calculateBDAG, etc.). Calling it via
     eth_call is non-committing — no signature, no gas, no transaction.
     Requires:
        - Swap contract address
        - Preview function ABI (4-byte selector + arg encoding)
        - JSON-RPC endpoint (BSC mainnet or whichever chain hosts the swap)
     None are currently configured. Resolver returns status='not_configured'
     for this strategy until operator wires them.

  C. WALLET-GATED UI QUOTE API (STUB)
     The swap UI at purchase3.blockdag.network/swap fetches a per-amount quote
     after wallet connection. The endpoint is not publicly reachable; we
     have searched the loaded JS bundles + probed common paths (getQuote,
     calculate, estimate, preview, etc.) — none respond. If the operator
     captures the endpoint URL from a real wallet session, paste it into
     UI_QUOTE_ENDPOINT_HINT and the resolver will start using it.

Outputs `verdict` ∈ {READY, WAIT, NO_GO}.
  • READY  — Fresh ROI ≥ floor, freshness OK, calibration confidence ≥ medium,
              size respects Coinstore min-deposit constraint.
  • WAIT   — viable but missing one of {fresh ROI ≥ floor, freshness, calibration}.
  • NO_GO  — ROI negative OR live data unavailable OR size below the hard
              Coinstore minimum-deposit floor of 3,703 BDAG.

NO TRANSACTION SUBMISSION. NO SIGNATURE. NO WALLET. NO FUND MOVEMENT.
"""
import asyncio
import logging
import statistics

import httpx

from core.models import now_iso
from services import db
from services.execution import (arbitrage_intel, buy_price_audit, executable_quote,
                                quote_capture)
from services.execution.fees import get_effective_fees, taker_pct, usdt_withdrawal_usd
from services.portal_price import portal_price

logger = logging.getLogger("quote_resolver")

MIN_CALIB_SAMPLES = 3
COINSTORE_MIN_DEPOSIT_BDAG = 3703
FRESH_ROI_FLOOR_PCT = 2.0     # mirrors gate threshold

# When the operator finds the real wallet-gated quote endpoint, set this:
UI_QUOTE_ENDPOINT_HINT = None      # e.g. "https://sw-api.blockdag.network/quote"

# When the operator supplies the contract address + RPC, set these:
SWAP_CONTRACT_ADDRESS = None       # e.g. "0xa12345…"
SWAP_PREVIEW_FN_SIGNATURE = None   # e.g. "calculateBDAG(uint256)"
EVM_RPC_URL = None                 # e.g. "https://bsc-dataseed.binance.org"


# ---------- Strategy 0 (PRIMARY): captured executable quote ----------------

async def _captured_quote(input_usd: float) -> dict:
    """PRIMARY — most recent operator-captured pre-trade quote from swap UI."""
    latest = await quote_capture.latest()
    rolling = await quote_capture.rolling_summary()
    if not latest.get("available"):
        return {"strategy": "captured_quote", "available": False,
                "status": "no_captures", "samples_count": 0,
                "reason": ("No executable-quote captures recorded yet — paste the bookmarklet "
                           "into the swap page console after wallet connection, or use the "
                           "manual capture form.")}
    fresh = bool(latest.get("fresh"))
    eff = latest["effective_price"]
    bdag_expected = round(input_usd / eff, 4) if eff else None
    return {
        "strategy": "captured_quote",
        "available": fresh, "status": "ok" if fresh else "stale",
        "input_usd": input_usd, "bdag_expected": bdag_expected,
        "effective_price": eff,
        "samples_count": rolling.get("count", 0),
        "latest_capture": {
            "id": latest.get("id"), "input_amount": latest.get("input_amount"),
            "bdag_allocated": latest.get("bdag_allocated"),
            "effective_price": eff, "source": latest.get("source"),
            "age_s": latest.get("age_s"),
            "fresh_window_s": latest.get("fresh_window_s"),
            "created_at": latest.get("created_at"),
        },
        "rolling": rolling,
        "reason": (("Fresh capture (age {0}s ≤ {1}s) from source='{2}' — AUTHORITATIVE."
                    .format(latest.get("age_s"), latest.get("fresh_window_s"),
                            latest.get("source")))
                   if fresh else
                   ("Latest capture age {0}s > fresh window {1}s — falling through."
                    .format(latest.get("age_s"), latest.get("fresh_window_s")))),
    }


# ---------- Strategy A: executed-calibration -------------------------------

async def _executed_calibration(input_usd: float) -> dict:
    """Apply rolling-average bonus factor from operator-attested executed swaps."""
    pf = portal_price.status_brief()
    base = pf.get("bdag_price")
    base_stale = pf.get("stale")
    docs = await buy_price_audit.list_empirical(20)
    samples = [d for d in docs if isinstance(d.get("effective_price"), (int, float))]
    n = len(samples)

    if not base:
        return {"strategy": "executed_calibration", "available": False,
                "reason": "Live API base price unavailable (portal feed empty).",
                "status": "unavailable"}
    if n == 0:
        return {"strategy": "executed_calibration", "available": False,
                "reason": "No executed-price samples yet — record one via the Buy-Price Audit form.",
                "status": "needs_samples"}

    avg_eff = statistics.mean(s["effective_price"] for s in samples)
    # bonus_factor < 1 = wallet pays less per BDAG than the API base.
    bonus_factor = round(avg_eff / base, 6)
    predicted_unit_price = round(base * bonus_factor, 12)   # = avg_eff
    bdag_expected = round(input_usd / predicted_unit_price, 4) if predicted_unit_price > 0 else None
    confidence = ("high" if n >= 10 else "medium" if n >= MIN_CALIB_SAMPLES else "low")
    return {
        "strategy": "executed_calibration",
        "available": (n >= MIN_CALIB_SAMPLES) and not base_stale,
        "status": ("ok" if (n >= MIN_CALIB_SAMPLES and not base_stale)
                   else ("low_confidence" if n < MIN_CALIB_SAMPLES else "stale_base")),
        "input_usd": input_usd,
        "bdag_expected": bdag_expected,
        "effective_price": predicted_unit_price,
        "calibration": {
            "live_api_base_price": base,
            "live_api_base_stale": bool(base_stale),
            "rolling_avg_effective_price": round(avg_eff, 12),
            "bonus_factor": bonus_factor,
            "implied_bonus_pct": round((1 - bonus_factor) * 100, 3),
            "samples_count": n,
            "min_samples_required": MIN_CALIB_SAMPLES,
            "confidence": confidence,
        },
        "reason": ("Bonus factor calibrated from {0} executed swaps — "
                   "applied to the live API base ${1:.6e} to predict allocation."
                   .format(n, base)),
    }


# ---------- Strategy B: eth_call contract preview (stub) -------------------

async def _eth_call_preview(input_usd: float) -> dict:
    if not (SWAP_CONTRACT_ADDRESS and SWAP_PREVIEW_FN_SIGNATURE and EVM_RPC_URL):
        return {
            "strategy": "eth_call_preview", "available": False,
            "status": "not_configured",
            "reason": ("Contract address, preview-function ABI, and JSON-RPC URL are not configured. "
                       "Once supplied, this strategy will call the swap contract’s view-function via "
                       "eth_call — non-committing, no signature, no gas — and return the exact "
                       "pre-trade BDAG allocation."),
            "needs": {
                "swap_contract_address": SWAP_CONTRACT_ADDRESS,
                "swap_preview_fn_signature": SWAP_PREVIEW_FN_SIGNATURE,
                "evm_rpc_url": EVM_RPC_URL,
            },
        }
    # When all three are set, perform the call. Skipped while unconfigured.
    return {"strategy": "eth_call_preview", "available": False,
            "status": "not_implemented_yet", "reason": "Configured but executor wiring pending."}


# ---------- Strategy C: wallet-gated UI quote API (stub) -------------------

async def _ui_quote_endpoint(input_usd: float) -> dict:
    if not UI_QUOTE_ENDPOINT_HINT:
        return {
            "strategy": "ui_quote_api", "available": False,
            "status": "endpoint_unknown",
            "reason": ("The wallet-gated quote endpoint was not discovered during network inspection "
                       "of purchase3.blockdag.network/swap (the Connect-Wallet gate blocks the form). "
                       "Paste the endpoint URL into UI_QUOTE_ENDPOINT_HINT if you capture it from a "
                       "real wallet session."),
        }
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(UI_QUOTE_ENDPOINT_HINT,
                            params={"amount_usd": input_usd},
                            headers={"User-Agent": "ArbiCore/quote-resolver",
                                     "Referer": "https://purchase3.blockdag.network/"})
            r.raise_for_status()
            payload = r.json()
            return {"strategy": "ui_quote_api", "available": True, "status": "ok",
                    "input_usd": input_usd, "raw": payload}
    except Exception as e:
        return {"strategy": "ui_quote_api", "available": False, "status": "fetch_error",
                "reason": str(e)[:200]}


# ---------- Economics from a quoted unit price -----------------------------

async def _cycle_economics(input_usd: float, unit_price: float, venue: str = None) -> dict:
    """Replay the existing arbitrage_intel cycle math at the QUOTED buy price.
    Reuses the live order book + measured transfer fee + Coinstore taker/withdrawal
    fees so the verdict reflects the *executable* economics, not API-inferred ones.
    """
    fees = await get_effective_fees()
    purchase_gas = fees["purchase_gas_usd"]

    # Use the first BDAG route — the system's default. Venue is whatever that route
    # exits to (coinstore/xt/etc). This keeps the resolver aligned with cycle_model
    # and arbitrage_intel rather than hard-coding coinstore.
    q = {"purchase.asset": "BDAG"}
    if venue:
        q["exit.exchange"] = venue
    route = await db.routes_col.find_one(q, {"_id": 0})
    if not route:
        return {"available": False, "reason": "no BDAG route configured"}

    venue = (route.get("exit") or {}).get("exchange") or venue or "coinstore"
    taker = taker_pct(fees, venue)
    usdt_wd = usdt_withdrawal_usd(fees, venue)
    transfer_base = fees["bdag_transfer_fee_base"]

    intel = await arbitrage_intel.analyze(route["id"])
    market = intel.get("recommended") or {}
    best_bid = intel.get("best_bid")
    weighted_sell = market.get("weighted_sell_price")
    if not best_bid:
        return {"available": False, "reason": "no live bid ladder"}

    # Predicted BDAG bought at the quoted unit price (excludes purchase gas)
    bdag_bought = max(0.0, (input_usd - purchase_gas)) / unit_price if unit_price else 0
    bdag_after_transfer = max(0.0, bdag_bought - (transfer_base or 0))
    # Sell using the EXISTING weighted-sell estimate (or fall back to best_bid)
    sell_unit = weighted_sell or best_bid
    gross_proceeds = bdag_after_transfer * sell_unit
    trading_fee = gross_proceeds * (taker / 100.0)
    transfer_fee_usd = (transfer_base or 0) * (intel.get("buy_price") or 0)
    total_fees = (trading_fee or 0) + (usdt_wd or 0) + (purchase_gas or 0) + transfer_fee_usd
    net_profit = gross_proceeds - trading_fee - usdt_wd - input_usd
    wallet_received = max(0.0, gross_proceeds - trading_fee - usdt_wd)
    roi_pct = round((net_profit / input_usd) * 100, 4) if input_usd > 0 else None
    meets_min_deposit = bdag_after_transfer >= COINSTORE_MIN_DEPOSIT_BDAG

    return {
        "available": True,
        "venue": venue,
        "buy_price_used": unit_price,
        "bdag_bought": round(bdag_bought, 4),
        "bdag_after_transfer": round(bdag_after_transfer, 4),
        "best_bid_used": best_bid,
        "weighted_sell_price_used": sell_unit,
        "gross_proceeds_usd": round(gross_proceeds, 6),
        "trading_fee_usd": round(trading_fee, 6), "trading_fee_pct": taker,
        "bdag_transfer_fee_bdag": round(transfer_base or 0, 9),
        "bdag_transfer_fee_usd": round(transfer_fee_usd, 6),
        "usdt_withdrawal_fee_usd": round(usdt_wd or 0, 6),
        "purchase_gas_usd": round(purchase_gas or 0, 6),
        "total_fees_usd": round(total_fees, 6),
        "net_profit_usd": round(net_profit, 6),
        "wallet_received_usd": round(wallet_received, 6),
        "roi_pct": roi_pct,
        "meets_coinstore_min_deposit": meets_min_deposit,
        "coinstore_min_deposit_bdag": COINSTORE_MIN_DEPOSIT_BDAG,
    }


# ---------- Composite quote with verdict -----------------------------------

def _verdict(economics: dict, calib_confidence: str, calib_status: str) -> dict:
    if not economics.get("available"):
        return {"verdict": "NO_GO",
                "reasons": [economics.get("reason") or "economics unavailable"]}
    reasons = []
    if not economics.get("meets_coinstore_min_deposit"):
        reasons.append(("Predicted post-transfer balance {0:.0f} BDAG < Coinstore minimum "
                        "deposit {1} BDAG").format(economics.get("bdag_after_transfer", 0),
                                                   COINSTORE_MIN_DEPOSIT_BDAG))
    roi = economics.get("roi_pct")
    if roi is None or roi < 0:
        return {"verdict": "NO_GO",
                "reasons": (reasons + ["Fresh ROI is negative — live swap > Coinstore bid"])}
    if roi < FRESH_ROI_FLOOR_PCT:
        reasons.append("Fresh ROI {0}% < floor {1}%".format(roi, FRESH_ROI_FLOOR_PCT))
    if calib_confidence == "low":
        reasons.append("Calibration confidence LOW (< {0} samples)".format(MIN_CALIB_SAMPLES))
    if calib_status == "stale_base":
        reasons.append("Live API base price is stale (>300s) — wait for next portal refresh")
    if reasons:
        return {"verdict": "WAIT", "reasons": reasons}
    return {"verdict": "READY", "reasons": ["Fresh ROI clears floor with full freshness + calibration."]}


def _strategy_summary(active_strategy, captured, eth_stub, ui_stub) -> list:
    return [
        {"strategy": "captured_quote",
         "label": "Captured Executable Quote (operator-attested, swap UI pre-signature)",
         "status": "ACTIVE" if active_strategy == "captured_quote" else (captured.get("status") or "—").upper(),
         "production_grade": True,
         "note": captured.get("reason") or "Authoritative when a capture < 5 min old exists."},
        {"strategy": "executed_calibration",
         "label": "Executed-Calibration (rolling-avg bonus from operator-attested swaps)",
         "status": "ACTIVE" if active_strategy == "executed_calibration" else "WAITING",
         "production_grade": True,
         "note": "Calibrated bonus factor applied to the live API base."},
        {"strategy": "eth_call_preview",
         "label": "On-chain eth_call · swap contract view function",
         "status": "NOT_APPLICABLE",
         "production_grade": False,
         "note": ("Not applicable on BlockDAG architecture — there is no token contract address; "
                  "BDAG runs on BlockDAG Mainnet and the quote math lives in BlockDAG's backend, "
                  "not in an EVM swap contract.")},
        {"strategy": "ui_quote_api",
         "label": "Wallet-gated UI quote endpoint (Reown/WalletConnect-gated)",
         "status": ui_stub.get("status"),
         "production_grade": False,
         "note": ui_stub.get("reason")},
    ]


async def quote(input_usd: float, pay_token: str = "USDT") -> dict:
    """Single non-committing quote pass.

    Precedence: executed_calibration → eth_call_preview → ui_quote_api.
    Returns the chosen strategy's economics + verdict + full chain.
    """
    if not (input_usd and input_usd > 0):
        return {"phase": "Quote Resolver (read-only, non-committing)",
                "generated_at": now_iso(),
                "verdict": "NO_GO", "reasons": ["investment_usd must be > 0"],
                "input_usd": input_usd}

    calib, captured, eth_stub, ui_stub = await asyncio.gather(
        _executed_calibration(input_usd),
        _captured_quote(input_usd),
        _eth_call_preview(input_usd),
        _ui_quote_endpoint(input_usd),
    )

    # Walk precedence: captured_quote → executed_calibration → eth_call_preview → ui_quote_api
    if captured.get("available"):
        active_strategy = "captured_quote"
        unit_price = captured["effective_price"]
        bdag_expected = captured["bdag_expected"]
    elif calib.get("available"):
        active_strategy = "executed_calibration"
        unit_price = calib["effective_price"]
        bdag_expected = calib["bdag_expected"]
    elif eth_stub.get("available"):
        active_strategy = "eth_call_preview"
        unit_price = eth_stub.get("effective_price")
        bdag_expected = eth_stub.get("bdag_expected")
    elif ui_stub.get("available"):
        active_strategy = "ui_quote_api"
        unit_price = ui_stub.get("effective_price")
        bdag_expected = ui_stub.get("bdag_expected")
    else:
        active_strategy = None
        unit_price = None
        bdag_expected = None

    if active_strategy and unit_price:
        economics = await _cycle_economics(input_usd, unit_price)
    else:
        economics = {"available": False,
                     "reason": "No production-grade strategy available — record empirical swaps or "
                               "configure the eth_call contract preview."}

    verdict = _verdict(
        economics,
        calib_confidence=(calib.get("calibration") or {}).get("confidence"),
        calib_status=calib.get("status"))

    # Helpful cross-check: which executable_quote authoritative source aligns with the chosen quote?
    eq = await executable_quote.resolve()

    return {
        "phase": "Quote Resolver (read-only, non-committing)",
        "generated_at": now_iso(),
        "input_usd": input_usd,
        "pay_token": pay_token,
        "active_strategy": active_strategy,
        "quote": {
            "bdag_expected": bdag_expected,
            "effective_price": unit_price,
            "live_api_base_price": (calib.get("calibration") or {}).get("live_api_base_price"),
            "implied_bonus_pct": (calib.get("calibration") or {}).get("implied_bonus_pct"),
        },
        "economics": economics,
        **verdict,
        "strategies": _strategy_summary(active_strategy, captured, eth_stub, ui_stub),
        "strategy_details": {
            "captured_quote": captured,
            "executed_calibration": calib,
            "eth_call_preview": eth_stub,
            "ui_quote_api": ui_stub,
        },
        "cross_check": {
            "executable_quote_authoritative_source": eq.get("authoritative", {}).get("source"),
            "executable_quote_authoritative_value": eq.get("authoritative", {}).get("value"),
            "matches_chosen_quote": (
                eq.get("authoritative", {}).get("value") is not None and unit_price is not None
                and abs(eq["authoritative"]["value"] - unit_price) / unit_price < 0.001
                if unit_price else None),
        },
        "consumed_by_arbicore_for_roi": False,
        "consumed_by_arbicore_note": (
            "This quote is exposed READ-ONLY. The Fresh-Cycle ROI authority in arbitrage_intel still "
            "consumes the live API base price (the Portal Feed). Wiring this resolver into Fresh-Cycle "
            "ROI is a deliberate, operator-initiated step."),
        "constants": {
            "min_calibration_samples": MIN_CALIB_SAMPLES,
            "coinstore_min_deposit_bdag": COINSTORE_MIN_DEPOSIT_BDAG,
            "fresh_roi_floor_pct": FRESH_ROI_FLOOR_PCT,
        },
        "note": "No transaction submission. No signature. No wallet. No fund movement.",
    }


async def strategies() -> dict:
    """Lightweight overview of the strategies + their wiring status."""
    captured = await _captured_quote(50)
    eth_stub = await _eth_call_preview(50)
    ui_stub = await _ui_quote_endpoint(50)
    return {
        "phase": "Quote Resolver Strategies (read-only)",
        "generated_at": now_iso(),
        "strategies": _strategy_summary(None, captured, eth_stub, ui_stub),
        "configuration": {
            "ui_quote_endpoint_hint": UI_QUOTE_ENDPOINT_HINT,
            "swap_contract_address": SWAP_CONTRACT_ADDRESS,
            "swap_preview_fn_signature": SWAP_PREVIEW_FN_SIGNATURE,
            "evm_rpc_url": EVM_RPC_URL,
            "min_calibration_samples": MIN_CALIB_SAMPLES,
        },
        "note": "BlockDAG architecture has no token contract address — BDAG runs on BlockDAG Mainnet. "
                "Captured executable quotes are the highest-fidelity buy-price source.",
    }
