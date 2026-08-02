"""WebSocket market data manager — XT & BitMart primary feeds (Sprint 3).
REST fallback lives in the connectors: they consult ws_manager first and only
hit REST when the WS cache is missing or stale (> FRESH_TTL_S). One feed
failing never affects the other; reconnects use exponential backoff.

Verified live schemas (June 2026):
  XT      wss://stream.xt.com/public
          {"method":"subscribe","params":["ticker@bdag_usdt","depth@bdag_usdt,50"],"id":"1"}
  BitMart wss://ws-manager-compress.bitmart.com/api?protocol=1.1
          {"op":"subscribe","args":["spot/ticker:BDAG_USDT","spot/depth50:BDAG_USDT"]}
"""
import asyncio
import json
import logging
import time
import zlib

import websockets

from core.models import now_iso

logger = logging.getLogger("ws")

FRESH_TTL_S = 15
CONN_LIVE_S = 45   # connection considered alive if any frame (incl. pong) within this window
PING_EVERY_S = 20
MAX_BACKOFF_S = 60


class _Feed:
    key = ""
    url = ""
    # Both XT and BitMart public channels are push-on-change: no push means the
    # value did NOT change. While the connection is demonstrably alive, the
    # cached payload is therefore still current even past FRESH_TTL_S.
    push_on_change = True

    def __init__(self):
        self.symbols = set()   # {(BASE, QUOTE)}
        self.cache = {}        # (BASE, QUOTE) -> {ticker, ticker_at, orderbook, orderbook_at}
        self.connected = False
        self.last_msg_at = None
        self.messages = 0
        self.reconnects = 0
        self.last_error = None
        self._ws = None
        self._task = None
        self._ping_task = None

    # ---- overrides ----
    def map_symbol(self, base, quote):
        raise NotImplementedError

    def sub_messages(self, pairs):
        raise NotImplementedError

    def handle(self, raw):
        raise NotImplementedError

    # ---- lifecycle ----
    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self):
        for t in (self._task, self._ping_task):
            if t:
                t.cancel()
        self._task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    def ensure(self, base, quote):
        pair = (base.upper(), quote.upper())
        if pair in self.symbols:
            return
        self.symbols.add(pair)
        if self._ws is not None and self.connected:
            asyncio.create_task(self._send_subs([pair]))

    async def _send_subs(self, pairs):
        try:
            for msg in self.sub_messages(pairs):
                await self._ws.send(json.dumps(msg))
        except Exception as e:
            logger.warning("%s subscribe failed: %s", self.key, e)

    async def _run(self):
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20,
                                              max_size=2 ** 22) as ws:
                    self._ws = ws
                    self.connected = True
                    self.last_error = None
                    backoff = 1
                    if self.symbols:
                        await self._send_subs(list(self.symbols))
                    self._ping_task = asyncio.create_task(self._ping_loop(ws))
                    async for raw in ws:
                        self.messages += 1
                        self.last_msg_at = time.monotonic()
                        try:
                            self.handle(raw)
                        except Exception as e:
                            logger.debug("%s parse error: %s", self.key, e)
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.last_error = str(e)[:160]
                logger.warning("%s ws disconnected: %s", self.key, e)
            finally:
                self.connected = False
                self._ws = None
                if self._ping_task:
                    self._ping_task.cancel()
                    self._ping_task = None
            self.reconnects += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_S)

    async def _ping_loop(self, ws):
        try:
            while True:
                await asyncio.sleep(PING_EVERY_S)
                await ws.send("ping")
        except asyncio.CancelledError:
            return
        except Exception:
            return

    # ---- cache ----
    def _put(self, pair, kind, payload):
        entry = self.cache.setdefault(pair, {})
        entry[kind] = payload
        entry[f"{kind}_at"] = time.monotonic()

    def get(self, kind, base, quote):
        entry = self.cache.get((base.upper(), quote.upper()))
        if not entry or kind not in entry:
            return None
        if time.monotonic() - entry.get(f"{kind}_at", 0) <= FRESH_TTL_S:
            return entry[kind]
        conn_alive = (self.connected and self.last_msg_at
                      and time.monotonic() - self.last_msg_at < CONN_LIVE_S)
        if self.push_on_change and conn_alive:
            # value unchanged by definition — refresh ts to reflect "current as of now"
            return {**entry[kind], "ts": now_iso()}
        return None

    def status(self):
        age = round(time.monotonic() - self.last_msg_at, 1) if self.last_msg_at else None
        live = self.connected and age is not None and age < CONN_LIVE_S
        return {"connected": self.connected, "last_msg_age_s": age,
                "subscriptions": [f"{b}/{q}" for b, q in sorted(self.symbols)],
                "messages": self.messages, "reconnects": self.reconnects,
                "mode": "ws" if live else "rest-fallback", "last_error": self.last_error}


class XTFeed(_Feed):
    key = "xt"
    url = "wss://stream.xt.com/public"

    def map_symbol(self, base, quote):
        return f"{base.lower()}_{quote.lower()}"

    def sub_messages(self, pairs):
        params = []
        for b, q in pairs:
            s = self.map_symbol(b, q)
            params += [f"ticker@{s}", f"depth@{s},50"]
        return [{"method": "subscribe", "params": params, "id": str(int(time.time() * 1000))}]

    def _pair_for(self, sym):
        for b, q in self.symbols:
            if self.map_symbol(b, q) == sym:
                return (b, q)
        return None

    def handle(self, raw):
        if isinstance(raw, bytes):
            raw = raw.decode()
        if raw in ("ping", "pong"):
            return
        msg = json.loads(raw)
        topic, data = msg.get("topic"), msg.get("data")
        if not topic or not isinstance(data, dict):
            return
        pair = self._pair_for(data.get("s", ""))
        if not pair:
            return
        b, q = pair
        if topic == "ticker" and data.get("c") is not None:
            self._put(pair, "ticker", {
                "exchange": self.key, "base": b, "quote": q, "last": float(data["c"]),
                "open_24h": float(data["o"]) if data.get("o") else None,
                "high_24h": float(data["h"]) if data.get("h") else None,
                "low_24h": float(data["l"]) if data.get("l") else None,
                "volume_24h_base": float(data["q"]) if data.get("q") else None,
                "volume_24h_quote": float(data["v"]) if data.get("v") else None,
                "ts": now_iso(), "source": "ws"})
        elif topic == "depth":
            ob = {"exchange": self.key, "base": b, "quote": q,
                  "bids": [[float(p), float(qty)] for p, qty in (data.get("b") or [])],
                  "asks": [[float(p), float(qty)] for p, qty in (data.get("a") or [])],
                  "ts": now_iso(), "source": "ws"}
            if ob["bids"] or ob["asks"]:
                self._put(pair, "orderbook", ob)


class BitmartFeed(_Feed):
    key = "bitmart"
    url = "wss://ws-manager-compress.bitmart.com/api?protocol=1.1"

    def map_symbol(self, base, quote):
        return f"{base.upper()}_{quote.upper()}"

    def sub_messages(self, pairs):
        args = []
        for b, q in pairs:
            s = self.map_symbol(b, q)
            args += [f"spot/ticker:{s}", f"spot/depth50:{s}"]
        return [{"op": "subscribe", "args": args}]

    def handle(self, raw):
        if isinstance(raw, bytes):
            try:
                raw = zlib.decompress(raw, -15).decode()
            except Exception:
                raw = raw.decode(errors="ignore")
        if not raw or raw in ("ping", "pong"):
            return
        msg = json.loads(raw)
        table, data = msg.get("table"), msg.get("data")
        if not table or not data:
            return
        d = data[0]
        sym = d.get("symbol", "")
        if "_" not in sym:
            return
        b, q = sym.split("_", 1)
        pair = (b.upper(), q.upper())
        if pair not in self.symbols:
            return
        if table.startswith("spot/ticker") and d.get("last_price") is not None:
            self._put(pair, "ticker", {
                "exchange": self.key, "base": pair[0], "quote": pair[1],
                "last": float(d["last_price"]),
                "bid": float(d["bid_px"]) if d.get("bid_px") else None,
                "ask": float(d["ask_px"]) if d.get("ask_px") else None,
                "open_24h": float(d["open_24h"]) if d.get("open_24h") else None,
                "high_24h": float(d["high_24h"]) if d.get("high_24h") else None,
                "low_24h": float(d["low_24h"]) if d.get("low_24h") else None,
                "volume_24h_base": float(d["base_volume_24h"]) if d.get("base_volume_24h") else None,
                "volume_24h_quote": float(d["quote_volume_24h"]) if d.get("quote_volume_24h") else None,
                "ts": now_iso(), "source": "ws"})
        elif table.startswith("spot/depth"):
            ob = {"exchange": self.key, "base": pair[0], "quote": pair[1],
                  "bids": [[float(p), float(qty)] for p, qty in (d.get("bids") or [])],
                  "asks": [[float(p), float(qty)] for p, qty in (d.get("asks") or [])],
                  "ts": now_iso(), "source": "ws"}
            if ob["bids"] or ob["asks"]:
                self._put(pair, "orderbook", ob)


class WSManager:
    def __init__(self):
        self.feeds = {"xt": XTFeed(), "bitmart": BitmartFeed()}
        self._started = False

    async def start(self):
        if self._started:
            return
        self._started = True
        for f in self.feeds.values():
            f.start()
        logger.info("WS manager started (xt, bitmart)")

    async def stop(self):
        self._started = False
        for f in self.feeds.values():
            await f.stop()

    def ensure(self, exchange, base, quote):
        feed = self.feeds.get(exchange)
        if feed:
            feed.ensure(base, quote)

    def get_ticker(self, exchange, base, quote):
        feed = self.feeds.get(exchange)
        return feed.get("ticker", base, quote) if feed else None

    def get_orderbook(self, exchange, base, quote):
        feed = self.feeds.get(exchange)
        return feed.get("orderbook", base, quote) if feed else None

    def status(self):
        return {k: f.status() for k, f in self.feeds.items()}


ws_manager = WSManager()
