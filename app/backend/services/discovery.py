"""Exchange Discovery Service v1 — dual source:
1. Connector scan: every live connector probed for the asset (detects listings on covered venues).
2. CoinGecko aggregator scan: discovers venues we have NO connector for.
Findings persisted to `discoveries`; deltas vs previous scan emitted as events.
CoinGecko throttling/unavailability degrades gracefully to connector-only scanning.
"""
import httpx

from core import registry
from core.errors import ConnectorError, SymbolNotListed
from core.models import new_id, now_iso
from services import db

CG_BASE = "https://api.coingecko.com/api/v3"

# CoinGecko exchange identifier -> ArbiCore connector key
CG_ID_MAP = {
    "xt": "xt", "bitmart": "bitmart", "mxc": "mexc", "mexc": "mexc", "gate": "gate",
    "coinstore": "coinstore", "bitmax": "ascendex", "ascendex": "ascendex",
    "lbank": "lbank", "pionex": "pionex", "kucoin": "kucoin", "binance": "binance",
    "bybit_spot": "bybit", "bitget": "bitget", "biconomy": "biconomy",
}


async def _connector_scan(asset: str, quote: str) -> list:
    venues = []
    for desc in registry.available():
        if not desc.get("live"):
            continue
        conn = registry.resolve(desc["key"], "live")
        entry = {"source": "connector", "key": desc["key"], "name": desc["name"],
                 "connector_known": True, "connector_live": True}
        try:
            t = await conn.get_ticker(asset, quote)
            entry.update(listed=True, pair=f"{asset}/{quote}", last=t.last,
                         volume_24h_quote=t.volume_24h_quote)
        except SymbolNotListed:
            entry.update(listed=False)
        except (ConnectorError, Exception) as e:
            entry.update(listed=None, error=str(e)[:120])
        venues.append(entry)
    return venues


async def _coingecko_scan(asset: str) -> dict:
    known_keys = {d["key"] for d in registry.available()}
    out = {"status": "ok", "venues": []}
    try:
        async with httpx.AsyncClient(timeout=15) as cl:
            resp = await cl.get(f"{CG_BASE}/search", params={"query": asset})
            if resp.status_code == 429 or "throttled" in resp.text.lower():
                return {"status": "throttled", "venues": []}
            coins = resp.json().get("coins", [])
            coin = next((c for c in coins if c.get("symbol", "").upper() == asset.upper()), None)
            if not coin:
                return {"status": "asset_not_found", "venues": []}
            resp2 = await cl.get(f"{CG_BASE}/coins/{coin['id']}/tickers")
            if resp2.status_code == 429 or "throttled" in resp2.text.lower():
                return {"status": "throttled", "venues": []}
            for t in resp2.json().get("tickers", []):
                ident = (t.get("market") or {}).get("identifier", "")
                key = CG_ID_MAP.get(ident)
                out["venues"].append({
                    "source": "coingecko",
                    "key": key or ident,
                    "name": (t.get("market") or {}).get("name", ident),
                    "pair": f"{t.get('base')}/{t.get('target')}",
                    "listed": True,
                    "last": t.get("last"),
                    "volume_24h_quote": t.get("converted_volume", {}).get("usd"),
                    "trust_score": t.get("trust_score"),
                    "connector_known": (key in known_keys) if key else False,
                    "connector_live": False,
                })
    except Exception as e:
        return {"status": f"error: {str(e)[:100]}", "venues": []}
    return out


async def scan(asset: str = "BDAG", quote: str = "USDT", emit=None) -> dict:
    connector_venues = await _connector_scan(asset, quote)
    cg = await _coingecko_scan(asset)

    prev = await db.discoveries_col.find_one({"asset": asset}, {"_id": 0}, sort=[("ts", -1)])
    prev_listed = set()
    if prev:
        prev_listed = {v["key"] for v in prev.get("venues", []) if v.get("listed")}

    all_venues = connector_venues + cg["venues"]
    findings = []
    for v in all_venues:
        if v.get("listed") and v["key"] not in prev_listed and prev is not None:
            kind = "LISTING_DETECTED" if v.get("connector_known") else "VENUE_DISCOVERED"
            findings.append({"type": kind, "venue": v["key"], "name": v.get("name"), "pair": v.get("pair")})

    doc = {
        "id": new_id(), "asset": asset, "quote": quote, "ts": now_iso(), "created_at": now_iso(),
        "sources": {"connectors": "ok", "coingecko": cg["status"]},
        "venues": all_venues, "new_findings": findings,
    }
    await db.discoveries_col.insert_one(dict(doc))
    if emit:
        for f in findings:
            await emit("warn", "discovery", f"{f['type']}: {f['name']} ({f.get('pair')})")
        if cg["status"] != "ok":
            await emit("info", "discovery", f"CoinGecko source degraded: {cg['status']} (connector scan still active)")
    doc.pop("_id", None)
    return doc
