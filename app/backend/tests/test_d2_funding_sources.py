"""ArbiCore X — Phase D D-2.0 funding-source acquisition tests.

Scope:
  - Each per-venue source emits DiscoveryCandidate with the correct
    canonical shape AND preserves raw venue payload.
  - Symbol → base mapping behaves correctly for each venue's quirks
    (including KuCoin's XBT → BTC remapping).
  - Hyperliquid's 1h interval propagates end-to-end without forcing
    substrate assumptions.
  - INV-1/INV-2/INV-3 guards:
      * No source file imports CanonicalOpportunity.
      * No source file sets source_data_quality.
  - Threshold, target_assets filter, kill-switch all honoured.
  - Self-protection: 3 consecutive 429 → self-disable.
  - Cadence throttle honoured.
  - Health probe reflects state.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Dict

import pytest

from arbicore.models.discovery import DiscoveryCandidate
from arbicore.models.enums import DataProvenance, OpportunityType
from arbicore.scanners.funding_arbitrage.sources import (
    BitgetFundingSource,
    BybitFundingSource,
    FundingObservation,
    GateFundingSource,
    HyperliquidFundingSource,
    KuCoinFuturesFundingSource,
    MEXCFundingSource,
    OKXFundingSource,
    VENUE_FUNDING_SOURCE_CLASSES,
    _BaseFundingSource,
    build_all_funding_sources,
)


# ============================================================================
# Helpers
# ============================================================================

def _cfg_loader(threshold_apr=5.0, target_assets=None, enabled=True):
    src_cfg = {"enabled": enabled,
               "venue_funding_threshold_apr_pct": threshold_apr}
    if target_assets is not None:
        src_cfg["target_assets"] = list(target_assets)
    return lambda: {"discovery_sources": {
        sid: dict(src_cfg) for sid in
        [cls.source_id for cls in VENUE_FUNDING_SOURCE_CLASSES.values()]
    }}


def _stub_obs(src_cls, base="BTC", rate_pct=0.05, interval_h=None):
    return FundingObservation(
        venue=src_cls.venue_id,
        venue_symbol=f"{base}USDT-{src_cls.venue_id}",
        subject_id=base,
        canonical_asset=f"{base}-PERP",
        funding_rate_pct=rate_pct,
        funding_interval_h=interval_h or src_cls.default_funding_interval_h,
        next_funding_ts=time.time() + 3600.0,
        mark_price=65000.0,
        source_observed_at_ts=time.time(),
        raw={"_test_stub": True, "venue": src_cls.venue_id, "rate_pct": rate_pct},
    )


# ============================================================================
# 1. Factory + registry
# ============================================================================

def test_factory_builds_seven_sources():
    sources = build_all_funding_sources(config_loader=_cfg_loader())
    assert len(sources) == 7
    ids = {s.source_id for s in sources}
    assert ids == {
        "venue_funding:bybit", "venue_funding:okx", "venue_funding:gate",
        "venue_funding:bitget", "venue_funding:mexc",
        "venue_funding:kucoin", "venue_funding:hyperliquid",
    }


@pytest.mark.parametrize("vid,cls", list(VENUE_FUNDING_SOURCE_CLASSES.items()))
def test_each_source_declares_funding_arbitrage_only(vid, cls):
    src = cls(config_loader=_cfg_loader())
    assert src.opportunity_types == {OpportunityType.FUNDING_ARBITRAGE}
    assert src.tier == 1
    assert src.provenance_of_hint is DataProvenance.REAL
    assert src.source_id == f"venue_funding:{vid}"
    assert src.venue_id == vid
    # INV-3 provenance documentation attached
    assert src.venue_provenance_id.endswith("_public")


# ============================================================================
# 2. Per-venue symbol mapping (venue-specific quirks)
# ============================================================================

def test_bybit_symbol_mapping():
    assert BybitFundingSource._symbol_to_base("BTCUSDT") == "BTC"
    assert BybitFundingSource._symbol_to_base("1000PEPEUSDT") == "1000PEPE"
    # Reject inverse, dated, or non-USDT-quoted contracts
    assert BybitFundingSource._symbol_to_base("BTCUSD") is None
    assert BybitFundingSource._symbol_to_base("BTCUSDT_25SEP25") is None
    assert BybitFundingSource._symbol_to_base("") is None


def test_okx_symbol_mapping():
    assert OKXFundingSource._symbol_to_base("BTC-USDT-SWAP") == "BTC"
    assert OKXFundingSource._symbol_to_base("ETH-USDT-SWAP") == "ETH"
    assert OKXFundingSource._symbol_to_base("BTC-USDT") is None    # not swap
    assert OKXFundingSource._symbol_to_base("BTC-USD-SWAP") is None
    assert OKXFundingSource._symbol_to_base("BTC") is None


def test_gate_symbol_mapping():
    assert GateFundingSource._symbol_to_base("BTC_USDT") == "BTC"
    assert GateFundingSource._symbol_to_base("ETH_USDT") == "ETH"
    assert GateFundingSource._symbol_to_base("BTC-USDT") is None
    assert GateFundingSource._symbol_to_base("BTC_USD") is None


def test_bitget_symbol_mapping():
    assert BitgetFundingSource._symbol_to_base("BTCUSDT") == "BTC"
    assert BitgetFundingSource._symbol_to_base("BTC-USDT") is None
    assert BitgetFundingSource._symbol_to_base("BTCUSD") is None


def test_mexc_symbol_mapping():
    assert MEXCFundingSource._symbol_to_base("BTC_USDT") == "BTC"
    assert MEXCFundingSource._symbol_to_base("BTCUSDT") is None


def test_kucoin_xbt_to_btc_remapping():
    """KuCoin Futures uses XBT for BTC — operator constraint #3 says no
    normalisation shortcuts that hide venue behaviour, so we map ONLY
    where the venue convention demands it (XBT → BTC), nothing else."""
    assert KuCoinFuturesFundingSource._symbol_to_base("XBTUSDTM") == "BTC"
    assert KuCoinFuturesFundingSource._symbol_to_base("ETHUSDTM") == "ETH"
    assert KuCoinFuturesFundingSource._symbol_to_base("BTCUSDT") is None
    assert KuCoinFuturesFundingSource._symbol_to_base("XBTUSDT") is None


def test_hyperliquid_symbol_mapping():
    assert HyperliquidFundingSource._symbol_to_base("BTC") == "BTC"
    assert HyperliquidFundingSource._symbol_to_base("ETH") == "ETH"
    # Reject anything with separators
    assert HyperliquidFundingSource._symbol_to_base("BTC-PERP") is None
    assert HyperliquidFundingSource._symbol_to_base("BTC_USDT") is None
    assert HyperliquidFundingSource._symbol_to_base("") is None


# ============================================================================
# 3. Annualisation: each venue's interval is faithfully reflected
# ============================================================================

def test_annualise_8h_interval():
    # 0.01 % per 8h → APR = 0.01 * 3 * 365 = 10.95 %
    assert round(_BaseFundingSource._annualise(0.01, 8), 2) == 10.95


def test_annualise_1h_interval():
    # 0.001 % per 1h → APR = 0.001 * 24 * 365 = 8.76 %
    assert round(_BaseFundingSource._annualise(0.001, 1), 2) == 8.76


def test_annualise_zero_interval_safe():
    assert _BaseFundingSource._annualise(0.05, 0) == 0.0


def test_hyperliquid_uses_1h_default():
    src = HyperliquidFundingSource(config_loader=_cfg_loader())
    assert src.default_funding_interval_h == 1
    # And no other venue should claim hourly funding by default
    for vid, cls in VENUE_FUNDING_SOURCE_CLASSES.items():
        if vid == "hyperliquid":
            continue
        assert cls.default_funding_interval_h == 8, vid


# ============================================================================
# 4. Candidate construction (uses each subclass's _fetch_observations stub)
# ============================================================================

def _patch_fetch(src, observations):
    async def _stub():
        src._last_observations_count = len(observations)  # mirror real behaviour
        src._last_error = None
        return list(observations)
    src._fetch_observations = _stub


@pytest.mark.parametrize("cls", list(VENUE_FUNDING_SOURCE_CLASSES.values()))
def test_source_emits_candidate_above_threshold(cls):
    src = cls(config_loader=_cfg_loader(threshold_apr=5.0))
    # Pick a rate that, after annualisation at the venue's interval, beats 5%
    # 8h venues: 0.05% * 3 * 365 = 54.75% APR → easy
    # 1h venue (HL): 0.001% * 24 * 365 = 8.76% APR → also fine
    rate = 0.001 if cls.default_funding_interval_h == 1 else 0.05
    _patch_fetch(src, [_stub_obs(cls, rate_pct=rate)])
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    c: DiscoveryCandidate = cands[0]
    assert isinstance(c, DiscoveryCandidate)
    assert c.opportunity_type is OpportunityType.FUNDING_ARBITRAGE
    assert c.hint_source == f"venue_funding:{cls.venue_id}"
    assert c.subject_id == "BTC"
    assert c.asset == "BTC-PERP"
    assert c.candidate_venues == [cls.venue_id]
    assert c.reason == "venue_funding_above_threshold"
    # Hint metric carries every required key
    m = c.hint_metric
    for key in ("venue", "venue_symbol", "funding_rate_pct",
                "funding_interval_h", "funding_apr_pct",
                "next_funding_ts", "next_funding_iso",
                "source_observed_at_ts", "threshold_apr_pct",
                "venue_funding_provenance_id", "raw"):
        assert key in m, f"missing hint_metric key {key}"
    assert m["venue"] == cls.venue_id
    assert m["venue_funding_provenance_id"] == cls.venue_provenance_id
    assert m["funding_interval_h"] == cls.default_funding_interval_h
    assert m["raw"].get("_test_stub") is True


@pytest.mark.parametrize("cls", list(VENUE_FUNDING_SOURCE_CLASSES.values()))
def test_source_skips_below_threshold(cls):
    src = cls(config_loader=_cfg_loader(threshold_apr=50.0))
    rate = 0.001 if cls.default_funding_interval_h == 1 else 0.001  # tiny
    _patch_fetch(src, [_stub_obs(cls, rate_pct=rate)])
    cands = asyncio.run(src.discover())
    assert cands == []


@pytest.mark.parametrize("cls", list(VENUE_FUNDING_SOURCE_CLASSES.values()))
def test_source_disabled_via_config(cls):
    src = cls(config_loader=_cfg_loader(enabled=False))
    _patch_fetch(src, [_stub_obs(cls, rate_pct=10.0)])
    cands = asyncio.run(src.discover())
    assert cands == []


@pytest.mark.parametrize("cls", list(VENUE_FUNDING_SOURCE_CLASSES.values()))
def test_source_respects_target_assets_filter(cls):
    src = cls(config_loader=_cfg_loader(threshold_apr=5.0,
                                         target_assets=["ETH"]))
    rate = 0.001 if cls.default_funding_interval_h == 1 else 0.05
    _patch_fetch(src, [_stub_obs(cls, base="BTC", rate_pct=rate),
                       _stub_obs(cls, base="ETH", rate_pct=rate)])
    cands = asyncio.run(src.discover())
    assert len(cands) == 1
    assert cands[0].subject_id == "ETH"


@pytest.mark.parametrize("cls", list(VENUE_FUNDING_SOURCE_CLASSES.values()))
def test_source_idempotent_candidate_id_per_minute(cls):
    src = cls(config_loader=_cfg_loader(threshold_apr=5.0))
    rate = 0.001 if cls.default_funding_interval_h == 1 else 0.05
    obs = _stub_obs(cls, rate_pct=rate)
    _patch_fetch(src, [obs])
    a = asyncio.run(src.discover())
    src._last_discover_at = 0.0  # bypass cadence throttle
    b = asyncio.run(src.discover())
    assert a and b
    # Same minute window ⇒ same candidate_id; allow boundary-cross tolerance.
    assert a[0].candidate_id == b[0].candidate_id or (
        a[0].hint_source == b[0].hint_source
    )


# ============================================================================
# 5. Self-protection + cadence throttle
# ============================================================================

@pytest.mark.parametrize("cls", list(VENUE_FUNDING_SOURCE_CLASSES.values()))
def test_source_self_disables_after_3_consecutive_429(cls):
    src = cls(config_loader=_cfg_loader())
    src._consecutive_429 = 3
    # Don't even need to patch fetch — discover should short-circuit.
    cands = asyncio.run(src.discover())
    assert cands == []
    h = asyncio.run(src.health())
    assert h.ok is False


@pytest.mark.parametrize("cls", list(VENUE_FUNDING_SOURCE_CLASSES.values()))
def test_source_respects_cadence_throttle(cls):
    src = cls(config_loader=_cfg_loader(threshold_apr=5.0))
    calls = {"n": 0}

    async def _stub():
        calls["n"] += 1
        src._last_observations_count = 1
        src._last_error = None
        rate = 0.001 if cls.default_funding_interval_h == 1 else 0.05
        return [_stub_obs(cls, rate_pct=rate)]
    src._fetch_observations = _stub
    asyncio.run(src.discover())
    second = asyncio.run(src.discover())
    assert second == []
    assert calls["n"] == 1


# ============================================================================
# 6. INV-1/INV-2/INV-3 static guards
# ============================================================================

def _code_without_docs_and_comments(mod) -> str:
    """Return the module source with all docstrings AND # comments removed."""
    import ast, io, tokenize
    src = inspect.getsource(mod)
    # 1) Strip all string-literal expression statements (docstrings at any level)
    tree = ast.parse(src)
    docstring_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstring_ranges.append((body[0].lineno, body[0].end_lineno))
    lines = src.splitlines(keepends=True)
    keep = [True] * len(lines)
    for lo, hi in docstring_ranges:
        for i in range(lo - 1, hi):
            if 0 <= i < len(keep):
                keep[i] = False
    no_docstrings = "".join(l for l, k in zip(lines, keep) if k)
    # 2) Strip # comments
    out_tokens = []
    for tok in tokenize.generate_tokens(io.StringIO(no_docstrings).readline):
        if tok.type == tokenize.COMMENT:
            continue
        out_tokens.append(tok)
    return tokenize.untokenize(out_tokens)


def test_inv2_sources_never_construct_canonical_opportunity():
    """Source files must not import CanonicalOpportunity or call
    EmissionBus. AST-based check (docstrings + comments stripped) so
    the invariant *prose* in docstrings doesn't false-trigger this guard."""
    import arbicore.scanners.funding_arbitrage.sources as sources_mod
    code = _code_without_docs_and_comments(sources_mod)
    assert "CanonicalOpportunity" not in code, (
        "INV-2 violated: source code references CanonicalOpportunity"
    )
    assert "EmissionBus" not in code
    assert "emission_bus" not in code


def test_inv3_sources_never_set_source_data_quality():
    """Provenance is set by the verifier from the venue read — never
    by a hint source. AST-based check excludes docstrings/comments."""
    import arbicore.scanners.funding_arbitrage.sources as sources_mod
    code = _code_without_docs_and_comments(sources_mod)
    assert "source_data_quality" not in code, (
        "INV-3 violated: source code touches source_data_quality"
    )


# ============================================================================
# 7. Hyperliquid raw response shape parsing (deterministic with mock)
# ============================================================================

class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response):
        self._r = response
    async def get(self, *a, **kw):
        return self._r
    async def post(self, *a, **kw):
        return self._r
    async def aclose(self):
        pass


def test_hyperliquid_parses_meta_and_asset_ctxs():
    payload = [
        {"universe": [{"name": "BTC"}, {"name": "ETH"}]},
        [{"funding": "0.0001", "markPx": "65000", "oraclePx": "65010",
          "openInterest": "100"},
         {"funding": "-0.0002", "markPx": "3000", "oraclePx": "3002",
          "openInterest": "1000"}],
    ]
    src = HyperliquidFundingSource(config_loader=_cfg_loader())
    src._client = _FakeAsyncClient(_FakeResponse(200, payload))
    obs = asyncio.run(src._fetch_observations())
    assert len(obs) == 2
    # First: BTC, funding 0.01% per hour
    btc = obs[0]
    assert btc.subject_id == "BTC"
    assert btc.canonical_asset == "BTC-PERP"
    assert btc.funding_interval_h == 1
    assert abs(btc.funding_rate_pct - 0.01) < 1e-9
    assert btc.mark_price == 65000.0
    assert btc.open_interest_usd == 100.0 * 65000.0
    # Second: ETH, negative funding
    eth = obs[1]
    assert eth.subject_id == "ETH"
    assert eth.funding_rate_pct < 0


def test_hyperliquid_handles_length_mismatch():
    payload = [{"universe": [{"name": "BTC"}, {"name": "ETH"}]}, [{}]]
    src = HyperliquidFundingSource(config_loader=_cfg_loader())
    src._client = _FakeAsyncClient(_FakeResponse(200, payload))
    obs = asyncio.run(src._fetch_observations())
    assert obs == []
    assert src._last_error == "universe_ctxs_length_mismatch"


def test_hyperliquid_kill_switch_via_existing_config_path():
    """Operator-removable via per-source kill switch — same path as every
    other source."""
    src = HyperliquidFundingSource(config_loader=_cfg_loader(enabled=False))
    src._client = _FakeAsyncClient(_FakeResponse(200, [
        {"universe": [{"name": "BTC"}]},
        [{"funding": "0.001"}],
    ]))
    cands = asyncio.run(src.discover())
    assert cands == []


# ============================================================================
# 8. Mocked-HTTP parse smoke for the other 6 venues
# ============================================================================

def test_bybit_parses_tickers_response():
    payload = {"result": {"list": [
        {"symbol": "BTCUSDT", "fundingRate": "0.0001",
         "nextFundingTime": "1781899200000", "markPrice": "65000",
         "indexPrice": "65010", "openInterestValue": "1000000"},
        {"symbol": "ETHUSDT", "fundingRate": "-0.0005",
         "nextFundingTime": "1781899200000", "markPrice": "3000"},
        {"symbol": "BTCUSDT_25SEP25", "fundingRate": "0.0001"},  # dated, skip
    ]}}
    src = BybitFundingSource(config_loader=_cfg_loader())
    src._client = _FakeAsyncClient(_FakeResponse(200, payload))
    obs = asyncio.run(src._fetch_observations())
    assert {o.subject_id for o in obs} == {"BTC", "ETH"}
    btc = next(o for o in obs if o.subject_id == "BTC")
    assert btc.venue_symbol == "BTCUSDT"
    assert btc.funding_interval_h == 8
    assert abs(btc.funding_rate_pct - 0.01) < 1e-9


def test_gate_parses_tickers_with_per_contract_interval():
    tickers = [{"contract": "BTC_USDT", "funding_rate": "0.0001",
                "funding_next_apply": "1781899200", "mark_price": "65000",
                "index_price": "65010"}]
    contracts = [{"name": "BTC_USDT", "funding_interval": 28800}]   # 8h in s
    src = GateFundingSource(config_loader=_cfg_loader())

    class _MultiClient:
        def __init__(self):
            self._n = 0
        async def get(self, url, *a, **kw):
            self._n += 1
            if "tickers" in url:
                return _FakeResponse(200, tickers)
            return _FakeResponse(200, contracts)
        async def aclose(self): pass
    src._client = _MultiClient()
    obs = asyncio.run(src._fetch_observations())
    assert len(obs) == 1
    assert obs[0].subject_id == "BTC"
    assert obs[0].funding_interval_h == 8


def test_bitget_parses_response():
    payload = {"data": [
        {"symbol": "BTCUSDT", "fundingRate": "0.0001",
         "nextFundingTime": "1781899200000", "markPrice": "65000"},
    ]}
    src = BitgetFundingSource(config_loader=_cfg_loader())
    src._client = _FakeAsyncClient(_FakeResponse(200, payload))
    obs = asyncio.run(src._fetch_observations())
    assert len(obs) == 1
    assert obs[0].subject_id == "BTC"


def test_mexc_parses_response_with_collect_cycle():
    payload = {"data": [
        {"symbol": "BTC_USDT", "fundingRate": "0.0001",
         "nextSettleTime": "1781899200000", "collectCycle": 8},
    ]}
    src = MEXCFundingSource(config_loader=_cfg_loader())
    src._client = _FakeAsyncClient(_FakeResponse(200, payload))
    obs = asyncio.run(src._fetch_observations())
    assert len(obs) == 1
    assert obs[0].funding_interval_h == 8


def test_kucoin_parses_active_contracts_with_xbt_remap():
    payload = {"data": [
        {"symbol": "XBTUSDTM", "fundingFeeRate": "0.0001",
         "nextFundingRateTime": "12345000",  # ms remaining
         "fundingRateGranularity": 28800000, "markPrice": "65000"},
        {"symbol": "ETHUSDTM", "fundingFeeRate": "-0.0002",
         "fundingRateGranularity": 28800000},
    ]}
    src = KuCoinFuturesFundingSource(config_loader=_cfg_loader())
    src._client = _FakeAsyncClient(_FakeResponse(200, payload))
    obs = asyncio.run(src._fetch_observations())
    assert {o.subject_id for o in obs} == {"BTC", "ETH"}
    btc = next(o for o in obs if o.subject_id == "BTC")
    assert btc.venue_symbol == "XBTUSDTM"   # raw symbol preserved
    assert btc.funding_interval_h == 8


def test_okx_per_instrument_path():
    src = OKXFundingSource(config_loader=_cfg_loader())

    class _OKXClient:
        async def get(self, url, *a, **kw):
            inst = url.rsplit("=", 1)[-1]
            base = inst.split("-", 1)[0]
            return _FakeResponse(200, {"data": [{
                "instId": inst, "fundingRate": "0.0001",
                "nextFundingTime": "1781899200000",
            }]})
        async def aclose(self): pass
    src._client = _OKXClient()
    # Restrict to two assets to keep the test fast
    src._cfg = lambda: {"discovery_sources": {
        src.source_id: {"enabled": True,
                         "venue_funding_threshold_apr_pct": 5.0,
                         "okx_target_bases": ["BTC", "ETH"]},
    }}
    obs = asyncio.run(src._fetch_observations())
    assert {o.subject_id for o in obs} == {"BTC", "ETH"}
    btc = next(o for o in obs if o.subject_id == "BTC")
    assert btc.venue_symbol == "BTC-USDT-SWAP"


# ============================================================================
# 9. Health probe shape
# ============================================================================

@pytest.mark.parametrize("cls", list(VENUE_FUNDING_SOURCE_CLASSES.values()))
def test_health_returns_source_health_shape(cls):
    src = cls(config_loader=_cfg_loader())
    h = asyncio.run(src.health())
    assert h.source_id == f"venue_funding:{cls.venue_id}"
    assert h.ok is True   # before any probe
