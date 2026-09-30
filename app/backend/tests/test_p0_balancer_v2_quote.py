"""P0 — Balancer V2 pool discovery + queryBatchSwap quote adapter.

Offline, fail-closed contract tests. No real RPC, no signing, no broadcast.
The injected ``eth_call`` is a scripted fake so every negative path (RPC/HTTP
faults, reverts, malformed data, stale/unknown pools, insufficient liquidity,
unknown fee/decimals, route mismatch) is exercised deterministically.

RUNTIME-VERIFICATION-PENDING: these tests prove the ADAPTER contract only. Real
six-chain live pool discovery + quoting must be validated read-only on the VPS.
"""
from __future__ import annotations

import httpx
import pytest
from eth_abi import encode as abi_encode
from eth_utils import to_checksum_address

import arbicore.discovery.balancer_v2_pool_discovery as bal
from arbicore.discovery.balancer_v2_pool_discovery import (
    BALANCER_V2_VAULT_BY_CHAIN, SEL_GET_POOL_ID, SEL_GET_POOL_TOKENS,
    SEL_GET_SWAP_FEE, SEL_DECIMALS, SEL_QUERY_BATCH_SWAP,
    discover_pool, quote_single_swap, discover_and_quote,
)
from arbicore.execution.quoter import BalancerV2Quoter, QuoterRegistry

# ---- fixtures / constants ----------------------------------------------------

WETH = to_checksum_address("0x" + "11" * 20)
USDC = to_checksum_address("0x" + "22" * 20)
POOL = to_checksum_address("0x" + "ab" * 20)
# Balancer poolId embeds the pool address (20 bytes) + specialization (2 bytes)
# + nonce. Build a valid id for POOL.
POOL_ID = bytes.fromhex(POOL[2:]) + (0).to_bytes(2, "big") + (7).to_bytes(10, "big")
POOL_ID_HEX = "0x" + POOL_ID.hex()

VAULT = BALANCER_V2_VAULT_BY_CHAIN["ethereum"]

_ENC = {
    "get_pool_id": "0x" + abi_encode(["bytes32"], [POOL_ID]).hex(),
    "swap_fee": "0x" + abi_encode(["uint256"], [10 ** 15]).hex(),      # 0.1% = 10 bps
    "dec_weth": "0x" + abi_encode(["uint256"], [18]).hex(),
    "dec_usdc": "0x" + abi_encode(["uint256"], [6]).hex(),
}


def _pool_tokens(balances, last_change_block=1000, tokens=(WETH, USDC)):
    return "0x" + abi_encode(
        ["address[]", "uint256[]", "uint256"],
        [list(tokens), list(balances), last_change_block]).hex()


def _batch_swap(amount_in, amount_out):
    return "0x" + abi_encode(["int256[]"], [[int(amount_in), -int(amount_out)]]).hex()


class FakeChain:
    """Scripted eth_call over Balancer selectors. Override individual responses
    to simulate reverts / rpc errors / malformed data per scenario."""

    def __init__(self, *, balances=(5 * 10 ** 18, 20_000 * 10 ** 6),
                 amount_out=1900 * 10 ** 6, block=12345, last_change_block=1000):
        self.balances = balances
        self.amount_out = amount_out
        self.block = block
        self.last_change_block = last_change_block
        self.responses = {}   # (to_lower, selector) -> ("ok", hex) | ("revert", msg) | ("rpc", msg) | ("raise", exc) | ("raw", hex)
        self.calls = []

    def set(self, to, selector, mode, payload):
        self.responses[(to.lower(), selector)] = (mode, payload)

    async def __call__(self, to, data):
        selector = data[:10]
        self.calls.append((to, selector))
        override = self.responses.get((to.lower(), selector))
        if override is not None:
            mode, payload = override
            if mode == "raise":
                raise payload
            if mode == "revert":
                return None, None, {"code": 3, "message": f"execution reverted: {payload}"}
            if mode == "rpc":
                return None, None, {"code": -32000, "message": payload}
            if mode == "raw":
                return payload, self.block, None
            return payload, self.block, None
        # defaults
        if selector == SEL_GET_POOL_ID:
            return _ENC["get_pool_id"], self.block, None
        if selector == SEL_GET_POOL_TOKENS:
            return _pool_tokens(self.balances, self.last_change_block), self.block, None
        if selector == SEL_GET_SWAP_FEE:
            return _ENC["swap_fee"], self.block, None
        if selector == SEL_DECIMALS:
            return (_ENC["dec_weth"] if to.lower() == WETH.lower() else _ENC["dec_usdc"]), self.block, None
        if selector == SEL_QUERY_BATCH_SWAP:
            return _batch_swap(10 ** 18, self.amount_out), self.block, None
        return None, None, {"code": -32601, "message": "method not found"}


# ---- registration ------------------------------------------------------------

def test_backend_registered_in_registry():
    qr = QuoterRegistry()
    assert qr.supports("balancer_v2")
    assert "balancer_v2" in qr.supported_dexes


def test_vault_map_matches_calldata_single_source_of_truth():
    from arbicore.execution.calldata import BALANCER_V2_VAULT_BY_CHAIN as CALLDATA_MAP
    for chain, addr in BALANCER_V2_VAULT_BY_CHAIN.items():
        assert to_checksum_address(CALLDATA_MAP[chain]) == addr
    assert "bnb" not in BALANCER_V2_VAULT_BY_CHAIN  # Balancer V2 not on BNB → fail closed


# ---- happy path --------------------------------------------------------------

@pytest.mark.asyncio
async def test_discover_pool_happy_path_full_provenance():
    fc = FakeChain()
    disc = await discover_pool(fc, "ethereum", pool_address=POOL)
    assert disc.status == bal.OK
    m = disc.meta
    assert m.pool_id == POOL_ID_HEX
    assert m.pool_address == POOL
    assert m.vault == VAULT
    assert [t.address for t in m.tokens] == [WETH, USDC]          # ordering preserved
    assert [t.decimals for t in m.tokens] == [18, 6]              # token decimals
    assert [t.balance for t in m.tokens] == [5 * 10 ** 18, 20_000 * 10 ** 6]  # balances
    assert m.swap_fee_1e18 == 10 ** 15 and abs(m.swap_fee_bps - 10.0) < 1e-9   # fee → bps
    assert m.last_change_block == 1000 and m.query_block_number == 12345       # provenance


@pytest.mark.asyncio
async def test_quote_single_swap_happy_path_nets_fee():
    fc = FakeChain(amount_out=1901 * 10 ** 6)
    q = await discover_and_quote(fc, "ethereum", WETH, USDC, 10 ** 18, pool_address=POOL)
    assert q.status == bal.OK
    assert q.amount_out_wei == 1901 * 10 ** 6
    assert q.block_number == 12345
    assert q.deltas == [10 ** 18, -(1901 * 10 ** 6)]


@pytest.mark.asyncio
async def test_pool_id_input_derives_address():
    fc = FakeChain()
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.OK and disc.meta.pool_address == POOL
    # no getPoolId call needed when pool_id is supplied
    assert all(sel != SEL_GET_POOL_ID for _to, sel in fc.calls)


# ---- structural fail-closed --------------------------------------------------

@pytest.mark.asyncio
async def test_unsupported_chain_bnb_fails_closed():
    fc = FakeChain()
    disc = await discover_pool(fc, "bnb", pool_address=POOL)
    assert disc.status == bal.UNSUPPORTED_CHAIN
    assert fc.calls == []  # short-circuits before any RPC


@pytest.mark.asyncio
async def test_missing_pool_identity_fails_closed():
    fc = FakeChain()
    disc = await discover_pool(fc, "ethereum")
    assert disc.status == bal.MISSING_POOL_IDENTITY


@pytest.mark.asyncio
async def test_pool_id_address_mismatch_fails_closed():
    fc = FakeChain()
    other = to_checksum_address("0x" + "cd" * 20)
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX, pool_address=other)
    assert disc.status == bal.POOL_ID_MISMATCH


@pytest.mark.asyncio
async def test_getpoolid_returns_foreign_address_mismatch():
    fc = FakeChain()
    foreign = to_checksum_address("0x" + "ee" * 20)
    foreign_id = "0x" + (bytes.fromhex(foreign[2:]) + (0).to_bytes(12, "big")).hex()
    fc.set(POOL, SEL_GET_POOL_ID, "ok", foreign_id)
    disc = await discover_pool(fc, "ethereum", pool_address=POOL)
    assert disc.status == bal.POOL_ID_MISMATCH


@pytest.mark.asyncio
async def test_malformed_pool_id_fails_closed():
    fc = FakeChain()
    disc = await discover_pool(fc, "ethereum", pool_id="0x1234")  # not 32 bytes
    assert disc.status == bal.MALFORMED


# ---- discovery reverts / rpc / malformed -------------------------------------

@pytest.mark.asyncio
async def test_unknown_pool_getpooltokens_revert():
    fc = FakeChain()
    fc.set(VAULT, SEL_GET_POOL_TOKENS, "revert", "BAL#500")
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.UNKNOWN_POOL


@pytest.mark.asyncio
async def test_getpooltokens_empty_arrays_unknown_pool():
    fc = FakeChain()
    fc.set(VAULT, SEL_GET_POOL_TOKENS, "ok", _pool_tokens([], tokens=[]))
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.UNKNOWN_POOL


@pytest.mark.asyncio
async def test_rpc_failure_getpooltokens():
    fc = FakeChain()
    fc.set(VAULT, SEL_GET_POOL_TOKENS, "rpc", "node down")
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.RPC_ERROR


@pytest.mark.asyncio
async def test_rate_limited_classified_as_rpc():
    fc = FakeChain()
    fc.responses[(VAULT.lower(), SEL_GET_POOL_TOKENS)] = ("_rate", None)

    async def rl(to, data):
        if data[:10] == SEL_GET_POOL_TOKENS:
            return None, None, {"code": -32016, "message": "over rate limit"}
        return await FakeChain.__call__(fc, to, data)
    disc = await discover_pool(rl, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.RPC_ERROR


@pytest.mark.asyncio
async def test_malformed_getpooltokens_data():
    fc = FakeChain()
    fc.set(VAULT, SEL_GET_POOL_TOKENS, "raw", "0xdeadbeef")  # undecodable
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.MALFORMED


@pytest.mark.asyncio
async def test_unknown_fee_revert():
    fc = FakeChain()
    fc.set(POOL, SEL_GET_SWAP_FEE, "revert", "no fee")
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.UNKNOWN_FEE


@pytest.mark.asyncio
async def test_fee_out_of_range_fails_closed():
    fc = FakeChain()
    fc.set(POOL, SEL_GET_SWAP_FEE, "ok", "0x" + abi_encode(["uint256"], [10 ** 18]).hex())
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.UNKNOWN_FEE


@pytest.mark.asyncio
async def test_unknown_decimals_revert():
    fc = FakeChain()
    fc.set(USDC, SEL_DECIMALS, "revert", "no decimals")
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.UNKNOWN_DECIMALS


@pytest.mark.asyncio
async def test_decimals_out_of_range_fails_closed():
    fc = FakeChain()
    fc.set(USDC, SEL_DECIMALS, "ok", "0x" + abi_encode(["uint256"], [99]).hex())
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.UNKNOWN_DECIMALS


# ---- HTTP status faults (transport) → rpc_error ------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 403, 404, 500, 502, 503])
async def test_http_status_faults_fail_closed_as_rpc(code):
    fc = FakeChain()
    req = httpx.Request("POST", "http://rpc.invalid")
    resp = httpx.Response(status_code=code, request=req)
    fc.set(VAULT, SEL_GET_POOL_TOKENS, "raise",
           httpx.HTTPStatusError(f"{code}", request=req, response=resp))
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    assert disc.status == bal.RPC_ERROR


# ---- liquidity / route / staleness at quote time -----------------------------

@pytest.mark.asyncio
async def test_token_not_in_pool_route_mismatch():
    fc = FakeChain()
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    dai = to_checksum_address("0x" + "33" * 20)
    q = await quote_single_swap(fc, disc.meta, WETH, dai, 10 ** 18)
    assert q.status == bal.TOKEN_NOT_IN_POOL


@pytest.mark.asyncio
async def test_zero_balance_insufficient_liquidity():
    fc = FakeChain(balances=(0, 20_000 * 10 ** 6))
    q = await discover_and_quote(fc, "ethereum", WETH, USDC, 10 ** 18, pool_id=POOL_ID_HEX)
    assert q.status == bal.INSUFFICIENT_LIQUIDITY


@pytest.mark.asyncio
async def test_amount_out_exceeds_balance_insufficient_liquidity():
    fc = FakeChain(balances=(5 * 10 ** 18, 1000 * 10 ** 6), amount_out=2000 * 10 ** 6)
    q = await discover_and_quote(fc, "ethereum", WETH, USDC, 10 ** 18, pool_id=POOL_ID_HEX)
    assert q.status == bal.INSUFFICIENT_LIQUIDITY


@pytest.mark.asyncio
async def test_quote_revert_fails_closed():
    fc = FakeChain()
    fc.set(VAULT, SEL_QUERY_BATCH_SWAP, "revert", "BAL#304")
    q = await discover_and_quote(fc, "ethereum", WETH, USDC, 10 ** 18, pool_id=POOL_ID_HEX)
    assert q.status == bal.QUOTE_REVERT
    assert q.amount_out_wei == 0


@pytest.mark.asyncio
async def test_no_output_zero_delta_fails_closed():
    fc = FakeChain(amount_out=0)
    q = await discover_and_quote(fc, "ethereum", WETH, USDC, 10 ** 18, pool_id=POOL_ID_HEX)
    assert q.status == bal.NO_OUTPUT
    assert q.amount_out_wei == 0


@pytest.mark.asyncio
async def test_malformed_batchswap_deltas_fails_closed():
    fc = FakeChain()
    fc.set(VAULT, SEL_QUERY_BATCH_SWAP, "raw", "0x" + abi_encode(["int256[]"], [[123]]).hex())
    q = await discover_and_quote(fc, "ethereum", WETH, USDC, 10 ** 18, pool_id=POOL_ID_HEX)
    assert q.status == bal.MALFORMED


@pytest.mark.asyncio
async def test_zero_amount_in_no_output():
    fc = FakeChain()
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    q = await quote_single_swap(fc, disc.meta, WETH, USDC, 0)
    assert q.status == bal.NO_OUTPUT


@pytest.mark.asyncio
async def test_stale_pool_fails_closed():
    fc = FakeChain(last_change_block=100, block=100)
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    q = await quote_single_swap(fc, disc.meta, WETH, USDC, 10 ** 18,
                                current_block=1000, max_age_blocks=50)
    assert q.status == bal.STALE_POOL


@pytest.mark.asyncio
async def test_fresh_pool_not_stale():
    fc = FakeChain(last_change_block=990, block=990)
    disc = await discover_pool(fc, "ethereum", pool_id=POOL_ID_HEX)
    q = await quote_single_swap(fc, disc.meta, WETH, USDC, 10 ** 18,
                                current_block=1000, max_age_blocks=50)
    assert q.status == bal.OK


# ---- backend (BalancerV2Quoter.quote_hop) HopQuote mapping -------------------

@pytest.mark.asyncio
async def test_backend_unsupported_chain_no_adapter():
    q = BalancerV2Quoter()
    hop = await q.quote_hop(hop_index=0, chain="bnb", token_in=WETH, token_out=USDC,
                            amount_in_wei=10 ** 18, hop_spec={"pool_id": POOL_ID_HEX},
                            rpc_url="http://unused.invalid")
    assert hop.status == "fallback:no_adapter" and hop.amount_out_wei == 0


@pytest.mark.asyncio
async def test_backend_missing_pool_identity_no_adapter():
    q = BalancerV2Quoter()
    hop = await q.quote_hop(hop_index=0, chain="ethereum", token_in=WETH, token_out=USDC,
                            amount_in_wei=10 ** 18, hop_spec={}, rpc_url="http://unused.invalid")
    assert hop.status == "fallback:no_adapter" and hop.amount_out_wei == 0


@pytest.mark.asyncio
async def test_backend_happy_path_maps_to_ok_hop(monkeypatch):
    fc = FakeChain(amount_out=1899 * 10 ** 6)

    async def fake_eth_call(rpc_url, *, to, data, block="latest", timeout=12.0,
                            with_block_number=True, max_retries=None):
        return await fc(to, data)
    monkeypatch.setattr("arbicore.execution.quoter._eth_call", fake_eth_call)

    q = BalancerV2Quoter()
    hop = await q.quote_hop(hop_index=0, chain="ethereum", token_in=WETH, token_out=USDC,
                            amount_in_wei=10 ** 18, hop_spec={"pool_id": POOL_ID_HEX},
                            rpc_url="http://rpc.example")
    assert hop.status == "ok"
    assert hop.amount_out_wei == 1899 * 10 ** 6
    assert hop.dex == "balancer_v2"
    assert hop.block_number == 12345


@pytest.mark.asyncio
async def test_backend_quote_revert_maps_to_fallback_revert(monkeypatch):
    fc = FakeChain()
    fc.set(VAULT, SEL_QUERY_BATCH_SWAP, "revert", "BAL#304")

    async def fake_eth_call(rpc_url, *, to, data, block="latest", timeout=12.0,
                            with_block_number=True, max_retries=None):
        return await fc(to, data)
    monkeypatch.setattr("arbicore.execution.quoter._eth_call", fake_eth_call)

    q = BalancerV2Quoter()
    hop = await q.quote_hop(hop_index=0, chain="ethereum", token_in=WETH, token_out=USDC,
                            amount_in_wei=10 ** 18, hop_spec={"pool_id": POOL_ID_HEX},
                            rpc_url="http://rpc.example")
    assert hop.status == "fallback:revert" and hop.amount_out_wei == 0


@pytest.mark.asyncio
async def test_backend_rpc_error_maps_to_fallback_rpc_error(monkeypatch):
    fc = FakeChain()
    fc.set(VAULT, SEL_GET_POOL_TOKENS, "rpc", "node down")

    async def fake_eth_call(rpc_url, *, to, data, block="latest", timeout=12.0,
                            with_block_number=True, max_retries=None):
        return await fc(to, data)
    monkeypatch.setattr("arbicore.execution.quoter._eth_call", fake_eth_call)

    q = BalancerV2Quoter()
    hop = await q.quote_hop(hop_index=0, chain="ethereum", token_in=WETH, token_out=USDC,
                            amount_in_wei=10 ** 18, hop_spec={"pool_id": POOL_ID_HEX},
                            rpc_url="http://rpc.example")
    assert hop.status == "fallback:rpc_error" and hop.amount_out_wei == 0


@pytest.mark.asyncio
async def test_backend_never_positive_on_any_error(monkeypatch):
    """Meta-invariant: any DENY status yields amount_out_wei == 0 (UNKNOWN never
    becomes a non-zero quote)."""
    for selector, mode in [(SEL_GET_POOL_TOKENS, "revert"), (SEL_GET_SWAP_FEE, "revert"),
                           (SEL_DECIMALS, "revert"), (SEL_QUERY_BATCH_SWAP, "revert")]:
        fc = FakeChain()
        fc.set(VAULT if selector in (SEL_GET_POOL_TOKENS, SEL_QUERY_BATCH_SWAP) else POOL
               if selector == SEL_GET_SWAP_FEE else USDC, selector, mode, "x")

        async def fake_eth_call(rpc_url, *, to, data, block="latest", timeout=12.0,
                                with_block_number=True, max_retries=None):
            return await fc(to, data)
        monkeypatch.setattr("arbicore.execution.quoter._eth_call", fake_eth_call)

        q = BalancerV2Quoter()
        hop = await q.quote_hop(hop_index=0, chain="ethereum", token_in=WETH, token_out=USDC,
                                amount_in_wei=10 ** 18, hop_spec={"pool_id": POOL_ID_HEX},
                                rpc_url="http://rpc.example")
        assert hop.status != "ok"
        assert hop.amount_out_wei == 0
