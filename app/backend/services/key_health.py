"""Key health testing — READ-ONLY signed probes per exchange.
Each test makes a single balance/account read to verify the key works.
Never trades, never withdraws, never moves funds."""
import hashlib
import hmac
import time

import httpx

TIMEOUT = 12.0


async def _request(method, url, headers=None, params=None, content=None):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.request(method, url, headers=headers, params=params, content=content)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, {"raw": resp.text[:200]}


async def test_xt(api_key, api_secret, _passphrase=None):
    ts = str(int(time.time() * 1000))
    header_part = ("xt-validate-algorithms=HmacSHA256"
                   f"&xt-validate-appkey={api_key}&xt-validate-recvwindow=5000&xt-validate-timestamp={ts}")
    sig = hmac.new(api_secret.encode(), (header_part + "#GET#/v4/balances").encode(), hashlib.sha256).hexdigest()
    headers = {"xt-validate-algorithms": "HmacSHA256", "xt-validate-appkey": api_key,
               "xt-validate-recvwindow": "5000", "xt-validate-timestamp": ts,
               "xt-validate-signature": sig, "Content-Type": "application/json"}
    status, data = await _request("GET", "https://sapi.xt.com/v4/balances", headers=headers)
    if status == 200 and isinstance(data, dict) and data.get("rc") == 0:
        return True, "Key OK — balances readable"
    detail = data.get("mc") if isinstance(data, dict) else data
    return False, f"HTTP {status}: {str(detail)[:140]}"


async def test_mexc(api_key, api_secret, _passphrase=None):
    ts = str(int(time.time() * 1000))
    qs = f"recvWindow=5000&timestamp={ts}"
    sig = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    status, data = await _request("GET", f"https://api.mexc.com/api/v3/account?{qs}&signature={sig}",
                                  headers={"X-MEXC-APIKEY": api_key})
    if status == 200 and isinstance(data, dict) and "balances" in data:
        return True, "Key OK — account readable"
    detail = data.get("msg") if isinstance(data, dict) else data
    return False, f"HTTP {status}: {str(detail)[:140]}"


async def test_gate(api_key, api_secret, _passphrase=None):
    ts = str(int(time.time()))
    path = "/api/v4/spot/accounts"
    body_hash = hashlib.sha512(b"").hexdigest()
    sign_str = f"GET\n{path}\n\n{body_hash}\n{ts}"
    sig = hmac.new(api_secret.encode(), sign_str.encode(), hashlib.sha512).hexdigest()
    headers = {"KEY": api_key, "Timestamp": ts, "SIGN": sig, "Accept": "application/json"}
    status, data = await _request("GET", f"https://api.gateio.ws{path}", headers=headers)
    if status == 200 and isinstance(data, list):
        return True, f"Key OK — {len(data)} balances readable"
    detail = data.get("message") if isinstance(data, dict) else data
    return False, f"HTTP {status}: {str(detail)[:140]}"


async def test_bitmart(api_key, api_secret, memo=None):
    # KEYED level: validates the access key itself
    status, data = await _request("GET", "https://api-cloud.bitmart.com/account/v1/wallet",
                                  headers={"X-BM-KEY": api_key})
    if not (status == 200 and isinstance(data, dict) and data.get("code") == 1000):
        detail = data.get("message") if isinstance(data, dict) else data
        return False, f"HTTP {status}: {str(detail)[:140]}"
    if not (api_secret and memo):
        return True, "Key OK (KEYED check) — add the API memo to verify the signature too"
    # SIGNED level: validates secret + memo via a read-only order query
    ts = str(int(time.time() * 1000))
    body = "{}"
    sig = hmac.new(api_secret.encode(), f"{ts}#{memo}#{body}".encode(), hashlib.sha256).hexdigest()
    status2, data2 = await _request("POST", "https://api-cloud.bitmart.com/spot/v4/query/open-orders",
                                    headers={"X-BM-KEY": api_key, "X-BM-SIGN": sig,
                                             "X-BM-TIMESTAMP": ts, "Content-Type": "application/json"},
                                    content=body)
    if status2 == 200 and isinstance(data2, dict) and data2.get("code") == 1000:
        return True, "Key OK — KEYED + SIGNED checks passed"
    detail = data2.get("message") if isinstance(data2, dict) else data2
    return False, f"KEYED ok but SIGNED failed — HTTP {status2}: {str(detail)[:120]}"


async def test_coinstore(api_key, api_secret, _passphrase=None):
    expires = int(time.time() * 1000)
    key_hash = hmac.new(api_secret.encode(), str(expires // 30000).encode(), hashlib.sha256).hexdigest()
    payload = "{}"
    sig = hmac.new(key_hash.encode(), payload.encode(), hashlib.sha256).hexdigest()
    headers = {"X-CS-APIKEY": api_key, "X-CS-SIGN": sig, "X-CS-EXPIRES": str(expires),
               "Content-Type": "application/json"}
    status, data = await _request("POST", "https://api.coinstore.com/api/spot/accountList",
                                  headers=headers, content=payload)
    if status == 200 and isinstance(data, dict) and str(data.get("code")) == "0":
        return True, "Key OK — account list readable"
    detail = data.get("message") if isinstance(data, dict) else data
    return False, f"HTTP {status}: {str(detail)[:140]}"


TESTS = {"xt": test_xt, "mexc": test_mexc, "gate": test_gate,
         "bitmart": test_bitmart, "coinstore": test_coinstore}


async def run_test(exchange, api_key, api_secret, passphrase=None):
    fn = TESTS.get(exchange)
    if not fn:
        return {"ok": False, "message": f"No health test implemented for {exchange}"}
    try:
        ok, message = await fn(api_key, api_secret, passphrase)
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"network error: {str(e)[:140]}"}
    return {"ok": ok, "message": message}
