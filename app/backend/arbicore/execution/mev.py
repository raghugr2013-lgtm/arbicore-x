"""Wave 6C · MEV Router abstraction.

Wave 6C ships **routing metadata only** — nothing is ever submitted.
Actual transaction submission (broadcasting) is Wave 6E territory and
gated by the execution-mode ladder (must be ``LIMITED_LIVE`` or
``FULL_LIVE`` to submit anything).

Backends implement the ``MevRouterBackend`` protocol so that future
implementations (Flashbots protect, Eden, MEV-Blocker, chain-specific
private mempools) drop in without touching planning logic.

Every backend surface here is READ-ONLY and produces a
``RoutingDecision`` value object that describes *how* a plan would be
routed if execution were live — colour, target, deadline, fallback,
and warnings.  No transactions are ever broadcast in this wave.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger("arbicore.execution.mev")


ROUTER_KINDS: tuple = ("public_rpc", "private_bundle", "protect_relay")


@dataclass(frozen=True)
class RoutingDecision:
    router: str
    kind: str
    chain: str
    target: str                 # target url / relay identifier (never a secret)
    deadline_blocks: int
    fallback_router: Optional[str]
    private: bool               # true when submission would be hidden from public mempool
    protects_against: List[str] # e.g. ["sandwich","frontrun"]
    warnings: List[str]
    would_broadcast: bool       # ALWAYS False in Wave 6C — invariant asserted below
    method: str                 # "shadow_route_only"
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Extra invariant on serialise — nothing about live broadcast can leak.
        assert d["would_broadcast"] is False, "MEV router leaked would_broadcast=True"
        return d


class MevRouterBackend(Protocol):
    router: str
    kind: str

    def is_available(self) -> bool: ...

    def supports(self, chain: str) -> bool: ...

    async def route(self, *, chain: str,
                    protected: bool = True) -> RoutingDecision: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# PublicRpcRouter — default; simulates routing via the public mempool.
# ---------------------------------------------------------------------------

class PublicRpcRouter:
    router = "public_rpc"
    kind = "public_rpc"
    supports_chains = ("ethereum", "base", "arbitrum", "optimism", "polygon")

    def __init__(self, *, rpc_url: Optional[str] = None,
                 deadline_blocks: int = 3):
        self._rpc_url = rpc_url or os.environ.get("ARBICORE_RPC_URL", "public_rpc_placeholder")
        self._deadline = int(deadline_blocks)

    def is_available(self) -> bool:
        return True

    def supports(self, chain: str) -> bool:
        return chain in self.supports_chains

    async def route(self, *, chain: str, protected: bool = True) -> RoutingDecision:
        warnings: List[str] = []
        if protected:
            warnings.append(
                "public_rpc offers no MEV protection — sandwich/frontrun exposure remains"
            )
        return RoutingDecision(
            router=self.router,
            kind=self.kind,
            chain=chain,
            target="__public_rpc_placeholder__",  # redacted; never a secret
            deadline_blocks=self._deadline,
            fallback_router=None,
            private=False,
            protects_against=[],
            warnings=warnings,
            would_broadcast=False,
            method="shadow_route_only",
            generated_at=_now_iso(),
        )


# ---------------------------------------------------------------------------
# FlashbotsRouter — opt-in.  Wave 6C never submits bundles; only
# describes the routing decision that WOULD apply if broadcast were
# allowed.
# ---------------------------------------------------------------------------

class FlashbotsRouter:
    router = "flashbots_protect"
    kind = "protect_relay"
    supports_chains = ("ethereum",)  # Base uses MEV-Share; kept isolated below.

    def __init__(self, *,
                 relay_url: Optional[str] = None,
                 deadline_blocks: int = 3):
        self._relay_url = (relay_url
                           or os.environ.get("ARBICORE_MEV_RELAY_URL")
                           or "https://relay.flashbots.net")
        self._deadline = int(deadline_blocks)

    def is_available(self) -> bool:
        return True

    def supports(self, chain: str) -> bool:
        return chain in self.supports_chains

    async def route(self, *, chain: str, protected: bool = True) -> RoutingDecision:
        warnings: List[str] = []
        if not protected:
            warnings.append(
                "flashbots relay implies protected routing — 'protected=False' is ignored"
            )
        return RoutingDecision(
            router=self.router,
            kind=self.kind,
            chain=chain,
            target=self._relay_url,
            deadline_blocks=self._deadline,
            fallback_router="public_rpc",
            private=True,
            protects_against=["sandwich", "frontrun"],
            warnings=warnings,
            would_broadcast=False,
            method="shadow_route_only",
            generated_at=_now_iso(),
        )


# ---------------------------------------------------------------------------
# MevRouterRegistry
# ---------------------------------------------------------------------------

_DEFAULT_ROUTERS: Dict[str, MevRouterBackend] = {
    "public_rpc":         PublicRpcRouter(),
    "flashbots_protect":  FlashbotsRouter(),
}


class MevRouterRegistry:
    def __init__(self, routers: Optional[Dict[str, MevRouterBackend]] = None,
                 default: str = "public_rpc"):
        self._routers: Dict[str, MevRouterBackend] = dict(routers or _DEFAULT_ROUTERS)
        if default not in self._routers:
            raise ValueError(f"unknown default router '{default}'")
        self._default = default

    def register(self, router: MevRouterBackend) -> None:
        self._routers[router.router] = router

    def get(self, router: str) -> MevRouterBackend:
        try:
            return self._routers[router]
        except KeyError:
            raise ValueError(
                f"unknown MEV router '{router}'; available: {sorted(self._routers.keys())}"
            )

    def catalog(self) -> Dict[str, Any]:
        return {
            "default_router": self._default,
            "routers": [
                {
                    "router": r.router,
                    "kind": r.kind,
                    "available": r.is_available(),
                    "supports_chains": list(getattr(r, "supports_chains", ())),
                }
                for r in self._routers.values()
            ],
            "would_broadcast": False,  # invariant surfaced in catalog too
        }

    @property
    def default(self) -> str:
        return self._default

    async def route(self, *, router: Optional[str] = None,
                    chain: str, protected: bool = True) -> RoutingDecision:
        name = router or self._default
        backend = self.get(name)
        if not backend.supports(chain):
            # Fall back to default if the chosen router doesn't cover this chain.
            if name != self._default:
                logger.info("router '%s' does not support chain '%s'; falling back to '%s'",
                            name, chain, self._default)
                backend = self.get(self._default)
        decision = await backend.route(chain=chain, protected=protected)
        # Broadcast invariant — asserted twice defensively.
        assert decision.would_broadcast is False
        return decision
