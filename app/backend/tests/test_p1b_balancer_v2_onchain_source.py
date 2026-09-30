"""P1 follow-up — on-chain Balancer V2 PoolRegistered candidate-discovery source.

Offline, fail-closed contract tests. Scripted eth_getLogs + eth_blockNumber
fakes; a compact multi-pool eth_call fake proves candidates are re-validated /
token-pair-filtered through the FROZEN P0 path. No real RPC/network, no signing,
no broadcast, no execution.

RUNTIME-VERIFICATION-PENDING: proves the discovery-source contract only. Real
five-chain live eth_getLogs discovery must be validated read-only on the VPS.
"""
from __future__ import annotations

import pytest
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import to_checksum_address

import arbicore.discovery.balancer_v2_pool_discovery as bal
from arbicore.discovery.balancer_v2_pool_discovery import (
    SEL_DECIMALS, SEL_GET_POOL_ID, SEL_GET_POOL_TOKENS, SEL_GET_SWAP_FEE,
    SEL_QUERY_BATCH_SWAP,
)
from arbicore.discovery.balancer_v2_onchain_source import (
    POOL_REGISTERED_TOPIC, OnChainPoolRegisteredSource,
)
from arbicore.discovery.balancer_v2_pool_enumeration import (
    ENUM_OK, SRC_DISCOVERY_UNAVAILABLE, SRC_MALFORMED, SRC_OK,
    SRC_UNSUPPORTED_CHAIN, enumerate_and_quote,
)

WETH = to_checksum_address("0x" + "11" * 20)
USDC = to_checksum_address("0x" + "22" * 20)
DAI = to_checksum_address("0x" + "33" * 20)
POOL_A = to_checksum_address("0x" + "aa" * 20)
POOL_B = to_checksum_address("0x" + "bb" * 20)
POOL_C = to_checksum_address("0x" + "cc" * 20)
OTHER_VAULT = to_checksum_address("0x" + "de" * 20)
ETH_VAULT = bal.BALANCER_V2_VAULT_BY_CHAIN["ethereum"]
AMT = 10 ** 18


def _pool_id(addr, nonce):
    return bytes.fromhex(addr[2:]) + (0).to_bytes(2, "big") + int(nonce).to_bytes(10, "big")


def _log(addr, nonce, *, vault=ETH_VAULT, spec=0, block=100,
         topic0=POOL_REGISTERED_TOPIC, addr_topic=None, pid_hex=None):
    pid = pid_hex or ("0x" + _pool_id(addr, nonce).hex())
    at = addr_topic or ("0x" + "0" * 24 + addr[2:].lower())
    return {"address": vault, "topics": [topic0, pid, at],
            "data": "0x" + int(spec).to_bytes(32, "big").hex(), "blockNumber": hex(block)}


def logs_fn(logs_by_range=None, flat=None):
    """Build an eth_getLogs fake. `flat` returns the same logs for any range;
    `logs_by_range` maps (from,to)->logs for chunking assertions."""
    calls = []

    async def _fn(chain, address, topics, from_block, to_block):
        calls.append((from_block, to_block))
        if logs_by_range is not None:
            return list(logs_by_range.get((from_block, to_block), []))
        return list(flat or [])
    _fn.calls = calls
    return _fn


async def _block_number(_chain):
    return 1_000_000


# ---- decoding & basic discovery ---------------------------------------------

@pytest.mark.asyncio
async def test_pool_registered_decoding_single_valid():
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[_log(POOL_A, 1, spec=2, block=555)]))
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_OK and len(r.candidates) == 1
    c = r.candidates[0]
    assert c.pool_address == POOL_A
    assert c.pool_id == "0x" + _pool_id(POOL_A, 1).hex()
    assert c.declared_vault == ETH_VAULT
    assert c.raw["specialization"] == 2 and c.raw["block_number"] == 555
    assert c.source == "balancer_v2_onchain_pool_registered"


@pytest.mark.asyncio
async def test_multiple_pools():
    src = OnChainPoolRegisteredSource(
        eth_get_logs_fn=logs_fn(flat=[_log(POOL_A, 1), _log(POOL_B, 2), _log(POOL_C, 3)]))
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_OK and len(r.candidates) == 3


@pytest.mark.asyncio
async def test_duplicate_events_deduped():
    src = OnChainPoolRegisteredSource(
        eth_get_logs_fn=logs_fn(flat=[_log(POOL_A, 1), _log(POOL_A, 1), _log(POOL_A, 1)]))
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_OK and len(r.candidates) == 1


@pytest.mark.asyncio
async def test_empty_result_is_ok_not_unavailable():
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[]))
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_OK and r.candidates == []   # honest empty, not unavailable


# ---- malformed / wrong vault ------------------------------------------------

@pytest.mark.asyncio
async def test_malformed_event_too_few_topics():
    bad = {"address": ETH_VAULT, "topics": [POOL_REGISTERED_TOPIC], "data": "0x", "blockNumber": "0x1"}
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[bad]))
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_MALFORMED


@pytest.mark.asyncio
async def test_wrong_vault_emitter_malformed():
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[_log(POOL_A, 1, vault=OTHER_VAULT)]))
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_MALFORMED


@pytest.mark.asyncio
async def test_poolid_not_embedding_address_malformed():
    # poolId embeds POOL_B but the address topic says POOL_A → fabrication guard.
    bad = _log(POOL_A, 1, pid_hex="0x" + _pool_id(POOL_B, 1).hex())
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[bad]))
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_MALFORMED


@pytest.mark.asyncio
async def test_wrong_topic0_malformed():
    bad = _log(POOL_A, 1, topic0="0x" + "ab" * 32)
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[bad]))
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_MALFORMED


# ---- RPC failure / rate-limit / non-list ------------------------------------

@pytest.mark.asyncio
async def test_rpc_failure_unavailable():
    async def boom(*a):
        raise RuntimeError("connection reset")
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=boom)
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_DISCOVERY_UNAVAILABLE


@pytest.mark.asyncio
async def test_rpc_rate_limit_unavailable():
    async def limited(*a):
        raise RuntimeError("429 Too Many Requests: rate limit exceeded")
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=limited)
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_DISCOVERY_UNAVAILABLE


@pytest.mark.asyncio
async def test_non_list_result_malformed():
    async def weird(*a):
        return {"not": "a list"}
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=weird)
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_MALFORMED


# ---- block-range chunking ---------------------------------------------------

@pytest.mark.asyncio
async def test_block_range_chunking_and_aggregation():
    ranges = {(0, 9): [_log(POOL_A, 1)], (10, 19): [_log(POOL_B, 2)], (20, 25): [_log(POOL_C, 3)]}
    fn = logs_fn(logs_by_range=ranges)
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=fn, chunk_size=10)
    r = await src.discover_candidates("ethereum", from_block=0, to_block=25)
    assert r.status == SRC_OK and len(r.candidates) == 3
    assert fn.calls == [(0, 9), (10, 19), (20, 25)]          # bounded, chunked
    assert r.provenance["chunks"] == 3 and r.provenance["chunk_size"] == 10


@pytest.mark.asyncio
async def test_invalid_range_unavailable():
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[]))
    r = await src.discover_candidates("ethereum", from_block=100, to_block=10)
    assert r.status == SRC_DISCOVERY_UNAVAILABLE


# ---- unsupported chain / unavailable fetcher --------------------------------

@pytest.mark.asyncio
async def test_unsupported_chain_bnb():
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[]))
    r = await src.discover_candidates("bnb", from_block=0, to_block=100)
    assert r.status == SRC_UNSUPPORTED_CHAIN


@pytest.mark.asyncio
async def test_no_fetcher_unavailable():
    src = OnChainPoolRegisteredSource()
    r = await src.discover_candidates("ethereum", from_block=0, to_block=100)
    assert r.status == SRC_DISCOVERY_UNAVAILABLE


# ---- find_pools window resolution -------------------------------------------

@pytest.mark.asyncio
async def test_find_pools_resolves_window_via_blocknumber():
    fn = logs_fn(flat=[_log(POOL_A, 1)])
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=fn, eth_block_number_fn=_block_number,
                                      window_blocks=1000, chunk_size=100_000)
    r = await src.find_pools("ethereum", WETH, USDC)
    assert r.status == SRC_OK and len(r.candidates) == 1
    assert r.provenance["to_block"] == 1_000_000
    assert r.provenance["from_block"] == 1_000_000 - 1000


@pytest.mark.asyncio
async def test_find_pools_unresolved_to_block_unavailable():
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[]))  # no to_block, no blocknum fn
    r = await src.find_pools("ethereum", WETH, USDC)
    assert r.status == SRC_DISCOVERY_UNAVAILABLE


@pytest.mark.asyncio
async def test_provenance_preserved():
    src = OnChainPoolRegisteredSource(eth_get_logs_fn=logs_fn(flat=[_log(POOL_A, 1)]))
    r = await src.discover_candidates("ethereum", from_block=5, to_block=25)
    p = r.provenance
    assert p["chain"] == "ethereum" and p["vault"] == ETH_VAULT
    assert p["from_block"] == 5 and p["to_block"] == 25
    assert p["event_topic0"] == POOL_REGISTERED_TOPIC and p["returned"] == 1
    # no RPC URL / credentials leaked into provenance
    assert not any("http" in str(v).lower() for v in p.values())


# ---- token-pair filtering THROUGH the frozen P0 path ------------------------

class _MiniChain:
    """Minimal P0 eth_call fake: two pools, membership decides filtering."""

    def __init__(self):
        self.pools, self.decimals, self.block = {}, {}, 999_999

    def add(self, addr, nonce, toks, bals, out, fee=10 ** 15, lcb=1000):
        self.pools[addr.lower()] = {"pid": _pool_id(addr, nonce),
                                    "tokens": [to_checksum_address(a) for a, _ in toks],
                                    "bals": [int(b) for b in bals], "out": int(out),
                                    "fee": fee, "lcb": lcb}
        for a, d in toks:
            self.decimals[a.lower()] = d
        return self

    def _by_id(self, pid):
        return next((p for p in self.pools.values() if p["pid"] == pid), None)

    async def __call__(self, to, data):
        sel = data[:10]
        if sel == SEL_GET_POOL_ID:
            p = self.pools.get(to.lower())
            return ("0x" + abi_encode(["bytes32"], [p["pid"]]).hex(), self.block, None) if p \
                else (None, None, {"code": 3, "message": "revert"})
        if sel == SEL_GET_POOL_TOKENS:
            (pid,) = abi_decode(["bytes32"], bytes.fromhex(data[10:]))
            p = self._by_id(pid)
            if not p:
                return None, None, {"code": 3, "message": "revert"}
            return "0x" + abi_encode(["address[]", "uint256[]", "uint256"],
                                     [p["tokens"], p["bals"], p["lcb"]]).hex(), self.block, None
        if sel == SEL_GET_SWAP_FEE:
            p = self.pools.get(to.lower())
            return ("0x" + abi_encode(["uint256"], [p["fee"]]).hex(), self.block, None)
        if sel == SEL_DECIMALS:
            d = self.decimals.get(to.lower())
            return ("0x" + abi_encode(["uint256"], [d]).hex(), self.block, None) if d is not None \
                else (None, None, {"code": 3, "message": "revert"})
        if sel == SEL_QUERY_BATCH_SWAP:
            (_k, sw, _a, _f) = abi_decode(
                ["uint8", "(bytes32,uint256,uint256,uint256,bytes)[]", "address[]",
                 "(address,bool,address,bool)"], bytes.fromhex(data[10:]))
            p = self._by_id(sw[0][0])
            return "0x" + abi_encode(["int256[]"], [[int(sw[0][3]), -int(p["out"])]]).hex(), self.block, None
        return None, None, {"code": -32601, "message": "no method"}


@pytest.mark.asyncio
async def test_token_pair_filtering_through_p0_end_to_end():
    # Discovery returns two pools; only the WETH/USDC one survives P0 membership.
    src = OnChainPoolRegisteredSource(
        eth_get_logs_fn=logs_fn(flat=[_log(POOL_A, 1), _log(POOL_C, 3)]),
        from_block=0, to_block=100)
    chain = _MiniChain()
    chain.add(POOL_A, 1, [(WETH, 18), (USDC, 6)], [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    chain.add(POOL_C, 3, [(WETH, 18), (DAI, 18)], [5 * 10 ** 18, 9_000 * 10 ** 18], 5 * 10 ** 18)
    r = await enumerate_and_quote(src, chain, "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK
    assert len(r.quotes) == 1 and r.best.quote.meta.pool_address == POOL_A
    assert any(rj.status == bal.TOKEN_NOT_IN_POOL for rj in r.rejected)
    assert r.source_name == "balancer_v2_onchain_pool_registered"
