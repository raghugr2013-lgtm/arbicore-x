"""Log-synced pool-state cache with block-staleness protection.

Holds pool reserves / CL state in memory, updated from chain event logs
(Sync / Swap / Mint / Burn) rather than per-quote RPC. Every read enforces a
max-staleness (in blocks) so the searcher never quotes on stale state — a
stale pool returns None (honest refusal), never a fabricated quote.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import amm_math


@dataclass
class PoolState:
    pool: str
    kind: str                       # "v2" | "v3" | "stable"
    token0: str
    token1: str
    fee_bps: int = 30
    # v2
    reserve0: float = 0.0
    reserve1: float = 0.0
    # v3
    liquidity: float = 0.0
    sqrt_p: float = 0.0
    tick: int = 0
    # stable
    balances: List[float] = field(default_factory=list)
    amp: float = 100.0
    block: int = 0
    updated_at: float = 0.0


class PoolStateCache:
    def __init__(self, *, max_staleness_blocks: int = 5,
                 clock=time.monotonic) -> None:
        self._pools: Dict[str, PoolState] = {}
        self._head_block: int = 0
        self._max_stale = int(max_staleness_blocks)
        self._clock = clock

    @property
    def head_block(self) -> int:
        return self._head_block

    def set_head_block(self, block: int) -> None:
        self._head_block = max(self._head_block, int(block))

    def upsert(self, state: PoolState) -> None:
        state.updated_at = self._clock()
        self._pools[state.pool] = state
        self.set_head_block(state.block)

    def apply_log(self, log: Dict) -> None:
        """Apply a decoded event log. Supported: 'Sync' (v2 reserves),
        'Swap'/'Mint'/'Burn' (v3 liquidity/sqrt update), 'StableBalances'."""
        pool = log.get("pool")
        st = self._pools.get(pool)
        if st is None:
            return
        block = int(log.get("block", st.block))
        ev = log.get("event")
        if ev == "Sync":
            st.reserve0 = float(log.get("reserve0", st.reserve0))
            st.reserve1 = float(log.get("reserve1", st.reserve1))
        elif ev in ("Swap", "Mint", "Burn"):
            if "liquidity" in log:
                st.liquidity = float(log["liquidity"])
            if "sqrt_p" in log:
                st.sqrt_p = float(log["sqrt_p"])
            if "tick" in log:
                st.tick = int(log["tick"])
            if "liquidity_delta" in log:
                # V3 Mint/Burn change GLOBAL (active) liquidity only when the
                # current tick is within the position range. Apply the signed
                # delta only in-range; Swap events remain authoritative.
                lo = log.get("tick_lower")
                hi = log.get("tick_upper")
                in_range = (lo is None or hi is None
                            or int(lo) <= st.tick < int(hi))
                if in_range:
                    st.liquidity = max(0.0, st.liquidity
                                       + float(log["liquidity_delta"]))
            if "reserve0" in log:
                st.reserve0 = float(log["reserve0"])
            if "reserve1" in log:
                st.reserve1 = float(log["reserve1"])
        elif ev == "Initialize":
            if "sqrt_p" in log:
                st.sqrt_p = float(log["sqrt_p"])
            if "tick" in log:
                st.tick = int(log["tick"])
        elif ev == "StableBalances":
            st.balances = [float(x) for x in log.get("balances", st.balances)]
        st.block = block
        st.updated_at = self._clock()
        self.set_head_block(block)

    def get(self, pool: str) -> Optional[PoolState]:
        st = self._pools.get(pool)
        if st is None:
            return None
        if self._head_block - st.block > self._max_stale:
            return None                      # stale-state protection: refuse
        return st

    def pools(self) -> List[str]:
        """All known pool keys (ignores staleness) — for WSS subscription."""
        return list(self._pools.keys())

    def all_states(self) -> List[PoolState]:
        """All PoolState skeletons/values (ignores staleness) — for bootstrap."""
        return list(self._pools.values())

    def quote(self, pool: str, token_in: str, amount_in: float) -> Optional[float]:
        """Local quote for one hop. None on stale/unknown/unpriceable state."""
        st = self.get(pool)
        if st is None or amount_in <= 0:
            return None
        if token_in not in (st.token0, st.token1):
            return None
        if st.kind == "v2":
            if st.reserve0 <= 0 or st.reserve1 <= 0:
                return None
            if token_in == st.token0:
                return amm_math.v2_amount_out(amount_in, st.reserve0, st.reserve1, st.fee_bps) or None
            return amm_math.v2_amount_out(amount_in, st.reserve1, st.reserve0, st.fee_bps) or None
        if st.kind == "v3":
            if st.liquidity <= 0 or st.sqrt_p <= 0:
                return None
            zfo = token_in == st.token0
            return amm_math.v3_amount_out(amount_in, st.liquidity, st.sqrt_p, zfo, st.fee_bps) or None
        if st.kind == "stable":
            if len(st.balances) < 2:
                return None
            i, j = (0, 1) if token_in == st.token0 else (1, 0)
            return amm_math.stable_amount_out(amount_in, i, j, st.balances, st.amp, st.fee_bps) or None
        return None


__all__ = ["PoolState", "PoolStateCache"]
