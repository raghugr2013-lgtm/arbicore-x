"""D-3.6B — Base · Aerodrome (classic AMM + SlipStream) wiring for EVMV3Quoter.

Offline, deterministic. The on-chain eth_call is delegated to the canonical
QuoterRegistry backends (aerodrome classic Router + SlipStream QuoterV2); here
we monkeypatch QuoterRegistry.quote_route with real-shaped RouteQuotes keyed on
the hop dex so we exercise the D-3.6B wiring (both families queried, best valid
amountOut wins, fail-closed, backend provenance) with ZERO network. Also proves
the wired quoter integrates with the existing DEXQuoteVerifier gate path.
Real-network proof lives in test_d3_6b_aerodrome_smoke.py.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.scanners.dex_arbitrage.quoter import DEXQuoteResult, EVMV3Quoter
from arbicore.execution import quoter as execq
from arbicore.scanners.dex_arbitrage import DEXQuoteVerifier
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import OpportunityType


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _hop(*, dex, token_in, token_out, amount_in_wei, amount_out_wei, block=27000000):
    contract = {
        "aerodrome": execq.BASE_AERO_CLASSIC_ROUTER,
        "aerodrome_slipstream": execq.BASE_AERO_SLIPSTREAM_QUOTER,
        "uniswap_v3": execq.BASE_UNIV3_QUOTER_V2,
    }[dex]
    return execq.HopQuote(
        hop_index=0, dex=dex, token_in=token_in, token_out=token_out,
        amount_in_wei=int(amount_in_wei), amount_out_wei=int(amount_out_wei),
        sqrt_price_x96_after=None, gas_estimate_units=80000, price_impact_bps=None,
        quoter_contract=contract, rpc_host="mainnet.base.org",
        block_number=block, status="ok", error=None, generated_at="2026-06-01T00:00:00Z")


def _route_ok(hop):
    return execq.RouteQuote(
        chain="base", hops=[hop], final_amount_out_wei=hop.amount_out_wei,
        aggregate_price_impact_bps=None, aggregate_gas_estimate_units=80000,
        status="ok", generated_at="2026-06-01T00:00:00Z", ttl_seconds=5)


def _route_fail(dex, err="fallback:revert"):
    h = execq.HopQuote(
        hop_index=0, dex=dex, token_in="0x", token_out="0x", amount_in_wei=1,
        amount_out_wei=0, sqrt_price_x96_after=None, gas_estimate_units=None,
        price_impact_bps=None, quoter_contract="n/a", rpc_host="mainnet.base.org",
        block_number=None, status=err, error="reverted", generated_at="t")
    return execq.RouteQuote(
        chain="base", hops=[h], final_amount_out_wei=0,
        aggregate_price_impact_bps=None, aggregate_gas_estimate_units=None,
        status=err, generated_at="t", ttl_seconds=5)


def _clear_rpc(monkeypatch):
    for k in ("ARBICORE_RPC_URL_BASE", "ARBICORE_RPC_URL", "BASE_RPC_URL",
              "ALCHEMY_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def _aero_quoter():
    return EVMV3Quoter(chain="base", dex="aerodrome",
                       source_id="aerodrome_quoter_base")


# ----- credentials ----------------------------------------------------------

def test_aerodrome_base_enabled_by_base_rpc(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    assert _aero_quoter().credentials_available is True


def test_aerodrome_base_disabled_without_rpc(monkeypatch):
    _clear_rpc(monkeypatch)
    res = _run(_aero_quoter().quote(pair_canonical="WETH/USDC", size_in_usd=1000.0))
    assert res.ok is False and res.reason.startswith("credentials_missing:")


# ----- both backends succeed → highest amountOut wins -----------------------

def test_both_backends_succeed_best_wins(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    seen = []

    async def fake(self, *, chain, hops, rpc_url=None):
        h = hops[0]; dex = h["dex"]; seen.append(dex)
        out = {"aerodrome": 400_000_000_000_000_000,          # 0.40 WETH
               "aerodrome_slipstream": 410_000_000_000_000_000}[dex]  # 0.41
        return _route_ok(_hop(dex=dex, token_in=h["token_in"],
                              token_out=h["token_out"],
                              amount_in_wei=h["amount_in_wei"], amount_out_wei=out))

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake)
    res = _run(_aero_quoter().quote(pair_canonical="WETH/USDC",
                                    size_in_usd=1000.0, direction="buy"))
    assert res.ok is True and res.dex == "aerodrome"
    assert res.token_in == "USDC" and res.token_out == "WETH"
    assert res.amount_out == pytest.approx(0.41)
    assert res.raw["winning_backend"] == "aerodrome_slipstream"
    assert res.raw["winning_dex"] == "aerodrome_slipstream"
    # both families were queried + recorded in provenance
    assert set(seen) == {"aerodrome", "aerodrome_slipstream"}
    attempts = res.raw["backend_attempts"]
    assert {a["backend"] for a in attempts} == {"aerodrome_classic", "aerodrome_slipstream"}
    assert all(a["status"] == "ok" for a in attempts)


# ----- one succeeds / one fails → the successful authoritative quote wins ----

def test_one_backend_fails_other_used(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")

    async def fake(self, *, chain, hops, rpc_url=None):
        h = hops[0]; dex = h["dex"]
        if dex == "aerodrome_slipstream":
            return _route_fail("aerodrome_slipstream")
        return _route_ok(_hop(dex="aerodrome", token_in=h["token_in"],
                              token_out=h["token_out"],
                              amount_in_wei=h["amount_in_wei"],
                              amount_out_wei=395_000_000_000_000_000))

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake)
    res = _run(_aero_quoter().quote(pair_canonical="WETH/USDC",
                                    size_in_usd=1000.0, direction="buy"))
    assert res.ok is True
    assert res.raw["winning_backend"] == "aerodrome_classic"
    attempts = {a["backend"]: a["status"] for a in res.raw["backend_attempts"]}
    assert attempts["aerodrome_classic"] == "ok"
    assert attempts["aerodrome_slipstream"].startswith("fallback:")


# ----- both fail → fail-closed ----------------------------------------------

def test_both_backends_fail_closed(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")

    async def fake(self, *, chain, hops, rpc_url=None):
        return _route_fail(hops[0]["dex"])

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake)
    res = _run(_aero_quoter().quote(pair_canonical="WETH/USDC",
                                    size_in_usd=1000.0, direction="buy"))
    assert res.ok is False
    assert res.reason == "quote_unavailable:all_aerodrome_backends_failed"


# ----- non-positive amountOut rejected --------------------------------------

def test_nonpositive_amount_out_rejected(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")

    async def fake(self, *, chain, hops, rpc_url=None):
        h = hops[0]
        # status ok but zero output → must be treated as a failure (no fabrication)
        return _route_ok(_hop(dex=h["dex"], token_in=h["token_in"],
                              token_out=h["token_out"],
                              amount_in_wei=h["amount_in_wei"], amount_out_wei=0))

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake)
    res = _run(_aero_quoter().quote(pair_canonical="WETH/USDC",
                                    size_in_usd=1000.0, direction="buy"))
    assert res.ok is False
    assert res.reason.startswith("quote_unavailable:")


# ----- no aerodrome pool for the pair → fail-closed -------------------------

def test_no_aerodrome_pool_for_pair(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")
    # cbETH/USDC has NO aerodrome venue in the canonical registry.
    res = _run(_aero_quoter().quote(pair_canonical="cbETH/USDC",
                                    size_in_usd=1000.0, direction="buy"))
    assert res.ok is False
    assert res.reason.startswith("no_aerodrome_pool_for_pair:")


# ----- integration with the existing DEXQuoteVerifier (gates NOT bypassed) --

class _StubCaps:
    async def is_gate_3_pass(self, venue_id, base, quote):
        return True, "ok"


def test_integration_verifier_consumes_aerodrome_and_runs_gates(monkeypatch):
    _clear_rpc(monkeypatch)
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", "https://mainnet.base.org")

    # Distinct live-shaped outputs per dex so buy_dex != sell_dex, spread > 0.
    async def fake(self, *, chain, hops, rpc_url=None):
        h = hops[0]; dex = h["dex"]
        out_map = {
            "uniswap_v3": 400_000_000_000_000_000,
            "aerodrome": 402_000_000_000_000_000,
            "aerodrome_slipstream": 405_000_000_000_000_000,
        }
        # For the WETH->USDC (sell) direction the out token is USDC (6dec).
        is_sell = h["token_out"].lower().endswith("da02913")  # USDC addr suffix
        out = out_map[dex] if not is_sell else {"uniswap_v3": 120_000_000,
                                                "aerodrome": 118_000_000,
                                                "aerodrome_slipstream": 121_000_000}[dex]
        return _route_ok(_hop(dex=dex, token_in=h["token_in"], token_out=h["token_out"],
                              amount_in_wei=h["amount_in_wei"], amount_out_wei=out))

    monkeypatch.setattr(execq.QuoterRegistry, "quote_route", fake)

    # Capture the VerificationEvidence to prove backend provenance reaches evidence.
    import arbicore.scanners.dex_arbitrage.verifier as vmod
    orig_build = vmod.build_canonical_from_evidence
    captured = {}

    def _capture(evidence, **kw):
        captured["evidence"] = evidence
        return orig_build(evidence, **kw)
    monkeypatch.setattr(vmod, "build_canonical_from_evidence", _capture)

    verifier = DEXQuoteVerifier(
        quoters=[
            EVMV3Quoter(chain="base", dex="uniswap_v3",
                        source_id="uniswap_v3_quoter_base"),
            EVMV3Quoter(chain="base", dex="aerodrome",
                        source_id="aerodrome_quoter_base"),
        ],
        venue_caps=_StubCaps(),
        config_loader=lambda: {"default_notional_usd": 1000.0,
                               "gate_thresholds": {"default": {
                                   "min_net_spread_after_slip_after_gas_pct": 0.1,
                                   "min_depth_usd": 5000, "min_confidence": 55}}},
    )
    cand = DiscoveryCandidate(
        candidate_id="cand_d36b", opportunity_type=OpportunityType.DEX_ARBITRAGE,
        hint_source="venue_dex_pool:uniswap_v3:base", subject_id="WETH/USDC@base",
        asset="WETH", candidate_venues=["uniswap_v3:base", "aerodrome:base"])
    opp, tag = _run(verifier.verify(cand))

    # Integration proven: the wired quoters were consumed (>=2 viable venues),
    # a canonical row was built from evidence, and the gate pipeline RAN
    # (outcome is confirmed/denied-at-gate — NOT venue-unreadable, NOT error).
    assert tag != VerifiedOutcome.DENIED_VENUE_UNREADABLE
    assert not tag.startswith("error:")
    assert opp is not None
    ev = captured["evidence"]
    aero_legs = [l for l in ev.legs if l.venue_id.startswith("aerodrome:")]
    assert aero_legs, "expected an aerodrome leg in the evidence"
    # backend/pool family is distinguishable in the evidence
    assert aero_legs[0].metadata.get("quote_backend") in (
        "aerodrome_classic", "aerodrome_slipstream")
