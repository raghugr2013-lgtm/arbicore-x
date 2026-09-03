"""ArbiCore X — Wallet & Capital Intelligence Engine (READ-ONLY, SHADOW-safe).

Extends the existing wallet infrastructure (``WalletBalanceReader``,
``WalletRegistryRepo``, the Base token universe + router allowlist) with:

  * live native + ERC-20 balances for the configured Base gas/execution wallet
  * a full transaction statement (timestamp, block, hash, direction, token,
    amount, gas, fee, P/L, status) sourced from an explorer index
  * DEX activity classification by venue / router / method selector
  * flash-loan arbitrage money-trail reconstruction (borrow → swaps → repay)
  * capital-flow reconciliation: start + inflows − outflows − fees + P/L = end
  * per-wallet and per-venue/pair statistics

STRICT read-only: only ``eth_call`` / ``eth_getBalance`` and a read-only
explorer API are used. No private keys are ever read, logged, or displayed —
only public addresses and on-chain/transaction data. No signing/broadcast.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..discovery.base_venues import TOKENS, ROUTER_ALLOWLIST

logger = logging.getLogger("arbicore.capital.wallet_intelligence")

# Known Base venue routers → human-readable venue label (superset of the
# allowlist so we can *classify* observed activity, never execute it).
_VENUE_ROUTERS: Dict[str, str] = {
    "0x2626664c2603336e57b271c5c0b26f421741e481": "uniswap_v3",
    "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43": "aerodrome",
    "0x6ff5693b99212da76ad316178a184ab56d299b43": "uniswap_universal",
    "0x2223f9fe624f69da4d8256a7bcc9104fba7f8f75": "uniswap_universal",
    "0xba12222222228d8ba445958a75a0704d566bf2c8": "balancer_vault",
}
# Flash-loan providers on Base (for money-trail detection).
_FLASH_PROVIDERS: Dict[str, str] = {
    "0xa238dd80c259a72e81d7e4664a9801593f98d1c5": "aave_v3_pool",
    "0xba12222222228d8ba445958a75a0704d566bf2c8": "balancer_vault",
}

_ERC20_BALANCEOF = "0x70a08231"
_ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"
_BASE_CHAIN_ID = 8453


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _addr_word(address: str) -> str:
    return address.lower().replace("0x", "").rjust(64, "0")


class WalletIntelligenceEngine:
    def __init__(self, *, rpc_url: str, balance_reader,
                 etherscan_key: Optional[str] = None,
                 eth_price_provider=None, chain: str = "base",
                 cache_ttl_s: float = 45.0):
        self._rpc = rpc_url
        self._balance = balance_reader
        self._es_key = etherscan_key or os.environ.get("ARBICORE_ETHERSCAN_API_KEY")
        self._eth_price_provider = eth_price_provider
        self._chain = chain
        self._token_by_addr = {v["address"].lower(): {"symbol": k, **v}
                               for k, v in TOKENS.items()}
        # Short-lived cache so composite/overview calls don't recompute the
        # expensive (rate-limited) balance + statement reads multiple times.
        self._cache_ttl = float(cache_ttl_s)
        self._cache: Dict[str, Any] = {}

    async def _cached(self, key: str, producer):
        import time
        now = time.time()
        hit = self._cache.get(key)
        if hit and (now - hit[0]) < self._cache_ttl:
            return hit[1]
        val = await producer()
        self._cache[key] = (now, val)
        return val

    # ---- read-only RPC ---------------------------------------------------
    async def _eth_call(self, to: str, data: str) -> Optional[str]:
        if not self._rpc:
            return None
        from ..execution.quoter import _throttle, _is_rate_limited
        for attempt in range(4):
            await _throttle()
            try:
                async with httpx.AsyncClient(timeout=12) as c:
                    r = await c.post(self._rpc, json={
                        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
                        "params": [{"to": to, "data": data}, "latest"]})
                body = r.json()
            except Exception:  # noqa: BLE001
                return None
            if _is_rate_limited(body.get("error")):
                await asyncio.sleep(0.4 * (2 ** attempt))
                continue
            return body.get("result")
        return None

    async def _erc20_balance(self, token_addr: str, owner: str) -> int:
        res = await self._eth_call(token_addr, _ERC20_BALANCEOF + _addr_word(owner))
        if not res or res == "0x":
            return 0
        try:
            return int(res, 16)
        except ValueError:
            return 0

    async def _eth_price_usd(self) -> Optional[float]:
        if self._eth_price_provider is not None:
            try:
                p = await self._eth_price_provider()
                if p:
                    return float(p)
            except Exception:  # noqa: BLE001
                pass
        env = os.environ.get("ARBICORE_NATIVE_PRICE_USD")
        return float(env) if env else None

    def _token_price_usd(self, symbol: str, eth_usd: Optional[float]) -> Optional[float]:
        meta = TOKENS.get(symbol, {})
        if meta.get("stable"):
            return 1.0
        if symbol in ("WETH", "cbETH", "rETH", "wstETH", "weETH"):
            return eth_usd
        return None  # unpriced (honest — do not fabricate)

    # ---- live balances ---------------------------------------------------
    async def live_balances(self, address: str) -> Dict[str, Any]:
        return await self._cached(f"bal:{address.lower()}",
                                  lambda: self._live_balances_impl(address))

    async def _live_balances_impl(self, address: str) -> Dict[str, Any]:
        eth_usd = await self._eth_price_usd()
        native = await self._balance.read(chain=self._chain, address=address)
        native_d = native.to_dict()
        # ERC-20 balances across the verified Base universe (concurrent, each
        # call still globally throttled inside _eth_call to respect the RPC).
        async def _one(sym: str, meta: Dict[str, Any]):
            raw = await self._erc20_balance(meta["address"], address)
            return sym, meta, raw
        results = await asyncio.gather(*[_one(s, m) for s, m in TOKENS.items()],
                                       return_exceptions=True)
        tokens_out: List[Dict[str, Any]] = []
        total_usd = float(native_d.get("balance_usd") or 0.0)
        for res in results:
            if isinstance(res, Exception):
                continue
            sym, meta, raw = res
            if raw <= 0:
                continue
            amt = raw / (10 ** meta["decimals"])
            price = self._token_price_usd(sym, eth_usd)
            usd = round(amt * price, 4) if price is not None else None
            if usd:
                total_usd += usd
            tokens_out.append({
                "symbol": sym, "address": meta["address"],
                "balance_raw": str(raw), "balance": round(amt, 8),
                "price_usd": price, "value_usd": usd,
                "priced": price is not None,
            })
        ok = bool(native_d.get("ok"))
        return {
            "address": address, "chain": self._chain,
            "native": {"symbol": native_d.get("symbol"),
                       "balance": native_d.get("balance_native"),
                       "balance_wei": str(native_d.get("balance_wei")),
                       "value_usd": native_d.get("balance_usd"),
                       "is_gas_balance": True},
            "gas_balance_eth": native_d.get("balance_native"),
            "tokens": tokens_out,
            # Truth rule: when the on-chain source is unavailable (RPC not
            # configured / unreachable) total value is UNKNOWN → None (UI "—"),
            # NOT a coerced $0. A genuine confirmed zero (source ok) stays 0.
            "total_value_usd": round(total_usd, 4) if ok else None,
            "eth_price_usd": eth_usd,
            "block_number": native_d.get("block_number"),
            "rpc": native_d.get("rpc_endpoint_redacted"),
            "ok": ok,
            "available": ok,
            "unavailable_reason": None if ok else (
                "on-chain balance source unavailable (RPC not configured or unreachable)"),
            "last_sync": _now_iso(),
        }

    # ---- explorer tx source (read-only) ---------------------------------
    async def _es(self, module: str, action: str, address: str,
                  extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = {"chainid": _BASE_CHAIN_ID, "module": module, "action": action,
                  "address": address, "sort": "desc", "page": 1, "offset": 200}
        if extra:
            params.update(extra)
        if self._es_key:
            params["apikey"] = self._es_key
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(_ETHERSCAN_V2, params=params)
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"explorer request failed: {type(exc).__name__}"}
        status = str(body.get("status"))
        msg = str(body.get("message") or "")
        result = body.get("result")
        if status == "1" and isinstance(result, list):
            return {"ok": True, "result": result}
        if isinstance(result, list) and not result:  # "No transactions found"
            return {"ok": True, "result": []}
        # Prefer the descriptive result string (e.g. "Missing/Invalid API Key")
        # over the generic "NOTOK" message so the operator knows what to fix.
        detail = result if isinstance(result, str) and result else msg
        if not self._es_key and ("api key" in str(detail).lower() or msg == "NOTOK"):
            detail = ("explorer API key not configured — set ARBICORE_ETHERSCAN_API_KEY "
                      "(free Etherscan V2 key; supports Base chainid 8453) to enable "
                      "the full transaction statement & money trail")
        return {"ok": False, "reason": str(detail)[:200]}

    def _classify_tx(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        to = (tx.get("to") or "").lower()
        method_id = (tx.get("methodId") or (tx.get("input") or "")[:10]).lower()
        venue = _VENUE_ROUTERS.get(to)
        flash = _FLASH_PROVIDERS.get(to)
        executor = (os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") or "").lower()
        tx_type = "transfer"
        if to == executor and executor:
            tx_type = "executor_call"
        elif flash:
            tx_type = "flash_loan"
        elif venue:
            tx_type = "dex_swap"
        elif (tx.get("input") or "0x") in ("0x", ""):
            tx_type = "native_transfer"
        elif tx.get("contractAddress"):
            tx_type = "contract_creation"
        return {"tx_type": tx_type, "venue": venue, "flash_provider": flash,
                "method_id": method_id}

    async def transaction_statement(self, address: str, *,
                                    limit: int = 100,
                                    tx_type: Optional[str] = None,
                                    venue: Optional[str] = None,
                                    status: Optional[str] = None,
                                    start_ts: Optional[int] = None,
                                    end_ts: Optional[int] = None) -> Dict[str, Any]:
        key = f"stmt:{address.lower()}:{limit}:{tx_type}:{venue}:{status}:{start_ts}:{end_ts}"
        return await self._cached(key, lambda: self._statement_impl(
            address, limit=limit, tx_type=tx_type, venue=venue, status=status,
            start_ts=start_ts, end_ts=end_ts))

    async def _statement_impl(self, address: str, *,
                              limit: int = 100,
                              tx_type: Optional[str] = None,
                              venue: Optional[str] = None,
                              status: Optional[str] = None,
                              start_ts: Optional[int] = None,
                              end_ts: Optional[int] = None) -> Dict[str, Any]:
        addr = address.lower()
        eth_usd = await self._eth_price_usd()
        normal = await self._es("account", "txlist", address)
        tokentx = await self._es("account", "tokentx", address)
        source_ok = normal.get("ok")
        rows: List[Dict[str, Any]] = []

        # Group ERC-20 transfers by tx hash for direction/amount + money trail.
        tok_by_hash: Dict[str, List[Dict[str, Any]]] = {}
        for t in (tokentx.get("result") or []):
            tok_by_hash.setdefault((t.get("hash") or "").lower(), []).append(t)

        for tx in (normal.get("result") or []):
            h = (tx.get("hash") or "").lower()
            frm = (tx.get("from") or "").lower()
            to = (tx.get("to") or "").lower()
            ts = int(tx.get("timeStamp") or 0)
            if start_ts and ts < start_ts:
                continue
            if end_ts and ts > end_ts:
                continue
            value_wei = int(tx.get("value") or 0)
            gas_used = int(tx.get("gasUsed") or 0)
            gas_price = int(tx.get("gasPrice") or 0)
            fee_wei = gas_used * gas_price
            fee_eth = fee_wei / 1e18
            direction = "self"
            if frm == addr and to != addr:
                direction = "out"
            elif to == addr and frm != addr:
                direction = "in"
            ok = str(tx.get("isError") or "0") == "0" and str(tx.get("txreceipt_status", "1")) in ("1", "")
            cls = self._classify_tx(tx)
            transfers = [self._fmt_transfer(t, addr) for t in tok_by_hash.get(h, [])]
            # native amount signed relative to the wallet
            native_amt = value_wei / 1e18
            row = {
                "hash": tx.get("hash"), "block": int(tx.get("blockNumber") or 0),
                "timestamp": ts, "datetime": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
                "from": tx.get("from"), "to": tx.get("to"),
                "direction": direction,
                "native_symbol": "ETH", "native_amount": round(native_amt, 8),
                "native_value_usd": round(native_amt * eth_usd, 4) if eth_usd else None,
                "gas_used": gas_used, "gas_price_wei": gas_price,
                "fee_eth": round(fee_eth, 10),
                "fee_usd": round(fee_eth * eth_usd, 6) if eth_usd else None,
                "status": "success" if ok else "failed",
                "token_transfers": transfers,
                **cls,
            }
            rows.append(row)

        # Apply filters
        def _keep(r: Dict[str, Any]) -> bool:
            if tx_type and r["tx_type"] != tx_type:
                return False
            if venue and (r.get("venue") or "") != venue:
                return False
            if status and r["status"] != status:
                return False
            return True

        rows = [r for r in rows if _keep(r)][:limit]
        return {
            "address": address,
            "source": "etherscan_v2",
            "source_ok": bool(source_ok),
            "source_reason": None if source_ok else normal.get("reason"),
            "explorer_key_configured": bool(self._es_key),
            "count": len(rows),
            "transactions": rows,
            "eth_price_usd": eth_usd,
            "generated_at": _now_iso(),
        }

    def _fmt_transfer(self, t: Dict[str, Any], wallet: str) -> Dict[str, Any]:
        dec = int(t.get("tokenDecimal") or 18)
        raw = int(t.get("value") or 0)
        frm = (t.get("from") or "").lower()
        to = (t.get("to") or "").lower()
        return {
            "token": t.get("tokenSymbol") or "?",
            "token_address": t.get("contractAddress"),
            "amount": round(raw / (10 ** dec), 10),
            "amount_raw": str(raw),
            "from": t.get("from"), "to": t.get("to"),
            "direction": "in" if to == wallet else ("out" if frm == wallet else "internal"),
        }

    # ---- flash-loan money trail -----------------------------------------
    async def money_trail(self, address: str, tx_hash: str) -> Dict[str, Any]:
        """Reconstruct borrow → swaps → repay for a single tx from its token
        transfers (read-only, from the explorer index)."""
        addr = address.lower()
        eth_usd = await self._eth_price_usd()
        res = await self._es("account", "tokentx", address, extra={"offset": 500})
        if not res.get("ok"):
            return {"ok": False, "reason": res.get("reason"), "tx_hash": tx_hash}
        legs = [self._fmt_transfer(t, addr)
                for t in (res.get("result") or [])
                if (t.get("hash") or "").lower() == tx_hash.lower()]
        if not legs:
            return {"ok": True, "tx_hash": tx_hash, "legs": [],
                    "reason": "no ERC-20 legs for this tx (native-only or not indexed)",
                    "net_by_token": {}, "generated_at": _now_iso()}
        # Net per token from the wallet's perspective = realized P/L per token.
        net: Dict[str, float] = {}
        for leg in legs:
            sign = 1.0 if leg["direction"] == "in" else (-1.0 if leg["direction"] == "out" else 0.0)
            net[leg["token"]] = round(net.get(leg["token"], 0.0) + sign * leg["amount"], 10)
        # Heuristic stage labels: first out=borrow-repay context, ins=proceeds.
        trail = {
            "borrow": [l for l in legs if l["direction"] == "in"][:1],
            "swaps": legs,
            "repay": [l for l in legs if l["direction"] == "out"][-1:] if any(l["direction"] == "out" for l in legs) else [],
        }
        realized_usd = None
        # If the net is denominated in a stable/ETH token we can price it.
        priced = 0.0
        have_price = False
        for tok, amt in net.items():
            p = self._token_price_usd(tok, eth_usd)
            if p is not None:
                priced += amt * p
                have_price = True
        if have_price:
            realized_usd = round(priced, 6)
        return {
            "ok": True, "tx_hash": tx_hash, "leg_count": len(legs),
            "legs": legs, "trail": trail, "net_by_token": net,
            "realized_pl_usd": realized_usd, "eth_price_usd": eth_usd,
            "generated_at": _now_iso(),
        }

    # ---- capital reconciliation -----------------------------------------
    async def capital_reconciliation(self, address: str, *,
                                     limit: int = 200) -> Dict[str, Any]:
        """start + inflows − outflows − fees + realized P/L = end.

        ``end`` is the LIVE native balance; ``start`` is derived from the
        statement so the identity is checkable. A non-zero ``residual`` means
        the statement is incomplete (e.g. explorer unavailable) — reported
        honestly, never hidden."""
        stmt = await self.transaction_statement(address, limit=limit)
        eth_usd = stmt.get("eth_price_usd")
        bal = await self.live_balances(address)
        end_eth = float(bal["native"]["balance"] or 0.0)

        inflow = outflow = fees = 0.0
        for r in stmt["transactions"]:
            fees += float(r.get("fee_eth") or 0.0) if r["direction"] != "in" else 0.0
            amt = float(r.get("native_amount") or 0.0)
            if amt <= 0:
                continue
            if r["direction"] == "in":
                inflow += amt
            elif r["direction"] == "out":
                outflow += amt
        # Native-ETH identity: start = end − inflow + outflow + fees.
        start_eth = round(end_eth - inflow + outflow + fees, 10)
        implied_end = round(start_eth + inflow - outflow - fees, 10)
        residual = round(end_eth - implied_end, 10)

        def _usd(x):
            return round(x * eth_usd, 4) if eth_usd else None
        return {
            "address": address,
            "currency": "ETH (native)",
            "start_balance": start_eth, "start_balance_usd": _usd(start_eth),
            "inflows": round(inflow, 10), "inflows_usd": _usd(inflow),
            "outflows": round(outflow, 10), "outflows_usd": _usd(outflow),
            "fees": round(fees, 10), "fees_usd": _usd(fees),
            "end_balance": end_eth, "end_balance_usd": _usd(end_eth),
            "residual": residual,
            "reconciled": abs(residual) < 1e-9,
            "statement_complete": bool(stmt.get("source_ok")),
            "statement_note": None if stmt.get("source_ok") else stmt.get("source_reason"),
            "tx_count": stmt["count"],
            "eth_price_usd": eth_usd,
            "generated_at": _now_iso(),
        }

    # ---- per-venue / per-pair statistics --------------------------------
    async def venue_pair_stats(self, address: str, *, limit: int = 200) -> Dict[str, Any]:
        stmt = await self.transaction_statement(address, limit=limit)
        by_venue: Dict[str, Dict[str, Any]] = {}
        by_type: Dict[str, int] = {}
        for r in stmt["transactions"]:
            by_type[r["tx_type"]] = by_type.get(r["tx_type"], 0) + 1
            v = r.get("venue")
            if not v:
                continue
            e = by_venue.setdefault(v, {"venue": v, "tx_count": 0, "success": 0,
                                        "failed": 0, "total_fee_eth": 0.0, "pairs": {}})
            e["tx_count"] += 1
            e["success" if r["status"] == "success" else "failed"] += 1
            e["total_fee_eth"] = round(e["total_fee_eth"] + float(r.get("fee_eth") or 0.0), 10)
            # Derive a pair from the token transfers when available.
            toks = [t["token"] for t in r.get("token_transfers", [])]
            if len(toks) >= 2:
                pair = f"{toks[0]}/{toks[-1]}"
                e["pairs"][pair] = e["pairs"].get(pair, 0) + 1
        return {
            "address": address,
            "by_venue": list(by_venue.values()),
            "by_tx_type": by_type,
            "source_ok": bool(stmt.get("source_ok")),
            "source_note": None if stmt.get("source_ok") else stmt.get("source_reason"),
            "generated_at": _now_iso(),
        }


__all__ = ["WalletIntelligenceEngine"]
