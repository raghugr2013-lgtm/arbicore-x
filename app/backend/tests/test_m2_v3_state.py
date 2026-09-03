"""M2 — V3 state ingestion tests (offline, deterministic; no RPC/network).

Covers: sqrtPriceX96 conversion, V3 event decoding (Swap/Mint/Burn/Initialize),
live PoolState updates, tick handling, Mint/Burn in-range liquidity, slot0/
liquidity bootstrap, stale-block refusal, and fail-closed on malformed data.
"""
from __future__ import annotations

import asyncio

from eth_abi import encode as abi_encode
from eth_utils import keccak

from arbicore.searcher import v3_state as v3
from arbicore.searcher.pool_cache import PoolStateCache, PoolState


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _addr32(a: str) -> str:
    return "0x" + a.lower().replace("0x", "").rjust(64, "0")


def _swap_log(pool, sqrtp, liq, tick, block=100):
    data = abi_encode(["int256", "int256", "uint160", "uint128", "int24"],
                      [-1000, 2000, int(sqrtp), int(liq), int(tick)])
    return {"address": pool, "blockNumber": hex(block),
            "data": "0x" + data.hex(),
            "topics": [v3.V3_SWAP_TOPIC0, _addr32("0x1"), _addr32("0x2")]}


def _mint_log(pool, amount, tl, tu, block=101):
    data = abi_encode(["address", "uint128", "uint256", "uint256"],
                      ["0x000000000000000000000000000000000000dEaD",
                       int(amount), 1, 1])
    tl32 = "0x" + (tl & (2**256 - 1)).to_bytes(32, "big").hex()
    tu32 = "0x" + (tu & (2**256 - 1)).to_bytes(32, "big").hex()
    return {"address": pool, "blockNumber": hex(block),
            "data": "0x" + data.hex(),
            "topics": [v3.V3_MINT_TOPIC0, _addr32("0xabc"), tl32, tu32]}


def _burn_log(pool, amount, tl, tu, block=102):
    data = abi_encode(["uint128", "uint256", "uint256"], [int(amount), 1, 1])
    tl32 = "0x" + (tl & (2**256 - 1)).to_bytes(32, "big").hex()
    tu32 = "0x" + (tu & (2**256 - 1)).to_bytes(32, "big").hex()
    return {"address": pool, "blockNumber": hex(block),
            "data": "0x" + data.hex(),
            "topics": [v3.V3_BURN_TOPIC0, _addr32("0xabc"), tl32, tu32]}


def _init_log(pool, sqrtp, tick, block=99):
    data = abi_encode(["uint160", "int24"], [int(sqrtp), int(tick)])
    return {"address": pool, "blockNumber": hex(block),
            "data": "0x" + data.hex(), "topics": [v3.V3_INIT_TOPIC0]}


# ── sqrtPriceX96 conversion ─────────────────────────────────────────────────
def test_sqrtx96_roundtrip():
    raw_sqrt = 2.5
    x96 = int(raw_sqrt * (2 ** 96))
    assert abs(v3.sqrtx96_to_sqrt_p(x96) - raw_sqrt) < 1e-9


def test_sqrtx96_zero_and_negative_fail_closed():
    assert v3.sqrtx96_to_sqrt_p(0) == 0.0
    assert v3.sqrtx96_to_sqrt_p(-5) == 0.0


def test_human_price_recovers_expected_usdc_per_weth():
    # WETH(18)=token0, USDC(6)=token1 ; target 3000 USDC per WETH.
    # raw price = token1_wei/token0_wei = 3000 * 1e6 / 1e18 = 3e-9
    raw_price = 3000 * (10 ** 6) / (10 ** 18)
    x96 = int((raw_price ** 0.5) * (2 ** 96))
    human = v3.human_price_token1_per_token0(x96, dec0=18, dec1=6)
    assert abs(human - 3000) / 3000 < 1e-3


def test_topic_constants_match_keccak():
    assert v3.V3_SWAP_TOPIC0 == "0x" + keccak(
        text="Swap(address,address,int256,int256,uint160,uint128,int24)").hex()
    assert v3.V3_INIT_TOPIC0 == "0x" + keccak(
        text="Initialize(uint160,int24)").hex()


# ── V3 event decoding ───────────────────────────────────────────────────────
def test_decode_swap():
    x96 = int(2.0 * (2 ** 96))
    dec = v3.decode_v3_log(_swap_log("0xPOOL", x96, 123456, -42))
    assert dec["event"] == "Swap"
    assert dec["pool"] == "0xpool"
    assert abs(dec["sqrt_p"] - 2.0) < 1e-9
    assert dec["liquidity"] == 123456.0
    assert dec["tick"] == -42
    assert dec["block"] == 100


def test_decode_mint_and_burn_signed_ticks():
    m = v3.decode_v3_log(_mint_log("0xP", 5000, -100, 200))
    assert m["event"] == "Mint" and m["liquidity_delta"] == 5000.0
    assert m["tick_lower"] == -100 and m["tick_upper"] == 200
    bn = v3.decode_v3_log(_burn_log("0xP", 4000, -100, 200))
    assert bn["event"] == "Burn" and bn["liquidity_delta"] == -4000.0


def test_decode_initialize():
    x96 = int(1.5 * (2 ** 96))
    dec = v3.decode_v3_log(_init_log("0xP", x96, 7))
    assert dec["event"] == "Initialize" and dec["tick"] == 7
    assert abs(dec["sqrt_p"] - 1.5) < 1e-9


def test_decode_non_v3_returns_none():
    assert v3.decode_v3_log({"topics": ["0xdeadbeef"], "data": "0x"}) is None
    assert v3.decode_v3_log({"topics": [], "data": "0x"}) is None


def test_decode_malformed_fail_closed():
    bad = {"address": "0xP", "blockNumber": "0x1",
           "topics": [v3.V3_SWAP_TOPIC0], "data": "0x1234"}
    assert v3.decode_v3_log(bad) is None


# ── Live PoolState updates via cache.apply_log ──────────────────────────────
def test_swap_updates_live_state_and_quote():
    c = PoolStateCache(max_staleness_blocks=10)
    c.upsert(PoolState(pool="0xp", kind="v3", token0="WETH", token1="USDC",
                       fee_bps=5, block=100))
    c.apply_log(v3.decode_v3_log(_swap_log("0xp", int(2.0 * 2**96), 1_000_000, 5)))
    st = c.get("0xp")
    assert st.sqrt_p > 0 and st.liquidity == 1_000_000.0 and st.tick == 5
    out = c.quote("0xp", "WETH", 1.0)
    assert out is not None and out > 0


def test_mint_in_range_increases_liquidity_out_of_range_ignored():
    c = PoolStateCache(max_staleness_blocks=100)
    c.upsert(PoolState(pool="0xp", kind="v3", token0="WETH", token1="USDC",
                       fee_bps=5, block=1))
    c.apply_log(v3.decode_v3_log(_swap_log("0xp", int(2.0 * 2**96), 1000, 100)))
    # in-range mint (0..200 contains tick 100)
    c.apply_log(v3.decode_v3_log(_mint_log("0xp", 500, 0, 200)))
    assert c.get("0xp").liquidity == 1500.0
    # out-of-range mint (500..600 excludes tick 100) → unchanged
    c.apply_log(v3.decode_v3_log(_mint_log("0xp", 999, 500, 600)))
    assert c.get("0xp").liquidity == 1500.0
    # in-range burn reduces
    c.apply_log(v3.decode_v3_log(_burn_log("0xp", 300, 0, 200)))
    assert c.get("0xp").liquidity == 1200.0


def test_stale_block_refusal_after_head_advance():
    c = PoolStateCache(max_staleness_blocks=5)
    c.upsert(PoolState(pool="0xp", kind="v3", token0="WETH", token1="USDC",
                       fee_bps=5, liquidity=1000, sqrt_p=2.0, block=100))
    c.set_head_block(100)
    assert c.get("0xp") is not None
    c.set_head_block(110)                    # 10 > 5 → stale
    assert c.get("0xp") is None


def test_initialize_sets_sqrt_before_first_swap():
    c = PoolStateCache(max_staleness_blocks=100)
    c.upsert(PoolState(pool="0xp", kind="v3", token0="WETH", token1="USDC",
                       fee_bps=5, block=1))
    c.apply_log(v3.decode_v3_log(_init_log("0xp", int(1.5 * 2**96), 3)))
    assert abs(c.get("0xp").sqrt_p - 1.5) < 1e-9 and c.get("0xp").tick == 3


# ── slot0()/liquidity() bootstrap ───────────────────────────────────────────
def test_v3_state_initializer_reads_slot0_and_liquidity():
    x96 = int(2.0 * 2**96)
    slot0 = "0x" + abi_encode(
        ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"],
        [x96, 12, 0, 1, 1, 0, True]).hex()
    liq = "0x" + abi_encode(["uint128"], [777_000]).hex()

    async def fake_eth_call(to, data):
        if data == v3.SLOT0_SELECTOR:
            return slot0
        if data == v3.LIQUIDITY_SELECTOR:
            return liq
        return None

    init = v3.make_v3_state_initializer(fake_eth_call)
    st = _run(init(pool_address="0xPool", token0="WETH", token1="USDC",
                   fee_bps=5, block=200))
    assert st.kind == "v3" and st.liquidity == 777_000.0 and st.tick == 12
    assert abs(st.sqrt_p - 2.0) < 1e-9 and st.block == 200 and st.pool == "0xpool"


def test_v3_state_initializer_fail_closed_on_empty():
    async def empty(to, data):
        return None
    init = v3.make_v3_state_initializer(empty)
    assert _run(init(pool_address="0xP", token0="A", token1="B",
                     fee_bps=5, block=1)) is None
