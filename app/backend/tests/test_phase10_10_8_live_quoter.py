"""Phase 10.10.8 · canonical live profitability engine — regression tests.

Covers three surfaces:

1. ``QuoterRegistry`` — the on-chain quote adapter (mocked httpx).
2. ``DryRunEngine.evaluate_live`` — the async live-evaluation entrypoint.
3. ``_compute_confidence`` — the deterministic scoring formula.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from eth_abi import encode as abi_encode
from eth_utils import to_checksum_address

from arbicore.execution.adapters import AdapterRegistry
from arbicore.execution.gas import GasEstimate
from arbicore.execution.planner import (
    DryRunEngine, ExecutionPlanner, _compute_confidence,
)
from arbicore.execution.quoter import (
    HopQuote, RouteQuote,
    UniV3QuoterV2, AerodromeSlipStreamQuoter, AerodromeClassicQuoter,
    QuoterRegistry, BASE_UNIV3_QUOTER_V2,
)


WETH = to_checksum_address("0x4200000000000000000000000000000000000006")
USDC = to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
SIGNER = to_checksum_address("0x998d6efF2b28b72c44f7a334c42678eb4cCaad25")


# --------------------------------------------------------------------------- #
# Mock httpx.AsyncClient that speaks JSON-RPC batch                           #
# --------------------------------------------------------------------------- #

class _StubResp:
    def __init__(self, body):
        self._body = body
    def json(self):
        return self._body
    def raise_for_status(self):
        pass


class _RpcStub:
    """Route eth_call by (contract, selector) → canned response."""
    responses: dict = {}      # {(to_lower, sel_lower): result_hex_or_error_dict}
    block_number: int = 49_000_000

    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass

    async def post(self, url, json):
        # Batch or singleton
        if isinstance(json, list):
            out = []
            for req in json:
                out.append(self._handle_one(req))
            return _StubResp(out)
        return _StubResp(self._handle_one(json))

    def _handle_one(self, req):
        method = req.get("method")
        params = req.get("params") or []
        rid = req.get("id")
        if method == "eth_blockNumber":
            return {"jsonrpc": "2.0", "id": rid, "result": hex(self.block_number)}
        if method == "eth_call":
            call = params[0]
            to = (call.get("to") or "").lower()
            data = (call.get("data") or "").lower()
            sel = data[:10]
            resp = _RpcStub.responses.get((to, sel))
            if isinstance(resp, dict) and "error" in resp:
                return {"jsonrpc": "2.0", "id": rid, "error": resp["error"]}
            if resp is None:
                return {"jsonrpc": "2.0", "id": rid, "error":
                        {"code": -32000, "message": "no stub configured"}}
            return {"jsonrpc": "2.0", "id": rid, "result": resp}
        return {"jsonrpc": "2.0", "id": rid, "result": "0x0"}


def _mk_univ3_quote_result(amount_out: int, sqrt: int = 0, ticks: int = 0, gas_est: int = 0) -> str:
    """Encode the tuple (uint256, uint160, uint32, uint256) that
    UniV3 QuoterV2 returns for ``quoteExactInputSingle``."""
    return "0x" + abi_encode(
        ["uint256", "uint160", "uint32", "uint256"],
        [amount_out, sqrt, ticks, gas_est],
    ).hex()


def _mk_aero_classic_result(amount_in: int, amount_out: int) -> str:
    return "0x" + abi_encode(["uint256[]"], [[amount_in, amount_out]]).hex()


# --------------------------------------------------------------------------- #
# UniV3 adapter                                                               #
# --------------------------------------------------------------------------- #

class TestUniV3QuoterV2:
    @pytest.mark.asyncio
    async def test_happy_path(self, monkeypatch):
        _RpcStub.responses = {
            (BASE_UNIV3_QUOTER_V2.lower(),
             "0xc6a5026a"): _mk_univ3_quote_result(30_500_000, sqrt=123, gas_est=95_000),
        }
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _RpcStub)
        q = UniV3QuoterV2()
        r = await q.quote_hop(
            hop_index=0, chain="base",
            token_in=WETH, token_out=USDC,
            amount_in_wei=10_000_000_000_000_000,
            hop_spec={"fee": 500}, rpc_url="https://stub/rpc",
        )
        assert r.status == "ok"
        assert r.amount_out_wei == 30_500_000
        assert r.sqrt_price_x96_after == 123
        assert r.gas_estimate_units == 95_000
        assert r.quoter_contract == BASE_UNIV3_QUOTER_V2
        assert r.block_number == 49_000_000

    @pytest.mark.asyncio
    async def test_fallback_when_rpc_reverts(self, monkeypatch):
        _RpcStub.responses = {
            (BASE_UNIV3_QUOTER_V2.lower(), "0xc6a5026a"): {
                "error": {"code": -32000, "message": "execution reverted"}
            },
        }
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _RpcStub)
        r = await UniV3QuoterV2().quote_hop(
            hop_index=0, chain="base",
            token_in=WETH, token_out=USDC, amount_in_wei=1,
            hop_spec={"fee": 500}, rpc_url="https://stub/rpc",
        )
        assert r.status == "fallback:revert"
        assert r.amount_out_wei == 0

    @pytest.mark.asyncio
    async def test_fallback_when_fee_missing(self, monkeypatch):
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _RpcStub)
        r = await UniV3QuoterV2().quote_hop(
            hop_index=0, chain="base",
            token_in=WETH, token_out=USDC, amount_in_wei=1,
            hop_spec={}, rpc_url="https://stub/rpc",
        )
        assert r.status == "fallback:no_adapter"
        assert "fee tier" in r.error.lower()

    @pytest.mark.asyncio
    async def test_unsupported_chain(self, monkeypatch):
        r = await UniV3QuoterV2().quote_hop(
            hop_index=0, chain="polygon",
            token_in=WETH, token_out=USDC, amount_in_wei=1,
            hop_spec={"fee": 500}, rpc_url="https://stub/rpc",
        )
        assert r.status == "fallback:no_adapter"

    @pytest.mark.asyncio
    async def test_fee_bps_accepted_as_input(self, monkeypatch):
        _RpcStub.responses = {
            (BASE_UNIV3_QUOTER_V2.lower(),
             "0xc6a5026a"): _mk_univ3_quote_result(1_000_000),
        }
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _RpcStub)
        # fee_tier_bps=5 → 500 ppm  → contract should accept
        r = await UniV3QuoterV2().quote_hop(
            hop_index=0, chain="base",
            token_in=WETH, token_out=USDC, amount_in_wei=1_000,
            hop_spec={"fee_tier_bps": 5}, rpc_url="https://stub/rpc",
        )
        assert r.status == "ok"
        assert r.amount_out_wei == 1_000_000


# --------------------------------------------------------------------------- #
# Aerodrome classic AMM                                                       #
# --------------------------------------------------------------------------- #

class TestAerodromeClassic:
    @pytest.mark.asyncio
    async def test_happy_path(self, monkeypatch):
        # selector 0xf41766d8 → aero getAmountsOut
        from arbicore.execution.quoter import BASE_AERO_CLASSIC_ROUTER, _SEL
        sel = _SEL["aero_getAmountsOut"].lower()
        _RpcStub.responses = {
            (BASE_AERO_CLASSIC_ROUTER.lower(),
             sel): _mk_aero_classic_result(10_000_000_000_000_000, 30_450_000),
        }
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _RpcStub)
        r = await AerodromeClassicQuoter().quote_hop(
            hop_index=0, chain="base",
            token_in=WETH, token_out=USDC,
            amount_in_wei=10_000_000_000_000_000,
            hop_spec={"stable": False}, rpc_url="https://stub/rpc",
        )
        assert r.status == "ok"
        assert r.amount_out_wei == 30_450_000
        assert r.quoter_contract == BASE_AERO_CLASSIC_ROUTER


# --------------------------------------------------------------------------- #
# QuoterRegistry route-quote                                                  #
# --------------------------------------------------------------------------- #

class TestQuoterRegistryRoute:
    @pytest.mark.asyncio
    async def test_full_live_route(self, monkeypatch):
        _RpcStub.responses = {
            (BASE_UNIV3_QUOTER_V2.lower(),
             "0xc6a5026a"): _mk_univ3_quote_result(30_450_000),
        }
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _RpcStub)
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub/rpc")
        reg = QuoterRegistry(cache_ttl_s=0.0)  # disable cache
        rq = await reg.quote_route(
            chain="base",
            hops=[{"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
                    "amount_in_wei": 10_000_000_000_000_000, "fee": 500}],
        )
        assert rq.status == "ok"
        assert rq.final_amount_out_wei == 30_450_000
        assert rq.hops[0].block_number == 49_000_000

    @pytest.mark.asyncio
    async def test_route_chaining_amount_in(self, monkeypatch):
        """Hop 0 output feeds hop 1 amountIn — must be automatic."""
        # First call: WETH→USDC returns 30_450_000
        # Second call: USDC→WETH returns 9_950_000_000_000_000
        results = iter([
            _mk_univ3_quote_result(30_450_000),
            _mk_univ3_quote_result(9_950_000_000_000_000),
        ])
        class _ChainStub(_RpcStub):
            async def post(self, url, json):
                out = []
                for req in json:
                    if req.get("method") == "eth_call":
                        out.append({"jsonrpc":"2.0","id":req["id"],"result":next(results)})
                    else:
                        out.append({"jsonrpc":"2.0","id":req["id"],"result":hex(49_000_000)})
                return _StubResp(out)
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _ChainStub)
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub/rpc")
        reg = QuoterRegistry(cache_ttl_s=0.0)
        rq = await reg.quote_route(chain="base", hops=[
            {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
             "amount_in_wei": 10_000_000_000_000_000, "fee": 500},
            {"dex": "uniswap_v3", "token_in": USDC, "token_out": WETH,
             "fee": 500},  # no amount_in_wei → chain from prior hop
        ])
        assert rq.status == "ok"
        assert rq.hops[0].amount_in_wei == 10_000_000_000_000_000
        assert rq.hops[0].amount_out_wei == 30_450_000
        # Hop 1 amount_in must be hop 0 amount_out
        assert rq.hops[1].amount_in_wei == 30_450_000
        assert rq.hops[1].amount_out_wei == 9_950_000_000_000_000
        assert rq.final_amount_out_wei == 9_950_000_000_000_000

    @pytest.mark.asyncio
    async def test_partial_status_on_single_hop_fallback(self, monkeypatch):
        results = iter([_mk_univ3_quote_result(30_450_000)])
        class _MixStub(_RpcStub):
            async def post(self, url, json):
                out = []
                for req in json:
                    if req.get("method") == "eth_call":
                        # First eth_call gets a good response; second reverts
                        try:
                            out.append({"jsonrpc":"2.0","id":req["id"],
                                        "result":next(results)})
                        except StopIteration:
                            out.append({"jsonrpc":"2.0","id":req["id"],
                                        "error":{"code":3,"message":"revert"}})
                    else:
                        out.append({"jsonrpc":"2.0","id":req["id"],
                                    "result":hex(49_000_000)})
                return _StubResp(out)
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _MixStub)
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub/rpc")
        reg = QuoterRegistry(cache_ttl_s=0.0)
        rq = await reg.quote_route(chain="base", hops=[
            {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
             "amount_in_wei": 10_000_000_000_000_000, "fee": 500},
            {"dex": "uniswap_v3", "token_in": USDC, "token_out": WETH, "fee": 500},
        ])
        assert rq.status == "partial"
        assert rq.hops[0].status == "ok"
        assert rq.hops[1].status == "fallback:revert"

    @pytest.mark.asyncio
    async def test_break_even_when_all_hops_fail(self, monkeypatch):
        class _AllFailStub(_RpcStub):
            async def post(self, url, json):
                out = []
                for req in json:
                    if req.get("method") == "eth_call":
                        out.append({"jsonrpc":"2.0","id":req["id"],
                                    "error":{"code":3,"message":"revert"}})
                    else:
                        out.append({"jsonrpc":"2.0","id":req["id"],
                                    "result":hex(49_000_000)})
                return _StubResp(out)
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _AllFailStub)
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub/rpc")
        reg = QuoterRegistry(cache_ttl_s=0.0)
        rq = await reg.quote_route(chain="base", hops=[
            {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
             "amount_in_wei": 10, "fee": 500},
        ])
        assert rq.status == "fallback:break_even"

    @pytest.mark.asyncio
    async def test_no_rpc_url_returns_fallback_break_even(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        reg = QuoterRegistry()
        rq = await reg.quote_route(chain="base", hops=[
            {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
             "amount_in_wei": 10, "fee": 500},
        ])
        assert rq.status == "fallback:break_even"
        assert rq.hops[0].error is not None
        assert "ARBICORE_RPC_URL" in rq.hops[0].error

    @pytest.mark.asyncio
    async def test_ttl_cache_hits_second_call(self, monkeypatch):
        call_count = {"n": 0}
        class _CountStub(_RpcStub):
            async def post(self, url, json):
                out = []
                for req in json:
                    if req.get("method") == "eth_call":
                        call_count["n"] += 1
                        out.append({"jsonrpc":"2.0","id":req["id"],
                                    "result":_mk_univ3_quote_result(1_000)})
                    else:
                        out.append({"jsonrpc":"2.0","id":req["id"],
                                    "result":hex(49_000_000)})
                return _StubResp(out)
        monkeypatch.setattr("arbicore.execution.quoter.httpx.AsyncClient", _CountStub)
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub/rpc")
        reg = QuoterRegistry(cache_ttl_s=60.0)
        hop = {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
               "amount_in_wei": 1_000_000, "fee": 500}
        await reg.quote_route(chain="base", hops=[hop])
        await reg.quote_route(chain="base", hops=[hop])
        assert call_count["n"] == 1, "Second identical call should hit cache"


# --------------------------------------------------------------------------- #
# DryRunEngine.evaluate_live                                                  #
# --------------------------------------------------------------------------- #

class _FakeGasOracle:
    provider = "fake_gas"
    def is_available(self): return True
    async def estimate(self, *, chain, step_kinds, native_price_usd=None):
        return GasEstimate(
            provider=self.provider, gas_price_wei=int(0.03e9),
            max_fee_per_gas_wei=int(0.05e9), max_priority_fee_wei=int(0.01e9),
            total_gas_units=500_000, total_cost_wei=15_000_000_000_000,
            total_cost_native=0.000015, total_cost_usd=0.05,
            per_step_gas_units=[500_000], per_step_cost_wei=[15_000_000_000_000],
            native_price_usd=3_000.0, method="rpc_gas_price",
            generated_at="2026-08-02T00:00:00+00:00",
        )


class _FakeProfitableQuoter:
    async def quote_plan(self, plan_doc, *, rpc_url=None):
        return RouteQuote(
            chain=plan_doc.get("chain", "base"),
            hops=[HopQuote(
                hop_index=0, dex="uniswap_v3", token_in=WETH, token_out=USDC,
                amount_in_wei=10_000_000_000_000_000, amount_out_wei=30_500_000,
                sqrt_price_x96_after=1, gas_estimate_units=95_000,
                price_impact_bps=None,
                quoter_contract=BASE_UNIV3_QUOTER_V2,
                rpc_host="stub", block_number=49_000_000,
                status="ok", error=None, generated_at="2026-08-02T00:00:00+00:00",
            )],
            # A route that beats break-even by 1 % so profitable=True
            final_amount_out_wei=10_100_000_000_000_000,
            aggregate_price_impact_bps=None,
            aggregate_gas_estimate_units=95_000,
            status="ok",
            generated_at="2026-08-02T00:00:00+00:00", ttl_seconds=5,
        )


class TestEvaluateLive:
    @pytest.mark.asyncio
    async def test_live_profitable_route(self):
        planner = ExecutionPlanner(AdapterRegistry())
        plan = planner.build(
            strategy="flash_loan_arbitrage", chain="base",
            borrow_token=WETH,
            borrow_amount_wei=10_000_000_000_000_000,
            flash_loan_provider="balancer_v2",
            swap_hops=[{
                "dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
                "amount_in_wei": 10_000_000_000_000_000,
                "min_amount_out_wei": 30_000_000, "fee_tier_bps": 5,
            }],
            borrow_amount_usd=30.0,
            mode="LIMITED_LIVE",
        )
        dre = DryRunEngine(
            AdapterRegistry(),
            gas_oracle=_FakeGasOracle(),
            quoter=_FakeProfitableQuoter(),
        )
        eco = await dre.evaluate_live(plan)
        assert eco["quote_source"] == "live"
        assert eco["gas_source"] == "live_rpc_gas_price"
        assert eco["effective_out_wei"] == 10_100_000_000_000_000
        assert eco["gas_estimate_usd"] == 0.05
        assert eco["profitable"] is True
        assert eco["net_profit_usd"] > 0
        # Confidence score included and bounded
        assert 0.0 <= eco["confidence_score"] <= 1.0
        assert "quote_route" in eco
        assert "gas_detail" in eco
        # Engine version marker
        assert eco["engine_version"] == "dry_run@live-1"

    @pytest.mark.asyncio
    async def test_fallback_when_quoter_missing(self):
        planner = ExecutionPlanner(AdapterRegistry())
        plan = planner.build(
            strategy="flash_loan_arbitrage", chain="base",
            borrow_token=WETH, borrow_amount_wei=1,
            flash_loan_provider="balancer_v2",
            swap_hops=[{"dex":"uniswap_v3","token_in":WETH,"token_out":USDC,
                         "amount_in_wei":1,"min_amount_out_wei":1,"fee_tier_bps":5}],
            borrow_amount_usd=1.0,
        )
        dre = DryRunEngine(AdapterRegistry(), gas_oracle=_FakeGasOracle())  # no quoter
        eco = await dre.evaluate_live(plan)
        # No quoter → quote_source stays at fallback:break_even but gas is live
        assert eco["quote_source"] == "fallback:break_even"
        assert eco["gas_source"] == "live_rpc_gas_price"


# --------------------------------------------------------------------------- #
# Confidence scoring                                                          #
# --------------------------------------------------------------------------- #

class TestConfidence:
    def test_no_quote_gives_low_confidence(self):
        assert _compute_confidence({}, None) < 0.3

    def test_live_and_profitable_maxes_out(self):
        class _Q: status = "ok"
        eco = {
            "effective_out_wei": 101,          # 1 % over break-even
            "min_break_even_wei": 100,
            "gross_profit_usd": 1.0, "gas_estimate_usd": 0.1,   # gas ratio 10 %
            "min_output_after_slippage_covers_repay": True,
            "slippage": {"aggregate_slippage_bps": 30},
        }
        assert _compute_confidence(eco, _Q()) == 1.0

    def test_partial_quote_drops_signal(self):
        class _Q: status = "partial"
        eco = {"effective_out_wei": 101, "min_break_even_wei": 100,
                "gross_profit_usd": 1, "gas_estimate_usd": 0.1,
                "min_output_after_slippage_covers_repay": True,
                "slippage": {}}
        # quote_signal drops from 1.0 to 0.5 → score decreases
        assert 0.7 < _compute_confidence(eco, _Q()) < 0.95

    def test_high_gas_ratio_reduces_score(self):
        class _Q: status = "ok"
        eco = {"effective_out_wei": 200, "min_break_even_wei": 100,
                "gross_profit_usd": 1, "gas_estimate_usd": 1.0,  # 100 % gas
                "min_output_after_slippage_covers_repay": True,
                "slippage": {}}
        assert _compute_confidence(eco, _Q()) < 0.9
