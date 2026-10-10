import asyncio, json, os, re, hashlib, urllib.parse, httpx
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
  db=AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)["arbicore_x"]
  doc=await db.arbicore_config.find_one({"_id":"network"})
  url=doc["rpc_urls"]["base"][0]
  addrs={
    "address_file": open("/tmp/deployer_addr.txt").read().strip(),
    "prior_derived_s1b": "0x3b37a5E124b177fEE30365deb295A5CCF76841Cd",
  }
  out={}
  async with httpx.AsyncClient(timeout=25) as client:
    for label,addr in addrs.items():
      r=await client.post(url, json={"jsonrpc":"2.0","id":1,"method":"eth_getBalance","params":[addr,"latest"]})
      js=r.json()
      wei=int(js["result"],16) if r.status_code==200 and "result" in js else None
      out[label]={
        "addr_prefix": addr[:6], "addr_suffix": addr[-4:],
        "http": r.status_code,
        "rpc_error": js.get("error",{}).get("message") if isinstance(js.get("error"),dict) else None,
        "balance_eth": (wei/1e18 if wei is not None else None),
        "nonzero": bool(wei),
      }
  m=re.match(r".*/v2/([^/]+)", urllib.parse.urlparse(url).path or "")
  print(json.dumps({
    "rpc_primary_fp8": hashlib.sha256(m.group(1).encode()).hexdigest()[:8] if m else None,
    "balances": out
  }))
asyncio.run(main())
