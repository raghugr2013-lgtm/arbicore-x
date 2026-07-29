"""D-5.1 — TransferModelProvider tests (LiFiTransferProvider)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from arbicore.models.discovery import DiscoveryCandidate, make_candidate_id
from arbicore.models.enums import OpportunityType
from arbicore.scanners.cross_chain_arbitrage.transfer_provider import (
    LiFiTransferProvider, noop_transfer_provider,
)


def _make_candidate(*, bridge="lifi", src="ethereum", dst="arbitrum",
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
        hint_source="t", hint_observed_at=1.0,
        subject_id=subject, asset=asset,
        candidate_venues=[f"{bridge}:{src}", f"{bridge}:{dst}"],
        hint_metric={"bridge": bridge,
                      "source_chain": src,
                      "destination_chain": dst},
        reason="t",
    )


def test_noop_provider_returns_none():
    out = asyncio.run(noop_transfer_provider(_make_candidate()))
    assert out is None


def test_lifi_provider_rejects_wrong_bridge():
    p = LiFiTransferProvider()
    out = asyncio.run(p(_make_candidate(bridge="stargate")))
    assert out is None
    asyncio.run(p.close())


def test_lifi_provider_rejects_unsupported_chain():
    p = LiFiTransferProvider()
    out = asyncio.run(p(_make_candidate(src="aptos", dst="cosmos")))
    assert out is None
    asyncio.run(p.close())


def test_lifi_provider_handles_http_failure(monkeypatch):
    p = LiFiTransferProvider()

    async def _fail(*a, **kw):
        return None
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.transfer_provider."
        "get_json_with_retry", _fail)
    out = asyncio.run(p(_make_candidate()))
    assert out is None
    asyncio.run(p.close())


def test_lifi_provider_projects_quote(monkeypatch):
    p = LiFiTransferProvider(default_notional_usd=1000.0)
    quote = {
        "estimate": {
            "toAmount": str(995 * 10**6),
            "feeCosts": [{"amountUSD": "1.50"}],
            "gasCosts": [{"type": "SEND", "amountUSD": "4.00"}],
            "slippage": 0.005,
            "executionDuration": 240,
        }
    }

    async def _ok(*a, **kw):
        return quote
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.transfer_provider."
        "get_json_with_retry", _ok)
    out = asyncio.run(p(_make_candidate(asset="USDC")))
    assert out is not None
    assert out["bridge"] == "lifi"
    assert out["source_id"] == "lifi_quote_real"
    assert out["expected_out_amount"] == 995.0
    assert out["total_bridge_fee_usd"] == 1.5
    assert out["gas_source_chain_usd"] == 4.0
    assert out["slippage_bridge_pct"] == 0.5
    assert out["primary_venue_id"] == "lifi:ethereum:USDC"
    asyncio.run(p.close())


def test_lifi_provider_caches_repeat_calls(monkeypatch):
    p = LiFiTransferProvider(ttl_cache_s=60.0)
    calls = {"n": 0}

    async def _ok(*a, **kw):
        calls["n"] += 1
        return {"estimate": {"toAmount": "1000000000",
                              "feeCosts": [], "gasCosts": [],
                              "slippage": 0.005}}
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.transfer_provider."
        "get_json_with_retry", _ok)
    cand = _make_candidate()
    a = asyncio.run(p(cand))
    b = asyncio.run(p(cand))
    assert a is not None and b is not None
    assert calls["n"] == 1
    asyncio.run(p.close())


def test_lifi_provider_caches_none_responses(monkeypatch):
    p = LiFiTransferProvider(ttl_cache_s=60.0)
    calls = {"n": 0}

    async def _none(*a, **kw):
        calls["n"] += 1
        return None
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.transfer_provider."
        "get_json_with_retry", _none)
    cand = _make_candidate()
    asyncio.run(p(cand))
    asyncio.run(p(cand))
    assert calls["n"] == 1
    asyncio.run(p.close())


def test_inv3_provider_source_id_is_real():
    from arbicore.data.provenance import SOURCE_REGISTRY, DataProvenance
    assert SOURCE_REGISTRY["lifi_quote_real"].provenance == DataProvenance.REAL


def test_inv2_transfer_provider_no_emission_bus():
    import arbicore.scanners.cross_chain_arbitrage.transfer_provider as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "from ...runtime.event_bus" not in text



# ── Subset C — LI.FI POST→GET drift regression guard ─────────────────────
def test_subset_c_lifi_quote_uses_get_helper():
    """LI.FI deprecated POST /v1/quote (404). The provider MUST call
    get_json_with_retry (not post_json_with_retry) for the /quote endpoint.
    Catches accidental POST regressions in future refactors."""
    import inspect
    import arbicore.scanners.cross_chain_arbitrage.transfer_provider as mod
    src = inspect.getsource(mod.LiFiTransferProvider.__call__)
    assert "get_json_with_retry" in src, \
        "LiFiTransferProvider must use get_json_with_retry for /quote (Subset C)"
    assert "post_json_with_retry" not in src, \
        "LiFiTransferProvider must NOT use post_json_with_retry for /quote (Subset C)"


def test_subset_c_get_helper_exists():
    """The http_retry substrate must expose get_json_with_retry mirroring
    the POST helper's retry / backoff contract (Subset C addition)."""
    from arbicore.scanners.http_retry import (
        get_json_with_retry, post_json_with_retry, RetryConfig,
    )
    import inspect
    # Both helpers exist
    assert callable(get_json_with_retry)
    assert callable(post_json_with_retry)
    # GET helper accepts a `params` kw, distinguishing it from POST
    sig = inspect.signature(get_json_with_retry)
    assert "params" in sig.parameters, "get_json_with_retry must accept params="
    assert "config" in sig.parameters, "get_json_with_retry must accept config="
