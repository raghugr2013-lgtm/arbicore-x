"""ArbiCore X — Route Success Tracking contract (Phase 3 prep, interface only)."""
from __future__ import annotations

from abc import ABC, abstractmethod


class RouteSuccessTracker(ABC):
    """Tracks realized success rate per route (buy_venue->sell_venue).

    Extends the Phase 1 ``SignalConfidenceEngine`` (which tracks persistence,
    not realized success) with actual outcome-based success once execution data
    exists. Must consume REAL data only. Not implemented in Phase 1.
    """

    @abstractmethod
    def record_result(self, route: str, *, succeeded: bool, profit_usd: float) -> None: ...

    @abstractmethod
    def get_success_rate(self, route: str) -> float:
        """Return realized success rate in [0, 100] for the route."""

    @abstractmethod
    def sample_size(self, route: str) -> int: ...
