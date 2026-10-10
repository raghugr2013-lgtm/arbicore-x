"""Read model over stored Opportunity Ledger documents.

Operates only on ledger rows. It does not open discovery candidates,
verifier bundles, or the economics assessor.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

_SECRET = re.compile(
    r"(://|mongodb(\+srv)?://|BEGIN [A-Z ]*PRIVATE KEY|"
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.)",
    re.IGNORECASE,
)

SORTS = ("net", "timestamp", "chain", "family")


def sanitize(value: Any) -> Any:
    """Drop secret-bearing strings. Numbers, including zero, stay numbers."""
    if isinstance(value, str):
        if _SECRET.search(value):
            return None
        return value
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    return None


def _evidence(row: Dict[str, Any]) -> Dict[str, Any]:
    evidence = row.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def _strategy(row: Dict[str, Any]) -> Dict[str, Any]:
    strategy = _evidence(row).get("strategy")
    return strategy if isinstance(strategy, dict) else {}


def _provenance(row: Dict[str, Any]) -> Dict[str, Any]:
    provenance = _evidence(row).get("provenance")
    return provenance if isinstance(provenance, dict) else {}


def _gates(row: Dict[str, Any]) -> Dict[str, Any]:
    gates = _evidence(row).get("gates")
    return gates if isinstance(gates, dict) else {}


def _economics(row: Dict[str, Any]) -> Dict[str, Any]:
    economics = _evidence(row).get("economics")
    return economics if isinstance(economics, dict) else {}


def _timestamps(row: Dict[str, Any]) -> Dict[str, Any]:
    stamps = _provenance(row).get("timestamps")
    return stamps if isinstance(stamps, dict) else {}


def decision_net(row: Dict[str, Any]) -> Optional[float]:
    value = _gates(row).get("decision_net_usd")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def verified_at(row: Dict[str, Any]) -> Optional[float]:
    value = _timestamps(row).get("verified_at")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def timestamp_iso(value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def chain_of(row: Dict[str, Any]) -> Optional[str]:
    value = _provenance(row).get("chain")
    return value if isinstance(value, str) else None


def family_of(row: Dict[str, Any]) -> Optional[str]:
    value = _strategy(row).get("primary_family")
    return value if isinstance(value, str) else None


def provider_of(row: Dict[str, Any]) -> Optional[str]:
    value = _provenance(row).get("flash_loan_provider")
    return value if isinstance(value, str) else None


def gate_status(row: Dict[str, Any], name: str) -> Optional[str]:
    gate = _gates(row).get(name)
    if not isinstance(gate, dict):
        return None
    status = gate.get("status")
    return status if isinstance(status, str) else None


def gate_reason(row: Dict[str, Any], name: str) -> Optional[str]:
    gate = _gates(row).get(name)
    if not isinstance(gate, dict):
        return None
    reason = gate.get("reason")
    return reason if isinstance(reason, str) else None


def bundle_status(row: Dict[str, Any]) -> str:
    bundle_id = row.get("verifier_bundle_id")
    if isinstance(bundle_id, str) and bundle_id.strip():
        return "verifier_bundle"
    return "decision_only"


def _count(values: Iterable[Optional[str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        key = value if isinstance(value, str) and value else "unavailable"
        counts[key] = counts.get(key, 0) + 1
    return counts


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate one run from ledger rows already loaded."""
    nets = [decision_net(row) for row in rows]
    numeric = [value for value in nets if value is not None]
    best_row = None
    worst_row = None
    for row in rows:
        net = decision_net(row)
        if net is None:
            continue
        if best_row is None or net > decision_net(best_row):
            best_row = row
        if worst_row is None or net < decision_net(worst_row):
            worst_row = row
    verified = [verified_at(row) for row in rows]
    verified_nums = [value for value in verified if value is not None]
    total = len(rows)
    backed = sum(1 for row in rows if bundle_status(row) == "verifier_bundle")
    mean = (sum(numeric) / len(numeric)) if numeric else None

    def _extreme(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        return {
            "opportunity_id": row.get("opportunity_id"),
            "ledger_id": row.get("ledger_id"),
            "decision_net_usd": decision_net(row),
            "chain": chain_of(row),
            "strategy_family": family_of(row),
        }

    run_ids = {row.get("run_id") for row in rows}
    run_id = next(iter(run_ids)) if len(run_ids) == 1 else None
    return sanitize({
        "run_id": run_id,
        "period": {
            "first_verified_at": min(verified_nums) if verified_nums else None,
            "last_verified_at": max(verified_nums) if verified_nums else None,
            "first_verified_at_iso": timestamp_iso(min(verified_nums)) if verified_nums else None,
            "last_verified_at_iso": timestamp_iso(max(verified_nums)) if verified_nums else None,
            "source": "ledger verified_at span",
        },
        "total": total,
        "verifier_backed": backed,
        "decision_only": total - backed,
        "strategy_distribution": _count(family_of(row) for row in rows),
        "chain_distribution": _count(chain_of(row) for row in rows),
        "provider_distribution": _count(provider_of(row) for row in rows),
        "gate_7_status": _count(gate_status(row, "gate_7") for row in rows),
        "net": {
            "count": len(numeric),
            "mean": mean,
            "best": max(numeric) if numeric else None,
            "worst": min(numeric) if numeric else None,
            "ge_0": sum(1 for value in numeric if value >= 0),
            "ge_25": sum(1 for value in numeric if value >= 25),
        },
        "best_opportunity": _extreme(best_row),
        "worst_opportunity": _extreme(worst_row),
    })


def slim_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """List payload. Route legs and the economics block are omitted."""
    verified = verified_at(row)
    return sanitize({
        "ledger_id": row.get("ledger_id"),
        "opportunity_id": row.get("opportunity_id"),
        "run_id": row.get("run_id"),
        "timestamp": timestamp_iso(verified),
        "verified_at": verified,
        "chain": chain_of(row),
        "strategy_family": family_of(row),
        "provider": provider_of(row),
        "bundle_status": bundle_status(row),
        "decision_net_usd": decision_net(row),
        "gate_7": gate_status(row, "gate_7"),
        "final_status": _gates(row).get("final_observed_status"),
    })


def _parse_bound(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        raise ValueError("timestamp bound must be a unix time or ISO-8601 string")


def apply_filters(
    rows: List[Dict[str, Any]],
    *,
    run_id: Optional[str] = None,
    chain: Optional[str] = None,
    family: Optional[str] = None,
    provider: Optional[str] = None,
    bundle: Optional[str] = None,
    gate_7: Optional[str] = None,
    net_min: Optional[float] = None,
    net_max: Optional[float] = None,
    ts_from: Optional[str] = None,
    ts_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start = _parse_bound(ts_from)
    end = _parse_bound(ts_to)
    kept: List[Dict[str, Any]] = []
    for row in rows:
        if run_id and row.get("run_id") != run_id:
            continue
        if chain and chain_of(row) != chain:
            continue
        if family and family_of(row) != family:
            continue
        if provider and provider_of(row) != provider:
            continue
        status = bundle_status(row)
        if bundle == "backed" and status != "verifier_bundle":
            continue
        if bundle == "decision_only" and status != "decision_only":
            continue
        stored_gate = gate_status(row, "gate_7")
        if gate_7 == "unavailable" and stored_gate is not None:
            continue
        if gate_7 and gate_7 != "unavailable" and stored_gate != gate_7:
            continue
        net = decision_net(row)
        if net_min is not None and (net is None or net < net_min):
            continue
        if net_max is not None and (net is None or net > net_max):
            continue
        stamp = verified_at(row)
        if start is not None and (stamp is None or stamp < start):
            continue
        if end is not None and (stamp is None or stamp > end):
            continue
        kept.append(row)
    return kept


def sort_rows(rows: List[Dict[str, Any]], sort: str, order: str) -> List[Dict[str, Any]]:
    if sort not in SORTS:
        raise ValueError("sort must be net, timestamp, chain, or family")
    if order not in ("asc", "desc"):
        raise ValueError("order must be asc or desc")
    descending = order == "desc"

    def key(row: Dict[str, Any]) -> Tuple[int, Any]:
        if sort == "net":
            net = decision_net(row)
            if net is None:
                return (1, 0)
            return (0, -net if descending else net)
        if sort == "timestamp":
            stamp = verified_at(row)
            if stamp is None:
                return (1, 0)
            return (0, -stamp if descending else stamp)
        text = chain_of(row) if sort == "chain" else family_of(row)
        if not text:
            return (1, "")
        folded = text.lower()
        return (0, _invert_text(folded) if descending else folded)

    return sorted(rows, key=key)


def _invert_text(text: str) -> str:
    return "".join(chr(0x10FFFF - ord(char)) for char in text)


def paginate(rows: List[Dict[str, Any]], page: int, page_size: int) -> Dict[str, Any]:
    page = 1 if page < 1 else page
    page_size = 1 if page_size < 1 else min(page_size, 100)
    start = (page - 1) * page_size
    window = rows[start:start + page_size]
    return {
        "items": [slim_row(row) for row in window],
        "page": page,
        "page_size": page_size,
        "total": len(rows),
    }


def detail(row: Dict[str, Any]) -> Dict[str, Any]:
    """Full ledger record for one opportunity. Nulls are preserved."""
    cleaned = sanitize({key: value for key, value in row.items() if key != "_id"})
    cleaned["display_timestamp"] = timestamp_iso(verified_at(row))
    return cleaned


def timeline_rows(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per stored timestamp. Missing stages are omitted."""
    stamps = _timestamps(row)
    stages = (
        ("hint_observed_at", "DISCOVERED"),
        ("verified_at", "VERIFIED"),
        ("bundle_created_at", "BUNDLE_RECORDED"),
    )
    out: List[Dict[str, Any]] = []
    for field, stage in stages:
        raw = stamps.get(field)
        iso = timestamp_iso(raw)
        if iso is None and not isinstance(raw, (int, float)):
            continue
        if isinstance(raw, bool):
            continue
        if raw is None:
            continue
        out.append({
            "opportunity_id": row.get("opportunity_id"),
            "ledger_id": row.get("ledger_id"),
            "run_id": row.get("run_id"),
            "stage": stage,
            "timestamp": iso,
        })
    return out


def run_index(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        run_id = row.get("run_id")
        if not isinstance(run_id, str):
            continue
        grouped.setdefault(run_id, []).append(row)
    listed = []
    for run_id, group in grouped.items():
        summary = summarize(group)
        listed.append({
            "run_id": run_id,
            "opportunities": summary["total"],
            "first_verified_at": summary["period"]["first_verified_at_iso"],
            "last_verified_at": summary["period"]["last_verified_at_iso"],
        })
    listed.sort(key=lambda item: item["last_verified_at"] or "", reverse=True)
    return listed
