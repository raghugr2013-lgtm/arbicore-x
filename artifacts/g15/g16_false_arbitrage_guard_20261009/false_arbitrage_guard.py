"""G1.6 — Offline false-arbitrage detection guard (investigation flags only).

Additive accounting checks over frozen MEV Scout winner rows.
Does NOT rewrite source classifications and NEVER declares non-arbitrage
solely because a pattern matched.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

FLAG_CROSS = "POTENTIAL_CROSS_TX_MIRROR"
FLAG_REPEATED = "REPEATED_POOL_ROUTE"
FLAG_BOTH = "BOTH_FLAGS"
FLAG_NONE = "NO_FLAG"

DEFAULT_AMOUNT_TOLERANCE = 0.05  # relative |a-b|/max(a,b)
DEFAULT_BLOCK_WINDOW = 3


def _norm_addr(a: Optional[str]) -> str:
    return (a or "").strip().lower()


def _as_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(x)
    except (TypeError, ValueError):
        try:
            return int(str(x), 0)
        except (TypeError, ValueError):
            return None


def amounts_comparable(a: Any, b: Any, *, tolerance: float) -> bool:
    a_i = _as_int(a)
    b_i = _as_int(b)
    if a_i is None or b_i is None:
        return False
    if a_i < 0 or b_i < 0:
        return False
    if a_i == 0 and b_i == 0:
        return True
    denom = max(a_i, b_i)
    if denom == 0:
        return False
    return abs(a_i - b_i) / denom <= tolerance


def extract_legs(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    legs = row.get("legs") or []
    if not isinstance(legs, list):
        return []
    out = []
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        pool = _norm_addr(leg.get("pool"))
        tin = _norm_addr(leg.get("token_in"))
        tout = _norm_addr(leg.get("token_out"))
        ain = _as_int(leg.get("amount_in_raw"))
        aout = _as_int(leg.get("amount_out_raw"))
        if not pool or not tin or not tout:
            continue
        out.append(
            {
                "pool": pool,
                "token_in": tin,
                "token_out": tout,
                "amount_in_raw": ain,
                "amount_out_raw": aout,
                "venue": leg.get("venue"),
            }
        )
    return out


def repeated_pool_in_route(row: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """True if the same pool appears more than once in the route/legs."""
    pools_field = row.get("pools")
    seq: List[str] = []
    if isinstance(pools_field, list):
        seq = [_norm_addr(p) for p in pools_field if _norm_addr(p)]
    legs = extract_legs(row)
    if not seq and legs:
        seq = [lg["pool"] for lg in legs]
    seen = set()
    dupes = []
    for p in seq:
        if p in seen and p not in dupes:
            dupes.append(p)
        seen.add(p)
    # also catch multi-leg reuse even if pools[] was unique-set
    leg_counts: Dict[str, int] = defaultdict(int)
    for lg in legs:
        leg_counts[lg["pool"]] += 1
    for p, n in leg_counts.items():
        if n > 1 and p not in dupes:
            dupes.append(p)
    return (len(dupes) > 0, dupes)


def legs_are_reverse_mirror(
    a: Dict[str, Any],
    b: Dict[str, Any],
    *,
    tolerance: float,
) -> Tuple[bool, str]:
    """Same pool, opposite direction, comparable overlapping sizes."""
    if a["pool"] != b["pool"]:
        return False, "pool_mismatch"
    if a["token_in"] != b["token_out"] or a["token_out"] != b["token_in"]:
        return False, "direction_not_reversed"
    # Compare a.amount_in vs b.amount_out (token a_in == b_out) and vice versa.
    # Both sides must be comparable — one-sided proximity is insufficient.
    c1 = amounts_comparable(a["amount_in_raw"], b["amount_out_raw"], tolerance=tolerance)
    c2 = amounts_comparable(a["amount_out_raw"], b["amount_in_raw"], tolerance=tolerance)
    if c1 and c2:
        return True, "reverse_direction_both_amounts_within_tolerance"
    return False, "amount_mismatch"


@dataclass
class MirrorLink:
    tx_a: str
    tx_b: str
    block_a: int
    block_b: int
    tx_index_a: Optional[int]
    tx_index_b: Optional[int]
    pool: str
    direction_a: str
    direction_b: str
    amount_in_a: Optional[int]
    amount_out_a: Optional[int]
    amount_in_b: Optional[int]
    amount_out_b: Optional[int]
    block_delta: int
    rationale: str
    same_searcher: bool
    same_operator: bool
    net_usd_a: Optional[float]
    net_usd_b: Optional[float]

    def pair_key(self) -> Tuple[str, str]:
        return tuple(sorted((self.tx_a, self.tx_b)))  # type: ignore[return-value]


@dataclass
class GuardResult:
    tx_hash: str
    original_classification: Any
    original_pipeline_class: Any
    original_net_usd: Optional[float]
    guard_flag: str
    repeated_pools: List[str] = field(default_factory=list)
    mirror_links: List[str] = field(default_factory=list)  # peer tx hashes
    inferred_bundle_net_usd: Optional[float] = None
    notes: List[str] = field(default_factory=list)


def _net_usd(row: Dict[str, Any]) -> Optional[float]:
    for k in ("searcher_kept_net_usd", "searcher_kept_net_strict_usd", "kept_net_upper_bound_usd"):
        v = row.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def find_cross_tx_mirrors(
    rows: Sequence[Dict[str, Any]],
    *,
    block_window: int = DEFAULT_BLOCK_WINDOW,
    amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
) -> List[MirrorLink]:
    """Find potential cross-tx mirrors. Deduplicates undirected pairs."""
    # Index legs by pool -> list of (row_idx, leg)
    by_pool: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    normalised: List[Dict[str, Any]] = []
    for i, row in enumerate(rows):
        block = _as_int(row.get("block"))
        if block is None:
            normalised.append(row)
            continue
        legs = extract_legs(row)
        normalised.append(row)
        for leg in legs:
            by_pool[leg["pool"]].append((i, leg))

    links: List[MirrorLink] = []
    seen_pairs = set()

    for pool, entries in by_pool.items():
        # sort by block for windowed compare
        entries_sorted = sorted(
            entries,
            key=lambda t: (
                _as_int(rows[t[0]].get("block")) or 0,
                _as_int(rows[t[0]].get("tx_index")) or 0,
                rows[t[0]].get("tx_hash") or "",
            ),
        )
        for ai in range(len(entries_sorted)):
            i, leg_a = entries_sorted[ai]
            row_a = rows[i]
            ba = _as_int(row_a.get("block"))
            ha = (row_a.get("tx_hash") or "").lower()
            if ba is None or not ha:
                continue
            for bi in range(ai + 1, len(entries_sorted)):
                j, leg_b = entries_sorted[bi]
                row_b = rows[j]
                bb = _as_int(row_b.get("block"))
                hb = (row_b.get("tx_hash") or "").lower()
                if bb is None or not hb or ha == hb:
                    continue
                if bb - ba > block_window:
                    break  # further entries only farther
                if abs(bb - ba) > block_window:
                    continue
                ok, why = legs_are_reverse_mirror(leg_a, leg_b, tolerance=amount_tolerance)
                if not ok:
                    continue
                pair = tuple(sorted((ha, hb)))
                # one link record per unordered tx pair + pool
                key = (pair[0], pair[1], pool)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                same_s = _norm_addr(row_a.get("searcher_contract")) == _norm_addr(
                    row_b.get("searcher_contract")
                ) and bool(_norm_addr(row_a.get("searcher_contract")))
                same_o = _norm_addr(row_a.get("operator_eoa")) == _norm_addr(
                    row_b.get("operator_eoa")
                ) and bool(_norm_addr(row_a.get("operator_eoa")))
                rationale_parts = [
                    why,
                    f"same_pool={pool}",
                    f"block_delta={abs(bb - ba)} (window=±{block_window})",
                    f"same_searcher={same_s}",
                    f"same_operator={same_o}",
                ]
                links.append(
                    MirrorLink(
                        tx_a=ha,
                        tx_b=hb,
                        block_a=ba,
                        block_b=bb,
                        tx_index_a=_as_int(row_a.get("tx_index")),
                        tx_index_b=_as_int(row_b.get("tx_index")),
                        pool=pool,
                        direction_a=f"{leg_a['token_in']}->{leg_a['token_out']}",
                        direction_b=f"{leg_b['token_in']}->{leg_b['token_out']}",
                        amount_in_a=leg_a["amount_in_raw"],
                        amount_out_a=leg_a["amount_out_raw"],
                        amount_in_b=leg_b["amount_in_raw"],
                        amount_out_b=leg_b["amount_out_raw"],
                        block_delta=abs(bb - ba),
                        rationale="; ".join(rationale_parts),
                        same_searcher=same_s,
                        same_operator=same_o,
                        net_usd_a=_net_usd(row_a),
                        net_usd_b=_net_usd(row_b),
                    )
                )
    return links


def apply_guard(
    rows: Sequence[Dict[str, Any]],
    *,
    block_window: int = DEFAULT_BLOCK_WINDOW,
    amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
) -> Dict[str, Any]:
    """Return per-tx guard results + deduped mirror links + summary stats.

    Original classification / NET on each input row are left untouched; results
    are additive. Flags are investigation signals only.
    """
    links = find_cross_tx_mirrors(
        rows, block_window=block_window, amount_tolerance=amount_tolerance
    )
    peers: Dict[str, List[str]] = defaultdict(list)
    link_by_tx: Dict[str, List[MirrorLink]] = defaultdict(list)
    for link in links:
        peers[link.tx_a].append(link.tx_b)
        peers[link.tx_b].append(link.tx_a)
        link_by_tx[link.tx_a].append(link)
        link_by_tx[link.tx_b].append(link)

    # Union-find-ish bundles for corrected NET (sum of member original NETs)
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for link in links:
        union(link.tx_a, link.tx_b)

    nets = {(row.get("tx_hash") or "").lower(): _net_usd(row) for row in rows}
    bundle_members: Dict[str, List[str]] = defaultdict(list)
    for h in nets:
        if not h:
            continue
        if h in peers or h in parent:
            bundle_members[find(h)].append(h)

    bundle_net: Dict[str, Optional[float]] = {}
    for root, members in bundle_members.items():
        vals = [nets[m] for m in members]
        if any(v is None for v in vals):
            # keep visibility: sum of known + mark partial
            known = [v for v in vals if v is not None]
            bundle_net[root] = sum(known) if known else None
        else:
            bundle_net[root] = float(sum(vals))  # type: ignore[arg-type]

    results: List[GuardResult] = []
    flag_counts = defaultdict(int)
    for row in rows:
        h = (row.get("tx_hash") or "").lower()
        rep, dupes = repeated_pool_in_route(row)
        has_mirror = h in peers and len(peers[h]) > 0
        if rep and has_mirror:
            flag = FLAG_BOTH
        elif has_mirror:
            flag = FLAG_CROSS
        elif rep:
            flag = FLAG_REPEATED
        else:
            flag = FLAG_NONE
        flag_counts[flag] += 1
        inferred = None
        notes = [
            "guard_flag is an investigation signal, not proof of fraud or zero profit",
            "original_classification preserved",
        ]
        if has_mirror:
            root = find(h)
            inferred = bundle_net.get(root)
            notes.append(
                "inferred_bundle_net_usd = sum of original per-tx NETs in linked component; "
                "losses are not dropped"
            )
            if any(nets[m] is None for m in bundle_members.get(root, [])):
                notes.append("bundle_net_partial_missing_member_net")
        results.append(
            GuardResult(
                tx_hash=h,
                original_classification=row.get("classification"),
                original_pipeline_class=row.get("pipeline_class"),
                original_net_usd=_net_usd(row),
                guard_flag=flag,
                repeated_pools=dupes,
                mirror_links=sorted(set(peers.get(h, []))),
                inferred_bundle_net_usd=inferred,
                notes=notes,
            )
        )

    # Dedup overlapping mirrors: unique unordered pairs
    unique_pairs = sorted({link.pair_key() for link in links})

    return {
        "params": {
            "block_window": block_window,
            "amount_tolerance": amount_tolerance,
            "overlap_policy": (
                "Undirected (tx_a,tx_b,pool) keys; each tx counted once in flag histogram; "
                "bundle NET sums member original NETs without dropping negatives"
            ),
        },
        "row_count": len(rows),
        "flag_counts": dict(flag_counts),
        "mirror_link_count": len(links),
        "unique_mirror_pairs": len(unique_pairs),
        "results": [asdict(r) for r in results],
        "mirror_links": [asdict(l) for l in links],
    }


def load_jsonl(path: str, *, chain: Optional[str] = "base") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            import json

            d = json.loads(line)
            if chain is not None and d.get("chain") != chain:
                continue
            rows.append(d)
    return rows


__all__ = [
    "FLAG_CROSS",
    "FLAG_REPEATED",
    "FLAG_BOTH",
    "FLAG_NONE",
    "apply_guard",
    "find_cross_tx_mirrors",
    "repeated_pool_in_route",
    "amounts_comparable",
    "legs_are_reverse_mirror",
    "load_jsonl",
]
