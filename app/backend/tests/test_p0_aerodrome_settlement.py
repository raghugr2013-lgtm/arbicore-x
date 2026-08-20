"""P0-3 — Allowlisted Aerodrome on-chain settlement adapter (no signing/broadcast)."""
import pytest

from arbicore.execution.aerodrome_settlement import (
    AerodromeSettlementAdapter, AerodromeSettlementError,
    AERODROME_ROUTER, AERODROME_POOL_FACTORY,
)
from eth_utils import keccak

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DAI = "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"
SELECTOR = "0x" + keccak(text=("swapExactTokensForTokens(uint256,uint256,"
                                "(address,address,bool,address)[],address,uint256)"))[:4].hex()


def _adapter():
    return AerodromeSettlementAdapter(
        token_allowlist=[WETH, USDC, DAI], router_allowlist=[AERODROME_ROUTER])


def test_encode_single_hop_produces_real_calldata():
    out = _adapter().encode_settlement(
        hops=[{"token_in": WETH, "token_out": USDC, "stable": False}],
        amount_in_wei=10**16, min_amount_out_wei=22_000_000,
        recipient="0x0000000000000000000000000000000000000001", deadline=1_900_000_000)
    assert out["to"].lower() == AERODROME_ROUTER.lower()
    assert out["data"].startswith(SELECTOR)
    assert len(out["data"]) > 200          # non-trivial ABI payload
    assert out["value_wei"] == 0
    assert out["signed"] is False and out["broadcast"] is False
    assert out["route_hops"][0]["factory"].lower() == AERODROME_POOL_FACTORY.lower()


def test_multi_hop_chaining_and_stable_flags():
    out = _adapter().encode_settlement(
        hops=[{"token_in": WETH, "token_out": USDC, "stable": False},
              {"token_in": USDC, "token_out": DAI, "stable": True}],
        amount_in_wei=10**16, min_amount_out_wei=1,
        recipient="0x0000000000000000000000000000000000000001", deadline=1_900_000_000)
    assert len(out["route_hops"]) == 2
    assert out["route_hops"][1]["stable"] is True


def test_rejects_non_chaining_hops():
    with pytest.raises(AerodromeSettlementError):
        _adapter().encode_settlement(
            hops=[{"token_in": WETH, "token_out": USDC},
                  {"token_in": DAI, "token_out": WETH}],   # USDC != DAI
            amount_in_wei=10**16, min_amount_out_wei=1,
            recipient="0x0000000000000000000000000000000000000001", deadline=1)


def test_rejects_non_allowlisted_token():
    with pytest.raises(AerodromeSettlementError):
        _adapter().encode_settlement(
            hops=[{"token_in": WETH, "token_out": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}],
            amount_in_wei=10**16, min_amount_out_wei=1,
            recipient="0x0000000000000000000000000000000000000001", deadline=1)


def test_rejects_arbitrary_target_router():
    with pytest.raises(AerodromeSettlementError):
        _adapter().encode_settlement(
            hops=[{"token_in": WETH, "token_out": USDC}],
            amount_in_wei=10**16, min_amount_out_wei=1,
            recipient="0x0000000000000000000000000000000000000001", deadline=1,
            router="0x1111111111111111111111111111111111111111")


def test_rejects_nonpositive_amounts():
    with pytest.raises(AerodromeSettlementError):
        _adapter().encode_settlement(
            hops=[{"token_in": WETH, "token_out": USDC}],
            amount_in_wei=0, min_amount_out_wei=1,
            recipient="0x0000000000000000000000000000000000000001", deadline=1)


def test_self_test_passes():
    st = AerodromeSettlementAdapter().self_test()
    assert st["passed"] is True
    assert st["selector"] == SELECTOR
