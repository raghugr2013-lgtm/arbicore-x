"""H05 — exact USD→wei borrow sizer + evidence-based certification.

Covers TRACK 1:
  * build_borrow_sizer converts USD notional -> exact borrow-token wei from a
    REAL price + registry-verified decimals, and FAILS CLOSED on every
    missing/invalid input (no fallback pricing, no assumed decimals, chain-scoped).
  * make_live_quote_provider awaits an ASYNC sizer and stamps size_basis="exact"
    + binds quote_notional_usd to the SAME requested notional; with no/None sizer
    it stays size_basis="probe" (verifier then denies DENIED_SIZE_NOT_QUOTED).
  * BOTH composition quote-provider paths wire the sizer (static AST check).
  * vps_harness H05 certification: env flags ALONE can NEVER produce PASS; a real
    exact-size quote fact is required; probe/missing/malformed facts never PASS.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from arbicore.searcher.price_feed import build_borrow_sizer
from arbicore.certification import vps_harness as H

_REPO = next(p for p in Path(__file__).resolve().parents
             if (p / "app/backend/arbicore/runtime/composition.py").is_file())
_COMPOSITION = _REPO / "app/backend/arbicore/runtime/composition.py"


class _FakeFeed:
    """Minimal stand-in for OnChainUsdPriceFeed: async price + verified decimals."""
    def __init__(self, prices, decimals):
        self._prices = prices          # symbol -> USD price (or None)
        self._decs = decimals          # symbol -> int decimals

    def decimals_for(self, token):
        return self._decs.get(str(token).upper())

    async def price_source(self, token):
        return self._prices.get(str(token).upper())


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ───────────────────────── sizer: exact conversion ──────────────────────────
def test_sizer_converts_usd_to_exact_wei():
    feed = _FakeFeed({"USDC": 1.0, "WETH": 2000.0}, {"USDC": 6, "WETH": 18})
    sizer = build_borrow_sizer(feed, chain_scope="base")
    # 5000 USDC @ $1, 6 decimals -> 5000 * 1e6
    assert _run(sizer("base", "USDC", 5000.0)) == 5000 * 10**6
    # 5000 USD of WETH @ $2000, 18 decimals -> 2.5e18
    assert _run(sizer("base", "WETH", 5000.0)) == int(5000 / 2000.0 * 10**18)


def test_sizer_returns_none_when_price_feed_missing():
    assert build_borrow_sizer(None) is None


@pytest.mark.parametrize("chain", ["ethereum", "arbitrum", "BASE ", "polygon", ""])
def test_sizer_is_chain_scoped_no_foreign_sizing(chain):
    feed = _FakeFeed({"USDC": 1.0}, {"USDC": 6})
    sizer = build_borrow_sizer(feed, chain_scope="base")
    assert _run(sizer(chain, "USDC", 1000.0)) is None  # only exact "base" sizes


def test_sizer_fails_closed_on_missing_price():
    feed = _FakeFeed({"USDC": None}, {"USDC": 6})
    sizer = build_borrow_sizer(feed, chain_scope="base")
    assert _run(sizer("base", "USDC", 1000.0)) is None


def test_sizer_fails_closed_on_nonpositive_price():
    feed = _FakeFeed({"USDC": 0.0}, {"USDC": 6})
    sizer = build_borrow_sizer(feed, chain_scope="base")
    assert _run(sizer("base", "USDC", 1000.0)) is None


def test_sizer_fails_closed_on_unknown_decimals():
    feed = _FakeFeed({"XYZ": 1.0}, {})   # no decimals -> never assume 18
    sizer = build_borrow_sizer(feed, chain_scope="base")
    assert _run(sizer("base", "XYZ", 1000.0)) is None


@pytest.mark.parametrize("usd", [0.0, -100.0])
def test_sizer_fails_closed_on_nonpositive_notional(usd):
    feed = _FakeFeed({"USDC": 1.0}, {"USDC": 6})
    sizer = build_borrow_sizer(feed, chain_scope="base")
    assert _run(sizer("base", "USDC", usd)) is None


def test_sizer_fails_closed_on_empty_token():
    feed = _FakeFeed({"USDC": 1.0}, {"USDC": 6})
    sizer = build_borrow_sizer(feed, chain_scope="base")
    assert _run(sizer("base", "", 1000.0)) is None


# ─────────────── provider stamps exact vs probe (async sizer) ────────────────
def _mk_base_plan():
    from types import SimpleNamespace as NS
    p = NS(dex="uniswap_v3", token_in="USDC", token_out="WETH", fee=500,
           tick_spacing=None, stable=None, tvl_key="k0", tvl_addr=None, fee_bps=5)
    return [p], ["USDC", "WETH", "USDC"], 111   # probe amount = 111 wei


class _FakeRegistry:
    def __init__(self, final_out):
        self._out = final_out

    async def quote_route(self, chain, hops):
        from types import SimpleNamespace as NS
        return NS(status="ok",
                  hops=[NS(status="ok", dex="uniswap_v3", block_number=100)],
                  final_amount_out_wei=self._out,
                  aggregate_gas_estimate_units=150000)


def test_provider_awaits_async_sizer_and_binds_exact_notional(monkeypatch):
    from arbicore.scanners.flash_loan_arbitrage import live_quote_provider as L
    monkeypatch.setattr(L, "_plan_base", lambda hm: _mk_base_plan())
    feed = _FakeFeed({"USDC": 1.0}, {"USDC": 6})
    sizer = build_borrow_sizer(feed, chain_scope="base")            # async sizer
    provider = L.make_live_quote_provider(
        _FakeRegistry(final_out=5001 * 10**6), borrow_sizer=sizer)
    facts = _run(provider({"chain": "base", "borrow_token": "USDC"}, 5000.0))
    assert facts is not None
    assert facts["size_basis"] == "exact"
    assert facts["exact_size"] is True
    assert facts["quote_notional_usd"] == 5000.0
    assert facts["quoted_amount_in_wei"] == 5000 * 10**6   # EXACT size, not probe
    assert facts["borrow_token"] == "USDC"


def test_provider_stays_probe_without_sizer(monkeypatch):
    from arbicore.scanners.flash_loan_arbitrage import live_quote_provider as L
    monkeypatch.setattr(L, "_plan_base", lambda hm: _mk_base_plan())
    provider = L.make_live_quote_provider(_FakeRegistry(final_out=222))
    facts = _run(provider({"chain": "base", "borrow_token": "USDC"}, 5000.0))
    assert facts is not None
    assert facts["size_basis"] == "probe"
    assert facts["exact_size"] is False
    assert facts["quote_notional_usd"] is None
    assert facts["quoted_amount_in_wei"] == 111             # untouched probe size


# ─────────── both composition sites actually wire the sizer (static) ─────────
def _call_sites_with_sizer():
    tree = ast.parse(_COMPOSITION.read_text())
    hits = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "make_live_quote_provider"):
            continue
        if any(kw.arg == "borrow_sizer" for kw in node.keywords):
            hits += 1
    return hits


def test_both_quote_provider_paths_wire_borrow_sizer():
    # build_controlled_live_safety + _wire_canonical_flash_loan_scanner
    assert _call_sites_with_sizer() == 2


# ─────────────── H05 certification: flags alone can NEVER PASS ───────────────
_EXACT_FACT = {"size_basis": "exact", "exact_size": True,
               "quote_notional_usd": 5000.0, "quoted_amount_in_wei": 5000 * 10**6,
               "borrow_token": "USDC", "chain": "base", "quote_block": 123}
_PROBE_FACT = {"size_basis": "probe", "exact_size": False,
               "quote_notional_usd": 0.0, "quoted_amount_in_wei": 0,
               "borrow_token": "USDC"}


def test_classify_h05_flags_only_never_pass():
    # Both flags on but NO exact fact -> BLOCKED, never PASS.
    assert H.classify_h05(None, price_feed_enabled=True,
                          borrow_sizer_enabled=True) == H.BLOCKED
    # Probe fact + flags -> still BLOCKED.
    assert H.classify_h05(_PROBE_FACT, price_feed_enabled=True,
                          borrow_sizer_enabled=True) == H.BLOCKED


def test_classify_h05_not_configured_without_flags():
    assert H.classify_h05(None, price_feed_enabled=False,
                          borrow_sizer_enabled=False) == H.NOT_CONFIGURED


def test_classify_h05_pass_only_with_real_exact_fact():
    assert H.classify_h05(_EXACT_FACT, price_feed_enabled=True,
                          borrow_sizer_enabled=True) == H.PASS


def test_check_h05_sizer_env_flags_alone_do_not_pass(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_BORROW_SIZER_ENABLED", "true")
    res = H.check_h05_sizer(exact_quote_fact=None)          # no live evidence
    assert res["status"] != H.PASS
    assert res["status"] == H.BLOCKED
    res_pass = H.check_h05_sizer(exact_quote_fact=_EXACT_FACT)
    assert res_pass["status"] == H.PASS


def test_extract_exact_quote_fact_from_nested_bundle():
    bundle = {"bundle_id": "b1", "verdict": "CONFIRMED",
              "evidence": {"quote": {"facts": _EXACT_FACT}}}
    assert H.extract_exact_quote_fact(bundle) == _EXACT_FACT
    probe_bundle = {"evidence": {"quote": {"facts": _PROBE_FACT}}}
    assert H.extract_exact_quote_fact(probe_bundle) is None
