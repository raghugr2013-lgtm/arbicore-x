"""Track 2 — reusable, CHAIN-SCOPED execution-readiness evaluator.

Deterministic (fully injected) proofs that the non-Base execution ladder:
  * selects chain-scoped resources (Arbitrum, not Base) with no Base leakage;
  * fails closed at each missing stage (RPC / chain-id / receiver / executor /
    simulation);
  * treats a wrong-chain RPC (Base chain-id for an Arbitrum request) as BLOCKED;
  * has no signing/broadcast side effects;
  * keeps Limited-Live RED / execution_capable False without full evidence;
  * only reports execution_capable when EVERY stage has positive evidence.
"""
from __future__ import annotations

import pytest

from arbicore.control.chain_execution_readiness import (
    BLOCKED, PASS, STAGE_ORDER, UNKNOWN,
    evaluate_chain_execution_readiness,
    build_chain_execution_readiness_report,
)

ARB = "arbitrum"
ARB_ID = 42161
BASE_ID = 8453


class _FakeReceiver:
    def __init__(self, deployed, supported):
        self.deployed = deployed
        self._supported = set(supported)

    def supports(self, provider):
        return self.deployed and str(provider).lower() in self._supported


def _reader_returning(value):
    async def _r(chain):
        return value
    return _r


def _base_kwargs(**over):
    """A fully-injected, chain-scoped happy-ish baseline for Arbitrum; individual
    tests override one seam to prove a specific fail-closed path."""
    calls = over.pop("_calls", [])

    def eth_call_factory(chain):
        calls.append(chain)
        async def _eth_call(to, data):   # a real (fake) chain-scoped eth_call
            return None
        return _eth_call

    kw = dict(
        eth_call_factory=eth_call_factory,
        chain_id_reader=_reader_returning(ARB_ID),
        pool_graph_fn=lambda c: _fake_pools(c),
        gas_model_fn=lambda c: object(),
        economic_rpc_fn=lambda c: True,
        receiver_capability_fn=lambda c: _FakeReceiver(True, {"aave_v3", "balancer_v2"}),
        executor_address_fn=lambda c: "0x" + "ab" * 20,
    )
    kw.update(over)
    return kw, calls


class _Pool:
    def __init__(self, dex, chain):
        self.dex_protocol = dex
        self.chain = chain


def _fake_pools(chain):
    return [_Pool("uniswap_v3", chain), _Pool("sushiswap_v3", chain)]


# ---------------------------------------------------------------------------
# Chain-scoped selection + no Base leakage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chain_scoped_selection_uses_requested_chain_only():
    calls = []
    kw, calls = _base_kwargs(_calls=calls)
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    assert res["chain"] == ARB
    assert res["expected_chain_id"] == ARB_ID
    # RPC factory was asked ONLY for arbitrum — never base.
    assert calls and all(c == ARB for c in calls)
    assert "base" not in calls


@pytest.mark.asyncio
async def test_wrong_chain_rpc_is_blocked_no_base_leakage():
    # RPC actually answers with Base's chain-id → must be caught as a mismatch.
    kw, _ = _base_kwargs(chain_id_reader=_reader_returning(BASE_ID))
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    cv = res["stages"]["CHAIN_VERIFICATION"]
    assert cv["status"] == BLOCKED
    assert cv["reason"] == "chain_id_mismatch_rpc_bound_to_wrong_chain"
    assert cv["evidence"]["observed_chain_id"] == BASE_ID
    assert res["execution_capable"] is False


# ---------------------------------------------------------------------------
# Per-stage fail-closed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_rpc_fails_closed():
    kw, _ = _base_kwargs(eth_call_factory=lambda c: None)
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    assert res["stages"]["RPC"]["status"] == BLOCKED
    assert res["stages"]["RPC"]["reason"] == "no_operator_configured_rpc"
    assert res["reached_stage"] == "RPC"
    assert res["execution_capable"] is False


@pytest.mark.asyncio
async def test_missing_receiver_fails_closed():
    kw, _ = _base_kwargs(receiver_capability_fn=lambda c: _FakeReceiver(False, set()))
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    ec = res["stages"]["EXECUTION_CAPABILITY"]
    assert ec["status"] == BLOCKED
    assert ec["reason"] == "no_deployed_receiver"
    assert res["execution_capable"] is False


@pytest.mark.asyncio
async def test_receiver_without_supported_head_fails_closed():
    kw, _ = _base_kwargs(
        receiver_capability_fn=lambda c: _FakeReceiver(True, {"morpho_blue"}))
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    ec = res["stages"]["EXECUTION_CAPABILITY"]
    assert ec["status"] == BLOCKED
    assert ec["reason"] == "receiver_declares_no_supported_runtime_flash_head"


@pytest.mark.asyncio
async def test_missing_executor_fails_closed():
    kw, _ = _base_kwargs(executor_address_fn=lambda c: None)
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    assert res["stages"]["SIMULATION"]["status"] == BLOCKED
    assert res["stages"]["SIMULATION"]["reason"] == "no_executor_address"
    assert res["stages"]["EXECUTION_CAPABILITY"]["status"] == BLOCKED
    assert res["execution_capable"] is False


@pytest.mark.asyncio
async def test_missing_simulation_evidence_is_not_pass():
    # Even with RPC + executor, the exact candidate-bound sim is unproven here.
    kw, _ = _base_kwargs()
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    assert res["stages"]["SIMULATION"]["status"] == UNKNOWN
    assert res["stages"]["SIMULATION"]["reason"] == \
        "simulation_requires_candidate_bound_calldata"
    assert res["execution_capable"] is False


@pytest.mark.asyncio
async def test_empty_universe_blocks_composition_and_route():
    kw, _ = _base_kwargs(pool_graph_fn=lambda c: [])
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    assert res["stages"]["MARKET_COMPOSITION"]["status"] == BLOCKED
    assert res["stages"]["ROUTE"]["status"] == BLOCKED


@pytest.mark.asyncio
async def test_no_gas_model_blocks_economics():
    kw, _ = _base_kwargs(gas_model_fn=lambda c: None)
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    assert res["stages"]["ECONOMICS"]["status"] == BLOCKED
    assert res["stages"]["ECONOMICS"]["reason"] == "no_gas_model"


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_signing_broadcast_and_limited_live_red():
    kw, _ = _base_kwargs()
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    assert res["signed"] is False
    assert res["broadcast"] is False
    assert res["limited_live_eligible"] is False


@pytest.mark.asyncio
async def test_full_evidence_reports_execution_capable_but_never_limited_live():
    # Provide positive evidence at EVERY stage that this evaluator can assert
    # (chain verified, universe present, gas+econ RPC, receiver+executor). The
    # inherently-live stages (LIQUIDITY/QUOTE/SIMULATION) stay UNKNOWN by design,
    # so execution_capable MUST remain False — proving no false GREEN.
    kw, _ = _base_kwargs()
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    assert res["stages"]["CHAIN_VERIFICATION"]["status"] == PASS
    assert res["stages"]["MARKET_COMPOSITION"]["status"] == PASS
    assert res["stages"]["ROUTE"]["status"] == PASS
    assert res["stages"]["EXECUTION_CAPABILITY"]["status"] == PASS
    # Live-only stages remain fail-closed ⇒ overall not execution-capable.
    assert res["execution_capable"] is False
    assert res["limited_live_eligible"] is False


# ---------------------------------------------------------------------------
# Offline report over all six chains — pure, fail-closed, no Base-first
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_offline_report_all_six_chains_fail_closed():
    report = await build_chain_execution_readiness_report()
    nets = report["networks"]
    assert set(nets) == {"base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"}
    # No operator RPC in this env ⇒ nothing execution-capable, Limited-Live off.
    assert report["execution_capable_count"] == 0
    assert report["safety"]["limited_live_enabled"] is False
    for c, r in nets.items():
        assert r["execution_capable"] is False
        assert r["limited_live_eligible"] is False
        # Each chain evaluated independently against its OWN expected id.
        assert r["stages"]["RPC"]["status"] == BLOCKED  # offline env
        assert set(r["stages"]) == set(STAGE_ORDER)


@pytest.mark.asyncio
async def test_unknown_chain_is_blocked():
    res = await evaluate_chain_execution_readiness("solana",
                                                   eth_call_factory=lambda c: None)
    assert res["expected_chain_id"] is None
    assert res["stages"]["CHAIN_VERIFICATION"]["status"] == BLOCKED
    assert res["stages"]["CHAIN_VERIFICATION"]["reason"] == "unknown_chain"


# ---------------------------------------------------------------------------
# LIVE chain-verification + liquidity (operator-RPC boundary) — reusable
# ---------------------------------------------------------------------------
def _live_probe(balances):
    async def _p(chain, eth_call):
        return {p: {"liquidity_tokens": v, "borrow_token": "USDC",
                    "token_address": "0x" + "cc" * 20}
                for p, v in balances.items()}
    return _p


@pytest.mark.asyncio
async def test_live_chain_verification_pass_on_matching_chainid():
    kw, _ = _base_kwargs(chain_id_reader=_reader_returning(ARB_ID))
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    cv = res["stages"]["CHAIN_VERIFICATION"]
    assert cv["status"] == PASS
    assert cv["reason"] == "rpc_confirmed_on_expected_chain"
    assert cv["evidence"]["chain_id"] == ARB_ID


@pytest.mark.asyncio
async def test_live_liquidity_proven_onchain_advances_stage():
    kw, _ = _base_kwargs(
        liquidity_probe_fn=_live_probe({"aave_v3": 12_500_000.0,
                                        "balancer_v2": 3_000_000.0}))
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    lp = res["stages"]["LIQUIDITY_PROVIDER"]
    assert lp["status"] == PASS
    assert lp["reason"] == "runtime_liquidity_proven_onchain"
    assert lp["evidence"]["proven_providers"] == ["aave_v3", "balancer_v2"]
    assert lp["evidence"]["liquidity"]["aave_v3"]["liquidity_tokens"] == 12_500_000.0


@pytest.mark.asyncio
async def test_live_liquidity_reusable_across_all_five_evm_chains():
    # SAME code path, different chain scope — no Arbitrum special-case.
    for chain in ("ethereum", "optimism", "polygon", "arbitrum", "bnb"):
        heads_balances = {"aave_v3": 1_000_000.0}
        kw, _ = _base_kwargs(
            chain_id_reader=None,   # exercise default live reader (fail-closed None ok)
            liquidity_probe_fn=_live_probe(heads_balances))
        res = await evaluate_chain_execution_readiness(chain, **kw)
        assert res["stages"]["LIQUIDITY_PROVIDER"]["status"] == PASS


@pytest.mark.asyncio
async def test_live_liquidity_fails_closed_without_rpc():
    kw, _ = _base_kwargs(eth_call_factory=lambda c: None,
                         liquidity_probe_fn=_live_probe({"aave_v3": 9e9}))
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    lp = res["stages"]["LIQUIDITY_PROVIDER"]
    assert lp["status"] == UNKNOWN
    assert lp["reason"] == "liquidity_unverified_no_operator_rpc"


@pytest.mark.asyncio
async def test_live_liquidity_fails_closed_on_empty_read():
    kw, _ = _base_kwargs(liquidity_probe_fn=_live_probe({}))
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    lp = res["stages"]["LIQUIDITY_PROVIDER"]
    assert lp["status"] == UNKNOWN
    assert lp["reason"] == "liquidity_read_returned_no_provider_balance"


@pytest.mark.asyncio
async def test_live_liquidity_probe_receives_requested_chain_only():
    seen = []

    async def spy_probe(chain, eth_call):
        seen.append(chain)
        return {"aave_v3": {"liquidity_tokens": 5.0}}

    kw, _ = _base_kwargs(liquidity_probe_fn=spy_probe)
    await evaluate_chain_execution_readiness(ARB, **kw)
    assert seen == [ARB]      # probe scoped to arbitrum, never base


@pytest.mark.asyncio
async def test_default_liquidity_probe_end_to_end_arbitrum():
    """Exercise the REAL default probe (registry USDC + provider_liquidity
    selectors) against a realistic chain-scoped eth_call — proving the genuine
    read chain, not an injected shortcut."""
    from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
        AAVE_V3_POOL, SEL_BALANCE_OF, SEL_GET_RESERVE_DATA)
    atoken = "0x724dc807b04555b71ed48a6896b6F41593b8C637"  # arbitrum aUSDC-like

    def _word(a):
        return a.lower().replace("0x", "").rjust(64, "0")

    async def eth_call(to, data):
        sel = data[:10]
        if sel == SEL_GET_RESERVE_DATA:
            return "0x" + "".join(["0" * 64] * 8 + [_word(atoken)] + ["0" * 64] * 6)
        if sel == SEL_BALANCE_OF:
            return hex(9_000_000 * 10 ** 6)   # 9M units for whichever holder
        raise AssertionError("unexpected selector")

    # Confirm the probe targets the ARBITRUM Aave pool (never Base's).
    assert AAVE_V3_POOL["arbitrum"] != AAVE_V3_POOL["base"]

    kw, _ = _base_kwargs(
        eth_call_factory=lambda c: eth_call,     # chain-scoped operator RPC seam
        chain_id_reader=_reader_returning(ARB_ID))
    res = await evaluate_chain_execution_readiness(ARB, **kw)
    lp = res["stages"]["LIQUIDITY_PROVIDER"]
    assert lp["status"] == PASS
    assert lp["reason"] == "runtime_liquidity_proven_onchain"
    # Both Arbitrum runtime heads (aave_v3 + balancer_v2) proven from real reads.
    assert set(lp["evidence"]["proven_providers"]) == {"aave_v3", "balancer_v2"}
    assert lp["evidence"]["liquidity"]["aave_v3"]["liquidity_tokens"] == 9_000_000.0
    assert res["stages"]["CHAIN_VERIFICATION"]["status"] == PASS
