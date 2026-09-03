"""Independent ABI decode verification of make_calldata_tx_builder output.

Not part of the pytest suite — invoked directly by the testing agent.
"""
import asyncio
from eth_abi import decode as abi_decode

from arbicore.searcher.pool_cache import PoolStateCache, PoolState
from arbicore.searcher.route import Edge
from arbicore.searcher.revm_backend import make_calldata_tx_builder


WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
EXEC = "0x1111111111111111111111111111111111111111"
FROM = "0x2222222222222222222222222222222222222222"
POOL_A = "0xaaaa000000000000000000000000000000000001"
POOL_B = "0xbbbb000000000000000000000000000000000002"


def _put(cache, pool_addr, t0, t1, fee_bps):
    st = PoolState(pool=pool_addr, kind="v3", token0=t0, token1=t1,
                   fee_bps=fee_bps, block=1)
    cache.upsert(st)


async def main():
    cache = PoolStateCache()
    _put(cache, POOL_A, "WETH", "USDC", 5)   # 5 bps -> 500 ppm
    _put(cache, POOL_B, "USDC", "WETH", 30)  # 30 bps -> 3000 ppm

    tx_builder = make_calldata_tx_builder(
        cache=cache,
        executor_address=EXEC,
        from_address=FROM,
        profit_recipient=FROM,
        token_addresses={"WETH": WETH, "USDC": USDC},
        token_decimals={"WETH": 18, "USDC": 6},
        chain="base",
    )

    cycle = [
        Edge(pool=POOL_A, token_in="WETH", token_out="USDC"),
        Edge(pool=POOL_B, token_in="USDC", token_out="WETH"),
    ]
    tx = await tx_builder(cycle, 1.5)  # 1.5 WETH
    print("TX keys:", sorted(tx.keys()))
    print("to:", tx["to"])
    print("from:", tx["from"])
    print("value:", tx["value"])
    assert tx["value"] == "0x0"
    assert tx["to"].lower() == EXEC.lower()
    assert tx["from"].lower() == FROM.lower()

    data = tx["data"]
    assert data.startswith("0x")
    selector = data[:10]
    print("selector:", selector)
    assert selector == "0x64ba4bc1", f"expected canonical execute selector, got {selector}"

    body = bytes.fromhex(data[10:])
    tokens, amounts, user_data = abi_decode(
        ["address[]", "uint256[]", "bytes"], body,
    )
    print("tokens:", tokens)
    print("amounts:", amounts)
    assert [t.lower() for t in tokens] == [WETH.lower()]
    assert list(amounts) == [int(1.5 * 10**18)]

    hops, profit_recipient = abi_decode(
        ["(address,address,uint24,uint256,uint256,uint160)[]", "address"],
        user_data,
    )
    print("profit_recipient:", profit_recipient)
    print("hops:", hops)
    assert profit_recipient.lower() == FROM.lower()
    assert len(hops) == 2

    # Hop 0: WETH->USDC, feePpm=500 (5 bps * 100), amountIn = 1.5e18
    h0_in, h0_out, h0_fee, h0_amt, h0_min, h0_sqrt = hops[0]
    assert h0_in.lower() == WETH.lower()
    assert h0_out.lower() == USDC.lower()
    assert h0_fee == 500
    assert h0_amt == int(1.5 * 10**18)
    assert h0_min == 0
    assert h0_sqrt == 0

    # Hop 1: USDC->WETH, feePpm=3000, amountIn=0 (forward)
    h1_in, h1_out, h1_fee, h1_amt, _, _ = hops[1]
    assert h1_in.lower() == USDC.lower()
    assert h1_out.lower() == WETH.lower()
    assert h1_fee == 3000
    assert h1_amt == 0

    # Determinism
    tx2 = await tx_builder(cycle, 1.5)
    assert tx == tx2, "non-deterministic output!"

    # Fail-closed: empty cycle
    try:
        await tx_builder([], 1.0)
        raise SystemExit("EXPECTED ValueError on empty cycle")
    except ValueError as e:
        print("empty cycle -> ValueError OK:", e)

    # Fail-closed: unmapped symbol
    bad_builder = make_calldata_tx_builder(
        cache=cache,
        executor_address=EXEC,
        from_address=FROM,
        token_addresses={"WETH": WETH},  # missing USDC
        token_decimals={"WETH": 18},
    )
    try:
        await bad_builder(cycle, 1.0)
        raise SystemExit("EXPECTED ValueError on unmapped token")
    except ValueError as e:
        print("unmapped token -> ValueError OK:", e)

    # Fail-closed: no executor
    import os
    os.environ.pop("ARBICORE_EXECUTOR_ADDRESS_BASE", None)
    no_exec = make_calldata_tx_builder(
        cache=cache,
        from_address=FROM,
        token_addresses={"WETH": WETH, "USDC": USDC},
        token_decimals={"WETH": 18, "USDC": 6},
    )
    try:
        await no_exec(cycle, 1.0)
        raise SystemExit("EXPECTED ValueError on missing executor")
    except ValueError as e:
        print("missing executor -> ValueError OK:", e)

    print("\nALL INDEPENDENT ABI CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
