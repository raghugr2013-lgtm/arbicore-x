"""D-5.2 Completion — StargateTransferProvider tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from arbicore.models.discovery import DiscoveryCandidate, make_candidate_id
from arbicore.models.enums import OpportunityType
from arbicore.scanners.cross_chain_arbitrage.transfer_provider import (
    StargateTransferProvider,
)


def _cand(*, bridge="stargate", src="ethereum", dst="arbitrum",
           asset="USDC") -> DiscoveryCandidate:
    subject = f"cross_chain:{bridge}:{src}→{dst}:{asset}"
    cid = make_candidate_id(
        hint_source="t",
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        subject_id=subject, asset=asset,
        candidate_venues=[f"{bridge}:{src}", f"{bridge}:{dst}"],
        hint_observed_at=1.0,
    )
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        hint_source="t", hint_observed_at=1.0, subject_id=subject,
        asset=asset,
        candidate_venues=[f"{bridge}:{src}", f"{bridge}:{dst}"],
        hint_metric={"bridge": bridge,
                      "source_chain": src,
                      "destination_chain": dst},
        reason="t",
    )


def test_stargate_rejects_wrong_bridge():
    p = StargateTransferProvider()
    out = asyncio.run(p(_cand(bridge="lifi")))
    assert out is None
    asyncio.run(p.close())


def test_stargate_rejects_solana():
    p = StargateTransferProvider()
    out = asyncio.run(p(_cand(src="solana", dst="ethereum")))
    assert out is None
    asyncio.run(p.close())


def test_stargate_rejects_unsupported_asset():
    p = StargateTransferProvider()
    out = asyncio.run(p(_cand(asset="DOGE")))
    assert out is None
    asyncio.run(p.close())


def test_stargate_handles_http_failure(monkeypatch):
    p = StargateTransferProvider()

    async def _fail(*a, **kw):
        return None
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.transfer_provider."
        "post_json_with_retry", _fail)
    out = asyncio.run(p(_cand()))
    assert out is None
    asyncio.run(p.close())


def test_stargate_projects_v2_quote(monkeypatch):
    p = StargateTransferProvider(default_notional_usd=1000.0)

    quote = {
        "quotes": [{
            "dstAmount": str(998 * 10**6),  # 998 USDC
            "fees": [{"amountUSD": "1.20"}],
            "gasCosts": [
                {"type": "SEND", "amountUSD": "3.50"},
                {"type": "RECEIVE", "amountUSD": "0.20"},
            ],
            "slippageBps": 50,
            "estimatedTime": 60,
        }]
    }

    async def _ok(*a, **kw):
        return quote
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.transfer_provider."
        "post_json_with_retry", _ok)
    out = asyncio.run(p(_cand()))
    assert out is not None
    assert out["bridge"] == "stargate"
    assert out["source_id"] == "stargate_quote_real"
    assert out["expected_out_amount"] == 998.0
    assert out["total_bridge_fee_usd"] == 1.20
    assert out["gas_source_chain_usd"] == 3.5
    assert out["gas_destination_chain_usd"] == 0.2
    assert out["slippage_bridge_pct"] == 0.5
    assert out["primary_venue_id"] == "stargate:ethereum:USDC"
    assert out["secondary_venue_id"] == "stargate:arbitrum:USDC"
    asyncio.run(p.close())


def test_stargate_caches_repeat_calls(monkeypatch):
    p = StargateTransferProvider(ttl_cache_s=60.0)
    calls = {"n": 0}

    async def _ok(*a, **kw):
        calls["n"] += 1
        return {"quotes": [{"dstAmount": "1000000000",
                              "fees": [], "gasCosts": [],
                              "slippageBps": 50}]}
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.transfer_provider."
        "post_json_with_retry", _ok)
    cand = _cand()
    asyncio.run(p(cand))
    asyncio.run(p(cand))
    assert calls["n"] == 1
    asyncio.run(p.close())


def test_stargate_inv3_source_id_is_real():
    from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
    assert SOURCE_REGISTRY["stargate_quote_real"].provenance == \
        DataProvenance.REAL


def test_stargate_inv2_no_emission_bus():
    import arbicore.scanners.cross_chain_arbitrage.transfer_provider as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "from ...runtime.event_bus" not in text


def test_stargate_tolerates_inline_quote_shape(monkeypatch):
    """Newer Stargate shapes inline the quote at the top level."""
    p = StargateTransferProvider()

    async def _ok(*a, **kw):
        return {"dstAmount": str(1000 * 10**6),
                "fees": [], "gasCosts": [],
                "slippageBps": 50, "estimatedTime": 60}
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.transfer_provider."
        "post_json_with_retry", _ok)
    out = asyncio.run(p(_cand()))
    assert out is not None
    assert out["expected_out_amount"] == 1000.0
    asyncio.run(p.close())


def test_stargate_reuses_http_retry_substrate():
    """Substrate-reuse audit: provider must consume http_retry imports."""
    import arbicore.scanners.cross_chain_arbitrage.transfer_provider as mod
    text = open(mod.__file__).read()
    assert "post_json_with_retry" in text
    assert "TTLCache" in text
    assert "RetryConfig" in text
