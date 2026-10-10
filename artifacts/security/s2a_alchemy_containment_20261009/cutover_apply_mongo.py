import asyncio, hashlib, json, os, re, urllib.parse, secrets
from datetime import datetime, timezone

STAGE = "/tmp/s2a_alchemy_replacements.env"
CHAIN_MAP = {
    "ethereum": "PRIMARY_ETHEREUM",
    "arbitrum": "PRIMARY_ARBITRUM",
    "base": "PRIMARY_BASE",
    "optimism": "PRIMARY_OPTIMISM",
    "polygon": "PRIMARY_POLYGON",
    "bnb": "PRIMARY_BNB",
}
HOST_EXPECT = {
    "ethereum": "eth-mainnet.g.alchemy.com",
    "arbitrum": "arb-mainnet.g.alchemy.com",
    "base": "base-mainnet.g.alchemy.com",
    "optimism": "opt-mainnet.g.alchemy.com",
    "polygon": "polygon-mainnet.g.alchemy.com",
    "bnb": "bnb-mainnet.g.alchemy.com",
}
OLD_PRIMARY = "24dab5d1"
FALLBACKS = ["e315c86f", "dc432a6b", "6e67e161", "cd505118", "124bc59c"]

def fp8(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:8]

def parse_kv(path):
    kv = {}
    for line in open(path):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        kv[k.strip()] = v.strip().strip('"').strip("'")
    return kv

def url_fp_host(u):
    p = urllib.parse.urlparse(u)
    m = re.match(r"^/(v2|v3)/([^/]+)", p.path or "")
    if not m:
        raise ValueError("bad url")
    return fp8(m.group(2)), p.hostname

async def main():
    kv = parse_kv(STAGE)
    assert kv.get("FALLBACK_POLICY") == "retain_existing"
    from motor.motor_asyncio import AsyncIOMotorClient
    uri = os.environ["MONGO_URL"]
    db = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=8000)["arbicore_x"]
    doc = await db.arbicore_config.find_one({"_id": "network"})
    assert doc and "rpc_urls" in doc
    rpc = doc["rpc_urls"]
    summary = {"before_primary": {}, "after_primary": {}, "fallbacks_unchanged": True}
    new_rpc = {}
    for chain, keyname in CHAIN_MAP.items():
        arr = list(rpc[chain])
        assert len(arr) == 6
        old_fp, old_host = url_fp_host(arr[0])
        assert old_fp == OLD_PRIMARY
        assert old_host == HOST_EXPECT[chain]
        # fallbacks
        for i, u in enumerate(arr[1:], 1):
            f, h = url_fp_host(u)
            assert f == FALLBACKS[i - 1]
            assert h == HOST_EXPECT[chain]
        new_url = kv[keyname]
        new_fp, new_host = url_fp_host(new_url)
        assert new_host == HOST_EXPECT[chain]
        assert new_fp != OLD_PRIMARY
        summary["before_primary"][chain] = {"fp8": old_fp, "host": old_host}
        summary["after_primary"][chain] = {"fp8": new_fp, "host": new_host}
        arr[0] = new_url
        # verify fallbacks still same object values
        new_rpc[chain] = arr
    # write
    rev = "rev-" + secrets.token_hex(16)
    now = datetime.now(timezone.utc).isoformat()
    res = await db.arbicore_config.update_one(
        {"_id": "network"},
        {"$set": {
            "rpc_urls": new_rpc,
            "updated_at": now,
            "updated_by": "s2a-alchemy-cutover",
            "revision_id": rev,
        }},
    )
    assert res.modified_count == 1
    # re-read verify
    doc2 = await db.arbicore_config.find_one({"_id": "network"})
    for chain in CHAIN_MAP:
        arr = doc2["rpc_urls"][chain]
        assert url_fp_host(arr[0])[0] == summary["after_primary"][chain]["fp8"]
        for i, u in enumerate(arr[1:], 1):
            assert url_fp_host(u)[0] == FALLBACKS[i - 1]
    summary["revision_id"] = rev
    summary["updated_at"] = now
    summary["fallbacks_preserved"] = True
    # do not include urls
    print(json.dumps(summary))

asyncio.run(main())
