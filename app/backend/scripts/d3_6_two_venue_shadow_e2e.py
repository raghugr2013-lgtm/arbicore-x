#!/usr/bin/env python3
"""D-3.6 shadow-only TWO-VENUE E2E — Base · Uniswap V3 + Aerodrome (READ-ONLY).

Runs the full shadow chain against a REAL Base RPC and prints every economic
field, preserving block/quote/backend provenance:

  discovery(candidate) → UniV3 live quote + Aerodrome live quote →
  DEXQuoteVerifier → cross-venue spread → all-in economics → economic gate →
  decision (+ exact rejection reason)

STRICTLY read-only: issues eth_call only. NEVER signs / broadcasts / executes.
Does NOT enable Limited Live. Fail-closed throughout (no fabricated numbers).

Run inside the validator (real ARBICORE_RPC_URL_BASE):
    python3 -m scripts.d3_6_two_venue_shadow_e2e            # WETH/USDC@base
    python3 -m scripts.d3_6_two_venue_shadow_e2e BASE/QUOTE # explicit pair
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, Optional


def _mask(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    return u.split("//", 1)[-1].split("/", 1)[0]


async def _leg_quotes(quoter, pair: str, notional: float) -> Dict[str, Any]:
    buy = await quoter.quote(pair_canonical=pair, size_in_usd=notional, direction="buy")
    sell = await quoter.quote(pair_canonical=pair, size_in_usd=notional, direction="sell")

    def _q(q):
        return {
            "ok": q.ok, "reason": q.reason, "dex": q.dex,
            "token_in": q.token_in, "token_out": q.token_out,
            "amount_in": q.amount_in, "amount_out": q.amount_out,
            "normalized_price_quote_per_base": q.effective_price,
            "fee_tier_bps": q.fee_tier_bps,
            "winning_backend": (q.raw or {}).get("winning_backend"),
            "block_number": (q.raw or {}).get("block_number"),
            "quoter_contract": (q.raw or {}).get("quoter_contract"),
            "backend_attempts": (q.raw or {}).get("backend_attempts"),
        }
    return {"buy": _q(buy), "sell": _q(sell), "_buy_obj": buy, "_sell_obj": sell}


async def main() -> None:
    from arbicore.config.persistent import resolve_rpc_url_from_env
    from arbicore.scanners.dex_arbitrage.quoter import EVMV3Quoter
    from arbicore.scanners.dex_arbitrage import DEXQuoteVerifier
    from arbicore.scanners.dex_arbitrage.economics import DEXEconomicsAssessor
    from arbicore.models.discovery import DiscoveryCandidate
    from arbicore.models.enums import OpportunityType, MevRiskLevel

    pair_arg = sys.argv[1] if len(sys.argv) > 1 else "WETH/USDC"
    base_sym, quote_sym = pair_arg.split("/", 1)
    chain = "base"
    subject = f"{base_sym}/{quote_sym}@{chain}"
    notional = float(os.environ.get("ARBICORE_DEX_NOTIONAL_USD", "1000"))
    min_net_usd = float(os.environ.get("ARBICORE_MIN_NET_PROFIT_USD", "35"))

    out: Dict[str, Any] = {
        "mode": "SHADOW_READONLY", "limited_live": False, "signing": False,
        "chain": chain, "pair": subject, "notional_usd": notional,
        "rpc_host": _mask(resolve_rpc_url_from_env(chain)),
    }
    if not resolve_rpc_url_from_env(chain):
        out["error"] = "no Base RPC configured (ARBICORE_RPC_URL_BASE) — fail-closed"
        print(json.dumps(out, indent=2, default=str)); sys.exit(2)

    # 1) discovery — the candidate under shadow verification
    candidate = DiscoveryCandidate(
        candidate_id=f"shadow:{base_sym}/{quote_sym}:{chain}",
        opportunity_type=OpportunityType.DEX_ARBITRAGE,
        hint_source="shadow_e2e", subject_id=subject, asset=base_sym,
        candidate_venues=[f"uniswap_v3:{chain}", f"aerodrome:{chain}"])
    out["candidate"] = {"candidate_id": candidate.candidate_id,
                        "subject_id": candidate.subject_id,
                        "venues": candidate.candidate_venues}

    # 2) live quotes from BOTH venues (UniV3 + Aerodrome best-of-family)
    univ3 = EVMV3Quoter(chain=chain, dex="uniswap_v3",
                        source_id=f"uniswap_v3_quoter_{chain}")
    aero = EVMV3Quoter(chain=chain, dex="aerodrome",
                       source_id=f"aerodrome_quoter_{chain}")
    uq = await _leg_quotes(univ3, subject, notional)
    aq = await _leg_quotes(aero, subject, notional)
    out["venue_quotes"] = {"uniswap_v3": {"buy": uq["buy"], "sell": uq["sell"]},
                           "aerodrome": {"buy": aq["buy"], "sell": aq["sell"]}}

    # 3) normalized prices + cross-venue spread (QUOTE-per-BASE; ask vs bid)
    asks = {"uniswap_v3": uq["buy"], "aerodrome": aq["buy"]}
    bids = {"uniswap_v3": uq["sell"], "aerodrome": aq["sell"]}
    ask_ok = {k: v["normalized_price_quote_per_base"] for k, v in asks.items()
              if v["ok"] and (v["normalized_price_quote_per_base"] or 0) > 0}
    bid_ok = {k: v["normalized_price_quote_per_base"] for k, v in bids.items()
              if v["ok"] and (v["normalized_price_quote_per_base"] or 0) > 0}
    out["normalized_prices_quote_per_base"] = {"asks": ask_ok, "bids": bid_ok}
    if not ask_ok or not bid_ok:
        out["spread"] = {"status": "fail_closed",
                         "reason": "one or both venues unpriceable"}
        print(json.dumps(out, indent=2, default=str)); return
    buy_venue = min(ask_ok, key=ask_ok.get); best_ask = ask_ok[buy_venue]
    sell_venue = max(bid_ok, key=bid_ok.get); best_bid = bid_ok[sell_venue]
    spread_pct = (best_bid - best_ask) / best_ask * 100.0
    out["spread"] = {
        "buy_venue": buy_venue, "best_ask_quote_per_base": best_ask,
        "buy_backend": asks[buy_venue]["winning_backend"],
        "buy_block": asks[buy_venue]["block_number"],
        "sell_venue": sell_venue, "best_bid_quote_per_base": best_bid,
        "sell_backend": bids[sell_venue]["winning_backend"],
        "sell_block": bids[sell_venue]["block_number"],
        "spread_pct": spread_pct, "spread_bps": spread_pct * 100.0,
        "same_venue_both_legs": buy_venue == sell_venue,
    }

    # 4) all-in economics (universal substrate via DEXEconomicsAssessor)
    econ = DEXEconomicsAssessor(config_loader=lambda: {})
    buy_obj = (uq if buy_venue == "uniswap_v3" else aq)["_buy_obj"]
    sell_obj = (uq if sell_venue == "uniswap_v3" else aq)["_sell_obj"]
    a = econ.assess(buy_quote=buy_obj, sell_quote=sell_obj, chain=chain,
                    gross_spread_pct=spread_pct, notional_usd=notional,
                    mev_risk_level=MevRiskLevel.LOW)
    gross_edge_usd = spread_pct / 100.0 * notional
    net_pct = float(a.net_after_costs_pct)
    net_usd = net_pct / 100.0 * notional
    out["economics"] = {
        "liquidity_usd": {
            "buy": asks[buy_venue].get("pool_liquidity_usd")
            if isinstance(asks[buy_venue], dict) else None,
            "sell": bids[sell_venue].get("pool_liquidity_usd")
            if isinstance(bids[sell_venue], dict) else None,
            "note": "on-chain TVL not fetched in this quote path (M2.6 provides it); "
                    "Gate 2 depth is fail-closed when unavailable",
        },
        "total_gas_usd": a.total_gas_usd,
        "gas_drag_pct": a.gas_drag_pct,
        "total_slippage_pct": a.total_slippage_pct,
        "total_fee_pct": getattr(a, "total_fee_pct", None),
        "flash_loan_fee": {
            "applies": False,
            "note": "spot two-venue DEX arb has no flash-loan leg; flash-loan fee "
                    "(+M3 authority) applies only to the flash_loan_arbitrage strategy",
        },
        "all_in_cost_pct": (spread_pct - net_pct),
        "gross_edge_usd": gross_edge_usd,
        "net_spread_after_slip_after_gas_pct": a.net_after_costs_pct,
        "mev_adjusted_net_pct": a.mev_adjusted_net_pct,
        "net_profit_usd": net_usd,
    }

    # 5) economic gate ($35 absolute floor) + full verifier gate pipeline
    passes_35 = net_usd >= min_net_usd
    out["economic_gate_$35"] = {
        "min_net_profit_usd": min_net_usd, "net_profit_usd": net_usd,
        "passed": bool(passes_35),
        "reason": None if passes_35 else
        f"net_profit_${net_usd:.2f}_below_min_${min_net_usd:.2f}",
    }

    verifier = DEXQuoteVerifier(
        quoters=[univ3, aero], venue_caps=_StubCaps(),
        config_loader=lambda: {"default_notional_usd": notional,
                               "gate_thresholds": {"default": {
                                   "min_net_spread_after_slip_after_gas_pct": 0.1,
                                   "min_depth_usd": 5000, "min_confidence": 55}}})
    opp, tag = await verifier.verify(candidate)
    out["verifier_decision"] = {
        "opportunity_built": opp is not None,
        "status": (str(opp.status) if opp is not None else None),
        "outcome_tag": tag,
        "rejected_at_gate": (opp.metadata.get("rejected_at_gate")
                             if opp is not None and opp.metadata else None),
        "rejection_reason": (opp.metadata.get("rejected_reason")
                             if opp is not None and opp.metadata else None),
    }
    out["m3_decision"] = {
        "applies": False,
        "note": "M3 (pre_broadcast execution authority) governs the flash_loan "
                "strategy only; the two-venue spot DEX shadow path is authorized "
                "by the DEX economic gates above. No signing/broadcast reachable.",
    }
    print(json.dumps(out, indent=2, default=str))


class _StubCaps:
    async def is_gate_3_pass(self, venue_id, base, quote):
        return True, "ok"


if __name__ == "__main__":
    asyncio.run(main())
