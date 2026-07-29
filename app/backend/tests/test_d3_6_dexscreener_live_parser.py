"""D-3.6 — DexScreener live REST integration parser tests.

The DexScreenerHintSource is the only D-3 source wired to a live public
endpoint at D-3.6 (no credentials required). All credentialed sources
(Alchemy / Helius / Graph) remain stubbed and graceful-disabled.

These tests use a mocked httpx.AsyncClient so they:
  - exercise the real `_fetch_pair_dex_quotes` parser path
  - cover happy-path, non-200, malformed JSON, base/quote symbol mismatch,
    missing fields, network error → graceful-disable

INV-1 (DiscoveryCandidate ≠ CanonicalOpportunity) and INV-3 (HINT provenance
is telemetry only) are re-asserted here so the live wiring cannot silently
drift outside the contract.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import DiscoveryCandidate
from arbicore.models.enums import DataProvenance, OpportunityType
from arbicore.scanners.discovery.dexscreener_hint import DexScreenerHintSource


# ---------------------------------------------------------------------------
# Mock httpx client
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _MockClient:
    def __init__(self, resp: _Resp | Exception):
        self._resp = resp
        self.calls = []

    async def get(self, url: str, params: Dict[str, Any] | None = None):
        self.calls.append((url, params))
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp

    async def aclose(self):  # noqa: D401
        pass


def _make_source(client: _MockClient, *, cfg: Dict[str, Any] | None = None):
    cfg = cfg or {
        "tier_a_pairs": ["WETH/USDC@ethereum"],
        "discovery_sources": {"dexscreener_hint": {
            "ds_divergence_threshold_bps": 40,
            "volume_floor_usd": 50_000,
        }},
    }
    return DexScreenerHintSource(
        config_loader=lambda: cfg, http_client=client,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Happy path — two venues, diverged
# ---------------------------------------------------------------------------

def test_live_parser_happy_path_emits_candidate():
    payload = {"pairs": [
        {
            "baseToken": {"symbol": "WETH"},
            "quoteToken": {"symbol": "USDC"},
            "priceUsd": "2000.00",
            "liquidity": {"usd": 5_000_000.0},
            "volume": {"h24": 100_000_000.0},
            "dexId": "uniswap",
            "chainId": "ethereum",
            "pairAddress": "0xpool_a",
        },
        {
            "baseToken": {"symbol": "WETH"},
            "quoteToken": {"symbol": "USDC"},
            "priceUsd": "2020.00",
            "liquidity": {"usd": 3_000_000.0},
            "volume": {"h24": 80_000_000.0},
            "dexId": "pancakeswap",
            "chainId": "bnb",
            "pairAddress": "0xpool_b",
        },
    ]}
    client = _MockClient(_Resp(200, payload))
    src = _make_source(client)
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    c = cands[0]
    # INV-1: DiscoveryCandidate ≠ CanonicalOpportunity
    assert isinstance(c, DiscoveryCandidate)
    assert not isinstance(c, CanonicalOpportunity)
    assert c.opportunity_type == OpportunityType.DEX_ARBITRAGE
    assert c.hint_source == "dexscreener_hint"
    assert c.subject_id == "WETH/USDC"
    assert c.asset == "WETH"
    # Divergence is (2020-2000)/2000 * 10000 = 100 bps
    assert abs(c.hint_metric["divergence_bps"] - 100.0) < 1.0
    assert c.hint_metric["observation_count"] == 2
    # Venues span both DEX:chain pairs (sorted)
    assert "uniswap:ethereum" in c.candidate_venues
    assert "pancakeswap:bnb" in c.candidate_venues
    # Source health reflects a successful poll
    h = asyncio.run(src.health())
    assert h.ok is True
    assert h.last_error is None


# ---------------------------------------------------------------------------
# Symbol-mismatch filter
# ---------------------------------------------------------------------------

def test_live_parser_filters_reverse_pair_rows():
    """USDC/WETH (reversed) and non-matching symbols are filtered out."""
    payload = {"pairs": [
        {
            "baseToken": {"symbol": "WETH"}, "quoteToken": {"symbol": "USDC"},
            "priceUsd": "2000", "liquidity": {"usd": 1_000_000},
            "volume": {"h24": 100_000_000}, "dexId": "uniswap",
            "chainId": "ethereum", "pairAddress": "0x1",
        },
        {  # reverse pair — must be discarded
            "baseToken": {"symbol": "USDC"}, "quoteToken": {"symbol": "WETH"},
            "priceUsd": "0.0005", "liquidity": {"usd": 999_999},
            "volume": {"h24": 100_000_000}, "dexId": "sushi",
            "chainId": "ethereum", "pairAddress": "0x2",
        },
        {  # foreign quote token — must be discarded
            "baseToken": {"symbol": "WETH"}, "quoteToken": {"symbol": "DAI"},
            "priceUsd": "2001", "liquidity": {"usd": 1_000_000},
            "volume": {"h24": 100_000_000}, "dexId": "uniswap",
            "chainId": "ethereum", "pairAddress": "0x3",
        },
    ]}
    src = _make_source(_MockClient(_Resp(200, payload)))
    cands = asyncio.run(src.discover())
    # Only one matching observation → cannot diverge → no candidate
    assert cands == []


# ---------------------------------------------------------------------------
# Volume floor filter
# ---------------------------------------------------------------------------

def test_live_parser_respects_volume_floor():
    payload = {"pairs": [
        {
            "baseToken": {"symbol": "WETH"}, "quoteToken": {"symbol": "USDC"},
            "priceUsd": "2000", "liquidity": {"usd": 1_000_000},
            "volume": {"h24": 100_000_000}, "dexId": "uniswap",
            "chainId": "ethereum", "pairAddress": "0x1",
        },
        {  # too thin
            "baseToken": {"symbol": "WETH"}, "quoteToken": {"symbol": "USDC"},
            "priceUsd": "2100", "liquidity": {"usd": 10_000},
            "volume": {"h24": 1_000}, "dexId": "sushi",
            "chainId": "ethereum", "pairAddress": "0x2",
        },
    ]}
    src = _make_source(_MockClient(_Resp(200, payload)))
    cands = asyncio.run(src.discover())
    assert cands == []


# ---------------------------------------------------------------------------
# HTTP error / non-200
# ---------------------------------------------------------------------------

def test_live_parser_non_200_returns_no_candidates():
    src = _make_source(_MockClient(_Resp(503, {"error": "upstream"})))
    cands = asyncio.run(src.discover())
    assert cands == []
    h = asyncio.run(src.health())
    # non-200 is silent (parser returns []) — last_error remains None
    assert h.ok is True


def test_live_parser_network_error_graceful_disable():
    client = _MockClient(RuntimeError("connection refused"))
    src = _make_source(client)
    cands = asyncio.run(src.discover())
    assert cands == []
    h = asyncio.run(src.health())
    assert h.ok is False
    assert h.last_error and "RuntimeError" in h.last_error
    # latency telemetry still recorded
    assert h.latency_ms >= 0


# ---------------------------------------------------------------------------
# Malformed payload
# ---------------------------------------------------------------------------

def test_live_parser_handles_malformed_rows():
    payload = {"pairs": [
        {"baseToken": None, "quoteToken": None},
        {"baseToken": {"symbol": "WETH"}, "quoteToken": {"symbol": "USDC"},
         "priceUsd": "not-a-number", "dexId": "x", "chainId": "y"},
        {"baseToken": {"symbol": "WETH"}, "quoteToken": {"symbol": "USDC"},
         "priceUsd": "2000", "liquidity": {"usd": 1_000_000},
         "volume": {"h24": 100_000_000}, "dexId": "uniswap",
         "chainId": "ethereum", "pairAddress": "0x1"},
    ]}
    src = _make_source(_MockClient(_Resp(200, payload)))
    # Only one parseable observation → no divergence → no candidate, but no crash
    cands = asyncio.run(src.discover())
    assert cands == []


def test_live_parser_handles_empty_pairs():
    src = _make_source(_MockClient(_Resp(200, {"pairs": []})))
    assert asyncio.run(src.discover()) == []


# ---------------------------------------------------------------------------
# INV-3: provenance attribute is REAL but classified as HINT (telemetry only)
# ---------------------------------------------------------------------------

def test_inv_3_dexscreener_hint_provenance_is_telemetry_only():
    src = DexScreenerHintSource(config_loader=lambda: {})
    # Aggregator HINT provenance is technically REAL (the data is live) but
    # the SOURCE_REGISTRY classifies it as HINT-only via a reason marker so
    # the verifier never propagates this to CanonicalOpportunity.source_data_quality.
    assert src.provenance_of_hint == DataProvenance.REAL
    from arbicore.data.provenance import SOURCE_REGISTRY
    entry = SOURCE_REGISTRY["dexscreener_hint"]
    assert entry.provenance == DataProvenance.REAL
    assert "HINT" in entry.reason.upper()
    # The hint source itself declares aggregator tier=2
    assert src.tier == 2
