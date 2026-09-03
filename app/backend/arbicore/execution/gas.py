"""Wave 6C · Gas Oracle abstraction.

Provider-agnostic, deterministic, and offline-friendly.

Two backends ship in this wave:

    * ``StaticGasOracle``  — deploy-time constants (default).  Emits a
      fully-populated ``GasEstimate`` with per-step and total values
      derived from a per-kind gas heuristic.  Deterministic.
    * ``RpcGasOracle``     — opt-in.  Queries ``eth_gasPrice`` /
      ``eth_feeHistory`` via a supplied HTTP RPC endpoint.  Only
      reads chain state; never broadcasts.  On any error it falls
      back to the ``StaticGasOracle`` so the pipeline never blocks
      on RPC availability.

Both backends return a ``GasEstimate`` value object.  The estimate is
attached to the plan's ``economics`` block by ``DryRunEngine``.  No new
dependencies — HTTP is done through ``httpx`` (already in
``requirements.txt``).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger("arbicore.execution.gas")


# ---------------------------------------------------------------------------
# Per-step gas heuristics (units of gas at pre-EIP-1559 pricing scheme)
# ---------------------------------------------------------------------------

DEFAULT_GAS_UNITS: Dict[str, int] = {
    # Rough EVM heuristics — deliberately conservative.
    "borrow":  180_000,   # flash loan entry
    "swap":    150_000,   # per hop
    "repay":    80_000,   # flash repay leg
    "profit":   21_000,   # settlement / event
}


@dataclass(frozen=True)
class GasEstimate:
    """Deterministic gas estimate for an execution plan."""
    provider: str
    gas_price_wei: int
    max_fee_per_gas_wei: int
    max_priority_fee_wei: int
    total_gas_units: int
    total_cost_wei: int
    total_cost_native: float
    total_cost_usd: Optional[float]
    per_step_gas_units: List[int]
    per_step_cost_wei: List[int]
    native_price_usd: Optional[float]
    method: str            # "static" | "rpc_gas_price" | "rpc_fee_history"
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class GasOracleBackend(Protocol):
    provider: str

    def is_available(self) -> bool: ...

    async def estimate(self, *, chain: str,
                       step_kinds: List[str],
                       native_price_usd: Optional[float] = None
                       ) -> GasEstimate: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sum_gas_units(step_kinds: List[str],
                   overrides: Optional[Dict[str, int]] = None
                   ) -> tuple:
    units_map = dict(DEFAULT_GAS_UNITS)
    if overrides:
        units_map.update(overrides)
    per_step = [int(units_map.get(k, 100_000)) for k in step_kinds]
    return per_step, sum(per_step)


# ---------------------------------------------------------------------------
# StaticGasOracle — offline default
# ---------------------------------------------------------------------------

class StaticGasOracle:
    """Deterministic gas oracle using deploy-time constants.

    Configuration is read from environment (fail-safe defaults kept
    conservative to prevent underestimation):

        ARBICORE_GAS_PRICE_GWEI   — legacy gas price (default 0.05 on Base)
        ARBICORE_MAX_FEE_GWEI     — EIP-1559 max fee cap (default = gas_price)
        ARBICORE_PRIO_FEE_GWEI    — priority tip (default 0.01)
    """
    provider = "static_gas_oracle"

    def __init__(self, *,
                 default_gwei: float = 0.05,
                 priority_gwei: float = 0.01,
                 native_price_usd: Optional[float] = 2500.0):
        env_gwei = os.environ.get("ARBICORE_GAS_PRICE_GWEI")
        env_prio = os.environ.get("ARBICORE_PRIO_FEE_GWEI")
        env_max  = os.environ.get("ARBICORE_MAX_FEE_GWEI")
        env_ntv  = os.environ.get("ARBICORE_NATIVE_PRICE_USD")
        self._gas_gwei = float(env_gwei if env_gwei is not None else default_gwei)
        self._prio_gwei = float(env_prio if env_prio is not None else priority_gwei)
        self._max_fee_gwei = float(env_max if env_max is not None else self._gas_gwei)
        self._native_price_usd = (float(env_ntv) if env_ntv else native_price_usd)

    def is_available(self) -> bool:
        return True

    async def estimate(self, *, chain: str,
                       step_kinds: List[str],
                       native_price_usd: Optional[float] = None
                       ) -> GasEstimate:
        native_price = native_price_usd if native_price_usd is not None else self._native_price_usd
        gas_price_wei = int(self._gas_gwei * 1e9)
        prio_wei = int(self._prio_gwei * 1e9)
        max_fee_wei = max(int(self._max_fee_gwei * 1e9), gas_price_wei)
        per_step, total_units = _sum_gas_units(step_kinds)
        per_step_cost = [u * gas_price_wei for u in per_step]
        total_cost = sum(per_step_cost)
        native_cost = total_cost / 1e18
        usd_cost = (round(native_cost * native_price, 6)
                    if native_price is not None else None)
        return GasEstimate(
            provider=self.provider,
            gas_price_wei=gas_price_wei,
            max_fee_per_gas_wei=max_fee_wei,
            max_priority_fee_wei=prio_wei,
            total_gas_units=total_units,
            total_cost_wei=total_cost,
            total_cost_native=native_cost,
            total_cost_usd=usd_cost,
            per_step_gas_units=per_step,
            per_step_cost_wei=per_step_cost,
            native_price_usd=native_price,
            method="static",
            generated_at=_now_iso(),
        )


# ---------------------------------------------------------------------------
# RpcGasOracle — opt-in, read-only
# ---------------------------------------------------------------------------

class RpcGasOracle:
    """Reads live gas price via JSON-RPC ``eth_gasPrice`` (and
    optionally ``eth_maxPriorityFeePerGas`` when the endpoint exposes
    it).  Falls back to ``StaticGasOracle`` on any error — the caller
    never observes an outage.

    NEVER broadcasts.  Only calls read-only RPC methods.
    """
    provider = "rpc_gas_oracle"
    _READ_ONLY_METHODS: frozenset = frozenset({
        "eth_gasPrice", "eth_maxPriorityFeePerGas", "eth_feeHistory",
    })

    def __init__(self, *,
                 rpc_url: Optional[str] = None,
                 timeout_s: float = 5.0,
                 fallback: Optional[GasOracleBackend] = None,
                 native_price_usd: Optional[float] = None):
        # Phase 10.10.8 · lazy RPC URL resolution.  Storing the URL at
        # construction time captured the value BEFORE the Phase 10.10
        # ``env_sync`` startup hook exported it, so the oracle always
        # fell through to the static fallback.  We now resolve
        # ``ARBICORE_RPC_URL`` on every call (cheap dict lookup).
        self._explicit_rpc_url = rpc_url
        self._timeout = float(timeout_s)
        self._fallback = fallback or StaticGasOracle()
        # Native price default mirrors StaticGasOracle (see class docstring).
        env_ntv = os.environ.get("ARBICORE_NATIVE_PRICE_USD")
        self._native_price_usd = (
            native_price_usd if native_price_usd is not None
            else (float(env_ntv) if env_ntv else 2500.0)
        )

    @property
    def _rpc_url(self) -> Optional[str]:
        from ..config.persistent import first_rpc_endpoint
        return self._explicit_rpc_url or first_rpc_endpoint(os.environ.get("ARBICORE_RPC_URL"))

    def is_available(self) -> bool:
        return bool(self._rpc_url)

    async def _rpc(self, method: str, params: Optional[List[Any]] = None) -> Any:
        assert method in self._READ_ONLY_METHODS, (
            f"RpcGasOracle refused non-read-only method '{method}'"
        )
        import httpx  # local import — avoid httpx cost when disabled
        payload = {"jsonrpc": "2.0", "id": 1, "method": method,
                   "params": list(params or [])}
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.post(self._rpc_url, json=payload)
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                raise RuntimeError(f"rpc error: {body['error']}")
            return body.get("result")

    async def estimate(self, *, chain: str,
                       step_kinds: List[str],
                       native_price_usd: Optional[float] = None
                       ) -> GasEstimate:
        if not self.is_available():
            return await self._fallback.estimate(
                chain=chain, step_kinds=step_kinds,
                native_price_usd=native_price_usd,
            )
        try:
            gas_hex = await self._rpc("eth_gasPrice")
            gas_price = int(gas_hex, 16) if isinstance(gas_hex, str) else int(gas_hex or 0)
            try:
                prio_hex = await self._rpc("eth_maxPriorityFeePerGas")
                prio_wei = int(prio_hex, 16) if isinstance(prio_hex, str) else int(prio_hex or 0)
            except Exception:  # noqa: BLE001
                prio_wei = 0
            per_step, total_units = _sum_gas_units(step_kinds)
            per_step_cost = [u * gas_price for u in per_step]
            total_cost = sum(per_step_cost)
            native_cost = total_cost / 1e18
            native_price = (native_price_usd if native_price_usd is not None
                            else self._native_price_usd)
            usd_cost = (round(native_cost * native_price, 6)
                        if native_price is not None else None)
            return GasEstimate(
                provider=self.provider,
                gas_price_wei=gas_price,
                max_fee_per_gas_wei=max(gas_price, prio_wei + gas_price),
                max_priority_fee_wei=prio_wei,
                total_gas_units=total_units,
                total_cost_wei=total_cost,
                total_cost_native=native_cost,
                total_cost_usd=usd_cost,
                per_step_gas_units=per_step,
                per_step_cost_wei=per_step_cost,
                native_price_usd=native_price,
                method="rpc_gas_price",
                generated_at=_now_iso(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("RpcGasOracle failed (%s) — falling back to static", exc)
            return await self._fallback.estimate(
                chain=chain, step_kinds=step_kinds,
                native_price_usd=native_price_usd,
            )
