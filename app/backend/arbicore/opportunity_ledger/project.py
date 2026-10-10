"""Build one ledger projection from stored evidence.

Calls ``observe_strategy_intelligence``. Does not call the economics
assessor, the gates, or ``classify_strategy``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..observability import observe_strategy_intelligence
from ..observability.fields import STATUS_AVAILABLE
from .identity import ledger_id_for, normalize_mode, opportunity_id_for

SCHEMA_VERSION = "opportunity_ledger.v1"

_SECRET = re.compile(
    r"(://|mongodb(\+srv)?://|BEGIN [A-Z ]*PRIVATE KEY|"
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.)",
    re.IGNORECASE,
)
_GIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_REVISION = re.compile(r"^rev-[0-9a-f]{8,64}$")


def _plain(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        dumped = dump()
        if isinstance(dumped, dict):
            return dumped
    raise TypeError("candidate and bundle must be dicts or pydantic models")


def _available(field: Any) -> Any:
    """Persist an observer value only when its status is available.

    Available zero stays zero. Unavailable and not-persisted stay None.
    """
    if not isinstance(field, dict) or field.get("status") != STATUS_AVAILABLE:
        return None
    return field.get("value")


def _scrub(value: Any, flag: List[bool]) -> Any:
    if isinstance(value, str):
        if _SECRET.search(value):
            flag[0] = True
            return None
        return value
    if isinstance(value, list):
        return [_scrub(item, flag) for item in value]
    if isinstance(value, dict):
        return {str(key): _scrub(item, flag) for key, item in value.items()}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if value is None or isinstance(value, bool):
        return value
    flag[0] = True
    return None


def _safe_sha(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and _GIT_SHA.fullmatch(value):
        return value
    return None


def _safe_revision(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and _REVISION.fullmatch(value):
        return value
    return None


def _gate(gates: Any, name: str) -> Dict[str, Any]:
    if not isinstance(gates, dict):
        return {"status": None, "reason": None}
    gate = gates.get(name)
    if not isinstance(gate, dict):
        return {"status": None, "reason": None}
    status = gate.get("status")
    reason = gate.get("reason")
    return {
        "status": status if isinstance(status, str) else None,
        "reason": reason if isinstance(reason, str) else None,
    }


def _legs(view_legs: Any) -> List[Dict[str, Any]]:
    if not isinstance(view_legs, list):
        return []
    ordered = sorted(
        (leg for leg in view_legs if isinstance(leg, dict)),
        key=lambda leg: leg.get("hop_index") if isinstance(leg.get("hop_index"), int) else 0,
    )
    out: List[Dict[str, Any]] = []
    for leg in ordered:
        quote = leg.get("quote") if isinstance(leg.get("quote"), dict) else {}
        out.append({
            "leg_index": leg.get("hop_index") if isinstance(leg.get("hop_index"), int) else None,
            "token_in": _available(leg.get("token_in")),
            "token_out": _available(leg.get("token_out")),
            "protocol": _available(leg.get("protocol")),
            "venue": _available(leg.get("venue")),
            "pool": _available(leg.get("pool")),
            "pool_address": _available(leg.get("pool_address")),
            "input_amount": _available(quote.get("amount_in_wei")),
            "output_amount": _available(quote.get("amount_out_wei")),
            "quote": None,
            "fee_bps": _available(quote.get("fee_bps")),
            "quote_status": _available(quote.get("quote_status")),
            "quote_timestamp": None,
            "block": _available(quote.get("block_number")),
            "source": _available(quote.get("source_id")),
        })
    return out


def _economics(fields: Any) -> Dict[str, Any]:
    src = fields if isinstance(fields, dict) else {}

    def pick(name: str) -> Any:
        return _available(src.get(name))

    return {
        "notional_usd": pick("quote_notional_usd"),
        "gross_spread_pct": pick("gross_profit_pct"),
        "gross_profit_usd": pick("gross_profit_usd"),
        "dex_fee_pct": pick("dex_fee_pct"),
        "dex_fee_usd": pick("dex_fee_usd"),
        "flash_loan_fee_usd": pick("flash_loan_fee_usd"),
        "flash_loan_fee_pct": pick("flash_loan_fee_pct"),
        "gas_cost_usd": pick("gas_cost_usd"),
        "gas_units": pick("gas_units"),
        "gas_price": pick("gas_price"),
        "slippage_pct": pick("slippage_pct"),
        "slippage_usd": pick("slippage_usd"),
        "mev_penalty": pick("mev_penalty"),
        "mev_adjusted_net_usd": pick("mev_adjusted_net_usd"),
        "mev_adjusted_net_pct": pick("mev_adjusted_net_pct"),
        "total_cost_usd": None,
        "true_net_usd": pick("true_net_usd"),
        "true_net_pct": pick("true_net_pct"),
    }


def project_opportunity_ledger(
    *,
    candidate: Any,
    run_id: str,
    mode: str,
    bundle: Any = None,
    git_sha: Optional[str] = None,
    network_config_revision: Optional[str] = None,
    projected_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a ledger document. Does not write it."""
    cand = _plain(candidate)
    if cand is None:
        raise ValueError("candidate is required")
    bund = _plain(bundle)
    mode_n = normalize_mode(mode)
    candidate_id = cand.get("candidate_id")
    opp_id = opportunity_id_for(candidate_id=candidate_id, bundle=bund)
    ledger_id = ledger_id_for(mode=mode_n, run_id=run_id, candidate_id=str(candidate_id))

    observation = observe_strategy_intelligence(bund, cand)
    strategy = observation.get("strategy") or {}
    econ_fields = ((observation.get("economics") or {}).get("fields") or {})
    bundle_id = None
    if isinstance(bund, dict) and isinstance(bund.get("bundle_id"), str) and bund.get("bundle_id").strip():
        bundle_id = bund.get("bundle_id").strip()

    chain = None
    if isinstance(bund, dict) and isinstance(bund.get("chain"), str):
        chain = bund.get("chain")
    elif isinstance(cand.get("chain"), str):
        chain = cand.get("chain")

    provider = None
    if isinstance(bund, dict) and isinstance(bund.get("flash_loan_provider"), str):
        provider = bund.get("flash_loan_provider")
    hint = cand.get("hint_metric") if isinstance(cand.get("hint_metric"), dict) else {}
    if provider is None and isinstance(hint.get("provider"), str):
        provider = hint.get("provider")

    verified = cand.get("verified_outcome")
    if not isinstance(verified, str):
        verified = None
    bundle_outcome = None
    gates = None
    if isinstance(bund, dict):
        if isinstance(bund.get("outcome_tag"), str):
            bundle_outcome = bund.get("outcome_tag")
        gates = bund.get("gates")

    calc = (observation.get("economics") or {}).get("calculator_version")
    if not isinstance(calc, str) or not calc.strip():
        calc = None

    record: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ledger_id": ledger_id,
        "opportunity_id": opp_id,
        "run_id": run_id,
        "mode": mode_n,
        "candidate_id": str(candidate_id),
        "verifier_bundle_id": bundle_id,
        "evidence": {
            "strategy": {
                "primary_family": strategy.get("primary_family"),
                "secondary_tags": list(strategy.get("secondary_tags") or []),
                "confidence": strategy.get("confidence"),
                "evidence": list(strategy.get("evidence") or []),
                "classifier_version": strategy.get("classifier_version"),
                "classification_completeness": strategy.get("strategy_completeness"),
                "classification_state": strategy.get("classification_state"),
            },
            "legs": _legs(observation.get("legs")),
            "economics": _economics(econ_fields),
            "gates": {
                "gate_7": _gate(gates, "gate_7"),
                "gate_8": _gate(gates, "gate_8"),
                "gate_9": _gate(gates, "gate_9"),
                "final_observed_status": verified,
                "bundle_outcome_tag": bundle_outcome,
                "decision_net_usd": _available(econ_fields.get("decision_net_usd")),
            },
            "provenance": {
                "chain": chain,
                "flash_loan_provider": provider,
                "quote_source": None,
                "verifier_component": (
                    bund.get("source_component")
                    if isinstance(bund, dict) and isinstance(bund.get("source_component"), str)
                    else None
                ),
                "evidence_schema_version": observation.get("evidence_schema_version"),
                "calculator_version": calc,
                "classifier_version": observation.get("classifier_version"),
                "git_sha": _safe_sha(git_sha),
                "network_config_revision": _safe_revision(network_config_revision),
                "rpc_identity": None,
                "timestamps": {
                    "hint_observed_at": cand.get("hint_observed_at"),
                    "verified_at": cand.get("verified_at"),
                    "bundle_created_at": observation.get("bundle_created_at"),
                },
                "bundle_presence": observation.get("bundle_presence"),
            },
        },
        "projected_at": projected_at or datetime.now(timezone.utc).isoformat(),
    }
    legs = record["evidence"]["legs"]
    if legs and isinstance(legs[0].get("source"), str):
        record["evidence"]["provenance"]["quote_source"] = legs[0]["source"]

    flag = [False]
    scrubbed = _scrub(record, flag)
    scrubbed["evidence"]["provenance"]["secrets_withheld"] = flag[0]
    return scrubbed
