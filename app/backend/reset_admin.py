"""Emergency admin recovery — resets the AUTHENTICATION store used by the
running application so the first-run setup flow re-opens.

v2.9.3 — Auth-store-aware, safety-net variant.

Background
----------
Between v1.0.0 and v2.9.2 the repository accumulated two authentication
implementations that used different Mongo collections:

  * Canonical (mounted since v2.9.3): ``users``  — single-admin, first-run
    setup, cookie-based JWT.  Reset ⇒ ``GET /api/auth/status`` reports
    ``setup_complete=false`` and the UI shows the CREATE ADMIN card.

  * Legacy (Tree-B, retired in v2.9.3): ``auth_users`` — auto-seeded
    ``admin`` / ``operator`` accounts, bearer-token JWT.  This collection
    is no longer read by the running application.

This script is intentionally conservative:

  * By default it ONLY resets the canonical ``users`` collection.
  * If ``users`` is empty but ``auth_users`` is populated, it PRINTS a
    warning and refuses to touch ``auth_users`` without ``--legacy``.
  * It NEVER clears both stores by default.
  * ``--dry-run`` reports what WOULD change without writing to Mongo.

Usage
-----
    # Preview only — no writes
    python reset_admin.py --dry-run

    # Reset canonical store (default; matches v2.9.3+ running app)
    python reset_admin.py

    # Also clear the legacy Tree-B store (only if you know why)
    python reset_admin.py --legacy

    # Only clear legacy, keep canonical
    python reset_admin.py --legacy --skip-canonical

Exit codes: 0 on success, non-zero on any Mongo error.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


CANONICAL_USERS_COLL = "users"
CANONICAL_LOCKOUT_COLL = "login_attempts"
LEGACY_USERS_COLL = "auth_users"
LEGACY_SESSIONS_COLL = "auth_sessions"


async def _count(db, name: str) -> int:
    try:
        return await db[name].count_documents({})
    except Exception as exc:  # noqa: BLE001
        print(f"  ! could not read {name!r}: {exc}", file=sys.stderr)
        return -1


async def _wipe(db, name: str, dry_run: bool) -> int:
    if dry_run:
        n = await _count(db, name)
        print(f"  [dry-run] would delete {n} document(s) from {name!r}")
        return n
    res = await db[name].delete_many({})
    print(f"  - deleted {res.deleted_count} document(s) from {name!r}")
    return res.deleted_count


async def main(args: argparse.Namespace) -> int:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL and DB_NAME must be set in the environment (.env).",
              file=sys.stderr)
        return 2

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]

        # ---- inventory ----
        canonical_n = await _count(db, CANONICAL_USERS_COLL)
        legacy_n = await _count(db, LEGACY_USERS_COLL)
        lockout_n = await _count(db, CANONICAL_LOCKOUT_COLL)
        sessions_n = await _count(db, LEGACY_SESSIONS_COLL)

        print(f"Auth store inventory in database {db_name!r}:")
        print(f"  canonical  {CANONICAL_USERS_COLL!r:16s} -> {canonical_n} document(s)")
        print(f"  canonical  {CANONICAL_LOCKOUT_COLL!r:16s} -> {lockout_n} document(s)")
        print(f"  legacy     {LEGACY_USERS_COLL!r:16s} -> {legacy_n} document(s)")
        print(f"  legacy     {LEGACY_SESSIONS_COLL!r:16s} -> {sessions_n} document(s)")
        print("")

        # ---- safety net: canonical empty but legacy populated ----
        if (
            not args.legacy
            and canonical_n == 0
            and legacy_n > 0
        ):
            print(
                "WARNING: The canonical store 'users' is already empty, but the\n"
                "legacy store 'auth_users' contains {n} document(s). The running\n"
                "v2.9.3+ backend reads only 'users', so clearing it again is a\n"
                "no-op. If you *intentionally* want to also clear the legacy\n"
                "collections, re-run with:  python reset_admin.py --legacy\n"
                .format(n=legacy_n)
            )
            print("Refusing to proceed without --legacy or --skip-canonical.")
            return 3

        touched = False

        # ---- canonical reset (default) ----
        if not args.skip_canonical:
            print("Resetting canonical authentication store …")
            await _wipe(db, CANONICAL_USERS_COLL, dry_run=args.dry_run)
            await _wipe(db, CANONICAL_LOCKOUT_COLL, dry_run=args.dry_run)
            touched = True

        # ---- legacy reset (opt-in) ----
        if args.legacy:
            print("Resetting LEGACY authentication store (opt-in via --legacy) …")
            await _wipe(db, LEGACY_USERS_COLL, dry_run=args.dry_run)
            await _wipe(db, LEGACY_SESSIONS_COLL, dry_run=args.dry_run)
            touched = True

        if not touched:
            print("Nothing to do — both stores skipped.")
            return 0

        print("")
        if args.dry_run:
            print("Dry-run complete. Re-run without --dry-run to apply.")
        else:
            print("Setup flow is open again — open the dashboard to create a new")
            print("admin account. Vault keys, market data, MID, and calibration")
            print("state are untouched.")
        return 0
    finally:
        client.close()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Reset the authentication store used by the running ArbiCore X backend."
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would change without writing to Mongo.")
    p.add_argument("--legacy", action="store_true",
                   help="Also reset the retired Tree-B store (auth_users, auth_sessions).")
    p.add_argument("--skip-canonical", action="store_true",
                   help="Do NOT reset the canonical 'users'/'login_attempts' collections. "
                        "Only meaningful together with --legacy.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(main(args)))
