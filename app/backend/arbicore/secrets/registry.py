"""Wave 6A · SecretRegistry — pluggable façade over one or more
``SecretBackend`` implementations.

Design:
    * The registry keeps a *default* backend for writes but can route
      reads across all registered backends (handle_id is namespaced).
    * Public REST NEVER returns plaintext or cipher material — only
      handle metadata (id, scope, provider, algorithm, created_at,
      label).
    * ``resolve()`` (which returns plaintext bytes) is call-restricted
      to internal signer flow (Wave 6D+); the registry exposes it via
      an intentionally-Pythonic method that the REST layer never
      forwards to.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .backends import CAPABILITY_SCOPES, SecretBackend, SecretHandle

logger = logging.getLogger("arbicore.secrets.registry")


class SecretRegistry:
    def __init__(self, default_backend: SecretBackend):
        self._backends: Dict[str, SecretBackend] = {default_backend.provider: default_backend}
        self._default = default_backend

    def register_backend(self, backend: SecretBackend) -> None:
        self._backends[backend.provider] = backend

    @property
    def default_provider(self) -> str:
        return self._default.provider

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "default_provider": self._default.provider,
            "providers": [
                {
                    "provider": b.provider,
                    "available": b.is_available(),
                    "is_default": (b.provider == self._default.provider),
                }
                for b in self._backends.values()
            ],
            "capability_scopes": list(CAPABILITY_SCOPES),
        }

    # --- ops surface ---

    async def put(self, plaintext: bytes, *, scope: str, algorithm: str,
                  label: str = "", provider: Optional[str] = None) -> SecretHandle:
        backend = self._backends[provider] if provider else self._default
        if not backend.is_available():
            raise RuntimeError(f"secret backend '{backend.provider}' unavailable")
        return await backend.put(plaintext, scope=scope, algorithm=algorithm,
                                 label=label)

    async def list_handles(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for backend in self._backends.values():
            if not backend.is_available():
                continue
            try:
                out.extend(await backend.list_handles())
            except Exception as exc:  # noqa: BLE001
                logger.warning("backend %s list failed: %s", backend.provider, exc)
        return out

    async def delete(self, handle_id: str) -> bool:
        # Try each backend — handles are opaque; only one backend owns any given id.
        for backend in self._backends.values():
            if not backend.is_available():
                continue
            try:
                if await backend.delete(handle_id):
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("backend %s delete failed: %s", backend.provider, exc)
        return False

    async def resolve(self, handle_id: str) -> Optional[bytes]:
        """INTERNAL — used by the signer flow only.  MUST NEVER be
        exposed through public REST."""
        for backend in self._backends.values():
            if not backend.is_available():
                continue
            try:
                b = await backend.get(handle_id)
                if b is not None:
                    return b
            except Exception as exc:  # noqa: BLE001
                logger.warning("backend %s resolve failed: %s", backend.provider, exc)
        return None
