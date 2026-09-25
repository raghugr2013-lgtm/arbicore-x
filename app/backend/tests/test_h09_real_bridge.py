import pytest

from arbicore.certification.h09_real_bridge import simulate_candidate_binding


def bundle():
    return {
        "bundle_id": "flarb:candidate-1:123",
        "candidate_id": "candidate-1",
        "opportunity_id": "opp-1",
        "verification_status": "CONFIRMED",
        "broadcast": False,
        "chain": "base",
        "borrow_token": "USDC",
        "quotes": {
            "quoted_amount_in_wei": 10_000_000_000,
            "token_decimals": 6,
            "quote_block": 45169467,
        },
        "route": [{"venue_id": "pool-a"}],
        "liquidity": {"source": "onchain_reserves"},
        "economics": {"atomic_profit_usd": 25.0},
        "execution_plan": {
            "executor_address": "0x" + "11" * 20,
            "receiver_version": "v1",
            "token": "USDC",
            "exact_input_wei": 10_000_000_000,
            "route": [{"venue_id": "pool-a"}],
            "executor_entry_calldata": "0x1234",
        },
    }


@pytest.mark.asyncio
async def test_real_bridge_rejects_missing_provenance():
    class Repo:
        async def find_for_audit(self, **kwargs):
            return []

    result, diag = await simulate_candidate_binding(
        Repo(),
        audit_run_id="audit-1",
        scanner_tick_id=1,
        candidate_id="candidate-1",
        rpc_url="http://invalid",
        signer_present=False,
    )

    assert result is None
    assert diag["ok"] is False
    assert diag["broadcast"] is False
    assert diag["signed"] is False


@pytest.mark.asyncio
async def test_real_bridge_uses_exact_block_and_never_broadcasts():
    class Repo:
        async def find_for_audit(self, **kwargs):
            return [bundle()]

    seen = {}
    factory_seen = {}

    class FakeSimulator:
        def readiness(self):
            return {"ready": True}

        async def capability_self_test(self):
            return {"code_injection": False, "reason": "test-double"}

        async def simulate_atomic(self, **kwargs):
            seen.update(kwargs)
            return {
                "ok": False,
                "passed": False,
                "simulation_kind": "onchain_eth_call",
                "quote_block": 45169467,
                "signed": False,
                "broadcast": False,
            }

    def fake_sim_factory(**kwargs):
        factory_seen.update(kwargs)
        return FakeSimulator()

    result, diag = await simulate_candidate_binding(
        Repo(),
        audit_run_id="audit-1",
        scanner_tick_id=1,
        candidate_id="candidate-1",
        rpc_url="http://example",
        signer_present=False,
        sim_factory=fake_sim_factory,
    )

    # sim_factory is passed into the canonical probe; the bridge must
    # preserve exact candidate binding and never enable execution.
    assert seen["block_tag"] == hex(45169467)
    assert factory_seen["executor_address"] == "0x" + "11" * 20
    assert result["broadcast"] is False
    assert result["signed"] is False
    assert diag["broadcast"] is False
    assert diag["signed"] is False
