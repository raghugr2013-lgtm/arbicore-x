"""Economics observability for an existing m2.3 evidence bundle.

Reads stored fields. Does not call ``aggregate_economics``, does not apply
Gate 7, and does not substitute zero for a missing field.

``AVAILABLE_NOT_PERSISTED`` is used only when the bundle shows the economics
assessor ran (an ``economics`` object was stored) and the named calculator
output is not one of the keys the verifier copies onto the bundle.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .fields import (
    KIND_BUNDLE,
    KIND_DECISION,
    KIND_ECON,
    KIND_FLASH,
    KIND_GAS,
    KIND_QUOTE,
    STATUS_AVAILABLE,
    STATUS_NOT_PERSISTED,
    STATUS_UNAVAILABLE,
    as_dict,
    is_number,
    lookup,
    not_persisted,
    observed,
    unavailable,
)

# Cent-rounded Gate-7 decision text written by FlashLoanOpportunityVerifier.
_DECISION_NET = re.compile(
    r"gate_7:atomic_profit\s+\$?(?P<amt>-?\d+(?:\.\d+)?)\s*<\s*floor\s+\$?(?P<floor>-?\d+(?:\.\d+)?)"
)
_REASON_FLOOR = re.compile(
    r"floor\s+\$?(?P<floor>-?\d+(?:\.\d+)?)"
)

# Calculator attributes that exist on EconomicAssessment / the assessor and
# are not copied by ``_build_evidence_bundle``. Names are schema facts, not
# recomputed values.
_NOT_PERSISTED = {
    "flash_loan_fee_pct": (
        "not_persisted:FlashLoanEconomicsAssessor.provider_fee_bps",
        "Applied flash-loan fee rate is computed inside the assessor. "
        "fees.flash_loan_fee_bps stores the quote override coerced with "
        "`or 0`, which is not a proven applied rate.",
    ),
    "mev_penalty": (
        "not_persisted:EconomicAssessment.mev_penalty_pct",
        "aggregate_economics computes mev_penalty_pct and the m2.3 bundle "
        "does not copy it. The stored mev label is not converted into a penalty.",
    ),
    "mev_adjusted_net_pct": (
        "not_persisted:EconomicAssessment.mev_adjusted_net_pct",
        "aggregate_economics computes mev_adjusted_net_pct and the m2.3 "
        "bundle does not copy it.",
    ),
    "true_net_pct": (
        "not_persisted:EconomicAssessment.mev_adjusted_net_pct",
        "True-net percent is the assessor's mev-adjusted net percent. "
        "The bundle stores the dollar atomic profit, not this percent.",
    ),
}

ECON_COMPLETE = "COMPLETE"
ECON_PARTIAL = "PARTIAL"
ECON_UNAVAILABLE = "UNAVAILABLE"

BUNDLE_COMPLETE = "COMPLETE_BUNDLE"
BUNDLE_PARTIAL = "PARTIAL_BUNDLE"
BUNDLE_NONE = "NO_BUNDLE"


def bundle_presence(bundle: Optional[Dict[str, Any]]) -> str:
    if not isinstance(bundle, dict) or not bundle:
        return BUNDLE_NONE
    markers = ("bundle_id", "route", "quotes", "economics", "gates", "schema_version")
    if not any(key in bundle for key in markers):
        return BUNDLE_NONE
    route = as_dict(bundle.get("route")) or {}
    quotes = as_dict(bundle.get("quotes")) or {}
    econ = as_dict(bundle.get("economics"))
    fees = as_dict(bundle.get("fees"))
    gas = as_dict(bundle.get("gas"))
    gates = as_dict(bundle.get("gates")) or {}
    hops = quotes.get("hop_legs")
    pools = route.get("route_pools")
    protocols = route.get("route_dex_protocols")
    path = route.get("cycle_token_path")
    complete = (
        bundle.get("schema_version") == "m2.3"
        and isinstance(path, list) and len(path) >= 2
        and isinstance(route.get("hop_count"), int)
        and isinstance(pools, list) and len(pools) == route.get("hop_count")
        and isinstance(protocols, list) and len(protocols) == len(pools)
        and isinstance(hops, list) and len(hops) == len(pools)
        and econ is not None and "atomic_profit_usd" in econ
        and fees is not None
        and gas is not None
        and isinstance(gates.get("gate_7"), dict)
    )
    return BUNDLE_COMPLETE if complete else BUNDLE_PARTIAL


def _candidate_timestamp(candidate: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(candidate, dict):
        return None
    for key in ("verified_at", "verified_at_ts"):
        raw = candidate.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if is_number(raw) and float(raw) > 0:
            return str(raw)
    return None


def _timestamp(
    bundle: Optional[Dict[str, Any]],
    candidate: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    if isinstance(bundle, dict):
        block = as_dict(bundle.get("block_context")) or {}
        verified = block.get("verified_at_ts")
        if is_number(verified) and float(verified) > 0:
            return str(verified)
        created = bundle.get("created_at")
        if isinstance(created, str) and created.strip():
            return created.strip()
    return _candidate_timestamp(candidate)


def _calculator_version(bundle: Optional[Dict[str, Any]]) -> Optional[str]:
    """Only a version string actually stored on the bundle. Never invented."""
    if not isinstance(bundle, dict):
        return None
    econ = as_dict(bundle.get("economics")) or {}
    for key in ("calculator_version", "economics_version"):
        found, value = lookup(econ, key)
        if found and isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _available_number(
    bundle: Dict[str, Any],
    path: str,
    *,
    kind: str,
    timestamp: Optional[str],
    calculator_version: Optional[str],
    note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    found, value = lookup(bundle, path)
    if not found or not is_number(value):
        return None
    return observed(
        value=value,
        status=STATUS_AVAILABLE,
        source=f"verifier_bundle.{path}",
        provenance_kind=kind,
        timestamp=timestamp,
        calculator_version=calculator_version,
        note=note,
    )


def _decision_texts(
    bundle: Optional[Dict[str, Any]],
    candidate: Optional[Dict[str, Any]],
) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    if isinstance(bundle, dict):
        tag = bundle.get("outcome_tag")
        if isinstance(tag, str) and tag.strip():
            found.append(("verifier_bundle.outcome_tag", tag.strip()))
    if isinstance(candidate, dict):
        for key in ("verified_outcome", "outcome"):
            raw = candidate.get(key)
            if isinstance(raw, str) and raw.strip():
                found.append((f"discovery_candidate.{key}", raw.strip()))
                break
    return found


def _parse_decision_net(
    bundle: Optional[Dict[str, Any]],
    candidate: Optional[Dict[str, Any]],
    timestamp: Optional[str],
) -> Dict[str, Any]:
    parsed: List[Tuple[str, float, float]] = []
    for source, text in _decision_texts(bundle, candidate):
        match = _DECISION_NET.search(text)
        if not match:
            continue
        parsed.append((source, float(match.group("amt")), float(match.group("floor"))))
    if not parsed:
        return unavailable(
            note="no persisted Gate-7 decision text with atomic_profit and floor"
        )
    amounts = {row[1] for row in parsed}
    if len(amounts) != 1:
        return unavailable(
            note="persisted decision nets disagree: "
            + ", ".join(f"{src}={amt}" for src, amt, _floor in parsed)
        )
    source, amt, floor = parsed[0]
    return observed(
        value=amt,
        status=STATUS_AVAILABLE,
        source=source,
        provenance_kind=KIND_DECISION,
        timestamp=timestamp,
        note=f"cent-rounded decision net parsed from stored text; floor_usd={floor}",
    )


def _gate7(
    bundle: Optional[Dict[str, Any]],
    timestamp: Optional[str],
) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        return unavailable()
    gates = as_dict(bundle.get("gates"))
    if gates is None or "gate_7" not in gates:
        return unavailable(note="gates.gate_7 is not on the bundle")
    gate = gates.get("gate_7")
    if not isinstance(gate, dict) or "status" not in gate:
        return unavailable(note="gates.gate_7 has no status")
    value: Dict[str, Any] = {
        "status": gate.get("status"),
        "reason": gate.get("reason"),
    }
    reason = gate.get("reason")
    if isinstance(reason, str):
        floor_match = _REASON_FLOOR.search(reason)
        if floor_match:
            value["floor_usd"] = float(floor_match.group("floor"))
    return observed(
        value=value,
        status=STATUS_AVAILABLE,
        source="verifier_bundle.gates.gate_7",
        provenance_kind=KIND_BUNDLE,
        timestamp=timestamp,
        note="Gate 7 status and reason as stored. The floor is read from the "
             "stored reason text when that text contains it.",
    )


def _assessor_ran(bundle: Optional[Dict[str, Any]]) -> bool:
    return isinstance(bundle, dict) and isinstance(bundle.get("economics"), dict)


def _not_persisted_or_absent(bundle: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
    if not _assessor_ran(bundle):
        return unavailable(
            note="economics block is absent, so this calculator output was not produced for the row"
        )
    source, note = _NOT_PERSISTED[key]
    return not_persisted(source=source, note=note)


def _gross_pct(
    bundle: Dict[str, Any],
    timestamp: Optional[str],
    calculator_version: Optional[str],
) -> Tuple[Dict[str, Any], List[str]]:
    unresolved: List[str] = []
    econ = _available_number(
        bundle, "economics.gross_spread_pct", kind=KIND_ECON,
        timestamp=timestamp, calculator_version=calculator_version,
    )
    quote = _available_number(
        bundle, "quotes.gross_profit_pct", kind=KIND_QUOTE,
        timestamp=timestamp, calculator_version=None,
    )
    if econ and quote:
        if abs(float(econ["value"]) - float(quote["value"])) > 1e-4:
            unresolved.append("gross_profit_pct")
            return unavailable(
                note="economics.gross_spread_pct and quotes.gross_profit_pct disagree"
            ), unresolved
        econ["note"] = "agrees with quotes.gross_profit_pct within 1e-4; value not recomputed"
        return econ, unresolved
    if econ:
        return econ, unresolved
    if quote:
        return quote, unresolved
    return unavailable(note="gross percent is not stored"), unresolved


def _true_net(
    bundle: Dict[str, Any],
    timestamp: Optional[str],
    calculator_version: Optional[str],
) -> Tuple[Dict[str, Any], List[str]]:
    unresolved: List[str] = []
    atomic = _available_number(
        bundle, "economics.atomic_profit_usd", kind=KIND_ECON,
        timestamp=timestamp, calculator_version=calculator_version,
        note="stored atomic profit; not recomputed",
    )
    expected = _available_number(
        bundle, "economics.expected_net_after_costs_usd", kind=KIND_ECON,
        timestamp=timestamp, calculator_version=calculator_version,
    )
    if atomic and expected and abs(float(atomic["value"]) - float(expected["value"])) > 1e-4:
        unresolved.append("true_net_usd")
        return unavailable(
            note="atomic_profit_usd and expected_net_after_costs_usd disagree; neither was recomputed"
        ), unresolved
    if atomic:
        return atomic, unresolved
    if expected:
        expected["note"] = "stored expected_net_after_costs_usd; atomic_profit_usd key absent"
        return expected, unresolved
    return unavailable(note="true net dollars are not stored"), unresolved


def observe_economics(
    bundle: Optional[Dict[str, Any]],
    candidate: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    timestamp = _timestamp(bundle, candidate)
    version = _calculator_version(bundle)
    presence = bundle_presence(bundle)
    unresolved: List[str] = []
    doc = bundle if isinstance(bundle, dict) else {}

    gross, gross_un = _gross_pct(doc, timestamp, version)
    unresolved.extend(gross_un)
    true_net, net_un = _true_net(doc, timestamp, version)
    unresolved.extend(net_un)

    quote_notional = _available_number(
        doc, "quotes.quote_notional_usd", kind=KIND_QUOTE,
        timestamp=timestamp, calculator_version=version,
    ) or unavailable(note="quotes.quote_notional_usd is not stored; borrow amount was not substituted")

    dex_fee_pct = _available_number(
        doc, "fees.total_swap_fee_pct", kind=KIND_ECON,
        timestamp=timestamp, calculator_version=version,
        note="stored swap-fee telemetry percent",
    ) or unavailable()

    flash_fee_usd = _available_number(
        doc, "fees.flash_loan_fee_usd", kind=KIND_FLASH,
        timestamp=timestamp, calculator_version=version,
        note="stored flash-loan fee dollars from the assessor",
    ) or unavailable()

    gas_units = _available_number(
        doc, "gas.tx_gas_units", kind=KIND_GAS,
        timestamp=timestamp, calculator_version=None,
        note="stored quote gas units",
    ) or unavailable()

    gas_cost = _available_number(
        doc, "gas.gas_cost_usd", kind=KIND_GAS,
        timestamp=timestamp, calculator_version=version,
        note="stored gas cost dollars",
    ) or unavailable()

    slippage_pct = _available_number(
        doc, "fees.total_slippage_pct", kind=KIND_ECON,
        timestamp=timestamp, calculator_version=version,
    ) or unavailable()

    atomic = _available_number(
        doc, "economics.atomic_profit_usd", kind=KIND_ECON,
        timestamp=timestamp, calculator_version=version,
        note="stored atomic profit; not recomputed",
    ) or unavailable()

    gross_usd = (
        _available_number(
            doc, "economics.gross_profit_usd", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or _available_number(
            doc, "quotes.gross_profit_usd", kind=KIND_QUOTE,
            timestamp=timestamp, calculator_version=None,
        )
        or unavailable(
            note="no m2.3 field and EconomicAssessment has no gross-profit dollar attribute"
        )
    )
    dex_fee_usd = (
        _available_number(
            doc, "fees.total_swap_fee_usd", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or _available_number(
            doc, "fees.dex_fee_usd", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or unavailable(
            note="no m2.3 field and the assessor does not emit a DEX-fee dollar attribute"
        )
    )
    slippage_usd = (
        _available_number(
            doc, "fees.total_slippage_usd", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or _available_number(
            doc, "fees.slippage_usd", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or unavailable(
            note="no m2.3 field and EconomicAssessment has no slippage dollar attribute"
        )
    )
    gas_price = (
        _available_number(
            doc, "gas.gas_price", kind=KIND_GAS,
            timestamp=timestamp, calculator_version=None,
        )
        or _available_number(
            doc, "gas.gas_price_wei", kind=KIND_GAS,
            timestamp=timestamp, calculator_version=None,
        )
        or unavailable(note="the gas model stores a USD estimate, not a gas price")
    )
    flash_fee_pct = (
        _available_number(
            doc, "fees.flash_loan_fee_pct", kind=KIND_FLASH,
            timestamp=timestamp, calculator_version=version,
        )
        or _available_number(
            doc, "economics.flash_loan_fee_pct", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or _not_persisted_or_absent(bundle, "flash_loan_fee_pct")
    )
    mev_penalty = (
        _available_number(
            doc, "economics.mev_penalty_pct", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or _available_number(
            doc, "mev.mev_penalty_pct", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or _not_persisted_or_absent(bundle, "mev_penalty")
    )
    mev_adj_pct = (
        _available_number(
            doc, "economics.mev_adjusted_net_pct", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or _not_persisted_or_absent(bundle, "mev_adjusted_net_pct")
    )
    true_net_pct = (
        _available_number(
            doc, "economics.true_net_pct", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
        )
        or _available_number(
            doc, "economics.mev_adjusted_net_pct", kind=KIND_ECON,
            timestamp=timestamp, calculator_version=version,
            note="stored mev_adjusted_net_pct read as true-net percent",
        )
        or _not_persisted_or_absent(bundle, "true_net_pct")
    )

    mev_adjusted_usd: Dict[str, Any]
    if atomic["status"] == STATUS_AVAILABLE and isinstance(bundle, dict) and bundle.get("schema_version") == "m2.3":
        mev_adjusted_usd = observed(
            value=atomic["value"],
            status=STATUS_AVAILABLE,
            source="verifier_bundle.economics.atomic_profit_usd",
            provenance_kind=KIND_ECON,
            timestamp=timestamp,
            calculator_version=version,
            note="m2.3 writer stores the assessor's MEV-adjusted expected "
                 "profit dollars in atomic_profit_usd. Value is that stored "
                 "number, not a new calculation.",
        )
    else:
        mev_adjusted_usd = unavailable(
            note="MEV-adjusted dollars are not stored on this record"
        )

    fields: Dict[str, Any] = {
        "quote_notional_usd": quote_notional,
        "gross_profit_pct": gross,
        "gross_profit_usd": gross_usd,
        "dex_fee_pct": dex_fee_pct,
        "dex_fee_usd": dex_fee_usd,
        "flash_loan_fee_pct": flash_fee_pct,
        "flash_loan_fee_usd": flash_fee_usd,
        "gas_units": gas_units,
        "gas_price": gas_price,
        "gas_cost_usd": gas_cost,
        "slippage_pct": slippage_pct,
        "slippage_usd": slippage_usd,
        "mev_penalty": mev_penalty,
        "mev_adjusted_net_pct": mev_adj_pct,
        "mev_adjusted_net_usd": mev_adjusted_usd,
        "true_net_usd": true_net,
        "true_net_pct": true_net_pct,
        "decision_net_usd": _parse_decision_net(bundle, candidate, timestamp),
        "atomic_profit_usd": atomic,
        "gate_7": _gate7(bundle, timestamp),
    }

    # Raw override-or-zero bps, kept out of the applied-rate field.
    if isinstance(bundle, dict):
        found, raw_bps = lookup(bundle, "fees.flash_loan_fee_bps")
        if found and is_number(raw_bps):
            fields["flash_loan_fee_bps_stored"] = observed(
                value=raw_bps,
                status=STATUS_AVAILABLE,
                source="verifier_bundle.fees.flash_loan_fee_bps",
                provenance_kind=KIND_BUNDLE,
                timestamp=timestamp,
                note="quote override coerced with `or 0`. Not the applied catalog rate.",
            )

    ranked = [
        fields[name] for name in (
            "quote_notional_usd", "gross_profit_pct", "gross_profit_usd",
            "dex_fee_pct", "dex_fee_usd", "flash_loan_fee_pct",
            "flash_loan_fee_usd", "gas_units", "gas_price", "gas_cost_usd",
            "slippage_pct", "slippage_usd", "mev_penalty",
            "mev_adjusted_net_pct", "mev_adjusted_net_usd",
            "true_net_usd", "true_net_pct", "decision_net_usd",
            "atomic_profit_usd", "gate_7",
        )
    ]
    available = sum(1 for field in ranked if field["status"] == STATUS_AVAILABLE)
    if available == len(ranked):
        completeness = ECON_COMPLETE
    elif available == 0:
        completeness = ECON_UNAVAILABLE
    else:
        completeness = ECON_PARTIAL

    return {
        "completeness": completeness,
        "bundle_presence": presence,
        "fields": fields,
        "unresolved_fields": unresolved,
        "timestamp": timestamp,
        "calculator_version": version,
    }
