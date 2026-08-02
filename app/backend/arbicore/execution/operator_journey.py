"""Guided Flash Loan Operator Journey — Phase 10.7.

Read-only composer that groups every existing readiness signal
(wizard state, FL prereqs, post-trade receipts, operational flags)
into 14 progressive stages the operator can advance through
one at a time.  ZERO new state stored — everything is derived.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# fix_path → wizard step_key mapping for each journey stage
_STAGES: List[Dict[str, Any]] = [
    {"key": "settings",   "label": "1 · Configure Settings",
     "fix_path": "/v2/settings", "prereq_keys": []},
    {"key": "network",    "label": "2 · Configure Network (Base RPC)",
     "fix_path": "/v2/settings/network", "prereq_keys": ["rpc"]},
    {"key": "scanner",    "label": "3 · Configure Scanner",
     "fix_path": "/v2/settings/scanner", "prereq_keys": []},
    {"key": "wallet",     "label": "4 · Register Wallet",
     "fix_path": "/v2/flash-loan-operator", "prereq_keys": ["wallet"]},
    {"key": "secret",     "label": "5 · Store Secret",
     "fix_path": "/v2/settings/secrets", "prereq_keys": ["secret"]},
    {"key": "secret_link","label": "6 · Link Secret to Wallet",
     "fix_path": "/v2/flash-loan-operator", "prereq_keys": ["secret"]},
    {"key": "deploy",     "label": "7 · Deploy FlashLoanReceiver.sol",
     "fix_path": "/v2/settings/network", "prereq_keys": ["executor"]},
    {"key": "exec_addr",  "label": "8 · Configure Executor Address",
     "fix_path": "/v2/settings/network", "prereq_keys": ["executor"]},
    {"key": "exec_verify","label": "9 · Verify Executor",
     "fix_path": "/v2/executor-verify",  "prereq_keys": ["executor_verify"]},
    {"key": "family_on",  "label": "10 · Enable Flash Loan Scanner Family",
     "fix_path": "/v2/settings/scanner", "prereq_keys": []},
    {"key": "await_opp",  "label": "11 · Manual plan OR await opportunity",
     "fix_path": "/v2/flash-loan-operator", "prereq_keys": []},
    {"key": "revert_test","label": "12 · Intentional revert test",
     "fix_path": "/v2/flash-loan-operator", "prereq_keys": []},
    {"key": "first_live", "label": "13 · First LIMITED_LIVE Flash Loan",
     "fix_path": "/v2/flash-loan-operator", "prereq_keys": []},
    {"key": "post_trade", "label": "14 · Review + Mark VPS-Ready",
     "fix_path": "/v2/post-trade", "prereq_keys": []},
]


async def build_journey(*, wizard_state, prereqs, post_trade,
                        scanner_family_enabled: bool,
                        operational_flags: Dict[str, Any]
                        ) -> Dict[str, Any]:
    """Compose the 14-stage journey from existing signals."""
    steps_by_key = {s["key"]: s for s in (wizard_state or {}).get("steps") or []}
    prereq_by_key = {c["key"]: c
                      for c in (prereqs or {}).get("checks") or []}
    receipts = (post_trade or {}).get("receipts") or []

    def _status(prereq_keys: List[str], override=None) -> str:
        if override is not None:
            return override
        if not prereq_keys:
            return "INFO"
        for k in prereq_keys:
            s = (steps_by_key.get(k) or {}).get("status")
            if s == "BLOCKED":
                return "BLOCKED"
            if s == "WAIT":
                return "WAIT"
        return "READY"

    live_receipts = [r for r in receipts
                       if r.get("mode") == "LIMITED_LIVE"
                       and r.get("broadcast_sent")]

    stages: List[Dict[str, Any]] = []
    for s in _STAGES:
        key = s["key"]
        override = None
        detail = ""
        if key == "settings":
            override = "READY"
            detail = "Settings shell available (11 sub-tabs live)"
        elif key == "family_on":
            override = "READY" if scanner_family_enabled else "WAIT"
            detail = ("Flash Loan family enabled" if scanner_family_enabled
                       else "Toggle enabled in Settings › Scanner → Flash Loan")
        elif key == "secret_link":
            # READY only when both wallet + secret prereqs are READY.
            w = (steps_by_key.get("wallet") or {}).get("status")
            sec = (steps_by_key.get("secret") or {}).get("status")
            override = "READY" if (w == "READY" and sec == "READY") else "BLOCKED" if (w == "BLOCKED" or sec == "BLOCKED") else "WAIT"
            detail = "Wallet has bound secret_handle_id" if override == "READY" else "Copy the handle_id from Secrets → paste into wallet form"
        elif key == "deploy":
            e = (steps_by_key.get("executor") or {}).get("status")
            override = "READY" if e == "READY" else ("WAIT" if e == "WAIT" else "BLOCKED")
            detail = "FlashLoanReceiver.sol deployed" if override == "READY" else "Deploy per canonical_repo/contracts/DEPLOY.md then paste address in Network"
        elif key == "await_opp":
            override = "INFO"
            detail = "Auto-discovery for Flash Loan is deferred to Phase 10.9 — compose a manual plan on the Operator page"
        elif key == "revert_test":
            revert = any((r.get("tx_hash") and not r.get("broadcast_sent")) or
                          (r.get("preflight_ok") is False and r.get("tx_hash"))
                          for r in receipts)
            override = "READY" if revert else "WAIT"
            detail = "Intentional-revert tx recorded" if revert else "Optional but recommended — see Manual §11.1 Tx#1"
        elif key == "first_live":
            override = "READY" if live_receipts else "WAIT"
            detail = (f"{len(live_receipts)} LIMITED_LIVE tx sent"
                       if live_receipts else "No LIMITED_LIVE broadcasts yet")
        elif key == "post_trade":
            marked = bool((operational_flags or {}).get("vps_ready"))
            if marked:
                override = "READY"; detail = "Operator marked system VPS-ready"
            elif live_receipts:
                override = "WAIT"
                detail = "Review Post-Trade + Telegram then mark VPS-ready in Operational flags"
            else:
                override = "BLOCKED"; detail = "Complete stage 13 first"

        status = _status(s["prereq_keys"], override=override)
        stages.append({**s, "status": status, "detail": detail})

    # Progressive unlock: a stage is 'unlocked' iff every previous stage
    # is READY or INFO.  BLOCKED / WAIT locks the tail.
    unlocked_until = 0
    for i, st in enumerate(stages):
        if st["status"] in ("READY", "INFO"):
            unlocked_until = i + 1
        else:
            break
    for i, st in enumerate(stages):
        st["unlocked"] = i < unlocked_until + 1  # current + next
        st["is_current"] = (i == unlocked_until) if unlocked_until < len(stages) else (i == len(stages) - 1)

    return {
        "stages": stages,
        "current_stage_index": unlocked_until if unlocked_until < len(stages) else len(stages) - 1,
        "completed": unlocked_until == len(stages),
        "live_broadcast_count": len(live_receipts),
        "generated_at": _iso_now(),
    }
