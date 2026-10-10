# Audit artifact — G1.5 offline Base route coverage

**Do not treat this directory as product code.** Scripts here are for reproducible offline audit only.

## Inputs (read-only)
- Frozen export: `../core-20261008T2216Z/G1_5_EXPORT_20261008T2216Z/MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl`
- Universe snapshot: `arbicore_base_universe_snapshot.json` (dumped from `arbicore-x-backend-new`)

## Re-run matcher
```bash
cd ~/projects/arbicore-x-cert/artifacts/g15/audit_offline_base_replay_20261009
python3 offline_base_winner_route_coverage.py
```

## Refresh universe snapshot (optional; requires container; no writes to ArbiCore)
```bash
docker exec -i arbicore-x-backend-new python3 -c '
from arbicore.discovery.base_pool_registry import build_canonical_pools, registry_summary
from arbicore.discovery import base_venues as bv
import json
out={
  "build_info": json.load(open("/app/BUILD_INFO.json")),
  "registry_summary": registry_summary(),
  "tokens": {k:{"address":v["address"].lower(),"decimals":v["decimals"]} for k,v in bv.TOKENS.items()},
  "borrow_tokens": bv.BORROW_TOKENS,
  "router_allowlist": [a.lower() for a in bv.ROUTER_ALLOWLIST],
  "venues":[{"dex":d,"a":a,"b":b,"param":p} for d,a,b,p in bv.VENUES],
  "pools":[p.to_dict() for p in build_canonical_pools()],
}
for p in out["pools"]:
  if p.get("address"): p["address"]=p["address"].lower()
  p["token0"]["address"]=p["token0"]["address"].lower()
  p["token1"]["address"]=p["token1"]["address"].lower()
print(json.dumps(out))
' > arbicore_base_universe_snapshot.json
```

## Primary report
See `BASE_G15_OFFLINE_ROUTE_COVERAGE_AUDIT.md`.
