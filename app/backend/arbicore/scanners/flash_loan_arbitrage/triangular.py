"""Phase-2 Step 3 · Triangular (A→B→C→A) flash-loan arbitrage — live enumerator.

Generates GENUINE 3-leg cycles over the chain's token/pool graph, prices each
leg with a real quote, and computes TRUE net economics via the shared engine
(``multichain_economics.compute_true_net_profit``): gross edge − DEX fees
(embedded in the quotes) − flash fee − gas − L1/chain cost − slippage − provider
overhead. Only ECONOMICALLY-VALID candidates are emitted, tagged
``StrategyType.TRIANGULAR`` on the canonical model (no parallel pipeline).

Two layers:
  * pure ``enumerate_cycles`` + ``evaluate_cycle`` — deterministic, offline-
    testable with any injected async ``quote_fn``.
  * ``UniV3QuoteClient`` — a real, read-only Uniswap-V3 ``QuoterV2`` client
    (``quoteExactInputSingle``) for live quoting on the VPS/sandbox.

ZERO signing / ZERO broadcast. Any unavailable quote ⇒ that cycle is SKIPPED
(fail-closed), never priced with a substituted value.
"""
from __future__ import annotations

from itertools import permutations
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from eth_utils import function_signature_to_4byte_selector

from ...models.enums import DataProvenance
from .strategy_tagging import emit_flash_candidate
from .multichain_economics import compute_true_net_profit

# quote_fn(token_in_symbol, token_out_symbol, amount_in_float) -> amount_out|None
QuoteFn = Callable[[str, str, float], Awaitable[Optional[float]]]


def enumerate_cycles(base: str, intermediates: List[str]
                     ) -> List[Tuple[str, str, str, str]]:
    """All A→B→C→A cycles where A is the flash-borrowed ``base`` token.

    B, C are distinct intermediates (and ≠ base). Returns ordered token paths
    ``(base, B, C, base)``.
    """
    base = base.upper()
    inter = [t.upper() for t in intermediates if t.upper() != base]
    return [(base, b, c, base) for b, c in permutations(sorted(set(inter)), 2)]


async def evaluate_cycle(cycle: Tuple[str, str, str, str], *,
                         start_amount: float, quote_fn: QuoteFn
                         ) -> Optional[Dict[str, Any]]:
    """Price a cycle end-to-end. Returns gross edge in base-token units, or
    ``None`` if ANY leg cannot be quoted (fail-closed)."""
    amt = float(start_amount)
    legs: List[Dict[str, Any]] = []
    for a, b in zip(cycle, cycle[1:]):
        out = await quote_fn(a, b, amt)
        if out is None or out <= 0:
            return None  # unquotable leg ⇒ skip the whole cycle
        legs.append({"from": a, "to": b, "amount_in": amt, "amount_out": out})
        amt = out
    return {"cycle": list(cycle), "start_amount": float(start_amount),
            "end_amount": amt, "gross_edge_tokens": amt - float(start_amount),
            "legs": legs}


async def discover_triangular(
    *,
    chain: str,
    chain_id: int,
    base_token: str,
    intermediates: List[str],
    start_amount_tokens: float,
    base_token_price_usd: Optional[float],
    quote_fn: QuoteFn,
    gas_model,
    route_gas_units: int,
    native_usd: Optional[float],
    liquidity_by_provider: Optional[Dict[str, Optional[float]]] = None,
    fee_bps_by_provider: Optional[Dict[str, Optional[int]]] = None,
    min_net_profit_usd: float = 35.0,
) -> Dict[str, Any]:
    """Enumerate + evaluate + emit ECONOMICALLY-VALID triangular candidates.

    Returns ``{evaluated, valid, emitted:[CanonicalOpportunity], details:[...]}``.
    A cycle is emitted ONLY when true net profit ≥ ``min_net_profit_usd`` (the
    $35 gate is never lowered) — otherwise it is recorded but NOT emitted.
    """
    if base_token_price_usd is None or base_token_price_usd <= 0:
        return {"evaluated": 0, "valid": 0, "emitted": [],
                "denied": "base_token_price_unavailable", "details": []}

    cycles = enumerate_cycles(base_token, intermediates)
    details: List[Dict[str, Any]] = []
    emitted = []
    valid = 0
    for cyc in cycles:
        priced = await evaluate_cycle(cyc, start_amount=start_amount_tokens,
                                      quote_fn=quote_fn)
        if priced is None:
            details.append({"cycle": list(cyc), "status": "unquotable"})
            continue
        gross_usd = priced["gross_edge_tokens"] * base_token_price_usd
        notional_usd = start_amount_tokens * base_token_price_usd
        borrow_usd = notional_usd
        econ = await compute_true_net_profit(
            chain=chain, gas_model=gas_model, gross_profit_usd=gross_usd,
            borrow_amount_usd=borrow_usd, notional_usd=notional_usd,
            route_gas_units=route_gas_units, native_usd=native_usd,
            borrow_token=base_token, liquidity_by_provider=liquidity_by_provider,
            fee_bps_by_provider=fee_bps_by_provider)
        if econ.get("denied"):
            details.append({"cycle": list(cyc), "status": "denied",
                            "reason": econ.get("reason"),
                            "gross_usd": round(gross_usd, 4)})
            continue
        net = econ["true_net_profit_usd"]
        rec = {"cycle": list(cyc), "status": "priced",
               "gross_usd": round(gross_usd, 4), "true_net_usd": net,
               "provider": econ["provider"], "provider_fee_usd": econ["provider_fee_usd"]}
        if net >= min_net_profit_usd:
            valid += 1
            rec["status"] = "economically_valid"
            opp = emit_flash_candidate(
                asset=f"{cyc[0]}->{cyc[1]}->{cyc[2]}->{cyc[3]}",
                chain=chain, chain_id=chain_id,
                route_tokens=list(cyc),
                buy_venue=None, sell_venue=None,
                expected_profit_usd=net, capital_required_usd=borrow_usd,
                provenance=DataProvenance.REAL if native_usd else DataProvenance.SIMULATED,
                metadata={"triangular_legs": priced["legs"],
                          "provider": econ["provider"],
                          "true_net_breakdown": econ["breakdown"]})
            emitted.append(opp)
        details.append(rec)
    return {"evaluated": len(cycles), "valid": valid,
            "emitted": emitted, "details": details}


async def discover_triangular_multi(
    *, bases: List[Dict[str, Any]], **common) -> Dict[str, Any]:
    """Run triangular discovery over MULTIPLE base assets (reuses the single-
    base enumerator — no second pipeline). ``bases`` is a list of dicts, each:
    ``{"base_token", "intermediates", "start_amount_tokens", "base_token_price_usd"}``.
    Aggregates emitted candidates + per-base details.
    """
    total_eval = 0
    total_valid = 0
    emitted: List[Any] = []
    per_base: Dict[str, Any] = {}
    for b in bases:
        res = await discover_triangular(
            base_token=b["base_token"], intermediates=b["intermediates"],
            start_amount_tokens=b["start_amount_tokens"],
            base_token_price_usd=b.get("base_token_price_usd"), **common)
        total_eval += res.get("evaluated", 0)
        total_valid += res.get("valid", 0)
        emitted.extend(res.get("emitted", []))
        per_base[b["base_token"]] = {"evaluated": res.get("evaluated", 0),
                                     "valid": res.get("valid", 0),
                                     "denied": res.get("denied")}
    return {"evaluated": total_eval, "valid": total_valid,
            "emitted": emitted, "per_base": per_base}


# --------------------------------------------------------------------------
# Live Uniswap-V3 QuoterV2 client (read-only, fail-closed).
# --------------------------------------------------------------------------
UNIV3_QUOTER_V2: Dict[str, str] = {
    "ethereum": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    "arbitrum": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    "optimism": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    "polygon": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
    "base": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
}
_SEL_QUOTE_SINGLE = "0x" + function_signature_to_4byte_selector(
    "quoteExactInputSingle((address,address,uint256,uint24,uint160))").hex()


class UniV3QuoteClient:
    """Real quoteExactInputSingle over an EVM provider, best-of-fee-tiers.

    For each leg it tries every configured fee tier and returns the BEST
    (max) amount_out — real best-execution across pools. ``None`` ⇒ no tier is
    quotable (fail-closed; the leg/cycle is skipped, never priced with a guess).
    """

    DEFAULT_FEE_TIERS = (500, 3000, 10000, 100)

    def __init__(self, provider, chain: str,
                 tokens: Dict[str, Dict[str, Any]],
                 fee_tier: Optional[int] = None,
                 fee_tiers: Optional[List[int]] = None):
        self._p = provider
        self._quoter = UNIV3_QUOTER_V2.get((chain or "").lower())
        self._tokens = {k.upper(): v for k, v in tokens.items()}
        if fee_tiers:
            self._fees = list(fee_tiers)
        elif fee_tier is not None:
            self._fees = [fee_tier]
        else:
            self._fees = list(self.DEFAULT_FEE_TIERS)

    async def _quote_tier(self, ti, to, amt_wei: int, fee: int) -> Optional[float]:
        data = (_SEL_QUOTE_SINGLE
                + ti["address"].lower().replace("0x", "").rjust(64, "0")
                + to["address"].lower().replace("0x", "").rjust(64, "0")
                + f"{amt_wei:064x}" + f"{fee:064x}" + f"{0:064x}")
        try:
            raw = await self._p.eth_call({"to": self._quoter, "data": data})
        except Exception:  # noqa: BLE001
            return None
        if not raw or raw in ("0x", "0x0"):
            return None
        try:
            return int(raw[2:66], 16) / (10 ** to["decimals"])
        except (ValueError, IndexError):
            return None

    async def quote(self, sym_in: str, sym_out: str,
                    amount_in: float) -> Optional[float]:
        if not self._quoter:
            return None
        ti = self._tokens.get(sym_in.upper())
        to = self._tokens.get(sym_out.upper())
        if not ti or not to:
            return None
        amt_wei = int(amount_in * (10 ** ti["decimals"]))
        best: Optional[float] = None
        for fee in self._fees:
            out = await self._quote_tier(ti, to, amt_wei, fee)
            if out is not None and (best is None or out > best):
                best = out
        return best


__all__ = [
    "enumerate_cycles", "evaluate_cycle", "discover_triangular",
    "discover_triangular_multi", "UniV3QuoteClient", "UNIV3_QUOTER_V2",
]
