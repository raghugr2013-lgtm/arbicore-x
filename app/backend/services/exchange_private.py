"""READ-ONLY private balance fetchers per exchange (Sprint 4).
Single signed balance/account read per call. Never trades, never withdraws,
never moves funds — no write-capable endpoint exists in this module.
Returns {"ok", "balances": [{asset, free, locked, total}], "error", "rate_limited"}."""
import hashlib
import hmac
import time

import httpx

TIMEOUT = 12.0


async def _request(method, url, headers=None, content=None):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.request(method, url, headers=headers, content=content)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, {"raw": resp.text[:200]}


def _f(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _row(asset, free, locked):
    free, locked = _f(free), _f(locked)
    return {"asset": asset.upper(), "free": free, "locked": locked,
            "total": round(free + locked, 12)}


def _err(status, detail, rate_limited=False):
    return {"ok": False, "balances": [],
            "error": f"HTTP {status}: {str(detail)[:160]}",
            "rate_limited": rate_limited or status == 429}


def _ok(rows):
    return {"ok": True, "balances": [r for r in rows if r["total"] > 0],
            "error": None, "rate_limited": False}


async def fetch_xt(api_key, api_secret, _passphrase=None):
    ts = str(int(time.time() * 1000))
    header_part = ("xt-validate-algorithms=HmacSHA256"
                   f"&xt-validate-appkey={api_key}&xt-validate-recvwindow=5000&xt-validate-timestamp={ts}")
    sig = hmac.new(api_secret.encode(), (header_part + "#GET#/v4/balances").encode(),
                   hashlib.sha256).hexdigest()
    headers = {"xt-validate-algorithms": "HmacSHA256", "xt-validate-appkey": api_key,
               "xt-validate-recvwindow": "5000", "xt-validate-timestamp": ts,
               "xt-validate-signature": sig, "Content-Type": "application/json"}
    status, data = await _request("GET", "https://sapi.xt.com/v4/balances", headers=headers)
    if status == 200 and isinstance(data, dict) and data.get("rc") == 0:
        assets = (data.get("result") or {}).get("assets") or []
        return _ok([_row(a.get("currency", ""), a.get("availableAmount"), a.get("frozenAmount"))
                    for a in assets])
    return _err(status, (data or {}).get("mc") or data)


async def fetch_mexc(api_key, api_secret, _passphrase=None):
    ts = str(int(time.time() * 1000))
    qs = f"recvWindow=5000&timestamp={ts}"
    sig = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    status, data = await _request("GET", f"https://api.mexc.com/api/v3/account?{qs}&signature={sig}",
                                  headers={"X-MEXC-APIKEY": api_key})
    if status == 200 and isinstance(data, dict) and "balances" in data:
        return _ok([_row(b.get("asset", ""), b.get("free"), b.get("locked"))
                    for b in data["balances"]])
    return _err(status, (data or {}).get("msg") or data)


async def fetch_gate(api_key, api_secret, _passphrase=None):
    ts = str(int(time.time()))
    path = "/api/v4/spot/accounts"
    body_hash = hashlib.sha512(b"").hexdigest()
    sig = hmac.new(api_secret.encode(), f"GET\n{path}\n\n{body_hash}\n{ts}".encode(),
                   hashlib.sha512).hexdigest()
    status, data = await _request("GET", f"https://api.gateio.ws{path}",
                                  headers={"KEY": api_key, "Timestamp": ts, "SIGN": sig,
                                           "Accept": "application/json"})
    if status == 200 and isinstance(data, list):
        return _ok([_row(b.get("currency", ""), b.get("available"), b.get("locked"))
                    for b in data])
    return _err(status, data.get("message") if isinstance(data, dict) else data)


async def fetch_bitmart(api_key, _api_secret=None, _memo=None):
    # /account/v1/wallet is KEYED level — only the access key header required
    status, data = await _request("GET", "https://api-cloud.bitmart.com/account/v1/wallet",
                                  headers={"X-BM-KEY": api_key})
    if status == 200 and isinstance(data, dict) and data.get("code") == 1000:
        wallet = (data.get("data") or {}).get("wallet") or []
        return _ok([_row(b.get("currency", ""), b.get("available"), b.get("frozen"))
                    for b in wallet])
    return _err(status, (data or {}).get("message") or data)


async def fetch_coinstore(api_key, api_secret, _passphrase=None):
    expires = int(time.time() * 1000)
    key_hash = hmac.new(api_secret.encode(), str(expires // 30000).encode(),
                        hashlib.sha256).hexdigest()
    payload = "{}"
    sig = hmac.new(key_hash.encode(), payload.encode(), hashlib.sha256).hexdigest()
    status, data = await _request("POST", "https://api.coinstore.com/api/spot/accountList",
                                  headers={"X-CS-APIKEY": api_key, "X-CS-SIGN": sig,
                                           "X-CS-EXPIRES": str(expires),
                                           "Content-Type": "application/json"},
                                  content=payload)
    if status == 200 and isinstance(data, dict) and str(data.get("code")) == "0":
        agg = {}
        for r in data.get("data") or []:
            cur = str(r.get("currency", "")).upper()
            if not cur:
                continue
            slot = agg.setdefault(cur, {"free": 0.0, "locked": 0.0})
            if str(r.get("typeName", "")).upper() == "FROZEN":
                slot["locked"] += _f(r.get("balance"))
            else:
                slot["free"] += _f(r.get("balance"))
        return _ok([_row(c, v["free"], v["locked"]) for c, v in agg.items()])
    return _err(status, (data or {}).get("message") or data)


FETCHERS = {"xt": fetch_xt, "mexc": fetch_mexc, "gate": fetch_gate,
            "bitmart": fetch_bitmart, "coinstore": fetch_coinstore}


async def fetch_balances(exchange, api_key, api_secret, passphrase=None):
    fn = FETCHERS.get(exchange)
    if not fn:
        return {"ok": False, "balances": [], "error": f"no balance fetcher for {exchange}",
                "rate_limited": False}
    try:
        return await fn(api_key, api_secret, passphrase)
    except httpx.HTTPError as e:
        return {"ok": False, "balances": [], "error": f"network error: {str(e)[:140]}",
                "rate_limited": False}
