"""Read-only balance polling service (Sprint 4).
60s cadence · per-exchange polling status · 429-aware exponential backoff ·
manual refresh · USD valuation via live market data · snapshot persistence.
NEVER writes to exchanges — every call is a read-only account query."""
import asyncio
import logging
import time

from core import healthstats
from core import registry
from core.models import new_id, now_iso
from services import db, exchange_private, vault

logger = logging.getLogger("balances")

POLL_S = 60
HEALTH_FLUSH_S = 300
PRICE_CACHE_S = 300
MIN_REFRESH_GAP_S = 5
STABLES = {"USDT", "USDC", "USD", "DAI", "FDUSD", "BUSD", "TUSD", "USDD"}


class BalanceService:
    def __init__(self):
        self.state = {}        # exchange -> status dict
        self.last_cycle_at = None
        self._price_cache = {}  # asset -> (price|None, monotonic)
        self._wake = asyncio.Event()
        self._running = False
        self._task = None
        self._health_task = None
        self._last_cycle_mono = 0.0

    # ---------- lifecycle ----------
    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self._health_task = asyncio.create_task(self._health_loop())
        logger.info("Balance service started (poll every %ss)", POLL_S)

    async def stop(self):
        self._running = False
        for t in (self._task, self._health_task):
            if t:
                t.cancel()

    def refresh_now(self) -> bool:
        if time.monotonic() - self._last_cycle_mono < MIN_REFRESH_GAP_S:
            return False
        self._wake.set()
        return True

    async def _loop(self):
        await asyncio.sleep(5)
        while self._running:
            try:
                await self._cycle()
            except Exception as e:
                logger.warning("balance cycle failed: %s", e)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=POLL_S)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def _health_loop(self):
        while self._running:
            await asyncio.sleep(HEALTH_FLUSH_S)
            try:
                snap = healthstats.snapshot_and_reset()
                docs = [{"id": new_id(), "ts": now_iso(), "created_at": now_iso(),
                         "window_s": HEALTH_FLUSH_S, "exchange": ex, **s}
                        for ex, s in snap.items() if s["requests"] > 0]
                if docs:
                    await db.exchange_health_snaps.insert_many(docs)
            except Exception as e:
                logger.warning("health flush failed: %s", e)

    # ---------- polling ----------
    async def _cycle(self):
        self._last_cycle_mono = time.monotonic()
        keys = await db.api_keys_col.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
        latest = {}
        for k in keys:
            latest.setdefault(k["exchange"], k)  # newest key per exchange

        for ex in vault.SUPPORTED_EXCHANGES:
            st = self.state.setdefault(ex, {"exchange": ex, "polls": 0, "failures": 0,
                                            "fail_streak": 0, "status": "no_key",
                                            "balances": [], "total_usd": None})
            kd = latest.get(ex)
            if not kd:
                st.update(status="no_key", balances=[], total_usd=None, key_id=None,
                          key_label=None, error=None)
                continue
            st.update(key_id=kd["id"], key_label=kd.get("label"))
            if st.get("backoff_until") and time.monotonic() < st["backoff_until"]:
                st["status"] = "rate_limited"
                continue
            await self._poll_exchange(ex, st, kd)
        self.last_cycle_at = now_iso()

    async def _poll_exchange(self, ex, st, key_doc):
        creds = await vault.get_credentials(key_doc["id"])
        t0 = time.monotonic()
        res = await exchange_private.fetch_balances(ex, creds["api_key"], creds["api_secret"],
                                                    creds["passphrase"])
        latency = round((time.monotonic() - t0) * 1000)
        st["polls"] += 1
        st["last_poll_at"] = now_iso()
        st["latency_ms"] = latency
        prev_status = st.get("status")

        if res["ok"]:
            balances = await self._value(ex, res["balances"])
            total = round(sum(b["usd_value"] for b in balances if b["usd_value"] is not None), 2)
            st.update(status="ok", balances=balances, total_usd=total, error=None,
                      backoff_until=None, fail_streak=0)
            await db.balance_snapshots.insert_one({
                "id": new_id(), "ts": now_iso(), "created_at": now_iso(), "exchange": ex,
                "ok": True, "balances": balances, "total_usd": total, "latency_ms": latency})
            if key_doc.get("status") != "healthy":
                await vault.set_test_result(key_doc["id"], True, "balances OK (auto-poll)")
            return

        st["failures"] += 1
        st["fail_streak"] = st.get("fail_streak", 0) + 1
        st["error"] = res["error"]
        if res["rate_limited"]:
            backoff = min(120 * (2 ** (st["fail_streak"] - 1)), 1800)
            st["status"] = "rate_limited"
            st["backoff_until"] = time.monotonic() + backoff
            st["backoff_s"] = backoff
        else:
            st["status"] = "error"
        if prev_status != st["status"]:  # persist error transitions only (no noise)
            await db.balance_snapshots.insert_one({
                "id": new_id(), "ts": now_iso(), "created_at": now_iso(), "exchange": ex,
                "ok": False, "error": res["error"], "latency_ms": latency})
            if key_doc.get("status") == "healthy" and not res["rate_limited"]:
                await vault.set_test_result(key_doc["id"], False, res["error"])

    # ---------- valuation ----------
    async def _value(self, ex, balances):
        out = []
        for b in balances:
            price = await self._price(ex, b["asset"])
            out.append({**b, "usd_price": price,
                        "usd_value": round(b["total"] * price, 2) if price is not None else None})
        out.sort(key=lambda x: -(x["usd_value"] or 0))
        return out

    async def _price(self, ex, asset):
        asset = asset.upper()
        if asset in STABLES:
            return 1.0
        cached = self._price_cache.get(asset)
        if cached and time.monotonic() - cached[1] < PRICE_CACHE_S:
            return cached[0]
        price = self._from_collector(asset)
        if price is None:
            price = await self._from_public_ticker(ex, asset)
        self._price_cache[asset] = (price, time.monotonic())
        return price

    def _from_collector(self, asset):
        from services.collector import collector
        for exmap in collector.cache.values():
            for entry in exmap.values():
                if not isinstance(entry, dict):
                    continue
                t = entry.get("ticker")
                if (isinstance(t, dict) and str(t.get("base", "")).upper() == asset
                        and str(t.get("quote", "")).upper() in STABLES and t.get("last")):
                    return float(t["last"])
        return None

    async def _from_public_ticker(self, ex, asset):
        try:
            conn = registry.resolve(ex, "live")
            t = await conn.get_ticker(asset, "USDT")
            return float(t.last) if t and t.last else None
        except Exception:
            return None

    # ---------- views ----------
    def _sanitize(self, st):
        out = {k: v for k, v in st.items() if k not in ("backoff_until",)}
        if st.get("backoff_until"):
            out["backoff_remaining_s"] = max(0, round(st["backoff_until"] - time.monotonic()))
        return out

    def status_full(self):
        exchanges = {ex: self._sanitize(st) for ex, st in self.state.items()}
        totals = [st.get("total_usd") for st in self.state.values()
                  if st.get("total_usd") is not None]
        return {"polling": {"interval_s": POLL_S, "running": self._running,
                            "last_cycle_at": self.last_cycle_at},
                "total_usd": round(sum(totals), 2) if totals else None,
                "exchanges": exchanges}

    def get_free(self, ex, asset):
        st = self.state.get(ex)
        if not st or st.get("status") == "no_key":
            return None
        if st.get("status") != "ok" and not st.get("balances"):
            return None
        for b in st.get("balances", []):
            if b["asset"] == asset.upper():
                return b["free"]
        return 0.0

    def has_key(self, ex):
        return (self.state.get(ex) or {}).get("status") not in (None, "no_key")

    def totals(self):
        return {ex: st.get("total_usd") for ex, st in self.state.items()}


balance_service = BalanceService()
