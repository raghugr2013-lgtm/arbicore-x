"""ArbiCore X — NON-LIVE fork-equivalent execution proof against live Base state.

CERTIFICATION · NON-LIVE · SYNTHETIC/CONTROLLED · read-only.

Runs the REAL production execution components against **live Base mainnet state**
via read-only ``eth_call`` (a fork-equivalent at the latest block — no local Anvil
required, no deployment, no signing, no broadcast, no mainnet transaction):

  * chain verification            (eth_chainId == 8453)
  * state-override capability      (AtomicExecutorSimulator.capability_self_test)
  * live UniV3 quote               (UniV3QuoterV2 against real pools)
  * route + swap + repayment       (SettlementSimulator — real Aerodrome getAmountsOut)
  * economic gate + $25 floor       (economics.net_profit.compute_net_profit)
  * atomic executor receiver path   (Balancer V2 borrow + UniV3 swap) — reported
                                    BLOCKED unless a MAINNET-immutable receiver
                                    runtime bytecode is supplied (never faked)
  * fail-closed refusals            (unsupported provider, signer/bytecode absent)

RPC precedence: ARBICORE_FORK_RPC > ARBICORE_RPC_URL_BASE > https://mainnet.base.org
A block number is pinned at start for reproducibility labelling (public RPC is not
archive, so exact historical replay later needs an archive endpoint).

Writes gitignored evidence to ``vps_cert_out/fork_cert_evidence.json``. NEVER marks
real mainnet EXECUTION-CERTIFIED / ECONOMICALLY-VALID / Limited-Live / Full-Live.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

import httpx

from arbicore.execution.atomic_executor_sim import AtomicExecutorSimulator
from arbicore.execution.settlement_simulator import SettlementSimulator
from arbicore.execution.quoter import UniV3QuoterV2
from arbicore.execution.receiver_capability import receiver_supports
from arbicore.economics.net_profit import compute_net_profit

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
GATE7_FLOOR_USD = 25.0

LABEL = {
    "classification": "CERTIFICATION", "live": False, "candidate": "SYNTHETIC/CONTROLLED",
    "environment": "read-only eth_call against LIVE Base mainnet state (fork-equivalent latest block)",
    "is_real_profitable_opportunity": False,
    "is_economically_valid_market_opportunity": False,
    "signing": "OFF", "broadcast": "OFF", "auto_execution": "OFF",
    "limited_live": "OFF", "full_live": "OFF", "withdrawals": "OFF",
    "mainnet_receiver_deployed": False,
}


def _rpc() -> str:
    return (os.environ.get("ARBICORE_FORK_RPC")
            or os.environ.get("ARBICORE_RPC_URL_BASE")
            or "https://mainnet.base.org")


async def _block_number(rpc: str) -> int:
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.post(rpc, json={"jsonrpc": "2.0", "id": 1,
                                    "method": "eth_blockNumber", "params": []})
    return int(r.json()["result"], 16)


async def _chain_id(rpc: str) -> int:
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.post(rpc, json={"jsonrpc": "2.0", "id": 1,
                                    "method": "eth_chainId", "params": []})
    return int(r.json()["result"], 16)


async def run() -> Dict[str, Any]:
    rpc = _rpc()
    stages: Dict[str, Any] = {}
    latency_ms: Dict[str, float] = {}

    def _timed(name):
        t0 = time.perf_counter()
        def done():
            latency_ms[name] = round((time.perf_counter() - t0) * 1000.0, 3)
        return done

    # 0. pin block + chain verification
    d = _timed("chain_verification")
    block = await _block_number(rpc)
    cid = await _chain_id(rpc)
    stages["chain_verification"] = {"chain_id": cid, "expected": 8453,
                                    "passed": cid == 8453, "pinned_block": block}
    d()

    # 1. state-override capability (prerequisite for atomic sim)
    d = _timed("state_override_capability")
    atomic = AtomicExecutorSimulator(rpc_url=rpc)
    cap = await atomic.capability_self_test()
    stages["state_override_capability"] = cap
    d()

    # 2. live UniV3 quote (real quoter, real pool state)
    d = _timed("live_univ3_quote")
    q = UniV3QuoterV2()
    hop = await q.quote_hop(hop_index=0, chain="base", token_in=WETH, token_out=USDC,
                            amount_in_wei=10 ** 18,
                            hop_spec={"fee": 500}, rpc_url=rpc)
    hop_status = getattr(hop, "status", None)
    amt_out = getattr(hop, "amount_out_wei", None)
    hop_ok = (hop_status == "ok") and bool(amt_out)
    stages["live_univ3_quote"] = {
        "dex": "uniswap_v3", "token_in": "WETH", "token_out": "USDC",
        "amount_in_wei": 10 ** 18, "amount_out": str(amt_out) if amt_out is not None else None,
        "ok": hop_ok, "status": hop_status,
        "price_impact_bps": getattr(hop, "price_impact_bps", None),
        "block_number": getattr(hop, "block_number", None),
    }
    d()

    # 3. route + swap + repayment (real SettlementSimulator on live state)
    d = _timed("settlement_route_swap_repayment")
    sim = SettlementSimulator(rpc_url=rpc)
    settle = await sim.self_test()
    stages["settlement_route_swap_repayment"] = settle
    d()

    # 4. economic gate + $25 floor (real engine bridged from a controlled candidate)
    d = _timed("economics")
    econ = compute_net_profit(
        gross_spread_bps=25.0, notional_usd=2500.0,
        buy_venue_fee_bps=5.0, sell_venue_fee_bps=5.0,
        gas_native_wei=10 ** 9, native_price_usd=2500.0, estimated_gas_units=350_000,
        slippage_bps=3.0, flash_loan_notional_usd=2500.0, liquidity_impact_bps=2.0,
    )
    stages["economics"] = {
        "synthetic_net_profit_usd": econ.net_profit_usd,
        "total_cost_usd": econ.total_cost_usd,
        "clears_gate7_floor": econ.net_profit_usd >= GATE7_FLOOR_USD,
        "note": "SYNTHETIC candidate — NOT a real market edge; $25 floor unchanged",
    }
    d()

    # 5. atomic executor receiver path (Balancer V2 borrow + UniV3 swap) — honest boundary
    d = _timed("atomic_executor_receiver_path")
    receiver_bytecode = os.environ.get("ARBICORE_MAINNET_RECEIVER_RUNTIME_BYTECODE")
    receiver_addr = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    if receiver_bytecode and receiver_addr:
        a2 = AtomicExecutorSimulator(rpc_url=rpc, executor_address=receiver_addr,
                                     executor_bytecode=receiver_bytecode)
        entry = os.environ.get("ARBICORE_FORK_ENTRY_CALLDATA", "0x64ba4bc1")
        res = await a2.simulate_atomic(entry_calldata=entry, signer_present=True,
                                       from_address="0x0000000000000000000000000000000000000001",
                                       block_tag=hex(block))
        stages["atomic_executor_receiver_path"] = {**res, "status": "FORK_TESTED"}
    else:
        stages["atomic_executor_receiver_path"] = {
            "available": False, "passed": False, "status": "BLOCKED",
            "reason": ("no MAINNET-immutable receiver runtime bytecode supplied "
                       "(ARBICORE_MAINNET_RECEIVER_RUNTIME_BYTECODE) and/or executor "
                       "address; repo only carries Sepolia creation bytecode whose "
                       "immutables (aavePool/uniRouter) are wrong for mainnet — "
                       "injecting it would be invalid, so the full atomic "
                       "Balancer-borrow+UniV3-swap-through-receiver path is BLOCKED. "
                       "Not faked."),
        }
    d()

    # 6. fail-closed refusals against real capability
    d = _timed("fail_closed")
    atomic_no_signer = await AtomicExecutorSimulator(
        rpc_url=rpc, executor_address="0x00000000000000000000000000000000000ce111"
    ).simulate_atomic(entry_calldata="0x64ba4bc1", signer_present=False)
    stages["fail_closed"] = {
        "receiver_supports_balancer_v2_base": receiver_supports("base", "balancer_v2"),
        "atomic_sim_signer_absent_available": atomic_no_signer.get("available"),
    }
    d()

    evidence = {
        "label": LABEL, "rpc_host": rpc.split("//")[-1].split("/")[0],
        "pinned_block": block, "stages": stages, "latency_ms": latency_ms,
        "capability_changes": {
            "chain_verification": "FORK-TESTED" if stages["chain_verification"]["passed"] else "BLOCKED",
            "state_override_capability": "FORK-TESTED" if cap.get("code_injection") else "BLOCKED",
            "live_univ3_quote": "FORK-TESTED" if stages["live_univ3_quote"]["ok"] else "BLOCKED",
            "route_swap_repayment_economics": "FORK-TESTED" if settle.get("ran") else "BLOCKED",
            "atomic_executor_receiver_path": stages["atomic_executor_receiver_path"]["status"],
            "mainnet_execution_certified": "FALSE (unchanged)",
            "economically_valid_real": "0 (unchanged)",
            "limited_live_eligible": "NO", "full_live_eligible": "NO",
        },
    }
    return evidence


def main() -> Dict[str, Any]:
    evidence = asyncio.new_event_loop().run_until_complete(run())
    out_dir = Path(__file__).resolve().parents[3] / "vps_cert_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fork_cert_evidence.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))
    return evidence


if __name__ == "__main__":
    main()
