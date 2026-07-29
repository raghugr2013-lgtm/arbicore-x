"""Venue Monitoring Layer — lightweight, public-only connectors.

Each function returns a normalised dict; all venues use the same shape so the
scorer + runner are venue-agnostic. ALL endpoints below are PUBLIC. No keys.

Shape:
    {
      "exchange": str,
      "symbol": str,                # canonical for the venue
      "ok": bool,                   # at least ticker or depth succeeded
      "latency_ms": float,
      "ticker": {                   # may be None on failure
        "last": float, "bid": float|None, "ask": float|None,
        "volume_24h_base": float|None, "volume_24h_quote_usd": float|None,
      } | None,
      "depth": {                    # may be None on failure
        "bids": [[price, qty], ...],
        "asks": [[price, qty], ...],
        "best_bid": float|None, "best_ask": float|None,
      } | None,
      "status": {
        "deposit_enabled": bool|None,
        "withdraw_enabled_usdt": bool|None,
        "trading_active": bool|None,
      },
      "errors": [str],
    }
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx


def _empty(exchange: str, symbol: str) -> dict[str, Any]:
    return {
        "exchange": exchange,
        "symbol": symbol,
        "ok": False,
        "latency_ms": None,
        "ticker": None,
        "depth": None,
        "status": {"deposit_enabled": None, "withdraw_enabled_usdt": None, "trading_active": None},
        "errors": [],
    }


def _derive_top(depth: dict[str, list]) -> dict:
    bids = depth.get("bids") or []
    asks = depth.get("asks") or []
    return {
        "bids": bids,
        "asks": asks,
        "best_bid": float(bids[0][0]) if bids else None,
        "best_ask": float(asks[0][0]) if asks else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COINSTORE — already integrated heavily elsewhere; replicate here in the
# venue-monitor-friendly shape for parity with the other 4 venues.
# ─────────────────────────────────────────────────────────────────────────────
async def fetch_coinstore(client: httpx.AsyncClient, base: str = "BDAG", quote: str = "USDT") -> dict:
    symbol = f"{base}{quote}"
    out = _empty("coinstore", symbol)
    t0 = time.monotonic()
    try:
        r = await client.get(f"https://api.coinstore.com/api/v1/market/depth/{symbol}", params={"depth": 50})
        if r.status_code == 200:
            j = r.json()
            data = j.get("data") or j
            bids = [[float(b[0]), float(b[1])] for b in (data.get("b") or data.get("bids") or [])]
            asks = [[float(b[0]), float(b[1])] for b in (data.get("a") or data.get("asks") or [])]
            out["depth"] = _derive_top({"bids": bids, "asks": asks})
        else:
            out["errors"].append(f"depth http {r.status_code}")
    except Exception as e:
        out["errors"].append(f"depth: {e!r}")
    try:
        r = await client.get("https://api.coinstore.com/api/v1/market/tickers")
        if r.status_code == 200:
            j = r.json()
            data = j.get("data") if isinstance(j, dict) else j
            # data may itself be a list OR {"items": [...]}
            rows = data if isinstance(data, list) else ((data or {}).get("items") or [])
            row = next((x for x in rows if (x.get("symbol") or x.get("s") or "").upper() == symbol), None)
            if row:
                out["ticker"] = {
                    "last": float(row.get("close") or row.get("c") or 0) or None,
                    "bid": float(row.get("bid") or row.get("bidPrice") or 0) or None,
                    "ask": float(row.get("ask") or row.get("askPrice") or 0) or None,
                    "volume_24h_base": float(row.get("volume") or row.get("v") or 0) or None,
                    "volume_24h_quote_usd": float(row.get("amount") or row.get("qv") or 0) or None,
                }
    except Exception as e:
        out["errors"].append(f"ticker: {e!r}")
    # Status endpoint — Coinstore exposes /api/v2/public/config/spot/symbols
    try:
        r = await client.get("https://api.coinstore.com/api/v2/public/config/spot/symbols")
        if r.status_code == 200:
            j = r.json()
            rows = j.get("data") or []
            row = next((x for x in rows if (x.get("symbolCode") or "").upper() == symbol), None)
            if row:
                out["status"]["trading_active"] = bool(row.get("openTrade", True))
        # Coinstore doesn't expose per-asset deposit/withdraw flags publicly without auth.
        # We leave deposit_enabled/withdraw_enabled_usdt as None — operator manual flag fills it.
    except Exception as e:
        out["errors"].append(f"status: {e!r}")
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    out["ok"] = bool(out["ticker"] or out["depth"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# AZBIT — data.azbit.com
# ─────────────────────────────────────────────────────────────────────────────
async def fetch_azbit(client: httpx.AsyncClient, base: str = "BDAG", quote: str = "USDT") -> dict:
    pair = f"{base}_{quote}"
    out = _empty("azbit", pair)
    t0 = time.monotonic()
    try:
        r = await client.get("https://data.azbit.com/api/orderbook", params={"currencyPairCode": pair})
        if r.status_code == 200:
            j = r.json()
            # Azbit returns a flat list [{isBid:bool, price, amount}, ...]
            entries = j if isinstance(j, list) else (j.get("data") or j.get("orders") or [])
            bids = sorted(([float(b.get("price")), float(b.get("amount"))]
                           for b in entries if b.get("isBid") is True), key=lambda r: -r[0])
            asks = sorted(([float(b.get("price")), float(b.get("amount"))]
                           for b in entries if b.get("isBid") is False), key=lambda r: r[0])
            out["depth"] = _derive_top({"bids": bids, "asks": asks})
        else:
            out["errors"].append(f"depth http {r.status_code}")
    except Exception as e:
        out["errors"].append(f"depth: {e!r}")
    try:
        r = await client.get("https://data.azbit.com/api/tickers")
        if r.status_code == 200:
            j = r.json()
            rows = j if isinstance(j, list) else (j.get("data") or [])
            row = next((x for x in rows if (x.get("currencyPairCode") or "").upper() == pair), None)
            if row:
                out["ticker"] = {
                    "last": float(row.get("lastPrice") or row.get("last") or 0) or None,
                    "bid": float(row.get("bid") or 0) or None,
                    "ask": float(row.get("ask") or 0) or None,
                    "volume_24h_base": float(row.get("volume24h") or row.get("volume") or 0) or None,
                    "volume_24h_quote_usd": float(row.get("quoteVolume24h") or 0) or None,
                }
    except Exception as e:
        out["errors"].append(f"ticker: {e!r}")
    try:
        r = await client.get("https://data.azbit.com/api/currencies/pairs")
        if r.status_code == 200:
            j = r.json()
            rows = j if isinstance(j, list) else (j.get("data") or [])
            row = next((x for x in rows if isinstance(x, dict)
                        and (x.get("code") or x.get("currencyPairCode") or "").upper() == pair), None)
            # Presence of the pair in the list = trading active. Azbit does not
            # expose per-currency deposit/withdraw flags on its public API.
            if row:
                out["status"]["trading_active"] = True
        # deposit_enabled / withdraw_enabled_usdt stay None — operator manual flag fills them.
    except Exception as e:
        out["errors"].append(f"status: {e!r}")
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    out["ok"] = bool(out["ticker"] or out["depth"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# P2B (p2pb2b) — api.p2pb2b.com
# ─────────────────────────────────────────────────────────────────────────────
async def fetch_p2b(client: httpx.AsyncClient, base: str = "BDAG", quote: str = "USDT") -> dict:
    market = f"{base}_{quote}"
    out = _empty("p2b", market)
    t0 = time.monotonic()
    try:
        r = await client.get("https://api.p2pb2b.com/api/v2/public/depth/result",
                             params={"market": market, "limit": 100})
        if r.status_code == 200:
            j = r.json()
            res = j.get("result") or j
            bids = [[float(b[0]), float(b[1])] for b in (res.get("bids") or [])]
            asks = [[float(b[0]), float(b[1])] for b in (res.get("asks") or [])]
            out["depth"] = _derive_top({"bids": bids, "asks": asks})
        else:
            out["errors"].append(f"depth http {r.status_code}")
    except Exception as e:
        out["errors"].append(f"depth: {e!r}")
    try:
        r = await client.get("https://api.p2pb2b.com/api/v2/public/ticker", params={"market": market})
        if r.status_code == 200:
            j = r.json()
            res = j.get("result") or {}
            out["ticker"] = {
                "last": float(res.get("last") or 0) or None,
                "bid": float(res.get("bid") or 0) or None,
                "ask": float(res.get("ask") or 0) or None,
                "volume_24h_base": float(res.get("volume") or 0) or None,
                "volume_24h_quote_usd": float(res.get("deal") or 0) or None,
            }
    except Exception as e:
        out["errors"].append(f"ticker: {e!r}")
    try:
        r = await client.get("https://api.p2pb2b.com/api/v2/public/markets")
        if r.status_code == 200:
            j = r.json()
            rows = j.get("result") or []
            row = next((x for x in rows if (x.get("name") or "").upper() == market), None)
            if row:
                out["status"]["trading_active"] = True  # listed means enabled in P2B's public surface
        r2 = await client.get("https://api.p2pb2b.com/api/v2/public/currency")
        if r2.status_code == 200:
            j2 = r2.json()
            rows = j2.get("result") or []
            bdag = next((x for x in rows if (x.get("name") or x.get("symbol") or "").upper() == base), None)
            usdt = next((x for x in rows if (x.get("name") or x.get("symbol") or "").upper() == quote), None)
            if bdag:
                out["status"]["deposit_enabled"] = bool(bdag.get("can_deposit", bdag.get("depositEnabled", True)))
            if usdt:
                out["status"]["withdraw_enabled_usdt"] = bool(usdt.get("can_withdraw", usdt.get("withdrawEnabled", True)))
        # If the currency endpoint is empty (P2B's currency catalog is currently
        # unpopulated on the public side), flags stay None — operator-verified.
    except Exception as e:
        out["errors"].append(f"status: {e!r}")
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    out["ok"] = bool(out["ticker"] or out["depth"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# PIONEX — api.pionex.com
# ─────────────────────────────────────────────────────────────────────────────
async def fetch_pionex(client: httpx.AsyncClient, base: str = "BDAG", quote: str = "USDT") -> dict:
    symbol = f"{base}_{quote}"
    out = _empty("pionex", symbol)
    t0 = time.monotonic()
    try:
        r = await client.get("https://api.pionex.com/api/v1/market/depth",
                             params={"symbol": symbol, "limit": 50})
        if r.status_code == 200:
            j = r.json()
            data = j.get("data") or j
            bids = [[float(b[0]), float(b[1])] for b in (data.get("bids") or [])]
            asks = [[float(b[0]), float(b[1])] for b in (data.get("asks") or [])]
            out["depth"] = _derive_top({"bids": bids, "asks": asks})
        else:
            out["errors"].append(f"depth http {r.status_code}")
    except Exception as e:
        out["errors"].append(f"depth: {e!r}")
    try:
        r = await client.get("https://api.pionex.com/api/v1/market/tickers", params={"symbol": symbol})
        if r.status_code == 200:
            j = r.json()
            rows = (j.get("data") or {}).get("tickers") or j.get("data") or []
            row = next((x for x in rows if (x.get("symbol") or "").upper() == symbol), None)
            if row:
                out["ticker"] = {
                    "last": float(row.get("close") or row.get("last") or 0) or None,
                    "bid": None, "ask": None,
                    "volume_24h_base": float(row.get("volume") or 0) or None,
                    "volume_24h_quote_usd": float(row.get("amount") or 0) or None,
                }
        r2 = await client.get("https://api.pionex.com/api/v1/market/bookTickers", params={"symbol": symbol})
        if r2.status_code == 200:
            j2 = r2.json()
            rows = (j2.get("data") or {}).get("tickers") or j2.get("data") or []
            row = next((x for x in rows if (x.get("symbol") or "").upper() == symbol), None)
            if row and out["ticker"]:
                out["ticker"]["bid"] = float(row.get("bidPrice") or 0) or None
                out["ticker"]["ask"] = float(row.get("askPrice") or 0) or None
    except Exception as e:
        out["errors"].append(f"ticker: {e!r}")
    try:
        r = await client.get("https://api.pionex.com/api/v1/common/symbols")
        if r.status_code == 200:
            j = r.json()
            rows = (j.get("data") or {}).get("symbols") or j.get("data") or []
            row = next((x for x in rows if (x.get("symbol") or "").upper() == symbol), None)
            if row:
                out["status"]["trading_active"] = bool(row.get("enable", row.get("isOpen", True)))
        # Pionex public API does NOT expose a per-coin deposit/withdraw flag
        # (the older /common/currencies endpoint returns 404). Flags remain
        # None — operator-verified.
    except Exception as e:
        out["errors"].append(f"status: {e!r}")
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    out["ok"] = bool(out["ticker"] or out["depth"])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# XT — sapi.xt.com (public-only path; never use the signed client here)
# ─────────────────────────────────────────────────────────────────────────────
async def fetch_xt(client: httpx.AsyncClient, base: str = "BDAG", quote: str = "USDT") -> dict:
    symbol = f"{base.lower()}_{quote.lower()}"
    out = _empty("xt", symbol)
    t0 = time.monotonic()
    try:
        r = await client.get("https://sapi.xt.com/v4/public/depth",
                             params={"symbol": symbol, "limit": 50})
        if r.status_code == 200:
            j = r.json()
            if j.get("rc") == 0:
                data = j.get("result") or {}
                bids = [[float(b[0]), float(b[1])] for b in (data.get("bids") or [])]
                asks = [[float(b[0]), float(b[1])] for b in (data.get("asks") or [])]
                out["depth"] = _derive_top({"bids": bids, "asks": asks})
            else:
                out["errors"].append(f"depth rc {j.get('rc')} mc={j.get('mc')}")
        else:
            out["errors"].append(f"depth http {r.status_code}")
    except Exception as e:
        out["errors"].append(f"depth: {e!r}")
    try:
        r = await client.get("https://sapi.xt.com/v4/public/ticker/24h", params={"symbol": symbol})
        if r.status_code == 200:
            j = r.json()
            if j.get("rc") == 0:
                rows = j.get("result") or []
                row = rows[0] if rows else None
                if row:
                    out["ticker"] = {
                        "last": float(row.get("c") or 0) or None,
                        "bid": float(row.get("bp") or 0) or None,
                        "ask": float(row.get("ap") or 0) or None,
                        "volume_24h_base": float(row.get("q") or 0) or None,
                        "volume_24h_quote_usd": float(row.get("v") or 0) or None,
                    }
    except Exception as e:
        out["errors"].append(f"ticker: {e!r}")
    try:
        r = await client.get("https://sapi.xt.com/v4/public/symbol", params={"symbol": symbol})
        if r.status_code == 200:
            j = r.json()
            if j.get("rc") == 0:
                rows = (j.get("result") or {}).get("symbols") or []
                row = next((x for x in rows if (x.get("symbol") or "").lower() == symbol), None)
                if row:
                    out["status"]["trading_active"] = bool(row.get("tradingEnabled", True))
        # Currency-level deposit/withdraw flags via wallet endpoint
        r2 = await client.get("https://sapi.xt.com/v4/public/wallet/support/currency")
        if r2.status_code == 200:
            j2 = r2.json()
            if j2.get("rc") == 0:
                rows = j2.get("result") or []
                bdag = next((x for x in rows if (x.get("currency") or "").lower() == base.lower()), None)
                usdt = next((x for x in rows if (x.get("currency") or "").lower() == quote.lower()), None)
                if bdag:
                    out["status"]["deposit_enabled"] = bool(bdag.get("depositEnabled", True))
                if usdt:
                    out["status"]["withdraw_enabled_usdt"] = bool(usdt.get("withdrawEnabled", True))
    except Exception as e:
        out["errors"].append(f"status: {e!r}")
    out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
    out["ok"] = bool(out["ticker"] or out["depth"])
    return out


VENUE_FETCHERS = {
    "coinstore": fetch_coinstore,
    "azbit": fetch_azbit,
    "p2b": fetch_p2b,
    "pionex": fetch_pionex,
    "xt": fetch_xt,
}


async def fetch_all(timeout_s: float = 8.0) -> list[dict]:
    """Fetch all 5 venues in parallel. Never raises — failures surface in `errors`."""
    async with httpx.AsyncClient(timeout=timeout_s,
                                 headers={"User-Agent": "ArbiCore-VenueMonitor/1.0"}) as client:
        results = await asyncio.gather(
            *(fn(client) for fn in VENUE_FETCHERS.values()),
            return_exceptions=True,
        )
    out = []
    for ex, res in zip(VENUE_FETCHERS.keys(), results):
        if isinstance(res, Exception):
            empty = _empty(ex, "BDAG_USDT")
            empty["errors"].append(f"fetch_all: {res!r}")
            out.append(empty)
        else:
            out.append(res)
    return out
