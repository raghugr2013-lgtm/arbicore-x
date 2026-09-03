"""Pre-Limited-Live hardening regression suite.

Proves the fail-closed invariants that must hold BEFORE a controlled
Limited-Live activation — covering the economic gate, the hard simulation
gate, the execution-mode ladder, the quote RPC-failover semantics and the
executor/signer readiness probes. Everything here is offline/deterministic
(no RPC, no DB); it exercises the REAL production code paths.

Every execution-relevant case asserts EXPECTED = NOT EXECUTABLE / NO BROADCAST
unless it is a deliberately permitted path.
"""
from __future__ import annotations

import os
import asyncio
import pytest

from arbicore.execution.mode import is_broadcast_allowed, default_mode_map
from arbicore.economics.net_profit import compute_net_profit
from arbicore.economics.opportunity_decision import (
    run_simulation_gate, decide_opportunity,
)
from arbicore.execution.quoter import (
    QuoterRegistry, HopQuote, _should_failover, _fallback_hop, _now_iso,
)
from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
    resolve_executor_address, probe_signer_readiness,
)


# --------------------------------------------------------------------------- #
# Phase 4 — execution mode ladder: SHADOW can never broadcast                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("mode", ["OBSERVE", "PAPER", "SHADOW", "", None, "LIVE", "garbage"])
def test_non_live_modes_cannot_broadcast(mode):
    assert is_broadcast_allowed(mode) is False


@pytest.mark.parametrize("mode", ["LIMITED_LIVE", "FULL_LIVE"])
def test_only_live_modes_may_broadcast(mode):
    assert is_broadcast_allowed(mode) is True


def test_flash_loan_default_mode_is_shadow():
    assert default_mode_map().get("flash_loan_arbitrage") == "SHADOW"


# --------------------------------------------------------------------------- #
# Phase 2 — net-profit economics                                              #
# --------------------------------------------------------------------------- #

def test_negative_net_profit_is_not_profitable():
    r = compute_net_profit(gross_spread_bps=5.0, notional_usd=10_000.0,
                           flash_loan_notional_usd=10_000.0, flash_loan_fee_bps=9.0,
                           slippage_bps=50.0)
    assert r.net_profit_usd < 0
    assert r.is_profitable is False


def test_zero_spread_is_not_profitable():
    r = compute_net_profit(gross_spread_bps=0.0, notional_usd=10_000.0)
    assert r.is_profitable is False


def test_flash_loan_fee_is_accounted():
    base = compute_net_profit(gross_spread_bps=20.0, notional_usd=10_000.0)
    withfee = compute_net_profit(gross_spread_bps=20.0, notional_usd=10_000.0,
                                 flash_loan_notional_usd=10_000.0, flash_loan_fee_bps=9.0)
    assert withfee.net_profit_usd < base.net_profit_usd
    assert withfee.flash_loan_fee_usd == pytest.approx(9.0)  # 9bps of 10k


# --------------------------------------------------------------------------- #
# Phase 2/3/8 — hard simulation gate fail-closed matrix                       #
# --------------------------------------------------------------------------- #

ROUTER = "0x2626664c2603336e57b271c5c0b26f421741e481"
TOK_IN = "0x4200000000000000000000000000000000000006"
TOK_OUT = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
ALLOW_R = [ROUTER]
ALLOW_T = [TOK_IN, TOK_OUT]


def _good_opp(**over):
    opp = {
        "opportunity_id": "opp-1",
        "quote_status": "REAL",
        "hops": [{"router": ROUTER, "token_in": TOK_IN, "token_out": TOK_OUT,
                  "amount_out_min_wei": 123}],
        "flash_loan_provider": "balancer_v2",
        "expected_slippage_bps": 20.0,
        "gas_cost_usd": 3.0,
        "repayment_ok": True,
        "user_data_hex": "0xabcd",
        "gross_spread_bps": 30.0,
        "max_hops": 3,
    }
    opp.update(over)
    return opp


def test_sim_gate_baseline_passes():
    r = run_simulation_gate(_good_opp(), router_allowlist=ALLOW_R, token_allowlist=ALLOW_T)
    assert r.passed is True, r.failures


@pytest.mark.parametrize("mutation,failing_check", [
    ({"gas_cost_usd": 0.0}, "gas_ok"),                       # missing gas can't become free
    ({"gas_cost_usd": None}, "gas_ok"),
    ({"gas_cost_usd": 9999.0}, "gas_ok"),                    # gas over cap
    ({"hops": [{"router": ROUTER, "token_in": TOK_IN, "token_out": TOK_OUT,
                "amount_out_min_wei": 0}]}, "min_output_nonzero"),  # unbounded slippage
    ({"quote_status": "STALE"}, "quote_fresh"),              # stale quote
    ({"quote_status": None}, "quote_fresh"),
    ({"expected_slippage_bps": 10_000.0}, "slippage_ok"),    # slippage over cap
    ({"flash_loan_provider": "unknown"}, "provider_ok"),
    ({"hops": []}, "has_route"),                             # no route
    ({"gross_spread_bps": 0.0}, "expected_profit_positive"),
    ({"hops": [{"router": "0xbad", "token_in": TOK_IN, "token_out": TOK_OUT,
                "amount_out_min_wei": 1}]}, "router_allowlisted"),
])
def test_sim_gate_fails_closed(mutation, failing_check):
    r = run_simulation_gate(_good_opp(**mutation),
                            router_allowlist=ALLOW_R, token_allowlist=ALLOW_T)
    assert r.passed is False
    assert failing_check in r.failures


def test_decide_opportunity_high_gas_not_executable():
    # gross spread positive but gas far exceeds cap → not executable
    d = decide_opportunity(_good_opp(gas_cost_usd=9999.0),
                           router_allowlist=ALLOW_R, token_allowlist=ALLOW_T)
    assert d.would_execute is False


def test_decide_opportunity_stale_quote_not_executable():
    d = decide_opportunity(_good_opp(quote_status="STALE"),
                           router_allowlist=ALLOW_R, token_allowlist=ALLOW_T)
    assert d.would_execute is False


# --------------------------------------------------------------------------- #
# Phase 6 — quote RPC failover semantics                                      #
# --------------------------------------------------------------------------- #

def _hop(status, err=None, out=0):
    return HopQuote(
        hop_index=0, dex="uniswap_v3", token_in=TOK_IN, token_out=TOK_OUT,
        amount_in_wei=10**18, amount_out_wei=out, sqrt_price_x96_after=None,
        gas_estimate_units=None, price_impact_bps=None, quoter_contract="0xq",
        rpc_host="h", block_number=(1 if status == "ok" else None),
        status=status, error=err, generated_at=_now_iso())


def test_should_failover_semantics():
    assert _should_failover(_hop("ok", out=5)) is False
    assert _should_failover(_hop("fallback:no_adapter", "no adapter")) is False
    # genuine on-chain revert must NOT be treated as a provider failure
    assert _should_failover(_hop("fallback:revert", "code=3 execution reverted")) is False
    # transient/provider faults DO fail over
    assert _should_failover(_hop("fallback:revert", "code=-32016 HTTP 429 rate limited")) is True
    assert _should_failover(_hop("fallback:rpc_error", "ConnectError")) is True


class _FakeBackend:
    dex = "uniswap_v3"

    def __init__(self, status_by_host):
        self._by_host = status_by_host

    async def quote_hop(self, *, hop_index, chain, token_in, token_out,
                        amount_in_wei, hop_spec, rpc_url, max_retries=None):
        from urllib.parse import urlparse
        host = urlparse(rpc_url).hostname or rpc_url
        st = self._by_host.get(host, ("fallback:rpc_error", "no route"))
        status, err = st
        if status == "ok":
            return _hop("ok", out=245_000)
        return _fallback_hop(hop_index, self.dex, token_in, token_out,
                             amount_in_wei, "0xq", host, status, err)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mk_registry(status_by_host):
    return QuoterRegistry(backends=[_FakeBackend(status_by_host)],
                          rpc_url_env="ARBICORE_RPC_URL_BASE")


def _hops():
    return [{"dex": "uniswap_v3", "token_in": TOK_IN, "token_out": TOK_OUT,
             "amount_in_wei": 10**18, "fee": 500}]


def _set_rpc(primary, failover=None, monkeypatch=None):
    monkeypatch.setenv("ARBICORE_RPC_URL_BASE", primary)
    if failover:
        monkeypatch.setenv("PROVIDER_RPC_URLS_BASE", failover)
    else:
        monkeypatch.delenv("PROVIDER_RPC_URLS_BASE", raising=False)
    monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)


def test_failover_healthy_primary(monkeypatch):
    _set_rpc("https://alchemy.test", monkeypatch=monkeypatch)
    reg = _mk_registry({"alchemy.test": ("ok", None)})
    rq = _run(reg.quote_route(chain="base", hops=_hops()))
    assert rq.status == "ok" and rq.final_amount_out_wei == 245_000


def test_failover_primary_429_uses_secondary(monkeypatch):
    _set_rpc("https://alchemy.test", "https://public.test", monkeypatch=monkeypatch)
    reg = _mk_registry({"alchemy.test": ("fallback:revert", "code=-32016 HTTP 429 rate limited"),
                        "public.test": ("ok", None)})
    rq = _run(reg.quote_route(chain="base", hops=_hops()))
    assert rq.status == "ok" and rq.final_amount_out_wei == 245_000


def test_failover_transport_error_uses_secondary(monkeypatch):
    _set_rpc("https://alchemy.test", "https://public.test", monkeypatch=monkeypatch)
    reg = _mk_registry({"alchemy.test": ("fallback:rpc_error", "ConnectError"),
                        "public.test": ("ok", None)})
    rq = _run(reg.quote_route(chain="base", hops=_hops()))
    assert rq.status == "ok"


def test_genuine_revert_does_not_failover(monkeypatch):
    # primary returns a genuine execution revert; secondary is healthy but MUST
    # NOT be consulted (a real revert is the same on every node).
    _set_rpc("https://alchemy.test", "https://public.test", monkeypatch=monkeypatch)
    reg = _mk_registry({"alchemy.test": ("fallback:revert", "code=3 execution reverted"),
                        "public.test": ("ok", None)})
    rq = _run(reg.quote_route(chain="base", hops=_hops()))
    assert rq.status == "fallback:break_even"


def test_all_providers_down_fail_closed(monkeypatch):
    _set_rpc("https://a.test", "https://b.test,https://c.test", monkeypatch=monkeypatch)
    reg = _mk_registry({})  # every host → rpc_error
    rq = _run(reg.quote_route(chain="base", hops=_hops()))
    assert rq.status == "fallback:break_even"
    assert rq.final_amount_out_wei == 10**18  # passthrough, never a fabricated quote


def test_only_ok_quotes_are_cached(monkeypatch):
    _set_rpc("https://a.test", "https://b.test", monkeypatch=monkeypatch)
    reg = _mk_registry({"a.test": ("fallback:rpc_error", "x"), "b.test": ("fallback:rpc_error", "x")})
    _run(reg.quote_route(chain="base", hops=_hops()))
    assert len(reg._cache) == 0  # transient fallbacks never cached


def test_no_rpc_configured_fail_closed(monkeypatch):
    for k in ["ARBICORE_RPC_URL_BASE", "ARBICORE_RPC_URL", "PROVIDER_RPC_URLS_BASE",
              "PROVIDER_RPC_URLS", "BASE_RPC_URL"]:
        monkeypatch.delenv(k, raising=False)
    reg = _mk_registry({})
    rq = _run(reg.quote_route(chain="base", hops=_hops()))
    assert rq.status == "fallback:break_even"


# --------------------------------------------------------------------------- #
# Phase 5/11 — executor + signer readiness fail-closed                        #
# --------------------------------------------------------------------------- #

def test_missing_executor_address_blocks(monkeypatch):
    monkeypatch.delenv("ARBICORE_EXECUTOR_ADDRESS_BASE", raising=False)
    monkeypatch.setenv("ARBICORE_CHAIN_ID", "8453")  # base mainnet: registry = not_deployed
    assert resolve_executor_address("8453") in (None, "")


def test_signer_not_ready_without_owner():
    sig = probe_signer_readiness(executor_owner=None)
    ready = sig.get("ready") if isinstance(sig, dict) else sig
    assert not ready
