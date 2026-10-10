"""Deterministic strategy-family classification over stored route evidence.

Protocol identity is taken only from explicit per-leg protocol fields
(``dex_protocol``, ``route_dex_protocols``, ``route_hops[].dex``). Pool ids,
pool addresses, and venue ids are never parsed into a protocol. The
flash-loan provider is not a route protocol. Asset class (stablecoin,
LST/LRT) uses the symbol sets already maintained by ``strategy_tagging``;
those sets do not assign a protocol.

No economics are computed here.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..scanners.flash_loan_arbitrage.strategy_tagging import (
    LST_LRT_SYMBOLS,
    STABLE_SYMBOLS,
)
from .fields import (
    CLASSIFIER_VERSION,
    KIND_LEG,
    KIND_QUOTE,
    KIND_UNAVAILABLE,
    STATUS_AVAILABLE,
    as_dict,
    is_number,
    observed,
    unavailable,
)

FAMILIES: Tuple[str, ...] = (
    "DEX_TO_DEX",
    "TRIANGULAR",
    "MULTI_HOP",
    "MULTI_DEX",
    "CROSS_POOL",
    "CROSS_PROTOCOL",
    "STABLECOIN_CROSS_PROTOCOL",
    "LST_LRT_CROSS_PROTOCOL",
    "COMPLEX_TRIANGULAR_CROSS_PROTOCOL",
)

PRIMARY_UNKNOWN = "UNKNOWN"
PRIMARY_UNCLASSIFIED = "UNCLASSIFIED"

STATE_COMPLETE = "COMPLETE"
STATE_INCOMPLETE = "INCOMPLETE"
STATE_UNKNOWN = "UNKNOWN"

CONF_HIGH = "HIGH"
CONF_MEDIUM = "MEDIUM"
CONF_LOW = "LOW"
CONF_NONE = "NONE"

STRATEGY_FULL = "FULLY_CLASSIFIED"
STRATEGY_PARTIAL = "PARTIALLY_CLASSIFIED"
STRATEGY_UNKNOWN = "UNKNOWN"


def _text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _symbol(value: Any) -> Optional[str]:
    text = _text(value)
    return text.upper() if text else None


def _protocol(value: Any) -> Optional[str]:
    text = _text(value)
    return text.lower() if text else None


def _is_address(value: str) -> bool:
    return value.startswith("0x") and len(value) >= 10


def _list_of(value: Any) -> Optional[List[Any]]:
    if isinstance(value, list):
        return list(value)
    return None


def _hop_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or isinstance(value, float):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


class _Source:
    """A stored route section plus the provenance prefix for its fields."""

    def __init__(self, payload: Dict[str, Any], prefix: str, kind: str) -> None:
        self.payload = payload
        self.prefix = prefix
        self.kind = kind

    def get_list(self, key: str) -> Optional[List[Any]]:
        if key not in self.payload:
            return None
        return _list_of(self.payload.get(key))


def _first_list(
    sources: Sequence[_Source], key: str,
) -> Tuple[Optional[List[Any]], Optional[str], Optional[str]]:
    for src in sources:
        found = src.get_list(key)
        if found is not None:
            return found, f"{src.prefix}.{key}", src.kind
    return None, None, None


def _align_protocols(
    hop_count: Optional[int],
    hop_legs: Optional[List[Any]],
    route_protocols: Optional[List[Any]],
    route_hops: Optional[List[Any]],
    *,
    leg_source: str,
    route_source: str,
    hop_source: str,
) -> Tuple[List[Optional[str]], List[str], List[str], List[str]]:
    """Return per-hop protocols, evidence lines, unresolved names, conflicts.

    A blank protocol is missing. Disagreement between two explicit fields on
    the same hop is a conflict: that hop contributes no protocol.
    """
    n = hop_count if hop_count is not None else 0
    protocols: List[Optional[str]] = [None] * n
    evidence: List[str] = []
    unresolved: List[str] = []
    conflicts: List[str] = []
    for i in range(n):
        candidates: List[Tuple[str, str]] = []
        if hop_legs is not None and i < len(hop_legs) and isinstance(hop_legs[i], dict):
            parsed = _protocol(hop_legs[i].get("dex_protocol"))
            if "dex_protocol" in hop_legs[i] and parsed:
                candidates.append((parsed, f"{leg_source}[{i}].dex_protocol"))
        if route_protocols is not None and i < len(route_protocols):
            parsed = _protocol(route_protocols[i])
            if parsed:
                candidates.append((parsed, f"{route_source}[{i}]"))
        if route_hops is not None and i < len(route_hops) and isinstance(route_hops[i], dict):
            parsed = _protocol(route_hops[i].get("dex"))
            if "dex" in route_hops[i] and parsed:
                candidates.append((parsed, f"{hop_source}[{i}].dex"))
        distinct = {p for p, _src in candidates}
        if len(distinct) > 1:
            conflicts.append(
                f"legs[{i}].protocol conflict: "
                + ", ".join(f"{p}@{src}" for p, src in candidates)
            )
            unresolved.append(f"legs[{i}].protocol")
            continue
        if len(distinct) == 1:
            protocols[i] = candidates[0][0]
            evidence.append(
                f"leg[{i}].protocol={candidates[0][0]} from {candidates[0][1]}"
            )
        else:
            unresolved.append(f"legs[{i}].protocol")
    return protocols, evidence, unresolved, conflicts


def _path_symbols(
    path: Optional[List[Any]], source: Optional[str],
) -> Tuple[Optional[List[str]], List[str], List[str]]:
    evidence: List[str] = []
    unresolved: List[str] = []
    if path is None:
        unresolved.append("route.cycle_token_path")
        return None, evidence, unresolved
    symbols: List[str] = []
    for i, raw in enumerate(path):
        sym = _symbol(raw)
        if sym is None:
            unresolved.append(f"route.cycle_token_path[{i}]")
            return None, evidence, unresolved
        symbols.append(sym)
    if source:
        evidence.append(
            f"cycle_token_path={'→'.join(symbols)} from {source}"
        )
    return symbols, evidence, unresolved


def _consistent_hop_count(
    counts: List[Tuple[str, int]],
) -> Tuple[Optional[int], List[str], List[str]]:
    evidence: List[str] = []
    unresolved: List[str] = []
    if not counts:
        unresolved.append("route.hop_count")
        return None, evidence, unresolved
    values = {v for _s, v in counts}
    described = ", ".join(f"{src}={val}" for src, val in counts)
    if len(values) != 1:
        unresolved.append("route.hop_count")
        evidence.append(f"hop_count conflict: {described}")
        return None, evidence, unresolved
    hop_count = counts[0][1]
    evidence.append(f"hop_count={hop_count} consistent ({described})")
    return hop_count, evidence, unresolved


def _field_from_index(
    items: Optional[List[Any]],
    index: int,
    *,
    source: Optional[str],
    kind: str,
    timestamp: Optional[str],
    normalizer,
) -> Dict[str, Any]:
    if items is None or index >= len(items) or source is None:
        return unavailable()
    raw = items[index]
    value = normalizer(raw) if normalizer is not None else raw
    if value is None:
        return unavailable(note=f"{source}[{index}] present but empty")
    return observed(
        value=value,
        status=STATUS_AVAILABLE,
        source=f"{source}[{index}]",
        provenance_kind=kind,
        timestamp=timestamp,
    )


def _quote_field(
    leg: Optional[Dict[str, Any]],
    key: str,
    *,
    source_prefix: Optional[str],
    timestamp: Optional[str],
    numeric: bool = False,
) -> Dict[str, Any]:
    if leg is None or source_prefix is None or key not in leg:
        return unavailable()
    raw = leg.get(key)
    if numeric:
        if not is_number(raw):
            return unavailable(note=f"{source_prefix}.{key} is not a finite number")
        value: Any = raw
    else:
        if raw is None:
            return unavailable()
        value = raw
    return observed(
        value=value,
        status=STATUS_AVAILABLE,
        source=f"{source_prefix}.{key}",
        provenance_kind=KIND_QUOTE,
        timestamp=timestamp,
    )


def build_route_view(
    bundle: Optional[Dict[str, Any]],
    candidate: Optional[Dict[str, Any]],
    *,
    timestamp: Optional[str],
) -> Dict[str, Any]:
    """Normalize per-leg evidence from a bundle and, for gaps only, a candidate.

    Bundle fields win. A candidate value is used only when the bundle does not
    carry that list. Disagreement between two present counts is a conflict.
    """
    bundle = bundle if isinstance(bundle, dict) else None
    candidate = candidate if isinstance(candidate, dict) else None
    hint = as_dict((candidate or {}).get("hint_metric")) or {}
    route = as_dict((bundle or {}).get("route")) or {}
    quotes = as_dict((bundle or {}).get("quotes")) or {}

    sources_route = []
    if route:
        sources_route.append(_Source(route, "verifier_bundle.route", KIND_LEG))
    if hint:
        sources_route.append(_Source(hint, "discovery_candidate.hint_metric", KIND_LEG))

    evidence: List[str] = []
    unresolved: List[str] = []
    conflicts: List[str] = []

    path, path_source, _kind = _first_list(sources_route, "cycle_token_path")
    symbols, path_ev, path_un = _path_symbols(path, path_source)
    evidence.extend(path_ev)
    unresolved.extend(path_un)

    pools, pool_source, _pk = _first_list(sources_route, "route_pools")
    addresses = None
    address_source = None
    if isinstance(route.get("route_pool_addresses"), list):
        addresses = list(route.get("route_pool_addresses") or [])
        address_source = "verifier_bundle.route.route_pool_addresses"

    protocols_list, protocol_source, _prk = _first_list(
        sources_route, "route_dex_protocols")
    route_hops, hop_source, _hk = _first_list(sources_route, "route_hops")

    hop_legs = None
    leg_source = None
    if isinstance(quotes.get("hop_legs"), list):
        hop_legs = list(quotes.get("hop_legs") or [])
        leg_source = "verifier_bundle.quotes.hop_legs"

    counts: List[Tuple[str, int]] = []
    for src in sources_route:
        if "hop_count" in src.payload:
            parsed = _hop_int(src.payload.get("hop_count"))
            if parsed is None:
                unresolved.append(f"{src.prefix}.hop_count")
                conflicts.append(f"{src.prefix}.hop_count is not a non-negative integer")
            else:
                counts.append((f"{src.prefix}.hop_count", parsed))
    if symbols is not None:
        counts.append((f"{path_source}.len-1", max(0, len(symbols) - 1)))
    if pools:
        counts.append((f"{pool_source}.len", len(pools)))
    if hop_legs:
        counts.append((f"{leg_source}.len", len(hop_legs)))
    if protocols_list:
        counts.append((f"{protocol_source}.len", len(protocols_list)))
    if route_hops:
        counts.append((f"{hop_source}.len", len(route_hops)))

    # Bundle and candidate hop_count both present is already two entries.
    hop_count, hop_ev, hop_un = _consistent_hop_count(counts)
    evidence.extend(hop_ev)
    if hop_count is None:
        unresolved.extend(hop_un)
        if any("conflict" in line for line in hop_ev):
            conflicts.append("hop_count sources disagree")

    chain_value = None
    chain_source = None
    chain_kind = KIND_UNAVAILABLE
    if bundle and _text(bundle.get("chain")):
        chain_value = _text(bundle.get("chain")).lower()
        chain_source = "verifier_bundle.chain"
        chain_kind = "verifier_bundle"
    elif hint and _text(hint.get("chain")):
        chain_value = _text(hint.get("chain")).lower()
        chain_source = "discovery_candidate.hint_metric.chain"
        chain_kind = KIND_LEG
    elif candidate and _text(candidate.get("chain")):
        chain_value = _text(candidate.get("chain")).lower()
        chain_source = "discovery_candidate.chain"
        chain_kind = KIND_LEG

    protocols, prot_ev, prot_un, prot_conflicts = _align_protocols(
        hop_count,
        hop_legs,
        protocols_list,
        route_hops,
        leg_source=leg_source or "verifier_bundle.quotes.hop_legs",
        route_source=protocol_source or "route.route_dex_protocols",
        hop_source=hop_source or "route_hops",
    )
    evidence.extend(prot_ev)
    unresolved.extend(prot_un)
    conflicts.extend(prot_conflicts)

    legs: List[Dict[str, Any]] = []
    n = hop_count or 0
    optional_gaps = False
    for i in range(n):
        leg = hop_legs[i] if hop_legs and i < len(hop_legs) and isinstance(hop_legs[i], dict) else None
        symbol_in = symbols[i] if symbols is not None and i < len(symbols) else None
        symbol_out = symbols[i + 1] if symbols is not None and i + 1 < len(symbols) else None

        token_in = unavailable()
        token_out = unavailable()
        if leg is not None and leg_source and _text(leg.get("token_in")):
            token_in = observed(
                value=_text(leg.get("token_in")),
                status=STATUS_AVAILABLE,
                source=f"{leg_source}[{i}].token_in",
                provenance_kind=KIND_QUOTE,
                timestamp=timestamp,
            )
        elif symbol_in and path_source:
            token_in = observed(
                value=symbol_in,
                status=STATUS_AVAILABLE,
                source=f"{path_source}[{i}]",
                provenance_kind=KIND_LEG,
                timestamp=timestamp,
                note="route symbol; quote token_in was not stored on this leg",
            )
        if leg is not None and leg_source and _text(leg.get("token_out")):
            token_out = observed(
                value=_text(leg.get("token_out")),
                status=STATUS_AVAILABLE,
                source=f"{leg_source}[{i}].token_out",
                provenance_kind=KIND_QUOTE,
                timestamp=timestamp,
            )
        elif symbol_out and path_source:
            token_out = observed(
                value=symbol_out,
                status=STATUS_AVAILABLE,
                source=f"{path_source}[{i + 1}]",
                provenance_kind=KIND_LEG,
                timestamp=timestamp,
                note="route symbol; quote token_out was not stored on this leg",
            )
        if (
            leg is not None
            and symbol_in
            and _text(leg.get("token_in"))
            and not _is_address(_text(leg.get("token_in")))
            and _symbol(leg.get("token_in")) != symbol_in
        ):
            conflicts.append(f"legs[{i}].token_in disagrees with cycle_token_path")
            unresolved.append(f"legs[{i}].token_in")

        pool_field = _field_from_index(
            pools, i, source=pool_source, kind=KIND_LEG,
            timestamp=timestamp, normalizer=_text,
        )
        address_field = _field_from_index(
            addresses, i, source=address_source, kind=KIND_LEG,
            timestamp=timestamp, normalizer=_text,
        )
        if address_field["status"] != STATUS_AVAILABLE:
            optional_gaps = True
        venue_field = unavailable()
        if leg is not None and leg_source and _text(leg.get("venue_id")):
            venue_field = observed(
                value=_text(leg.get("venue_id")),
                status=STATUS_AVAILABLE,
                source=f"{leg_source}[{i}].venue_id",
                provenance_kind=KIND_QUOTE,
                timestamp=timestamp,
                note="venue id is not a protocol",
            )
        protocol_field = unavailable()
        if i < len(protocols) and protocols[i]:
            protocol_field = observed(
                value=protocols[i],
                status=STATUS_AVAILABLE,
                source=f"legs[{i}].protocol",
                provenance_kind=KIND_LEG,
                timestamp=timestamp,
            )
        chain_field = unavailable()
        if chain_value and chain_source:
            chain_field = observed(
                value=chain_value,
                status=STATUS_AVAILABLE,
                source=chain_source,
                provenance_kind=chain_kind,
                timestamp=timestamp,
            )
        quote_amounts_missing = (
            leg is None
            or "amount_in_wei" not in leg
            or "amount_out_wei" not in leg
        )
        if quote_amounts_missing:
            optional_gaps = True
        legs.append({
            "hop_index": i,
            "token_in": token_in,
            "token_out": token_out,
            "pool": pool_field,
            "pool_address": address_field,
            "venue": venue_field,
            "protocol": protocol_field,
            "chain": chain_field,
            "quote": {
                "fee_bps": _quote_field(
                    leg, "fee_bps", source_prefix=(f"{leg_source}[{i}]" if leg_source else None),
                    timestamp=timestamp, numeric=True,
                ),
                "source_id": _quote_field(
                    leg, "source_id",
                    source_prefix=(f"{leg_source}[{i}]" if leg_source else None),
                    timestamp=timestamp,
                ),
                "amount_in_wei": _quote_field(
                    leg, "amount_in_wei",
                    source_prefix=(f"{leg_source}[{i}]" if leg_source else None),
                    timestamp=timestamp, numeric=True,
                ),
                "amount_out_wei": _quote_field(
                    leg, "amount_out_wei",
                    source_prefix=(f"{leg_source}[{i}]" if leg_source else None),
                    timestamp=timestamp, numeric=True,
                ),
                "block_number": _quote_field(
                    leg, "block_number",
                    source_prefix=(f"{leg_source}[{i}]" if leg_source else None),
                    timestamp=timestamp, numeric=True,
                ),
                "quote_status": _quote_field(
                    leg, "status",
                    source_prefix=(f"{leg_source}[{i}]" if leg_source else None),
                    timestamp=timestamp,
                ),
                "depth_usd": _quote_field(
                    leg, "depth_usd",
                    source_prefix=(f"{leg_source}[{i}]" if leg_source else None),
                    timestamp=timestamp, numeric=True,
                ),
                "path_symbol_in": (
                    observed(
                        value=symbol_in, status=STATUS_AVAILABLE,
                        source=f"{path_source}[{i}]", provenance_kind=KIND_LEG,
                        timestamp=timestamp,
                    ) if symbol_in and path_source else unavailable()
                ),
                "path_symbol_out": (
                    observed(
                        value=symbol_out, status=STATUS_AVAILABLE,
                        source=f"{path_source}[{i + 1}]", provenance_kind=KIND_LEG,
                        timestamp=timestamp,
                    ) if symbol_out and path_source else unavailable()
                ),
            },
        })

    pool_ids: List[Optional[str]] = []
    pools_complete = bool(pools) and hop_count is not None and len(pools) == hop_count
    if pools_complete:
        for i in range(hop_count or 0):
            pool_ids.append(_text(pools[i]) if i < len(pools) else None)
        if any(p is None for p in pool_ids):
            pools_complete = False
            unresolved.append("route.route_pools")
    elif hop_count:
        unresolved.append("route.route_pools")

    distinct_pools = len({p for p in pool_ids if p}) if pools_complete else 0
    if pools_complete and distinct_pools >= 2:
        evidence.append(
            f"distinct_pools={distinct_pools} from {pool_source}"
        )
    elif pools_complete:
        evidence.append(f"pools_not_distinct count={distinct_pools} from {pool_source}")

    if addresses is not None and hop_count is not None and len(addresses) == hop_count:
        addr_norm = []
        for raw in addresses:
            text = _text(raw)
            addr_norm.append(text.lower() if text else None)
        if pools_complete and all(addr_norm) and distinct_pools == 1 and len(set(addr_norm)) > 1:
            conflicts.append(
                "route_pool_addresses differ but route_pools identify one pool"
            )
            unresolved.append("route.route_pool_addresses")

    protocols_complete = (
        hop_count is not None
        and hop_count > 0
        and len(protocols) == hop_count
        and all(protocols)
        and not prot_conflicts
    )
    distinct_protocols = sorted({p for p in protocols if p}) if protocols_complete else []
    if protocols_complete:
        evidence.append(
            "per_leg_protocols=[" + ", ".join(distinct_protocols) + "] "
            f"count={len(protocols)} distinct={len(distinct_protocols)}"
        )

    closed = bool(symbols) and len(symbols) >= 2 and symbols[0] == symbols[-1]
    n_unique = len(set(symbols)) if symbols else 0
    if symbols is not None:
        evidence.append(
            f"path_closed={closed} distinct_tokens={n_unique}"
        )

    provider = None
    if bundle and _text(bundle.get("flash_loan_provider")):
        provider = _text(bundle.get("flash_loan_provider")).lower()
        evidence.append(
            f"flash_loan_provider={provider} is not a route protocol"
        )
    elif hint and _text(hint.get("provider")):
        provider = _text(hint.get("provider")).lower()
        evidence.append(
            f"flash_loan_provider={provider} from candidate hint is not a route protocol"
        )

    has_route_evidence = any((
        symbols, pools, hop_legs, protocols_list, route_hops,
        hop_count is not None,
    ))

    return {
        "legs": legs,
        "hop_count": hop_count,
        "symbols": symbols,
        "closed": closed,
        "n_unique": n_unique,
        "protocols_complete": protocols_complete,
        "distinct_protocols": distinct_protocols,
        "pools_complete": pools_complete,
        "distinct_pools": distinct_pools,
        "conflicts": conflicts,
        "unresolved": unresolved,
        "evidence": evidence,
        "optional_gaps": optional_gaps,
        "has_route_evidence": has_route_evidence,
        "provider": provider,
        "chain": chain_value,
    }


def _predicates(view: Dict[str, Any]) -> Dict[str, bool]:
    hops = view["hop_count"]
    symbols = view["symbols"] or []
    closed = bool(view["closed"])
    n_unique = int(view["n_unique"])
    cross = bool(view["protocols_complete"] and len(view["distinct_protocols"]) >= 2)
    same = bool(view["protocols_complete"] and len(view["distinct_protocols"]) == 1)
    pools_cross = bool(view["pools_complete"] and view["distinct_pools"] >= 2)
    triangular = bool(closed and n_unique == 3 and hops is not None and hops >= 3)
    lst = any(sym in LST_LRT_SYMBOLS for sym in symbols)
    all_stable = bool(symbols) and all(sym in STABLE_SYMBOLS for sym in symbols)
    return {
        "closed": closed,
        "cross_protocol": cross,
        "same_protocol": same,
        "cross_pool": pools_cross,
        "triangular": triangular,
        "lst": lst,
        "all_stable": all_stable,
        "DEX_TO_DEX": bool(
            cross and hops == 2 and closed and n_unique == 2 and pools_cross
        ),
        "TRIANGULAR": triangular and not cross,
        "MULTI_HOP": bool(hops is not None and hops >= 4 and not triangular),
        "MULTI_DEX": bool(
            cross and hops is not None and hops >= 3 and not triangular
        ),
        "CROSS_POOL": pools_cross,
        "CROSS_PROTOCOL": cross,
        "STABLECOIN_CROSS_PROTOCOL": bool(all_stable and cross and not lst),
        "LST_LRT_CROSS_PROTOCOL": bool(lst and cross),
        "COMPLEX_TRIANGULAR_CROSS_PROTOCOL": bool(
            triangular and cross and hops is not None and hops > 3
        ),
    }


def _choose_primary(view: Dict[str, Any], pred: Dict[str, bool]) -> Optional[str]:
    """Return a family only when per-leg protocol evidence is complete.

    Without a protocol on every hop the route cannot be told apart from a
    cross-protocol variant, so no family is assigned.
    """
    hops = view["hop_count"]
    if not view["protocols_complete"]:
        return None
    if pred["LST_LRT_CROSS_PROTOCOL"]:
        return "LST_LRT_CROSS_PROTOCOL"
    if pred["STABLECOIN_CROSS_PROTOCOL"]:
        return "STABLECOIN_CROSS_PROTOCOL"
    if pred["COMPLEX_TRIANGULAR_CROSS_PROTOCOL"]:
        return "COMPLEX_TRIANGULAR_CROSS_PROTOCOL"
    if pred["triangular"] and pred["cross_protocol"] and hops == 3:
        return "CROSS_PROTOCOL"
    if pred["triangular"] and not pred["cross_protocol"]:
        return "TRIANGULAR"
    if pred["MULTI_DEX"]:
        return "MULTI_DEX"
    if pred["MULTI_HOP"]:
        return "MULTI_HOP"
    if pred["DEX_TO_DEX"]:
        return "DEX_TO_DEX"
    if (
        hops == 2
        and pred["same_protocol"]
        and pred["cross_pool"]
        and pred["closed"]
        and view["n_unique"] == 2
    ):
        return "CROSS_POOL"
    if pred["cross_protocol"]:
        return "CROSS_PROTOCOL"
    return None


def classify_route(view: Dict[str, Any]) -> Dict[str, Any]:
    """Assign primary family, secondary tags, state, and the evidence why."""
    pred = _predicates(view)
    evidence = list(view["evidence"])
    unresolved = list(dict.fromkeys(view["unresolved"]))
    conflicts = list(view["conflicts"])

    if pred["lst"] and not pred["cross_protocol"]:
        evidence.append(
            "LST/LRT symbol present on the stored path; "
            "LST_LRT_CROSS_PROTOCOL not assigned because cross-protocol "
            "is not proven from per-leg protocol fields"
        )
    if pred["all_stable"] and not pred["cross_protocol"]:
        evidence.append(
            "every stored path symbol is a stablecoin; "
            "STABLECOIN_CROSS_PROTOCOL not assigned because cross-protocol "
            "is not proven from per-leg protocol fields"
        )
    if pred["cross_protocol"]:
        evidence.append(
            "cross_protocol proven: every hop has an explicit protocol and "
            f"at least two distinct values {view['distinct_protocols']}"
        )
    elif view["hop_count"]:
        evidence.append(
            "cross_protocol not proven: per-leg protocol evidence is incomplete "
            "or not distinct. venue ids, pool ids, and pool addresses were not "
            "parsed as protocols"
        )

    blocked = bool(conflicts) or view["hop_count"] is None or not view["closed"]
    primary: str
    state: str
    if not view["has_route_evidence"]:
        primary = PRIMARY_UNKNOWN
        state = STATE_UNKNOWN
        evidence.append("no stored route evidence; primary_family=UNKNOWN")
    elif blocked or _choose_primary(view, pred) is None:
        primary = PRIMARY_UNCLASSIFIED
        state = STATE_INCOMPLETE
        if conflicts:
            evidence.append(
                "classification_state=INCOMPLETE because stored route fields conflict: "
                + "; ".join(conflicts)
            )
        elif not view["closed"]:
            evidence.append(
                "classification_state=INCOMPLETE because the stored token path "
                "is not a closed cycle"
            )
        elif view["hop_count"] is None:
            evidence.append(
                "classification_state=INCOMPLETE because hop_count is missing "
                "or inconsistent"
            )
        else:
            why = (
                "per-leg protocol evidence is incomplete"
                if not view["protocols_complete"]
                else "stored evidence does not satisfy a strategy-family rule"
            )
            evidence.append(
                f"classification_state=INCOMPLETE because {why}. No family was forced"
            )
        unresolved.extend(conflicts)
    else:
        primary = _choose_primary(view, pred) or PRIMARY_UNCLASSIFIED
        state = STATE_COMPLETE
        evidence.append(
            f"primary_family={primary} under classifier {CLASSIFIER_VERSION}. "
            + _primary_reason(primary, view, pred)
        )
        if (
            pred["triangular"]
            and not pred["cross_protocol"]
            and view["hop_count"] is not None
            and view["hop_count"] > 3
        ):
            evidence.append(
                "hop_count>3 with a closed 3-token path stays TRIANGULAR; "
                "MULTI_HOP is not assigned to that shape"
            )

    if state != STATE_COMPLETE:
        secondary: List[str] = []
    else:
        secondary = [name for name in FAMILIES if pred.get(name) and name != primary]
        # TRIANGULAR predicate above is "triangular and not cross". Surface the
        # shape tag when the path is triangular and another family won.
        if pred["triangular"] and "TRIANGULAR" not in secondary and primary != "TRIANGULAR":
            secondary.append("TRIANGULAR")
            secondary = [name for name in FAMILIES if name in set(secondary)]
        evidence.append(
            "secondary_tags=" + (", ".join(secondary) if secondary else "(none)")
        )

    if state == STATE_UNKNOWN:
        confidence = CONF_NONE
        completeness = STRATEGY_UNKNOWN
    elif state == STATE_INCOMPLETE:
        confidence = CONF_LOW
        completeness = STRATEGY_PARTIAL
    elif view["optional_gaps"]:
        confidence = CONF_MEDIUM
        completeness = STRATEGY_FULL
    else:
        confidence = CONF_HIGH
        completeness = STRATEGY_FULL

    # Required discriminators that are still missing keep the state incomplete
    # only when we refused a family. A completed family may still lack optional
    # quote amounts; those stay out of unresolved_fields.
    return {
        "primary_family": primary,
        "secondary_tags": secondary,
        "classification_state": state,
        "confidence": confidence,
        "strategy_completeness": completeness,
        "evidence": evidence,
        "unresolved_fields": list(dict.fromkeys(unresolved)),
        "classifier_version": CLASSIFIER_VERSION,
        "conflicts": conflicts,
    }


def _primary_reason(primary: str, view: Dict[str, Any], pred: Dict[str, bool]) -> str:
    hops = view["hop_count"]
    protocols = view["distinct_protocols"]
    reasons = {
        "LST_LRT_CROSS_PROTOCOL": (
            "a stored path symbol is in the LST/LRT set and every hop has an "
            f"explicit protocol with distinct values {protocols}"
        ),
        "STABLECOIN_CROSS_PROTOCOL": (
            "every stored path symbol is in the stablecoin set and every hop "
            f"has an explicit protocol with distinct values {protocols}"
        ),
        "COMPLEX_TRIANGULAR_CROSS_PROTOCOL": (
            f"closed 3-token path, hop_count={hops}>3, and distinct per-leg "
            f"protocols {protocols}"
        ),
        "CROSS_PROTOCOL": (
            "distinct per-leg protocols "
            f"{protocols} on hop_count={hops}; a more specific stable, LST, "
            "complex-triangular, multi-dex, or 2-hop DEX-to-DEX rule did not take priority"
        ),
        "TRIANGULAR": (
            f"closed path with exactly 3 distinct tokens and hop_count={hops}; "
            "cross-protocol is not proven, so the path stays triangular "
            "(hop_count>3 remains triangular, with MULTI_HOP only as a tag "
            "when that predicate is also true)"
        ),
        "MULTI_DEX": (
            f"hop_count={hops}>=3, path is not a 3-token cycle, distinct "
            f"per-leg protocols {protocols}"
        ),
        "MULTI_HOP": (
            f"hop_count={hops}>=4 and the path is not a 3-token cycle; "
            "per-leg protocols are not distinct"
        ),
        "DEX_TO_DEX": (
            "hop_count=2, closed 2-token path, distinct pools, and distinct "
            f"per-leg protocols {protocols}. CROSS_PROTOCOL is a tag on this "
            "shape, not the primary"
        ),
        "CROSS_POOL": (
            "hop_count=2, closed 2-token path, one explicit protocol on every "
            f"hop ({protocols}), and at least two distinct pool ids. Different "
            "venues were not treated as different protocols"
        ),
    }
    return reasons.get(primary, "family rule matched stored evidence")
