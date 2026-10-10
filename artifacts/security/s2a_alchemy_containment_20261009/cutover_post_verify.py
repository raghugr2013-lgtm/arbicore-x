import asyncio, hashlib, json, os, re, urllib.parse, httpx

EXPECTED_NEW = None  # filled from mongo
FALLBACKS = ["e315c86f", "dc432a6b", "6e67e161", "cd505118", "124bc59c"]
HOST = {
    "ethereum": "eth-mainnet.g.alchemy.com",
    "arbitrum": "arb-mainnet.g.alchemy.com",
    "base": "base-mainnet.g.alchemy.com",
    "optimism": "opt-mainnet.g.alchemy.com",
    "polygon": "polygon-mainnet.g.alchemy.com",
    "bnb": "bnb-mainnet.g.alchemy.com",
}

def fp8(t): return hashlib.sha256(t.encode()).hexdigest()[:8]

def url_meta(u):
    p = urllib.parse.urlparse(u)
    m = re.match(r"^/(v2|v3)/([^/]+)", p.path or "")
    return {"host": p.hostname, "fp8": fp8(m.group(2)) if m else None, "url": u}

async def eth_block(url):
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(url, json={"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]})
            return {"http_status": r.status_code, "ok": r.status_code==200 and "result" in r.json(), "body_has_error": "error" in (r.json() if r.headers.get("content-type","").startswith("application/json") else {})}
    except Exception as e:
        return {"http_status": None, "ok": False, "error": type(e).__name__}

async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)["arbicore_x"]
    doc = await db.arbicore_config.find_one({"_id":"network"})
    rpc = doc["rpc_urls"]
    chains = {}
    primary_fps = set()
    for chain, expect_host in HOST.items():
        arr = rpc[chain]
        metas = [url_meta(u) for u in arr]
        # strip urls from output
        slots = [{"index":i, "host":m["host"], "fp8":m["fp8"]} for i,m in enumerate(metas)]
        primary_fps.add(metas[0]["fp8"])
        assert metas[0]["host"]==expect_host
        assert metas[0]["fp8"] != "24dab5d1"
        for i,m in enumerate(metas[1:],1):
            assert m["fp8"]==FALLBACKS[i-1], (chain,i,m["fp8"])
            assert m["host"]==expect_host
        health = await eth_block(arr[0])
        # fallback probe index 1 only (safe read)
        fb_health = await eth_block(arr[1])
        chains[chain] = {
            "slots": slots,
            "primary_health": {k:v for k,v in health.items()},
            "fallback1_health": {k:v for k,v in fb_health.items()},
        }
    out = {
        "revision_id": doc.get("revision_id"),
        "updated_by": doc.get("updated_by"),
        "updated_at": str(doc.get("updated_at")),
        "distinct_primary_fps": sorted(primary_fps),
        "primary_not_old_24dab5d1": all(f != "24dab5d1" for f in primary_fps),
        "fallbacks_preserved": True,
        "chains": chains,
    }
    print(json.dumps(out))

asyncio.run(main())
