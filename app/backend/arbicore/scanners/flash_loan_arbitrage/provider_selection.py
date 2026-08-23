"""T1 · Flash-loan provider selection kernel.

Chooses the cheapest *feasible* flash-loan provider for a borrow, given the
chain, and (when known) each provider's available liquidity for the borrow
asset. Preference is fee-driven: 0-fee venues (Balancer V2, Morpho Blue) win,
then Aave V3 (5 bps depth), then Uniswap V3 pool-tier.

Fail-closed: a provider is only feasible if its available liquidity for the
borrow asset is KNOWN and >= the borrow amount. Unknown liquidity is never
assumed sufficient (no fabricated liquidity). Pure / deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .economics import FLASH_LOAN_PROVIDERS, provider_fee_bps


@dataclass
class ProviderChoice:
    provider: Optional[str]
    fee_bps: Optional[int]
    available_liquidity_usd: Optional[float]
    feasible: bool
    reason: str
    considered: List[Dict] = field(default_factory=list)


def select_flash_loan_provider(
    *,
    chain: str,
    borrow_amount_usd: float,
    liquidity_by_provider: Optional[Dict[str, Optional[float]]] = None,
    fee_override_bps: Optional[Dict[str, int]] = None,
    require_liquidity: bool = True,
) -> ProviderChoice:
    chain = (chain or "").lower()
    liq = liquidity_by_provider or {}
    fee_over = fee_override_bps or {}
    considered: List[Dict] = []

    candidates = []
    for name, meta in FLASH_LOAN_PROVIDERS.items():
        if chain not in meta.get("supports_chains", ()):
            continue
        fee = provider_fee_bps(name, fee_over.get(name))
        avail = liq.get(name)
        if require_liquidity:
            feasible = avail is not None and float(avail) >= float(borrow_amount_usd)
            why = ("ok" if feasible else
                   ("liquidity_unverifiable" if avail is None
                    else f"insufficient_liquidity({avail:.0f}<{borrow_amount_usd:.0f})"))
        else:
            feasible, why = True, "liquidity_not_required"
        rec = {"provider": name, "fee_bps": fee,
               "available_liquidity_usd": avail, "feasible": feasible,
               "reason": why}
        considered.append(rec)
        if feasible:
            candidates.append(rec)

    if not candidates:
        return ProviderChoice(
            provider=None, fee_bps=None, available_liquidity_usd=None,
            feasible=False,
            reason=("no_feasible_provider" if considered
                    else f"no_provider_supports_chain:{chain}"),
            considered=considered)

    # cheapest fee first; break ties by deepest known liquidity.
    candidates.sort(key=lambda r: (r["fee_bps"],
                                   -(r["available_liquidity_usd"] or 0.0)))
    best = candidates[0]
    return ProviderChoice(
        provider=best["provider"], fee_bps=best["fee_bps"],
        available_liquidity_usd=best["available_liquidity_usd"],
        feasible=True, reason="cheapest_feasible_provider",
        considered=considered)


__all__ = ["ProviderChoice", "select_flash_loan_provider"]
