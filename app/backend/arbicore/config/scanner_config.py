"""Phase 10.4 · Scanner Configuration Activation.

Multi-family configuration surface built on top of the Phase 10.1
:class:`ConfigRepo` substrate.  The default schemas are **activated**
from the dormant canonical
``arbicore/data/scanner_config_repo.py`` (v1.0.2 bundle), imported here
as :mod:`arbicore.data.scanner_config_defaults`.

Layout under the shared ``arbicore_config`` collection:

* ``scanner`` — global (cross-family) controls.
* ``scanner.flash_loan_arb`` — Flash Loan family.
* ``scanner.cex_arb``        — CEX arbitrage family.
* ``scanner.dex_arb``        — DEX arbitrage family.
* ``scanner.cross_chain_arb``— Cross-chain arbitrage family.
* ``scanner.funding_arb``    — Funding arbitrage family.
* ``scanner.launch_arb``     — Launch arbitrage family.

Each of these seven kinds inherits Draft / Apply / Rollback / Audit for
free — **no new configuration framework introduced.**
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .persistent import ConfigRepo, SUPPORTED_CHAINS
from ..data.scanner_config_defaults import (
    CANONICAL_FAMILIES, FAMILY_DEFAULTS, FAMILY_LABELS,
)


SCANNER_GLOBAL_KIND = "scanner"

# The set of DEX / market families the operator can toggle on/off inside
# a family that supports on-chain DEX routing (dex_arb, flash_loan_arb).
MARKET_FAMILIES = (
    "uniswap_v2", "uniswap_v3", "aerodrome",
    "sushi", "pancake", "curve", "balancer_v2",
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kind_for_family(family_id: str) -> str:
    if family_id not in CANONICAL_FAMILIES:
        raise ValueError(
            f"unknown scanner family '{family_id}'; "
            f"supported: {list(CANONICAL_FAMILIES)}"
        )
    return f"{SCANNER_GLOBAL_KIND}.{family_id}"


# ---------------------------------------------------------------------------
# Global defaults — cross-family controls
# ---------------------------------------------------------------------------

DEFAULT_SCANNER_GLOBAL: Dict[str, Any] = {
    "enabled": True,
    "paused": False,
    "worker_concurrency": 4,
    "max_concurrent_scans": 4,
    "opportunity_cache_s": 30,
    "opportunity_expiry_s": 300,
    # Per-chain scanner health / limits.
    "networks": {
        c: {
            "enabled": (c == "base"),
            "rpc_priority": 0,
            "max_gas_gwei": 30 if c == "ethereum" else 0.1,
            "max_latency_ms": 1500,
        }
        for c in SUPPORTED_CHAINS
    },
    # Token / pair families — shared across DEX-touching scanners.
    "token_families": {
        "stables":          ["USDC", "USDT", "DAI", "USDbC", "FRAX"],
        "eth_pairs":        ["WETH", "cbETH", "stETH", "rETH"],
        "wbtc_pairs":       ["WBTC", "cbBTC"],
        "blue_chips":       ["WETH", "WBTC", "LINK", "UNI", "AAVE"],
        "custom_whitelist": [],
        "blacklist":        [],
    },
    # DEX / market family enable — read by dex_arb + flash_loan_arb.
    "market_families": {mf: True for mf in MARKET_FAMILIES if mf != "sushi" and mf != "pancake"},
    "runtime": {
        "last_reload_at": None,
        "last_reload_by": None,
    },
}
# Ensure sushi + pancake keys are present (disabled by default).
DEFAULT_SCANNER_GLOBAL["market_families"]["sushi"] = False
DEFAULT_SCANNER_GLOBAL["market_families"]["pancake"] = False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _positive_number(v) -> bool:
    return isinstance(v, (int, float)) and v > 0


def _validate_global(patch: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    if "worker_concurrency" in patch and not _positive_number(patch["worker_concurrency"]):
        errors.append("worker_concurrency must be > 0")
    if "max_concurrent_scans" in patch and not _positive_number(patch["max_concurrent_scans"]):
        errors.append("max_concurrent_scans must be > 0")
    for k in ("opportunity_cache_s", "opportunity_expiry_s"):
        v = patch.get(k)
        if v is not None and not _positive_number(v):
            errors.append(f"{k} must be > 0")
    for chain, cfg in (patch.get("networks") or {}).items():
        if chain not in SUPPORTED_CHAINS:
            errors.append(f"unsupported chain '{chain}' in networks")
            continue
        if not isinstance(cfg, dict):
            errors.append(f"networks[{chain}] must be a mapping")
            continue
        for k in ("max_gas_gwei", "max_latency_ms", "rpc_priority"):
            v = cfg.get(k)
            if v is not None and (not isinstance(v, (int, float)) or v < 0):
                errors.append(f"networks[{chain}].{k} must be a non-negative number")
        if "enabled" in cfg and not isinstance(cfg["enabled"], bool):
            errors.append(f"networks[{chain}].enabled must be bool")
    for name, enabled in (patch.get("market_families") or {}).items():
        if name not in MARKET_FAMILIES:
            errors.append(f"unknown market_family '{name}'")
        if not isinstance(enabled, bool):
            errors.append(f"market_families[{name}] must be bool")
    tf = patch.get("token_families") or {}
    for k, v in tf.items():
        if k not in DEFAULT_SCANNER_GLOBAL["token_families"]:
            errors.append(f"unknown token_family '{k}'")
        elif not isinstance(v, list) or not all(isinstance(t, str) for t in v):
            errors.append(f"token_families[{k}] must be a list of strings")
    # Warnings
    if "networks" in patch:
        enabled = [c for c, cfg in patch["networks"].items() if cfg.get("enabled")]
        if not enabled:
            warnings.append("no chain enabled — scanner will idle")
    if "market_families" in patch:
        enabled = [m for m, on in patch["market_families"].items() if on]
        if not enabled:
            warnings.append("no market family enabled")
    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def _validate_family(family_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Per-family validator.

    Every family shares five core fields — ``enabled``, ``interval_s``,
    ``verifier_concurrency``, ``gate_thresholds``, ``default_notional_usd``
    (some families only have a subset).  Family-specific keys are
    passed through unchanged.
    """
    errors: List[str] = []
    warnings: List[str] = []
    if "enabled" in patch and not isinstance(patch["enabled"], bool):
        errors.append("enabled must be bool")
    if "interval_s" in patch and not _positive_number(patch["interval_s"]):
        errors.append("interval_s must be > 0")
    if "verifier_concurrency" in patch and not _positive_number(patch["verifier_concurrency"]):
        errors.append("verifier_concurrency must be > 0")
    if "default_notional_usd" in patch:
        v = patch["default_notional_usd"]
        if not isinstance(v, (int, float)) or v <= 0:
            errors.append("default_notional_usd must be > 0")
    # gate_thresholds is a dict-of-dicts; every leaf value must be a number
    gt = patch.get("gate_thresholds")
    if gt is not None:
        if not isinstance(gt, dict):
            errors.append("gate_thresholds must be a mapping")
        else:
            for pair, gates in gt.items():
                if not isinstance(gates, dict):
                    errors.append(f"gate_thresholds[{pair}] must be a mapping")
                    continue
                for gk, gv in gates.items():
                    # Numeric gates
                    if gk in ("min_spread_pct", "min_depth_usd",
                              "min_confidence", "min_atomic_profit_usd",
                              "min_pool_tvl_usd_in_route",
                              "min_apr_diff_pct", "min_edge_ppm",
                              "min_break_even_hours"):
                        if not isinstance(gv, (int, float)) or gv < 0:
                            errors.append(
                                f"gate_thresholds[{pair}].{gk} must be a "
                                "non-negative number")
    # tier_a_pairs / tier_b_pairs
    for k in ("tier_a_pairs", "tier_b_pairs"):
        v = patch.get(k)
        if v is not None:
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errors.append(f"{k} must be a list of strings")
    # Family-specific warnings
    if family_id == "flash_loan_arb":
        if isinstance(patch.get("providers"), dict):
            any_on = any(p.get("enabled") for p in patch["providers"].values())
            if not any_on and patch.get("enabled"):
                warnings.append("family enabled but no flash-loan provider enabled")
    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Domain façade
# ---------------------------------------------------------------------------

class ScannerConfigRepo:
    """Multi-family scanner configuration facade.

    Reuses the Phase-10 :class:`ConfigRepo` substrate for every kind
    (global + per-family), so Draft / Apply / Rollback / Audit come for
    free without a bespoke collection.
    """

    def __init__(self, config_repo: ConfigRepo, *, network_repo=None):
        self._repo = config_repo
        self._network = network_repo

    async def ensure_indexes(self) -> None:
        await self._repo.ensure_indexes()

    async def ensure_seeded(self) -> Dict[str, Any]:
        """Seed the global scanner config + every canonical family
        exactly once. Never overwrites existing operator values."""
        current = await self._repo.get_current(SCANNER_GLOBAL_KIND, default={})
        if not current:
            await self._repo.apply(
                SCANNER_GLOBAL_KIND,
                patch=copy.deepcopy(DEFAULT_SCANNER_GLOBAL),
                actor="system:boot",
                reason="seed defaults for scanner (global)",
            )
        for fid in CANONICAL_FAMILIES:
            kind = _kind_for_family(fid)
            existing = await self._repo.get_current(kind, default={})
            if existing:
                continue
            defaults = copy.deepcopy(FAMILY_DEFAULTS[fid])
            defaults.pop("_id", None)  # legacy marker — kind is the ID now
            await self._repo.apply(
                kind, patch=defaults,
                actor="system:boot",
                reason=f"seed canonical defaults for {fid}",
            )
        return await self.snapshot()

    async def snapshot(self) -> Dict[str, Any]:
        """Return the entire scanner surface (global + all families) in
        one document — used by the UI initial-load path."""
        global_cfg = await self._repo.get_current(
            SCANNER_GLOBAL_KIND, default=DEFAULT_SCANNER_GLOBAL,
        )
        families: Dict[str, Any] = {}
        for fid in CANONICAL_FAMILIES:
            families[fid] = await self._repo.get_current(
                _kind_for_family(fid),
                default={**FAMILY_DEFAULTS[fid]},
            )
        return {
            "global": global_cfg,
            "families": families,
            "family_ids": list(CANONICAL_FAMILIES),
            "family_labels": dict(FAMILY_LABELS),
            "market_families_supported": list(MARKET_FAMILIES),
            "generated_at": _iso_now(),
        }

    # -----------------------------------------------------------------
    # Global surface
    # -----------------------------------------------------------------

    async def get_global(self) -> Dict[str, Any]:
        return await self._repo.get_current(SCANNER_GLOBAL_KIND,
                                             default=DEFAULT_SCANNER_GLOBAL)

    async def get_global_draft(self) -> Optional[Dict[str, Any]]:
        return await self._repo.get_draft(SCANNER_GLOBAL_KIND)

    def validate_global(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        return _validate_global(patch or {})

    async def validate_global_live(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        base = self.validate_global(patch)
        if self._network is None:
            return base
        try:
            netcfg = await self._network.get()
        except Exception:  # noqa: BLE001
            return base
        warnings = list(base.get("warnings") or [])
        for chain, cfg in (patch.get("networks") or {}).items():
            if not cfg.get("enabled"):
                continue
            rpcs = (netcfg.get("rpc_urls") or {}).get(chain) or []
            if not rpcs:
                warnings.append(
                    f"chain '{chain}' enabled in scanner but no RPC "
                    "configured in Settings > Network"
                )
        return {**base, "warnings": warnings}

    async def save_global_draft(self, patch: Dict[str, Any],
                                 actor: str = "operator") -> Dict[str, Any]:
        v = self.validate_global(patch)
        if not v["ok"]:
            raise ValueError("draft failed validation: " + "; ".join(v["errors"]))
        return await self._repo.save_draft(SCANNER_GLOBAL_KIND, patch, actor=actor)

    async def apply_global(self, patch: Optional[Dict[str, Any]] = None,
                            actor: str = "operator",
                            reason: str = "") -> Dict[str, Any]:
        if patch is not None:
            v = self.validate_global(patch)
            if not v["ok"]:
                raise ValueError("apply failed validation: " + "; ".join(v["errors"]))
        return await self._repo.apply(SCANNER_GLOBAL_KIND, patch=patch,
                                       actor=actor, reason=reason)

    async def rollback_global(self, revision_id: Optional[str] = None,
                               actor: str = "operator", reason: str = "") -> Dict[str, Any]:
        return await self._repo.rollback(SCANNER_GLOBAL_KIND,
                                          revision_id=revision_id,
                                          actor=actor, reason=reason)

    async def global_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await self._repo.history(SCANNER_GLOBAL_KIND, limit=limit)

    # -----------------------------------------------------------------
    # Per-family surface
    # -----------------------------------------------------------------

    async def get_family(self, family_id: str) -> Dict[str, Any]:
        return await self._repo.get_current(
            _kind_for_family(family_id),
            default={**FAMILY_DEFAULTS[family_id]},
        )

    async def get_family_draft(self, family_id: str) -> Optional[Dict[str, Any]]:
        return await self._repo.get_draft(_kind_for_family(family_id))

    def validate_family(self, family_id: str,
                         patch: Dict[str, Any]) -> Dict[str, Any]:
        if family_id not in CANONICAL_FAMILIES:
            return {"ok": False,
                     "errors": [f"unknown family '{family_id}'"],
                     "warnings": []}
        return _validate_family(family_id, patch or {})

    async def save_family_draft(self, family_id: str,
                                 patch: Dict[str, Any],
                                 actor: str = "operator") -> Dict[str, Any]:
        v = self.validate_family(family_id, patch)
        if not v["ok"]:
            raise ValueError("draft failed validation: " + "; ".join(v["errors"]))
        return await self._repo.save_draft(_kind_for_family(family_id),
                                            patch, actor=actor)

    async def apply_family(self, family_id: str,
                            patch: Optional[Dict[str, Any]] = None,
                            actor: str = "operator",
                            reason: str = "") -> Dict[str, Any]:
        kind = _kind_for_family(family_id)
        if patch is not None:
            v = self.validate_family(family_id, patch)
            if not v["ok"]:
                raise ValueError("apply failed validation: " + "; ".join(v["errors"]))
        return await self._repo.apply(kind, patch=patch,
                                       actor=actor, reason=reason)

    async def rollback_family(self, family_id: str,
                               revision_id: Optional[str] = None,
                               actor: str = "operator",
                               reason: str = "") -> Dict[str, Any]:
        return await self._repo.rollback(
            _kind_for_family(family_id),
            revision_id=revision_id, actor=actor, reason=reason,
        )

    async def family_history(self, family_id: str,
                              limit: int = 50) -> List[Dict[str, Any]]:
        return await self._repo.history(_kind_for_family(family_id),
                                          limit=limit)

    # -----------------------------------------------------------------
    # Runtime controls — thin wrappers on top of apply_global
    # -----------------------------------------------------------------

    async def pause(self, *, actor: str = "operator",
                     reason: str = "") -> Dict[str, Any]:
        cur = await self.get_global()
        return await self.apply_global(
            patch={"paused": True, "runtime": {**(cur.get("runtime") or {}),
                                                  "last_reload_at": _iso_now(),
                                                  "last_reload_by": actor}},
            actor=actor, reason=reason or "operator pause",
        )

    async def resume(self, *, actor: str = "operator",
                      reason: str = "") -> Dict[str, Any]:
        cur = await self.get_global()
        return await self.apply_global(
            patch={"paused": False, "runtime": {**(cur.get("runtime") or {}),
                                                    "last_reload_at": _iso_now(),
                                                    "last_reload_by": actor}},
            actor=actor, reason=reason or "operator resume",
        )

    async def reload(self, *, actor: str = "operator",
                      reason: str = "") -> Dict[str, Any]:
        return await self.apply_global(
            patch={"runtime": {"last_reload_at": _iso_now(),
                                "last_reload_by": actor}},
            actor=actor, reason=reason or "operator reload",
        )
