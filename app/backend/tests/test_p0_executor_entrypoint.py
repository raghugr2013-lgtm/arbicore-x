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
    return asyncio.get_event_loop().run_until_complete(c)


def test_build_entrypoint_calldata():
    out = build_executor_entrypoint_calldata(
        borrow_token=WETH, borrow_amount_wei=10**16,
        settlement_target=ROUTER, settlement_calldata_hex="0xabcdef")
    sig = "executeArbitrage(address,uint256,address,bytes)"
    assert out["selector"] == "0x" + keccak(text=sig)[:4].hex()
    assert out["calldata"].startswith(out["selector"])
    assert out["signed"] is False and out["broadcast"] is False
    assert out["settlement_target"].lower() == ROUTER.lower()


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
