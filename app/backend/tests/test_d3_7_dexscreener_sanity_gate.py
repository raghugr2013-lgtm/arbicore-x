"""D-3.7 — DexScreener hint-layer divergence sanity gate.

Suppresses implausible divergence values (e.g. > 1000 bps by default) as
symbol-collision artefacts. INV-3 already prevents propagation to canonical;
the gate eliminates wasted verifier cycles.

Tests cover:
  - Below-ceiling divergence (e.g. 100 bps) → candidate emitted
  - Above-ceiling divergence (e.g. 6000 bps) → no candidate, counter increments
  - Above-ceiling but high-throughput case → counter increments without crashing
  - Ceiling override via config → custom threshold respected
  - INV-1 / INV-3 still hold across the gate (typing preserved; provenance
    annotation unchanged)
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import DiscoveryCandidate
from arbicore.scanners.discovery.dexscreener_hint import DexScreenerHintSource


def _make_source(*, observations: List[Dict[str, Any]],
                 cfg_overrides: Dict[str, Any] | None = None
                 ) -> DexScreenerHintSource:
    discovery_cfg = {"ds_divergence_threshold_bps": 40, "volume_floor_usd": 0}
    if cfg_overrides:
        discovery_cfg.update(cfg_overrides)

    class _Patched(DexScreenerHintSource):
        async def _fetch_pair_dex_quotes(self, pair_canonical):
            return observations

    return _Patched(config_loader=lambda: {
        "tier_a_pairs": ["WETH/USDC@ethereum"],
        "discovery_sources": {"dexscreener_hint": discovery_cfg},
    })


# ---------------------------------------------------------------------------
# Below-ceiling — candidate still emits
# ---------------------------------------------------------------------------

def test_sanity_gate_allows_plausible_divergence():
    src = _make_source(observations=[
        {"dex": "uniswap", "chain": "ethereum", "mid": 2000.0,
         "h24_volume_usd": 100_000_000},
        {"dex": "pancake", "chain": "bnb", "mid": 2020.0,
         "h24_volume_usd": 100_000_000},
    ])
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    assert isinstance(cands[0], DiscoveryCandidate)
    assert not isinstance(cands[0], CanonicalOpportunity)
    # 100 bps is well below the 1000 default ceiling
    assert abs(cands[0].hint_metric["divergence_bps"] - 100.0) < 1.0
    # Sanity gate counter unchanged
    assert src._last_sanity_rejections == 0


# ---------------------------------------------------------------------------
# Above-ceiling — drop + counter increments
# ---------------------------------------------------------------------------

def test_sanity_gate_drops_implausible_divergence():
    """Mids of 2000 and 3500 → 7500 bps → above the 1000 default ceiling."""
    src = _make_source(observations=[
        {"dex": "uniswap", "chain": "ethereum", "mid": 2000.0,
         "h24_volume_usd": 100_000_000},
        {"dex": "impostor", "chain": "long_tail_chain", "mid": 3500.0,
         "h24_volume_usd": 100_000_000},
    ])
    cands = asyncio.run(src.discover())
    assert cands == []
    assert src._last_sanity_rejections == 1


def test_sanity_gate_repeated_rejections_accumulate():
    src = _make_source(observations=[
        {"dex": "uniswap", "chain": "ethereum", "mid": 2000.0,
         "h24_volume_usd": 100_000_000},
        {"dex": "impostor", "chain": "x", "mid": 8000.0,
         "h24_volume_usd": 100_000_000},
    ])
    for _ in range(3):
        asyncio.run(src.discover())
    assert src._last_sanity_rejections == 3


# ---------------------------------------------------------------------------
# Extreme outlier (the WETH/USDT $6.61e-06 case observed in the live probe)
# ---------------------------------------------------------------------------

def test_sanity_gate_drops_extreme_outlier_no_crash():
    src = _make_source(observations=[
        {"dex": "uniswap", "chain": "ethereum", "mid": 2277.86,
         "h24_volume_usd": 100_000_000},
        {"dex": "impostor", "chain": "fantom_test", "mid": 6.61e-06,
         "h24_volume_usd": 100_000_000},
    ])
    cands = asyncio.run(src.discover())
    assert cands == []
    assert src._last_sanity_rejections == 1
    # health() still surfaces successfully — no error from this path
    h = asyncio.run(src.health())
    assert h.ok is True


# ---------------------------------------------------------------------------
# Custom ceiling — operator can override
# ---------------------------------------------------------------------------

def test_sanity_gate_respects_custom_ceiling():
    # With ceiling raised to 10_000 bps, a 7500 bps case should pass.
    src = _make_source(
        observations=[
            {"dex": "uniswap", "chain": "ethereum", "mid": 2000.0,
             "h24_volume_usd": 100_000_000},
            {"dex": "impostor", "chain": "x", "mid": 3500.0,
             "h24_volume_usd": 100_000_000},
        ],
        cfg_overrides={"ds_divergence_sanity_ceiling_bps": 10_000.0},
    )
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    assert src._last_sanity_rejections == 0


def test_sanity_gate_respects_lowered_ceiling():
    # With ceiling lowered to 50 bps, a 100 bps case should be rejected.
    src = _make_source(
        observations=[
            {"dex": "uniswap", "chain": "ethereum", "mid": 2000.0,
             "h24_volume_usd": 100_000_000},
            {"dex": "pancake", "chain": "bnb", "mid": 2020.0,
             "h24_volume_usd": 100_000_000},
        ],
        cfg_overrides={"ds_divergence_sanity_ceiling_bps": 50.0},
    )
    cands = asyncio.run(src.discover())
    assert cands == []
    assert src._last_sanity_rejections == 1


# ---------------------------------------------------------------------------
# Boundary — divergence equal to ceiling is allowed (strict > only)
# ---------------------------------------------------------------------------

def test_sanity_gate_allows_exactly_at_ceiling():
    # mids 2000 and 2020 → 100 bps; ceiling exactly 100 → not rejected (strict >).
    src = _make_source(
        observations=[
            {"dex": "uniswap", "chain": "ethereum", "mid": 2000.0,
             "h24_volume_usd": 100_000_000},
            {"dex": "pancake", "chain": "bnb", "mid": 2020.0,
             "h24_volume_usd": 100_000_000},
        ],
        cfg_overrides={"ds_divergence_sanity_ceiling_bps": 100.0},
    )
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    assert src._last_sanity_rejections == 0
