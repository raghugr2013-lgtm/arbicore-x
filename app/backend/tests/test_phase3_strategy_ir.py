"""Phase-3 — native Strategy IR: schema, fingerprint, execution isolation, adapter.

Deterministic; the registry test uses the local Mongo. Proves a Strategy IR is
DATA ONLY and can never carry or create execution authority.
"""
import asyncio

import pytest
from pydantic import ValidationError

from arbicore.strategy_ir.schema import (
    StrategyIR, StrategyProvenance, SourceClass, StrategyIRValidationError,
    compute_fingerprint, FORBIDDEN_KEYS)
from arbicore.strategy_ir.adapter import candidate_to_opportunity_hypothesis
from arbicore.economics.opportunity_decision import decide_opportunity


def _ir(**kw):
    base = dict(strategy_type="dex_dex",
                parameters={"pair": "WETH/USDC", "min_edge_bps": 15},
                constraints={"max_notional_usd": 50_000, "max_hops": 2},
                required_capabilities=["base", "flash_aave_v3"],
                route_hints=[{"dex": "aerodrome", "token_in": "WETH", "token_out": "USDC"}],
                provenance=StrategyProvenance(source="strategy_factory", trust=0.7, confidence=0.6),
                source_class=SourceClass.EXTERNAL)
    base.update(kw)
    return StrategyIR(**base)


# ── schema / validation ──
def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        _ir(strategy_type="fx_scalp")


def test_version_must_be_positive():
    with pytest.raises(ValidationError):
        _ir(strategy_version=0)


def test_valid_ir_validates_and_gets_fingerprint():
    ir = _ir().validate_non_executable()
    assert ir.strategy_fingerprint.startswith("sfp_")
    assert ir.strategy_type == "dex_dex"


# ── fingerprint identity ──
def test_fingerprint_is_deterministic_and_semantic():
    a = _ir().validate_non_executable().strategy_fingerprint
    b = _ir().validate_non_executable().strategy_fingerprint
    assert a == b                                   # deterministic
    # volatile fields do not change identity
    c = _ir(strategy_version=9,
            provenance=StrategyProvenance(source="github", trust=0.1, confidence=0.1),
            lineage=["x"]).validate_non_executable().strategy_fingerprint
    assert c == a
    # semantic change => new identity
    d = _ir(parameters={"pair": "WETH/USDC", "min_edge_bps": 99}).validate_non_executable().strategy_fingerprint
    assert d != a


# ── EXECUTION ISOLATION (core security) ──
@pytest.mark.parametrize("bad", ["private_key", "signer", "calldata", "broadcast",
                                 "execution_mode", "kill_switch", "authorize",
                                 "bypass_simulation", "allowlist_override",
                                 "profitability_override", "enable_live"])
def test_forbidden_field_in_parameters_rejected(bad):
    ir = _ir(parameters={"pair": "WETH/USDC", bad: "anything"})
    with pytest.raises(StrategyIRValidationError):
        ir.validate_non_executable()


def test_forbidden_field_nested_in_route_hints_rejected():
    ir = _ir(route_hints=[{"dex": "x", "userData": "0xdeadbeef"}])
    with pytest.raises(StrategyIRValidationError):
        ir.validate_non_executable()


def test_forbidden_field_case_and_dash_insensitive():
    ir = _ir(constraints={"Kill-Switch": True})
    with pytest.raises(StrategyIRValidationError):
        ir.validate_non_executable()


# ── adapter isolation: hypothesis cannot pass the existing sim gate ──
def test_adapter_hypothesis_is_non_executable_and_fails_gate():
    ir = _ir().validate_non_executable()
    hyp = candidate_to_opportunity_hypothesis(ir)
    assert hyp["executable"] is False
    assert hyp["provenance"] == "STRATEGY_IR_CANDIDATE"
    assert hyp["quote_status"] == "UNAVAILABLE"
    assert "calldata_hex" not in hyp and "signer" not in hyp
    # feed it to the REAL decision path with permissive allowlists — must still
    # refuse to execute (fails quote freshness / calldata / gas / repayment).
    d = decide_opportunity(hyp, router_allowlist=["0xrouter"],
                           token_allowlist=["WETH", "USDC"])
    assert d.would_execute is False


def test_adapter_output_has_no_execution_authority_keys():
    hyp = candidate_to_opportunity_hypothesis(_ir().validate_non_executable())
    forbidden_present = FORBIDDEN_KEYS.intersection({k.lower() for k in hyp})
    assert not forbidden_present


# ── registry (local Mongo) ──
def test_registry_register_and_duplicate_idempotent():
    from arbicore.strategy_ir import registry as reg

    async def _run():
        # isolate: clear this fingerprint's rows first
        ir = _ir().validate_non_executable()
        await reg._registry.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        await reg._candidates.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        r1 = await reg.register(ir)
        assert r1["registered"] is True and r1["duplicate"] is False
        r2 = await reg.register(_ir().validate_non_executable())   # same fp+version
        assert r2["duplicate"] is True                              # idempotent
        entry = await reg.get_registry_entry(r1["strategy_id"])
        assert entry and entry["strategy_fingerprint"] == ir.strategy_fingerprint
        # cleanup
        await reg._registry.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})
        await reg._candidates.delete_many({"strategy_fingerprint": ir.strategy_fingerprint})

    asyncio.get_event_loop().run_until_complete(_run())
