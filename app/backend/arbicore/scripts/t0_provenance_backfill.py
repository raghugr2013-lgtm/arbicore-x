"""T0-9 · Additive, idempotent provenance backfill (DRY-RUN by default).

Tags historical canonical opportunities that originated from the thin
activator (``metadata.engine == 'thin_activator'``) as SIMULATED so that
provenance-filtered certification (T0-7) treats them honestly. Also joins
paper evidence → opportunity to stamp ``source_data_quality`` on evidence
rows that predate T0.

SAFETY:
  * DRY-RUN by default — prints counts, writes nothing unless --apply.
  * NEVER deletes any document (auditability preserved).
  * Idempotent — re-running converges (only sets fields, never unsets).
  * Reads MONGO_URL / DB_NAME from env (never printed).

Usage (operator, on VPS — NOT run automatically):
    python -m arbicore.scripts.t0_provenance_backfill            # dry-run
    python -m arbicore.scripts.t0_provenance_backfill --apply    # write
"""
from __future__ import annotations

import argparse
import asyncio
import os


async def _run(apply: bool) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("MONGO_URL / DB_NAME must be set (values not printed)")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    opps = db["arbicore_opportunities"]
    thin_query = {"metadata.engine": "thin_activator",
                  "source_data_quality": {"$ne": "SIMULATED"}}
    thin_count = await opps.count_documents(thin_query)
    print(f"[opportunities] thin_activator rows needing SIMULATED tag: {thin_count}")

    if apply and thin_count:
        res = await opps.update_many(
            thin_query, {"$set": {"source_data_quality": "SIMULATED"}})
        print(f"[opportunities] tagged {res.modified_count} rows SIMULATED")

    # Evidence stamping (best-effort join; never deletes).
    ev = db["arbicore_paper_evidence"]
    missing = await ev.count_documents({"source_data_quality": {"$exists": False}})
    print(f"[evidence] rows lacking source_data_quality: {missing}")
    if apply and missing:
        stamped = 0
        cursor = ev.find({"source_data_quality": {"$exists": False}},
                         {"opportunity_id": 1})
        async for doc in cursor:
            opp = await opps.find_one({"opportunity_id": doc.get("opportunity_id")},
                                      {"source_data_quality": 1})
            prov = (opp or {}).get("source_data_quality") or "unknown"
            await ev.update_one({"_id": doc["_id"]},
                                {"$set": {"source_data_quality": prov}})
            stamped += 1
        print(f"[evidence] stamped {stamped} rows")

    print("DRY-RUN (no writes)" if not apply else "APPLIED")
    client.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default: dry-run)")
    args = ap.parse_args()
    asyncio.run(_run(args.apply))


if __name__ == "__main__":
    main()
