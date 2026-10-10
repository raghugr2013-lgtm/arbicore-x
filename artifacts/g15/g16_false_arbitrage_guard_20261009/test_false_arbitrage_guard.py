"""Unit tests for G1.6 offline false-arbitrage guard."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from false_arbitrage_guard import (
    FLAG_BOTH,
    FLAG_CROSS,
    FLAG_NONE,
    FLAG_REPEATED,
    amounts_comparable,
    apply_guard,
    find_cross_tx_mirrors,
    legs_are_reverse_mirror,
    repeated_pool_in_route,
)


def _row(
    tx: str,
    block: int,
    legs,
    *,
    pools=None,
    net=1.0,
    searcher="0xabc",
    operator="0xdef",
    tx_index=1,
    classification="A",
):
    if pools is None:
        pools = []
        for lg in legs:
            p = lg["pool"]
            if p not in pools:
                pools.append(p)
    return {
        "tx_hash": tx,
        "chain": "base",
        "block": block,
        "tx_index": tx_index,
        "classification": classification,
        "pipeline_class": "test",
        "pools": pools,
        "legs": legs,
        "searcher_contract": searcher,
        "operator_eoa": operator,
        "searcher_kept_net_usd": net,
    }


def _leg(pool, tin, tout, ain, aout):
    return {
        "pool": pool,
        "token_in": tin,
        "token_out": tout,
        "amount_in_raw": str(ain),
        "amount_out_raw": str(aout),
        "venue": "test",
    }


POOL = "0x1111111111111111111111111111111111111111"
T0 = "0x2222222222222222222222222222222222222222"
T1 = "0x3333333333333333333333333333333333333333"


def test_amounts_comparable_boundaries():
    assert amounts_comparable(100, 100, tolerance=0.05)
    assert amounts_comparable(100, 95, tolerance=0.05)
    assert not amounts_comparable(100, 90, tolerance=0.05)
    assert not amounts_comparable(None, 100, tolerance=0.05)


def test_positive_cross_tx_mirror_within_window():
    rows = [
        _row("0xaa", 100, [_leg(POOL, T0, T1, 1000, 2000)], net=5.0, tx_index=1),
        _row("0xbb", 103, [_leg(POOL, T1, T0, 2000, 1000)], net=-1.0, tx_index=2),
    ]
    out = apply_guard(rows, block_window=3, amount_tolerance=0.05)
    flags = {r["tx_hash"]: r["guard_flag"] for r in out["results"]}
    assert flags["0xaa"] == FLAG_CROSS
    assert flags["0xbb"] == FLAG_CROSS
    assert out["unique_mirror_pairs"] == 1
    # losses not dropped in bundle
    for r in out["results"]:
        assert r["inferred_bundle_net_usd"] == pytest.approx(4.0)
        assert r["original_net_usd"] in (5.0, -1.0)


def test_non_match_different_pool():
    other = "0x4444444444444444444444444444444444444444"
    rows = [
        _row("0xaa", 100, [_leg(POOL, T0, T1, 1000, 2000)]),
        _row("0xbb", 101, [_leg(other, T1, T0, 2000, 1000)]),
    ]
    out = apply_guard(rows)
    assert out["mirror_link_count"] == 0
    assert all(r["guard_flag"] == FLAG_NONE for r in out["results"])


def test_block_window_boundary_inclusive():
    rows = [
        _row("0xaa", 100, [_leg(POOL, T0, T1, 1000, 2000)]),
        _row("0xbb", 103, [_leg(POOL, T1, T0, 2000, 1000)]),
    ]
    assert apply_guard(rows, block_window=3)["unique_mirror_pairs"] == 1
    assert apply_guard(rows, block_window=2)["unique_mirror_pairs"] == 0


def test_amount_mismatch_not_linked():
    rows = [
        _row("0xaa", 100, [_leg(POOL, T0, T1, 1000, 2000)]),
        _row("0xbb", 101, [_leg(POOL, T1, T0, 5000, 100)]),  # far off
    ]
    out = apply_guard(rows, amount_tolerance=0.05)
    assert out["mirror_link_count"] == 0


def test_repeated_pool_route():
    legs = [
        _leg(POOL, T0, T1, 1000, 2000),
        _leg(POOL, T1, T0, 2000, 1100),
    ]
    row = _row("0xaa", 100, legs, pools=[POOL, POOL])
    rep, dupes = repeated_pool_in_route(row)
    assert rep
    assert POOL in dupes
    out = apply_guard([row])
    assert out["results"][0]["guard_flag"] == FLAG_REPEATED


def test_both_flags():
    legs_a = [
        _leg(POOL, T0, T1, 1000, 2000),
        _leg(POOL, T1, T0, 2000, 1100),
    ]
    rows = [
        _row("0xaa", 100, legs_a, pools=[POOL, POOL], net=2.0),
        _row("0xbb", 101, [_leg(POOL, T1, T0, 2000, 1000)], net=0.5),
    ]
    out = apply_guard(rows)
    flags = {r["tx_hash"]: r["guard_flag"] for r in out["results"]}
    assert flags["0xaa"] == FLAG_BOTH
    assert flags["0xbb"] in (FLAG_CROSS, FLAG_BOTH)


def test_overlapping_candidates_dedup_by_pair():
    # three txs: a mirrors b and a mirrors c on same pool; pairs unique
    rows = [
        _row("0xaa", 100, [_leg(POOL, T0, T1, 1000, 2000)], net=3.0),
        _row("0xbb", 101, [_leg(POOL, T1, T0, 2000, 1000)], net=-0.5),
        _row("0xcc", 102, [_leg(POOL, T1, T0, 1990, 995)], net=-0.5),
    ]
    links = find_cross_tx_mirrors(rows, block_window=3, amount_tolerance=0.05)
    pairs = {tuple(sorted((l.tx_a, l.tx_b))) for l in links}
    assert ("0xaa", "0xbb") in pairs
    assert ("0xaa", "0xcc") in pairs
    # no duplicate pair rows
    assert len(links) == len(pairs)
    out = apply_guard(rows)
    # each tx once in results
    assert len(out["results"]) == 3
    assert out["unique_mirror_pairs"] == len(pairs)


def test_missing_evidence_legs_skipped():
    rows = [
        _row("0xaa", 100, [], pools=[]),  # no legs
        _row("0xbb", 101, [_leg(POOL, T1, T0, 2000, 1000)]),
    ]
    # force empty legs on aa
    rows[0]["legs"] = None
    out = apply_guard(rows)
    assert out["mirror_link_count"] == 0
    assert out["results"][0]["guard_flag"] == FLAG_NONE


def test_original_classification_preserved():
    rows = [
        _row("0xaa", 100, [_leg(POOL, T0, T1, 1000, 2000)], classification="B"),
        _row("0xbb", 101, [_leg(POOL, T1, T0, 2000, 1000)], classification="A"),
    ]
    out = apply_guard(rows)
    by = {r["tx_hash"]: r for r in out["results"]}
    assert by["0xaa"]["original_classification"] == "B"
    assert by["0xbb"]["original_classification"] == "A"
    # guard never sets classification to non-arb
    assert "non" not in by["0xaa"]["guard_flag"].lower()


def test_legs_are_reverse_mirror_unit():
    a = _leg(POOL, T0, T1, 1000, 2000)
    b = _leg(POOL, T1, T0, 2000, 1000)
    ok, why = legs_are_reverse_mirror(a, b, tolerance=0.05)
    assert ok
    assert "reverse" in why
