#!/usr/bin/env python3
"""G1.5 offline Base winner ↔ ArbiCore route-universe coverage (AUDIT ONLY).

Read-only. No RPC, no DB writes, no product-code changes.
Consumes:
  - frozen G1.5 winners JSONL
  - frozen ArbiCore Base universe snapshot (exported from running container)

Matching confidence tiers (documented in report):
  EXACT_POOL_AND_VENUE — every winner pool address ∈ ArbiCore resolved set
                         AND every leg venue maps to a supported ArbiCore dex
  PARTIAL_POOL_UNSUPPORTED_VENUE — all listed pools resolved, but ≥1 unsupported venue
  PARTIAL_POOL_SET   — ≥1 but not all winner pools ∈ resolved address set
  ROUTE_FAMILY       — all tokens ∈ ArbiCore TOKENS AND every leg venue maps to a
                       supported ArbiCore dex AND each undirected token pair has a
                       VENUES entry for that dex family (NO pool-address proof)
  UNMATCHED          — matchable identifiers present but outside universe
  UNMATCHABLE        — missing pools/legs/tokens required for matching

Token-overlap alone is NEVER sufficient for a positive match.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPORT = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/g15/"
    "core-20261008T2216Z/G1_5_EXPORT_20261008T2216Z"
)
WINNERS = EXPORT / "MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl"
UNIVERSE = ROOT / "arbicore_base_universe_snapshot.json"

# G1.5 venue label → ArbiCore dex family (or None if unsupported)
VENUE_MAP = {
    "UniswapV3": "uniswap_v3",
    "Aerodrome-Slipstream": "aerodrome_slipstream",
    "Aerodrome-Slipstream2": "aerodrome_slipstream",
    "Aerodrome-Slipstream3": "aerodrome_slipstream",
    "Aerodrome-V2": "aerodrome",
    # Explicit unsupported (kept for clarity / reporting)
    "UniswapV4": None,
    "UniV4": None,
    "PancakeV3": None,
    "UniswapV2": None,
    "Curve": None,
    "Balancer": None,
}


def _norm_addr(a: str | None) -> str | None:
    if not a or not isinstance(a, str):
        return None
    a = a.strip().lower()
    if not a.startswith("0x") or len(a) != 42:
        return None
    return a


def map_venue(label: str | None) -> tuple[str | None, str]:
    """Return (arbicore_dex_or_None, raw_label)."""
    if not label or not isinstance(label, str):
        return None, ""
    raw = label.strip()
    if raw in VENUE_MAP:
        return VENUE_MAP[raw], raw
    if raw.startswith("AlgebraIntegral"):
        return None, raw
    if raw.startswith("V3-type") or raw.startswith("V2-type"):
        return None, raw
    return None, raw


def load_universe(path: Path) -> dict:
    u = json.loads(path.read_text())
    token_by_addr = {v["address"].lower(): k for k, v in u["tokens"].items()}
    addr_to_pool = {}
    for p in u["pools"]:
        addr = p.get("address")
        if addr:
            addr_to_pool[addr.lower()] = p
    # undirected pair coverage per dex: frozenset({sym_a, sym_b})
    pair_by_dex: dict[str, set[frozenset[str]]] = defaultdict(set)
    for v in u["venues"]:
        pair_by_dex[v["dex"]].add(frozenset({v["a"], v["b"]}))
    return {
        "raw": u,
        "token_by_addr": token_by_addr,
        "token_syms": set(u["tokens"]),
        "addr_to_pool": addr_to_pool,
        "resolved_addrs": set(addr_to_pool),
        "pair_by_dex": pair_by_dex,
        "supported_dexes": set(pair_by_dex),
    }


def winner_leg_venues(o: dict) -> list[str]:
    legs = o.get("legs") or []
    out = []
    for leg in legs:
        if isinstance(leg, dict) and leg.get("venue"):
            out.append(str(leg["venue"]))
    if out:
        return out
    # fallback: venue field may be "A+B"
    v = o.get("venue")
    if isinstance(v, str) and v:
        return [p for p in v.split("+") if p]
    return []


def classify_match(o: dict, uni: dict) -> dict:
    pools = [_norm_addr(p) for p in (o.get("pools") or [])]
    pools = [p for p in pools if p]
    legs = o.get("legs") or []
    tokens = o.get("tokens") or []
    token_addrs = []
    for t in tokens:
        if isinstance(t, dict):
            token_addrs.append(_norm_addr(t.get("address")))
        elif isinstance(t, str):
            token_addrs.append(_norm_addr(t))
    token_addrs = [t for t in token_addrs if t]

    # Also collect from legs
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        for k in ("token_in", "token_out", "pool"):
            a = _norm_addr(leg.get(k) if k != "pool" else None)
            if a and k != "pool":
                token_addrs.append(a)
        pa = _norm_addr(leg.get("pool"))
        if pa and pa not in pools:
            pools.append(pa)

    token_addrs = sorted(set(token_addrs))
    pools = list(dict.fromkeys(pools))  # stable unique

    if not pools and not legs:
        return {
            "match_tier": "UNMATCHABLE",
            "match_reason": "missing_pools_and_legs",
            "pools_n": 0,
            "pools_in_universe": 0,
            "pools_matched": [],
            "tokens_all_in_universe": False,
            "venues_all_supported": False,
            "route_family_covered": False,
            "unsupported_venues": [],
            "unknown_tokens": [],
            "mapped_dexes": [],
        }

    pools_matched = [p for p in pools if p in uni["resolved_addrs"]]
    n_in = len(pools_matched)
    n_pools = len(pools)

    unknown_tokens = [t for t in token_addrs if t not in uni["token_by_addr"]]
    tokens_all = bool(token_addrs) and not unknown_tokens

    raw_venues = winner_leg_venues(o)
    mapped = []
    unsupported = []
    for rv in raw_venues:
        dex, raw = map_venue(rv)
        if dex is None:
            unsupported.append(raw or rv)
        else:
            mapped.append(dex)
    venues_all = bool(raw_venues) and not unsupported

    # Route-family: each consecutive hop's token symbols + mapped dex has a VENUES pair
    route_family = False
    hop_ok = []
    if venues_all and tokens_all and legs:
        ok = True
        for leg in legs:
            if not isinstance(leg, dict):
                ok = False
                break
            dex, _ = map_venue(leg.get("venue"))
            tin = _norm_addr(leg.get("token_in"))
            tout = _norm_addr(leg.get("token_out"))
            if not dex or not tin or not tout:
                ok = False
                break
            s_in = uni["token_by_addr"].get(tin)
            s_out = uni["token_by_addr"].get(tout)
            if not s_in or not s_out:
                ok = False
                break
            pair = frozenset({s_in, s_out})
            if pair not in uni["pair_by_dex"].get(dex, set()):
                ok = False
                hop_ok.append({"dex": dex, "pair": sorted(pair), "covered": False})
                break
            hop_ok.append({"dex": dex, "pair": sorted(pair), "covered": True})
        route_family = ok and bool(hop_ok)

    # Exact requires BOTH full pool-address coverage AND supported venues.
    # Pool addresses alone with an unsupported co-venue (e.g. UniV4) are PARTIAL.
    if n_pools == 0 and not legs:
        tier = "UNMATCHABLE"
        reason = "missing_pools_and_legs"
    elif n_pools == 0:
        if route_family:
            tier = "ROUTE_FAMILY"
            reason = "token_pair_and_venue_family_covered_without_pool_address_proof"
        else:
            tier = "UNMATCHABLE"
            reason = "no_valid_pool_addresses"
    elif n_in == n_pools and n_pools > 0 and venues_all:
        tier = "EXACT_POOL_AND_VENUE"
        reason = "all_pools_resolved_and_all_leg_venues_supported"
    elif n_in == n_pools and n_pools > 0 and not venues_all:
        tier = "PARTIAL_POOL_UNSUPPORTED_VENUE"
        reason = "all_listed_pools_resolved_but_route_includes_unsupported_venue"
    elif n_in > 0:
        tier = "PARTIAL_POOL_SET"
        reason = "some_pool_addresses_in_resolved_universe"
    elif route_family:
        tier = "ROUTE_FAMILY"
        reason = "token_pair_and_venue_family_covered_without_pool_address_proof"
    else:
        tier = "UNMATCHED"
        if unsupported:
            reason = "unsupported_venue_in_route"
        elif unknown_tokens:
            reason = "token_outside_universe"
        else:
            reason = "no_pool_or_route_family_match"

    return {
        "match_tier": tier,
        "match_reason": reason,
        "pools_n": n_pools,
        "pools_in_universe": n_in,
        "pools_matched": pools_matched,
        "tokens_all_in_universe": tokens_all,
        "venues_all_supported": venues_all,
        "route_family_covered": route_family,
        "unsupported_venues": sorted(set(unsupported)),
        "unknown_tokens": unknown_tokens,
        "mapped_dexes": mapped,
        "raw_venues": raw_venues,
    }


def pct(n: int, d: int) -> str:
    if d == 0:
        return "n/a"
    return f"{100.0 * n / d:.2f}%"


def median(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    if not xs:
        return None
    return statistics.median(xs)


def main() -> None:
    uni = load_universe(UNIVERSE)
    rows = []
    class_counts = Counter()
    tier_counts = Counter()
    tier_by_class = defaultdict(Counter)
    venue_atom = Counter()
    family_counts = Counter()
    owner_basis = Counter()
    profit_buckets = Counter()

    # value aggregates (Base only; report VERIFIED owner basis separately)
    kept_by_tier = defaultdict(list)
    kept_verified_by_tier = defaultdict(list)

    timing_ages = []
    same_block = 0
    censored_age = 0

    n_base = 0
    n_unmatchable = 0

    with WINNERS.open() as f:
        for line in f:
            o = json.loads(line)
            if o.get("chain") != "base":
                continue
            n_base += 1
            cls = o.get("classification") or "?"
            class_counts[cls] += 1
            family_counts[o.get("family") or "?"] += 1
            owner_basis[o.get("owner_payout_basis") or "MISSING"] += 1
            profit_buckets[o.get("profit_bucket") or "?"] += 1

            for v in winner_leg_venues(o):
                venue_atom[v] += 1

            m = classify_match(o, uni)
            tier_counts[m["match_tier"]] += 1
            tier_by_class[cls][m["match_tier"]] += 1
            if m["match_tier"] == "UNMATCHABLE":
                n_unmatchable += 1

            kept = o.get("searcher_kept_net_usd")
            if isinstance(kept, (int, float)) and not (isinstance(kept, float) and math.isnan(kept)):
                kept_by_tier[m["match_tier"]].append(float(kept))
                if o.get("owner_payout_basis") == "VERIFIED":
                    kept_verified_by_tier[m["match_tier"]].append(float(kept))

            t = o.get("timing") or {}
            age = t.get("route_state_age_s")
            if isinstance(age, (int, float)):
                timing_ages.append(float(age))
            if t.get("route_age_censored"):
                censored_age += 1
            if t.get("trigger_relation") == "same_block" or (
                t.get("blocks_between_trigger_and_winner") == 0
            ):
                same_block += 1

            rows.append(
                {
                    "tx_hash": o.get("tx_hash"),
                    "block": o.get("block"),
                    "timestamp_utc": o.get("timestamp_utc"),
                    "classification": cls,
                    "classification_reason": o.get("classification_reason"),
                    "family": o.get("family"),
                    "venue": o.get("venue"),
                    "venue_families": o.get("venue_families"),
                    "route": o.get("route"),
                    "pools_n": m["pools_n"],
                    "pools_in_universe": m["pools_in_universe"],
                    "match_tier": m["match_tier"],
                    "match_reason": m["match_reason"],
                    "tokens_all_in_universe": m["tokens_all_in_universe"],
                    "venues_all_supported": m["venues_all_supported"],
                    "route_family_covered": m["route_family_covered"],
                    "unsupported_venues": "|".join(m["unsupported_venues"]),
                    "owner_payout_basis": o.get("owner_payout_basis") or "MISSING",
                    "searcher_kept_net_usd": o.get("searcher_kept_net_usd"),
                    "searcher_kept_net_strict_usd": o.get("searcher_kept_net_strict_usd"),
                    "gross_profit_usd": o.get("gross_profit_usd"),
                    "profit_bucket": o.get("profit_bucket"),
                    "route_state_age_s": t.get("route_state_age_s"),
                    "route_age_censored": t.get("route_age_censored"),
                    "trigger_relation": t.get("trigger_relation"),
                    "blocks_between_trigger_and_winner": t.get(
                        "blocks_between_trigger_and_winner"
                    ),
                    "winner_tx_index": t.get("winner_tx_index") or o.get("tx_index"),
                    "opportunity_visible_at_prev_block_end": t.get(
                        "opportunity_visible_at_prev_block_end"
                    ),
                    "verified_vs_inferred_owner": (o.get("verified_vs_inferred") or {}).get(
                        "owner_payout_usd"
                    ),
                }
            )

    # CSV
    csv_path = ROOT / "BASE_G15_ROUTE_COVERAGE.csv"
    if rows:
        with csv_path.open("w", newline="") as cf:
            w = csv.DictWriter(cf, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # Summary JSON for report generation
    def kept_stats(xs):
        if not xs:
            return {"n": 0, "sum": 0.0, "median": None, "ge1": 0, "ge25": 0, "ge100": 0, "ge1000": 0}
        return {
            "n": len(xs),
            "sum": round(sum(xs), 4),
            "median": round(median(xs), 6) if median(xs) is not None else None,
            "ge1": sum(1 for x in xs if x >= 1),
            "ge25": sum(1 for x in xs if x >= 25),
            "ge100": sum(1 for x in xs if x >= 100),
            "ge1000": sum(1 for x in xs if x >= 1000),
        }

    # Unsupported venue prevalence among unmatched
    unsup_counter = Counter()
    for r in rows:
        if r["match_tier"] in ("UNMATCHED", "PARTIAL_POOL_SET"):
            for v in (r["unsupported_venues"] or "").split("|"):
                if v:
                    unsup_counter[v] += 1

    exact = tier_counts["EXACT_POOL_AND_VENUE"]
    partial_unsup = tier_counts["PARTIAL_POOL_UNSUPPORTED_VENUE"]
    partial_pool = tier_counts["PARTIAL_POOL_SET"]
    route_fam = tier_counts["ROUTE_FAMILY"]
    unmatched = tier_counts["UNMATCHED"]
    unmatchable = tier_counts["UNMATCHABLE"]
    partial_all = partial_unsup + partial_pool + route_fam

    summary = {
        "denominator_base_winners": n_base,
        "g15_classification_ABCD": dict(class_counts),
        "match_tiers": dict(tier_counts),
        "match_tiers_by_classification": {k: dict(v) for k, v in tier_by_class.items()},
        "coverage": {
            "exact_pool_and_venue": exact,
            "exact_pool_and_venue_pct": pct(exact, n_base),
            "partial_any": partial_all,
            "partial_any_pct": pct(partial_all, n_base),
            "partial_pool_unsupported_venue": partial_unsup,
            "partial_pool_set": partial_pool,
            "route_family_no_address_proof": route_fam,
            "unmatched": unmatched,
            "unmatched_pct": pct(unmatched, n_base),
            "unmatchable": unmatchable,
            "unmatchable_pct": pct(unmatchable, n_base),
            # Conservative addressable = EXACT only (pool addr + venue support)
            "conservative_addressable_exact": exact,
            # Sensitivity = EXACT + ROUTE_FAMILY (Aerodrome pairs without addr proof)
            "sensitivity_addressable_exact_or_route_family": exact + route_fam,
        },
        "kept_net_by_tier_ALL_OWNER_BASIS": {k: kept_stats(v) for k, v in kept_by_tier.items()},
        "kept_net_by_tier_VERIFIED_OWNER_ONLY": {
            k: kept_stats(v) for k, v in kept_verified_by_tier.items()
        },
        "owner_payout_basis": dict(owner_basis),
        "families": dict(family_counts),
        "profit_buckets": dict(profit_buckets),
        "leg_venue_atoms": venue_atom.most_common(),
        "unsupported_venue_hits_among_nonexact": unsup_counter.most_common(),
        "universe": {
            "git_sha": uni["raw"]["build_info"]["git_sha"],
            "git_tag": uni["raw"]["build_info"]["git_tag"],
            "build_time": uni["raw"]["build_info"]["build_time"],
            "n_venues": len(uni["raw"]["venues"]),
            "n_tokens": len(uni["raw"]["tokens"]),
            "registry_summary": uni["raw"]["registry_summary"],
            "resolved_pool_addresses": len(uni["resolved_addrs"]),
        },
        "timing_winner_side_observables": {
            "note": (
                "route_state_age_s is a G1.5 winner-side observable; "
                "NOT proof of ArbiCore discovery/decision latency causality."
            ),
            "n_with_route_state_age_s": len(timing_ages),
            "median_route_state_age_s": median(timing_ages),
            "p90_route_state_age_s": (
                statistics.quantiles(timing_ages, n=10)[8] if len(timing_ages) >= 10 else None
            ),
            "same_block_trigger_count": same_block,
            "route_age_censored_count": censored_age,
        },
    }

    (ROOT / "coverage_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary["coverage"], indent=2))
    print("class", summary["g15_classification_ABCD"])
    print("tiers", summary["match_tiers"])
    print("wrote", csv_path)


if __name__ == "__main__":
    main()
