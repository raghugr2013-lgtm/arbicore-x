"""ArbiCore X — Phase D D-1: Venue Capability Registry.

Per PHASE_D_WAVE_1_FINAL_AUTHORIZATION_PACKAGE.md rev 3/4 §1.2.

Two collections:
  - arbicore_venue_capabilities — live state (one doc per venue)
  - arbicore_venue_capability_history — append-only time-series for
    future learning of per-venue reliability priors

The capability registry is venue-typed, NOT category-typed. Future
D-2 perp venues, D-3 DEX pools (with synthetic venue_id), D-5 bridges
will all share this collection.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

LIVE_COLLECTION = "arbicore_venue_capabilities"
HISTORY_COLLECTION = "arbicore_venue_capability_history"


class VenueCapabilityRepository:
    def __init__(self, db) -> None:
        self._db = db
        self._live = db[LIVE_COLLECTION]
        self._hist = db[HISTORY_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._live.create_index("venue_id", unique=True)
        await self._hist.create_index([("venue_id", 1), ("captured_at_ts", -1)])
        # TTL on history: 90 days
        await self._hist.create_index(
            "captured_at_ts",
            expireAfterSeconds=90 * 86400,
        )

    async def upsert(self, venue_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert live state; append delta to history when relevant."""
        now = time.time()
        doc = dict(doc)
        doc["venue_id"] = venue_id
        doc["last_probe_at"] = now

        prev = await self._live.find_one({"venue_id": venue_id})
        await self._live.update_one(
            {"venue_id": venue_id},
            {"$set": doc},
            upsert=True,
        )
        # History: write a row whenever a coarse flag changes OR every 5 min
        if self._should_record_history(prev, doc):
            await self._hist.insert_one({
                "venue_id": venue_id,
                "captured_at_ts": now,
                "snapshot": {
                    "deposit_summary":  doc.get("deposit_summary"),
                    "withdraw_summary": doc.get("withdraw_summary"),
                    "api_healthy":      doc.get("api_healthy"),
                    "latency_ms":       doc.get("latency_ms"),
                    "data_quality":     doc.get("data_quality"),
                    "venue_status":     doc.get("venue_status"),
                },
                "trigger": "state_change" if prev else "first_probe",
            })
        return doc

    @staticmethod
    def _should_record_history(prev: Optional[Dict[str, Any]],
                               new: Dict[str, Any]) -> bool:
        if prev is None:
            return True
        watched = ("api_healthy", "data_quality", "venue_status")
        for k in watched:
            if prev.get(k) != new.get(k):
                return True
        last_hist = prev.get("last_history_at", 0)
        if (time.time() - float(last_hist or 0)) >= 300:
            return True
        return False

    async def get(self, venue_id: str) -> Optional[Dict[str, Any]]:
        doc = await self._live.find_one({"venue_id": venue_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def all_live(self) -> List[Dict[str, Any]]:
        out = []
        async for doc in self._live.find({}):
            doc.pop("_id", None)
            out.append(doc)
        return out

    async def history(self, venue_id: str, *,
                      window_days: int = 7) -> List[Dict[str, Any]]:
        cutoff = time.time() - window_days * 86400
        cur = self._hist.find({
            "venue_id": venue_id,
            "captured_at_ts": {"$gte": cutoff},
        }).sort("captured_at_ts", -1)
        out = []
        async for doc in cur:
            doc.pop("_id", None)
            out.append(doc)
        return out

    async def set_status(self, venue_id: str, *,
                         venue_status: str,
                         reason: str = "operator") -> None:
        await self.upsert(venue_id, {
            "venue_status": venue_status,
            "status_change_reason": reason,
        })

    async def is_gate_3_pass(self, venue_id: str, asset_base: str,
                             asset_quote: str) -> tuple:
        """Returns (passes: bool, reason: str)."""
        doc = await self.get(venue_id)
        if doc is None:
            return False, "no_capability_data"
        if doc.get("venue_status") in ("down", "disabled"):
            return False, f"venue_status={doc.get('venue_status')}"
        if not doc.get("api_healthy", True):
            return False, "api_unhealthy"
        if doc.get("data_quality") not in (None, "OK"):
            return False, f"data_quality={doc.get('data_quality')}"
        caps = doc.get("asset_caps", {}) or {}
        b = caps.get(asset_base, {})
        q = caps.get(asset_quote, {})
        # Treat missing/unknown as permissive (real systems may not expose
        # public coin info; we don't want to false-fail every candidate).
        if b.get("deposit_enabled") is False:
            return False, f"deposit_disabled:{asset_base}"
        if q.get("withdraw_enabled") is False:
            return False, f"withdraw_disabled:{asset_quote}"
        return True, "ok"

    # ─── Phase D D-2.0: Funding (perp) capability helpers ──────────────────
    # Additive, fully backwards-compatible. The CEX/spot path
    # (is_gate_3_pass above) is untouched. Both venues in a funding pair
    # must pass `is_funding_gate_pass` for the funding scanner's Gate 3 to
    # succeed.
    #
    # Document shape (all keys OPTIONAL — absent ⇒ unknown ⇒ permissive
    # except where strictly evidence is required):
    #   {
    #     "venue_id": "bybit",
    #     # ... existing keys preserved ...
    #     "has_perp_market": True | False | None,
    #     "perp_caps": {
    #         "BTC": {"listed": True, "perp_symbol": "BTCUSDT",
    #                 "funding_interval_h": 8, "last_funding_rate_pct": 0.01,
    #                 "next_funding_iso": "...", "open_interest_usd": ...},
    #         ...
    #     }
    #   }

    async def is_funding_gate_pass(self, venue_id: str,
                                   asset_base: str) -> tuple:
        """Returns (passes: bool, reason: str). Per-venue check used by the
        FundingDifferentialVerifier for BOTH the long and short venues.

        Unknown (absent) `has_perp_market` / `perp_caps[base]` is treated
        as a HARD failure here — unlike spot caps where unknown is
        permissive — because we will not pretend a venue has a perp market
        unless we have positive evidence.
        """
        doc = await self.get(venue_id)
        if doc is None:
            return False, "no_capability_data"
        if doc.get("venue_status") in ("down", "disabled"):
            return False, f"venue_status={doc.get('venue_status')}"
        if not doc.get("api_healthy", True):
            return False, "api_unhealthy"
        if doc.get("data_quality") not in (None, "OK"):
            return False, f"data_quality={doc.get('data_quality')}"
        # Venue must have positive evidence of a perp market.
        if doc.get("has_perp_market") is not True:
            return False, "no_perp_market_evidence"
        perp_caps = doc.get("perp_caps") or {}
        entry = perp_caps.get(asset_base)
        if not entry or entry.get("listed") is not True:
            return False, f"perp_not_listed:{asset_base}"
        return True, "ok"

    async def is_funding_pair_gate_pass(self, venue_a: str, venue_b: str,
                                        asset_base: str) -> tuple:
        """Returns (passes, reason). Convenience wrapper for the funding
        scanner — both venues must independently pass."""
        if venue_a == venue_b:
            return False, "same_venue"
        ok_a, why_a = await self.is_funding_gate_pass(venue_a, asset_base)
        if not ok_a:
            return False, f"{venue_a}:{why_a}"
        ok_b, why_b = await self.is_funding_gate_pass(venue_b, asset_base)
        if not ok_b:
            return False, f"{venue_b}:{why_b}"
        return True, "ok"
