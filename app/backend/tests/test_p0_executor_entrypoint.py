"""P0 — Executor entrypoint calldata + Anvil fork harness scaffold."""
import asyncio
from eth_utils import keccak

from arbicore.execution.executor_entrypoint import (
    build_executor_entrypoint_calldata, AnvilForkHarness,
)
from arbicore.execution.atomic_executor_sim import AtomicExecutorSimulator

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"


def _run(c):
    """Isolated event loop per call — deterministic regardless of pytest's
    asyncio test ordering. ``asyncio.get_event_loop()`` can return a loop that a
    prior test already closed; a fresh loop makes these tests order-independent."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_legacy_arbitrary_calldata_path_is_fail_closed():
    """DEPRECATED_PATH replaced: the legacy ``build_executor_entrypoint_calldata``
    used to encode an arbitrary ``target + calldata`` settlement call
    (``executeArbitrage(address,uint256,address,bytes)``). That arbitrary-call
    surface is intentionally removed (Freeze security boundary). The wrapper must
    now FAIL CLOSED for the canonical Balancer shape instead of inventing a
    tokens[]/amounts[] layout. This asserts the guard is active — not green by
    removal."""
    import pytest
    with pytest.raises(ValueError):
        build_executor_entrypoint_calldata(
            borrow_token=WETH, borrow_amount_wei=10**16,
            settlement_target=ROUTER, settlement_calldata_hex="0xabcdef")


def test_canonical_v2_entrypoint_calldata_deterministic():
    """Current canonical behaviour: typed V2 userData + Balancer execute() head
    (selector 0x64ba4bc1, preserved from V1), deterministic, never signed and
    never broadcast. This is real coverage of the canonical path — the legacy
    arbitrary surface stays disabled above."""
    from arbicore.execution import calldata_v2 as C2

    FAR = 2 ** 40
    hop = {"venue": "uniswap_v3", "router": ROUTER, "token_in": USDC,
           "token_out": WETH, "fee_or_tick_spacing": 500,
           "amount_in_wei": 1000, "amount_out_min_wei": 0, "deadline": FAR}
    ud1 = C2.build_user_data_v2(hops=[hop], profit_recipient=WETH,
                                min_profit_wei=0, deadline=FAR)
    ud2 = C2.build_user_data_v2(hops=[hop], profit_recipient=WETH,
                                min_profit_wei=0, deadline=FAR)
    assert ud1 == ud2  # deterministic

    call1 = C2.encode_execute_balancer_v2(tokens=[USDC], amounts=[1000], user_data_hex=ud1)
    call2 = C2.encode_execute_balancer_v2(tokens=[USDC], amounts=[1000], user_data_hex=ud1)
    assert call1.calldata_hex == call2.calldata_hex
    assert call1.selector_hex == "0x64ba4bc1"
    assert call1.calldata_hex.startswith("0x64ba4bc1")
    # Encoders are pure calldata builders — no signing/broadcast side effects.
    assert getattr(call1, "value_wei", 0) == 0


def test_fork_harness_readiness_no_fake_green():
    rd = AnvilForkHarness(fork_rpc_url=None).readiness()
    assert rd["ready_to_run"] is False
    assert rd["reason"]
    out = _run(AnvilForkHarness(fork_rpc_url=None).run_fork_validation())
    assert out["ran"] is False and out["passed"] is False


def test_atomic_sim_gated_on_signer_even_with_executor():
    s = AtomicExecutorSimulator(rpc_url="http://x",
                                executor_address="0x91c0bf28E32b76889BB2B61E1A2dDE9F7e4f3DE3")
    out = _run(s.simulate_atomic(entry_calldata="0x1234", signer_present=False))
    assert out["available"] is False and "signer" in out["reason"].lower()
