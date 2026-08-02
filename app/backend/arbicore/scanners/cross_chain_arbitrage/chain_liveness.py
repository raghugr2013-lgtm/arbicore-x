"""ChainLivenessRegistry — per-chain finality / congestion / gas snapshot.

Lightweight runtime substrate consumed by:
  - ``CrossChainGate8ChainLiveness`` (gate input)
  - ``CrossChainOpportunityVerifier`` (category_metadata projection)
  - ``MevRiskScorer`` (congestion is one of two MEV inputs)

The registry is a pure in-memory snapshot store. The orchestrator
refreshes it via an operator-injectable ``liveness_loader`` callable;
the default loader (`_noop_liveness_loader`) returns the conservative
CALM defaults shipped in ``scanner_config.cross_chain_arb.chains``.

INV-1: This module never constructs ``CanonicalOpportunity``.
INV-2: This module never calls ``EmissionBus``.
INV-3: This module never asserts provenance; it is read-only intel.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Operator-tunable defaults — used when no live snapshot exists for a chain.
_DEFAULT_CONGESTION_SCORE = 30.0     # 0..100; <50 = CALM
_DEFAULT_FINALITY_S = {
    "ethereum": 768.0,   # ~64 blocks × 12s
    "arbitrum": 5.0,
    "base":     5.0,
    "optimism": 5.0,
    "polygon":  256.0,   # 128 blocks × 2s
    "solana":   12.8,    # ~32 slots × 400ms
}


@dataclass
class ChainLivenessSnapshot:
    """One chain's live state. Pure value object."""
    chain: str
    finality_s: float
    congestion_score: float   # 0..100
    gas_token: str
    gas_estimate_usd: Optional[float] = None
    ok: bool = True
    last_error: Optional[str] = None
    snapshot_at_ts: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain": self.chain,
            "finality_s": self.finality_s,
            "congestion_score": self.congestion_score,
            "gas_token": self.gas_token,
            "gas_estimate_usd": self.gas_estimate_usd,
            "ok": self.ok,
            "last_error": self.last_error,
            "snapshot_at_ts": self.snapshot_at_ts,
        }


# Loader signature: () -> dict[chain_name, snapshot_dict_or_ChainLivenessSnapshot]
LivenessLoader = Callable[[], Awaitable[Dict[str, Any]]]


async def _noop_liveness_loader() -> Dict[str, Any]:
    """Default loader — returns empty dict so the registry falls back to
    config-derived CALM defaults for every chain it's asked about."""
    return {}


class ChainLivenessRegistry:
    """In-memory snapshot store + read-through default fallback."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], Dict[str, Any]],
        liveness_loader: Optional[LivenessLoader] = None,
    ) -> None:
        self._config_loader = config_loader
        self._loader: LivenessLoader = liveness_loader or _noop_liveness_loader
        self._snapshots: Dict[str, ChainLivenessSnapshot] = {}
        self._last_refresh_ts: Optional[float] = None
        self._last_error: Optional[str] = None

    @property
    def last_refresh_ts(self) -> Optional[float]:
        return self._last_refresh_ts

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def set_loader(self, loader: LivenessLoader) -> None:
        """Operator hook — replace the default loader at runtime."""
        self._loader = loader

    async def refresh(self) -> Dict[str, ChainLivenessSnapshot]:
        """Refresh all in-scope chain snapshots from the loader."""
        try:
            payload = await self._loader()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            return dict(self._snapshots)
        self._last_error = None
        now = time.time()
        for chain, snap in (payload or {}).items():
            if isinstance(snap, ChainLivenessSnapshot):
                self._snapshots[chain] = snap
                continue
            if not isinstance(snap, dict):
                continue
            cfg_chain = self._chain_cfg(chain)
            self._snapshots[chain] = ChainLivenessSnapshot(
                chain=chain,
                finality_s=float(snap.get(
                    "finality_s", _DEFAULT_FINALITY_S.get(chain, 60.0))),
                congestion_score=float(snap.get(
                    "congestion_score", _DEFAULT_CONGESTION_SCORE)),
                gas_token=str(snap.get("gas_token",
                                          cfg_chain.get("gas_token", "ETH"))),
                gas_estimate_usd=(float(snap["gas_estimate_usd"])
                                    if "gas_estimate_usd" in snap and snap["gas_estimate_usd"] is not None
                                    else None),
                ok=bool(snap.get("ok", True)),
                last_error=snap.get("last_error"),
                snapshot_at_ts=float(snap.get("snapshot_at_ts", now)),
            )
        self._last_refresh_ts = now
        return dict(self._snapshots)

    def get(self, chain: str) -> ChainLivenessSnapshot:
        """Read a snapshot — falls back to a CALM default when missing."""
        chain = (chain or "").lower()
        snap = self._snapshots.get(chain)
        if snap is not None:
            return snap
        return self._default_for(chain)

    def all_snapshots(self) -> Dict[str, ChainLivenessSnapshot]:
        # Materialise defaults for every in-scope chain so health surfaces
        # are deterministic regardless of refresh state.
        out: Dict[str, ChainLivenessSnapshot] = {}
        for chain in self._known_chains():
            out[chain] = self.get(chain)
        return out

    # ---- helpers ----------------------------------------------------------

    def _chain_cfg(self, chain: str) -> Dict[str, Any]:
        cfg = self._config_loader() or {}
        return (cfg.get("chains") or {}).get(chain) or {}

    def _known_chains(self) -> Any:
        cfg = self._config_loader() or {}
        return sorted((cfg.get("chains") or {}).keys())

    def _default_for(self, chain: str) -> ChainLivenessSnapshot:
        cfg_chain = self._chain_cfg(chain)
        return ChainLivenessSnapshot(
            chain=chain,
            finality_s=float(_DEFAULT_FINALITY_S.get(chain, 60.0)),
            congestion_score=_DEFAULT_CONGESTION_SCORE,
            gas_token=str(cfg_chain.get("gas_token", "ETH")),
            gas_estimate_usd=None,
            ok=True,
            last_error=None,
        )



# ============================================================================
# RpcChainLivenessLoader — D-5.2 completion (absorbed into existing module)
# ============================================================================

# EVM JSON-RPC pulls: blockNumber + gasPrice. Solana JSON-RPC pulls:
# getSlot + getRecentPrioritizationFees. All via the shared http_retry
# substrate — zero new HTTP infra. Operator-graduated by setting the
# per-chain RPC URL env var (e.g. ETH_RPC_URL, SOLANA_RPC_URL).

_GAS_BASELINE_WEI = {
    "ethereum": 25_000_000_000,
    "arbitrum":     100_000_000,
    "base":         100_000_000,
    "optimism":     100_000_000,
    "polygon":  35_000_000_000,
}
_GAS_HOT_WEI = {
    "ethereum": 100_000_000_000,
    "arbitrum": 1_000_000_000,
    "base":     1_000_000_000,
    "optimism": 1_000_000_000,
    "polygon":  300_000_000_000,
}
_SOLANA_PRIO_FEE_BASELINE = 1000
_SOLANA_PRIO_FEE_HOT = 100_000


class RpcChainLivenessLoader:
    """Operator-attached liveness loader that probes each in-scope chain
    via its JSON-RPC endpoint. Reuses the universal ``http_retry``
    substrate for retry / backoff / timeout; no new HTTP layer.

    INV-1/2/3: read-only intelligence. Never builds canonicals, never
    emits, never touches provenance.
    """

    def __init__(
        self,
        *,
        config_loader: Callable[[], Dict[str, Any]],
        http_client=None,
        ttl_cache_s: float = 12.0,
        retry_config=None,
        env_resolver: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        import httpx
        from ..http_retry import RetryConfig, TTLCache, DEFAULT_TIMEOUT_S
        self._config_loader = config_loader
        self._client = http_client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT_S)
        self._owns_client = http_client is None
        self._retry = retry_config or RetryConfig()
        self._cache = TTLCache(ttl_s=ttl_cache_s)
        if env_resolver is None:
            import os as _os
            self._env = _os.environ.get
        else:
            self._env = env_resolver

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __call__(self) -> Dict[str, Any]:
        cfg = self._config_loader() or {}
        chains_cfg = (cfg.get("chains") or {})
        out: Dict[str, Any] = {}
        for chain, ccfg in chains_cfg.items():
            chain_n = chain.lower()
            rpc_env = (ccfg or {}).get("rpc_env_var")
            rpc_url = (self._env(rpc_env, "") if rpc_env else "").strip()
            if not rpc_url:
                continue
            hit, cached = self._cache.get(chain_n)
            if hit:
                out[chain_n] = cached
                continue
            try:
                if chain_n == "solana":
                    snap = await self._probe_solana(rpc_url, ccfg)
                else:
                    snap = await self._probe_evm(chain_n, rpc_url, ccfg)
            except Exception as exc:  # noqa: BLE001
                snap = {
                    "finality_s": float(_DEFAULT_FINALITY_S.get(
                        chain_n, 60.0)),
                    "congestion_score": _DEFAULT_CONGESTION_SCORE,
                    "gas_token": (ccfg or {}).get("gas_token", "ETH"),
                    "ok": False,
                    "last_error": f"{type(exc).__name__}: {exc}",
                }
            self._cache.set(chain_n, snap)
            out[chain_n] = snap
        return out

    async def _probe_evm(self, chain: str, rpc_url: str,
                          ccfg: Dict[str, Any]) -> Dict[str, Any]:
        from ..http_retry import post_json_with_retry
        gas_resp = await post_json_with_retry(
            self._client, rpc_url,
            {"jsonrpc": "2.0", "id": 1,
              "method": "eth_gasPrice", "params": []},
            config=self._retry,
        )
        gas_wei = _parse_hex(gas_resp.get("result") if gas_resp else None)
        cong = self._project_evm_congestion(chain, gas_wei)
        return {
            "finality_s": float(_DEFAULT_FINALITY_S.get(chain, 30.0)),
            "congestion_score": cong,
            "gas_token": (ccfg or {}).get("gas_token", "ETH"),
            "ok": True, "last_error": None,
            "gas_estimate_usd": None,
        }

    async def _probe_solana(self, rpc_url: str,
                              ccfg: Dict[str, Any]) -> Dict[str, Any]:
        from ..http_retry import post_json_with_retry
        resp = await post_json_with_retry(
            self._client, rpc_url,
            {"jsonrpc": "2.0", "id": 1,
              "method": "getRecentPrioritizationFees", "params": [[]]},
            config=self._retry,
        )
        fees: list = []
        if resp and isinstance(resp.get("result"), list):
            for row in resp["result"]:
                try:
                    fees.append(float(row.get("prioritizationFee", 0)))
                except (TypeError, ValueError):
                    continue
        median_fee = sorted(fees)[len(fees) // 2] if fees else 0.0
        cong = self._project_solana_congestion(median_fee)
        return {
            "finality_s": float(_DEFAULT_FINALITY_S.get("solana", 12.8)),
            "congestion_score": cong,
            "gas_token": (ccfg or {}).get("gas_token", "SOL"),
            "ok": True, "last_error": None,
        }

    @staticmethod
    def _project_evm_congestion(chain: str,
                                  gas_wei: Optional[float]) -> float:
        if gas_wei is None:
            return _DEFAULT_CONGESTION_SCORE
        base = float(_GAS_BASELINE_WEI.get(chain, 25_000_000_000))
        hot = float(_GAS_HOT_WEI.get(chain, 100_000_000_000))
        if gas_wei <= base:
            return 20.0
        if gas_wei >= hot:
            return 95.0
        return 20.0 + (gas_wei - base) / (hot - base) * 75.0

    @staticmethod
    def _project_solana_congestion(median_prio_fee: float) -> float:
        if median_prio_fee <= _SOLANA_PRIO_FEE_BASELINE:
            return 20.0
        if median_prio_fee >= _SOLANA_PRIO_FEE_HOT:
            return 95.0
        return 20.0 + (median_prio_fee - _SOLANA_PRIO_FEE_BASELINE) / \
            (_SOLANA_PRIO_FEE_HOT - _SOLANA_PRIO_FEE_BASELINE) * 75.0


def _parse_hex(s) -> Optional[float]:
    """Decode an EVM JSON-RPC hex string to float; None on bad input."""
    if not isinstance(s, str) or not s.startswith("0x"):
        return None
    try:
        return float(int(s, 16))
    except (TypeError, ValueError):
        return None
