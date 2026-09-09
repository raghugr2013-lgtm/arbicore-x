"""H08 (P1 Batch 2) — versioned receiver capability, fail-closed.

A thin, READ-ONLY capability/version layer over ``executor_registry``. It does
NOT deploy, sign, broadcast, or mutate anything. Its sole job is to answer, per
chain and per provider/venue, whether the deployed receiver can be TRUSTED to
execute — and to expose its version/ABI provenance — so callers can reject
unsupported venues and un-versioned/unverified receivers by default.

Fail-closed rules:
  * A chain with no ``deploy_status == "success"`` record (or a missing/invalid
    address) is NOT execution-capable — every provider is rejected.
  * A provider/venue is supported ONLY if the deployment record EXPLICITLY lists
    it in ``supported_providers``. An absent list ⇒ no venue supported (we never
    infer capability from constructor args — that would fabricate support).
  * ``receiver_version`` / ``abi_version`` are surfaced from the record; when
    absent they are reported as ``"unversioned"`` with ``version_verified=False``
    so an un-versioned receiver cannot be treated as a verified one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from arbicore.execution.executor_registry import deployed_address, get_deployment


@dataclass(frozen=True)
class ReceiverCapability:
    chain: str
    deployed: bool
    address: Optional[str]
    receiver_version: str
    abi_version: str
    version_verified: bool
    bytecode_verified: bool
    supported_providers: List[str]
    constructor_args: Dict[str, Any]
    note: str

    def supports(self, provider: object) -> bool:
        p = str(provider or "").strip().lower()
        return bool(self.deployed and p and p in self.supported_providers)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain": self.chain, "deployed": self.deployed, "address": self.address,
            "receiver_version": self.receiver_version, "abi_version": self.abi_version,
            "version_verified": self.version_verified,
            "bytecode_verified": self.bytecode_verified,
            "supported_providers": list(self.supported_providers),
            "constructor_args": self.constructor_args, "note": self.note,
        }


def _norm_providers(rec: Dict[str, Any]) -> List[str]:
    raw = rec.get("supported_providers")
    if not isinstance(raw, (list, tuple)):
        return []
    return sorted({str(x).strip().lower() for x in raw if str(x).strip()})


def receiver_capability(chain: Any) -> ReceiverCapability:
    """Fail-closed capability descriptor for ``chain``'s receiver."""
    chain_s = str(chain).lower() if chain is not None else "unknown"
    addr = deployed_address(chain)          # None unless deploy_status==success
    rec = get_deployment(chain) or {}
    if not addr:
        status = rec.get("deploy_status", "absent")
        return ReceiverCapability(
            chain=chain_s, deployed=False, address=None,
            receiver_version="unversioned", abi_version="unversioned",
            version_verified=False, bytecode_verified=False,
            supported_providers=[], constructor_args={},
            note=(f"no successfully-deployed receiver (deploy_status={status}) "
                  "— execution-incapable, all venues rejected (fail closed)"))

    rv = str(rec.get("receiver_version") or "").strip()
    av = str(rec.get("abi_version") or "").strip()
    bytecode_verified = str(rec.get("basescan_verified") or "").lower() in (
        "true", "verified", "yes")
    providers = _norm_providers(rec)
    note = "deployed receiver present"
    if not providers:
        note += "; NO supported_providers declared ⇒ all venues rejected (fail closed)"
    if not rv:
        note += "; receiver_version missing ⇒ unversioned/unverified"
    return ReceiverCapability(
        chain=chain_s, deployed=True, address=addr,
        receiver_version=rv or "unversioned",
        abi_version=av or "unversioned",
        version_verified=bool(rv),
        bytecode_verified=bytecode_verified,
        supported_providers=providers,
        constructor_args=dict(rec.get("constructor_args") or {}),
        note=note)


def receiver_supports(chain: Any, provider: object) -> bool:
    """True only if ``chain`` has a deployed receiver that EXPLICITLY supports
    ``provider``. Fail-closed everywhere else (undeployed / undeclared)."""
    return receiver_capability(chain).supports(provider)


__all__ = ["ReceiverCapability", "receiver_capability", "receiver_supports"]
