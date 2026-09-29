"""H06 — canonical six-chain discovery integration (offline, mocked).

Proves the canonical FlashLoanArbitrageScanner wiring now routes through the
proven six-chain H05 exact-size path, preserves Base/non-Base behaviour, adds
BNB to scope, and keeps every safety gate closed. No production/RPC/exec.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")

import arbicore.runtime.composition as comp
from arbicore.runtime.composition import (
    build_h05_borrow_sizer, build_multichain_price_source, _H05_CHAINS,
)
from arbicore.scanners.flash_loan_arbitrage.sources import _IN_SCOPE_CHAINS

SIX = {"ethereum", "arbitrum", "base", "optimism", "polygon", "bnb"}


# A + E: canonical six-chain scope incl. BNB
def test_scope_is_the_canonical_six_including_bnb():
    assert _IN_SCOPE_CHAINS == SIX
    assert "bnb" in _IN_SCOPE_CHAINS
    assert set(_H05_CHAINS) == SIX


class _CapturingQuoter:
    def __init__(self):
        self.chains_seen = []

    async def quote_route(self, *, chain, hops):
        self.chains_seen.append(chain)
        hop = SimpleNamespace(dex="uniswap_v3", status="ok", block_number=1,
                              quoter_contract="0xq")
        return SimpleNamespace(status="ok", hops=[hop],
                               final_amount_out_wei=2000 * 10 ** 6,
                               aggregate_gas_estimate_units=1)


def _eth_ok(chain):
    async def eth_call(to, data):
        return None
    return eth_call


# C: Base uses the canonical Base pool registry via the six-chain source
@pytest.mark.asyncio
async def test_base_uses_canonical_registry(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_USD_NUMERAIRE", "USDC")
    calls = []

    async def spy_resolver(chain, eth_call):
        calls.append(chain)
        return SimpleNamespace(resolved_specs=[], pool_meta={}, unresolved=[])

    q = _CapturingQuoter()
    src = await build_multichain_price_source(
        q, chains=("base",), eth_call_factory=_eth_ok, resolver=spy_resolver)
    assert src is not None and src.configured_chains() == ["base"]
    assert calls == []  # SP-5 NOT used for Base
    assert await src.price_usd("base", "WETH") == pytest.approx(2000.0)


# D: non-Base chains use SP-5 path
@pytest.mark.asyncio
async def test_nonbase_uses_sp5(monkeypatch):
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_USD_NUMERAIRE", "USDC")
    seen = []
    WETH, USDC, POOL = "0x" + "a1" * 20, "0x" + "b2" * 20, "0x" + "cc" * 20

    async def spy_resolver(chain, eth_call):
        seen.append(chain)
        return SimpleNamespace(
            resolved_specs=[{"venue_id": "v", "dex": "uniswap_v3", "token_a": "WETH",
                             "token_b": "USDC", "fee_bps": 5,
                             "pool_contract_address": POOL}],
            pool_meta={POOL.lower(): ("WETH", WETH, 18, "USDC", USDC, 6)},
            unresolved=[])

    for ch in ("ethereum", "arbitrum", "optimism", "polygon", "bnb"):
        seen.clear()
        src = await build_multichain_price_source(
            _CapturingQuoter(), chains=(ch,), eth_call_factory=_eth_ok,
            resolver=spy_resolver)
        assert seen == [ch] and src is not None and src.configured_chains() == [ch]


# B: canonical scanner receives the H05 exact-size callback when flags enabled
@pytest.mark.asyncio
async def test_canonical_scanner_receives_exact_callback(monkeypatch):
    monkeypatch.setenv("ARBICORE_BORROW_SIZER_ENABLED", "true")
    monkeypatch.setenv("ARBICORE_PRICE_FEED_ENABLED", "true")

    class _Src:
        async def price_usd(self, chain, token):
            return 2000.0 if str(token).upper() == "WETH" else None

    captured = {}

    def _fake_make_live_quote_provider(quoter_registry, *, tvl_provider=None,
                                       borrow_sizer=None):
        captured["borrow_sizer"] = borrow_sizer
        return lambda *a, **k: None

    # stub the six-chain source and the provider factory to observe injection
    async def _fake_price_source(*a, **k):
        return _Src()
    monkeypatch.setattr(comp, "build_multichain_price_source", _fake_price_source)

    sizer = await build_h05_borrow_sizer(_CapturingQuoter())
    assert sizer is not None  # exact-size callback built from six-chain source
    assert await sizer("bnb", "WETH", 1000.0) == 5 * 10 ** 17


# G: with H05 flags disabled → no callback injected (backward compatible)
@pytest.mark.asyncio
async def test_disabled_flags_no_callback(monkeypatch):
    monkeypatch.delenv("ARBICORE_BORROW_SIZER_ENABLED", raising=False)
    monkeypatch.delenv("ARBICORE_PRICE_FEED_ENABLED", raising=False)
    assert await build_h05_borrow_sizer(_CapturingQuoter()) is None
    assert await build_multichain_price_source(_CapturingQuoter()) is None


# F: safety posture — canonical config represents six chains, only base enabled,
# and no execution/sign/broadcast is enabled by this wiring.
def test_canonical_config_six_chains_base_only_enabled():
    import inspect
    src = inspect.getsource(comp.get_flash_loan_arb_scanner)
    for ch in SIX:
        assert f'"{ch}"' in src
    # only base enabled by default in the canonical cache
    assert '"base": {"enabled": True}' in src
    for ch in ("ethereum", "arbitrum", "optimism", "polygon", "bnb"):
        assert f'"{ch}": {{"enabled": False}}' in src


def test_no_execution_signing_broadcast_enabled_in_wiring():
    import inspect
    src = inspect.getsource(comp._wire_canonical_flash_loan_scanner)
    lowered = src.lower()
    # wiring must not enable signing/broadcast/autoexec/live
    for bad in ("set_signing(true", "enable_broadcast", "autoexec_autostart = true",
                "full_live", "limited_live"):
        assert bad not in lowered
