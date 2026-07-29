"""Evidence Accuracy Report (READ-ONLY).

Captures exactly which assumptions were replaced by real-world evidence in this
build. Static record + live snapshot of current value vs former value, so the
operator can see at a glance how the ROI math moved from assumption-based to
evidence-based.

No execution, no orders, no fund movement.
"""
from core.models import now_iso
from services.execution import bdag_transfers
from services.execution.fees import get_fees

# Per the operator brief — every fee that moved from assumption → evidence.
ASSUMPTION_TO_EVIDENCE = [
    {
        "fee_id": "bdag_transfer_gas",
        "fee_name": "BDAG network transfer fee (wallet→exchange)",
        "before": {
            "classification": "Blockchain (hardcoded estimate)",
            "assumption_status": "Assumption",
            "source": "BlockDAG docs: 21,000 gas × ~12 gwei estimate",
            "default_value_bdag": 0.001,
            "confidence": "high",
            "recommendation": "Assumption Only",
        },
        "after": {
            "classification": "Measured From Real Transactions",
            "assumption_status": "Measured Transaction",
            "source": "Rolling average of operator-attested real BDAG transfers "
                      "(1,000 BDAG, 4,000 BDAG; observed fee 0.000001–0.000004 BDAG)",
            "confidence": "high",
            "recommendation": "Production Grade (measured)",
        },
        "magnitude_note": ("Measured value is roughly 250–1,000× smaller than the previous hardcoded "
                           "assumption. Consumed by Arbitrage Intelligence + Sizing + Gate."),
    },
    {
        "fee_id": "taker_fee_coinstore",
        "fee_name": "Coinstore trading (taker) fee",
        "before": {
            "classification": "Exchange (audited default)",
            "assumption_status": "Exchange Sourced (audited default — not live)",
            "source": "CoinGecko Coinstore exchange page (static default, user-overridable)",
            "default_value_pct": 0.20,
            "confidence": "medium",
            "recommendation": "Needs Verification",
        },
        "after": {
            "classification": "Exchange Sourced",
            "assumption_status": "Exchange Sourced (operator-verified live)",
            "source": "Operator-verified at the Coinstore account fee page (0.20% taker, 2026-06-14)",
            "value_pct": 0.20,
            "confidence": "high",
            "recommendation": "Production Grade",
        },
        "magnitude_note": "Value unchanged; confidence and provenance moved from audited-default to verified-live.",
    },
    {
        "fee_id": "usdt_withdrawal_fee_coinstore",
        "fee_name": "Coinstore USDT withdrawal fee (BEP20)",
        "before": {
            "classification": "Exchange (audited default)",
            "assumption_status": "Exchange Sourced (audited default — not live)",
            "source": "Coinstore shown at withdrawal — static default",
            "default_value_usd": 1.00,
            "confidence": "medium",
            "recommendation": "Needs Verification",
        },
        "after": {
            "classification": "Exchange Sourced",
            "assumption_status": "Exchange Sourced (operator-verified live)",
            "source": "Operator-verified at the Coinstore USDT BEP20 withdrawal page (1 USDT flat, 2026-06-14)",
            "value_usd": 1.00,
            "confidence": "high",
            "recommendation": "Production Grade",
        },
        "magnitude_note": "Value unchanged; confidence and provenance moved from audited-default to verified-live.",
    },
    {
        "fee_id": "exchange_deposit_fee_coinstore",
        "fee_name": "Coinstore BDAG deposit fee",
        "before": {
            "classification": "Hardcoded assumption",
            "assumption_status": "Assumption",
            "source": "Exchange deposits assumed free; BDAG deposit gating historically intermittent",
            "default_value_usd": 0.0,
            "confidence": "medium",
            "recommendation": "Assumption Only",
        },
        "after": {
            "classification": "Exchange Sourced",
            "assumption_status": "Exchange Sourced (operator-verified live)",
            "source": "Operator-verified at the Coinstore BDAG deposit page; 4,000 BDAG deposit confirmed "
                      "successful (2026-06-14). Minimum deposit = 3,703 BDAG.",
            "value_usd": 0.0,
            "confidence": "high",
            "recommendation": "Production Grade",
        },
        "magnitude_note": "Value unchanged; deposit-gate state is now positively confirmed by a real deposit, "
                          "and the 3,703 BDAG minimum deposit becomes a hard constraint for sizing.",
    },
]


# Inputs that REMAIN as assumptions (full transparency on what's left to verify).
REMAINING_ASSUMPTIONS = [
    {
        "fee_id": "bsc_purchase_gas",
        "fee_name": "BSC purchase gas",
        "current_classification": "Blockchain Sourced (estimate, no live oracle)",
        "rationale": ("Buffered to $0.10 vs ~$0.00–0.01 actual on BNB Smart Chain. Small absolute drag, "
                      "but not pulled from a live gas oracle."),
        "action_for_e5": "Wire a live BSC gas oracle before any E5 execution if cycle size grows.",
    },
    {
        "fee_id": "bdag_withdrawal_fee",
        "fee_name": "BDAG withdrawal fee (exchange→wallet)",
        "current_classification": "Hardcoded Assumption",
        "rationale": "Only shown in each venue's withdrawal UI at withdrawal time; not consumed by the current "
                     "sell-cycle ROI (E5 / certification only).",
        "action_for_e5": "Replace with operator-verified per-venue values before E5.",
    },
]


async def build() -> dict:
    fees = await get_fees()
    transfer_ev = await bdag_transfers.rolling_average()

    # live snapshot of consumed values
    live_snapshot = {
        "bdag_transfer_fee_consumed_bdag": (transfer_ev.get("avg_fee_bdag")
                                            if transfer_ev.get("count")
                                            else fees["bdag_transfer_fee_base"]),
        "bdag_transfer_evidence_count": transfer_ev.get("count", 0),
        "bdag_transfer_evidence_window": transfer_ev.get("window"),
        "coinstore_taker_fee_pct": (fees["taker_fee_pct"] or {}).get("coinstore"),
        "coinstore_usdt_withdrawal_fee_usd": (fees["usdt_withdrawal_fee_usd"] or {}).get("coinstore"),
        "coinstore_bdag_deposit_fee_usd": fees["exchange_deposit_fee_usd"],
        "coinstore_bdag_minimum_deposit_bdag": 3703,
    }

    replaced = ASSUMPTION_TO_EVIDENCE
    remaining = REMAINING_ASSUMPTIONS

    real_total = len(replaced)
    remaining_total = len(remaining)
    pct_evidence = round(real_total / (real_total + remaining_total) * 100, 1) \
        if (real_total + remaining_total) else 0.0

    return {
        "phase": "Evidence Accuracy Report (read-only)",
        "generated_at": now_iso(),
        "summary": {
            "assumptions_replaced_with_evidence": real_total,
            "assumptions_remaining": remaining_total,
            "pct_evidence_grade": pct_evidence,
            "headline": (f"{real_total} of {real_total + remaining_total} critical fee inputs are now driven by "
                         f"real-world evidence ({pct_evidence}%). Remaining {remaining_total} assumption(s) are "
                         f"non-critical for the current sell-cycle ROI."),
        },
        "live_snapshot": live_snapshot,
        "replaced": replaced,
        "remaining_assumptions": remaining,
        "assumption_status_taxonomy": ["Assumption", "Exchange Sourced", "Blockchain Sourced",
                                       "Measured Transaction", "User Configured"],
        "note": ("Read-only diff of what was assumption-based vs evidence-based BEFORE and AFTER this "
                 "update. No execution, no orders, no fund movement, no E5."),
    }
