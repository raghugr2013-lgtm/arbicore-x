"""H05 remediation — ExactSizeBorrowSizer.size(...) must FAIL CLOSED (return
None) for EVERY exception, including the two previously-escaping direct-sizer
paths flagged by Cursor certification of cc3a922:

  1. the injected decimals resolver raising, and
  2. an unsafe USD->wei conversion raising (e.g. OverflowError from
     math.floor(inf) when amount_token * 10**decimals overflows to inf).

These tests assert the sizer itself returns None (not merely that the canonical
provider catches the exception), and confirm existing fail-closed behavior is
preserved.
"""
import math

import pytest

from arbicore.scanners.flash_loan_arbitrage.exact_size_sizer import (
    ExactSizeBorrowSizer,
)


def _const_price(value):
    async def _price(chain, token):
        return value
    return _price


# ── Path #1: decimals resolver raises → None (previously escaped) ─────────────
@pytest.mark.asyncio
async def test_decimals_resolver_exception_fails_closed():
    def _boom_decimals(chain, token):
        raise RuntimeError("registry blew up")

    sizer = ExactSizeBorrowSizer(_const_price(2000.0), _boom_decimals)
    # Must not raise; must return None.
    assert await sizer.size("base", "WETH", 1000.0) is None


# ── Path #2: USD->wei conversion overflow → None (previously escaped) ─────────
@pytest.mark.asyncio
async def test_conversion_overflow_fails_closed():
    # Sanity: reproduce the raw OverflowError the sizer previously let escape.
    amount_token = 1e280           # finite, > 0 (passes the isfinite/>0 guard)
    with pytest.raises(OverflowError):
        int(math.floor(amount_token * (10 ** 36)))

    # price=1.0 and usd=1e280 -> amount_token=1e280; *10**36 -> inf ->
    # math.floor(inf) raises OverflowError inside size(). Must return None.
    sizer = ExactSizeBorrowSizer(_const_price(1.0), lambda c, t: 36)
    assert await sizer.size("base", "WETH", 1e280) is None


# ── Preserved behavior (regression) ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_preserved_failclosed_paths():
    good = ExactSizeBorrowSizer(_const_price(2000.0), lambda c, t: 18)
    # unknown chain/token
    assert await good.size("", "WETH", 1000.0) is None
    assert await good.size("base", "", 1000.0) is None
    # non-finite / non-positive usd
    assert await good.size("base", "WETH", float("nan")) is None
    assert await good.size("base", "WETH", 0.0) is None
    assert await good.size("base", "WETH", -5.0) is None
    # unknown decimals
    assert await ExactSizeBorrowSizer(_const_price(2000.0), lambda c, t: None).size(
        "base", "WETH", 1000.0) is None
    # missing / zero / negative / non-finite price
    for bad in (None, 0.0, -1.0, float("inf")):
        assert await ExactSizeBorrowSizer(_const_price(bad), lambda c, t: 18).size(
            "base", "WETH", 1000.0) is None
    # floor-to-zero (tiny usd vs huge unit price) -> None, never rounded up
    assert await ExactSizeBorrowSizer(_const_price(1e30), lambda c, t: 6).size(
        "base", "USDC", 1e-9) is None


@pytest.mark.asyncio
async def test_happy_path_still_exact():
    # 1000 USD / 2000 USD-per-WETH * 1e18 = 5e17 wei (exact, floor).
    sizer = ExactSizeBorrowSizer(_const_price(2000.0), lambda c, t: 18)
    assert await sizer.size("base", "WETH", 1000.0) == 5 * 10 ** 17
