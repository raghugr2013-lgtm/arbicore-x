"""BDAG Network Transfer Fee — measured-from-real-transactions evidence (READ-ONLY).

Persists every observed wallet → exchange BDAG transfer so we can replace the
hardcoded `bdag_transfer_fee_base` assumption (0.001 BDAG) with the actual
measured network fee. The arbitrage_intel cycle accounting consumes this rolling
average via `services/execution/fees.get_effective_fees()` when measured
evidence exists; otherwise it falls back to the audited default.

Operator-attested measurements are accepted (with or without a tx hash). No
fund movement is involved at any point — these are observations only.
"""
import statistics

from core.models import new_id, now_iso
from services import db

COLL = "bdag_transfer_evidence"
ROLLING_WINDOW = 50          # latest N transfers used for the effective fee


SEED_OBSERVATIONS = [
    {
        "id": "seed_2025_1000",
        "amount_bdag": 1000.0,
        "fee_bdag": 0.0000025,         # mid of the observed 0.000001–0.000004 range
        "fee_min_bdag": 0.000001,
        "fee_max_bdag": 0.000004,
        "tx_hash": None,
        "source": "operator_attested",
        "note": "Operator-attested 1,000 BDAG wallet→exchange transfer; measured fee 0.000001–0.000004 BDAG.",
        "created_at": "2025-12-01T00:00:00+00:00",
        "seed": True,
    },
    {
        "id": "seed_2025_4000",
        "amount_bdag": 4000.0,
        "fee_bdag": 0.0000025,
        "fee_min_bdag": 0.000001,
        "fee_max_bdag": 0.000004,
        "tx_hash": None,
        "source": "operator_attested",
        "note": "Operator-attested 4,000 BDAG wallet→exchange transfer (Coinstore deposit confirmed); "
                "measured fee 0.000001–0.000004 BDAG.",
        "created_at": "2025-12-01T00:00:01+00:00",
        "seed": True,
    },
]


async def ensure_seeded():
    existing = await db.db[COLL].count_documents({"seed": True})
    if existing == 0:
        await db.db[COLL].insert_many([dict(o) for o in SEED_OBSERVATIONS])


async def record(amount_bdag: float, fee_bdag: float, tx_hash: str = None,
                 source: str = "operator_attested", note: str = None) -> dict:
    doc = {
        "id": new_id(),
        "amount_bdag": float(amount_bdag),
        "fee_bdag": float(fee_bdag),
        "tx_hash": (tx_hash or None),
        "source": source,
        "note": note,
        "created_at": now_iso(),
        "seed": False,
    }
    await db.db[COLL].insert_one(doc)
    # Strip Mongo ObjectId from the returned doc to keep JSON serializable
    doc.pop("_id", None)
    return {**doc}


async def list_transfers(limit: int = 50) -> list:
    docs = await db.db[COLL].find({}, {"_id": 0}, sort=[("created_at", -1)]).to_list(max(1, min(limit, 500)))
    return docs


async def rolling_average() -> dict:
    docs = await db.db[COLL].find({}, {"_id": 0, "fee_bdag": 1, "amount_bdag": 1, "created_at": 1},
                                  sort=[("created_at", -1)]).to_list(ROLLING_WINDOW)
    fees = [d["fee_bdag"] for d in docs if isinstance(d.get("fee_bdag"), (int, float))]
    amounts = [d["amount_bdag"] for d in docs if isinstance(d.get("amount_bdag"), (int, float))]
    if not fees:
        return {
            "count": 0, "avg_fee_bdag": None, "median_fee_bdag": None,
            "min_fee_bdag": None, "max_fee_bdag": None,
            "avg_amount_bdag": None, "window": ROLLING_WINDOW,
            "first_at": None, "last_at": None,
            "note": "No measured BDAG transfers recorded yet.",
        }
    return {
        "count": len(fees),
        "avg_fee_bdag": round(statistics.mean(fees), 9),
        "median_fee_bdag": round(statistics.median(fees), 9),
        "min_fee_bdag": min(fees),
        "max_fee_bdag": max(fees),
        "avg_amount_bdag": round(statistics.mean(amounts), 4) if amounts else None,
        "stdev_fee_bdag": round(statistics.pstdev(fees), 9) if len(fees) > 1 else 0.0,
        "window": ROLLING_WINDOW,
        "first_at": docs[-1].get("created_at"),
        "last_at": docs[0].get("created_at"),
        "note": "Rolling average over the latest N≤{0} observed wallet→exchange transfers.".format(ROLLING_WINDOW),
    }


async def effective_transfer_fee_bdag(default: float) -> dict:
    """Returns the measured rolling-average BDAG transfer fee if any evidence
    exists, otherwise the audited default. Caller decides which to consume."""
    ra = await rolling_average()
    if ra.get("avg_fee_bdag") is not None:
        return {
            "value": ra["avg_fee_bdag"],
            "source": "measured_from_real_transactions",
            "evidence_count": ra["count"],
            "rolling_average": ra,
            "default_value": default,
        }
    return {
        "value": default,
        "source": "hardcoded_estimate",
        "evidence_count": 0,
        "rolling_average": ra,
        "default_value": default,
    }


async def status() -> dict:
    ra = await rolling_average()
    return {
        "phase": "BDAG Network Transfer Evidence (measured-from-real-transactions)",
        "generated_at": now_iso(),
        "rolling_average": ra,
        "recent_transfers": await list_transfers(20),
        "consumers": ["Arbitrage Intelligence", "Opportunity Engine", "Opportunity Gate",
                      "Sizing Engine", "Safety Interlock", "Certification", "E5 (future)"],
        "note": ("Read-only fee evidence. Used to replace the hardcoded BDAG transfer fee assumption with a "
                 "measured rolling average. No fund movement."),
    }
