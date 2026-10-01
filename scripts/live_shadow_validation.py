#!/usr/bin/env python3
"""Live SHADOW validation harness — Balancer P0/P1/P1b + GENERIC_DEX.

READ-ONLY. No signing, no broadcast, no mode promotion, no production deploy.
Uses certified modules as libraries. Writes JSON evidence under reports/.

RPC URLs must come from the environment (ARBICORE_RPC_URL_<CHAIN>). Hosts are
redacted in the report; credentials are never written.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Ensure backend package root is importable when run from repo / docker mount.
_BACKEND = os.environ.get("ARBICORE_BACKEND_ROOT", "/work")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from eth_utils import to_checksum_address  # noqa: E402

from arbicore.discovery.balancer_v2_pool_discovery import (  # noqa: E402
    BALANCER_V2_VAULT_BY_CHAIN, discover_and_quote, OK as P0_OK,
)
from arbicore.discovery.balancer_v2_pool_enumeration import (  # noqa: E402
    SubgraphBalancerV2PoolSource, ENUM_DISCOVERY_UNAVAILABLE, enumerate_and_quote,
)
from arbicore.discovery.balancer_v2_onchain_source import (  # noqa: E402
    OnChainPoolRegisteredSource, POOL_REGISTERED_TOPIC,
)
from arbicore.execution.quoter import QuoterRegistry  # noqa: E402
from arbicore.scanners.generic_dex_route_engine import (  # noqa: E402
    GenericDexRouteEngine, VenueSpec, ELIGIBLE, BELOW_PROFIT_FLOOR,
    NON_POSITIVE_NET, LEG1_QUOTE_FAILED, LEG2_QUOTE_FAILED, UNKNOWN_GAS,
    UNKNOWN_PRICE, UNKNOWN_DECIMALS, UNSUPPORTED_FLASH_PROVIDER,
)
from arbicore.chains import registries  # noqa: E402
from arbicore.config.persistent import resolve_rpc_url_from_env  # noqa: E402


CHAINS_BAL = ("ethereum", "arbitrum", "base", "optimism", "polygon")
CHAINS_ALL = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")
# Well-known Ethereum Balancer V2 80BAL-20WETH — identity only; still P0-validated.
KNOWN_ETH_BAL_WETH = {
    "pool_address": "0x5c6Ee304399DBdB9C8Ef030aB642B10820DB8F56",
    "pool_id": "0x5c6ee304399dbdb9c8ef030ab642b10820db8f56000200000000000000000014",
    "token_in": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",   # WETH
    "token_out": "0xba100000625a3754423978a60c9317c58a424e3D",  # BAL
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_rpc(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        p = urllib.parse.urlparse(url)
        host = p.hostname or "unknown"
        # Drop path/query (API keys live there for Alchemy-style URLs).
        return f"{p.scheme}://{host}/<redacted>"
    except Exception:
        return "<redacted>"


def _rpc(chain: str) -> Optional[str]:
    return resolve_rpc_url_from_env(chain)


async def _json_rpc(rpc_url: str, method: str, params: list) -> Any:
    import httpx
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(rpc_url, json=payload)
        r.raise_for_status()
        body = r.json()
    if "error" in body and body["error"]:
        raise RuntimeError(f"rpc_error:{body['error']}")
    return body.get("result")


def _rpc_error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _make_eth_call(rpc_url: str):
    async def _call(to: str, data: str):
        try:
            result = await _json_rpc(rpc_url, "eth_call",
                                     [{"to": to, "data": data}, "latest"])
            bn = await _json_rpc(rpc_url, "eth_blockNumber", [])
            block = int(bn, 16) if isinstance(bn, str) else None
            if result is None:
                return None, block, {"error": "null_result"}
            return result, block, None
        except Exception as exc:  # noqa: BLE001
            return None, None, {"error": f"{type(exc).__name__}: {exc}"}
    return _call


def _make_get_logs(rpc_url: str):
    async def _get_logs(chain, address, topics, from_block: int, to_block: int):
        params = [{
            "address": address,
            "topics": topics,
            "fromBlock": hex(int(from_block)),
            "toBlock": hex(int(to_block)),
        }]
        return await _json_rpc(rpc_url, "eth_getLogs", params)
    return _get_logs


def _make_block_number(rpc_url: str):
    async def _bn(chain):
        bn = await _json_rpc(rpc_url, "eth_blockNumber", [])
        return int(bn, 16)
    return _bn


# --------------------------------------------------------------------------- #
# Balancer validation
# --------------------------------------------------------------------------- #

async def validate_balancer_chain(chain: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "chain": chain, "rpc": _redact_rpc(_rpc(chain)),
        "provider": "balancer_v2", "p0": None, "p1_subgraph": None,
        "p1b_onchain": None, "failures": [],
    }
    rpc = _rpc(chain)
    if chain not in BALANCER_V2_VAULT_BY_CHAIN:
        out["failures"].append("unsupported_chain_for_balancer_v2")
        return out
    if not rpc:
        out["failures"].append("rpc_unconfigured")
        return out

    eth_call = _make_eth_call(rpc)

    # --- P1: subgraph (expect DISCOVERY_UNAVAILABLE when URL unset) ---
    sub = SubgraphBalancerV2PoolSource()
    # Prefer multichain registry; Base uses dedicated base_venues.
    if chain == "base":
        from arbicore.discovery.base_venues import TOKENS as _BASE_TOKENS
        weth = _BASE_TOKENS["WETH"]["address"]
        usdc = _BASE_TOKENS["USDC"]["address"]
    else:
        reg = registries.registry_for(chain) or {}
        tokens = reg.get("tokens") or {}
        weth = (tokens.get("WETH") or tokens.get("WBNB") or tokens.get("WMATIC") or {}).get("address")
        usdc = (tokens.get("USDC") or {}).get("address")
    if weth and usdc:
        src_res = await sub.find_pools(chain, weth, usdc)
        out["p1_subgraph"] = {
            "status": src_res.status,
            "error": src_res.error,
            "candidates": len(src_res.candidates or []),
            "source": src_res.source_name,
            "expected_unavailable_without_url": src_res.status == "discovery_unavailable",
        }
    else:
        out["p1_subgraph"] = {"status": "skipped", "error": "no_weth_usdc_in_registry"}

    # --- P1b: on-chain PoolRegistered (small recent window) ---
    get_logs = _make_get_logs(rpc)
    block_number = _make_block_number(rpc)
    # Keep window modest by default; allow override. Prefer enough history for PoolRegistered.
    window = int(os.environ.get("ARBICORE_SHADOW_BAL_WINDOW", "50000"))
    chunk = int(os.environ.get("ARBICORE_SHADOW_BAL_CHUNK", "2000"))
    src = OnChainPoolRegisteredSource(
        eth_get_logs_fn=get_logs,
        eth_block_number_fn=block_number,
        window_blocks=window,
        chunk_size=chunk,
    )
    try:
        p1b = await src.find_pools(chain, weth or "0x0", usdc or "0x0")
        sample = []
        for c in (p1b.candidates or [])[:5]:
            sample.append({
                "pool_id": c.pool_id,
                "pool_address": c.pool_address,
                "raw_block": (c.raw or {}).get("block_number"),
            })
        out["p1b_onchain"] = {
            "status": p1b.status,
            "error": p1b.error,
            "candidates": len(p1b.candidates or []),
            "sample": sample,
            "provenance": p1b.provenance,
            "topic0": POOL_REGISTERED_TOPIC,
            "window_blocks": window,
        }
    except Exception as exc:  # noqa: BLE001
        out["p1b_onchain"] = {"status": "rpc_error", "error": f"{type(exc).__name__}: {exc}"}
        out["failures"].append("p1b_exception")

    # --- P0: real quote ---
    # Prefer a P1b candidate; on ethereum fall back to known BAL/WETH identity.
    pool_id = None
    pool_address = None
    token_in = weth
    token_out = usdc
    if out.get("p1b_onchain") and (out["p1b_onchain"].get("sample") or []):
        s0 = out["p1b_onchain"]["sample"][0]
        pool_id = s0["pool_id"]
        pool_address = s0["pool_address"]
    elif chain == "ethereum":
        pool_id = KNOWN_ETH_BAL_WETH["pool_id"]
        pool_address = KNOWN_ETH_BAL_WETH["pool_address"]
        token_in = KNOWN_ETH_BAL_WETH["token_in"]
        token_out = KNOWN_ETH_BAL_WETH["token_out"]

    if pool_id or pool_address:
        # For P1b-discovered pools, membership unknown until getPoolTokens —
        # probe with registry WETH as token_in and first other token after discovery.
        # First call discover_and_quote; if TOKEN_NOT_IN_POOL, try get tokens via
        # a second strategy: quote tiny WETH only after reading pool tokens inline.
        amount = 10**15  # 0.001 WETH-scale; for USDC-scale pools may fail closed
        if token_out and token_in:
            q = await discover_and_quote(
                eth_call, chain, token_in, token_out, amount,
                pool_id=pool_id, pool_address=pool_address)
            out["p0"] = {
                "status": q.status,
                "error": q.error,
                "amount_out_wei": q.amount_out_wei,
                "block_number": q.block_number,
                "pool_id": pool_id,
                "pool_address": pool_address,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in_wei": amount,
                "meta": None if not q.meta else {
                    "pool_address": q.meta.pool_address,
                    "pool_id": q.meta.pool_id,
                    "tokens": [t.address for t in q.meta.tokens],
                    "balances": [t.balance for t in q.meta.tokens],
                    "decimals": [t.decimals for t in q.meta.tokens],
                    "swap_fee_bps": q.meta.swap_fee_bps,
                    "last_change_block": q.meta.last_change_block,
                },
            }
            # If membership failed on WETH/USDC, retry using first two pool tokens.
            if q.status == "token_not_in_pool" and q.meta and q.meta.tokens and len(q.meta.tokens) >= 2:
                t0, t1 = q.meta.tokens[0], q.meta.tokens[1]
                amt2 = max(1, 10 ** max(0, int(t0.decimals) - 3))
                q2 = await discover_and_quote(
                    eth_call, chain, t0.address, t1.address, amt2,
                    pool_id=pool_id, pool_address=pool_address)
                out["p0_retry_pool_tokens"] = {
                    "status": q2.status,
                    "error": q2.error,
                    "amount_out_wei": q2.amount_out_wei,
                    "amount_in_wei": amt2,
                    "block_number": q2.block_number,
                    "token_in": t0.address,
                    "token_out": t1.address,
                    "ok": q2.status == P0_OK,
                }
            elif q.status == P0_OK:
                out["p0"]["ok"] = True
            # Also: if discovery returned meta with tokens but quote failed for
            # other reasons, record liquidity snapshot from meta.
            if q.meta and q.meta.tokens:
                out["liquidity_snapshot"] = {
                    "tokens": [t.address for t in q.meta.tokens],
                    "balances": [t.balance for t in q.meta.tokens],
                    "decimals": [t.decimals for t in q.meta.tokens],
                    "swap_fee_bps": q.meta.swap_fee_bps,
                }
        else:
            out["failures"].append("no_token_pair_for_p0")
    else:
        out["failures"].append("no_pool_identity_for_p0")

    # Explicit Ethereum known-pool P0 proof (independent of P1b candidate membership).
    if chain == "ethereum":
        k = KNOWN_ETH_BAL_WETH
        amount = 10**15
        qk = await discover_and_quote(
            eth_call, chain, k["token_in"], k["token_out"], amount,
            pool_id=k["pool_id"], pool_address=k["pool_address"])
        out["p0_known_bal_weth"] = {
            "status": qk.status,
            "error": qk.error,
            "amount_in_wei": amount,
            "amount_out_wei": qk.amount_out_wei,
            "block_number": qk.block_number,
            "pool_id": k["pool_id"],
            "pool_address": k["pool_address"],
            "token_in": k["token_in"],
            "token_out": k["token_out"],
            "ok": qk.status == P0_OK,
            "meta": None if not qk.meta else {
                "tokens": [t.address for t in qk.meta.tokens],
                "balances": [t.balance for t in qk.meta.tokens],
                "decimals": [t.decimals for t in qk.meta.tokens],
                "swap_fee_bps": qk.meta.swap_fee_bps,
            },
        }
        if qk.status == P0_OK:
            regq = QuoterRegistry()
            hop = {
                "dex": "balancer_v2",
                "token_in": k["token_in"],
                "token_out": k["token_out"],
                "amount_in_wei": amount,
                "pool_id": k["pool_id"],
                "pool_address": k["pool_address"],
            }
            rq = await regq.quote_route(chain=chain, hops=[hop], rpc_url=rpc)
            h0 = rq.hops[0] if rq.hops else None
            out["p0_known_quoter_registry"] = {
                "route_status": rq.status,
                "hop_status": getattr(h0, "status", None),
                "amount_out_wei": getattr(h0, "amount_out_wei", None),
                "error": getattr(h0, "error", None),
            }

    return out


# --------------------------------------------------------------------------- #
# GENERIC_DEX validation
# --------------------------------------------------------------------------- #

class _RegistryPriceSource:
    """Honest price source for live validation.

    - Stables (USDC/USDT/DAI/USDbC/USDC.e): peg $1.0 (documented stable assumption)
    - Others: None unless a live UniV3 quote to USDC succeeds via QuoterRegistry
    Never fabricates WETH/etc prices without a real quote.
    """

    STABLES = {"USDC", "USDT", "DAI", "USDBC", "USDC.E"}

    def __init__(self, quoter: QuoterRegistry, symbol_index: Dict[str, Dict[str, str]]):
        self._quoter = quoter
        self._idx = symbol_index  # chain -> {symbol_upper: address}

    async def price_usd(self, chain: str, token: str) -> Optional[float]:
        c = (chain or "").lower()
        addr = to_checksum_address(token)
        # Resolve symbol from registry index.
        sym = None
        for s, a in (self._idx.get(c) or {}).items():
            if a.lower() == addr.lower():
                sym = s
                break
        if sym:
            norm = sym.upper().replace(".", "")
            if norm in {"USDC", "USDT", "DAI", "USDBC", "USDCE"} or sym.upper() in self.STABLES:
                return 1.0
        # Live WETH→USDC (or native wrap→USDC) via UniV3 0.05% then 0.3%.
        usdc = (self._idx.get(c) or {}).get("USDC")
        if not usdc:
            return None
        rpc = _rpc(c)
        for fee in (500, 3000):
            hop = {"dex": "uniswap_v3", "token_in": addr, "token_out": usdc,
                   "amount_in_wei": 10**15, "fee": fee}
            try:
                rq = await self._quoter.quote_route(chain=c, hops=[hop], rpc_url=rpc)
            except Exception:
                continue
            if rq.status == "ok" and rq.final_amount_out_wei and rq.final_amount_out_wei > 0:
                # amount_in 1e15 of 18-dec token → USDC 6-dec
                usdc_out = rq.final_amount_out_wei / 1e6
                token_in = 10**15 / 1e18
                if token_in > 0 and usdc_out > 0:
                    return float(usdc_out / token_in)
        return None


def _decimals_fn(chain: str, token: str) -> Optional[int]:
    from arbicore.scanners.flash_loan_arbitrage.exact_size_sizer import registry_decimals
    d = registry_decimals(chain, token)
    if d is not None:
        return d
    # Fall back to chain registry by address match.
    reg = registries.registry_for(chain) or {}
    for spec in (reg.get("tokens") or {}).values():
        if str(spec.get("address", "")).lower() == str(token).lower():
            try:
                return int(spec["decimals"])
            except Exception:
                return None
    # Base registry
    if chain == "base":
        from arbicore.discovery.base_venues import TOKENS
        for spec in TOKENS.values():
            if str(spec["address"]).lower() == str(token).lower():
                return int(spec["decimals"])
    return None


def _symbol_index() -> Dict[str, Dict[str, str]]:
    idx: Dict[str, Dict[str, str]] = {}
    for chain in CHAINS_ALL:
        m: Dict[str, str] = {}
        if chain == "base":
            from arbicore.discovery.base_venues import TOKENS
            for sym, spec in TOKENS.items():
                m[sym.upper()] = to_checksum_address(spec["address"])
        else:
            reg = registries.registry_for(chain) or {}
            for sym, spec in (reg.get("tokens") or {}).items():
                m[sym.upper()] = to_checksum_address(spec["address"])
        idx[chain] = m
    return idx


async def validate_generic_dex_chain(chain: str, quoter: QuoterRegistry,
                                     price_src, amount_usd: float = 200.0
                                     ) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "chain": chain, "rpc": _redact_rpc(_rpc(chain)), "candidates": [],
        "summary": {},
    }
    rpc = _rpc(chain)
    if not rpc:
        out["summary"] = {"error": "rpc_unconfigured"}
        return out

    idx = _symbol_index().get(chain) or {}
    # Borrow USDC (stable $1), intermediate WETH / WBNB / WMATIC
    borrow_sym = "USDC" if "USDC" in idx else None
    inter_sym = next((s for s in ("WETH", "WBNB", "WMATIC") if s in idx), None)
    if not borrow_sym or not inter_sym:
        out["summary"] = {"error": "missing_borrow_or_intermediate_token"}
        return out
    borrow = idx[borrow_sym]
    inter = idx[inter_sym]

    # Venue pairs: UniV3 fee tiers + second DEX where available.
    venues: List[VenueSpec] = [
        VenueSpec(dex="uniswap_v3", fee=500, fee_bps=5, venue_id="univ3_500"),
        VenueSpec(dex="uniswap_v3", fee=3000, fee_bps=30, venue_id="univ3_3000"),
    ]
    # Chain-specific second venues from registry dex list.
    reg = registries.registry_for(chain) if chain != "base" else None
    if chain == "base":
        venues.append(VenueSpec(dex="aerodrome_slipstream", fee=100, fee_bps=1,
                                venue_id="aero_ss_100"))
        venues.append(VenueSpec(dex="aerodrome", fee_bps=30, venue_id="aero_vol"))
    elif reg:
        for d in reg.get("dexes") or []:
            dex = d.get("dex")
            if dex in ("sushiswap_v3", "sushi_v3"):
                venues.append(VenueSpec(dex="sushiswap_v3", fee=500, fee_bps=5,
                                        venue_id="sushi_500"))
            if dex in ("pancake_v3", "pancakeswap_v3"):
                venues.append(VenueSpec(dex="pancake_v3", fee=500, fee_bps=5,
                                        venue_id="pancake_500"))
            if dex == "camelot_v3":
                venues.append(VenueSpec(dex="camelot_v3", fee_bps=0,
                                        venue_id="camelot"))
            if dex == "quickswap_v3":
                venues.append(VenueSpec(dex="quickswap_v3", fee_bps=0,
                                        venue_id="quickswap"))

    flash = "aave_v3" if chain != "bnb" else "aave_v3"
    # balancer_v2 flash also valid on non-BNB
    flash_providers = ["aave_v3"]
    if chain != "bnb":
        flash_providers.append("balancer_v2")

    eng = GenericDexRouteEngine(
        quoter, price_src, decimals_fn=_decimals_fn, min_atomic_profit_usd=25.0)

    buckets = {"A_eligible": 0, "B_below_floor_or_nonpos": 0, "C_quote_fail": 0,
               "D_liq_fail": 0, "E_gas_fail": 0, "F_rpc_data_fail": 0,
               "G_unsupported": 0}

    # Evaluate distinct buy/sell venue pairs (limit to keep RPC budget).
    pairs: List[Tuple[VenueSpec, VenueSpec]] = []
    for i, vb in enumerate(venues):
        for j, vs in enumerate(venues):
            if i == j:
                continue
            pairs.append((vb, vs))
    pairs = pairs[:8]

    for vb, vs in pairs:
        for fp in flash_providers[:1]:  # primary flash provider first
            try:
                r = await eng.evaluate_route(
                    chain=chain, borrow_token=borrow, intermediate_token=inter,
                    amount_usd=amount_usd, venue_buy=vb, venue_sell=vs,
                    flash_provider=fp, rpc_url=rpc)
            except Exception as exc:  # noqa: BLE001
                buckets["F_rpc_data_fail"] += 1
                out["candidates"].append({
                    "route": f"{vb.venue_id}->{vs.venue_id}",
                    "flash_provider": fp,
                    "status": "exception",
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue

            row = {
                "route": f"{vb.venue_id}->{vs.venue_id}",
                "flash_provider": fp,
                "borrow_asset": borrow_sym,
                "borrow_token": borrow,
                "intermediate": inter_sym,
                "borrow_amount_wei": r.borrow_amount_wei,
                "borrow_amount_usd": r.borrow_amount_usd,
                "status": r.status,
                "eligible": r.eligible,
                "gross_profit_usd": r.gross_profit_usd,
                "gas_cost_usd": r.gas_cost_usd,
                "flash_fee_usd": r.flash_fee_usd,
                "net_profit_usd": r.net_profit_usd,
                "min_atomic_profit_usd": r.min_atomic_profit_usd,
                "gate7_pass": bool(r.eligible and r.net_profit_usd >= 25.0),
                "reasons": list(r.reasons),
                "leg1_status": None if not r.leg1 else r.leg1.status,
                "leg2_status": None if not r.leg2 else r.leg2.status,
            }
            out["candidates"].append(row)

            st = r.status
            if st == ELIGIBLE:
                buckets["A_eligible"] += 1
            elif st in (BELOW_PROFIT_FLOOR, NON_POSITIVE_NET):
                buckets["B_below_floor_or_nonpos"] += 1
            elif st in (LEG1_QUOTE_FAILED, LEG2_QUOTE_FAILED):
                buckets["C_quote_fail"] += 1
            elif st in ("unknown_liquidity", "insufficient_liquidity"):
                buckets["D_liq_fail"] += 1
            elif st == UNKNOWN_GAS:
                buckets["E_gas_fail"] += 1
            elif st in (UNKNOWN_PRICE, UNKNOWN_DECIMALS):
                buckets["F_rpc_data_fail"] += 1
            elif st == UNSUPPORTED_FLASH_PROVIDER:
                buckets["G_unsupported"] += 1
            else:
                buckets["G_unsupported"] += 1

    out["summary"] = buckets
    return out


async def main() -> int:
    started = _now()
    report: Dict[str, Any] = {
        "phase": "live_shadow_validation",
        "certified_tip": "861af4d60e841ac8abac5891d663e23986c356ad",
        "tag": "arbicore-extract-port-pass-20261001",
        "started_at": started,
        "execution_mode_expected": "SHADOW",
        "signing": False,
        "broadcast": False,
        "balancer": [],
        "generic_dex": [],
        "integration_decision": {
            "generic_dex_scanner_wiring_required_for_evidence": False,
            "rationale": (
                "GenericDexRouteEngine is a certified library that already "
                "performs quotes→gas→economics→$25 Gate 7. Live SHADOW evidence "
                "is produced by driving it with QuoterRegistry + real RPCs. "
                "EmissionBus/scanner wiring remains a residual architecture item."
            ),
            "code_change": False,
        },
    }

    # Balancer
    for chain in CHAINS_BAL:
        print(f"[balancer] {chain} ...", flush=True)
        try:
            report["balancer"].append(await validate_balancer_chain(chain))
        except Exception as exc:  # noqa: BLE001
            report["balancer"].append({
                "chain": chain, "failures": [f"exception:{type(exc).__name__}: {exc}"]})

    # GENERIC_DEX
    quoter = QuoterRegistry()
    price_src = _RegistryPriceSource(quoter, _symbol_index())
    for chain in CHAINS_ALL:
        print(f"[generic_dex] {chain} ...", flush=True)
        try:
            report["generic_dex"].append(
                await validate_generic_dex_chain(chain, quoter, price_src))
        except Exception as exc:  # noqa: BLE001
            report["generic_dex"].append({
                "chain": chain, "summary": {"error": f"{type(exc).__name__}: {exc}"},
                "candidates": []})

    report["finished_at"] = _now()

    # Economic evidence rollup
    A = B = C = D = E = F = G = 0
    for g in report["generic_dex"]:
        s = g.get("summary") or {}
        A += int(s.get("A_eligible") or 0)
        B += int(s.get("B_below_floor_or_nonpos") or 0)
        C += int(s.get("C_quote_fail") or 0)
        D += int(s.get("D_liq_fail") or 0)
        E += int(s.get("E_gas_fail") or 0)
        F += int(s.get("F_rpc_data_fail") or 0)
        G += int(s.get("G_unsupported") or 0)
    report["economic_evidence"] = {
        "A_real_profitable": A,
        "B_real_economically_rejected": B,
        "C_quote_failures": C,
        "D_liquidity_failures": D,
        "E_gas_failures": E,
        "F_rpc_data_failures": F,
        "G_unsupported_routes": G,
        "note": "Counts from GENERIC_DEX live route evaluations only; "
                "unit-test greens are excluded.",
    }

    out_dir = os.environ.get(
        "ARBICORE_SHADOW_REPORT_DIR",
        "/home/raghu/projects/arbicore-x-cert/reports/shadow_validation")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"live_shadow_{stamp}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    # Also write a stable latest pointer
    latest = os.path.join(out_dir, "live_shadow_latest.json")
    with open(latest, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"WROTE {path}", flush=True)
    print(json.dumps(report["economic_evidence"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
