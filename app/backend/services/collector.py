"""Collector service — per-route async polling loops (ticker/depth/candles/fees/RPC),
normalized snapshot persistence, staleness tracking, and evaluation triggering.
One exchange failing never affects the others.
"""
import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone


def datetime_diff_h(ts_iso: str) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(ts_iso)).total_seconds() / 3600
    except ValueError:
        return 1e9


from connectors import sim as sim_module
from connectors.evm_wallet import EVMWatchConnector
from core import registry
from core.errors import ConnectorError, SymbolNotListed
from core.models import new_id, now_iso
from engines import pipeline
from services import capability, db, discovery, holdprob
from services.execution import buy_price
from services.observation import observation
from services.portal_price import portal_price
from services.telegram_alerts import telegram_alerts
from services.ws_manager import ws_manager

logger = logging.getLogger("collector")

TICKER_S, DEPTH_S, CANDLE_S, FEE_S, RPC_S = 5, 10, 60, 120, 60
HOLDPROB_S, DISCOVERY_S = 120, 6 * 3600
PERSIST_TICKER_EVERY_S = 30


class CollectorService:
    def __init__(self):
        self.cache = {}            # route_id -> {exchange -> {ticker, orderbook, fee, candles, listed, last_error}}
        self.network_health = {}   # network_key -> {healthy, block_number, ...}
        self.events = deque(maxlen=80)
        self.tasks = {}            # route_id -> [asyncio.Task]
        self.wallet = EVMWatchConnector()
        self._last_ticker_persist = {}
        self._has_transfer_history = {}
        self._running = False

    # ---------- lifecycle ----------
    async def start(self):
        self._running = True
        await ws_manager.start()
        routes = await db.routes_col.find({"active": True}, {"_id": 0}).to_list(50)
        for r in routes:
            self._start_route(r)
        self.tasks["_rpc"] = [asyncio.create_task(self._rpc_loop())]
        await self.event("info", "collector", "Collector started", route_id=None)

    async def stop(self):
        self._running = False
        for tasks in self.tasks.values():
            for t in tasks:
                t.cancel()
        await ws_manager.stop()
        await self.wallet.close()

    def _start_route(self, route):
        rid = route["id"]
        self.cache.setdefault(rid, {})
        base, quote = route["exit"]["base"], route["exit"]["quote"]
        for ex in (route.get("comparison_exchanges") or [route["exit"]["exchange"]]):
            ws_manager.ensure(ex, base, quote)  # no-op for non-WS exchanges
        self.tasks[rid] = [
            asyncio.create_task(self._loop(rid, "ticker", TICKER_S)),
            asyncio.create_task(self._loop(rid, "depth", DEPTH_S)),
            asyncio.create_task(self._loop(rid, "candles", CANDLE_S)),
            asyncio.create_task(self._loop(rid, "fees", FEE_S)),
            asyncio.create_task(self._holdprob_loop(rid)),
            asyncio.create_task(self._discovery_loop(rid)),
        ]

    async def reload_route(self, route_id):
        for t in self.tasks.get(route_id, []):
            t.cancel()
        self.cache[route_id] = {}
        route = await db.routes_col.find_one({"id": route_id, "active": True}, {"_id": 0})
        if route:
            self._start_route(route)
            await self.event("info", "collector", f"Route reloaded (mode={route.get('mode')})", route_id=route_id)

    # ---------- events ----------
    async def event(self, level, source, message, route_id=None):
        evt = {"id": new_id(), "ts": now_iso(), "created_at": now_iso(),
               "level": level, "source": source, "message": message, "route_id": route_id}
        self.events.appendleft({k: evt[k] for k in ("ts", "level", "source", "message")})
        try:
            await db.events_col.insert_one(evt)
        except Exception:
            pass

    # ---------- main loops ----------
    async def _loop(self, route_id, kind, interval):
        backoff = 0
        while self._running:
            try:
                route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
                if not route or not route.get("active"):
                    await asyncio.sleep(interval)
                    continue
                if route.get("mode") == "simulation":
                    sim_module.set_scenario(route.get("sim_config"))
                await self._collect(route, kind)
                if kind == "depth":
                    await self._evaluate(route)
                backoff = 0
            except asyncio.CancelledError:
                return
            except Exception as e:
                backoff = min(backoff + 1, 4)
                logger.warning("loop %s/%s error: %s", route_id[:8], kind, e)
                await self.event("error", f"collector:{kind}", str(e)[:200], route_id=route_id)
            await asyncio.sleep(interval * (2 ** backoff if backoff else 1))

    async def _collect(self, route, kind):
        rid = route["id"]
        mode = route.get("mode", "live")
        base, quote = route["exit"]["base"], route["exit"]["quote"]
        asset = route["purchase"]["asset"]
        exchanges = route.get("comparison_exchanges") or [route["exit"]["exchange"]]
        primary = route["exit"]["exchange"]

        async def one(ex_key):
            entry = self.cache[rid].setdefault(ex_key, {"listed": None})
            try:
                conn = registry.resolve(ex_key, mode)
            except KeyError:
                return
            try:
                if kind == "ticker":
                    t = (await conn.get_ticker(base, quote)).model_dump()
                    entry.update(ticker=t, listed=True, last_error=None)
                    now = time.time()
                    k = (rid, ex_key)
                    if now - self._last_ticker_persist.get(k, 0) >= PERSIST_TICKER_EVERY_S:
                        self._last_ticker_persist[k] = now
                        await db.ticker_snapshots.insert_one(
                            {**t, "id": new_id(), "route_id": rid, "created_at": now_iso()})
                elif kind == "depth":
                    ob = (await conn.get_orderbook(base, quote, 50)).model_dump()
                    entry.update(orderbook=ob, listed=True)
                    mid = None
                    if ob["bids"] and ob["asks"]:
                        mid = (ob["bids"][0][0] + ob["asks"][0][0]) / 2
                    await db.orderbook_snapshots.insert_one({
                        **ob, "id": new_id(), "route_id": rid, "created_at": now_iso(),
                        "derived": {
                            "best_bid": ob["bids"][0][0] if ob["bids"] else None,
                            "best_ask": ob["asks"][0][0] if ob["asks"] else None,
                            "mid": mid,
                            "bid_depth_quote_2pct": sum(p * q for p, q in ob["bids"]
                                                        if mid and p >= mid * 0.98) if mid else None,
                        }})
                elif kind == "candles":
                    cans = await conn.get_candles(base, quote, 5, 100)
                    entry.update(candles=[c.model_dump() for c in cans])
                    if cans:
                        latest = cans[-20:]
                        for c in latest:
                            await db.candles_col.update_one(
                                {"route_id": rid, "exchange": ex_key, "interval_min": 5, "open_time": c.open_time},
                                {"$set": {**c.model_dump(), "route_id": rid, "exchange": ex_key}},
                                upsert=True)
                elif kind == "fees":
                    fee = await conn.get_fee_info(asset)
                    prev = entry.get("fee")
                    entry["fee"] = fee.model_dump() if fee else None
                    if fee:
                        await db.fee_snapshots.insert_one(
                            {**fee.model_dump(), "id": new_id(), "route_id": rid,
                             "mode": mode, "created_at": now_iso()})
                        if mode == "live":  # capability registry reflects REALITY only
                            flips = await capability.record(ex_key, asset, fee.model_dump(), route_id=rid)
                            for fl in flips:
                                await telegram_alerts.notify(
                                    "capability_flip",
                                    f"⚙️ {ex_key.upper()} {asset}: {fl['field'].replace('_', ' ')} "
                                    f"flipped {fl['from']} → {fl['to']}")
                        if prev and prev.get("deposit_enabled") != fee.deposit_enabled:
                            await self.event("warn", f"capability:{ex_key}",
                                             f"{asset} deposit status flipped to {fee.deposit_enabled} on {ex_key}",
                                             route_id=rid)
            except SymbolNotListed as e:
                entry.update(listed=False, last_error=str(e))
            except ConnectorError as e:
                entry.update(last_error=str(e))
                if ex_key == primary:
                    await self.event("warn", f"connector:{ex_key}", str(e)[:160], route_id=rid)

        await asyncio.gather(*[one(ex) for ex in exchanges])

    async def _evaluate(self, route):
        rid = route["id"]
        primary = route["exit"]["exchange"]
        market = self.cache.get(rid, {}).get(primary)
        if not market:
            return
        # Buy-price precedence (Phase E1): active position cost basis
        # → manual override → live portal price (BDAG routes) → manual fallback.
        pos = await db.positions_col.find_one(
            {"route_id": rid, "status": {"$nin": ["SETTLED"]}}, {"_id": 0}, sort=[("created_at", -1)])
        route_eval = dict(route)
        bp = self._resolve_buy_price(route, pos)
        if bp["price"] is not None:
            route_eval["manual_buy"] = {"price": bp["price"], "qty": bp["qty"],
                                        "price_source": bp["source"]}
        net_key = route["purchase"].get("network")
        has_history = self._has_transfer_history.get(rid)
        if has_history is None:
            has_history = await db.transfers_col.count_documents({"route_id": rid, "status": "complete"}) > 0
            self._has_transfer_history[rid] = has_history
        net_health = self.network_health.get(net_key, {})
        hold_stats = self.cache[rid].get("_holdstats")

        ev = pipeline.run_evaluation(route_eval, market, net_health, has_history,
                                     hold_stats=hold_stats, connector_caps=self._caps(primary))
        ev["position_id"] = pos["id"] if pos else None

        # Venue matrix — full engine run per listed comparison venue (side-by-side spec)
        matrix = []
        for ex in route.get("comparison_exchanges", []):
            m = self.cache[rid].get(ex)
            entry = {"exchange": ex, "listed": (m or {}).get("listed")}
            if m and m.get("listed") and m.get("orderbook"):
                r2 = dict(route_eval)
                r2["exit"] = {**route["exit"], "exchange": ex}
                ev2 = ev if ex == primary else pipeline.run_evaluation(
                    r2, m, net_health, has_history, connector_caps=self._caps(ex))
                entry.update(
                    verdict=ev2["verdict"],
                    confidence=(ev2.get("confidence") or {}).get("score"),
                    net_spread_pct=ev2["spread"].get("net_pct"),
                    recommended=ev2["capacity"].get("recommended"),
                    overall=ev2["scores"].get("overall"),
                    deposit_enabled=(m.get("fee") or {}).get("deposit_enabled"),
                    source=(m.get("ticker") or {}).get("source"),
                )
            matrix.append(entry)
        ev["venue_matrix"] = matrix

        prev = self.cache[rid].get("_last_verdict")
        self.cache[rid]["_evaluation"] = ev
        self.cache[rid]["_last_verdict"] = ev["verdict"]
        await db.evaluations.insert_one({**ev, "created_at": now_iso()})
        net = ev["spread"].get("net_pct")
        if prev and prev != ev["verdict"]:
            await self.event("warn", "engine:verdict", f"Verdict flipped {prev} → {ev['verdict']}", route_id=rid)
            await telegram_alerts.notify(
                "verdict_flip",
                f"🚦 {route.get('name', rid[:8])}: verdict flipped {prev} → {ev['verdict']} "
                f"on {primary.upper()}" + (f" (net {net:+.2f}%)" if net is not None else ""))
        if ev["verdict"] == "GO" and net is not None:
            rec = ev["capacity"].get("recommended")
            await telegram_alerts.notify(
                "go_opportunity",
                f"🟢 GO on {primary.upper()} — {route.get('name', rid[:8])}: net spread {net:+.2f}%"
                + (f", recommended size {rec:,.0f}" if rec else ""),
                net_pct=net)
        await observation.on_evaluation(route, ev)

    def _caps(self, exchange_key):
        try:
            return registry.resolve(exchange_key, "live").capabilities
        except KeyError:
            return {}

    @staticmethod
    def _resolve_buy_price(route, pos):
        """Effective cost-basis price for evaluation (Phase E1 → E4.6.1).
        Delegates to the single shared resolver (services.execution.buy_price) so
        collector/evaluation, opportunity, shadow, certification, the ledger and the
        arbitrage-intel engine all resolve identically.
        Precedence: active position → manual override → live portal → manual fallback."""
        r = buy_price.resolve_sync(route, pos)
        return {"price": r["price"], "qty": r["qty"], "source": r["source"]}

    async def _holdprob_loop(self, route_id):
        await asyncio.sleep(20)
        while self._running:
            try:
                route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
                if route and route.get("active"):
                    stats = await holdprob.compute_delta_stats(
                        route_id, route["exit"]["exchange"],
                        route.get("risk_profile", {}).get("est_transfer_minutes", 30))
                    self.cache.setdefault(route_id, {})["_holdstats"] = stats
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("holdprob loop: %s", e)
            await asyncio.sleep(HOLDPROB_S)

    async def _discovery_loop(self, route_id):
        await asyncio.sleep(90)
        while self._running:
            try:
                route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
                if route and route.get("active"):
                    asset = route["purchase"]["asset"]
                    quote = route["exit"]["quote"]
                    latest = await db.discoveries_col.find_one({"asset": asset}, sort=[("ts", -1)])
                    if not latest or (now_iso() > latest["ts"] and
                                      (datetime_diff_h(latest["ts"]) >= DISCOVERY_S / 3600)):
                        await discovery.scan(asset, quote, emit=self.event)
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("discovery loop: %s", e)
            await asyncio.sleep(DISCOVERY_S)

    async def _rpc_loop(self):
        while self._running:
            try:
                networks = await db.networks_col.find({}, {"_id": 0}).to_list(20)
                for n in networks:
                    prev = self.network_health.get(n["key"], {}).get("healthy")
                    health = await self.wallet.check_rpc(n)
                    self.network_health[n["key"]] = {**health, "checked_at": now_iso()}
                    if prev is not None and prev != health["healthy"]:
                        await self.event("warn", f"rpc:{n['key']}",
                                         f"RPC health flipped to {'healthy' if health['healthy'] else 'UNHEALTHY'}")
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("rpc loop: %s", e)
            await asyncio.sleep(RPC_S)


collector = CollectorService()
