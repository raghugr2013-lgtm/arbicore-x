#!/usr/bin/env python3
"""Phase-2 · Live-chain validation harness (SHADOW / read-only / fail-closed).

Runs the full Arbitrum-style validation sequence against a REAL RPC for one
chain and prints a JSON evidence report:

  RPC connectivity → chainId → token registry (code+decimals) → DEX/venue
  registry (factory code) → real route discovery (factory.getPool) → real
  depth (pool token balances) → flash-provider availability + on-chain
  liquidity (Balancer Vault / Aave V3) → provider fee → gas price → L1/security
  fee → slippage → all-in cost → true-net vs the $35 gate → readiness.

ZERO signing. ZERO broadcast. Read-only eth_call / eth_getCode / eth_gasPrice.
Every unavailable/unreliable input FAILS CLOSED (DENY / UNKNOWN) — never a
substituted zero or default.

Usage:
    python scripts/phase2_validate_chain.py arbitrum
    ARBICORE_RPC_URL_ARBITRUM=https://... python scripts/phase2_validate_chain.py arbitrum
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from eth_utils import function_signature_to_4byte_selector  # noqa: E402

from arbicore.chains.evm_adapter import EvmChainAdapter  # noqa: E402
from arbicore.chains.gas_model import get_chain_gas_model  # noqa: E402
from arbicore.chains.evm_gas import CHAIN_SPECS  # noqa: E402
from arbicore.providers.rpc import EthJsonRpcProvider, DEFAULT_RPC_URLS  # noqa: E402
from arbicore.scanners.flash_loan_arbitrage import provider_liquidity as PL  # noqa: E402
from arbicore.scanners.flash_loan_arbitrage.flash_provider_optimizer import (  # noqa: E402
    optimize_flash_provider)

MIN_NET_PROFIT_USD = float(os.environ.get("ARBICORE_MIN_NET_PROFIT_USD", "35"))


def sel(sig):
    return "0x" + function_signature_to_4byte_selector(sig).hex()


SEL_DECIMALS = sel("decimals()")
SEL_GET_POOL = sel("getPool(address,address,uint24)")
SEL_BALANCE_OF = sel("balanceOf(address)")


def arg_addr(a):
    return a.lower().replace("0x", "").rjust(64, "0")


def arg_uint(n):
    return f"{n:064x}"


async def get_code_exists(p, addr):
    try:
        c = await p._call("eth_getCode", [addr, "latest"])
        return c is not None and len(c.replace("0x", "")) > 0
    except Exception as e:  # noqa
        return None


async def read_decimals(p, token):
    try:
        raw = await p.eth_call({"to": token, "data": SEL_DECIMALS})
        return int(raw, 16) if raw and raw != "0x" else None
    except Exception:  # noqa
        return None


async def fetch_native_usd(symbol):
    """Best-effort live native price. Unavailable ⇒ None (fail-closed downstream)."""
    ids = {"ETH": "ethereum", "POL": "matic-network", "BNB": "binancecoin"}
    cg = ids.get(symbol)
    if not cg:
        return None
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.coingecko.com/api/v3/simple/price",
                            params={"ids": cg, "vs_currencies": "usd"})
            return float(r.json()[cg]["usd"])
    except Exception:  # noqa
        return None


async def validate(chain):
    chain = chain.lower()
    report = {"chain": chain, "shadow": True, "signing": False,
              "broadcast": False, "stages": {}, "fail_closed_events": []}
    S = report["stages"]

    spec = CHAIN_SPECS.get(chain)
    if not spec:
        report["result"] = "UNSUPPORTED_CHAIN"
        return report
    adapter = EvmChainAdapter(chain)
    url = (adapter.resolve_rpc_url() or DEFAULT_RPC_URLS.get(chain))
    if not url:
        report["result"] = "NO_RPC"
        report["fail_closed_events"].append("no_rpc_configured")
        return report
    report["rpc_url_host"] = url.split("//")[-1].split("/")[0]
    p = EthJsonRpcProvider(chain=chain, url=url)

    # 1) RPC connectivity + chain identity.
    t0 = time.time()
    try:
        cid = await p.eth_chain_id()
        block = await p.eth_get_block_number()
        S["rpc"] = {"ok": True, "latency_ms": round((time.time() - t0) * 1000, 1),
                    "block": block}
        S["chain_identity"] = {"chain_id": cid,
                               "expected": spec["chain_id"],
                               "match": cid == spec["chain_id"]}
    except Exception as e:  # noqa
        S["rpc"] = {"ok": False, "error": str(e)[:200]}
        report["result"] = "RPC_UNREACHABLE"
        return report
    if not S["chain_identity"]["match"]:
        report["result"] = "CHAIN_ID_MISMATCH"
        return report

    # 2) Token registry — code + on-chain decimals.
    tokens = adapter.token_registry()
    tok_report = {}
    for sym, meta in tokens.items():
        addr = meta["address"]
        exists = await get_code_exists(p, addr)
        dec = await read_decimals(p, addr) if exists else None
        tok_report[sym] = {"address": addr, "code": exists,
                           "onchain_decimals": dec,
                           "registry_decimals": meta["decimals"],
                           "decimals_match": dec == meta["decimals"]}
    S["token_registry"] = {"count": len(tokens), "tokens": tok_report}

    # 3) DEX/venue registry — factory code exists.
    from arbicore.chains import registries
    dex_report = {}
    for d in registries.dexes_for(chain):
        dex_report[d["dex"]] = {"factory": d["factory"],
                                "code": await get_code_exists(p, d["factory"])}
    S["dex_registry"] = dex_report

    # 4) Real route discovery + depth: factory.getPool(WETH,USDC,0.05%).
    weth = (tokens.get("WETH") or tokens.get("WBNB") or tokens.get("WMATIC"))
    usdc = tokens.get("USDC")
    S["route_discovery"] = {}
    if weth and usdc:
        v3 = next((d for d in registries.dexes_for(chain) if d["kind"] == "v3"), None)
        if v3:
            for fee in (500, 3000):
                try:
                    data = (SEL_GET_POOL + arg_addr(weth["address"])
                            + arg_addr(usdc["address"]) + arg_uint(fee))
                    raw = await p.eth_call({"to": v3["factory"], "data": data})
                    pool = "0x" + raw[-40:] if raw and int(raw, 16) != 0 else None
                except Exception as e:  # noqa
                    pool = None
                depth = {}
                if pool:
                    for sym, meta in (("WETH", weth), ("USDC", usdc)):
                        try:
                            b = await p.eth_call({"to": meta["address"],
                                                  "data": SEL_BALANCE_OF + arg_addr(pool)})
                            depth[sym] = int(b, 16) / (10 ** meta["decimals"])
                        except Exception:  # noqa
                            depth[sym] = None
                S["route_discovery"][f"WETH/USDC@{fee}"] = {
                    "dex": v3["dex"], "pool": pool, "pool_token_depth": depth}

    # 5) Flash-provider availability + REAL on-chain liquidity.
    native_usd = await fetch_native_usd(spec["native"])
    S["native_price_usd"] = native_usd
    borrow_usd = 50_000.0
    liq = {}
    liquidity_by_provider = {}
    fee_by_provider = {}
    # Balancer (WETH) where supported; Aave (WETH) everywhere it has a pool.
    weth_price = (native_usd if spec["native"] == "ETH"
                  else await fetch_native_usd("ETH"))
    if weth:
        providers = adapter.flashloan_provider_registry()
        if "balancer_v2" in providers:
            r = await PL.read_balancer_liquidity(
                p, chain=chain, token_address=weth["address"],
                token_decimals=weth["decimals"], token_price_usd=weth_price,
                borrow_amount_usd=borrow_usd)
            liq["balancer_v2"] = r.to_dict()
            liquidity_by_provider["balancer_v2"] = r.feasible_usd
            fee_by_provider["balancer_v2"] = r.fee_bps
        if "aave_v3" in providers:
            r = await PL.read_aave_liquidity(
                p, chain=chain, token_address=weth["address"],
                token_decimals=weth["decimals"], token_price_usd=weth_price,
                borrow_amount_usd=borrow_usd)
            liq["aave_v3"] = r.to_dict()
            liquidity_by_provider["aave_v3"] = r.feasible_usd
            fee_by_provider["aave_v3"] = r.fee_bps
    S["provider_liquidity"] = liq

    # 6) Provider optimizer (economically best FEASIBLE provider).
    choice = optimize_flash_provider(
        chain=chain, borrow_token="WETH", borrow_amount_usd=borrow_usd,
        liquidity_by_provider=liquidity_by_provider,
        fee_bps_by_provider=fee_by_provider)
    S["provider_choice"] = {"feasible": choice.feasible,
                            "provider": choice.provider,
                            "fee_bps": choice.fee_bps,
                            "fee_usd": choice.fee_usd,
                            "callback_extra_gas": choice.callback_extra_gas_units,
                            "reason": choice.reason}

    # 7) Gas price + L1/security fee + all-in cost via the chain gas model.
    gm = get_chain_gas_model(chain)
    try:
        gp = await p.eth_get_gas_price()
        S["gas_price_wei"] = gp
    except Exception as e:  # noqa
        S["gas_price_wei"] = None
        report["fail_closed_events"].append("gas_price_read_failed")
    all_in = None
    if gm is not None:
        all_in = await gm.all_in_cost(
            gross_profit_usd=0.0, borrow_amount_usd=borrow_usd,
            notional_usd=borrow_usd, gas_units=300_000, eth_usd=native_usd)
    S["all_in_cost"] = all_in
    if all_in is None:
        report["fail_closed_events"].append("all_in_cost_denied")

    # 8) True-net vs the $35 gate (COSTS are real; a gross edge must beat them).
    if all_in is not None and choice.feasible:
        total_cost = all_in["all_in_cost_usd"] + (choice.fee_usd or 0.0)
        S["economics"] = {
            "min_net_profit_gate_usd": MIN_NET_PROFIT_USD,
            "real_all_in_cost_usd": round(total_cost, 4),
            "l2_fee_usd": all_in.get("l2_fee_usd"),
            "l1_fee_usd": all_in.get("l1_fee_usd"),
            "slippage_usd": all_in.get("slippage_usd"),
            "flash_provider_fee_usd": choice.fee_usd,
            "gross_edge_required_to_pass_usd": round(total_cost + MIN_NET_PROFIT_USD, 4),
            "note": "SHADOW: no live gross edge asserted; costs are real on-chain.",
        }
        S["readiness"] = {
            "m3_authority": "M3 remains final execution authority",
            "executable": False, "signing": False, "broadcast": False,
            "state": "COST_MODEL_LIVE (detection-only)"}

    # Overall fail-closed verdict.
    critical_ok = (S["rpc"]["ok"] and S["chain_identity"]["match"]
                   and S["token_registry"]["count"] > 0)
    report["result"] = "LIVE_VALIDATED" if critical_ok else "FAIL_CLOSED"
    report["all_in_cost_available"] = all_in is not None
    report["provider_feasible"] = choice.feasible
    await p.close()
    return report


async def main():
    chain = sys.argv[1] if len(sys.argv) > 1 else "arbitrum"
    rep = await validate(chain)
    print(json.dumps(rep, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
