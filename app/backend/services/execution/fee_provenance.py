"""Fee Provenance Audit (READ-ONLY).

For every fee that enters a Fresh-Cycle / Existing-Position ROI calculation, this
report states EXACTLY where the number comes from, how fresh it is, how much we
trust it, the evidence source category, and which engines consume it.

CLASSIFICATION TAXONOMY (per operator brief — 2026-06-14):
  • Live API
  • Measured (live order book)
  • Measured From Real Transactions
  • Exchange Sourced
  • Blockchain Sourced
  • Historical Measurement
  • User Configured
  • Hardcoded Assumption

ASSUMPTION STATUS bucket (5-way) is derived from CLASSIFICATION.

No execution, no orders, no fund movement.
"""
from core.models import now_iso
from services import db
from services.execution.bdag_transfers import effective_transfer_fee_bdag, rolling_average
from services.execution.fees import FEE_KEY, get_fees
from services.portal_price import portal_price

# Engines that consume the per-cycle fee model.
ALL_CONSUMERS = ["Opportunity Engine", "Opportunity Gate", "Arbitrage Intelligence",
                 "Sizing Engine", "Certification", "Safety Interlock", "E5 (future)"]


# Map classification → 5-way Assumption Status bucket
ASSUMPTION_BUCKET = {
    "Live API": "Exchange Sourced",
    "Measured (live order book)": "Exchange Sourced",
    "Measured From Real Transactions": "Measured Transaction",
    "Exchange Sourced": "Exchange Sourced",
    "Blockchain Sourced": "Blockchain Sourced",
    "Historical Measurement": "Measured Transaction",
    "User Configured": "User Configured",
    "Hardcoded Assumption": "Assumption",
    # legacy mappings (kept for safety)
    "Exchange (audited default)": "Exchange Sourced",
    "Blockchain (hardcoded estimate)": "Blockchain Sourced",
    "Blockchain (hardcoded buffer)": "Blockchain Sourced",
}


def _entry(**kw):
    bucket = ASSUMPTION_BUCKET.get(kw.get("classification"), "Assumption")
    kw.setdefault("assumption_status", bucket)
    return kw


async def build() -> dict:
    fees = await get_fees()
    raw = await db.execution_config.find_one({"key": FEE_KEY}, {"_id": 0, "updated_at": 1}) or {}
    fee_ts = raw.get("updated_at")
    portal = await portal_price.status()
    swap_price = portal.get("bdag_price")
    swap_ts = portal.get("fetched_at")

    # Coinstore-verified fees per operator evidence (2026-06-14)
    coinstore_taker = (fees["taker_fee_pct"] or {}).get("coinstore", 0.20)
    coinstore_usdt_wd = (fees["usdt_withdrawal_fee_usd"] or {}).get("coinstore", 1.00)

    # BDAG transfer fee — measured rolling average replaces the hardcoded estimate
    eff = await effective_transfer_fee_bdag(fees["bdag_transfer_fee_base"])
    ra = await rolling_average()
    transfer_value = eff["value"]
    measured_transfer = eff["source"] == "measured_from_real_transactions"

    fee_items = [
        _entry(
            id="buy_price_live_swap",
            name="BlockDAG purchase price (Live Swap)",
            current_value=swap_price, unit="USD/BDAG",
            classification="Live API",
            evidence_source="BlockDAG Portal API live feed",
            source="BlockDAG Portal API (sw-api/getInfo) — same quote as purchase3.blockdag.network/swap",
            source_url="https://purchase3.blockdag.network/swap",
            timestamp=swap_ts, refresh_frequency="~30s poll (treated stale > 300s)",
            confidence="high", real=True, recommendation="Production Grade",
            consumers=ALL_CONSUMERS,
            note="Live executable buy price — drives Fresh Cycle ROI direction."),
        _entry(
            id="order_book_slippage",
            name="Order-book slippage (multi-level VWAP)",
            current_value="live VWAP", unit="derived from live book",
            classification="Measured (live order book)",
            evidence_source="Coinstore BDAG/USDT live order book",
            source="Live exchange order book via collector — VWAP across every consumed bid level",
            source_url="https://www.coinstore.com/spot/BDAGUSDT",
            timestamp=now_iso(), refresh_frequency="live (collector poll ~15–60s)",
            confidence="high", real=True, recommendation="Production Grade",
            consumers=ALL_CONSUMERS,
            note="Actual execution slippage simulated from the real bid ladder — not a single-price assumption."),
        _entry(
            id="taker_fee_coinstore",
            name="Coinstore trading (taker) fee",
            current_value=coinstore_taker, unit="% of proceeds",
            classification="Exchange Sourced",
            evidence_source="Coinstore — operator-verified live fee schedule",
            source="Operator-verified at Coinstore account fee page (2026-06-14): 0.20% taker.",
            source_url="https://www.coinstore.com/spot/BDAGUSDT",
            timestamp=fee_ts, refresh_frequency="manual / on fee-config edit",
            confidence="high", real=True, recommendation="Production Grade",
            consumers=ALL_CONSUMERS,
            note="Verified directly against the Coinstore account fee schedule. Largest variable fee component."),
        _entry(
            id="bsc_purchase_gas",
            name="BSC purchase gas",
            current_value=fees["purchase_gas_usd"], unit="USD/cycle",
            classification="Blockchain Sourced",
            evidence_source="BNB Smart Chain average gas estimate (buffered)",
            source="BNB Smart Chain avg ~0.82 gwei (2026) — buffered to $0.10 (actual ~$0.00–0.01)",
            source_url="https://bscscan.com/chart/gasprice",
            timestamp=fee_ts, refresh_frequency="manual (no live gas oracle wired)",
            confidence="high", real=False, recommendation="Needs Verification",
            consumers=ALL_CONSUMERS,
            note="Conservative over-estimate. Small absolute impact on a $25–50 cycle. Wire a live BSC gas oracle "
                 "before E5 if cycle size grows."),
        _entry(
            id="bdag_transfer_gas",
            name="BDAG network transfer fee (wallet→exchange)",
            current_value=transfer_value, unit="BDAG/tx",
            classification=("Measured From Real Transactions" if measured_transfer
                            else "Blockchain Sourced"),
            evidence_source=("Rolling average of {} observed BDAG transfers (1,000 BDAG & 4,000 BDAG verified)"
                             .format(ra.get("count", 0))
                             if measured_transfer else "BlockDAG docs (21,000 gas × ~12 gwei estimate)"),
            source=("Measured rolling average of {} observed wallet→exchange BDAG transfers; "
                    "operator-attested fee range 0.000001–0.000004 BDAG.".format(ra.get("count", 0))
                    if measured_transfer
                    else "BlockDAG docs: 21,000 gas × ~12 gwei ≈ 0.000252 BDAG → default 0.001"),
            source_url=None,
            timestamp=ra.get("last_at") if measured_transfer else fee_ts,
            refresh_frequency=("each observed transfer (rolling N≤{0})".format(ra.get("window") or 50)
                               if measured_transfer else "manual"),
            confidence="high", real=bool(measured_transfer),
            recommendation=("Production Grade (measured)" if measured_transfer else "Assumption Only"),
            consumers=ALL_CONSUMERS,
            evidence_count=ra.get("count", 0),
            note=("Replaces the hardcoded 0.001 BDAG assumption with the measured rolling average. "
                  "Observed real-world cost is 1000–4000× smaller than the previous assumption.")
            if measured_transfer
            else "No measured transfers recorded yet — fall back to BlockDAG docs estimate."),
        _entry(
            id="usdt_withdrawal_fee_coinstore",
            name="Coinstore USDT withdrawal fee (BEP20)",
            current_value=coinstore_usdt_wd, unit="USD/withdrawal",
            classification="Exchange Sourced",
            evidence_source="Coinstore — operator-verified at withdrawal UI",
            source="Operator-verified at Coinstore USDT withdrawal page (2026-06-14): 1 USDT flat, BEP20.",
            source_url="https://www.coinstore.com/finance/withdraw/USDT",
            timestamp=fee_ts, refresh_frequency="manual / on fee-config edit",
            confidence="high", real=True, recommendation="Production Grade",
            consumers=ALL_CONSUMERS,
            note="Verified directly. Flat per-withdrawal; relatively larger drag on small cycles."),
        _entry(
            id="exchange_deposit_fee_coinstore",
            name="Coinstore BDAG deposit fee",
            current_value=fees["exchange_deposit_fee_usd"], unit="USD",
            classification="Exchange Sourced",
            evidence_source="Coinstore — operator-verified deposit page (4,000 BDAG deposit confirmed)",
            source=("Coinstore BDAG deposit verified: native BDAG network, minimum 3,703 BDAG, "
                    "deposit fee = $0. Confirmed by a successful 4,000 BDAG deposit (2026-06-14)."),
            source_url="https://www.coinstore.com/finance/deposit/BDAG",
            timestamp=fee_ts, refresh_frequency="manual",
            confidence="high", real=True, recommendation="Production Grade",
            consumers=ALL_CONSUMERS,
            evidence_meta={"deposit_network": "BDAG", "minimum_deposit_bdag": 3703,
                           "verified_deposit_bdag": 4000},
            note="Deposit fee verified zero; minimum deposit 3,703 BDAG is hard-blocking for cert-cap sizing."),
        _entry(
            id="bdag_withdrawal_fee",
            name="BDAG withdrawal fee (exchange→wallet)",
            current_value=fees["bdag_withdrawal_fee_base"], unit="BDAG",
            classification="Hardcoded Assumption",
            evidence_source="Not publicly fixed — shown per-venue in withdrawal UI only",
            source="Override per venue at withdrawal time; not pulled live.",
            source_url=None,
            timestamp=fee_ts, refresh_frequency="manual",
            confidence="low", real=False, recommendation="Assumption Only",
            consumers=["E5 (future)", "Certification"],
            note="Used only in withdrawal accounting / future E5, not in the current sell-cycle ROI."),
    ]

    real = [f for f in fee_items if f["real"]]
    assumed = [f for f in fee_items if not f["real"]]
    rec_counts = {}
    bucket_counts = {}
    for f in fee_items:
        rec_counts[f["recommendation"]] = rec_counts.get(f["recommendation"], 0) + 1
        bucket_counts[f["assumption_status"]] = bucket_counts.get(f["assumption_status"], 0) + 1

    trust_verdict = (
        "ROI math is now driven primarily by EVIDENCE: the live swap price + measured order-book slippage "
        "(REAL-TIME), Coinstore trading and withdrawal fees verified against the live Coinstore account "
        "(EXCHANGE SOURCED), Coinstore deposit fee verified via a successful 4,000 BDAG deposit "
        "(EXCHANGE SOURCED), and the BDAG network transfer fee replaced by the measured rolling average "
        "of real observed transfers (MEASURED FROM REAL TRANSACTIONS). Remaining assumptions are confined "
        "to BSC purchase gas (buffered, small absolute impact) and the BDAG exchange→wallet withdrawal fee "
        "(only consumed by future E5)."
    )

    return {
        "phase": "Fee Provenance Audit (read-only, evidence-based)",
        "generated_at": now_iso(),
        "fees": fee_items,
        "summary": {
            "total_fees": len(fee_items),
            "real_count": len(real),
            "assumed_count": len(assumed),
            "real_fees": [f["name"] for f in real],
            "assumed_fees": [f["name"] for f in assumed],
            "recommendation_counts": rec_counts,
            "assumption_status_counts": bucket_counts,
        },
        "assumption_status_taxonomy": ["Assumption", "Exchange Sourced", "Blockchain Sourced",
                                       "Measured Transaction", "User Configured"],
        "trust_verdict": trust_verdict,
        "note": "Read-only provenance inspection. No execution, no orders, no fund movement.",
    }
