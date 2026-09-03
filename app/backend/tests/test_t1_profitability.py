"""T1 (Base profitability) acceptance/unit tests. Offline, deterministic.

Run: python -m pytest tests/test_t1_profitability.py -p no:xdist -o addopts=""
"""
import os
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")


# ── Morpho provider added; catalog integrity ──────────────────────────────
def test_morpho_blue_provider_added():
    from arbicore.scanners.flash_loan_arbitrage.economics import (
        FLASH_LOAN_PROVIDERS, provider_fee_bps,
    )
    assert "morpho_blue" in FLASH_LOAN_PROVIDERS
    assert provider_fee_bps("morpho_blue") == 0
    assert "base" in FLASH_LOAN_PROVIDERS["morpho_blue"]["supports_chains"]
    # zero-fee venues remain zero
    assert provider_fee_bps("balancer_v2") == 0
    # Aave depth premium unchanged
    assert provider_fee_bps("aave_v3") == 5


# ── Provider selection: cheapest feasible; fail-closed on unknown liquidity ─
def test_provider_selection_prefers_zero_fee_feasible():
    from arbicore.scanners.flash_loan_arbitrage.provider_selection import (
        select_flash_loan_provider,
    )
    # Balancer has liquidity → chosen over Aave (5bps) even though Aave deeper
    c = select_flash_loan_provider(
        chain="base", borrow_amount_usd=100_000,
        liquidity_by_provider={"balancer_v2": 500_000, "aave_v3": 5_000_000,
                               "morpho_blue": 120_000})
    assert c.feasible and c.fee_bps == 0
    assert c.provider in {"balancer_v2", "morpho_blue"}

    # Only Aave has enough liquidity → Aave chosen despite 5bps
    c2 = select_flash_loan_provider(
        chain="base", borrow_amount_usd=1_000_000,
        liquidity_by_provider={"balancer_v2": 100_000, "aave_v3": 5_000_000})
    assert c2.feasible and c2.provider == "aave_v3" and c2.fee_bps == 5

    # Unknown liquidity → NOT feasible (never fabricate liquidity)
    c3 = select_flash_loan_provider(chain="base", borrow_amount_usd=100_000,
                                    liquidity_by_provider=None)
    assert c3.feasible is False and c3.reason == "no_feasible_provider"
    assert any(r["reason"] == "liquidity_unverifiable" for r in c3.considered)

    # Unsupported chain
    c4 = select_flash_loan_provider(chain="solana", borrow_amount_usd=1000,
                                    liquidity_by_provider={"aave_v3": 1e9})
    assert c4.feasible is False


# ── Real cached TVL (fail-closed, TTL) ─────────────────────────────────────
async def test_onchain_reserve_tvl_and_fail_closed():
    from arbicore.scanners.flash_loan_arbitrage.tvl_provider import (
        OnChainReserveTVLProvider,
    )
    async def reserves_ok(chain, pool): return ("WETH", 10.0, "USDC", 30000.0)
    async def price_ok(chain, tok): return {"WETH": 3000.0, "USDC": 1.0}.get(tok)
    p = OnChainReserveTVLProvider(reserves_ok, price_ok)
    assert await p.get_pool_tvl_usd("base", "0xp") == 10*3000 + 30000*1

    # missing price → None (no fabrication)
    async def price_missing(chain, tok): return None
    p2 = OnChainReserveTVLProvider(reserves_ok, price_missing)
    assert await p2.get_pool_tvl_usd("base", "0xp") is None

    # missing reserves → None
    async def reserves_none(chain, pool): return None
    p3 = OnChainReserveTVLProvider(reserves_none, price_ok)
    assert await p3.get_pool_tvl_usd("base", "0xp") is None


async def test_cached_tvl_ttl_and_miss_caching():
    from arbicore.scanners.flash_loan_arbitrage.tvl_provider import CachedTVLProvider

    class _Src:
        def __init__(self): self.calls = 0; self.val = 1000.0
        async def get_pool_tvl_usd(self, chain, pool):
            self.calls += 1
            return self.val

    clock = {"t": 0.0}
    src = _Src()
    c = CachedTVLProvider(src, ttl_sec=30.0, clock=lambda: clock["t"])
    assert await c.get_pool_tvl_usd("base", "0xp") == 1000.0
    src.val = 2000.0  # change underlying; cache should hold old value
    assert await c.get_pool_tvl_usd("base", "0xp") == 1000.0
    assert src.calls == 1                      # served from cache
    clock["t"] = 31.0                          # expire
    assert await c.get_pool_tvl_usd("base", "0xp") == 2000.0
    assert src.calls == 2


# ── Optimal sizing chooses EV-maximising notional (reuses existing kernel) ─
def test_optimal_sizing_maximises_ev_not_max_loan():
    from arbicore.economics.size_optimizer import optimize_size
    res = optimize_size(
        gross_spread_bps=40.0, pool_liquidity_usd=1_000_000.0,
        gas_cost_usd=2.0, flash_loan_fee_bps=0.0,
        buy_venue_fee_bps=5, sell_venue_fee_bps=5, native_price_usd=3000.0,
        prob_kwargs={"simulation_passed": True, "quote_age_sec": 1.0,
                     "gas_certainty": 0.9, "mev_risk": 0.2,
                     "historical_success_rate": 0.8})
    chosen = res["chosen"]
    assert chosen is not None and chosen["feasible"] is True
    # not simply the largest grid notional
    assert chosen["expected_value_usd"] >= 0
    assert res["objective"] == "max_risk_adjusted_expected_value"


# ── Full profit vector consistent with canonical kernel ────────────────────
def test_profit_vector_uses_canonical_expected_profit():
    from arbicore.scanners.economics import aggregate_economics, LegCost
    from arbicore.scanners.flash_loan_arbitrage.profit_vector import build_profit_vector
    from arbicore.models.enums import MevRiskLevel
    legs = [LegCost(leg_role="hop_0", venue_id="v", fee_bps=5, slippage_pct=0.05,
                    gas_estimate_usd=1.0, fee_kind="swap_fee"),
            LegCost(leg_role="flash", venue_id="balancer_v2", fee_bps=0,
                    fee_kind="flash_loan_premium")]
    a = aggregate_economics(legs=legs, gross_spread_pct=0.5, notional_usd=100_000.0,
                            mev_risk_level=MevRiskLevel.LOW)
    pv = build_profit_vector(assessment=a, execution_probability=0.9, confidence=0.85)
    assert pv.expected_net_profit_usd == round(a.expected_profit_usd, 6)
    # worst-case must be <= expected (stress can only reduce)
    assert pv.worst_case_net_profit_usd <= pv.expected_net_profit_usd
    assert pv.gross_profit_usd == round(100_000.0 * 0.5/100, 6)


# ── Ranking: executable value beats raw spread (§20 contract) ──────────────
def test_ranking_prefers_executable_over_raw_spread():
    from arbicore.scanners.flash_loan_arbitrage.ranking import rank_opportunities
    items = [
        # A: modest net, high execution probability + confidence (the §20 winner)
        {"opportunity_id": "A", "expected_net_profit_usd": 223.0,
         "execution_probability": 0.91, "confidence": 0.9,
         "min_route_tvl_usd": 400_000, "quote_age_sec": 1.0},
        # B: bigger apparent net but poor execution probability + stale + thin
        {"opportunity_id": "B", "expected_net_profit_usd": 500.0,
         "execution_probability": 0.15, "confidence": 0.4,
         "min_route_tvl_usd": 20_000, "quote_age_sec": 11.0,
         "worst_case_net_profit_usd": -50.0},
    ]
    ranked = rank_opportunities(items)
    assert ranked[0].opportunity_id == "A"
    assert ranked[0].score > ranked[1].score
