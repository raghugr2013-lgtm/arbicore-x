"""CapitalAllocationPolicy — clip oversize requests, never grow them."""
from __future__ import annotations

from typing import Optional

from .config import PolicyConfig


class CapitalAllocationPolicy:
    def __init__(self, cfg: PolicyConfig) -> None:
        self._cfg = cfg

    def clip_capital(self, *, requested_usd: float,
                     chain: Optional[str] = None,
                     opportunity_type: Optional[str] = None) -> float:
        clipped = float(requested_usd)
        clipped = min(clipped, self._cfg.max_per_trade_usd)
        if opportunity_type and opportunity_type in (
                self._cfg.per_type_caps_usd or {}):
            clipped = min(
                clipped,
                self._cfg.per_type_caps_usd[opportunity_type])
        # per-chain / per-day caps require external counters — the
        # policy exposes them but doesn't track them in-memory (that's
        # the executor's job in a future phase).
        return max(0.0, clipped)

    def to_dict(self) -> dict:
        return {
            "max_per_trade_usd":      self._cfg.max_per_trade_usd,
            "max_per_chain_usd":      self._cfg.max_per_chain_usd,
            "max_daily_notional_usd": self._cfg.max_daily_notional_usd,
            "per_type_caps_usd":      dict(self._cfg.per_type_caps_usd or {}),
        }
