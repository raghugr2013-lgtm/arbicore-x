"""Phase 8 — env-driven safety configuration.

Nothing hardcoded. Every threshold reads from an ``ARBICORE_SAFETY_*``
env variable and falls back to a conservative default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


def _f(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _b(name: str, default: bool) -> bool:
    v = os.environ.get(name, "").lower()
    if v in ("1", "true", "yes", "y", "on"):  return True
    if v in ("0", "false", "no", "n", "off"): return False
    return default


@dataclass(frozen=True)
class PolicyConfig:
    # kill switch
    kill_engaged_by_default: bool = True     # SAFE DEFAULT — off until operator engages
    # capital allocation
    max_per_trade_usd: float = 500.0
    max_per_chain_usd: float = 5000.0
    max_daily_notional_usd: float = 25000.0
    # execution readiness
    live_execution_enabled: bool = False     # HARD FALSE — Phase 8 requires operator override
    require_approval_gate: bool = True
    require_paper_validation: bool = True
    # per-opportunity-type caps (JSON-in-env: 'dex_arbitrage:250,flash_loan_arbitrage:1000')
    per_type_caps_usd: Dict[str, float] = field(default_factory=dict)


def _parse_type_caps(raw: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            continue
        k, v = pair.split(":", 1)
        try:
            out[k.strip()] = float(v.strip())
        except ValueError:
            continue
    return out


def load_policy_from_env() -> PolicyConfig:
    return PolicyConfig(
        kill_engaged_by_default=_b(
            "ARBICORE_SAFETY_KILL_DEFAULT", True),
        max_per_trade_usd=_f(
            "ARBICORE_SAFETY_MAX_PER_TRADE_USD", 500.0),
        max_per_chain_usd=_f(
            "ARBICORE_SAFETY_MAX_PER_CHAIN_USD", 5000.0),
        max_daily_notional_usd=_f(
            "ARBICORE_SAFETY_MAX_DAILY_NOTIONAL_USD", 25000.0),
        live_execution_enabled=_b(
            "ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED", False),
        require_approval_gate=_b(
            "ARBICORE_SAFETY_REQUIRE_APPROVAL", True),
        require_paper_validation=_b(
            "ARBICORE_SAFETY_REQUIRE_PAPER_VALIDATION", True),
        per_type_caps_usd=_parse_type_caps(
            os.environ.get("ARBICORE_SAFETY_PER_TYPE_CAPS_USD", "")),
    )
