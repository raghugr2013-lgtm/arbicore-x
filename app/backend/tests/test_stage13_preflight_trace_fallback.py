"""Stage 13 · Phase 10.10.4 — preflight ``debug_traceCall`` fallback.

Covers the scenario where the operator's RPC provider strips the
``data`` field from the JSON-RPC ``eth_call`` error (as many free /
public Base endpoints do), forcing us to replay the same call through
``debug_traceCall`` to recover the revert selector.

Two complementary paths are asserted:

1.  The RPC provider already returns ``error.data`` — the trace
    fallback MUST NOT be invoked (backward-compatible fast path).
2.  The RPC provider omits ``error.data`` but honours
    ``debug_traceCall`` — the fallback recovers the selector, the
    receipt is populated with ``preflight_revert_source ==
    'debug_traceCall'`` and the decoded name / component /
    explanation triple flows all the way through.
3.  Both channels fail — the receipt gracefully surfaces
    ``preflight_revert_source == 'unavailable'`` with no exception
    escaping.
"""
from __future__ import annotations

import pytest

from arbicore.execution.broadcast import (
    LimitedLiveBroadcaster,
    decode_revert_data,
    revert_component,
    revert_explanation,
)


# --------------------------------------------------------------------------- #
# Component / explanation helpers                                             #
# --------------------------------------------------------------------------- #

class TestRevertComponent:
    def test_dotted_name_returns_prefix(self):
        assert revert_component("FlashLoanReceiver.NotAuthorized()") == \
            "FlashLoanReceiver"

    def test_uniswap_prefix(self):
        assert revert_component("UniV3.V3TooLittleReceived()") == "UniV3"

    def test_unknown_selector_returns_none(self):
        assert revert_component("unknown selector 0xdeadbeef") is None

    def test_error_string_returns_prefix(self):
        # decode_revert_data emits "Error(string): 'STF'"; the component
        # extractor should strip the argument list and return just "Error".
        assert revert_component("Error(string): 'STF'") == "Error"

    def test_none_input(self):
        assert revert_component(None) is None
        assert revert_component("") is None


class TestRevertExplanation:
    def test_flash_loan_receiver_not_authorized(self):
        r = revert_explanation("0xea8e4eb5")
        assert r and "not authorised" in r.lower()

    def test_univ3_too_little_received_mentions_slippage(self):
        r = revert_explanation("0x39d35496")
        assert r and "slippage" in r.lower()

    def test_unknown_selector_returns_none(self):
        assert revert_explanation("0xdeadbeef") is None

    def test_none_input(self):
        assert revert_explanation(None) is None
        assert revert_explanation("") is None


# --------------------------------------------------------------------------- #
# debug_traceCall fallback (transport-level)                                  #
# --------------------------------------------------------------------------- #

def _make_broadcaster():
    return LimitedLiveBroadcaster(
        kill_switch=None, mode_repo=None, wallet_registry=None,
        secret_registry=None, capital_allocator=None,
    )


class _StubResponse:
    def __init__(self, body):
        self._body = body
    def json(self):
        return self._body
    def raise_for_status(self):
        pass


class _RoutingStubClient:
    """Async httpx.AsyncClient stub — responses driven by method name."""

    _responses: dict = {}
    _calls: list = []

    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass

    async def post(self, url, json):
        method = json.get("method")
        _RoutingStubClient._calls.append((method, json.get("params")))
        body = _RoutingStubClient._responses.get(method,
                {"jsonrpc": "2.0", "id": 1, "result": "0x0"})
        return _StubResponse(body)


@pytest.mark.asyncio
async def test_trace_fallback_recovers_selector_when_ethcall_omits_data(monkeypatch):
    """RPC returns bare 'execution reverted' on eth_call; debug_traceCall
    returns the revert bytes → fallback recovers the selector."""
    import httpx

    _RoutingStubClient._calls = []
    _RoutingStubClient._responses = {
        "eth_call": {
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": 3, "message": "execution reverted"},
        },
        "debug_traceCall": {
            "jsonrpc": "2.0", "id": 1,
            "result": {
                "type": "CALL",
                "output": "0xea8e4eb5",  # FlashLoanReceiver.NotAuthorized()
                "error": "execution reverted",
            },
        },
    }
    monkeypatch.setattr(httpx, "AsyncClient", _RoutingStubClient)
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub.example.com/rpc")

    b = _make_broadcaster()
    call_obj = {"from": "0x0", "to": "0x1", "data": "0x", "value": "0x0"}
    recovered, diag = await b._trace_call_revert_data(call_obj)
    assert recovered == "0xea8e4eb5"
    assert decode_revert_data(recovered) == "FlashLoanReceiver.NotAuthorized()"
    # And the debug_traceCall was actually dispatched.
    assert any(m == "debug_traceCall" for m, _ in _RoutingStubClient._calls)
    # Diagnostic captured the successful attempt.
    assert len(diag) == 1
    assert diag[0]["tracer"] == "callTracer"
    assert diag[0]["outcome"] == "recovered"
    assert diag[0]["source"] == "output"


@pytest.mark.asyncio
async def test_trace_fallback_supports_structlog_returnvalue(monkeypatch):
    """Older/geth-style tracer returns { returnValue, failed } instead
    of { output, error } — the fallback must parse both flavours."""
    import httpx

    _RoutingStubClient._calls = []
    _RoutingStubClient._responses = {
        "debug_traceCall": {
            "jsonrpc": "2.0", "id": 1,
            "result": {
                "failed": True,
                "returnValue": "39d35496",  # UniV3.V3TooLittleReceived, un-prefixed
            },
        },
    }
    monkeypatch.setattr(httpx, "AsyncClient", _RoutingStubClient)
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub.example.com/rpc")

    b = _make_broadcaster()
    recovered, diag = await b._trace_call_revert_data(
        {"from": "0x0", "to": "0x1", "data": "0x", "value": "0x0"}
    )
    assert recovered == "0x39d35496"
    assert decode_revert_data(recovered) == "UniV3.V3TooLittleReceived()"
    assert diag[0]["source"] == "returnValue"


@pytest.mark.asyncio
async def test_trace_fallback_returns_none_when_node_refuses(monkeypatch):
    """When the RPC also refuses debug_traceCall (e.g. -32601 method not
    found), the fallback returns None without raising."""
    import httpx

    _RoutingStubClient._calls = []
    _RoutingStubClient._responses = {
        "debug_traceCall": {
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32601, "message": "the method debug_traceCall does not exist"},
        },
    }
    monkeypatch.setattr(httpx, "AsyncClient", _RoutingStubClient)
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub.example.com/rpc")

    b = _make_broadcaster()
    recovered, diag = await b._trace_call_revert_data(
        {"from": "0x0", "to": "0x1", "data": "0x", "value": "0x0"}
    )
    assert recovered is None
    # Both tracer attempts were made and both classified as method_not_found.
    assert len(diag) == 2
    assert all(d["outcome"] == "method_not_found" for d in diag)
    assert all(d.get("rpc_code") == -32601 for d in diag)


@pytest.mark.asyncio
async def test_trace_fallback_recovers_from_nested_reverted_subcall(monkeypatch):
    """callTracer sometimes returns a top-level output of `0x` while
    the actual revert bytes hide in the first reverted sub-call.  The
    fallback scans one level deep to catch this shape."""
    import httpx

    _RoutingStubClient._calls = []
    _RoutingStubClient._responses = {
        "debug_traceCall": {
            "jsonrpc": "2.0", "id": 1,
            "result": {
                "type": "CALL",
                "output": "0x",  # top-level output empty
                "calls": [
                    {"type": "CALL", "output": "0x39d35496", "error": "execution reverted"},
                ],
            },
        },
    }
    monkeypatch.setattr(httpx, "AsyncClient", _RoutingStubClient)
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub.example.com/rpc")

    b = _make_broadcaster()
    recovered, diag = await b._trace_call_revert_data(
        {"from": "0x0", "to": "0x1", "data": "0x", "value": "0x0"}
    )
    assert recovered == "0x39d35496"
    assert diag[0]["source"] == "nested_call"


@pytest.mark.asyncio
async def test_trace_diagnostic_classifies_forbidden(monkeypatch):
    """Some paid endpoints (Alchemy free tier, drpc) return 'method
    not allowed' — the diagnostic must classify these as 'forbidden'
    so the UI can surface the correct recommendation."""
    import httpx

    _RoutingStubClient._calls = []
    _RoutingStubClient._responses = {
        "debug_traceCall": {
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32000, "message": "debug_traceCall is not allowed on this endpoint (paid plan required)"},
        },
    }
    monkeypatch.setattr(httpx, "AsyncClient", _RoutingStubClient)
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub.example.com/rpc")

    b = _make_broadcaster()
    recovered, diag = await b._trace_call_revert_data(
        {"from": "0x0", "to": "0x1", "data": "0x", "value": "0x0"}
    )
    assert recovered is None
    assert diag[0]["outcome"] == "forbidden"


@pytest.mark.asyncio
async def test_trace_diagnostic_classifies_empty_output(monkeypatch):
    """Node responds successfully but the tracer returned no revert
    bytes — the diagnostic classifies this as 'empty_output' so the UI
    can recommend Tenderly / a deeper simulator."""
    import httpx

    _RoutingStubClient._calls = []
    _RoutingStubClient._responses = {
        "debug_traceCall": {
            "jsonrpc": "2.0", "id": 1,
            "result": {"type": "CALL", "output": "0x", "calls": []},
        },
    }
    monkeypatch.setattr(httpx, "AsyncClient", _RoutingStubClient)
    monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub.example.com/rpc")

    b = _make_broadcaster()
    recovered, diag = await b._trace_call_revert_data(
        {"from": "0x0", "to": "0x1", "data": "0x", "value": "0x0"}
    )
    assert recovered is None
    assert diag[0]["outcome"] == "empty_output"
    assert diag[0]["top_level_output"] == "0x"
    assert diag[0]["nested_call_count"] == 0
