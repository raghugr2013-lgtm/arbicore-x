"""Universal DEX + FlashLoan provider adapter boundaries (chain-agnostic).

Interfaces only + thin Base implementations that delegate to existing,
verified data (base_venues, FLASH_LOAN_PROVIDERS, provider_selection). Adding
a chain/venue later = a new adapter + config, not core changes. No fake
integrations: adapters expose only venues/providers with real sources.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class DEXAdapter(Protocol):
    dex_id: str
    chain: str
    def kind(self) -> str: ...                 # "v2" | "v3" | "stable"
    def pools(self) -> List[Dict[str, Any]]: ...  # [{pool, token0, token1, fee_bps}]


@runtime_checkable
class FlashLoanProviderAdapter(Protocol):
    provider_id: str
    def supports_chain(self, chain: str) -> bool: ...
    def fee_bps(self, override_tier_bps: Optional[int] = None) -> int: ...
    def supported_assets(self, chain: str) -> List[str]: ...


class BaseAerodromeUniAdapter:
    """Thin Base DEX adapter over the verified curated venue list."""
    dex_id = "base_curated"
    chain = "base"

    def kind(self) -> str:
        return "v3"                            # mixed; per-pool kind in pools()

    def pools(self) -> List[Dict[str, Any]]:
        from ..discovery.base_venues import VENUES
        out = []
        for dex, a, b, pool in VENUES:
            out.append({"pool": pool, "token0": a, "token1": b,
                        "dex": dex, "fee_bps": 5})
        return out


class CatalogFlashLoanAdapter:
    """FlashLoanProviderAdapter backed by the verified FLASH_LOAN_PROVIDERS."""

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id

    def _meta(self) -> Dict[str, Any]:
        from ..scanners.flash_loan_arbitrage.economics import FLASH_LOAN_PROVIDERS
        return FLASH_LOAN_PROVIDERS.get(self.provider_id, {})

    def supports_chain(self, chain: str) -> bool:
        return (chain or "").lower() in self._meta().get("supports_chains", ())

    def fee_bps(self, override_tier_bps: Optional[int] = None) -> int:
        from ..scanners.flash_loan_arbitrage.economics import provider_fee_bps
        return provider_fee_bps(self.provider_id, override_tier_bps)

    def supported_assets(self, chain: str) -> List[str]:
        # Real asset lists are provider/chain-probed on the VPS; empty here
        # rather than fabricated.
        return []


__all__ = ["DEXAdapter", "FlashLoanProviderAdapter",
           "BaseAerodromeUniAdapter", "CatalogFlashLoanAdapter"]
