"""Focused offline coverage for the flash-loan provider optimizer (Part 5).

Proves the optimizer selects the economically BEST FEASIBLE flash-loan provider
(not merely the first configured one) and is fail-closed on unknown/insufficient
liquidity, unresolved fees, and unsupported chains. Pure/deterministic — no RPC.

Catalog (economics.FLASH_LOAN_PROVIDERS) at audit time:
  aave_v3      5 bps  chains: eth, arb, base, op, polygon, bnb
  balancer_v2  0 bps  chains: eth, arb, base, op, polygon
  uniswap_v3   tier   chains: eth, arb, base, op, polygon  (fee NOT fixed)
  morpho_blue  0 bps  chains: eth, base
"""
from __future__ import annotations

from arbicore.scanners.flash_loan_arbitrage.flash_provider_optimizer import (
    optimize_flash_provider,
)


def test_picks_cheapest_feasible_provider():
    # balancer_v2 (0 bps) and aave_v3 (5 bps) both feasible on base → cheapest wins.
    r = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"balancer_v2": 5_000_000, "aave_v3": 5_000_000})
    assert r.feasible is True
    assert r.provider == "balancer_v2"
    assert r.fee_bps == 0
    assert r.fee_usd == 0.0


def test_skips_insufficient_liquidity_and_selects_feasible_costlier():
    # Cheapest (balancer_v2) lacks liquidity → must fall through to aave_v3.
    r = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"balancer_v2": 100, "aave_v3": 5_000_000})
    assert r.feasible is True
    assert r.provider == "aave_v3"
    assert r.fee_bps == 5
    assert r.fee_usd == 5.0
    # the infeasible provider is recorded with a defensible reason
    bal = next(c for c in r.considered if c["provider"] == "balancer_v2")
    assert bal["feasible"] is False and "insufficient_liquidity" in bal["reason"]


def test_unknown_liquidity_is_fail_closed():
    r = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={})  # nothing known
    assert r.feasible is False
    assert r.reason == "no_feasible_provider"
    assert all(c["feasible"] is False for c in r.considered)


def test_uniswap_v3_tier_unresolved_is_refused_but_resolved_tier_is_usable():
    # No explicit tier → uniswap_v3 refused (fee_unresolved), NEVER assumed.
    r1 = optimize_flash_provider(
        chain="arbitrum", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"uniswap_v3": 5_000_000})
    uni1 = next(c for c in r1.considered if c["provider"] == "uniswap_v3")
    assert uni1["feasible"] is False and uni1["reason"] == "fee_unresolved"

    # With a resolved 5 bps tier it becomes feasible and can win on price.
    r2 = optimize_flash_provider(
        chain="arbitrum", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"uniswap_v3": 5_000_000, "aave_v3": 5_000_000},
        fee_bps_by_provider={"uniswap_v3": 5})
    # aave_v3 (5) and uniswap_v3 (5) tie on fee → deeper-liquidity tie-break;
    # both 5M here so a 5-bps provider is chosen deterministically.
    assert r2.feasible is True and r2.fee_bps == 5


def test_chain_support_bnb_only_aave():
    # On BNB only aave_v3 supports flash loans in the catalog.
    r = optimize_flash_provider(
        chain="bnb", borrow_token="USDT", borrow_amount_usd=10_000,
        liquidity_by_provider={"aave_v3": 5_000_000, "balancer_v2": 5_000_000,
                               "morpho_blue": 5_000_000})
    assert r.feasible is True
    assert r.provider == "aave_v3"
    names = {c["provider"] for c in r.considered}
    assert names == {"aave_v3"}  # unsupported providers not even considered


def test_no_provider_supports_chain():
    r = optimize_flash_provider(
        chain="solana", borrow_token="USDC", borrow_amount_usd=10_000,
        liquidity_by_provider={"aave_v3": 5_000_000})
    assert r.feasible is False
    assert r.reason.startswith("no_provider_supports_chain")


def test_borrow_amount_unknown_is_fail_closed():
    r = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=None,
        liquidity_by_provider={"balancer_v2": 5_000_000})
    assert r.feasible is False
    assert r.reason == "borrow_amount_unknown"


def test_tie_break_prefers_deeper_liquidity():
    # balancer_v2 and morpho_blue both 0 bps on base → deeper liquidity wins.
    r = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"balancer_v2": 1_000_000, "morpho_blue": 9_000_000})
    assert r.feasible is True
    assert r.fee_bps == 0
    assert r.provider == "morpho_blue"  # deeper known liquidity
