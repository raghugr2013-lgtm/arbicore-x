"""Read-only M3 VPS diagnostic ordering and fail-closed attribution."""

from scripts.m3_0_vps_validate import (
    _first_blocking_stage, _quote_block_from_evidence, _plan_from_evidence,
    _flash_loan_evidence_filter)


def test_m3_selects_flash_loan_verifier_evidence_schema():
    assert _flash_loan_evidence_filter("CONFIRMED") == {
        "source_component": "flash_loan_arb_verifier",
        "verification_status": "CONFIRMED",
    }
    assert _flash_loan_evidence_filter() == {
        "source_component": "flash_loan_arb_verifier",
    }


def test_quote_block_retrieved_from_quotes_hop_evidence():
    doc = {
        "block_context": {"verified_at_ts": 123.0},
        "quotes": {"hop_legs": [{"block_number": 50570372}]},
    }
    assert _quote_block_from_evidence(doc) == 50570372


def test_quote_block_never_comes_from_timestamp():
    doc = {"block_context": {"verified_at_ts": 50570372.0}}
    assert _quote_block_from_evidence(doc) is None


def test_quote_block_accepts_explicit_numeric_serialization():
    doc = {"block_context": {"block_number": "50571130"}}
    assert _quote_block_from_evidence(doc) == 50571130


def test_evidence_to_m3_plan_preserves_hop_quote_block():
    doc = {
        "bundle_id": "b1", "borrow_token": "USDT", "input_amount_usd": 10_000,
        "route": {"route_pools": ["p1", "p2", "p3"],
                  "cycle_token_path": ["USDT", "USDC", "WETH", "USDT"]},
        "quotes": {"hop_legs": [{"block_number": 50571615},
                                  {"block_number": 50571619}]},
    }
    plan = _plan_from_evidence(doc)
    assert plan["quoted_block"] == 50571619
    assert plan["deadline_ts"] is None


def _ok():
    return {
        "stage_1_plan_shape": {"shape_ok": True},
        "stage_6_facts": {"route_quote_status": "ok", "n_hop_legs": 2},
        "stage_8_mev": {"congestion_pct": 20.0, "mev_ok": True},
        "stage_3_head_block": 100,
        "stage_4_borrow_price_usd": 2500.0,
        "stage_7_flashloan_availability": {"available": True},
        "stage_9_economics": {"economics_inputs_present": True},
        "stage_10_all_in_cost": {"available": True},
        "stage_11_prebroadcast_gates": {
            "block_freshness": True, "reorg_protection": True,
            "deadline": True, "price_ok": True, "tvl_ok": True,
        },
    }


def test_economics_is_attributed_before_head_and_mev_later_stages():
    d = _ok()
    d["stage_9_economics"] = {"economics_inputs_present": False}
    assert "stage_9_economics" in _first_blocking_stage(d)


def test_all_in_cost_missing_is_fail_closed():
    d = _ok()
    d["stage_10_all_in_cost"] = {"available": False}
    assert "stage_10_all_in_cost" in _first_blocking_stage(d)


def test_prebroadcast_gate_is_reported_after_fresh_dependencies():
    d = _ok()
    d["stage_11_prebroadcast_gates"]["tvl_ok"] = False
    assert "stage_11_prebroadcast_gates.tvl_ok" in _first_blocking_stage(d)


def test_complete_probe_can_be_green_without_claiming_duplicate():
    d = _ok()
    assert _first_blocking_stage(d).startswith("none - all fresh stages")
