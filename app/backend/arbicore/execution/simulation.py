"""Wave 6C · On-chain Simulation Backend.

Two backends ship in this wave.  Both are strictly READ-ONLY —
neither broadcasts a transaction under any circumstances.

    * ``NoopSimulator``    — default; deterministic + offline.  Produces
      a positive ``SimulationResult`` derived purely from plan economics
      (no chain contact).
    * ``EthCallSimulator``  — opt-in.  Given an operator-supplied HTTP
      RPC endpoint, calls ``eth_call`` / ``eth_estimateGas`` for each
      execution step.  Never calls a non-read-only RPC method.  On any
      error it degrades gracefully to a ``NoopSimulator`` result with
      the error captured under ``fallback_reason`` — the pipeline
      never blocks on RPC availability.

Every backend returns a ``SimulationResult`` value object.  The result
is attached to the plan's ``economics`` block by ``DryRunEngine`` so
downstream evidence, calibration, and adaptive-weights all consume
the same substrate.

Invariants (asserted at value-object construction + registry level):

    1. ``would_broadcast`` is *always* ``False``.
    2. ``rpc_methods_called`` is a subset of the read-only allowlist.
    3. No private key material or signed transaction bytes ever appear
       in a ``SimulationResult`` — the value object exposes step-level
       success/failure and estimated gas only.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger("arbicore.execution.simulation")


READ_ONLY_RPC_METHODS: frozenset = frozenset({
    "eth_call",
    "eth_estimateGas",
    "eth_chainId",
    "eth_blockNumber",
    "eth_getBalance",
    "eth_getCode",
    "eth_getTransactionCount",
    "eth_getStorageAt",
    "eth_gasPrice",
    "eth_maxPriorityFeePerGas",
    "eth_feeHistory",
})

# Explicit denylist — belt-and-braces guard.  If any of these ever appear
# in the caller queue the simulator refuses the request outright.
FORBIDDEN_RPC_METHODS: frozenset = frozenset({
    "eth_sendTransaction",
    "eth_sendRawTransaction",
    "eth_signTransaction",
    "eth_sign",
    "personal_sign",
    "personal_sendTransaction",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Step + Plan simulation value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StepSimulation:
    step_index: int
    kind: str
    provider: str
    ok: bool
    estimated_gas_units: Optional[int]
    revert_reason: Optional[str]
    method: str                      # "eth_call" | "eth_estimateGas" | "noop"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulationResult:
    simulator: str
    ok: bool
    chain: str
    rpc_url_redacted: Optional[str]  # never the full URL — only host:port
    rpc_methods_called: List[str]
    steps: List[StepSimulation]
    total_estimated_gas: int
    revert_reasons: List[str]
    warnings: List[str]
    would_broadcast: bool            # ALWAYS False
    fallback_reason: Optional[str]   # populated when a non-Noop simulator degraded
    method: str
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        assert d["would_broadcast"] is False, "SimulationResult leaked would_broadcast=True"
        for m in d["rpc_methods_called"]:
            assert m in READ_ONLY_RPC_METHODS, (
                f"SimulationResult leaked non-read-only method '{m}'"
            )
        return d


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class SimulatorBackend(Protocol):
    simulator: str

    def is_available(self) -> bool: ...

    async def simulate(self, plan: Dict[str, Any]) -> SimulationResult: ...


# ---------------------------------------------------------------------------
# Redaction helper
# ---------------------------------------------------------------------------

def _redact_rpc(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        # Trim path/query and keep only scheme://host:port.  API-key
        # bearing query strings never leak.
        from urllib.parse import urlparse
        p = urlparse(url)
        if not p.hostname:
            return "***"
        host = p.hostname
        port = f":{p.port}" if p.port else ""
        return f"{p.scheme}://{host}{port}"
    except Exception:  # noqa: BLE001
        return "***"


# ---------------------------------------------------------------------------
# NoopSimulator — deterministic default
# ---------------------------------------------------------------------------

class NoopSimulator:
    """Deterministic simulator: derives a positive result from the plan's
    dry-run economics.  Never touches the chain.  Always available."""
    simulator = "noop"

    def is_available(self) -> bool:
        return True

    async def simulate(self, plan: Dict[str, Any]) -> SimulationResult:
        chain = plan.get("chain") or ""
        steps: List[StepSimulation] = []
        total_gas = 0
        # Per-step deterministic gas from the same heuristic as GasOracle.
        from .gas import DEFAULT_GAS_UNITS
        for s in plan.get("steps") or []:
            g = int(DEFAULT_GAS_UNITS.get(s.get("kind") or "", 100_000))
            total_gas += g
            steps.append(StepSimulation(
                step_index=int(s.get("step_index") or 0),
                kind=s.get("kind") or "",
                provider=s.get("provider") or "",
                ok=True,
                estimated_gas_units=g,
                revert_reason=None,
                method="noop",
                warnings=[],
            ))
        return SimulationResult(
            simulator=self.simulator,
            ok=True,
            chain=chain,
            rpc_url_redacted=None,
            rpc_methods_called=[],
            steps=steps,
            total_estimated_gas=total_gas,
            revert_reasons=[],
            warnings=[],
            would_broadcast=False,
            fallback_reason=None,
            method="noop",
            generated_at=_now_iso(),
        )


# ---------------------------------------------------------------------------
# EthCallSimulator — opt-in, read-only chain contact
# ---------------------------------------------------------------------------

class EthCallSimulator:
    """Uses ``eth_estimateGas`` (and, where possible, ``eth_call``) to
    simulate each step.  Read-only.  Never broadcasts.

    Because Wave 6B/6C intentionally never encodes bytes-level calldata
    (that's Wave 6E territory once the operator ships a verified
    executor contract), this simulator makes a **best-effort** attempt:

        * It calls ``eth_chainId`` + ``eth_blockNumber`` to prove the
          RPC endpoint is alive and matches the target chain.
        * For each step it calls ``eth_estimateGas`` when a resolvable
          ``to`` + ``data`` pair is available; otherwise it records a
          symbolic estimate using ``DEFAULT_GAS_UNITS`` and marks the
          step ``method="estimate_symbolic"``.

    Any failure downgrades the entire result to a Noop-equivalent
    payload with the failure reason captured in ``fallback_reason``.
    """
    simulator = "eth_call"

    _CHAIN_IDS: Dict[str, int] = {
        "ethereum": 1, "base": 8453, "arbitrum": 42_161,
        "optimism": 10, "polygon": 137,
    }

    def __init__(self, *,
                 rpc_url: Optional[str] = None,
                 timeout_s: float = 8.0,
                 fallback: Optional[SimulatorBackend] = None):
        self._rpc_url = rpc_url or os.environ.get("ARBICORE_RPC_URL")
        self._timeout = float(timeout_s)
        self._fallback = fallback or NoopSimulator()

    def is_available(self) -> bool:
        return bool(self._rpc_url)

    async def _rpc(self, method: str, params: Optional[List[Any]] = None) -> Any:
        if method in FORBIDDEN_RPC_METHODS:
            raise PermissionError(
                f"EthCallSimulator refused broadcast-capable method '{method}'"
            )
        if method not in READ_ONLY_RPC_METHODS:
            raise PermissionError(
                f"EthCallSimulator refused non-read-only method '{method}'"
            )
        import httpx
        payload = {"jsonrpc": "2.0", "id": 1, "method": method,
                   "params": list(params or [])}
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.post(self._rpc_url, json=payload)
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                raise RuntimeError(f"rpc error: {body['error']}")
            return body.get("result")

    async def simulate(self, plan: Dict[str, Any]) -> SimulationResult:
        if not self.is_available():
            noop = await self._fallback.simulate(plan)
            # Re-emit with fallback reason preserved.
            return SimulationResult(
                simulator=self.simulator, ok=noop.ok, chain=noop.chain,
                rpc_url_redacted=None, rpc_methods_called=[],
                steps=noop.steps, total_estimated_gas=noop.total_estimated_gas,
                revert_reasons=noop.revert_reasons, warnings=noop.warnings,
                would_broadcast=False,
                fallback_reason="rpc_url not configured",
                method="fallback_noop", generated_at=_now_iso(),
            )
        chain = plan.get("chain") or ""
        rpc_calls: List[str] = []
        warnings: List[str] = []
        revert_reasons: List[str] = []
        try:
            # 1. Chain-id sanity check.
            chain_id_hex = await self._rpc("eth_chainId")
            rpc_calls.append("eth_chainId")
            observed_id = int(chain_id_hex, 16) if isinstance(chain_id_hex, str) else int(chain_id_hex)
            expected_id = self._CHAIN_IDS.get(chain)
            if expected_id and observed_id != expected_id:
                warnings.append(
                    f"chain-id mismatch — expected {expected_id} for '{chain}', "
                    f"RPC reports {observed_id}"
                )
            # 2. Alive check.
            await self._rpc("eth_blockNumber")
            rpc_calls.append("eth_blockNumber")

            # 3. Per-step gas estimate — symbolic when calldata not encoded.
            from .gas import DEFAULT_GAS_UNITS
            steps: List[StepSimulation] = []
            total_gas = 0
            for s in plan.get("steps") or []:
                kind = s.get("kind") or ""
                fallback_g = int(DEFAULT_GAS_UNITS.get(kind, 100_000))
                total_gas += fallback_g
                # Symbolic step — Wave 6B does not encode calldata, so
                # we always mark method='estimate_symbolic' at this wave.
                # A future refinement can plug in bytes-level encoding
                # and switch to real eth_estimateGas per step.
                steps.append(StepSimulation(
                    step_index=int(s.get("step_index") or 0),
                    kind=kind,
                    provider=s.get("provider") or "",
                    ok=True,
                    estimated_gas_units=fallback_g,
                    revert_reason=None,
                    method="estimate_symbolic",
                    warnings=["calldata not encoded — symbolic estimate only"],
                ))

            return SimulationResult(
                simulator=self.simulator,
                ok=True,
                chain=chain,
                rpc_url_redacted=_redact_rpc(self._rpc_url),
                rpc_methods_called=rpc_calls,
                steps=steps,
                total_estimated_gas=total_gas,
                revert_reasons=revert_reasons,
                warnings=warnings,
                would_broadcast=False,
                fallback_reason=None,
                method="eth_call_symbolic",
                generated_at=_now_iso(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("EthCallSimulator failed (%s) — degrading to Noop", exc)
            noop = await self._fallback.simulate(plan)
            return SimulationResult(
                simulator=self.simulator,
                ok=noop.ok,
                chain=noop.chain,
                rpc_url_redacted=_redact_rpc(self._rpc_url),
                rpc_methods_called=rpc_calls,
                steps=noop.steps,
                total_estimated_gas=noop.total_estimated_gas,
                revert_reasons=noop.revert_reasons,
                warnings=noop.warnings + [f"eth_call simulator degraded: {type(exc).__name__}"],
                would_broadcast=False,
                fallback_reason=f"{type(exc).__name__}: {exc}",
                method="fallback_noop",
                generated_at=_now_iso(),
            )


# ---------------------------------------------------------------------------
# SimulationRegistry — pluggable façade.
# ---------------------------------------------------------------------------

_DEFAULT_SIMULATORS: Dict[str, SimulatorBackend] = {
    "noop":     NoopSimulator(),
    "eth_call": EthCallSimulator(),
}


class SimulationRegistry:
    """Selects among available simulator backends.

    * Default simulator is chosen deterministically via the
      ``ARBICORE_SIMULATOR`` env var (falls back to ``noop`` when
      unset or unavailable).
    * ``simulate(plan)`` dispatches to the selected backend.
    """

    def __init__(self, backends: Optional[Dict[str, SimulatorBackend]] = None,
                 default: Optional[str] = None):
        self._backends: Dict[str, SimulatorBackend] = dict(backends or _DEFAULT_SIMULATORS)
        chosen = default or os.environ.get("ARBICORE_SIMULATOR") or "noop"
        if chosen not in self._backends:
            chosen = "noop"
        if chosen != "noop" and not self._backends[chosen].is_available():
            logger.info("Simulator '%s' unavailable — defaulting to 'noop'", chosen)
            chosen = "noop"
        self._default = chosen

    def register(self, backend: SimulatorBackend) -> None:
        self._backends[backend.simulator] = backend

    @property
    def default(self) -> str:
        return self._default

    def get(self, simulator: str) -> SimulatorBackend:
        try:
            return self._backends[simulator]
        except KeyError:
            raise ValueError(
                f"unknown simulator '{simulator}'; available: {sorted(self._backends.keys())}"
            )

    def status(self) -> Dict[str, Any]:
        return {
            "default_simulator": self._default,
            "backends": [
                {"simulator": b.simulator,
                 "available": b.is_available()}
                for b in self._backends.values()
            ],
            "read_only_rpc_allowlist": sorted(READ_ONLY_RPC_METHODS),
            "forbidden_rpc_denylist": sorted(FORBIDDEN_RPC_METHODS),
            "would_broadcast": False,
        }

    async def simulate(self, plan: Dict[str, Any],
                       *, simulator: Optional[str] = None
                       ) -> SimulationResult:
        name = simulator or self._default
        backend = self.get(name)
        result = await backend.simulate(plan)
        # Invariant re-checks — defensive.
        assert result.would_broadcast is False
        for m in result.rpc_methods_called:
            assert m in READ_ONLY_RPC_METHODS
        return result
