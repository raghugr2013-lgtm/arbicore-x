"""Paper Validation — Simulation stage (v2.11.8 · Slice B).

Provides a pluggable Simulation stage for the OpportunityPipeline.  The
stage runs the executor calldata through a chosen backend and produces
a :class:`SimulationResult`.  Two backends ship in Slice B:

* :class:`EthCallSimulator` — real ``eth_call`` against
  ``BASE_RPC_URL``.  Uses the same JSON-RPC wire format as
  :mod:`arbicore.execution.quoter`.
* :class:`HeuristicSimulator` — documented offline dry-run.  Applies a
  short, explicit list of rejection rules and otherwise passes.

Future backends (Anvil, Tenderly, forge-fork) can plug in without
changing the pipeline — they only need to implement the
:class:`SimulationBackend` :class:`typing.Protocol`.

The chosen backend is recorded on the immutable :class:`EvidenceBundle`
as ``simulation_backend`` so every validation is traceable to the exact
oracle that produced its verdict.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Backend interface + result shape                                            #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SimulationResult:
    """Return value of :meth:`SimulationBackend.simulate`.

    ``ok`` is the terminal verdict for the Simulate stage.  When
    ``ok=False`` the pipeline classifier maps the failure to
    :data:`arbicore.paper.PaperOutcome.SIMULATION_FAILURE`.

    ``backend`` is the short name of the backend that produced the
    verdict — one of ``"eth_call"``, ``"heuristic"``, ``"anvil"``,
    ``"tenderly"``, …
    """

    ok: bool
    backend: str
    detail: str = ""
    revert_selector: Optional[str] = None
    revert_reason: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_stage_payload(self) -> Dict[str, Any]:
        return {
            "backend":         self.backend,
            "revert_selector": self.revert_selector,
            "revert_reason":   self.revert_reason,
            **self.payload,
        }


@runtime_checkable
class SimulationBackend(Protocol):
    """Provider surface for a Simulation backend.

    Implementations are expected to be stateless (or thread-safe) — the
    pipeline calls ``simulate`` once per opportunity.
    """

    name: str

    async def simulate(
        self, *,
        chain: str,
        to: str,
        data: str,
        from_: str,
        value: int = 0,
    ) -> SimulationResult: ...


# --------------------------------------------------------------------------- #
# Backend 1 — real RPC eth_call                                               #
# --------------------------------------------------------------------------- #

class EthCallSimulator:
    """Real RPC ``eth_call`` backend.

    Requires an RPC URL for the target chain.  On revert, extracts the
    4-byte selector from the returned revert data so the operator can
    map it against ``arbicore.execution.broadcast._REVERT_SELECTORS``.
    """

    name = "eth_call"

    def __init__(self, rpc_urls_by_chain: Dict[str, str]) -> None:
        self._rpc = dict(rpc_urls_by_chain or {})

    def supports(self, chain: str) -> bool:
        return bool(self._rpc.get(chain))

    async def simulate(self, *,
                        chain: str,
                        to: str,
                        data: str,
                        from_: str,
                        value: int = 0) -> SimulationResult:
        rpc = self._rpc.get(chain)
        if not rpc:
            return SimulationResult(
                ok=False, backend=self.name,
                detail=f"no RPC configured for chain '{chain}'",
                revert_reason=f"no RPC configured for chain '{chain}'",
            )
        try:
            import httpx
        except Exception as exc:  # pragma: no cover — httpx is a hard dep
            return SimulationResult(
                ok=False, backend=self.name,
                detail=f"httpx unavailable: {exc}",
                revert_reason=str(exc),
            )
        params = {"to": to, "data": data, "from": from_}
        if value:
            params["value"] = hex(int(value))
        payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                    "params": [params, "latest"]}
        try:
            async with httpx.AsyncClient(timeout=12.0) as c:
                resp = await c.post(rpc, json=payload)
                resp.raise_for_status()
                body = resp.json()
        except Exception as exc:  # noqa: BLE001
            return SimulationResult(
                ok=False, backend=self.name,
                detail=f"RPC transport error: {exc}",
                revert_reason=f"RPC transport error: {exc}",
            )
        if isinstance(body, dict) and "error" in body:
            err = body["error"] or {}
            revert_data = str((err.get("data") or "")).lower()
            selector = revert_data[:10] if revert_data.startswith("0x") \
                        and len(revert_data) >= 10 else None
            return SimulationResult(
                ok=False, backend=self.name,
                detail=f"eth_call reverted: {err.get('message', '(no msg)')}",
                revert_selector=selector,
                revert_reason=err.get("message"),
                payload={"raw_data": revert_data or None},
            )
        return SimulationResult(
            ok=True, backend=self.name, detail="eth_call succeeded",
            payload={"return_data": (body or {}).get("result")},
        )


# --------------------------------------------------------------------------- #
# Backend 2 — documented heuristic                                            #
# --------------------------------------------------------------------------- #

class HeuristicSimulator:
    """Documented offline dry-run.

    Applies a short list of explicit rejection rules — anything not
    caught by a rule passes.  The Framework logs the rule set on the
    evidence bundle so every heuristic verdict is fully explainable.

    Rules (in order):
        1. ``data`` must be a 0x-prefixed hex string of length >= 10
           (a 4-byte selector + at least one arg word).
        2. ``to`` must be a non-zero 0x-prefixed 20-byte address.
        3. If the calldata's selector matches a well-known revert-only
           signature (e.g. Solidity ``Panic`` / ``Error``), reject.
    """

    name = "heuristic"

    _KNOWN_REVERT_SELECTORS = {
        "0x08c379a0",   # Error(string)
        "0x4e487b71",   # Panic(uint256)
    }

    async def simulate(self, *,
                        chain: str,
                        to: str,
                        data: str,
                        from_: str,
                        value: int = 0) -> SimulationResult:
        detail_parts = []
        # Rule 1: calldata sanity
        if not (isinstance(data, str) and data.startswith("0x") and len(data) >= 10):
            return SimulationResult(
                ok=False, backend=self.name,
                detail="calldata missing / too short for a selector",
                revert_reason="calldata missing / too short",
            )
        # Rule 2: destination sanity
        if not (isinstance(to, str) and to.startswith("0x")
                and len(to) == 42 and int(to, 16) != 0):
            return SimulationResult(
                ok=False, backend=self.name,
                detail="destination address invalid or zero",
                revert_reason="invalid `to` address",
            )
        # Rule 3: revert-only selector guard
        sel = data[:10].lower()
        if sel in self._KNOWN_REVERT_SELECTORS:
            return SimulationResult(
                ok=False, backend=self.name,
                detail=f"calldata selector {sel} is a revert-only signature",
                revert_selector=sel,
                revert_reason="revert-only selector",
            )
        detail_parts.append(f"selector={sel}")
        return SimulationResult(
            ok=True, backend=self.name,
            detail="; ".join(detail_parts) or "heuristic pass",
        )


# --------------------------------------------------------------------------- #
# Router — pick the right backend based on env                                 #
# --------------------------------------------------------------------------- #

class SimulationRouter:
    """Facade over the backend registry.

    Picks the real ``eth_call`` backend when an RPC URL is configured
    for the opportunity's chain; otherwise falls back to
    :class:`HeuristicSimulator`.  The chosen backend name is captured
    on the resulting :class:`SimulationResult` so callers can persist
    it verbatim into ``EvidenceBundle.simulation_backend``.
    """

    def __init__(self,
                 *,
                 eth_call: Optional[EthCallSimulator] = None,
                 heuristic: Optional[HeuristicSimulator] = None) -> None:
        self._eth_call  = eth_call
        self._heuristic = heuristic or HeuristicSimulator()

    @classmethod
    def from_env(cls) -> "SimulationRouter":
        """Build the router from environment variables.

        Recognised chain → env-var mapping::

            base           BASE_RPC_URL
            base_sepolia   BASE_SEPOLIA_RPC_URL
        """
        rpcs: Dict[str, str] = {}
        for chain, key in (
            ("base",         "BASE_RPC_URL"),
            ("base_sepolia", "BASE_SEPOLIA_RPC_URL"),
        ):
            url = (os.environ.get(key) or "").strip()
            if url:
                rpcs[chain] = url
        eth = EthCallSimulator(rpcs) if rpcs else None
        return cls(eth_call=eth)

    async def simulate(self, *,
                        chain: str,
                        to: str,
                        data: str,
                        from_: str,
                        value: int = 0) -> SimulationResult:
        # Prefer real eth_call when the RPC is wired for this chain.
        if self._eth_call and self._eth_call.supports(chain):
            return await self._eth_call.simulate(
                chain=chain, to=to, data=data, from_=from_, value=value
            )
        return await self._heuristic.simulate(
            chain=chain, to=to, data=data, from_=from_, value=value
        )
