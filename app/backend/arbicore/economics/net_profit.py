"""Net-profit economics engine (Stage 3 · v2.6.0).

Every opportunity produced by a Stage-2/3 scanner is now normalised
through this module before it is emitted to MID or the Paper Engine.

Contract
--------
    result = compute_net_profit(
        gross_spread_bps=<float>,
        notional_usd=<float>,
        buy_venue_fee_bps=<float>, sell_venue_fee_bps=<float>,
        withdrawal_fee_usd=<float>,
        gas_native_wei=<int|None>, native_price_usd=<float|None>,
        estimated_gas_units=<int|None>,
        slippage_bps=<float>=0,
        flash_loan_notional_usd=<float>=0,
        flash_loan_fee_bps=<float>=0,
        liquidity_impact_bps=<float>=0,
    ) -> NetProfitResult

The function is pure — zero I/O, deterministic, easy to unit-test. Every
downstream consumer (LiveMarketScanner, CexDexScanner, DexDexScanner,
PaperEngine) uses this exact function.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class NetProfitResult:
    """A structured cost breakdown that Paper Engine + Dashboard both use."""
    gross_profit_usd: float
    trading_fees_usd: float
    withdrawal_fees_usd: float
    gas_cost_usd: float
    slippage_cost_usd: float
    flash_loan_fee_usd: float
    liquidity_impact_usd: float
    total_cost_usd: float
    net_profit_usd: float
    net_profit_bps: float           # net_profit / notional × 10_000
    is_profitable: bool
    inputs: Dict[str, Any]          # echo of the input args for auditability

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_net_profit(
    *,
    gross_spread_bps: float,
    notional_usd: float,
    buy_venue_fee_bps: float = 0.0,
    sell_venue_fee_bps: float = 0.0,
    withdrawal_fee_usd: float = 0.0,
    gas_native_wei: Optional[int] = None,
    native_price_usd: Optional[float] = None,
    estimated_gas_units: Optional[int] = None,
    slippage_bps: float = 0.0,
    flash_loan_notional_usd: float = 0.0,
    flash_loan_fee_bps: float = 0.0,
    liquidity_impact_bps: float = 0.0,
) -> NetProfitResult:
    gross_profit_usd = (float(gross_spread_bps) / 10_000.0) * float(notional_usd)

    trading_fees_usd = (
        (buy_venue_fee_bps + sell_venue_fee_bps) / 10_000.0 * notional_usd
    )
    slippage_cost_usd = (float(slippage_bps) / 10_000.0) * notional_usd
    liquidity_impact_usd = (
        float(liquidity_impact_bps) / 10_000.0 * notional_usd
    )
    flash_loan_fee_usd = (
        float(flash_loan_fee_bps) / 10_000.0 * float(flash_loan_notional_usd)
    )

    # Gas: if a full native-fee triple is supplied compute it; otherwise 0.
    gas_cost_usd = 0.0
    if (gas_native_wei is not None and native_price_usd is not None
            and estimated_gas_units is not None):
        gas_cost_native = (
            float(gas_native_wei) * float(estimated_gas_units) / 1e18)
        gas_cost_usd = gas_cost_native * float(native_price_usd)

    total_cost_usd = (
        trading_fees_usd + float(withdrawal_fee_usd) + gas_cost_usd
        + slippage_cost_usd + flash_loan_fee_usd + liquidity_impact_usd
    )
    net_profit_usd = gross_profit_usd - total_cost_usd
    net_profit_bps = (
        net_profit_usd / notional_usd * 10_000.0 if notional_usd > 0 else 0.0
    )

    return NetProfitResult(
        gross_profit_usd=round(gross_profit_usd, 6),
        trading_fees_usd=round(trading_fees_usd, 6),
        withdrawal_fees_usd=round(float(withdrawal_fee_usd), 6),
        gas_cost_usd=round(gas_cost_usd, 6),
        slippage_cost_usd=round(slippage_cost_usd, 6),
        flash_loan_fee_usd=round(flash_loan_fee_usd, 6),
        liquidity_impact_usd=round(liquidity_impact_usd, 6),
        total_cost_usd=round(total_cost_usd, 6),
        net_profit_usd=round(net_profit_usd, 6),
        net_profit_bps=round(net_profit_bps, 3),
        is_profitable=bool(net_profit_usd > 0),
        inputs={
            "gross_spread_bps": gross_spread_bps,
            "notional_usd": notional_usd,
            "buy_venue_fee_bps": buy_venue_fee_bps,
            "sell_venue_fee_bps": sell_venue_fee_bps,
            "withdrawal_fee_usd": withdrawal_fee_usd,
            "gas_native_wei": gas_native_wei,
            "native_price_usd": native_price_usd,
            "estimated_gas_units": estimated_gas_units,
            "slippage_bps": slippage_bps,
            "flash_loan_notional_usd": flash_loan_notional_usd,
            "flash_loan_fee_bps": flash_loan_fee_bps,
            "liquidity_impact_bps": liquidity_impact_bps,
        },
    )


# Reasonable venue fee defaults (spot maker/taker average, expressed in bps).
# These are updated infrequently and should be overriden per operator
# via env if desired.
VENUE_FEE_BPS: Dict[str, float] = {
    "binance":  10.0,   # 0.10% VIP-0
    "bybit":    10.0,
    "okx":      10.0,
    "coinbase": 60.0,   # coinbase advanced default
    "kraken":   26.0,
    "kucoin":   10.0,
    "uniswap_v2": 30.0,
    "uniswap_v3": 5.0,   # 0.05% low tier — v3 varies by pool
    "sushiswap":  30.0,
    "pancakeswap": 25.0,
    "curve":       4.0,
    "balancer_v2": 10.0,
    "jupiter":     5.0,
    "raydium":    25.0,
}

# Reasonable withdrawal-fee defaults (USD-equivalent flat per network hop).
WITHDRAWAL_FEE_USD: Dict[str, float] = {
    "cex_to_cex": 8.0,       # BTC network fee equivalent
    "cex_to_dex": 6.0,       # ERC-20 transfer to on-chain wallet
    "dex_to_cex": 6.0,
    "dex_to_dex": 0.0,       # in-chain hop, gas covers it
    "cex_only":   0.0,
}

# Rough native-token price fallback (USD). Live gas provider price is used
# when available; this is a last-resort static number.
NATIVE_PRICE_USD_FALLBACK: Dict[str, float] = {
    "ethereum": 1900.0,
    "arbitrum": 1900.0,
    "base":     1900.0,
    "optimism": 1900.0,
    "polygon":     0.6,
    "bnb":       320.0,
    "solana":    100.0,
    "cex":         0.0,
}


__all__ = [
    "NetProfitResult", "compute_net_profit",
    "VENUE_FEE_BPS", "WITHDRAWAL_FEE_USD", "NATIVE_PRICE_USD_FALLBACK",
]
