"""Regression: partial / reverted-hop flash-loan quotes must FAIL CLOSED and
NEVER fabricate profit, pass Gate 7, or become CONFIRMED.

Reproduces the exact VPS-audit defect (2026-06): a route whose final hop
reverts had its ``final_amount_out_wei`` left denominated in an INTERMEDIATE
token's units (``quote_route`` passes ``amountIn`` through as ``amountOut`` for
a degraded hop). Treating that as the borrow-token output produced absurd
gross profits (~3.6e10%  →  ~$3.6e12 net) that wrongly passed Gate 7 and
CONFIRMED.

Three layers are asserted:
  1. the REAL ``QuoterRegistry.quote_route`` passthrough mechanic that creates
     the intermediate-unit ``final_amount_out_wei`` (documents the defect);
  2. the live quote provider now returns ``None`` for any non-"ok" route;
  3. the verifier denies (``denied:quote_invalid:*``) — never CONFIRMED — for
     partial / reverted-hop / missing-output / malformed-gross quotes, while a
     genuinely valid "ok" quote still CONFIRMS (no over-blocking).

Offline / deterministic. No RPC, no signing, no broadcast.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

from arbicore.discovery import base_pool_registry as reg
from arbicore.execution.quoter import HopQuote, QuoterRegistry
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


# ---------------------------------------------------------------------------
# Layer 1 — the REAL quote_route passthrough that manufactures the defect
# ---------------------------------------------------------------------------

_USDC = "0xUSDC"
_WETH = "0xWETH"
_USDC_IN_WEI = 10_000 * 10 ** 6          # 10,000 USDC (6 decimals)
_WETH_OUT_WEI = 3 * 10 ** 18             # ~3 WETH (18 decimals) — hop-0 output


class _RevertFinalHopBackend:
    """UniV3-shaped backend: hop 0 quotes OK (USDC→WETH), the final hop reverts
    (WETH→USDC). Mirrors a route whose last leg cannot be priced on-chain."""

    dex = "uniswap_v3"

    async def quote_hop(self, *, hop_index, chain, token_in, token_out,
                        amount_in_wei, hop_spec, rpc_url):
        if hop_index == 0:
            return HopQuote(
                hop_index=0, dex="uniswap_v3", token_in=token_in,
                token_out=token_out, amount_in_wei=amount_in_wei,
                amount_out_wei=_WETH_OUT_WEI, sqrt_price_x96_after=None,
                gas_estimate_units=150_000, price_impact_bps=None,
                quoter_contract="0xquoter", rpc_host="testhost",
                block_number=100, status="ok", error=None, generated_at="t0")
        return HopQuote(
            hop_index=hop_index, dex="uniswap_v3", token_in=token_in,
            token_out=token_out, amount_in_wei=amount_in_wei,
            amount_out_wei=0, sqrt_price_x96_after=None,
            gas_estimate_units=None, price_impact_bps=None,
            quoter_contract="0xquoter", rpc_host="testhost",
            block_number=100, status="fallback:revert",
            error="execution reverted", generated_at="t0")


def test_real_quote_route_passthrough_creates_intermediate_unit_output():
    os.environ["ARBICORE_RPC_URL"] = "http://localhost:8545"
    registry = QuoterRegistry(backends=[_RevertFinalHopBackend()],
                              cache_ttl_s=0.0)
    hops = [
        {"dex": "uniswap_v3", "token_in": _USDC, "token_out": _WETH,
         "amount_in_wei": _USDC_IN_WEI},
        {"dex": "uniswap_v3", "token_in": _WETH, "token_out": _USDC},
    ]
    rq = _run(registry.quote_route(chain="base", hops=hops))

    # The reverted final hop was passed through: the "final output" is really
    # the INTERMEDIATE token amount (WETH wei, 18 decimals), not USDC.
    assert rq.status == "partial"
    assert rq.final_amount_out_wei == _WETH_OUT_WEI

    # The (now-suppressed) naive gross calc would have been astronomically
    # large — this is exactly the ~3.6e10% class of false profit.
    naive_gross_pct = 100.0 * (rq.final_amount_out_wei - _USDC_IN_WEI) \
        / _USDC_IN_WEI
    assert naive_gross_pct > 1_000_000.0


# ---------------------------------------------------------------------------
# Layer 2 — the live quote provider fails closed on any non-"ok" route
# ---------------------------------------------------------------------------

def _meta():
    return {"borrow_token": "WETH", "route_pools": ["p1", "p2"],
            "cycle_token_path": ["WETH", "USDC", "WETH"]}


class _FakeRegistry:
    def __init__(self, rq):
        self._rq = rq

    async def quote_route(self, *, chain, hops):
        return self._rq


def _rq(status, *, hop_status="ok", final_out=int(1.05e16)):
    hop = SimpleNamespace(dex="uniswap_v3", status=hop_status, block_number=1)
    return SimpleNamespace(status=status, final_amount_out_wei=final_out,
                           aggregate_gas_estimate_units=300_000,
                           hops=[hop, hop])


def test_provider_fail_closed_on_partial():
    prov = make_live_quote_provider(_FakeRegistry(_rq("partial")))
    assert _run(prov(_meta(), 10_000.0)) is None


def test_provider_fail_closed_on_reverted_hop_even_if_route_status_ok():
    # Defense-in-depth: a degraded hop with an (inconsistent) "ok" route status
    prov = make_live_quote_provider(
        _FakeRegistry(_rq("ok", hop_status="fallback:revert")))
    assert _run(prov(_meta(), 10_000.0)) is None


def test_provider_fail_closed_on_non_cyclic_path():
    prov = make_live_quote_provider(_FakeRegistry(_rq("ok")))
    bad = {"borrow_token": "WETH", "route_pools": ["p1", "p2"],
           "cycle_token_path": ["WETH", "USDC", "DAI"]}   # not a closed cycle
    assert _run(prov(bad, 10_000.0)) is None


def test_provider_fail_closed_on_zero_final_out():
    prov = make_live_quote_provider(_FakeRegistry(_rq("ok", final_out=0)))
    assert _run(prov(_meta(), 10_000.0)) is None


def test_provider_still_accepts_valid_ok_route():
    prov = make_live_quote_provider(_FakeRegistry(_rq("ok")))
    facts = _run(prov(_meta(), 10_000.0))
    assert facts is not None and facts["route_quote_status"] == "ok"


# ---------------------------------------------------------------------------
# Layer 3 — the verifier NEVER CONFIRMS an invalid quote (canonical boundary)
# ---------------------------------------------------------------------------

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
            "route_dex_protocols": ["uniswap_v3", "uniswap_v3"],
            "hop_count": 2}


def _facts(*, gross_pct, route_status="ok", hop_status=None):
    leg = {"venue_id": "uniswap_v3:base", "source_id": "uniswap_v3_quoter_base",
           "fee_bps": 5, "depth_usd": 500_000.0, "dex_protocol": "uniswap_v3"}
    if hop_status is not None:
        leg = {**leg, "status": hop_status}
    facts = {"hop_legs": [dict(leg), dict(leg)],
             "tx_gas_units": 250_000, "min_pool_tvl_usd_in_route": 500_000.0,
             "tvl_provenance": "onchain_reserves",
             "route_quote_status": route_status,
             "verified_at_ts": 123.0, "quote_block": 999}
    if gross_pct is not None:
        facts["gross_profit_pct"] = gross_pct
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


def _verify(facts):
    captured = []

    async def sink(b):
        captured.append(b)

    v = _mk_verifier(facts)
    v.evidence_sink = sink
    opp, outcome = _run(v.verify(_candidate()))
    return opp, outcome, (captured[0] if captured else None)


def _candidate():
    return DiscoveryCandidate(
        candidate_id="cand-partial", hint_source="test_source",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id="WETH-USDC", asset="WETH", hint_metric=_hm())


def test_verifier_denies_partial_with_absurd_gross_never_confirms():
    # The exact defect payload: partial route + ~3.6e10% gross.
    opp, outcome, bundle = _verify(
        _facts(gross_pct=35_983_627_573.0, route_status="partial"))
    assert opp is None, "partial quote must never produce a canonical opp"
    assert outcome.startswith(
        VerifiedOutcome.DENIED_QUOTE_INVALID_PREFIX)
    assert "route_status:partial" in outcome
    # Gate 7 must never have been evaluated (denied before economics), so the
    # absurd profit can never have 'passed' the atomic-profit floor.
    assert bundle["gates"]["gate_7"]["status"] == "NOT_EVALUATED"
    assert bundle["verification_status"] == "DENIED"


def test_verifier_denies_reverted_hop():
    opp, outcome, _b = _verify(
        _facts(gross_pct=5.0, route_status="ok", hop_status="fallback:revert"))
    assert opp is None
    assert outcome.startswith(VerifiedOutcome.DENIED_QUOTE_INVALID_PREFIX)
    assert "hop_0_status:fallback:revert" in outcome


def test_verifier_denies_missing_gross():
    opp, outcome, _b = _verify(_facts(gross_pct=None, route_status="ok"))
    assert opp is None
    assert outcome.endswith("gross_profit_missing")


def test_verifier_denies_malformed_gross():
    opp, outcome, _b = _verify(_facts(gross_pct="not-a-number"))
    assert opp is None
    assert outcome.endswith("gross_profit_malformed")


def test_verifier_denies_nonfinite_gross():
    opp, outcome, _b = _verify(_facts(gross_pct=float("inf")))
    assert opp is None
    assert outcome.endswith("gross_profit_nonfinite")


def test_verifier_still_confirms_valid_ok_quote():
    # Sanity: the fix must NOT over-block a genuinely valid, profitable quote.
    opp, outcome, bundle = _verify(_facts(gross_pct=3.0, route_status="ok"))
    assert opp is not None
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    assert bundle["gates"]["gate_7"]["status"] == "PASS"
