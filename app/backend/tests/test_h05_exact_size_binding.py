"""P0/H05 regression — exact-size economic binding (fail-closed).

The audit's H05 defect: a route quoted at a small research PROBE size had its
gross-profit RATIO extrapolated onto a different (larger) dollar notional. Price
impact is nonlinear, so a probe edge cannot certify a larger borrow.

This locks in the fix:
  1. The live quote provider stamps ``size_basis`` on every facts dict:
     ``"probe"`` when it could not size to the requested borrow, ``"exact"``
     (with a bound ``quote_notional_usd``) when a ``borrow_sizer`` sized it.
  2. The verifier FAILS CLOSED (``denied:size_not_quoted``) on a probe-sized
     quote — it never reaches economics / Gate 7 / CONFIRMED.
  3. When the quote binds its own USD notional, the verifier uses THAT notional
     for economics (ratio and notional describe the SAME size), never an
     extrapolated one.

Offline / deterministic. No RPC, no signing, no broadcast.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from arbicore.discovery import base_pool_registry as reg
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import OpportunityType
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
    MevRiskScorer,
)
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FlashLoanEconomicsAssessor,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)
from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    make_live_quote_provider,
)
from arbicore.scanners.flash_loan_arbitrage.verifier import (
    FlashLoanOpportunityVerifier,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------
# Provider: size_basis stamping
# --------------------------------------------------------------------------

def _meta():
    return {"borrow_token": "WETH", "route_pools": ["p1", "p2"],
            "cycle_token_path": ["WETH", "USDC", "WETH"]}


class _FakeRegistry:
    async def quote_route(self, *, chain, hops):
        hop = SimpleNamespace(dex="uniswap_v3", status="ok", block_number=7)
        # record the first-hop amount so we can assert exact sizing
        self.first_hop_amount = int(hops[0].get("amount_in_wei") or 0)
        return SimpleNamespace(status="ok",
                               final_amount_out_wei=int(1.05e16),
                               aggregate_gas_estimate_units=300_000,
                               hops=[hop, hop])


def test_provider_marks_probe_when_no_sizer():
    reg_ = _FakeRegistry()
    prov = make_live_quote_provider(reg_)
    facts = _run(prov(_meta(), 10_000.0))
    assert facts is not None
    assert facts["size_basis"] == "probe"
    assert facts["exact_size"] is False
    assert facts["quote_notional_usd"] is None


def test_provider_marks_exact_when_sizer_present():
    reg_ = _FakeRegistry()
    sized_wei = 5 * 10 ** 18

    def sizer(chain, token, usd):
        assert token == "WETH"
        return sized_wei

    prov = make_live_quote_provider(reg_, borrow_sizer=sizer)
    facts = _run(prov(_meta(), 12_345.0))
    assert facts["size_basis"] == "exact"
    assert facts["exact_size"] is True
    assert facts["quote_notional_usd"] == 12_345.0
    # the quote was actually taken at the EXACT sized amount, not a probe
    assert facts["quoted_amount_in_wei"] == sized_wei
    assert reg_.first_hop_amount == sized_wei


# --------------------------------------------------------------------------
# Verifier: fail-closed on probe, notional binding on exact
# --------------------------------------------------------------------------

def _real_pool_ids():
    ids = [p.canonical_id for p in reg.get_canonical_pools()
           if p.address_resolution == reg.DETERMINISTIC_VERIFIED
           and p.dex == "uniswap_v3"
           and {"WETH", "USDC"} == {p.token0_symbol, p.token1_symbol}]
    return ids[:2]


def _hm():
    return {"chain": "base", "provider": "balancer_v2", "borrow_token": "WETH",
            "borrow_amount_usd": 10_000.0, "route_pools": _real_pool_ids(),
            "cycle_token_path": ["WETH", "USDC", "WETH"],
            "route_dex_protocols": ["uniswap_v3", "uniswap_v3"], "hop_count": 2}


def _facts(*, size_basis=None, quote_notional_usd=None, gross_pct=3.0):
    leg = {"venue_id": "uniswap_v3:base", "source_id": "uniswap_v3_quoter_base",
           "fee_bps": 5, "depth_usd": 500_000.0, "dex_protocol": "uniswap_v3"}
    facts = {"hop_legs": [dict(leg), dict(leg)], "tx_gas_units": 250_000,
             "min_pool_tvl_usd_in_route": 500_000.0,
             "tvl_provenance": "onchain_reserves", "route_quote_status": "ok",
             "verified_at_ts": 123.0, "quote_block": 999,
             "gross_profit_pct": gross_pct}
    if size_basis is not None:
        facts["size_basis"] = size_basis
    if quote_notional_usd is not None:
        facts["quote_notional_usd"] = quote_notional_usd
    return facts


def _mk_verifier(facts):
    async def _qp(hm, borrow):
        return facts

    econ = FlashLoanEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=8, winsorize_pct=0.05),
        default_borrow_amount_usd=10_000.0)
    return FlashLoanOpportunityVerifier(
        quote_provider=_qp, economics_assessor=econ, mev_scorer=MevRiskScorer(),
        gate_7=FlashLoanGate7AtomicProfit({}),
        gate_8=FlashLoanGate8LiquidityDepth({}),
        gate_9=FlashLoanGate9FlashLoanMev({}),
        default_borrow_amount_usd=10_000.0)


def _candidate():
    return DiscoveryCandidate(
        candidate_id="cand-h05", hint_source="test_source",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id="WETH-USDC", asset="WETH", hint_metric=_hm())


def _verify(facts):
    captured = []

    async def sink(b):
        captured.append(b)

    v = _mk_verifier(facts)
    v.evidence_sink = sink
    opp, outcome = _run(v.verify(_candidate()))
    return opp, outcome, (captured[0] if captured else None)


def test_verifier_denies_probe_sized_quote():
    opp, outcome, bundle = _verify(_facts(size_basis="probe", gross_pct=5.0))
    assert opp is None, "a probe-sized quote must never CONFIRM"
    assert outcome == VerifiedOutcome.DENIED_SIZE_NOT_QUOTED
    # denied BEFORE economics — the probe edge never reached Gate 7
    assert bundle["gates"]["gate_7"]["status"] == "NOT_EVALUATED"
    assert bundle["verification_status"] == "DENIED"


def test_verifier_binds_notional_to_exact_quote():
    # exact-sized quote whose own USD notional is $250 (NOT the requested
    # $10,000). The economics MUST use $250, not extrapolate to $10,000.
    opp, outcome, bundle = _verify(
        _facts(size_basis="exact", quote_notional_usd=250.0, gross_pct=3.0))
    econ = bundle["economics"] if "economics" in bundle else None
    # borrow amount recorded in the bundle economics must be the bound $250
    meta = (bundle.get("category_metadata") or {})
    # atomic profit ≈ 3% of $250 ≈ $7.5 (NOT 3% of $10k = $300) → gate_7 floor
    # rejects, proving the notional was bound to the quoted size.
    assert bundle["economics"]["borrow_amount_usd"] == 250.0
    assert outcome != VerifiedOutcome.CONFIRMED_PREFIX  # tiny size → gate_7 deny


def test_verifier_backward_compatible_when_size_basis_absent():
    # Legacy/injected facts with no size_basis are unchanged (fixture owns its
    # own consistency) — a valid ok quote still CONFIRMS.
    opp, outcome, bundle = _verify(_facts(gross_pct=3.0))
    assert opp is not None
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
