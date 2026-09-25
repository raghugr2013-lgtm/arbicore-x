"""Executor-deployment capability gate — six-chain fail-closed proof.

Proves the settlement dispatcher only marks a route EXECUTABLE when a genuinely
DEPLOYED executor exists on the target chain. Today the sole deployed executor
is on Base Sepolia (84532); Base mainnet is not_deployed and the five other
chains are unregistered — all must be fail-closed, never falsely executable.
A chain flips to EXECUTABLE automatically once its executor is deployed.
"""
from __future__ import annotations

from arbicore.execution.settlement_dispatcher import evaluate_settlement, Verdict
from arbicore.execution import executor_registry


def _ev(chain, **kw):
    return evaluate_settlement(flash_provider="balancer_v2",
                               swap_venues=["uniswap_v3"], chain=chain, **kw)


# ── Registry truth: Base Sepolia + Base mainnet have deployed V1 executors ───
def test_registry_base_sepolia_and_base_mainnet_deployed():
    assert executor_registry.is_deployed("base_sepolia") is True
    # Base mainnet (8453) is now genuinely deployed (v1, on-chain verified).
    assert executor_registry.is_deployed("base") is True
    for chain in ("ethereum", "arbitrum", "optimism", "polygon", "bnb"):
        assert executor_registry.is_deployed(chain) is False, chain


# ── Runtime contract: operator/env passes deployment truth → EXECUTABLE ──────
def test_executor_deployed_true_executable():
    d = _ev("base", executor_deployed=True)
    assert d.executable is True and d.verdict is Verdict.EXECUTABLE


# ── Default (registry) fail-closed: undeployed chain is rejected ─────────────
# Base mainnet is now genuinely deployed, so the fail-closed default-registry
# intent is preserved against a genuinely UNDEPLOYED chain (ethereum) instead.
def test_undeployed_chain_default_registry_fail_closed():
    assert executor_registry.is_deployed("ethereum") is False
    d = _ev("ethereum")                   # executor_deployed=None ⇒ registry
    assert d.executable is False
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "executor_deployed"
    assert d.reason == "no_deployed_executor_on_chain:ethereum"


# ── Deployed V1 receiver: UniV3 route executable; non-UniV3 still fail-closed ─
def test_base_mainnet_v1_univ3_executable_and_aerodrome_requires_new_receiver():
    # balancer_v2 flash + uniswap_v3 swap on the deployed V1 receiver.
    ok = _ev("base")
    assert ok.verdict is Verdict.EXECUTABLE and ok.executable is True
    # Aerodrome is NOT native to the V1 receiver ⇒ REQUIRES_NEW_RECEIVER, never
    # silently executable. Deployment does NOT widen capability.
    ne = evaluate_settlement(flash_provider="balancer_v2",
                             swap_venues=["aerodrome"], chain="base")
    assert ne.verdict is Verdict.REQUIRES_NEW_RECEIVER
    assert ne.first_blocker == "receiver_schema_compatible"


# ── Every non-Base chain is fail-closed (never executable) ───────────────────
def test_all_five_non_base_chains_fail_closed():
    # Chains where the Balancer V2 flash head IS available → blocked at the
    # executor-deployment gate (no executor on those chains).
    for chain in ("ethereum", "arbitrum", "optimism", "polygon"):
        d = _ev(chain)
        assert d.executable is False, chain
        assert d.verdict is Verdict.REJECTED, chain
        assert d.first_blocker == "executor_deployed", chain
    # BNB has no Balancer V2 flash head → fails closed even earlier.
    d = _ev("bnb")
    assert d.executable is False
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "flash_provider_chain_supported"


# ── Even a perfect UniV3 + Aave route is NOT executable without executor ─────
def test_no_false_positive_on_unregistered_chain():
    d = evaluate_settlement(flash_provider="aave_v3", swap_venues=["uniswap_v3"],
                            chain="arbitrum")
    assert d.executable is False
    assert d.first_blocker == "executor_deployed"


# ── A chain flips to EXECUTABLE automatically once its executor is deployed ──
def test_explicit_executor_deployed_true_flips_to_executable():
    d = _ev("arbitrum", executor_deployed=True)
    assert d.executable is True and d.verdict is Verdict.EXECUTABLE


def test_explicit_executor_deployed_false_is_fail_closed():
    d = _ev("base", executor_deployed=False)
    assert d.executable is False and d.first_blocker == "executor_deployed"


# ── The executor gate is the LAST cell (schema/venue/flash checked first) ────
def test_executor_gate_does_not_mask_earlier_blockers():
    # Non-UniV3 venue still reports the receiver-schema blocker first
    # (REQUIRES_NEW_RECEIVER), not the executor gate.
    d = evaluate_settlement(flash_provider="balancer_v2", swap_venues=["aerodrome"],
                            chain="arbitrum")
    assert d.verdict is Verdict.REQUIRES_NEW_RECEIVER
    assert d.first_blocker == "receiver_schema_compatible"
