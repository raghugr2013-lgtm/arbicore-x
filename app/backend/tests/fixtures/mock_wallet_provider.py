"""ArbiCore X — Phase D D-4.1 MockWalletProvider test fixture.

REUSE WITH REFINEMENT from legacy `archive/backend/intel/providers/mock.py`.
Synthetic wallet provider for offline tests — produces deterministic buyer
records so D-4.1 source tests can exercise the HeliusWalletSource shape
without touching the network.

Provenance discipline: this fixture is TEST-ONLY. It is NEVER registered
as a real DiscoverySource. The arbicore_seed_fixture provenance applies
(SIMULATED).
"""
from __future__ import annotations

import hashlib
import random
import time
from typing import Any, Dict, List, Optional


class MockWalletProvider:
    """Deterministic synthetic Solana wallet provider."""

    name = "mock_wallet_provider"

    def __init__(self, *, seed: int = 1337,
                 wallets_per_token: int = 20,
                 fresh_wallet_pool: int = 200) -> None:
        self._seed = seed
        self._wallets_per_token = wallets_per_token
        self._fresh_wallet_pool = fresh_wallet_pool

    async def is_available(self) -> bool:
        return True

    async def recent_buyers(self, token_address: str, *, chain: str = "solana",
                             limit: int = 50,
                             reference_ts: Optional[float] = None
                             ) -> List[Dict[str, Any]]:
        # Seed deterministic per (token_address, seed) so tests are stable.
        rng = random.Random(f"{self._seed}:{token_address}")
        n = min(limit, self._wallets_per_token)
        out: List[Dict[str, Any]] = []
        now = reference_ts if reference_ts is not None else time.time()
        for i in range(n):
            seed = f"{self._seed}:{token_address}:{i}".encode()
            wallet = hashlib.sha1(seed).hexdigest()[:44]
            out.append({
                "wallet": wallet,
                "ts": now - rng.randint(60, 3600),
                "amount_sol": rng.uniform(0.1, 5.0),
                "amount_token": rng.uniform(1_000, 100_000),
                "tx_signature": hashlib.sha1(b"sig:" + seed).hexdigest()[:64],
            })
        return out

    async def wallet_transactions(self, wallet: str, *,
                                   since_ts: Optional[float] = None,
                                   limit: int = 100) -> List[Dict[str, Any]]:
        rng = random.Random(f"{self._seed}:tx:{wallet}")
        n = rng.randint(5, min(20, limit))
        now = time.time()
        out: List[Dict[str, Any]] = []
        for i in range(n):
            token_seed = f"{self._seed}:wallet:{wallet}:{i}".encode()
            token_mint = hashlib.sha1(token_seed).hexdigest()[:44]
            ts = now - rng.randint(60, 7 * 24 * 3600)
            if since_ts is not None and ts < since_ts:
                continue
            out.append({
                "wallet": wallet,
                "token_mint": token_mint,
                "ts": ts,
                "direction": rng.choice(["buy", "sell"]),
                "amount_sol": rng.uniform(0.05, 10.0),
                "tx_signature": hashlib.sha1(token_seed + b":sig").hexdigest()[:64],
            })
        return out
