"""P1 — Balancer V2 automatic candidate-pool discovery / enumeration.

Offline, fail-closed contract tests. No real RPC/network, no signing, no
broadcast. A scripted multi-pool ``eth_call`` fake + an injectable discovery
source exercise every candidate path deterministically, and the subgraph source
is tested for its fail-closed config/transport behaviour.

RUNTIME-VERIFICATION-PENDING: these prove the ENUMERATION LAYER contract only.
Real six-chain live discovery + quoting must be validated read-only on the VPS.
"""
from __future__ import annotations

import pytest
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import to_checksum_address

import arbicore.discovery.balancer_v2_pool_discovery as bal
from arbicore.discovery.balancer_v2_pool_discovery import (
    SEL_DECIMALS, SEL_GET_POOL_ID, SEL_GET_POOL_TOKENS, SEL_GET_SWAP_FEE,
    SEL_QUERY_BATCH_SWAP, discover_and_quote,
)
from arbicore.discovery.balancer_v2_pool_enumeration import (
    ENUM_DISCOVERY_UNAVAILABLE, ENUM_MALFORMED_DISCOVERY, ENUM_OK,
    ENUM_UNSUPPORTED_CHAIN, MISSING_POOL_IDENTITY, SRC_DISCOVERY_UNAVAILABLE,
    SRC_MALFORMED, SRC_OK, SRC_UNSUPPORTED_CHAIN, WRONG_VAULT,
    DiscoverySourceResult, PoolCandidate, SubgraphBalancerV2PoolSource,
    enumerate_and_quote,
)

# ---- constants ---------------------------------------------------------------

WETH = to_checksum_address("0x" + "11" * 20)
USDC = to_checksum_address("0x" + "22" * 20)
DAI = to_checksum_address("0x" + "33" * 20)
POOL_A = to_checksum_address("0x" + "aa" * 20)
POOL_B = to_checksum_address("0x" + "bb" * 20)
POOL_C = to_checksum_address("0x" + "cc" * 20)
OTHER_VAULT = to_checksum_address("0x" + "de" * 20)
FIVE_CHAINS = ["ethereum", "base", "arbitrum", "optimism", "polygon"]


def _pool_id(addr, nonce):
    return bytes.fromhex(addr[2:]) + (0).to_bytes(2, "big") + int(nonce).to_bytes(10, "big")


# ---- multi-pool scripted eth_call -------------------------------------------

class MultiPoolChain:
    def __init__(self, block=999_999):
        self.pools = {}       # addr_lower -> pool dict
        self.decimals = {}    # token addr_lower -> int
        self.block = block
        self.overrides = {}   # (to_lower, selector) -> (mode, payload)

    def add_pool(self, addr, nonce, token_decimals, balances, amount_out,
                 fee_1e18=10 ** 15, last_change_block=1000):
        tokens = [to_checksum_address(a) for a, _ in token_decimals]
        self.pools[addr.lower()] = {
            "pid": _pool_id(addr, nonce), "tokens": tokens,
            "balances": [int(b) for b in balances], "amount_out": int(amount_out),
            "fee": int(fee_1e18), "lcb": int(last_change_block)}
        for a, d in token_decimals:
            self.decimals[a.lower()] = int(d)
        return self

    def override(self, to, selector, mode, payload):
        self.overrides[(to.lower(), selector)] = (mode, payload)

    def _by_id(self, pid):
        for p in self.pools.values():
            if p["pid"] == pid:
                return p
        return None

    async def __call__(self, to, data):
        sel = data[:10]
        ov = self.overrides.get((to.lower(), sel))
        if ov is not None:
            mode, payload = ov
            if mode == "raise":
                raise payload
            if mode == "revert":
                return None, None, {"code": 3, "message": f"execution reverted: {payload}"}
            if mode == "rpc":
                return None, None, {"code": -32000, "message": payload}
            return payload, self.block, None
        if sel == SEL_GET_POOL_ID:
            p = self.pools.get(to.lower())
            if not p:
                return None, None, {"code": 3, "message": "execution reverted"}
            return "0x" + abi_encode(["bytes32"], [p["pid"]]).hex(), self.block, None
        if sel == SEL_GET_POOL_TOKENS:
            (pid,) = abi_decode(["bytes32"], bytes.fromhex(data[10:]))
            p = self._by_id(pid)
            if not p:
                return None, None, {"code": 3, "message": "execution reverted: BAL#500"}
            return "0x" + abi_encode(["address[]", "uint256[]", "uint256"],
                                     [p["tokens"], p["balances"], p["lcb"]]).hex(), self.block, None
        if sel == SEL_GET_SWAP_FEE:
            p = self.pools.get(to.lower())
            if not p:
                return None, None, {"code": 3, "message": "revert"}
            return "0x" + abi_encode(["uint256"], [p["fee"]]).hex(), self.block, None
        if sel == SEL_DECIMALS:
            d = self.decimals.get(to.lower())
            if d is None:
                return None, None, {"code": 3, "message": "revert"}
            return "0x" + abi_encode(["uint256"], [d]).hex(), self.block, None
        if sel == SEL_QUERY_BATCH_SWAP:
            (_k, swaps, _assets, _funds) = abi_decode(
                ["uint8", "(bytes32,uint256,uint256,uint256,bytes)[]", "address[]",
                 "(address,bool,address,bool)"], bytes.fromhex(data[10:]))
            p = self._by_id(swaps[0][0])
            if not p:
                return None, None, {"code": 3, "message": "revert"}
            return "0x" + abi_encode(["int256[]"],
                                     [[int(swaps[0][3]), -int(p["amount_out"])]]).hex(), self.block, None
        return None, None, {"code": -32601, "message": "method not found"}


class FakeSource:
    source_name = "fake"

    def __init__(self, status=SRC_OK, candidates=None, error=None):
        self._status, self._c, self._e = status, candidates or [], error

    async def find_pools(self, chain, a, b):
        return DiscoverySourceResult(self._status, list(self._c), self.source_name,
                                     self._e, {"q": [a, b]})


def _std_two_pools(a_out=1900 * 10 ** 6, b_out=1950 * 10 ** 6):
    mc = MultiPoolChain()
    mc.add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)], [5 * 10 ** 18, 20_000 * 10 ** 6], a_out)
    mc.add_pool(POOL_B, 2, [(WETH, 18), (USDC, 6)], [8 * 10 ** 18, 30_000 * 10 ** 6], b_out)
    return mc


def _cand(addr=None, pool_id=None, vault=None, chain="ethereum"):
    return PoolCandidate(chain=chain, pool_address=addr, pool_id=pool_id,
                         declared_vault=vault, source="fake")


AMT = 10 ** 18


# ---- discovery + quoting -----------------------------------------------------

@pytest.mark.asyncio
async def test_single_valid_candidate():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK
    assert len(r.quotes) == 1 and not r.rejected
    assert r.best.amount_out_wei == 1900 * 10 ** 6
    assert r.best.quote.meta.pool_address == POOL_A
    assert r.best.quote.meta.vault == bal.BALANCER_V2_VAULT_BY_CHAIN["ethereum"]


@pytest.mark.asyncio
async def test_multiple_candidates_ranked_best_first():
    mc = _std_two_pools(a_out=1900 * 10 ** 6, b_out=1950 * 10 ** 6)
    src = FakeSource(candidates=[_cand(addr=POOL_A), _cand(addr=POOL_B)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK and len(r.quotes) == 2
    outs = [q.amount_out_wei for q in r.quotes]
    assert outs == sorted(outs, reverse=True)          # ranked desc
    assert r.best.quote.meta.pool_address == POOL_B     # higher output wins


@pytest.mark.asyncio
async def test_duplicate_pool_elimination():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    src = FakeSource(candidates=[_cand(addr=POOL_A), _cand(addr=POOL_A),
                                 _cand(addr=POOL_A.lower())])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK and len(r.quotes) == 1   # deduped to one


@pytest.mark.asyncio
async def test_token_pair_filtering_only_matching_pool_quoted():
    mc = _std_two_pools()
    mc.add_pool(POOL_C, 3, [(WETH, 18), (DAI, 18)], [5 * 10 ** 18, 9_000 * 10 ** 18], 5 * 10 ** 18)
    src = FakeSource(candidates=[_cand(addr=POOL_A), _cand(addr=POOL_B), _cand(addr=POOL_C)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK and len(r.quotes) == 2
    assert any(rj.status == bal.TOKEN_NOT_IN_POOL for rj in r.rejected)


@pytest.mark.asyncio
async def test_missing_token_candidate_rejected():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (DAI, 18)],
                                   [5 * 10 ** 18, 9_000 * 10 ** 18], 5 * 10 ** 18)
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK and not r.quotes
    assert r.rejected[0].status == bal.TOKEN_NOT_IN_POOL


# ---- source-level fail-closed states ----------------------------------------

@pytest.mark.asyncio
async def test_unsupported_chain_bnb():
    src = FakeSource(candidates=[_cand(addr=POOL_A, chain="bnb")])
    r = await enumerate_and_quote(src, _std_two_pools(), "bnb", WETH, USDC, AMT)
    assert r.status == ENUM_UNSUPPORTED_CHAIN and not r.quotes


@pytest.mark.asyncio
async def test_discovery_unavailable_is_not_zero():
    src = FakeSource(status=SRC_DISCOVERY_UNAVAILABLE, error="source down")
    r = await enumerate_and_quote(src, _std_two_pools(), "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_DISCOVERY_UNAVAILABLE      # explicit, NOT ok/empty/zero
    assert not r.quotes and r.error == "source down"


@pytest.mark.asyncio
async def test_malformed_discovery():
    src = FakeSource(status=SRC_MALFORMED, error="bad body")
    r = await enumerate_and_quote(src, _std_two_pools(), "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_MALFORMED_DISCOVERY and not r.quotes


@pytest.mark.asyncio
async def test_source_ok_but_no_candidates_survive():
    # Discovery worked, but the single candidate does not exist on-chain.
    mc = MultiPoolChain()  # no pools registered → getPoolId reverts
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK and not r.quotes and r.rejected  # honest empty, not unavailable


# ---- per-candidate rejection paths ------------------------------------------

@pytest.mark.asyncio
async def test_invalid_pool_address_rejected():
    src = FakeSource(candidates=[_cand(addr="0xnot_an_address")])
    r = await enumerate_and_quote(src, _std_two_pools(), "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK and not r.quotes
    assert r.rejected[0].status == bal.MALFORMED


@pytest.mark.asyncio
async def test_pool_id_mismatch_rejected():
    src = FakeSource(candidates=[_cand(pool_id="0x" + _pool_id(POOL_A, 1).hex(),
                                       addr=POOL_B)])  # id embeds A, address says B
    r = await enumerate_and_quote(src, _std_two_pools(), "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == bal.POOL_ID_MISMATCH and not r.quotes


@pytest.mark.asyncio
async def test_wrong_vault_rejected_without_chain_calls():
    mc = _std_two_pools()
    src = FakeSource(candidates=[_cand(addr=POOL_A, vault=OTHER_VAULT)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == WRONG_VAULT and not r.quotes


@pytest.mark.asyncio
async def test_missing_pool_identity_rejected():
    src = FakeSource(candidates=[_cand()])  # neither id nor address
    r = await enumerate_and_quote(src, _std_two_pools(), "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == MISSING_POOL_IDENTITY and not r.quotes


@pytest.mark.asyncio
async def test_unknown_decimals_rejected():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    mc.decimals.pop(USDC.lower())  # token decimals() now reverts
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == bal.UNKNOWN_DECIMALS and not r.quotes


@pytest.mark.asyncio
async def test_zero_liquidity_rejected():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 0], 1900 * 10 ** 6)
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == bal.INSUFFICIENT_LIQUIDITY and not r.quotes


@pytest.mark.asyncio
async def test_stale_pool_rejected():
    mc = MultiPoolChain(block=1000).add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                             [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT,
                                  current_block=999_999, max_age_blocks=100)
    assert r.rejected[0].status == bal.STALE_POOL and not r.quotes


@pytest.mark.asyncio
async def test_unknown_fee_rejected():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    mc.override(POOL_A, SEL_GET_SWAP_FEE, "revert", "no fee")
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == bal.UNKNOWN_FEE and not r.quotes


@pytest.mark.asyncio
async def test_querybatchswap_failure_rejected():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    mc.override(bal.BALANCER_V2_VAULT_BY_CHAIN["ethereum"], SEL_QUERY_BATCH_SWAP, "revert", "BAL#001")
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == bal.QUOTE_REVERT and not r.quotes


@pytest.mark.asyncio
async def test_malformed_quote_rejected():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    mc.override(bal.BALANCER_V2_VAULT_BY_CHAIN["ethereum"], SEL_QUERY_BATCH_SWAP, "raw", "0x1234")
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == bal.MALFORMED and not r.quotes


@pytest.mark.asyncio
async def test_zero_output_rejected():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 0)
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == bal.NO_OUTPUT and not r.quotes


@pytest.mark.asyncio
async def test_negative_output_rejected():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    bad = "0x" + abi_encode(["int256[]"], [[AMT, 5]]).hex()  # delta[1] positive → out < 0
    mc.override(bal.BALANCER_V2_VAULT_BY_CHAIN["ethereum"], SEL_QUERY_BATCH_SWAP, "raw", bad)
    src = FakeSource(candidates=[_cand(addr=POOL_A)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.rejected[0].status == bal.NO_OUTPUT and not r.quotes


# ---- selection / ranking / limits / chains ----------------------------------

@pytest.mark.asyncio
async def test_multiple_valid_pools_selection():
    mc = _std_two_pools(a_out=1800 * 10 ** 6, b_out=2000 * 10 ** 6)
    mc.add_pool(POOL_C, 3, [(WETH, 18), (USDC, 6)], [9 * 10 ** 18, 40_000 * 10 ** 6], 1950 * 10 ** 6)
    src = FakeSource(candidates=[_cand(addr=POOL_A), _cand(addr=POOL_B), _cand(addr=POOL_C)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert [q.amount_out_wei for q in r.quotes] == [2000 * 10 ** 6, 1950 * 10 ** 6, 1800 * 10 ** 6]
    assert r.best.quote.meta.pool_address == POOL_B


@pytest.mark.asyncio
async def test_max_candidates_cap():
    mc = _std_two_pools()
    mc.add_pool(POOL_C, 3, [(WETH, 18), (USDC, 6)], [9 * 10 ** 18, 40_000 * 10 ** 6], 2100 * 10 ** 6)
    src = FakeSource(candidates=[_cand(addr=POOL_A), _cand(addr=POOL_B), _cand(addr=POOL_C)])
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT, max_candidates=1)
    assert len(r.quotes) + len(r.rejected) == 1   # only first candidate considered


@pytest.mark.parametrize("chain", FIVE_CHAINS)
@pytest.mark.asyncio
async def test_all_five_target_chains(chain):
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    src = FakeSource(candidates=[_cand(addr=POOL_A, chain=chain)])
    r = await enumerate_and_quote(src, mc, chain, WETH, USDC, AMT)
    assert r.status == ENUM_OK and len(r.quotes) == 1
    assert r.best.quote.meta.vault == bal.BALANCER_V2_VAULT_BY_CHAIN[chain]


# ---- P0 preservation ---------------------------------------------------------

@pytest.mark.asyncio
async def test_p0_path_unchanged_still_quotes():
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    q = await discover_and_quote(mc, "ethereum", WETH, USDC, AMT, pool_address=POOL_A)
    assert q.status == bal.OK and q.amount_out_wei == 1900 * 10 ** 6


# ---- subgraph source (fail-closed config/transport) -------------------------

@pytest.mark.asyncio
async def test_subgraph_missing_url_unavailable():
    src = SubgraphBalancerV2PoolSource(url_by_chain={})
    res = await src.find_pools("ethereum", WETH, USDC)
    assert res.status == SRC_DISCOVERY_UNAVAILABLE


@pytest.mark.asyncio
async def test_subgraph_unsupported_chain():
    src = SubgraphBalancerV2PoolSource(url_by_chain={"ethereum": "http://x"})
    res = await src.find_pools("bnb", WETH, USDC)
    assert res.status == SRC_UNSUPPORTED_CHAIN


@pytest.mark.asyncio
async def test_subgraph_transport_error_unavailable():
    async def boom(url, payload, headers):
        raise RuntimeError("connection refused")
    src = SubgraphBalancerV2PoolSource(url_by_chain={"ethereum": "http://x"}, http_post=boom)
    res = await src.find_pools("ethereum", WETH, USDC)
    assert res.status == SRC_DISCOVERY_UNAVAILABLE


@pytest.mark.asyncio
async def test_subgraph_non200_unavailable():
    async def http500(url, payload, headers):
        return 500, {}
    src = SubgraphBalancerV2PoolSource(url_by_chain={"ethereum": "http://x"}, http_post=http500)
    res = await src.find_pools("ethereum", WETH, USDC)
    assert res.status == SRC_DISCOVERY_UNAVAILABLE


@pytest.mark.asyncio
async def test_subgraph_malformed_body():
    async def bad(url, payload, headers):
        return 200, {"unexpected": True}
    src = SubgraphBalancerV2PoolSource(url_by_chain={"ethereum": "http://x"}, http_post=bad)
    res = await src.find_pools("ethereum", WETH, USDC)
    assert res.status == SRC_MALFORMED


@pytest.mark.asyncio
async def test_subgraph_ok_parses_candidates():
    async def ok(url, payload, headers):
        return 200, {"data": {"pools": [{"id": "0x" + _pool_id(POOL_A, 1).hex(),
                                         "address": POOL_A}]}}
    src = SubgraphBalancerV2PoolSource(url_by_chain={"ethereum": "http://x"}, http_post=ok)
    res = await src.find_pools("ethereum", WETH, USDC)
    assert res.status == SRC_OK and len(res.candidates) == 1
    assert res.candidates[0].pool_address == POOL_A


@pytest.mark.asyncio
async def test_subgraph_end_to_end_with_onchain_validation():
    async def ok(url, payload, headers):
        return 200, {"data": {"pools": [{"id": "0x" + _pool_id(POOL_A, 1).hex(),
                                         "address": POOL_A}]}}
    src = SubgraphBalancerV2PoolSource(url_by_chain={"ethereum": "http://x"}, http_post=ok)
    mc = MultiPoolChain().add_pool(POOL_A, 1, [(WETH, 18), (USDC, 6)],
                                   [5 * 10 ** 18, 20_000 * 10 ** 6], 1900 * 10 ** 6)
    r = await enumerate_and_quote(src, mc, "ethereum", WETH, USDC, AMT)
    assert r.status == ENUM_OK and r.best.amount_out_wei == 1900 * 10 ** 6
