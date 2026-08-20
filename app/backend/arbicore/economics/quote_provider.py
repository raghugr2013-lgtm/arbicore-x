"""ArbiCore X — Live-quote → opportunity seam (P0-4, read-only).

Turns a REAL on-chain Base route quote (produced by the existing
``execution.quoter.QuoterRegistry`` via read-only ``eth_call``) into the
opportunity dict that ``economics.opportunity_decision.decide_opportunity``
consumes. It NEVER signs, broadcasts, or deploys — it only reads quotes and
encodes (unsigned) executor calldata so the simulation gate's readiness
checks are genuine rather than faked.

Freshness/staleness is authoritative here:
  * live route quote (status == 'ok') & within max-age  → quote_status REAL
  * live/partial but older than max-age                 → quote_status STALE
  * any fallback (rpc error / revert / no adapter)      → quote_status UNAVAILABLE

Only a REAL quote can pass the downstream simulation gate.

Pure transform (no RPC itself). The caller passes the already-resolved
``RouteQuote``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..execution.calldata import build_user_data_from_hops


# dex name (as emitted by QuoterRegistry backends) → canonical Base router.
_DEX_ROUTER = {
    "uniswap_v3": "0x2626664c2603336E57B271c5C0b26F421741e481",
    "aerodrome_slipstream": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
    "aerodrome": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
}


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def quote_age_seconds(generated_at: Optional[str]) -> Optional[float]:
    dt = _parse_iso(generated_at)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def classify_quote_status(route_quote: Dict[str, Any], *,
                          max_age_sec: float = 12.0) -> Dict[str, Any]:
    """Return {'quote_status', 'quote_age_sec'} from a RouteQuote dict."""
    status = str(route_quote.get("status") or "")
    age = quote_age_seconds(route_quote.get("generated_at"))
    if status == "ok" and age is not None and age <= max_age_sec:
        qs = "REAL"
    elif status == "ok":
        qs = "STALE"                      # fully quoted but older than max-age
    else:
        qs = "UNAVAILABLE"                # 'partial' (a leg reverted) or fallback
    return {"quote_status": qs, "quote_age_sec": age}


def build_opportunity_from_route(
    route_quote: Dict[str, Any], *,
    input_hops: List[Dict[str, Any]],
    economics: Optional[Dict[str, Any]] = None,
    min_out_slippage_bps: float = 30.0,
    max_age_sec: float = 12.0,
    profit_recipient: str = "0x0000000000000000000000000000000000000001",
) -> Dict[str, Any]:
    """Compose the decision-engine opportunity dict from a live route quote.

    ``route_quote`` is ``QuoterRegistry.quote_route(...).to_dict()``.
    ``input_hops`` is the route spec that was quoted (dex/token_in/token_out/
    fee/amount_in_wei per hop). ``economics`` supplies the USD context the
    on-chain quote cannot (pool_liquidity_usd, gas_cost_usd, native_price_usd,
    flash-loan provider/fee, venue fees) — these are operator inputs, never
    invented.

    The realized gross spread is computed ONLY for a cyclic route (first
    token_in == last token_out); otherwise it is 0 and the opportunity is
    reported non-profitable rather than fabricated.
    """
    econ = dict(economics or {})
    hop_quotes = route_quote.get("hops") or []
    freshness = classify_quote_status(route_quote, max_age_sec=max_age_sec)
    quote_status = freshness["quote_status"]

    first_in = (input_hops[0].get("token_in") or input_hops[0].get("tokenIn") or "") if input_hops else ""
    last_out = (input_hops[-1].get("token_out") or input_hops[-1].get("tokenOut") or "") if input_hops else ""
    cyclic = bool(first_in) and first_in.lower() == last_out.lower()

    initial_in_wei = int((hop_quotes[0].get("amount_in_wei") if hop_quotes else 0) or 0)
    final_out_wei = int(route_quote.get("final_amount_out_wei") or 0)

    gross_spread_bps = 0.0
    repayment_ok = False
    if cyclic and initial_in_wei > 0 and quote_status == "REAL":
        gross_spread_bps = (final_out_wei - initial_in_wei) / initial_in_wei * 10_000.0
        repayment_ok = final_out_wei >= initial_in_wei

    # Build sim-gate hops (router allowlist / token allowlist / non-zero min
    # output) + genuine unsigned userData for the calldata_present check.
    decision_hops: List[Dict[str, Any]] = []
    encoder_hops: List[Dict[str, Any]] = []
    for i, spec in enumerate(input_hops):
        dex = str(spec.get("dex") or "").lower()
        token_in = spec.get("token_in") or spec.get("tokenIn")
        token_out = spec.get("token_out") or spec.get("tokenOut")
        quoted_out = int((hop_quotes[i].get("amount_out_wei") if i < len(hop_quotes) else 0) or 0)
        amount_out_min = int(quoted_out * (1.0 - min_out_slippage_bps / 10_000.0))
        decision_hops.append({
            "router": _DEX_ROUTER.get(dex, ""),
            "token_in": token_in, "token_out": token_out,
            "amount_out_min_wei": amount_out_min,
        })
        # fee tier: quoter uses ppm ('fee'); userData encoder wants bps.
        fee_ppm = int(spec.get("fee") or spec.get("fee_tier_ppm") or 500)
        encoder_hops.append({
            "token_in": token_in, "token_out": token_out,
            "fee_tier_bps": max(1, fee_ppm // 100),
            "amount_in_wei": int(spec.get("amount_in_wei") or spec.get("amountIn") or 0)
            if i == 0 else 0,
            "amount_out_min_wei": amount_out_min,
            "sqrt_price_limit_x96": 0,
        })

    user_data_hex = None
    if repayment_ok and all(int(h["amount_out_min_wei"]) > 0 for h in decision_hops):
        try:
            user_data_hex = build_user_data_from_hops(
                hops=encoder_hops, profit_recipient=profit_recipient)
        except ValueError:
            user_data_hex = None

    impact = route_quote.get("aggregate_price_impact_bps")
    expected_slippage_bps = econ.get("expected_slippage_bps")
    if expected_slippage_bps is None:
        expected_slippage_bps = float(impact) if impact is not None else min_out_slippage_bps

    opp: Dict[str, Any] = {
        "opportunity_id": econ.get("opportunity_id") or "live-quote",
        "gross_spread_bps": round(gross_spread_bps, 6),
        "pool_liquidity_usd": float(econ.get("pool_liquidity_usd") or 0.0),
        "gas_cost_usd": float(econ.get("gas_cost_usd") or 0.0),
        "flash_loan_fee_bps": float(econ.get("flash_loan_fee_bps") or 0.0),
        "flash_loan_provider": econ.get("flash_loan_provider") or "balancer_v2",
        "quote_status": quote_status,
        "quote_age_sec": freshness["quote_age_sec"],
        "gas_certainty": econ.get("gas_certainty"),
        "mev_risk": econ.get("mev_risk"),
        "historical_success_rate": econ.get("historical_success_rate"),
        "expected_slippage_bps": float(expected_slippage_bps),
        "repayment_ok": repayment_ok,
        "user_data_hex": user_data_hex,
        "buy_venue_fee_bps": float(econ.get("buy_venue_fee_bps") or 0.0),
        "sell_venue_fee_bps": float(econ.get("sell_venue_fee_bps") or 0.0),
        "native_price_usd": econ.get("native_price_usd"),
        "max_hops": int(econ.get("max_hops") or 3),
        "hops": decision_hops,
    }
    return {
        "opportunity": opp,
        "quote_provenance": {
            "route_status": route_quote.get("status"),
            "quote_status": quote_status,
            "quote_age_sec": freshness["quote_age_sec"],
            "cyclic_route": cyclic,
            "initial_amount_in_wei": str(initial_in_wei),
            "final_amount_out_wei": str(final_out_wei),
            "realized_gross_spread_bps": round(gross_spread_bps, 6),
            "rpc_host": (hop_quotes[0].get("rpc_host") if hop_quotes else None),
            "block_number": (hop_quotes[0].get("block_number") if hop_quotes else None),
        },
    }


__all__ = ["build_opportunity_from_route", "classify_quote_status",
           "quote_age_seconds"]
