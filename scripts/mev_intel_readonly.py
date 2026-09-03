#!/usr/bin/env python3
"""ISOLATED READ-ONLY MEV intelligence probe (pre-deployment test).

Reads PUBLIC Base mainnet on-chain data via a public JSON-RPC endpoint.
- NO writes anywhere (no Mongo, no files except stdout JSON).
- NO execution / signer / broadcast / new APIs / production coupling.
- Fetches real flash-loan + swap events for TODAY (chain UTC) and reconstructs
  ONLY what public logs+receipts permit. Anything not reliably derivable
  (searcher net profit, builder bribes) is left null with a reason — never faked.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

RPC = os.environ.get("ARBICORE_RPC_URL", "https://mainnet.base.org").split(",")[0].strip()

TOPICS = {
    "aave_v3_flashloan": "0xefefaba5e921573100900a3ad9cf29f222d995fb3b6045797eaea7521bd8d6f0",
    "balancer_v2_flashloan": "0x0d7d75e01ab95780d3cd1c8ec0dd6c2ce19e3a20427eec8bf53283b6fb8e95f0",
    "univ3_swap": "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67",
    "univ2_swap": "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822",
    "aerodrome_swap": "0xb3e2773606abfd36b5bd91394b3a54d1398336c65005baf7bf7a05efeffaf75b",
}
AAVE_V3_POOL = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"   # Base
BALANCER_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"  # Base

_id = 0


_UA = "Mozilla/5.0 (ArbiCore-X mev-intel readonly)"


def rpc(method, params, timeout=25, retries=3):
    global _id
    _id += 1
    body = json.dumps({"jsonrpc": "2.0", "id": _id, "method": method,
                       "params": params}).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            RPC, data=body,
            headers={"Content-Type": "application/json", "User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read())
            if "error" in out:
                raise RuntimeError(f"{method}: {out['error']}")
            return out["result"]
        except Exception as exc:                      # noqa: BLE001
            last = exc
            time.sleep(0.4 * (attempt + 1))
    raise last


def hx(x):
    return int(x, 16)


def get_logs(topic0, addr, from_b, to_b):
    return rpc("eth_getLogs", [{"fromBlock": hex(from_b), "toBlock": hex(to_b),
                                "address": addr, "topics": [topic0]}])


def scan_flashloans(from_b, to_b, chunk=800, cap=400):
    """Chunked scan for Aave V3 + Balancer flash-loan events."""
    found = {}
    for prov, (addr, topic) in {
        "aave_v3": (AAVE_V3_POOL, TOPICS["aave_v3_flashloan"]),
        "balancer_v2": (BALANCER_VAULT, TOPICS["balancer_v2_flashloan"]),
    }.items():
        b = from_b
        while b <= to_b and len(found) < cap:
            end = min(b + chunk - 1, to_b)
            try:
                logs = get_logs(topic, addr, b, end)
            except Exception as exc:                       # rate/range → shrink
                if chunk > 100:
                    chunk //= 2
                    continue
                sys.stderr.write(f"getLogs {prov} {b}-{end}: {exc}\n")
                b = end + 1
                continue
            for lg in logs:
                txh = lg["txHash"] if "txHash" in lg else lg["transactionHash"]
                rec = found.setdefault(txh, {
                    "tx": txh, "block": hx(lg["blockNumber"]),
                    "flash": [], "provider": prov})
                rec["flash"].append({"provider": prov,
                                     "data_len": len(lg.get("data", "0x")) // 2})
            b = end + 1
            time.sleep(0.05)
    return found


def reconstruct(txh):
    """Reconstruct log-derivable economics for one tx (NO trace, NO net profit)."""
    r = rpc("eth_getTransactionReceipt", [txh])
    if not r:
        return None
    logs = r.get("logs", []) or []
    swaps = {"univ3": 0, "univ2": 0, "aerodrome": 0}
    pools = set()
    for lg in logs:
        t0 = (lg.get("topics") or [""])[0]
        if t0 == TOPICS["univ3_swap"]:
            swaps["univ3"] += 1; pools.add(lg["address"])
        elif t0 == TOPICS["univ2_swap"]:
            swaps["univ2"] += 1; pools.add(lg["address"])
        elif t0 == TOPICS["aerodrome_swap"]:
            swaps["aerodrome"] += 1; pools.add(lg["address"])
    gas_used = hx(r.get("gasUsed", "0x0"))
    eff = hx(r.get("effectiveGasPrice", "0x0"))
    blk = rpc("eth_getBlockByNumber", [r["blockNumber"], False])
    base_fee = hx(blk.get("baseFeePerGas", "0x0"))
    ts = hx(blk["timestamp"])
    gas_cost_wei = gas_used * eff
    priority_wei = gas_used * max(0, eff - base_fee)
    total_swaps = sum(swaps.values())
    return {
        "tx": txh,
        "block": hx(r["blockNumber"]),
        "timestamp_utc": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
        "sender": r.get("from"),
        "status": hx(r.get("status", "0x0")),
        "swap_legs": swaps,
        "total_swap_legs": total_swaps,
        "distinct_pools": len(pools),
        "gas_used": gas_used,
        "effective_gas_price_gwei": round(eff / 1e9, 4),
        "gas_cost_eth": round(gas_cost_wei / 1e18, 8),
        "priority_fee_eth": round(priority_wei / 1e18, 8),
        # honest gaps — require trace/archive to reconstruct reliably:
        "gross_profit_eth": None,
        "net_profit_eth": None,
        "builder_bribe_eth": None,
        "reconstruction_note": ("net/gross profit + builder bribe NOT derivable "
                                "from public logs (needs debug_traceTransaction / "
                                "balance-diff on archive+trace RPC)"),
    }


def main():
    latest = hx(rpc("eth_blockNumber", []))
    head = rpc("eth_getBlockByNumber", [hex(latest), False])
    head_ts = hx(head["timestamp"])
    head_dt = datetime.fromtimestamp(head_ts, timezone.utc)
    # bounded sample: most-recent window of TODAY (chain UTC). Full-day scan of
    # ~43k Base blocks is infeasible on a rate-limited public RPC in this env.
    sample_blocks = int(os.environ.get("MEV_SAMPLE_BLOCKS", "2500"))
    from_b = latest - sample_blocks
    from_head = rpc("eth_getBlockByNumber", [hex(from_b), False])
    from_dt = datetime.fromtimestamp(hx(from_head["timestamp"]), timezone.utc)

    fl = scan_flashloans(from_b, latest)
    # reconstruct a bounded set of the flash-loan txs
    recon = []
    for i, txh in enumerate(list(fl.keys())):
        if i >= int(os.environ.get("MEV_RECON_CAP", "40")):
            break
        try:
            rr = reconstruct(txh)
            if rr:
                rr["providers"] = sorted({f["provider"] for f in fl[txh]["flash"]})
                recon.append(rr)
        except Exception as exc:
            sys.stderr.write(f"reconstruct {txh}: {exc}\n")
        time.sleep(0.05)

    # arb heuristic: flash-loan tx with >=2 swap legs and success
    arb_like = [r for r in recon if r["total_swap_legs"] >= 2 and r["status"] == 1]
    out = {
        "rpc_endpoint_host": RPC.split("//")[-1].split("/")[0],
        "chain_id": hx(rpc("eth_chainId", [])),
        "today_utc_date": head_dt.date().isoformat(),
        "window": {
            "from_block": from_b, "to_block": latest,
            "from_utc": from_dt.isoformat(), "to_utc": head_dt.isoformat(),
            "blocks_scanned": sample_blocks,
        },
        "trace_supported": False,
        "flashloan_txs_found": len(fl),
        "flashloan_txs_reconstructed": len(recon),
        "arb_like_txs": len(arb_like),
        "samples": recon,
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
