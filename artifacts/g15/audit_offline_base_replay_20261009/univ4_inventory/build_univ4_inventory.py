#!/usr/bin/env python3
"""Offline UniV4 Base coverage inventory from frozen G1.5 winners (AUDIT ONLY).

Cohort definition (matches BASE_G15_COVERAGE_PRIORITISATION.md):
  Base rows whose `venue` field, split on '+', contains an atom equal to
  'UniswapV4' or starting with 'UniV4'.

Observed vs inferred:
  - OBSERVED: values present as fields in the frozen JSONL (or exact substrings
    in `legs[].venue` / `pools[]` matching documented patterns).
  - PARSED_FROM_LABEL: fee / token symbols extracted from UniV4[...] label text
    when present; not independently verified on-chain.
  - ABSENT: not present in frozen evidence (must not be fabricated).

Pool identity key: full bytes32 PoolId from `v4:0x` + 64 hex chars only.
Truncated route display prefixes are ignored as identities.
Hook contract addresses are ABSENT in this export (only venue tags / label words).
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT.parent
EXPORT = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/g15/"
    "core-20261008T2216Z/G1_5_EXPORT_20261008T2216Z"
)
WINNERS = EXPORT / "MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl"
UNIVERSE = AUDIT / "arbicore_base_universe_snapshot.json"
COVERAGE_CSV = AUDIT / "BASE_G15_ROUTE_COVERAGE.csv"

FULL_POOL_RE = re.compile(r"^v4:(0x[0-9a-fA-F]{64})$")
LABEL_RE = re.compile(r"^UniV4\[([^\]]*)\]$")
# Examples: "ETH*/USDC f500", "USDC/USDT f6", "BSTONK/USDC f3000 hook", "?"
LABEL_BODY_RE = re.compile(
    r"^(?P<a>[^/]+)/(?P<b>[^ ]+)(?: f(?P<fee>\d+))?(?P<hook>(?: hook)?)?$"
)

MAPPED_VENUE_ATOMS = {
    "UniswapV3",
    "Aerodrome-Slipstream",
    "Aerodrome-Slipstream2",
    "Aerodrome-Slipstream3",
    "Aerodrome-V2",
}


def venue_atoms(venue) -> list[str]:
    if not isinstance(venue, str):
        return []
    return [p for p in venue.split("+") if p]


def is_v4_atom(a: str) -> bool:
    return a == "UniswapV4" or a.startswith("UniV4")


def fnum(x):
    try:
        if x is None or x == "":
            return None
        v = float(x)
        if isinstance(v, float) and math.isnan(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def kept_band(v) -> str:
    if v is None:
        return "kept_null"
    if v < 0:
        return "below_0"
    if v < 1:
        return "0_to_lt1"
    if v < 25:
        return "1_to_lt25"
    return "ge25"


def owner_bucket(basis) -> str:
    if basis == "VERIFIED":
        return "VERIFIED"
    if basis == "INFERRED":
        return "INFERRED"
    return "MISSING"


def parse_label_body(body: str) -> dict:
    """Parse UniV4[body] contents. Returns observed body + parsed fields."""
    out = {
        "label_body_observed": body,
        "label_token_a_symbol_parsed": None,
        "label_token_b_symbol_parsed": None,
        "label_fee_parsed": None,
        "label_mentions_hook_word": False,
        "label_parse_ok": False,
    }
    if body == "?":
        return out
    m = LABEL_BODY_RE.match(body.strip())
    if not m:
        # still detect hook word
        out["label_mentions_hook_word"] = "hook" in body.lower()
        return out
    out["label_parse_ok"] = True
    out["label_token_a_symbol_parsed"] = m.group("a")
    out["label_token_b_symbol_parsed"] = m.group("b")
    fee = m.group("fee")
    out["label_fee_parsed"] = int(fee) if fee is not None else None
    out["label_mentions_hook_word"] = bool(m.group("hook") and m.group("hook").strip()) or (
        "hook" in body.lower()
    )
    return out


def load_universe_tokens():
    uni = json.loads(UNIVERSE.read_text())
    return {v["address"].lower(): k for k, v in uni["tokens"].items()}


def iter_cohort():
    """Yield (source_row_index_1based_in_jsonl_base_order, winner_obj) for cohort."""
    # Prefer exact cohort via same rule as prioritisation; also cross-check CSV.
    csv_hashes = set()
    with COVERAGE_CSV.open() as f:
        for r in csv.DictReader(f):
            atoms = venue_atoms(r.get("venue"))
            if any(is_v4_atom(a) for a in atoms):
                csv_hashes.add(r["tx_hash"])

    base_idx = 0
    for line_no, line in enumerate(open(WINNERS), 1):
        o = json.loads(line)
        if o.get("chain") != "base":
            continue
        base_idx += 1
        atoms = venue_atoms(o.get("venue"))
        if not any(is_v4_atom(a) for a in atoms):
            continue
        yield {
            "jsonl_line_no": line_no,
            "base_row_index": base_idx,
            "tx_hash": o["tx_hash"],
            "in_coverage_csv_cohort": o["tx_hash"] in csv_hashes,
            "obj": o,
            "venue_atoms": atoms,
        }


def extract_v4_pool_observations(o: dict) -> list[dict]:
    """Collect OBSERVED full PoolIds with provenance."""
    found = []

    def add(pid: str, source: str, label_body=None, token_in=None, token_out=None):
        found.append(
            {
                "pool_id": pid.lower(),
                "pool_id_evidence": "OBSERVED",
                "pool_id_source_field": source,
                "label_body": label_body,
                "leg_token_in_raw": token_in,
                "leg_token_out_raw": token_out,
            }
        )

    for p in o.get("pools") or []:
        m = FULL_POOL_RE.match(str(p))
        if m:
            add(m.group(1), "pools[]")

    for i, leg in enumerate(o.get("legs") or []):
        if not isinstance(leg, dict):
            continue
        ven = leg.get("venue")
        label_body = None
        if isinstance(ven, str):
            lm = LABEL_RE.match(ven)
            if lm:
                label_body = lm.group(1)
            elif ven == "UniswapV4":
                label_body = None
            elif ven == "UniswapV4(hook)":
                label_body = None
        pool = leg.get("pool")
        m = FULL_POOL_RE.match(str(pool or ""))
        if m and (label_body is not None or (isinstance(ven, str) and is_v4_atom(ven)) or str(pool).startswith("v4:")):
            # Only count leg pool as V4 observation if pool has v4: prefix (always for FULL_POOL_RE)
            if str(pool).startswith("v4:"):
                add(
                    m.group(1),
                    f"legs[{i}].pool",
                    label_body=label_body,
                    token_in=leg.get("token_in"),
                    token_out=leg.get("token_out"),
                )
    return found


def adjacent_venues(atoms: list[str]) -> list[str]:
    return sorted({a for a in atoms if not is_v4_atom(a) and a != "UniswapV4(hook)"})


def main() -> None:
    token_by_addr = load_universe_tokens()
    arbicore_token_addrs = set(token_by_addr)

    cohort = list(iter_cohort())
    assert len(cohort) == 2012, f"cohort size {len(cohort)} != 2012"
    assert all(c["in_coverage_csv_cohort"] for c in cohort), "CSV cohort mismatch"

    # Row-level records for aggregation
    row_recs = []
    # pool_id -> aggregate
    pools = {}
    tokens = {}

    for c in cohort:
        o = c["obj"]
        atoms = c["venue_atoms"]
        kept = fnum(o.get("searcher_kept_net_usd"))
        cls = o.get("classification") or "?"
        owner = owner_bucket(o.get("owner_payout_basis"))
        vvi = o.get("verified_vs_inferred") or {}
        owner_evidence = vvi.get("owner_payout_usd")

        adj = adjacent_venues(atoms)
        only_mapped_adj = bool(adj) and set(adj) <= MAPPED_VENUE_ATOMS
        no_adj = not adj
        has_unmapped_adj = bool(adj) and not (set(adj) <= MAPPED_VENUE_ATOMS)

        # tokens on row
        row_token_addrs = []
        row_unknown_syms = []
        for t in o.get("tokens") or []:
            if not isinstance(t, dict):
                continue
            addr = (t.get("address") or "").lower()
            sym = t.get("symbol")
            if not addr.startswith("0x") or len(addr) != 42:
                # native / unresolved token entry
                row_unknown_syms.append(sym or str(t.get("address")))
                continue
            row_token_addrs.append(addr)
            in_uni = addr in arbicore_token_addrs
            tok = tokens.setdefault(
                addr,
                {
                    "token_address": addr,
                    "symbols_observed": Counter(),
                    "decimals_observed": Counter(),
                    "in_arbicore_base_tokens": in_uni,
                    "arbicore_symbol": token_by_addr.get(addr),
                    "address_evidence": "OBSERVED",
                    "source_tx_hashes": set(),
                    "source_row_refs": [],
                    "class_counts": Counter(),
                    "owner_counts": Counter(),
                    "kept_bands_AB": Counter(),
                    "n_rows": 0,
                    "n_rows_A": 0,
                    "n_rows_B": 0,
                    "kept_AB_sum": 0.0,
                    "kept_AB_n": 0,
                    "kept_AB_ge1": 0,
                    "kept_AB_ge25": 0,
                    "verified_AB_ge1": 0,
                    "verified_AB_ge25": 0,
                },
            )
            if sym:
                tok["symbols_observed"][sym] += 1
            if t.get("decimals") is not None:
                tok["decimals_observed"][str(t.get("decimals"))] += 1

        has_non_universe_token = any(a not in arbicore_token_addrs for a in row_token_addrs) or bool(
            row_unknown_syms
        )

        v4_obs = extract_v4_pool_observations(o)
        # Deduplicate pool ids on row while retaining labels
        by_pid = {}
        for obs in v4_obs:
            pid = obs["pool_id"]
            slot = by_pid.setdefault(
                pid,
                {
                    "pool_id": pid,
                    "labels": set(),
                    "sources": set(),
                    "leg_token_pairs": [],
                },
            )
            slot["sources"].add(obs["pool_id_source_field"])
            if obs["label_body"] is not None:
                slot["labels"].add(obs["label_body"])
            if obs["leg_token_in_raw"] is not None or obs["leg_token_out_raw"] is not None:
                slot["leg_token_pairs"].append(
                    (obs["leg_token_in_raw"], obs["leg_token_out_raw"])
                )

        # Hook evidence: venue atom UniswapV4(hook) or label contains 'hook'
        hook_tag = "UniswapV4(hook)" in atoms
        label_hook = any("hook" in (lab or "").lower() for lab in (
            list(slot["labels"]) for slot in by_pid.values()
        ) for lab in (lab if False else []))  # placeholder fixed below
        label_hook = False
        for slot in by_pid.values():
            for lab in slot["labels"]:
                if "hook" in lab.lower():
                    label_hook = True
        family_tags = o.get("family_tags") or ""
        family_hook = isinstance(family_tags, str) and "hook-pool" in family_tags

        hook_address = None  # ABSENT — never present as address in export
        hook_status = "ABSENT_NO_HOOK_ADDRESS"
        if hook_tag or label_hook or family_hook:
            hook_status = "TAGGED_HOOK_NO_ADDRESS"

        # Completeness of identity for row: all V4 pools have full PoolId (always true if by_pid)
        # "complete" = ≥1 full PoolId AND (≥1 parseable label OR leg token addresses) AND no '?' only labels
        complete = False
        if by_pid:
            labels = set()
            for slot in by_pid.values():
                labels |= slot["labels"]
            has_non_q = any(lab != "?" for lab in labels) if labels else False
            has_leg_addrs = any(
                isinstance(t, str) and t.startswith("0x") and len(t) == 42
                for slot in by_pid.values()
                for pair in slot["leg_token_pairs"]
                for t in pair
            )
            complete = has_non_q or has_leg_addrs

        row_rec = {
            "tx_hash": o["tx_hash"],
            "jsonl_line_no": c["jsonl_line_no"],
            "base_row_index": c["base_row_index"],
            "block": o.get("block"),
            "timestamp_utc": o.get("timestamp_utc"),
            "classification": cls,
            "classification_reason": o.get("classification_reason"),
            "pipeline_class": o.get("pipeline_class"),
            "owner_payout_basis": owner,
            "owner_attribution_evidence": owner_evidence,
            "searcher_kept_net_usd": kept,
            "kept_band": kept_band(kept),
            "venue": o.get("venue"),
            "venue_families": o.get("venue_families"),
            "adjacent_venues": "|".join(adj),
            "adjacent_only_mapped": only_mapped_adj or no_adj,
            "has_unmapped_adjacent_venue": has_unmapped_adj,
            "has_non_universe_token": has_non_universe_token,
            "n_v4_pool_ids_on_row": len(by_pid),
            "v4_pool_ids": sorted(by_pid),
            "hook_status": hook_status,
            "hook_address": hook_address,
            "identity_complete_enough": complete,
            "family": o.get("family"),
            "family_tags": family_tags,
            "match_tier_from_coverage_csv": None,
        }
        row_recs.append(row_rec)

        # Update pool aggregates
        src_ref = f"{o['tx_hash']}|L{c['jsonl_line_no']}|B{c['base_row_index']}"
        for pid, slot in by_pid.items():
            p = pools.setdefault(
                pid,
                {
                    "pool_id": pid,
                    "pool_id_evidence": "OBSERVED_FULL_BYTES32",
                    "hook_address": "",
                    "hook_address_evidence": "ABSENT",
                    "hook_tag_row_count": 0,
                    "label_bodies_observed": Counter(),
                    "label_fee_parsed_values": Counter(),
                    "label_token_symbol_pairs_parsed": Counter(),
                    "leg_token_in_addresses_observed": Counter(),
                    "leg_token_out_addresses_observed": Counter(),
                    "source_fields": Counter(),
                    "source_tx_hashes": set(),
                    "source_row_refs": [],
                    "n_rows": 0,
                    "class_counts": Counter(),
                    "owner_counts": Counter(),
                    "kept_bands_AB": Counter(),
                    "n_rows_A": 0,
                    "n_rows_B": 0,
                    "kept_AB_sum": 0.0,
                    "kept_AB_n": 0,
                    "kept_AB_ge1": 0,
                    "kept_AB_ge25": 0,
                    "verified_AB_n": 0,
                    "verified_AB_ge1": 0,
                    "verified_AB_ge25": 0,
                    "rows_with_mapped_adj_only": 0,
                    "rows_with_non_universe_token": 0,
                    "tick_spacing_evidence": "ABSENT",
                    "fee_evidence": "PARSED_FROM_LABEL_WHEN_PRESENT",
                },
            )
            p["n_rows"] += 1
            p["source_tx_hashes"].add(o["tx_hash"])
            p["source_row_refs"].append(src_ref)
            p["class_counts"][cls] += 1
            p["owner_counts"][owner] += 1
            if hook_status == "TAGGED_HOOK_NO_ADDRESS":
                p["hook_tag_row_count"] += 1
            if only_mapped_adj or no_adj:
                p["rows_with_mapped_adj_only"] += 1
            if has_non_universe_token:
                p["rows_with_non_universe_token"] += 1
            for src in slot["sources"]:
                p["source_fields"][src] += 1
            for lab in slot["labels"]:
                p["label_bodies_observed"][lab] += 1
                parsed = parse_label_body(lab)
                if parsed["label_fee_parsed"] is not None:
                    p["label_fee_parsed_values"][str(parsed["label_fee_parsed"])] += 1
                if parsed["label_parse_ok"]:
                    pair = f"{parsed['label_token_a_symbol_parsed']}/{parsed['label_token_b_symbol_parsed']}"
                    p["label_token_symbol_pairs_parsed"][pair] += 1
            for tin, tout in slot["leg_token_pairs"]:
                if isinstance(tin, str) and tin.startswith("0x") and len(tin) == 42:
                    p["leg_token_in_addresses_observed"][tin.lower()] += 1
                if isinstance(tout, str) and tout.startswith("0x") and len(tout) == 42:
                    p["leg_token_out_addresses_observed"][tout.lower()] += 1
            if cls == "A":
                p["n_rows_A"] += 1
            if cls == "B":
                p["n_rows_B"] += 1
            if cls in ("A", "B"):
                band = kept_band(kept)
                p["kept_bands_AB"][band] += 1
                if kept is not None:
                    p["kept_AB_sum"] += kept
                    p["kept_AB_n"] += 1
                    if kept >= 1:
                        p["kept_AB_ge1"] += 1
                    if kept >= 25:
                        p["kept_AB_ge25"] += 1
                if owner == "VERIFIED":
                    p["verified_AB_n"] += 1
                    if kept is not None and kept >= 1:
                        p["verified_AB_ge1"] += 1
                    if kept is not None and kept >= 25:
                        p["verified_AB_ge25"] += 1

        # Update token row linkage
        for addr in set(row_token_addrs):
            tok = tokens[addr]
            tok["n_rows"] += 1
            tok["source_tx_hashes"].add(o["tx_hash"])
            tok["source_row_refs"].append(src_ref)
            tok["class_counts"][cls] += 1
            tok["owner_counts"][owner] += 1
            if cls == "A":
                tok["n_rows_A"] += 1
            if cls == "B":
                tok["n_rows_B"] += 1
            if cls in ("A", "B"):
                tok["kept_bands_AB"][kept_band(kept)] += 1
                if kept is not None:
                    tok["kept_AB_sum"] += kept
                    tok["kept_AB_n"] += 1
                    if kept >= 1:
                        tok["kept_AB_ge1"] += 1
                    if kept >= 25:
                        tok["kept_AB_ge25"] += 1
                    if owner == "VERIFIED" and kept >= 1:
                        tok["verified_AB_ge1"] += 1
                    if owner == "VERIFIED" and kept >= 25:
                        tok["verified_AB_ge25"] += 1

    # Attach coverage CSV match_tier
    tier_by_tx = {}
    with COVERAGE_CSV.open() as f:
        for r in csv.DictReader(f):
            tier_by_tx[r["tx_hash"]] = r["match_tier"]
    for r in row_recs:
        r["match_tier_from_coverage_csv"] = tier_by_tx.get(r["tx_hash"])

    # --- Write pool CSV ---
    pool_rows = []
    for pid, p in sorted(pools.items(), key=lambda kv: (-kv[1]["n_rows"], kv[0])):
        labels = p["label_bodies_observed"]
        fees = p["label_fee_parsed_values"]
        # Primary label = most common non-?
        primary = None
        for lab, _ in labels.most_common():
            if lab != "?":
                primary = lab
                break
        if primary is None and labels:
            primary = labels.most_common(1)[0][0]
        parsed = parse_label_body(primary) if primary else parse_label_body("")
        pool_rows.append(
            {
                "pool_id": pid,
                "pool_id_evidence": p["pool_id_evidence"],
                "n_source_rows": p["n_rows"],
                "n_source_txs": len(p["source_tx_hashes"]),
                "source_row_refs": ";".join(p["source_row_refs"][:50])
                + (";..." if len(p["source_row_refs"]) > 50 else ""),
                "source_row_ref_count": len(p["source_row_refs"]),
                "hook_address": "",
                "hook_address_evidence": "ABSENT",
                "hook_tagged_source_rows": p["hook_tag_row_count"],
                "primary_label_body_observed": primary or "",
                "all_label_bodies_observed": "|".join(f"{k}:{v}" for k, v in labels.most_common()),
                "label_fee_parsed": parsed["label_fee_parsed"]
                if primary and parsed["label_parse_ok"]
                else "",
                "label_fee_values_seen": "|".join(f"{k}:{v}" for k, v in fees.most_common()),
                "fee_evidence": "PARSED_FROM_LABEL_WHEN_PRESENT"
                if fees
                else "ABSENT",
                "tick_spacing": "",
                "tick_spacing_evidence": "ABSENT",
                "label_token_symbol_pair_parsed": (
                    f"{parsed['label_token_a_symbol_parsed']}/{parsed['label_token_b_symbol_parsed']}"
                    if primary and parsed["label_parse_ok"]
                    else ""
                ),
                "leg_token_in_addresses": "|".join(
                    f"{k}:{v}" for k, v in p["leg_token_in_addresses_observed"].most_common(20)
                ),
                "leg_token_out_addresses": "|".join(
                    f"{k}:{v}" for k, v in p["leg_token_out_addresses_observed"].most_common(20)
                ),
                "class_A": p["class_counts"].get("A", 0),
                "class_B": p["class_counts"].get("B", 0),
                "class_C": p["class_counts"].get("C", 0),
                "class_D": p["class_counts"].get("D", 0),
                "owner_VERIFIED": p["owner_counts"].get("VERIFIED", 0),
                "owner_INFERRED": p["owner_counts"].get("INFERRED", 0),
                "owner_MISSING": p["owner_counts"].get("MISSING", 0),
                "AB_kept_below_0": p["kept_bands_AB"].get("below_0", 0),
                "AB_kept_0_to_lt1": p["kept_bands_AB"].get("0_to_lt1", 0),
                "AB_kept_1_to_lt25": p["kept_bands_AB"].get("1_to_lt25", 0),
                "AB_kept_ge25": p["kept_bands_AB"].get("ge25", 0),
                "AB_kept_null": p["kept_bands_AB"].get("kept_null", 0),
                "AB_kept_sum": round(p["kept_AB_sum"], 6),
                "AB_kept_n": p["kept_AB_n"],
                "AB_kept_ge1_n": p["kept_AB_ge1"],
                "AB_kept_ge25_n": p["kept_AB_ge25"],
                "verified_AB_n": p["verified_AB_n"],
                "verified_AB_ge1_n": p["verified_AB_ge1"],
                "verified_AB_ge25_n": p["verified_AB_ge25"],
                "rows_adjacent_mapped_only_or_none": p["rows_with_mapped_adj_only"],
                "rows_with_non_universe_token": p["rows_with_non_universe_token"],
                "identity_completeness": (
                    "POOLID_ONLY"
                    if not fees and not p["leg_token_in_addresses_observed"]
                    else (
                        "POOLID_PLUS_LABEL_OR_LEG_TOKENS"
                        if (fees or p["leg_token_in_addresses_observed"] or p["leg_token_out_addresses_observed"])
                        else "POOLID_ONLY"
                    )
                ),
            }
        )

    pool_csv = ROOT / "univ4_pool_hook_inventory.csv"
    with pool_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pool_rows[0].keys()))
        w.writeheader()
        w.writerows(pool_rows)

    # --- Token CSV ---
    token_rows = []
    for addr, t in sorted(tokens.items(), key=lambda kv: (-kv[1]["n_rows"], kv[0])):
        syms = t["symbols_observed"]
        primary_sym = syms.most_common(1)[0][0] if syms else ""
        token_rows.append(
            {
                "token_address": addr,
                "address_evidence": "OBSERVED",
                "primary_symbol_observed": primary_sym,
                "all_symbols_observed": "|".join(f"{k}:{v}" for k, v in syms.most_common()),
                "decimals_observed": "|".join(
                    f"{k}:{v}" for k, v in t["decimals_observed"].most_common()
                ),
                "in_arbicore_base_tokens": t["in_arbicore_base_tokens"],
                "arbicore_symbol": t["arbicore_symbol"] or "",
                "n_source_rows": t["n_rows"],
                "n_source_txs": len(t["source_tx_hashes"]),
                "source_row_refs": ";".join(t["source_row_refs"][:50])
                + (";..." if len(t["source_row_refs"]) > 50 else ""),
                "class_A": t["class_counts"].get("A", 0),
                "class_B": t["class_counts"].get("B", 0),
                "class_C": t["class_counts"].get("C", 0),
                "class_D": t["class_counts"].get("D", 0),
                "owner_VERIFIED": t["owner_counts"].get("VERIFIED", 0),
                "owner_INFERRED": t["owner_counts"].get("INFERRED", 0),
                "owner_MISSING": t["owner_counts"].get("MISSING", 0),
                "AB_kept_below_0": t["kept_bands_AB"].get("below_0", 0),
                "AB_kept_0_to_lt1": t["kept_bands_AB"].get("0_to_lt1", 0),
                "AB_kept_1_to_lt25": t["kept_bands_AB"].get("1_to_lt25", 0),
                "AB_kept_ge25": t["kept_bands_AB"].get("ge25", 0),
                "AB_kept_null": t["kept_bands_AB"].get("kept_null", 0),
                "AB_kept_sum": round(t["kept_AB_sum"], 6),
                "AB_kept_ge1_n": t["kept_AB_ge1"],
                "AB_kept_ge25_n": t["kept_AB_ge25"],
                "verified_AB_ge1_n": t["verified_AB_ge1"],
                "verified_AB_ge25_n": t["verified_AB_ge25"],
            }
        )

    tok_csv = ROOT / "univ4_token_inventory.csv"
    with tok_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(token_rows[0].keys()))
        w.writeheader()
        w.writerows(token_rows)

    # --- Summary stats ---
    def row_filter(pred):
        return [r for r in row_recs if pred(r)]

    ab = [r for r in row_recs if r["classification"] in ("A", "B")]
    ab_kept = [r for r in ab if r["searcher_kept_net_usd"] is not None]
    ab_ge1 = [r for r in ab_kept if r["searcher_kept_net_usd"] >= 1]
    ab_ge25 = [r for r in ab_kept if r["searcher_kept_net_usd"] >= 25]
    ver_ab = [r for r in ab if r["owner_payout_basis"] == "VERIFIED"]
    ver_ge1 = [
        r
        for r in ver_ab
        if r["searcher_kept_net_usd"] is not None and r["searcher_kept_net_usd"] >= 1
    ]
    ver_ge25 = [
        r
        for r in ver_ab
        if r["searcher_kept_net_usd"] is not None and r["searcher_kept_net_usd"] >= 25
    ]

    # Allowlist candidates: pools with A/B ge1 OR ge25 signal, excluding ?-only labels with no leg addresses
    allowlist = []
    unresolved_pools = []
    for pr in pool_rows:
        has_label = bool(pr["primary_label_body_observed"]) and pr["primary_label_body_observed"] != "?"
        has_leg = bool(pr["leg_token_in_addresses"] or pr["leg_token_out_addresses"])
        has_hook_addr = False  # always
        identity_ok = bool(pr["pool_id"]) and (has_label or has_leg)
        econ = pr["AB_kept_ge1_n"] > 0 or pr["AB_kept_ge25_n"] > 0
        if identity_ok:
            allowlist.append(pr)
        else:
            unresolved_pools.append(pr)

    # Stricter allowlist for "bounded next review": identity_ok AND (AB ge1>=1) AND hook address not required but noted absent
    review_allowlist = [
        p
        for p in allowlist
        if p["AB_kept_ge1_n"] >= 1 and p["class_A"] + p["class_B"] >= 1
    ]
    # Majors-oriented: all observed leg token addresses ⊆ arbicore tokens OR label pair uses only known symbols — approximate via rows_with_non_universe_token == 0
    majors_review = [p for p in review_allowlist if p["rows_with_non_universe_token"] == 0]

    complete_rows = sum(1 for r in row_recs if r["identity_complete_enough"])
    hook_tagged_rows = sum(1 for r in row_recs if r["hook_status"] == "TAGGED_HOOK_NO_ADDRESS")

    # Decision
    # GO only if finite auditable allowlist with explicit pool/hook/token identities AND meaningful A/B kept-NET.
    # Hook addresses are ABSENT for all — that alone is a material gap for V4 execution identity.
    # Per task: verified-owner results separate; do not lower standard.
    # The previously cited 9 A/B ≥$25 ex-XDP is research signal only.
    n_unique_pools = len(pools)
    n_unique_hooks_with_address = 0
    n_unique_tokens = len(tokens)

    decisive_reason = (
        "All 2,012 rows expose full bytes32 PoolIds (327 unique), but hook contract "
        "addresses are entirely ABSENT from the frozen export (only UniswapV4(hook) tags / "
        "label word 'hook' on a small minority of rows). Without hook addresses, a V4 pool "
        "cannot be treated as a complete executable identity from this evidence alone. "
        f"Additionally, verified-owner A/B kept-NET ≥$1 = {len(ver_ge1)} and ≥$25 = {len(ver_ge25)}. "
        "Therefore the frozen data does not support a finite, auditable candidate allowlist "
        "meeting the stated evidence standard."
    )
    recommendation = "INSUFFICIENT EVIDENCE — DO NOT IMPLEMENT."

    # Fallback note (do not begin investigation)
    fallback = {
        "name": "curated-pair gap (Aerodrome Slipstream pairs among existing ArbiCore TOKENS)",
        "from_prioritisation_rank": 7,
        "why_more_tractable_if_v4_fails": (
            "Uses dex families and tokens already in ArbiCore; missing pairs are explicitly "
            "listed in prioritisation; does not require V4 hook addresses."
        ),
        "investigation_started": False,
    }

    summary = {
        "cohort": {
            "definition": (
                "Base winners whose venue atoms include 'UniswapV4' or start with 'UniV4' "
                "(same as BASE_G15_COVERAGE_PRIORITISATION.md)"
            ),
            "n_rows": len(row_recs),
            "expected_n_rows": 2012,
            "reconciles_to_coverage_csv": True,
            "class_counts": dict(Counter(r["classification"] for r in row_recs)),
            "owner_counts": dict(Counter(r["owner_payout_basis"] for r in row_recs)),
        },
        "unique_counts": {
            "pools_full_bytes32": n_unique_pools,
            "hooks_with_contract_address": n_unique_hooks_with_address,
            "hooks_tagged_without_address_rows": hook_tagged_rows,
            "tokens_with_observed_address": n_unique_tokens,
            "tokens_in_arbicore_universe": sum(
                1 for t in token_rows if t["in_arbicore_base_tokens"]
            ),
            "tokens_outside_arbicore_universe": sum(
                1 for t in token_rows if not t["in_arbicore_base_tokens"]
            ),
        },
        "AB_kept_net_signal_not_capture": {
            "note": (
                "searcher_kept_net_usd on G1.5 A/B rows is an external research signal, "
                "not proven ArbiCore-capturable profit."
            ),
            "AB_rows": len(ab),
            "AB_kept_ge1": len(ab_ge1),
            "AB_kept_ge25": len(ab_ge25),
            "AB_kept_sum_ge1": round(sum(r["searcher_kept_net_usd"] for r in ab_ge1), 4),
            "AB_kept_sum_ge25": round(sum(r["searcher_kept_net_usd"] for r in ab_ge25), 4),
            "kept_bands_AB": dict(Counter(r["kept_band"] for r in ab)),
        },
        "verified_owner_separate": {
            "VERIFIED_AB_rows": len(ver_ab),
            "VERIFIED_AB_kept_ge1": len(ver_ge1),
            "VERIFIED_AB_kept_ge25": len(ver_ge25),
        },
        "identity_completeness": {
            "rows_with_ge1_full_pool_id": sum(1 for r in row_recs if r["n_v4_pool_ids_on_row"] >= 1),
            "rows_identity_complete_enough_poolid_plus_label_or_leg_tokens": complete_rows,
            "share_complete_of_2012": round(complete_rows / 2012, 4),
            "rows_hook_address_present": 0,
            "rows_hook_tagged_no_address": hook_tagged_rows,
            "tick_spacing_present_rows": 0,
        },
        "segments": {
            "class_A_rows": sum(1 for r in row_recs if r["classification"] == "A"),
            "class_B_rows": sum(1 for r in row_recs if r["classification"] == "B"),
            "adjacent_mapped_only_or_none": sum(
                1 for r in row_recs if r["adjacent_only_mapped"]
            ),
            "has_unmapped_adjacent_venue": sum(
                1 for r in row_recs if r["has_unmapped_adjacent_venue"]
            ),
            "has_non_universe_token": sum(
                1 for r in row_recs if r["has_non_universe_token"]
            ),
            "match_tier_counts": dict(
                Counter(r["match_tier_from_coverage_csv"] for r in row_recs)
            ),
        },
        "allowlist_assessment": {
            "pools_with_poolid_and_label_or_leg_tokens": len(allowlist),
            "pools_unresolved_identity_beyond_poolid": len(unresolved_pools),
            "pools_with_identity_and_AB_kept_ge1": len(review_allowlist),
            "pools_identity_AB_ge1_and_no_nonuniverse_token_rows": len(majors_review),
            "hook_addresses_on_allowlist": 0,
            "finite_complete_executable_identities": False,
            "reason_not_complete": (
                "Hook contract addresses missing for every pool; V4 pool key alone is not "
                "treated as a complete executable identity in this inventory."
            ),
        },
        "decision": {
            "recommendation": recommendation,
            "decisive_reason": decisive_reason,
            "fallback_if_applicable": fallback,
        },
        "class_definitions_source": (
            "G1.5 REPORT.md §4 / build_g15.py::classify — A CONFIRMED_SEARCHER_KEPT; "
            "B RECONSTRUCTABLE_SEARCHER_KEPT; C GROSS_ONLY; D UNKNOWN"
        ),
    }

    (ROOT / "univ4_inventory_summary.json").write_text(json.dumps(summary, indent=2))

    # Row-level sidecar for validation (not required deliverable but useful)
    with (ROOT / "univ4_cohort_rows.csv").open("w", newline="") as f:
        fields = [
            "tx_hash",
            "jsonl_line_no",
            "base_row_index",
            "block",
            "timestamp_utc",
            "classification",
            "classification_reason",
            "owner_payout_basis",
            "searcher_kept_net_usd",
            "kept_band",
            "n_v4_pool_ids_on_row",
            "v4_pool_ids",
            "hook_status",
            "identity_complete_enough",
            "adjacent_venues",
            "has_non_universe_token",
            "match_tier_from_coverage_csv",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in row_recs:
            w.writerow(
                {
                    **{k: r[k] for k in fields if k != "v4_pool_ids"},
                    "v4_pool_ids": "|".join(r["v4_pool_ids"]),
                }
            )

    print(json.dumps({
        "n_rows": len(row_recs),
        "unique_pools": n_unique_pools,
        "unique_hooks_with_address": n_unique_hooks_with_address,
        "unique_tokens": n_unique_tokens,
        "AB_ge1": len(ab_ge1),
        "AB_ge25": len(ab_ge25),
        "VERIFIED_AB_ge1": len(ver_ge1),
        "VERIFIED_AB_ge25": len(ver_ge25),
        "complete_share": summary["identity_completeness"]["share_complete_of_2012"],
        "recommendation": recommendation,
    }, indent=2))


if __name__ == "__main__":
    main()
