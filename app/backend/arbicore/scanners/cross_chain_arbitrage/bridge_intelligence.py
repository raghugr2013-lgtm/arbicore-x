"""Bridge route catalog + lightweight MEV risk scorer.

Both modules are runtime, in-memory substrates. No persistence, no I/O,
no learning. Consumed by ``CrossChainOpportunityVerifier`` and Gates 7/9.

BridgeRouteCatalog:
  - Static per-corridor metadata: liveness_score, health_score, inventory_pct,
    inbound_latency_p50/p95, fee_curve_bps.
  - Keyed by ``(bridge, source_chain, destination_chain, asset)``.
  - Operator-tunable via ``scanner_config.cross_chain_arb.bridges`` and
    ``scanner_config.cross_chain_arb.transfer_model.corridor_overrides``.

MevRiskScorer:
  - Runtime-only — no historical warehouse, no searcher DB, no dashboard.
  - Inputs: source/destination chain congestion + bridge type + asset
    family. Outputs: ``MevRiskLevel`` enum + ``cross_chain_mev_risk_class``
    string (HUMAN-readable label).
  - Lives here so the verifier can compose it without depending on a
    heavy MEV infrastructure module.

INV-1/2/3 preserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ...models.enums import MevRiskLevel


# ============================================================================
# BridgeRouteMetadata + BridgeRouteCatalog
# ============================================================================

@dataclass
class BridgeRouteMetadata:
    """Operator-tunable per-corridor liveness + health metrics."""
    bridge: str
    source_chain: str
    destination_chain: str
    asset: str
    bridge_health_score: float        # 0..100
    bridge_liveness_score: float      # 0..100
    bridge_inventory_pct: float       # 0..100
    inbound_latency_p50_s: float
    inbound_latency_p95_s: float
    fee_curve_bps: float              # avg fee bps (informational; provider returns live)

    @property
    def corridor_id(self) -> str:
        return (f"{self.bridge}:{self.source_chain}→{self.destination_chain}"
                f":{self.asset}")

    @property
    def route_id(self) -> str:
        return self.corridor_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bridge": self.bridge,
            "source_chain": self.source_chain,
            "destination_chain": self.destination_chain,
            "asset": self.asset,
            "corridor_id": self.corridor_id,
            "bridge_health_score": self.bridge_health_score,
            "bridge_liveness_score": self.bridge_liveness_score,
            "bridge_inventory_pct": self.bridge_inventory_pct,
            "inbound_latency_p50_s": self.inbound_latency_p50_s,
            "inbound_latency_p95_s": self.inbound_latency_p95_s,
            "fee_curve_bps": self.fee_curve_bps,
        }


# Conservative defaults; operator may override per-corridor via the scanner
# config. Numbers reflect typical 2026 LI.FI / Stargate observability.
_BRIDGE_DEFAULTS: Dict[str, Dict[str, float]] = {
    "lifi": {
        "bridge_health_score":   85.0,
        "bridge_liveness_score": 90.0,
        "bridge_inventory_pct":  80.0,
        "inbound_latency_p50_s": 180.0,
        "inbound_latency_p95_s": 900.0,
        "fee_curve_bps":         25.0,
    },
    "stargate": {
        "bridge_health_score":   90.0,
        "bridge_liveness_score": 92.0,
        "bridge_inventory_pct":  85.0,
        "inbound_latency_p50_s":  60.0,
        "inbound_latency_p95_s": 420.0,
        "fee_curve_bps":         10.0,
    },
}


class BridgeRouteCatalog:
    """In-memory corridor metadata store with config-derived defaults."""

    def __init__(self, *, config_loader) -> None:
        self._config_loader = config_loader
        self._overrides: Dict[str, BridgeRouteMetadata] = {}
        # Pre-load any operator-supplied overrides on construction.
        self.refresh_overrides()

    # ---- public API -------------------------------------------------------

    def refresh_overrides(self) -> int:
        """Re-read scanner_config.cross_chain_arb.transfer_model.
        corridor_overrides into the in-memory map.
        """
        cfg = self._config_loader() or {}
        tm = (cfg.get("transfer_model") or {})
        ovr = (tm.get("corridor_overrides") or {})
        self._overrides.clear()
        for cid, payload in ovr.items():
            try:
                bridge, route = cid.split(":", 1)
                src, rest = route.split("→", 1)
                dst, asset = rest.split(":", 1)
            except ValueError:
                continue
            d = _BRIDGE_DEFAULTS.get(bridge, {})
            self._overrides[cid] = BridgeRouteMetadata(
                bridge=bridge,
                source_chain=src,
                destination_chain=dst,
                asset=asset,
                bridge_health_score=float(payload.get(
                    "bridge_health_score", d.get("bridge_health_score", 80))),
                bridge_liveness_score=float(payload.get(
                    "bridge_liveness_score", d.get("bridge_liveness_score", 80))),
                bridge_inventory_pct=float(payload.get(
                    "bridge_inventory_pct", d.get("bridge_inventory_pct", 80))),
                inbound_latency_p50_s=float(payload.get(
                    "inbound_latency_p50_s", d.get("inbound_latency_p50_s", 200))),
                inbound_latency_p95_s=float(payload.get(
                    "inbound_latency_p95_s", d.get("inbound_latency_p95_s", 900))),
                fee_curve_bps=float(payload.get(
                    "fee_curve_bps", d.get("fee_curve_bps", 25))),
            )
        return len(self._overrides)

    def get(self, *, bridge: str, source_chain: str,
            destination_chain: str, asset: str,
            ) -> BridgeRouteMetadata:
        bridge_n = (bridge or "").lower()
        cid = f"{bridge_n}:{source_chain}→{destination_chain}:{asset}"
        if cid in self._overrides:
            return self._overrides[cid]
        d = _BRIDGE_DEFAULTS.get(bridge_n)
        if d is None:
            # Unknown bridge → conservative fail-low defaults so Gate 7 trips.
            return BridgeRouteMetadata(
                bridge=bridge_n, source_chain=source_chain,
                destination_chain=destination_chain, asset=asset,
                bridge_health_score=0.0, bridge_liveness_score=0.0,
                bridge_inventory_pct=0.0,
                inbound_latency_p50_s=99999.0,
                inbound_latency_p95_s=99999.0,
                fee_curve_bps=100.0,
            )
        return BridgeRouteMetadata(
            bridge=bridge_n, source_chain=source_chain,
            destination_chain=destination_chain, asset=asset,
            bridge_health_score=d["bridge_health_score"],
            bridge_liveness_score=d["bridge_liveness_score"],
            bridge_inventory_pct=d["bridge_inventory_pct"],
            inbound_latency_p50_s=d["inbound_latency_p50_s"],
            inbound_latency_p95_s=d["inbound_latency_p95_s"],
            fee_curve_bps=d["fee_curve_bps"],
        )

    def known_corridors(self) -> int:
        """Count of in-memory override corridors (operator-supplied)."""
        return len(self._overrides)


# ============================================================================
# MevRiskScorer — lightweight runtime classifier
# ============================================================================

class MevRiskScorer:
    """Runtime MEV risk classifier.

    Inputs are evidence-only — chain congestion + bridge type + asset
    family. No history, no warehouse, no searcher DB. The scorer is
    intentionally minimal: it produces a ``MevRiskLevel`` (LOW/MEDIUM/
    HIGH) and a HUMAN-readable label suitable for the
    ``cross_chain_mev_risk_class`` category_metadata key.

    Future MEV signals (route safety scoring, chain congestion intel)
    will plug in here as additional inputs; the scorer remains a single
    consumer-side concern shared across D-3/D-5/D-6.
    """

    # Asset families that historically attract more MEV attention.
    _HOT_ASSETS = frozenset({"WETH", "ETH", "WBTC", "BTC", "USDC", "USDT"})

    def classify(self,
                  *,
                  bridge: Optional[str] = None,
                  source_chain_congestion: float,
                  destination_chain_congestion: float,
                  asset: str,
                  notional_usd: float,
                  is_atomic: bool = False,
                  ) -> Dict[str, Any]:
        bridge_n = (bridge or "").lower()
        asset_n = (asset or "").upper()
        # Base score: average congestion (0..100)
        base = 0.5 * float(source_chain_congestion) + \
            0.5 * float(destination_chain_congestion)
        # Adjustments
        if bridge_n == "stargate":
            # Native bridge — deterministic delivery reduces front-run risk.
            base -= 5.0
        elif bridge_n == "lifi":
            # Aggregator may pick volatile routes — neutral baseline.
            base += 2.0
        # D-6.0 — atomic flash-loan tx has no settlement risk (entire
        # trade succeeds or reverts) but elevated sandwich exposure on
        # the executing chain. Net: small positive risk delta.
        if is_atomic:
            base += 8.0
        if asset_n in self._HOT_ASSETS:
            base += 5.0
        if notional_usd >= 10_000:
            base += 5.0
        if notional_usd >= 100_000:
            base += 5.0
        base = max(0.0, min(100.0, base))
        if base >= 70.0:
            level = MevRiskLevel.HIGH
            label = "HIGH"
        elif base >= 40.0:
            level = MevRiskLevel.MEDIUM
            label = "MEDIUM"
        else:
            level = MevRiskLevel.LOW
            label = "LOW"
        bridge_label = bridge_n or ("atomic_flashloan" if is_atomic else "")
        return {
            "level": level,
            "label": label,
            "score": round(base, 1),
            "bridge": bridge_label,
            "asset": asset_n,
            "notional_usd": float(notional_usd),
            "is_atomic": bool(is_atomic),
        }
