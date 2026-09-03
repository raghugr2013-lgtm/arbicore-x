"""Step 2 · Flash-provider optimizer (fail-closed, multi-provider).

Given a single candidate (chain, borrow token, borrow amount), compares every
flash-loan provider that supports the chain and picks the cheapest FEASIBLE one.

Reuses the existing flash-loan infrastructure — the ``FLASH_LOAN_PROVIDERS``
catalog and ``provider_fee_bps`` from ``economics.py``. It does NOT replace
``select_flash_loan_provider`` (kept as-is); it adds the stricter economics the
multi-chain/multi-strategy expansion needs:

  * ACTUAL fee — a provider is only feasible if its fee is KNOWN. Providers with
    a fixed protocol fee (Balancer V2 / Morpho Blue = 0 bps, Aave V3 = 5 bps)
    are known by protocol design. Uniswap-V3-style providers whose fee depends
    on the borrow-pool tier are feasible ONLY when the resolved tier is supplied
    in ``fee_bps_by_provider``. We NEVER fall back to an assumed/guessed fee for
    a provider whose real fee is unknown — that route is DENIED.
    (A genuine 0-bps protocol fee is a real fee, not an assumption.)
  * ACTUAL liquidity — feasible only if available liquidity for the borrow asset
    is KNOWN and >= the borrow amount. Unknown liquidity is never assumed
    sufficient.
  * Provider constraints / callback (extra) gas — each provider carries a
    representative flash-callback gas overhead so the downstream gas model can
    price the extra units. Unknown constraint does not fabricate a value.

Pure / deterministic — no network I/O. The caller supplies the on-chain reads
(liquidity, resolved Uniswap tier) so this stays unit-testable offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .economics import FLASH_LOAN_PROVIDERS, provider_fee_bps


# Per-provider constraints. ``fee_fixed`` marks providers whose fee is a real
# protocol constant (safe to read from the catalog). ``callback_extra_gas_units``
# is a conservative estimate of the flash-loan callback overhead ON TOP of the
# swap legs; the gas model adds it to the tx gas budget.
FLASH_PROVIDER_CONSTRAINTS: Dict[str, Dict[str, object]] = {
    "balancer_v2": {"fee_fixed": True, "callback_extra_gas_units": 90_000},
    "aave_v3": {"fee_fixed": True, "callback_extra_gas_units": 120_000},
    "morpho_blue": {"fee_fixed": True, "callback_extra_gas_units": 70_000},
    # Uniswap V3 flash fee == borrow-pool swap-fee tier → NOT fixed; the caller
    # must supply the resolved tier in ``fee_bps_by_provider`` or this provider
    # is refused (fee_unresolved) — never assumed.
    "uniswap_v3": {"fee_fixed": False, "callback_extra_gas_units": 100_000},
}


@dataclass
class OptimizedProvider:
    provider: Optional[str]
    fee_bps: Optional[int]
    fee_usd: Optional[float]
    available_liquidity_usd: Optional[float]
    callback_extra_gas_units: Optional[int]
    feasible: bool
    reason: str
    considered: List[Dict] = field(default_factory=list)


def _valid_fee_bps(v: object) -> bool:
    try:
        return int(v) >= 0
    except (TypeError, ValueError):
        return False


def optimize_flash_provider(
    *,
    chain: str,
    borrow_token: str,
    borrow_amount_usd: Optional[float],
    liquidity_by_provider: Optional[Dict[str, Optional[float]]] = None,
    fee_bps_by_provider: Optional[Dict[str, Optional[int]]] = None,
    require_liquidity: bool = True,
) -> OptimizedProvider:
    """Pick the cheapest feasible flash-loan provider for one candidate.

    Fail-closed: unknown/unreadable fee OR unknown/insufficient liquidity make a
    provider infeasible. If no provider is feasible, returns ``feasible=False``
    with a reason (``no_provider_supports_chain`` / ``no_feasible_provider``).
    """
    chain_n = (chain or "").lower()
    liq = liquidity_by_provider or {}
    fee_reads = fee_bps_by_provider or {}
    considered: List[Dict] = []

    if borrow_amount_usd is None or float(borrow_amount_usd) <= 0:
        return OptimizedProvider(
            provider=None, fee_bps=None, fee_usd=None,
            available_liquidity_usd=None, callback_extra_gas_units=None,
            feasible=False, reason="borrow_amount_unknown", considered=[])

    borrow = float(borrow_amount_usd)
    candidates: List[Dict] = []

    for name, meta in FLASH_LOAN_PROVIDERS.items():
        if chain_n not in meta.get("supports_chains", ()):
            continue
        constraint = FLASH_PROVIDER_CONSTRAINTS.get(name, {})

        # --- fee resolution (ACTUAL, never assumed) ---
        explicit = fee_reads.get(name)
        if explicit is not None:
            if not _valid_fee_bps(explicit):
                considered.append({"provider": name, "feasible": False,
                                   "reason": "fee_unreadable"})
                continue
            fee = int(explicit)
        elif constraint.get("fee_fixed"):
            fee = provider_fee_bps(name)   # real protocol constant
        else:
            considered.append({"provider": name, "feasible": False,
                               "reason": "fee_unresolved"})
            continue

        # --- liquidity (ACTUAL, never assumed sufficient) ---
        avail = liq.get(name)
        if require_liquidity:
            if avail is None:
                feasible, why = False, "liquidity_unreadable"
            elif float(avail) < borrow:
                feasible, why = False, (
                    f"insufficient_liquidity({float(avail):.0f}<{borrow:.0f})")
            else:
                feasible, why = True, "ok"
        else:
            feasible, why = True, "liquidity_not_required"

        extra_gas = constraint.get("callback_extra_gas_units")
        rec = {
            "provider": name,
            "fee_bps": fee,
            "fee_usd": round(borrow * fee / 10_000.0, 6),
            "available_liquidity_usd": avail,
            "callback_extra_gas_units": extra_gas,
            "feasible": feasible,
            "reason": why,
        }
        considered.append(rec)
        if feasible:
            candidates.append(rec)

    if not candidates:
        return OptimizedProvider(
            provider=None, fee_bps=None, fee_usd=None,
            available_liquidity_usd=None, callback_extra_gas_units=None,
            feasible=False,
            reason=("no_feasible_provider" if considered
                    else f"no_provider_supports_chain:{chain_n}"),
            considered=considered)

    # cheapest fee first; ties broken by deepest known liquidity.
    candidates.sort(key=lambda r: (r["fee_bps"],
                                   -(r["available_liquidity_usd"] or 0.0)))
    best = candidates[0]
    return OptimizedProvider(
        provider=best["provider"], fee_bps=best["fee_bps"],
        fee_usd=best["fee_usd"],
        available_liquidity_usd=best["available_liquidity_usd"],
        callback_extra_gas_units=best["callback_extra_gas_units"],
        feasible=True, reason="cheapest_feasible_provider",
        considered=considered)


__all__ = ["OptimizedProvider", "optimize_flash_provider",
           "FLASH_PROVIDER_CONSTRAINTS"]
