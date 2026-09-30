"""GENERIC_DEX route engine — buy on venue A, sell on venue B (single hop each).

A read-only, fail-closed orchestrator that composes ALREADY-VALIDATED building
blocks — it introduces NO new quote path and NO new economics math:

* exact-size quoting        -> execution.quoter.QuoterRegistry
                               (validated Uniswap V3 + Balancer V2 backends)
* USD pricing / exact size  -> H05 MultichainPriceSource + registry decimals
* flash-loan fee catalog     -> flash_loan_arbitrage.economics.provider_fee_bps
* net-profit economic gate   -> flash_loan_arbitrage.economics
                               .FlashLoanEconomicsAssessor (aggregate_economics)

Route shape (same-token atomic cycle):

    borrow BORROW_TOKEN (exact size)
        -> BUY  on venue A:  BORROW_TOKEN -> INTERMEDIATE
        -> SELL on venue B:  INTERMEDIATE -> BORROW_TOKEN
        -> repay flash loan + premium

Economic gate (immutable): net atomic profit must clear the $25 floor. Every
unknown fails CLOSED with an explicit reason and NEVER becomes zero:

    unknown USD price     -> UNKNOWN_PRICE
    unknown decimals      -> UNKNOWN_DECIMALS
    leg quote failed      -> LEG1_QUOTE_FAILED / LEG2_QUOTE_FAILED
      (insufficient / unknown liquidity surfaces here — the exact-size quote is
       the authoritative per-size liquidity proof)
    unknown gas           -> UNKNOWN_GAS   (never falls back to a default gas)
    unknown flash fee     -> UNSUPPORTED_FLASH_PROVIDER
    same start/end != cycle -> SAME_TOKEN_VIOLATION / INVALID_ROUTE
    non-positive / < floor  -> NON_POSITIVE_NET / BELOW_PROFIT_FLOOR

Six-chain architecture preserved (chain is a free parameter; quotes only succeed
where a validated adapter + RPC exist, and the flash provider must support the
chain). NO signing, NO broadcast, NO execution — evaluation only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from eth_utils import to_checksum_address

from ..models.enums import MevRiskLevel, StrategyType
from .flash_loan_arbitrage.economics import (
    FLASH_LOAN_PROVIDERS, FlashLoanEconomicsAssessor)

# --------------------------------------------------------------------------- #
# Immutable economic gate (mirrors data/scanner_config_defaults.py).          #
# Do NOT weaken. The constructor may only RAISE the floor, never lower it.    #
# --------------------------------------------------------------------------- #
MIN_ATOMIC_PROFIT_USD: float = 25.0

# Route status vocabulary (fail-closed).
ELIGIBLE = "eligible"
SAME_TOKEN_VIOLATION = "same_token_violation"
INVALID_ROUTE = "invalid_route"
UNSUPPORTED_FLASH_PROVIDER = "unsupported_flash_provider"
UNKNOWN_PRICE = "unknown_price"
UNKNOWN_DECIMALS = "unknown_decimals"
LEG1_QUOTE_FAILED = "leg1_quote_failed"
LEG2_QUOTE_FAILED = "leg2_quote_failed"
UNKNOWN_GAS = "unknown_gas"
UNKNOWN_LIQUIDITY = "unknown_liquidity"
INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
NON_POSITIVE_NET = "non_positive_net"
BELOW_PROFIT_FLOOR = "below_profit_floor"


PriceUsdFn = Callable[[str, str], Awaitable[Optional[float]]]
DecimalsFn = Callable[[str, str], Optional[int]]
GasEstimatorFn = Callable[[str], Awaitable[Optional[float]]]


def _finite_pos(x: Any) -> bool:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0.0


@dataclass(frozen=True)
class VenueSpec:
    """One DEX venue able to quote the leg's token pair. Carries the explicit
    on-chain pool identity — never a fabricated address."""
    dex: str
    fee: Optional[int] = None            # UniV3 fee tier (ppm-ish, backend-normalised)
    pool_id: Optional[str] = None        # Balancer V2 bytes32
    pool_address: Optional[str] = None   # Balancer V2 pool
    tick_spacing: Optional[int] = None
    fee_bps: Optional[int] = None        # observed pool fee (telemetry only)
    venue_id: Optional[str] = None

    def hop(self, token_in: str, token_out: str) -> Dict[str, Any]:
        h: Dict[str, Any] = {"dex": self.dex, "token_in": token_in,
                             "token_out": token_out}
        if self.fee is not None:
            h["fee"] = self.fee
        if self.tick_spacing is not None:
            h["tick_spacing"] = self.tick_spacing
        if self.pool_id is not None:
            h["pool_id"] = self.pool_id
        if self.pool_address is not None:
            h["pool_address"] = self.pool_address
        return h

    def observed_fee_bps(self) -> int:
        if self.fee_bps is not None:
            return int(self.fee_bps)
        if self.fee is not None:            # UniV3 fee is in ppm -> bps
            return int(int(self.fee) / 100)
        return 30

    def label(self, i: int) -> str:
        return self.venue_id or f"{self.dex}_{i}"


@dataclass(frozen=True)
class QuoteLeg:
    role: str
    dex: str
    token_in: str
    token_out: str
    amount_in_wei: int
    amount_out_wei: int
    status: str
    block_number: Optional[int]
    pool: Optional[str]


@dataclass(frozen=True)
class GenericDexRouteResult:
    status: str
    eligible: bool
    strategy: str
    chain: str
    borrow_token: str
    intermediate_token: str
    amount_usd_requested: float
    borrow_amount_wei: int
    borrow_amount_usd: float
    borrow_price_usd: Optional[float]
    flash_provider: str
    venue_buy: Optional[str]
    venue_sell: Optional[str]
    leg1: Optional[QuoteLeg]
    leg2: Optional[QuoteLeg]
    gross_profit_wei: int
    gross_profit_usd: float
    gross_profit_pct: float
    flash_fee_usd: float
    gas_cost_usd: float
    net_profit_usd: float
    min_atomic_profit_usd: float
    economics_metadata: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "status": self.status, "eligible": self.eligible,
            "strategy": self.strategy, "chain": self.chain,
            "borrow_token": self.borrow_token,
            "intermediate_token": self.intermediate_token,
            "borrow_amount_usd": self.borrow_amount_usd,
            "flash_provider": self.flash_provider,
            "venue_buy": self.venue_buy, "venue_sell": self.venue_sell,
            "gross_profit_usd": self.gross_profit_usd,
            "gross_profit_pct": self.gross_profit_pct,
            "flash_fee_usd": self.flash_fee_usd,
            "gas_cost_usd": self.gas_cost_usd,
            "net_profit_usd": self.net_profit_usd,
            "min_atomic_profit_usd": self.min_atomic_profit_usd,
            "reasons": list(self.reasons),
        }


class GenericDexRouteEngine:
    """Stateless GENERIC_DEX (2-venue, single-hop each) route evaluator."""

    def __init__(
        self, quoter_registry, price_source, *,
        decimals_fn: Optional[DecimalsFn] = None,
        economics_assessor: Optional[FlashLoanEconomicsAssessor] = None,
        min_atomic_profit_usd: float = MIN_ATOMIC_PROFIT_USD,
        mev_risk_level: MevRiskLevel = MevRiskLevel.MEDIUM,
    ) -> None:
        self.quoter = quoter_registry
        self.price_source = price_source
        self.decimals_fn = decimals_fn or _default_decimals_fn
        # Immutable floor — can only be raised, never lowered below $25.
        self.min_atomic = max(MIN_ATOMIC_PROFIT_USD, float(min_atomic_profit_usd))
        self.mev = mev_risk_level
        if economics_assessor is not None:
            self.assessor = economics_assessor
        else:
            from ..intelligence.roi_probability import ROIProbabilityEngine
            self.assessor = FlashLoanEconomicsAssessor(
                roi_engine=ROIProbabilityEngine())

    def _deny(self, status: str, reason: str, **kw) -> GenericDexRouteResult:
        base = dict(
            status=status, eligible=False, strategy=StrategyType.GENERIC_DEX.value,
            chain=kw.get("chain", ""), borrow_token=kw.get("borrow_token", ""),
            intermediate_token=kw.get("intermediate_token", ""),
            amount_usd_requested=float(kw.get("amount_usd", 0.0)),
            borrow_amount_wei=int(kw.get("borrow_amount_wei", 0)),
            borrow_amount_usd=float(kw.get("borrow_amount_usd", 0.0)),
            borrow_price_usd=kw.get("borrow_price_usd"),
            flash_provider=kw.get("flash_provider", ""),
            venue_buy=kw.get("venue_buy"), venue_sell=kw.get("venue_sell"),
            leg1=kw.get("leg1"), leg2=kw.get("leg2"),
            gross_profit_wei=int(kw.get("gross_profit_wei", 0)),
            gross_profit_usd=float(kw.get("gross_profit_usd", 0.0)),
            gross_profit_pct=float(kw.get("gross_profit_pct", 0.0)),
            flash_fee_usd=float(kw.get("flash_fee_usd", 0.0)),
            gas_cost_usd=float(kw.get("gas_cost_usd", 0.0)),
            net_profit_usd=float(kw.get("net_profit_usd", 0.0)),
            min_atomic_profit_usd=self.min_atomic,
            economics_metadata=kw.get("economics_metadata", {}),
            reasons=[reason],
        )
        return GenericDexRouteResult(**base)

    async def evaluate_route(
        self, *, chain: str, borrow_token: str, intermediate_token: str,
        amount_usd: float, venue_buy: VenueSpec, venue_sell: VenueSpec,
        flash_provider: str, rpc_url: Optional[str] = None,
        gas_cost_usd: Optional[float] = None,
        gas_estimator: Optional[GasEstimatorFn] = None,
        route_tvl_usd: Optional[float] = None,
        min_tvl_usd: float = 0.0,
    ) -> GenericDexRouteResult:
        chain_n = (chain or "").strip().lower()
        try:
            bt = to_checksum_address(borrow_token)
            it = to_checksum_address(intermediate_token)
        except (ValueError, TypeError):
            return self._deny(INVALID_ROUTE, "malformed token address",
                              chain=chain_n, flash_provider=flash_provider)
        ctx = dict(chain=chain_n, borrow_token=bt, intermediate_token=it,
                   amount_usd=amount_usd, flash_provider=(flash_provider or "").lower(),
                   venue_buy=venue_buy.label(0), venue_sell=venue_sell.label(1))

        # (1) same-token cycle validation
        if bt == it:
            return self._deny(SAME_TOKEN_VIOLATION,
                              "borrow token equals intermediate token", **ctx)

        # (2) flash-loan provider must exist AND support this chain (fee known)
        prov = (flash_provider or "").lower()
        meta = FLASH_LOAN_PROVIDERS.get(prov)
        if meta is None or chain_n not in meta.get("supports_chains", ()):
            return self._deny(UNSUPPORTED_FLASH_PROVIDER,
                              f"flash provider '{prov}' not available on {chain_n}",
                              **ctx)

        # (3) exact-size — USD price + decimals (fail closed on unknown)
        price = await self.price_source.price_usd(chain_n, bt)
        if not _finite_pos(price):
            return self._deny(UNKNOWN_PRICE,
                              f"USD price unavailable for {bt} on {chain_n}", **ctx)
        dec = self.decimals_fn(chain_n, bt)
        if dec is None or not (0 < int(dec) <= 36):
            return self._deny(UNKNOWN_DECIMALS,
                              f"decimals unavailable for {bt} on {chain_n}",
                              borrow_price_usd=price, **ctx)
        dec = int(dec)
        borrow_wei = int(math.floor(float(amount_usd) / float(price) * (10 ** dec)))
        if borrow_wei <= 0:
            return self._deny(UNKNOWN_PRICE,
                              "computed borrow size is non-positive",
                              borrow_price_usd=price, **ctx)
        borrow_usd = borrow_wei / (10 ** dec) * float(price)
        ctx.update(borrow_amount_wei=borrow_wei, borrow_amount_usd=borrow_usd,
                   borrow_price_usd=price)

        # (4) leg 1 — BUY on venue A: BORROW_TOKEN -> INTERMEDIATE (exact size)
        hop1 = venue_buy.hop(bt, it)
        hop1["amount_in_wei"] = borrow_wei
        rq1 = await self.quoter.quote_route(chain=chain_n, hops=[hop1], rpc_url=rpc_url)
        leg1 = _leg_from_route("buy", venue_buy.dex, bt, it, borrow_wei, rq1)
        if leg1.status != "ok" or leg1.amount_out_wei <= 0:
            return self._deny(LEG1_QUOTE_FAILED,
                              f"buy leg quote failed ({leg1.status})",
                              leg1=leg1, **ctx)

        # (5) leg 2 — SELL on venue B: INTERMEDIATE -> BORROW_TOKEN
        hop2 = venue_sell.hop(it, bt)
        hop2["amount_in_wei"] = leg1.amount_out_wei
        rq2 = await self.quoter.quote_route(chain=chain_n, hops=[hop2], rpc_url=rpc_url)
        leg2 = _leg_from_route("sell", venue_sell.dex, it, bt,
                               leg1.amount_out_wei, rq2)
        if leg2.status != "ok" or leg2.amount_out_wei <= 0:
            return self._deny(LEG2_QUOTE_FAILED,
                              f"sell leg quote failed ({leg2.status})",
                              leg1=leg1, leg2=leg2, **ctx)

        # (6) optional pool-TVL liquidity gate (fail closed when requested)
        if _finite_pos(min_tvl_usd):
            if route_tvl_usd is None:
                return self._deny(UNKNOWN_LIQUIDITY,
                                  "pool TVL required but unknown",
                                  leg1=leg1, leg2=leg2, **ctx)
            if float(route_tvl_usd) < float(min_tvl_usd):
                return self._deny(INSUFFICIENT_LIQUIDITY,
                                  f"route TVL ${route_tvl_usd:.0f} < "
                                  f"${min_tvl_usd:.0f}", leg1=leg1, leg2=leg2, **ctx)

        # (7) gross round-trip (both legs quote-inclusive of pool fee + impact)
        out_wei = leg2.amount_out_wei
        gross_wei = out_wei - borrow_wei
        gross_pct = gross_wei / borrow_wei * 100.0
        gross_usd = gross_wei / (10 ** dec) * float(price)

        # (8) gas — explicit live estimate required; NEVER a silent default
        gas_usd = gas_cost_usd
        if not _finite_pos(gas_usd) and gas_estimator is not None:
            gas_usd = await gas_estimator(chain_n)
        if not _finite_pos(gas_usd):
            return self._deny(UNKNOWN_GAS,
                              "gas cost unavailable (no live estimate)",
                              leg1=leg1, leg2=leg2, gross_profit_wei=gross_wei,
                              gross_profit_usd=gross_usd, gross_profit_pct=gross_pct,
                              **ctx)
        gas_usd = float(gas_usd)

        # (9) net-profit economic gate — reuse FlashLoanEconomicsAssessor
        econ = self.assessor.assess(
            provider=prov, chain=chain_n, borrow_token=bt,
            borrow_amount_usd=borrow_usd,
            hop_legs=[
                {"venue_id": venue_buy.label(0), "fee_bps": venue_buy.observed_fee_bps(),
                 "slippage_pct": 0.0},
                {"venue_id": venue_sell.label(1), "fee_bps": venue_sell.observed_fee_bps(),
                 "slippage_pct": 0.0},
            ],
            signal_categories=["generic_dex"],
            real_outcomes=[], synthetic_outcomes=None,
            gross_profit_pct=gross_pct, mev_risk_level=self.mev,
            gas_cost_usd_override=gas_usd, gross_is_quote_inclusive=True,
        )
        net = float(econ.atomic_profit_usd)
        flash_fee_usd = float(econ.flash_loan_fee_usd)

        common = dict(
            leg1=leg1, leg2=leg2, gross_profit_wei=gross_wei,
            gross_profit_usd=gross_usd, gross_profit_pct=gross_pct,
            flash_fee_usd=flash_fee_usd, gas_cost_usd=gas_usd,
            net_profit_usd=net, economics_metadata=econ.to_metadata(), **ctx)

        # (10) decision — non-positive OR below immutable floor => DENY
        if net <= 0.0:
            return self._deny(NON_POSITIVE_NET,
                              f"net profit ${net:.2f} <= 0", **common)
        if net < self.min_atomic:
            return self._deny(BELOW_PROFIT_FLOOR,
                              f"net profit ${net:.2f} < floor "
                              f"${self.min_atomic:.2f}", **common)

        result = self._deny(ELIGIBLE,
                            f"net profit ${net:.2f} >= floor ${self.min_atomic:.2f}",
                            **common)
        return GenericDexRouteResult(**{**result.__dict__, "eligible": True})


def _leg_from_route(role: str, dex: str, token_in: str, token_out: str,
                     amount_in_wei: int, rq) -> QuoteLeg:
    hop = rq.hops[0] if getattr(rq, "hops", None) else None
    status = rq.status if getattr(rq, "status", None) == "ok" else (
        getattr(hop, "status", None) or "fallback:break_even")
    return QuoteLeg(
        role=role, dex=dex, token_in=token_in, token_out=token_out,
        amount_in_wei=int(amount_in_wei),
        amount_out_wei=int(getattr(rq, "final_amount_out_wei", 0) or 0),
        status="ok" if getattr(rq, "status", None) == "ok" else str(status),
        block_number=getattr(hop, "block_number", None),
        pool=getattr(hop, "quoter_contract", None),
    )


def _default_decimals_fn(chain: str, token: str) -> Optional[int]:
    from ..runtime.composition import registry_decimals
    return registry_decimals(chain, token)
