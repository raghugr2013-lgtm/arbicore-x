"""Wallet + Coinstore Observer (READ-ONLY, NON-EXECUTING).

Reduces operator workload by auto-detecting on-chain milestones for the
USDT → BlockDAG Live Swap → BDAG → Coinstore → Sell → USDT cycle, plus
a one-line manual stamp for the Coinstore sell (the only step that
requires an authenticated exchange API).

Chain data sources (validated by diagnostics/blockdag_diag.py on 2026-06-15)
---------------------------------------------------------------------------
  • BlockDAG mainnet:  rpc.bdagscan.com (primary EVM RPC) + rpc.blockdag.engineering
    (secondary RPC, used as failover). Chain id 1404. We use **RPC block-walking**
    not an explorer txlist — neither bdagscan.com nor explorer.blockdag.engineering
    expose an etherscan-style address-tx API (HTML/Cloudflare-locked respectively).
  • BSC mainnet: BSCScan etherscan-style API for USDT BEP20 withdrawals.

Architecture
------------
Config (single doc in `observer_config`):
  - operator_bdag_address, operator_bsc_address
  - coinstore_bdag_deposit_address, coinstore_usdt_hot_wallet_address
  - blockdag_rpc_primary, blockdag_rpc_secondary
  - bscscan_api_base, bscscan_api_key
  - poll_interval_s (default 60), enabled (default False)
  - max_blocks_per_tick (default 200)
  - force_primary_down (debug toggle to prove failover)

Events (`observer_events`): one row per detected chain transaction, with a
candidate cycle match + status PROPOSED / AUTO_ADVANCED / UNMATCHED.

Sells (`coinstore_sells`): one row per operator stamp (sell-side).

Auto-advance rule (only when match is unambiguous):
  * Single open cycle in the correct prior state + amount within ±2 % →
    auto-transition.
  * Multiple candidates → PROPOSED (operator picks via UI).
  * No candidate → UNMATCHED (event still recorded for audit).

Hard guardrails reaffirmed: NO transaction signing. NO submission. NO
autonomous trading. NO fund movement. The poller only READS from public
chain RPCs; chain calls are skipped while config is dormant.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from core.models import new_id, now_iso
from services import db
from services.execution import arbitrage_cycles
from services.execution.blockdag_rpc import (DEFAULT_PRIMARY, DEFAULT_SECONDARY,
                                              EXPECTED_CHAIN_ID, ChainRPCError,
                                              BlockDAGRPCClient)

logger = logging.getLogger(__name__)

CONFIG_COLL = "observer_config"
EVENTS_COLL = "observer_events"
SELLS_COLL = "coinstore_sells"
CURSOR_COLL = "observer_block_cursor"
DIAG_COLL = "observer_diagnostics"
CONFIG_KEY = "wallet_observer"

DEFAULT_POLL_S = 60
AMOUNT_TOLERANCE_PCT = 2.0  # ±2 % match window for cycle auto-link
MAX_TX_PER_POLL = 25
DEFAULT_MAX_BLOCKS_PER_TICK = 200
INITIAL_BACKFILL_BLOCKS = 1000   # first-time scan window per address

ALLOWED_KINDS_LEGACY = ("etherscan", "blockscout", "custom")  # legacy compat for BSC

# Cycle states each milestone can auto-advance from → to
ADVANCE_RULES = {
    "BDAG_RECEIVED": {
        "from_states": {"QUOTED", "SWAP_SUBMITTED", "SWAP_CONFIRMED"},
        "to_state": "BDAG_RECEIVED",
        "amount_field": "bdag_expected",
    },
    "TRANSFER_SUBMITTED": {
        "from_states": {"BDAG_RECEIVED"},
        "to_state": "TRANSFER_SUBMITTED",
        "amount_field": "bdag_expected",
    },
    "DEPOSIT_CONFIRMED": {
        "from_states": {"TRANSFER_SUBMITTED"},
        "to_state": "DEPOSIT_CONFIRMED",
        "amount_field": "bdag_expected",
    },
    "WITHDRAWAL_COMPLETED": {
        "from_states": {"SOLD"},
        "to_state": "WITHDRAWN",
        "amount_field": "actuals.usdt_received",
    },
}


# ----------------------------- indexes / seed ---------------------------------

async def ensure_indexes():
    await db.db[CONFIG_COLL].create_index("key", unique=True)
    await db.db[EVENTS_COLL].create_index("tx_hash")
    await db.db[EVENTS_COLL].create_index([("chain", 1), ("detected_at", -1)])
    await db.db[EVENTS_COLL].create_index([("matched_cycle_id", 1), ("detected_at", -1)])
    await db.db[SELLS_COLL].create_index([("cycle_id", 1), ("stamped_at", -1)])
    await db.db[CURSOR_COLL].create_index([("chain", 1), ("address", 1)], unique=True)
    await db.db[DIAG_COLL].create_index([("ran_at", -1)])


def _default_config() -> dict:
    return {
        "key": CONFIG_KEY,
        "enabled": False,
        "poll_interval_s": DEFAULT_POLL_S,
        # operator wallets
        "operator_bdag_address": None,
        "operator_bsc_address": None,
        # exchange-side
        "coinstore_bdag_deposit_address": None,
        "coinstore_usdt_hot_wallet_address": None,
        # chain data sources — BlockDAG mainnet uses RPC block-walking with
        # automatic primary→secondary failover (no usable explorer API exists).
        "blockdag_rpc_primary": DEFAULT_PRIMARY,
        "blockdag_rpc_secondary": DEFAULT_SECONDARY,
        "bscscan_api_base": "https://api.bscscan.com/api",
        "bscscan_api_key": None,
        # tuning
        "max_blocks_per_tick": DEFAULT_MAX_BLOCKS_PER_TICK,
        "force_primary_down": False,   # debug toggle to prove failover
        # bookkeeping
        "last_poll_at": None,
        "last_poll_result": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


async def _read() -> dict:
    doc = await db.db[CONFIG_COLL].find_one({"key": CONFIG_KEY}, {"_id": 0})
    if not doc:
        doc = _default_config()
        await db.db[CONFIG_COLL].insert_one(dict(doc))
    # one-time migration: older docs had blockdag_explorer_base/kind — clear them
    if "blockdag_explorer_base" in doc or "blockdag_explorer_kind" in doc:
        await db.db[CONFIG_COLL].update_one(
            {"key": CONFIG_KEY},
            {"$unset": {"blockdag_explorer_base": "", "blockdag_explorer_kind": ""},
             "$setOnInsert": {}},
        )
        doc.pop("blockdag_explorer_base", None)
        doc.pop("blockdag_explorer_kind", None)
    # backfill missing new keys with defaults (e.g. user upgraded mid-flight)
    defaults = _default_config()
    for k, v in defaults.items():
        if k not in doc:
            doc[k] = v
    return doc


async def get_config() -> dict:
    return await _read()


def _dormancy_reasons(cfg: dict) -> list[str]:
    """Return human-readable reasons the observer is dormant (empty = ready)."""
    reasons = []
    if not cfg.get("enabled"):
        reasons.append("Observer is disabled — toggle 'Enable observer' to start polling.")
    have_bdag = bool(cfg.get("operator_bdag_address") and cfg.get("blockdag_rpc_primary"))
    have_bsc = bool(cfg.get("operator_bsc_address"))
    if not have_bdag and not have_bsc:
        reasons.append("No chain leg configured — set operator_bdag_address (BlockDAG RPC "
                       "primary defaults to rpc.bdagscan.com) and/or operator_bsc_address.")
    return reasons


async def update_config(patch: dict) -> dict:
    cfg = await _read()
    allowed = {"enabled", "poll_interval_s",
               "operator_bdag_address", "operator_bsc_address",
               "coinstore_bdag_deposit_address", "coinstore_usdt_hot_wallet_address",
               "blockdag_rpc_primary", "blockdag_rpc_secondary",
               "bscscan_api_base", "bscscan_api_key",
               "max_blocks_per_tick", "force_primary_down"}
    update: dict[str, Any] = {}
    for k, v in (patch or {}).items():
        if k not in allowed:
            continue
        if k == "poll_interval_s":
            v = max(15, int(v or DEFAULT_POLL_S))
        elif k == "max_blocks_per_tick":
            v = max(10, min(1000, int(v or DEFAULT_MAX_BLOCKS_PER_TICK)))
        elif k in ("enabled", "force_primary_down"):
            v = bool(v)
        elif isinstance(v, str):
            v = v.strip() or None
        update[k] = v
    if not update:
        return cfg
    update["updated_at"] = now_iso()
    await db.db[CONFIG_COLL].update_one({"key": CONFIG_KEY}, {"$set": update}, upsert=True)
    # propagate force_primary_down to the live client if any
    if "force_primary_down" in update and poller.rpc:
        poller.rpc.force_primary_down(update["force_primary_down"])
    # if RPC URLs changed, rebuild the live client
    if {"blockdag_rpc_primary", "blockdag_rpc_secondary"} & update.keys():
        poller.rebuild_rpc()
    return await _read()


# ----------------------------- chain pollers ----------------------------------

async def _fetch_blockdag_txs(cfg: dict, rpc: BlockDAGRPCClient) -> list[dict]:
    """Block-walking implementation. Polls a bounded range of the BlockDAG
    chain since the cursor we persisted last tick and returns the native
    transactions touching the operator's address.
    """
    addr = (cfg.get("operator_bdag_address") or "").strip()
    if not addr:
        return []
    try:
        head = await rpc.block_number()
    except ChainRPCError as e:
        logger.warning("[wallet_observer] block_number failed: %s", e)
        return []
    cur = await db.db[CURSOR_COLL].find_one({"chain": "BDAG", "address": addr.lower()},
                                            {"_id": 0})
    last = (cur or {}).get("last_scanned_block")
    if last is None:
        # first run — backfill a small recent window so we don't crawl from genesis
        last = max(0, head - INITIAL_BACKFILL_BLOCKS)
    max_window = int(cfg.get("max_blocks_per_tick") or DEFAULT_MAX_BLOCKS_PER_TICK)
    from_block = last + 1
    to_block = min(head, last + max_window)
    if to_block < from_block:
        return []
    try:
        txs = await rpc.scan_address(addr, from_block, to_block)
    except ChainRPCError as e:
        logger.warning("[wallet_observer] scan_address failed: %s", e)
        return []
    await db.db[CURSOR_COLL].update_one(
        {"chain": "BDAG", "address": addr.lower()},
        {"$set": {"chain": "BDAG", "address": addr.lower(),
                  "last_scanned_block": to_block, "head_block": head,
                  "scanned_at": now_iso()}},
        upsert=True,
    )
    return txs


async def _fetch_bsc_usdt_txs(cfg: dict) -> list[dict]:
    """USDT BEP20 token transfers for the operator's BSC address via BSCScan."""
    addr = (cfg.get("operator_bsc_address") or "").strip()
    base = (cfg.get("bscscan_api_base") or "https://api.bscscan.com/api").strip()
    api_key = (cfg.get("bscscan_api_key") or "").strip()
    if not addr:
        return []
    USDT_BEP20 = "0x55d398326f99059fF775485246999027B3197955"
    params = {
        "module": "account", "action": "tokentx",
        "contractaddress": USDT_BEP20, "address": addr,
        "sort": "desc", "page": 1, "offset": MAX_TX_PER_POLL,
    }
    if api_key:
        params["apikey"] = api_key
    try:
        async with httpx.AsyncClient(timeout=12.0) as cx:
            r = await cx.get(base, params=params)
            r.raise_for_status()
            body = r.json()
            items = body.get("result", []) if isinstance(body.get("result"), list) else []
            out = []
            for it in items[:MAX_TX_PER_POLL]:
                try:
                    dec = int(it.get("tokenDecimal") or 18)
                    val = int(it.get("value") or 0) / (10 ** dec)
                except (TypeError, ValueError):
                    val = None
                out.append({
                    "tx_hash": it.get("hash"),
                    "from": it.get("from"),
                    "to": it.get("to"),
                    "value": val,
                    "asset": "USDT",
                    "ts": it.get("timeStamp"),
                })
            return out
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("[wallet_observer] BSCScan fetch failed: %s", e)
        return []


def _decimal_from_wei(v) -> float | None:
    if v is None:
        return None
    try:
        return int(v) / 1e18
    except (TypeError, ValueError):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


# ----------------------------- cycle matching ---------------------------------

def _within_tolerance(actual: float, expected: float) -> bool:
    if expected is None or actual is None or expected <= 0:
        return False
    return abs(actual - expected) / expected * 100 <= AMOUNT_TOLERANCE_PCT


async def _match_candidates(milestone: str, amount: float | None) -> list[dict]:
    rule = ADVANCE_RULES[milestone]
    cur = db.db[arbitrage_cycles.COLL].find(
        {"state": {"$in": list(rule["from_states"])}}, {"_id": 0},
        sort=[("created_at", -1)],
    )
    out = []
    async for c in cur:
        # extract the comparable amount per rule
        af = rule["amount_field"]
        if af.startswith("actuals."):
            cand_amt = (c.get("actuals") or {}).get(af.split(".", 1)[1])
        else:
            cand_amt = c.get(af)
        if amount is None or _within_tolerance(amount, cand_amt):
            out.append({"cycle_id": c["id"], "state": c["state"],
                        "expected_amount": cand_amt})
    return out


def _classify_event(cfg: dict, chain: str, tx: dict) -> dict | None:
    """Return {milestone, direction} or None if not classifiable.

    Lower-case addresses for comparison.
    """
    op_bdag = (cfg.get("operator_bdag_address") or "").lower()
    cs_deposit = (cfg.get("coinstore_bdag_deposit_address") or "").lower()
    op_bsc = (cfg.get("operator_bsc_address") or "").lower()
    cs_hot = (cfg.get("coinstore_usdt_hot_wallet_address") or "").lower()

    frm = (tx.get("from") or "").lower()
    to = (tx.get("to") or "").lower()

    if chain == "BDAG":
        if op_bdag and to == op_bdag and frm != op_bdag:
            return {"milestone": "BDAG_RECEIVED", "direction": "IN"}
        if op_bdag and frm == op_bdag:
            if cs_deposit and to == cs_deposit:
                return {"milestone": "TRANSFER_SUBMITTED", "direction": "OUT"}
            return {"milestone": "TRANSFER_SUBMITTED", "direction": "OUT"}
        # tx observed at the Coinstore deposit address itself (rare unless polled)
        if cs_deposit and to == cs_deposit:
            return {"milestone": "DEPOSIT_CONFIRMED", "direction": "IN"}
        return None
    if chain == "BSC":
        if op_bsc and to == op_bsc and (not cs_hot or frm == cs_hot):
            return {"milestone": "WITHDRAWAL_COMPLETED", "direction": "IN"}
        return None
    return None


async def _record_event(cfg: dict, chain: str, tx: dict) -> dict | None:
    """Insert a normalised observer event if it doesn't already exist, attempt
    cycle auto-link, and auto-advance the cycle on unambiguous match."""
    txh = tx.get("tx_hash")
    if not txh:
        return None
    existing = await db.db[EVENTS_COLL].find_one({"tx_hash": txh, "chain": chain}, {"_id": 0})
    if existing:
        return None
    classified = _classify_event(cfg, chain, tx)
    if not classified:
        return None
    milestone = classified["milestone"]
    candidates = await _match_candidates(milestone, tx.get("value"))
    status = "UNMATCHED"
    matched_cycle = None
    if len(candidates) == 1:
        status = "AUTO_ADVANCED"
        matched_cycle = candidates[0]["cycle_id"]
    elif len(candidates) > 1:
        status = "PROPOSED"
    ev = {
        "id": new_id(),
        "chain": chain,
        "tx_hash": txh,
        "from_addr": tx.get("from"),
        "to_addr": tx.get("to"),
        "amount": tx.get("value"),
        "asset": tx.get("asset"),
        "direction": classified["direction"],
        "milestone": milestone,
        "block_ts": tx.get("ts"),
        "candidates": candidates,
        "matched_cycle_id": matched_cycle,
        "status": status,
        "detected_at": now_iso(),
        "created_at": now_iso(),
    }
    await db.db[EVENTS_COLL].insert_one(dict(ev))
    if status == "AUTO_ADVANCED" and matched_cycle:
        rule = ADVANCE_RULES[milestone]
        try:
            await arbitrage_cycles.transition(matched_cycle, rule["to_state"],
                                              note=f"Auto-advanced by observer · tx={txh[:10]}…")
        except ValueError as e:
            logger.info("[wallet_observer] auto-advance skipped (%s): %s", matched_cycle, e)
    ev["_id"] = None
    ev.pop("_id", None)
    return ev


# ----------------------------- recent events / linking ------------------------

async def list_events(limit: int = 50, status: str | None = None) -> list[dict]:
    q: dict = {}
    if status:
        q["status"] = status
    return await db.db[EVENTS_COLL].find(q, {"_id": 0},
                                         sort=[("detected_at", -1)]).to_list(max(1, min(limit, 200)))


async def link_event_to_cycle(event_id: str, cycle_id: str) -> dict:
    ev = await db.db[EVENTS_COLL].find_one({"id": event_id}, {"_id": 0})
    if not ev:
        raise ValueError("event not found")
    rule = ADVANCE_RULES.get(ev["milestone"])
    if not rule:
        raise ValueError(f"milestone {ev['milestone']} has no advance rule")
    cyc = await arbitrage_cycles.get(cycle_id)
    if not cyc:
        raise ValueError("cycle not found")
    if cyc["state"] not in rule["from_states"]:
        raise ValueError(f"cycle in state {cyc['state']} cannot accept {ev['milestone']}")
    await arbitrage_cycles.transition(cycle_id, rule["to_state"],
                                      note=f"Operator-linked observer event · tx={ev['tx_hash'][:10]}…")
    await db.db[EVENTS_COLL].update_one(
        {"id": event_id},
        {"$set": {"matched_cycle_id": cycle_id, "status": "MANUAL_CONFIRMED"}},
    )
    return await db.db[EVENTS_COLL].find_one({"id": event_id}, {"_id": 0})


# ----------------------------- Coinstore sell stamp ---------------------------

async def stamp_coinstore_sell(cycle_id: str, order_id: str, bdag_sold: float,
                               usdt_received: float, fee_usdt: float | None = None,
                               best_bid_at_sell: float | None = None) -> dict:
    cyc = await arbitrage_cycles.get(cycle_id)
    if not cyc:
        raise ValueError("cycle not found")
    if cyc["state"] in ("CLOSED", "ABORTED", "SOLD", "WITHDRAWN"):
        raise ValueError(f"cycle is already past SOLD ({cyc['state']})")
    bdag_sold = float(bdag_sold)
    usdt_received = float(usdt_received)
    if bdag_sold <= 0 or usdt_received <= 0:
        raise ValueError("bdag_sold and usdt_received must be > 0")
    sell_avg = round(usdt_received / bdag_sold, 12)
    actuals_update = {
        "actuals.usdt_received": round(usdt_received, 6),
        "actuals.sell_price_avg": sell_avg,
    }
    if best_bid_at_sell is not None:
        actuals_update["actuals.best_bid_at_sell"] = float(best_bid_at_sell)
        bid_q = cyc.get("best_bid_at_quote")
        if bid_q:
            actuals_update["actuals.drift_pct_at_sell"] = round(
                (float(best_bid_at_sell) - bid_q) / bid_q * 100, 4)
    # realized profit + ROI
    invest = cyc.get("input_amount_usd") or 0
    if invest > 0:
        net_profit = round(usdt_received - invest - (fee_usdt or 0), 6)
        actuals_update["actuals.net_profit_usd"] = net_profit
        actuals_update["actuals.realized_roi_pct"] = round(net_profit / invest * 100, 4)
    updated = await arbitrage_cycles.transition(
        cycle_id, "SOLD",
        note=f"Coinstore sell · order={order_id} · {bdag_sold} BDAG → {usdt_received} USDT",
        **actuals_update,
    )
    sell = {
        "id": new_id(),
        "cycle_id": cycle_id,
        "order_id": str(order_id),
        "bdag_sold": bdag_sold,
        "usdt_received": usdt_received,
        "fee_usdt": fee_usdt,
        "sell_price_avg": sell_avg,
        "best_bid_at_sell": best_bid_at_sell,
        "stamped_at": now_iso(),
    }
    await db.db[SELLS_COLL].insert_one(dict(sell))
    return {"sell": sell, "cycle": updated}


async def list_sells(limit: int = 50) -> list[dict]:
    return await db.db[SELLS_COLL].find({}, {"_id": 0},
                                        sort=[("stamped_at", -1)]).to_list(max(1, min(limit, 200)))


# ----------------------------- background poller ------------------------------

class _ObserverPoller:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_result: dict | None = None
        self.rpc: BlockDAGRPCClient | None = None

    def rebuild_rpc(self, primary: str | None = None, secondary: str | None = None) -> None:
        """(Re)create the RPC client with current URLs + propagate force-down."""
        self.rpc = BlockDAGRPCClient(primary=primary, secondary=secondary)

    async def _ensure_rpc(self, cfg: dict) -> BlockDAGRPCClient:
        prim = (cfg.get("blockdag_rpc_primary") or DEFAULT_PRIMARY).strip()
        sec = (cfg.get("blockdag_rpc_secondary") or "").strip() or None
        if (not self.rpc or self.rpc.primary != prim.rstrip("/")
                or (self.rpc.secondary or "") != (sec or "").rstrip("/")):
            self.rpc = BlockDAGRPCClient(primary=prim, secondary=sec)
        self.rpc.force_primary_down(bool(cfg.get("force_primary_down")))
        return self.rpc

    async def _tick(self) -> dict:
        cfg = await _read()
        if not cfg.get("enabled"):
            self._last_result = {"ran_at": now_iso(), "skipped": True,
                                 "reason": "observer disabled"}
            return self._last_result
        rpc = await self._ensure_rpc(cfg)
        new_events = 0
        bdag_txs: list[dict] = []
        if cfg.get("operator_bdag_address"):
            bdag_txs = await _fetch_blockdag_txs(cfg, rpc)
        for tx in bdag_txs:
            ev = await _record_event(cfg, "BDAG", tx)
            if ev:
                new_events += 1
        bsc_txs = await _fetch_bsc_usdt_txs(cfg) if cfg.get("operator_bsc_address") else []
        for tx in bsc_txs:
            ev = await _record_event(cfg, "BSC", tx)
            if ev:
                new_events += 1
        res = {"ran_at": now_iso(), "skipped": False,
               "bdag_tx_seen": len(bdag_txs), "bsc_tx_seen": len(bsc_txs),
               "new_events": new_events,
               "rpc_health": rpc.health_snapshot() if rpc else None}
        self._last_result = res
        await db.db[CONFIG_COLL].update_one(
            {"key": CONFIG_KEY},
            {"$set": {"last_poll_at": res["ran_at"], "last_poll_result": res}},
        )
        return res

    async def run_once(self) -> dict:
        try:
            return await self._tick()
        except Exception as e:  # noqa: BLE001  defensive — never crash poller
            logger.exception("[wallet_observer] tick failed: %s", e)
            return {"ran_at": now_iso(), "skipped": True, "error": str(e)}

    async def _loop(self):
        while not self._stop.is_set():
            cfg = await _read()
            await self.run_once()
            interval = max(15, int(cfg.get("poll_interval_s") or DEFAULT_POLL_S))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def start(self):
        if self._task and not self._task.done():
            return
        # opt-out via env for dev/testing
        if (os.environ.get("ARBICORE_OBSERVER_DISABLE") or "").lower() in ("1", "true", "yes"):
            logger.info("[wallet_observer] disabled via env")
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("[wallet_observer] started")

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None

    @property
    def last_result(self) -> dict | None:
        return self._last_result


poller = _ObserverPoller()


# ----------------------------- status / summary -------------------------------

async def status() -> dict:
    cfg = await _read()
    recent = await list_events(limit=10)
    proposed = await db.db[EVENTS_COLL].count_documents({"status": "PROPOSED"})
    unmatched = await db.db[EVENTS_COLL].count_documents({"status": "UNMATCHED"})
    auto = await db.db[EVENTS_COLL].count_documents({"status": "AUTO_ADVANCED"})
    manual = await db.db[EVENTS_COLL].count_documents({"status": "MANUAL_CONFIRMED"})
    sells_count = await db.db[SELLS_COLL].count_documents({})
    sells_recent = await list_sells(limit=5)
    last_diag = await db.db[DIAG_COLL].find_one({}, {"_id": 0},
                                                 sort=[("ran_at", -1)])
    rpc_health = poller.rpc.health_snapshot() if poller.rpc else None
    cursors = await db.db[CURSOR_COLL].find({}, {"_id": 0}).to_list(20)
    return {
        "phase": "Wallet + Coinstore Observer (read-only)",
        "generated_at": now_iso(),
        "config": {k: v for k, v in cfg.items() if k != "_id"},
        "dormancy_reasons": _dormancy_reasons(cfg),
        "ready": (len(_dormancy_reasons(cfg)) == 0),
        "last_poll_result": cfg.get("last_poll_result") or poller.last_result,
        "rpc_health": rpc_health,
        "block_cursors": cursors,
        "last_diagnostic": last_diag,
        "counters": {"proposed": proposed, "unmatched": unmatched,
                     "auto_advanced": auto, "manual_confirmed": manual,
                     "sells": sells_count},
        "recent_events": recent,
        "recent_sells": sells_recent,
        "advance_rules": {k: {"from_states": list(v["from_states"]),
                              "to_state": v["to_state"],
                              "amount_field": v["amount_field"]}
                          for k, v in ADVANCE_RULES.items()},
        "guardrails": {"execution_enabled": False, "wallet_enabled": False,
                       "transaction_signing": False, "autonomous_execution": False,
                       "fund_movement": False,
                       "note": "Observer only READS public chain RPCs and operator-stamped data."},
    }


# ----------------------------- diagnostic -------------------------------------

async def run_diagnostic(test_address: str | None = None,
                         test_tx: str | None = None,
                         expected_chain_id: int | None = None) -> dict:
    """Run a live connectivity probe against the configured RPC endpoints +
    explorer URLs, store the result in observer_diagnostics, and return it.
    """
    from diagnostics.blockdag_diag import run as _run_full
    report = await _run_full() if (test_address is None and test_tx is None) else \
        await _run_with_overrides(test_address, test_tx, expected_chain_id)
    # derive recommendation
    p = report["rpc_primary"]
    s = report["rpc_secondary"]
    primary_ok = p["score"] >= 50 and p["evm"]["eth_chainId"]["matches_expected"]
    secondary_ok = s["score"] >= 50 and s["evm"]["eth_chainId"]["matches_expected"]
    report["recommendation"] = {
        "primary": p["name"] if primary_ok else (s["name"] if secondary_ok else None),
        "backup":  s["name"] if (primary_ok and secondary_ok) else None,
        "reliability_score": max(p["score"], s["score"]),
        "verdict": ("PASS" if primary_ok or secondary_ok else "FAIL"),
        "notes": [],
    }
    if not primary_ok:
        report["recommendation"]["notes"].append(
            f"Primary {p['name']} failed reliability gate (score {p['score']})."
        )
    if not secondary_ok:
        report["recommendation"]["notes"].append(
            f"Secondary {s['name']} unusable (score {s['score']}, "
            f"reach stability {s['reachability']['stability_pct']}%, "
            f"likely Cloudflare/WAF block)."
        )
    report["ran_at_iso"] = now_iso()
    # Mongo can only store 8-byte ints — coerce any huge values (wei balances)
    # to strings so the diagnostic doc serialises cleanly.
    await db.db[DIAG_COLL].insert_one(_mongo_safe(dict(report)))
    report.pop("_id", None)
    return report


def _mongo_safe(obj):
    """Recursively coerce ints that overflow MongoDB's int64 to strings."""
    if isinstance(obj, dict):
        return {k: _mongo_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mongo_safe(v) for v in obj]
    if isinstance(obj, int) and (obj > (1 << 63) - 1 or obj < -(1 << 63)):
        return str(obj)
    return obj


async def _run_with_overrides(addr: str | None, tx: str | None,
                              chain_id: int | None) -> dict:
    """Internal: rerun diagnostic with custom test data (operator-supplied)."""
    from diagnostics import blockdag_diag as bd
    if addr:
        bd.TEST_ADDR = addr
    if tx:
        bd.TEST_TX = tx
    if chain_id is not None:
        bd.EXPECTED_CHAIN_ID = int(chain_id)
    return await bd.run()
