"""Read-only M3 VPS diagnostic ordering and fail-closed attribution."""

from scripts.m3_0_vps_validate import _first_blocking_stage


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
