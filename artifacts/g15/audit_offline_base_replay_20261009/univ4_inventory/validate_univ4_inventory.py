#!/usr/bin/env python3
"""Validate UniV4 inventory outputs reconcile to the frozen 2,012-row cohort."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT.parent
WINNERS = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/g15/"
    "core-20261008T2216Z/G1_5_EXPORT_20261008T2216Z/MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl"
)
COVERAGE = AUDIT / "BASE_G15_ROUTE_COVERAGE.csv"


def venue_atoms(v):
    if not isinstance(v, str):
        return []
    return [p for p in v.split("+") if p]


def is_v4(a):
    return a == "UniswapV4" or a.startswith("UniV4")


def main() -> int:
    errors = []

    # 1) Recompute cohort from JSONL
    jsonl_hashes = []
    for line in open(WINNERS):
        o = json.loads(line)
        if o.get("chain") != "base":
            continue
        if any(is_v4(a) for a in venue_atoms(o.get("venue"))):
            jsonl_hashes.append(o["tx_hash"])
    if len(jsonl_hashes) != 2012:
        errors.append(f"JSONL cohort size {len(jsonl_hashes)} != 2012")

    # 2) Coverage CSV cohort
    csv_hashes = []
    with COVERAGE.open() as f:
        for r in csv.DictReader(f):
            if any(is_v4(a) for a in venue_atoms(r.get("venue"))):
                csv_hashes.append(r["tx_hash"])
    if len(csv_hashes) != 2012:
        errors.append(f"CSV cohort size {len(csv_hashes)} != 2012")
    if set(jsonl_hashes) != set(csv_hashes):
        errors.append("JSONL and CSV cohort hash sets differ")

    # 3) Cohort rows file
    cohort_path = ROOT / "univ4_cohort_rows.csv"
    if not cohort_path.exists():
        errors.append("missing univ4_cohort_rows.csv — run build_univ4_inventory.py first")
        print("FAIL", errors)
        return 1
    cohort_hashes = []
    with cohort_path.open() as f:
        for r in csv.DictReader(f):
            cohort_hashes.append(r["tx_hash"])
    if len(cohort_hashes) != 2012:
        errors.append(f"cohort_rows size {len(cohort_hashes)} != 2012")
    if set(cohort_hashes) != set(jsonl_hashes):
        errors.append("cohort_rows hashes != JSONL cohort")
    if len(cohort_hashes) != len(set(cohort_hashes)):
        errors.append("duplicate tx_hash in cohort_rows")

    # 4) Summary JSON
    summary = json.loads((ROOT / "univ4_inventory_summary.json").read_text())
    if summary["cohort"]["n_rows"] != 2012:
        errors.append("summary n_rows != 2012")

    # 5) Pool CSV: every source ref tx must be in cohort; unique pool count matches summary
    pool_path = ROOT / "univ4_pool_hook_inventory.csv"
    pool_ids = []
    refs_txs = set()
    with pool_path.open() as f:
        for r in csv.DictReader(f):
            pool_ids.append(r["pool_id"])
            n = int(r["n_source_rows"])
            # spot-check refs
            for ref in r["source_row_refs"].split(";"):
                if not ref or ref == "...":
                    continue
                tx = ref.split("|", 1)[0]
                refs_txs.add(tx)
            if n < 1:
                errors.append(f"pool {r['pool_id']} has n_source_rows < 1")
    if len(pool_ids) != len(set(pool_ids)):
        errors.append("duplicate pool_id in pool inventory")
    if len(pool_ids) != summary["unique_counts"]["pools_full_bytes32"]:
        errors.append("pool CSV count != summary unique pools")
    if not refs_txs <= set(jsonl_hashes):
        errors.append("pool source refs contain non-cohort txs")

    # 6) Every cohort row must have >=1 full pool id listed
    missing_pid = [r["tx_hash"] for r in csv.DictReader(cohort_path.open()) if int(r["n_v4_pool_ids_on_row"]) < 1]
    if missing_pid:
        errors.append(f"{len(missing_pid)} cohort rows missing pool ids")

    # 7) Token inventory count
    tok_n = sum(1 for _ in csv.DictReader((ROOT / "univ4_token_inventory.csv").open()))
    if tok_n != summary["unique_counts"]["tokens_with_observed_address"]:
        errors.append("token CSV count != summary")

    # 8) AB ge1/ge25 reconcile from cohort file
    ab_ge1 = ab_ge25 = v_ge1 = v_ge25 = 0
    with cohort_path.open() as f:
        for r in csv.DictReader(f):
            if r["classification"] not in ("A", "B"):
                continue
            try:
                k = float(r["searcher_kept_net_usd"]) if r["searcher_kept_net_usd"] != "" else None
            except ValueError:
                k = None
            if k is None:
                continue
            if k >= 1:
                ab_ge1 += 1
            if k >= 25:
                ab_ge25 += 1
            if r["owner_payout_basis"] == "VERIFIED":
                if k >= 1:
                    v_ge1 += 1
                if k >= 25:
                    v_ge25 += 1
    if ab_ge1 != summary["AB_kept_net_signal_not_capture"]["AB_kept_ge1"]:
        errors.append(f"AB_ge1 mismatch {ab_ge1} vs summary")
    if ab_ge25 != summary["AB_kept_net_signal_not_capture"]["AB_kept_ge25"]:
        errors.append(f"AB_ge25 mismatch {ab_ge25} vs summary")
    if v_ge1 != summary["verified_owner_separate"]["VERIFIED_AB_kept_ge1"]:
        errors.append("verified ge1 mismatch")
    if v_ge25 != summary["verified_owner_separate"]["VERIFIED_AB_kept_ge25"]:
        errors.append("verified ge25 mismatch")

    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        return 1
    print("PASS")
    print(
        json.dumps(
            {
                "cohort_rows": 2012,
                "unique_pools": len(pool_ids),
                "unique_tokens": tok_n,
                "AB_kept_ge1": ab_ge1,
                "AB_kept_ge25": ab_ge25,
                "VERIFIED_AB_kept_ge1": v_ge1,
                "VERIFIED_AB_kept_ge25": v_ge25,
                "recommendation": summary["decision"]["recommendation"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
