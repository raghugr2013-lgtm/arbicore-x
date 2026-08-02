"""D-3.6 — Bounded live-network smoke probe.

CONTRACT:
  * Maximum 5 pairs (Tier-A set)
  * SINGLE observation cycle per pair (no loop)
  * Scanner remains DISABLED (we never construct the orchestrator)
  * NO emissions (no EmissionBus is used at all here)
  * NO state mutation (no DB writes, no scanner_state writes, no provenance writes)
  * Telemetry only — printed to stdout for the readiness assessment

Sources exercised:
  * DexScreenerHintSource (the only D-3 source wired live at D-3.6)
"""
import asyncio
import json
import os
import time
from typing import Any, Dict, List

# Make backend imports work when invoked from /app/backend.
import sys
sys.path.insert(0, "/app/backend")

from arbicore.scanners.discovery.dexscreener_hint import DexScreenerHintSource


PAIRS = [
    "WETH/USDC",
    "WETH/USDT",
    "WBTC/USDC",
    "ARB/USDC",
    "SOL/USDC",
]


def _cfg_for(pair: str) -> Dict[str, Any]:
    return {
        "tier_a_pairs": [f"{pair}@ethereum"],
        "discovery_sources": {"dexscreener_hint": {
            "ds_divergence_threshold_bps": 40.0,
            "volume_floor_usd": 50_000.0,
        }},
    }


async def _probe_pair(pair: str) -> Dict[str, Any]:
    src = DexScreenerHintSource(config_loader=lambda: _cfg_for(pair))
    t0 = time.time()
    try:
        # Direct parser call so we can collect the raw observation count
        # even when divergence < threshold (the public discover() returns []).
        raw = await src._fetch_pair_dex_quotes(pair)
        fetch_ms = int((time.time() - t0) * 1000)
        mids = [o["mid"] for o in raw if o.get("mid", 0) > 0]
        venues = sorted({f"{o.get('dex','?')}:{o.get('chain','?')}" for o in raw})
        if mids:
            mn, mx = min(mids), max(mids)
            div_bps = (mx - mn) / mn * 10_000.0 if mn > 0 else 0.0
        else:
            mn = mx = 0.0
            div_bps = 0.0
        # Run the gated discover() once, then read health.
        t1 = time.time()
        cands = await src.discover()
        discover_ms = int((time.time() - t1) * 1000)
        health = await src.health()
        await src.close()
        return {
            "pair": pair,
            "fetch_latency_ms": fetch_ms,
            "discover_latency_ms": discover_ms,
            "raw_observations": len(raw),
            "venue_count": len(venues),
            "venues": venues[:8],
            "mid_min": mn, "mid_max": mx,
            "divergence_bps": round(div_bps, 1),
            "candidate_emitted_above_threshold": len(cands),
            "health_ok": health.ok,
            "health_last_error": health.last_error,
            "health_latency_ms": health.latency_ms,
        }
    except Exception as exc:  # noqa: BLE001
        try:
            await src.close()
        except Exception:
            pass
        return {
            "pair": pair,
            "fetch_latency_ms": int((time.time() - t0) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _graceful_disable_summary() -> Dict[str, Any]:
    keys = {
        "ALCHEMY_API_KEY": os.environ.get("ALCHEMY_API_KEY"),
        "HELIUS_API_KEY": os.environ.get("HELIUS_API_KEY"),
        "GRAPH_GATEWAY_API_KEY": os.environ.get("GRAPH_GATEWAY_API_KEY"),
    }
    return {k: bool(v) for k, v in keys.items()}


async def main():
    print("=" * 78)
    print("D-3.6 BOUNDED LIVE-NETWORK SMOKE PROBE")
    print("=" * 78)
    print(f"Pairs probed (max 5): {PAIRS}")
    print(f"Scanner state: DISABLED (orchestrator NOT constructed)")
    print(f"Emissions: NONE (EmissionBus not wired)")
    print(f"State mutation: NONE (no DB / config writes)")
    print()

    results: List[Dict[str, Any]] = []
    for pair in PAIRS:
        r = await _probe_pair(pair)
        results.append(r)
        print(json.dumps(r, default=str))

    print()
    print("--- Aggregate ---")
    lats = [r["fetch_latency_ms"] for r in results if "fetch_latency_ms" in r]
    obs  = [r.get("raw_observations", 0) for r in results]
    err  = [r for r in results if "error" in r or not r.get("health_ok", True)]
    cnd  = sum(r.get("candidate_emitted_above_threshold", 0) for r in results)
    print(json.dumps({
        "probe_count": len(results),
        "fetch_latency_ms_min": min(lats) if lats else None,
        "fetch_latency_ms_max": max(lats) if lats else None,
        "fetch_latency_ms_mean": int(sum(lats) / len(lats)) if lats else None,
        "raw_observations_min": min(obs) if obs else None,
        "raw_observations_max": max(obs) if obs else None,
        "candidates_above_threshold_total": cnd,
        "error_count": len(err),
    }, default=str))

    print()
    print("--- Graceful-disable state (credentialed sources) ---")
    print(json.dumps(_graceful_disable_summary()))


if __name__ == "__main__":
    asyncio.run(main())
