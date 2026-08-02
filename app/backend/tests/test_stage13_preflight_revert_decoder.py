"""Stage 13 preflight revert-decoder tests.

Covers:
    * ``decode_revert_data`` — selector → human name for the LIMITED_LIVE
      contract stack (FlashLoanReceiver, Balancer, Uniswap V3, Error(string),
      Panic, ERC20).
    * ``BroadcastError.revert_data`` — the JSON-RPC ``error.data`` field
      (containing the on-chain revert selector) is preserved on the raised
      exception rather than being flattened into a message string.
"""
from __future__ import annotations

import pytest

from arbicore.execution.broadcast import (
    BroadcastError,
    LimitedLiveBroadcaster,
    decode_revert_data,
)


# -------------------------------------------------------------------------- #
# decode_revert_data                                                          #
# -------------------------------------------------------------------------- #

class TestDecodeRevertData:
    def test_flash_loan_receiver_not_authorized(self):
        assert decode_revert_data("0xea8e4eb5") == \
            "FlashLoanReceiver.NotAuthorized()"

    def test_flash_loan_receiver_not_owner(self):
        assert decode_revert_data("0x30cd7471") == \
            "FlashLoanReceiver.NotOwner()"

    def test_uniswap_v3_too_little_received(self):
        assert decode_revert_data("0x39d35496") == \
            "UniV3.V3TooLittleReceived()"

    def test_solidity_error_string_extracts_payload(self):
        # Selector 0x08c379a0 + abi-encoded string "STF"
        # eth_abi encoding of ("STF",) as bytes.
        from eth_abi import encode
        payload = encode(["string"], ["STF"])
        data = "0x08c379a0" + payload.hex()
        result = decode_revert_data(data)
        assert result.startswith("Error(string)")
        assert "'STF'" in result

    def test_panic_selector(self):
        assert decode_revert_data("0x4e487b71") == \
            "Panic(uint256)   [Solidity assert/overflow/etc.]"

    def test_unknown_selector_surfaces_hex(self):
        r = decode_revert_data("0xdeadbeef")
        assert r == "unknown selector 0xdeadbeef"

    def test_empty_data_returns_none(self):
        assert decode_revert_data("") is None
        assert decode_revert_data(None) is None

    def test_missing_0x_prefix_returns_none(self):
        assert decode_revert_data("ea8e4eb5") is None

    def test_case_insensitive_selector(self):
        # Upper-case hex still decodes.
        assert decode_revert_data("0xEA8E4EB5") == \
            "FlashLoanReceiver.NotAuthorized()"


# -------------------------------------------------------------------------- #
# BroadcastError.revert_data preservation                                     #
# -------------------------------------------------------------------------- #

class TestBroadcastErrorPreservesRevertData:
    """Assert the RPC's ``error.data`` field is attached to the raised
    exception (rather than being flattened into an unstructured string).

    Uses a synthetic broadcaster with a stubbed httpx client so no real
    RPC call is made.
    """

    @pytest.mark.asyncio
    async def test_rpc_error_data_is_attached_to_exception(self, monkeypatch):
        import httpx

        class _StubResponse:
            def __init__(self, body):
                self._body = body
            def json(self):
                return self._body
            def raise_for_status(self):
                pass

        class _StubClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def post(self, url, json):
                return _StubResponse({
                    "jsonrpc": "2.0", "id": 1,
                    "error": {
                        "code": 3,
                        "message": "execution reverted",
                        "data": "0xea8e4eb5",
                    },
                })

        monkeypatch.setattr(httpx, "AsyncClient", _StubClient)
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub.example.com/rpc")

        b = LimitedLiveBroadcaster(
            kill_switch=None, mode_repo=None, wallet_registry=None,
            secret_registry=None, capital_allocator=None,
        )

        with pytest.raises(BroadcastError) as exc_info:
            await b._rpc("eth_call", [{"to": "0x0", "data": "0x"}, "latest"])

        exc = exc_info.value
        # The full error dict is in the message …
        assert "execution reverted" in str(exc)
        # … AND `revert_data` is accessible as an attribute (this is what
        # the receipt / operator UI consumes).
        assert getattr(exc, "revert_data", None) == "0xea8e4eb5"
        assert decode_revert_data(exc.revert_data) == \
            "FlashLoanReceiver.NotAuthorized()"

    @pytest.mark.asyncio
    async def test_rpc_error_without_data_still_raises_cleanly(self, monkeypatch):
        import httpx

        class _StubResponse:
            def __init__(self, body): self._body = body
            def json(self): return self._body
            def raise_for_status(self): pass

        class _StubClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def post(self, url, json):
                return _StubResponse({
                    "jsonrpc": "2.0", "id": 1,
                    "error": {"code": 3, "message": "execution reverted"},
                })

        monkeypatch.setattr(httpx, "AsyncClient", _StubClient)
        monkeypatch.setenv("ARBICORE_RPC_URL", "https://stub.example.com/rpc")

        b = LimitedLiveBroadcaster(
            kill_switch=None, mode_repo=None, wallet_registry=None,
            secret_registry=None, capital_allocator=None,
        )

        with pytest.raises(BroadcastError) as exc_info:
            await b._rpc("eth_call", [{"to": "0x0", "data": "0x"}, "latest"])

        assert getattr(exc_info.value, "revert_data", "sentinel") is None
