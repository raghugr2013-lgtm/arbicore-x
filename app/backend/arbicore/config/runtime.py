"""Env-driven runtime configuration (Phase 6 · v2.7.0).

Single source of truth for everything a VPS operator can tune.  No
hardcoded values reach the running code; anything the operator can
change lives here and is read once at startup.

Values are read via a small `_env` helper that supports:
  * ``str`` (default fallback)
  * ``int``, ``float`` (default + safe parse)
  * ``bool`` — ``1/true/yes/on`` → True
  * ``csv`` (comma-separated)
  * ``json`` — for maps (venue-fee overrides, per-chain gwei, etc.)

Every value is exposed via :func:`get_runtime_config` so preflight,
scanners, and validation modules can read a single frozen snapshot.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_str(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    try:
        return int(v) if v not in (None, "") else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    try:
        return float(v) if v not in (None, "") else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_csv(name: str, default: str = "") -> List[str]:
    raw = os.environ.get(name, default) or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def _env_json(name: str, default: Optional[Dict[str, Any]] = None
                ) -> Dict[str, Any]:
    raw = os.environ.get(name)
    if not raw:
        return dict(default or {})
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("env %s is not valid JSON: %s — falling back",
                        name, e)
        return dict(default or {})


@dataclass
class RpcFailover:
    """Per-chain multi-endpoint failover list.

    Reads env ``PROVIDER_RPC_URLS_<CHAIN>`` (CSV) if set, otherwise
    falls back to ``PROVIDER_RPC_URL_<CHAIN>`` (single URL).
    """
    urls_by_chain: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "RpcFailover":
        chains = ["ethereum", "arbitrum", "base", "polygon", "optimism",
                   "bnb", "solana"]
        out: Dict[str, List[str]] = {}
        for c in chains:
            urls = _env_csv(f"PROVIDER_RPC_URLS_{c.upper()}")
            if not urls:
                single = _env_str(f"PROVIDER_RPC_URL_{c.upper()}")
                urls = [single] if single else []
            if urls:
                out[c] = urls
        return cls(urls_by_chain=out)


@dataclass
class ScannerCadence:
    live_market_interval_s: float
    live_market_min_spread_bps: float
    live_market_notional_usd: float
    cross_interval_s: float
    cross_min_net_bps: float
    cross_notional_usd: float
    autostart_live_market: bool
    autostart_cross: bool

    @classmethod
    def from_env(cls) -> "ScannerCadence":
        return cls(
            live_market_interval_s=_env_float("LIVE_TICK_INTERVAL_SECONDS", 15),
            live_market_min_spread_bps=_env_float("LIVE_MIN_SPREAD_BPS", 5),
            live_market_notional_usd=_env_float("LIVE_QUOTE_NOTIONAL_USD", 10000),
            cross_interval_s=_env_float("CROSS_TICK_INTERVAL_SECONDS", 25),
            cross_min_net_bps=_env_float("CROSS_MIN_NET_BPS", 8),
            cross_notional_usd=_env_float("CROSS_NOTIONAL_USD", 10000),
            autostart_live_market=_env_bool("LIVE_MARKET_AUTOSTART", False),
            autostart_cross=_env_bool("CROSS_AUTOSTART", False),
        )


@dataclass
class EconomicsConfig:
    venue_fee_bps_overrides: Dict[str, float]
    withdrawal_fee_overrides: Dict[str, float]
    native_price_overrides: Dict[str, float]
    default_slippage_bps: float
    default_liquidity_impact_bps: float
    default_gas_gwei_by_chain: Dict[str, float]
    default_gas_units: int

    @classmethod
    def from_env(cls) -> "EconomicsConfig":
        return cls(
            venue_fee_bps_overrides=_env_json("ECON_VENUE_FEE_BPS", {}),
            withdrawal_fee_overrides=_env_json("ECON_WITHDRAWAL_FEE_USD", {}),
            native_price_overrides=_env_json("ECON_NATIVE_PRICE_USD", {}),
            default_slippage_bps=_env_float("ECON_DEFAULT_SLIPPAGE_BPS", 8.0),
            default_liquidity_impact_bps=_env_float(
                "ECON_DEFAULT_LIQUIDITY_IMPACT_BPS", 4.0),
            default_gas_gwei_by_chain=_env_json(
                "ECON_DEFAULT_GAS_GWEI",
                {"ethereum": 15.0, "arbitrum": 0.1, "base": 0.05,
                  "polygon": 40.0, "optimism": 0.05, "bnb": 3.0}),
            default_gas_units=_env_int("ECON_DEFAULT_GAS_UNITS", 200_000),
        )


@dataclass
class ValidationConfig:
    window_hours: int
    daily_summary_hour_utc: int
    anomaly_min_scanner_ops: int
    anomaly_max_provider_error_rate: float
    anomaly_min_healthy_providers_pct: float
    run_id_prefix: str
    autostart_daily_writer: bool

    @classmethod
    def from_env(cls) -> "ValidationConfig":
        return cls(
            window_hours=_env_int("VALIDATION_WINDOW_HOURS", 24),
            daily_summary_hour_utc=_env_int("VALIDATION_DAILY_HOUR_UTC", 0),
            anomaly_min_scanner_ops=_env_int(
                "VALIDATION_ANOMALY_MIN_SCANNER_OPS", 20),
            anomaly_max_provider_error_rate=_env_float(
                "VALIDATION_ANOMALY_MAX_ERR_RATE", 0.25),
            anomaly_min_healthy_providers_pct=_env_float(
                "VALIDATION_ANOMALY_MIN_HEALTHY_PCT", 0.75),
            run_id_prefix=_env_str("VALIDATION_RUN_ID_PREFIX", "run"),
            autostart_daily_writer=_env_bool(
                "VALIDATION_AUTOSTART_DAILY_WRITER", True),
        )


@dataclass
class HardeningConfig:
    http_timeout_seconds: float
    http_retries: int
    http_backoff_initial_ms: int
    breaker_failure_threshold: int
    breaker_open_seconds: float
    ensure_indexes: bool

    @classmethod
    def from_env(cls) -> "HardeningConfig":
        return cls(
            http_timeout_seconds=_env_float("HARDEN_HTTP_TIMEOUT_S", 8.0),
            http_retries=_env_int("HARDEN_HTTP_RETRIES", 2),
            http_backoff_initial_ms=_env_int(
                "HARDEN_HTTP_BACKOFF_MS", 200),
            breaker_failure_threshold=_env_int(
                "HARDEN_BREAKER_FAILURE_THRESHOLD", 5),
            breaker_open_seconds=_env_float(
                "HARDEN_BREAKER_OPEN_S", 60.0),
            ensure_indexes=_env_bool("HARDEN_ENSURE_MONGO_INDEXES", True),
        )


@dataclass
class RuntimeConfig:
    rpc: RpcFailover
    scanners: ScannerCadence
    economics: EconomicsConfig
    validation: ValidationConfig
    hardening: HardeningConfig

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rpc": {"urls_by_chain": self.rpc.urls_by_chain,
                     "chain_count": len(self.rpc.urls_by_chain),
                     "endpoint_count": sum(len(v) for v
                                              in self.rpc.urls_by_chain.values())},
            "scanners": asdict(self.scanners),
            "economics": asdict(self.economics),
            "validation": asdict(self.validation),
            "hardening": asdict(self.hardening),
        }


_CONFIG: Optional[RuntimeConfig] = None


def get_runtime_config(refresh: bool = False) -> RuntimeConfig:
    """Load (once) and return the frozen runtime config snapshot."""
    global _CONFIG
    if _CONFIG is None or refresh:
        _CONFIG = RuntimeConfig(
            rpc=RpcFailover.from_env(),
            scanners=ScannerCadence.from_env(),
            economics=EconomicsConfig.from_env(),
            validation=ValidationConfig.from_env(),
            hardening=HardeningConfig.from_env(),
        )
        logger.info(
            "runtime_config loaded: rpc chains=%d · autostart_live=%s · "
            "autostart_cross=%s · window_hours=%d",
            len(_CONFIG.rpc.urls_by_chain),
            _CONFIG.scanners.autostart_live_market,
            _CONFIG.scanners.autostart_cross,
            _CONFIG.validation.window_hours,
        )
    return _CONFIG


__all__ = [
    "RuntimeConfig", "RpcFailover", "ScannerCadence",
    "EconomicsConfig", "ValidationConfig", "HardeningConfig",
    "get_runtime_config",
]
