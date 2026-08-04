"""Phase 7 — Flash Loan Operator preparation.

Provides the WalletCustodyProvider and SecretProvider registrations plus
a FlashLoan simulation harness. NO borrowing happens. Every actual
borrow API call is gated by the Phase-8 :class:`ApprovalGate` and the
kill switch — both of which default to REFUSE.

Concrete providers included:

  * :class:`NoOpWalletProvider` — placeholder custody. Refuses to sign.
  * :class:`EnvSecretProvider`  — reads secrets from process env only.

Real Aave / Balancer / hardware-wallet / MPC providers plug into the
same protocols in a follow-up sprint once you approve credentials.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ..providers.base import (
    ProviderError, ProviderKind, SecretProvider, WalletCustodyProvider,
)

logger = logging.getLogger(__name__)


class NoOpWalletProvider:
    """Custody stub that ONLY lists addresses (empty) and REFUSES to sign.

    Purpose: satisfies the Phase-7 abstraction so the executor can be
    built and unit-tested without depending on a live custody backend.
    """
    kind = ProviderKind.WALLET_CUSTODY
    custody_kind = "noop"

    def __init__(self, provider_id: str = "wallet_noop_v0") -> None:
        self.provider_id = provider_id

    async def list_addresses(self, chain: str) -> List[str]:
        return []

    async def sign_transaction(self, chain: str, address: str,
                                unsigned_tx: Dict[str, Any]
                                ) -> Dict[str, Any]:
        raise ProviderError(
            "wallet_noop_v0 refuses to sign — attach a real "
            "WalletCustodyProvider (Ledger / MPC / KMS) before enabling "
            "any execution path", retryable=False)

    async def health_probe(self) -> Dict[str, Any]:
        return {"provider_id": self.provider_id,
                "custody_kind": self.custody_kind,
                "signs": False}


class EnvSecretProvider:
    """Reads secrets from the process env only. Never writes back."""
    kind = ProviderKind.SECRET
    backend = "env"

    def __init__(self, provider_id: str = "secret_env_v0",
                  allowed_prefixes: Optional[List[str]] = None) -> None:
        self.provider_id = provider_id
        self._allowed = list(
            allowed_prefixes or ["ARBICORE_", "PROVIDER_", "WALLET_"])

    def _allowed_key(self, key: str) -> bool:
        return any(key.startswith(p) for p in self._allowed)

    async def get(self, key: str) -> Optional[str]:
        if not self._allowed_key(key):
            return None
        return os.environ.get(key)

    async def list_keys(self, prefix: str = "") -> List[str]:
        return [k for k in os.environ.keys()
                if k.startswith(prefix) and self._allowed_key(k)]

    async def health_probe(self) -> Dict[str, Any]:
        return {"provider_id": self.provider_id, "backend": self.backend,
                "allowed_prefixes": self._allowed,
                "visible_key_count": len(
                    [k for k in os.environ.keys()
                     if self._allowed_key(k)])}


__all__ = [
    "NoOpWalletProvider", "EnvSecretProvider",
    "WalletCustodyProvider", "SecretProvider",
]
