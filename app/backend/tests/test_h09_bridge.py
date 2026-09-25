import pytest

from arbicore.certification.h09_bridge import (
    build_candidate_simulation_binding,
    resolve_candidate_binding,
)


def complete_bundle():
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


def test_complete_binding():
    binding, diag = build_candidate_simulation_binding(complete_bundle())
    assert diag["ok"] is True
    assert binding is not None
    assert binding.is_complete()
    assert binding.chain == "base"
    assert binding.block_number == 45169467
    assert binding.exact_input_wei == 10_000_000_000
    assert binding.receiver_version == "v1"


def test_missing_binding_fails_closed():
    bundle = complete_bundle()
    del bundle["execution_plan"]["executor_entry_calldata"]
    binding, diag = build_candidate_simulation_binding(bundle)
    assert binding is not None
    assert diag["ok"] is False
    assert "calldata" in diag["missing_fields"]


@pytest.mark.asyncio
async def test_exact_provenance_required():
    class Repo:
        async def find_for_audit(self, **kwargs):
            return []

    bundle, binding, diag = await resolve_candidate_binding(
        Repo(),
        audit_run_id="audit-1",
        scanner_tick_id=1,
        candidate_id="candidate-1",
    )
    assert bundle is None
    assert binding is None
    assert diag["reason"] == "expected_exactly_one_bundle"


@pytest.mark.asyncio
async def test_wrong_candidate_cannot_bind():
    class Repo:
        async def find_for_audit(self, **kwargs):
            return [complete_bundle()]

    bundle, binding, diag = await resolve_candidate_binding(
        Repo(),
        audit_run_id="audit-1",
        scanner_tick_id=1,
        candidate_id="candidate-OTHER",
    )
    assert bundle is None
    assert binding is None
    assert diag["reason"] == "candidate_identity_mismatch"


@pytest.mark.asyncio
async def test_denied_bundle_cannot_bind():
    class Repo:
        async def find_for_audit(self, **kwargs):
            b = complete_bundle()
            b["verification_status"] = "DENIED"
            return [b]

    bundle, binding, diag = await resolve_candidate_binding(
        Repo(),
        audit_run_id="audit-1",
        scanner_tick_id=1,
        candidate_id="candidate-1",
    )
    assert bundle is None
    assert binding is None
    assert diag["reason"] == "bundle_not_confirmed"


@pytest.mark.asyncio
async def test_broadcast_bundle_cannot_bind():
    class Repo:
        async def find_for_audit(self, **kwargs):
            b = complete_bundle()
            b["broadcast"] = True
            return [b]

    bundle, binding, diag = await resolve_candidate_binding(
        Repo(),
        audit_run_id="audit-1",
        scanner_tick_id=1,
        candidate_id="candidate-1",
    )
    assert bundle is None
    assert binding is None
    assert diag["reason"] == "broadcast_evidence_forbidden"
