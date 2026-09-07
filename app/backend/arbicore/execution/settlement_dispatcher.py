"""Executor V2 — SECURE SETTLEMENT DISPATCHER (backend, fail-closed).

Purpose
-------
Close the gap between an *economically valid* opportunity and a *verified
executable settlement path* by determining — deterministically, with an
explicit per-stage pass/fail reason — whether a SPECIFIC route is genuinely
executable through the CURRENTLY DEPLOYED FlashLoanReceiver.

This module does NOT deploy, sign, broadcast, or execute anything. It does NOT
modify the deployed receiver and it does NOT widen ``SUPPORTED_DEXES``. It is a
pure classifier that composes the existing execution seams into ordered
capability cells.

Hard truth rules (North Star)
-----------------------------
Execution capability is NOT implied by any of:
    adapter presence · venue registration · quote existence · liquidity ·
    route discovery · calldata constructability · a simulation object ·
    an executor address.

A route only becomes ``EXECUTABLE`` when EVERY capability cell passes against
the deployed receiver's real ABI + schema. There is NO silent fallback from an
unsupported execution path to another path. When the only blocker is a swap
venue outside the deployed receiver's fixed ``SwapHop[]`` / single-router
settlement schema, the honest verdict is ``REQUIRES_NEW_RECEIVER`` — the
dispatcher STOPS at that boundary rather than pretending it is solved.

Current deployed V1 receiver truth (0x99c0b64e…1052):
    FLASH: balancer_v2, aave_v3   ·   SWAP: uniswap_v3 (single immutable
    SwapRouter02; the on-chain SwapHop has no per-hop router/venue field).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .adapters import AdapterRegistry
from ..scanners.flash_loan_arbitrage.executor_capability import (
    SUPPORTED_DEXES,
    SUPPORTED_FLASH_PROVIDERS,
)

# Venues the deployed V1 receiver can genuinely SETTLE (schema + immutable
# router). Mirrors ``SUPPORTED_DEXES`` — kept as a distinct name to make the
# "settleable by this receiver schema" intent explicit at call sites.
RECEIVER_NATIVE_SWAP_VENUES = frozenset(SUPPORTED_DEXES)

# Flash-loan heads the deployed V1 receiver exposes (E1-reconciled).
RECEIVER_FLASH_HEADS = frozenset(SUPPORTED_FLASH_PROVIDERS)

# Flash providers whose executor-relayed calldata encoder exists today
# (calldata.encode_plan_head_call). Intentionally identical to the receiver
# flash heads — a provider is only calldata-constructable if the receiver has a
# matching head.
CALLDATA_ENCODABLE_FLASH = frozenset({"balancer_v2", "aave_v3"})


class CellStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"          # not evaluated because an earlier cell already failed


class Verdict(str, enum.Enum):
    EXECUTABLE = "EXECUTABLE"                    # every cell passed
    REJECTED = "REJECTED"                        # a hard, unrecoverable blocker
    REQUIRES_NEW_RECEIVER = "REQUIRES_NEW_RECEIVER"  # only blocker: venue outside V1 schema
    UNVERIFIABLE = "UNVERIFIABLE"                # incomplete capability info → fail closed


@dataclass
class CapabilityCell:
    name: str
    status: CellStatus
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "status": self.status.value, "reason": self.reason}


@dataclass
class SettlementDecision:
    executable: bool
    verdict: Verdict
    flash_provider: Optional[str]
    swap_venues: List[str]
    chain: Optional[str]
    executor_address: Optional[str]
    first_blocker: Optional[str]
    reason: str
    cells: List[CapabilityCell] = field(default_factory=list)
    # Explicit, invariant safety markers — this classifier never signs/broadcasts.
    signed: bool = False
    broadcast: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executable": self.executable,
            "verdict": self.verdict.value,
            "flash_provider": self.flash_provider,
            "swap_venues": self.swap_venues,
            "chain": self.chain,
            "executor_address": self.executor_address,
            "first_blocker": self.first_blocker,
            "reason": self.reason,
            "cells": [c.to_dict() for c in self.cells],
            "signed": self.signed,
            "broadcast": self.broadcast,
        }


def _norm(v: Any) -> Any:
    return v.strip().lower() if isinstance(v, str) else v


def evaluate_settlement(
    *,
    flash_provider: Optional[str],
    swap_venues: List[Optional[str]],
    chain: str,
    executor_address: Optional[str] = None,
    executor_deployed: Optional[bool] = None,
    registry: Optional[AdapterRegistry] = None,
) -> SettlementDecision:
    """Classify whether a concrete route is executable through the deployed V1
    receiver. Pure + deterministic: identical inputs → identical decision.

    Args:
        flash_provider: the SINGLE chosen flash-loan provider (no fallback).
        swap_venues: ordered per-hop DEX venue names. A ``None``/empty entry is
            missing metadata ⇒ UNVERIFIABLE (fail closed).
        chain: target chain name (e.g. ``"base"``).
        executor_address: optional deployed executor address (recorded only;
            its presence is NEVER treated as execution proof).
        executor_deployed: authoritative "is an executor genuinely deployed on
            this chain?" When ``None`` the canonical ``executor_registry`` is
            consulted (deploy_status=="success"). Fail-closed when unknown.
        registry: optional AdapterRegistry (defaults to the canonical one).
    """
    reg = registry or AdapterRegistry()
    catalog = reg.catalog()
    dex_adapter_keys = {_norm(d["dex"]) for d in catalog["dex_providers"]}

    provider = _norm(flash_provider)
    venues_norm = [_norm(v) for v in (swap_venues or [])]

    cells: List[CapabilityCell] = []

    def _decide(verdict: Verdict, first_blocker: Optional[str], reason: str) -> SettlementDecision:
        # Any remaining unevaluated cells stay absent → mark them SKIP for clarity.
        return SettlementDecision(
            executable=(verdict == Verdict.EXECUTABLE),
            verdict=verdict,
            flash_provider=provider,
            swap_venues=[v for v in venues_norm],
            chain=chain,
            executor_address=executor_address,
            first_blocker=first_blocker,
            reason=reason,
            cells=cells,
        )

    # ── Cell 1: ROUTE_VALID ────────────────────────────────────────────────
    if not provider or not venues_norm:
        cells.append(CapabilityCell(
            "route_valid", CellStatus.FAIL,
            "route requires a flash provider and at least one swap venue"))
        return _decide(Verdict.REJECTED, "route_valid", "invalid_route:missing_provider_or_venues")
    cells.append(CapabilityCell("route_valid", CellStatus.PASS,
                                f"{len(venues_norm)} hop(s), provider={provider}"))

    # ── Cell 2: FLASH_PROVIDER_SUPPORTED (receiver flash head) ─────────────
    if provider not in RECEIVER_FLASH_HEADS:
        cells.append(CapabilityCell(
            "flash_provider_supported", CellStatus.FAIL,
            f"'{provider}' is not a deployed receiver flash head "
            f"{sorted(RECEIVER_FLASH_HEADS)}"))
        return _decide(Verdict.REJECTED, "flash_provider_supported",
                       f"unsupported_flash_provider:{provider}")
    cells.append(CapabilityCell("flash_provider_supported", CellStatus.PASS,
                                f"'{provider}' is a deployed receiver flash head"))

    # ── Cell 3: FLASH_PROVIDER_CHAIN_SUPPORTED (adapter supports chain) ────
    try:
        fl_adapter = reg.flash(provider)
        chain_ok = bool(fl_adapter.supports(chain))
    except ValueError:
        chain_ok = False
    if not chain_ok:
        cells.append(CapabilityCell(
            "flash_provider_chain_supported", CellStatus.FAIL,
            f"flash provider '{provider}' does not support chain '{chain}'"))
        return _decide(Verdict.REJECTED, "flash_provider_chain_supported",
                       f"flash_provider_chain_unsupported:{provider}@{chain}")
    cells.append(CapabilityCell("flash_provider_chain_supported", CellStatus.PASS,
                                f"'{provider}' supports chain '{chain}'"))

    # ── Cell 4: SWAP_VENUE_RESOLVED (metadata present) ─────────────────────
    if any(v in (None, "") for v in venues_norm):
        cells.append(CapabilityCell(
            "swap_venue_resolved", CellStatus.FAIL,
            "one or more hops have missing/unknown venue metadata"))
        return _decide(Verdict.UNVERIFIABLE, "swap_venue_resolved",
                       "venue_metadata_missing")
    cells.append(CapabilityCell("swap_venue_resolved", CellStatus.PASS,
                                f"venues={venues_norm}"))

    # ── Cell 5: VENUE_ADAPTER_AVAILABLE (route-construction possible) ──────
    no_adapter = sorted({v for v in venues_norm if v not in dex_adapter_keys})
    if no_adapter:
        cells.append(CapabilityCell(
            "venue_adapter_available", CellStatus.FAIL,
            f"no DEX calldata adapter for venue(s) {no_adapter}"))
        return _decide(Verdict.REJECTED, "venue_adapter_available",
                       f"no_dex_adapter:{no_adapter}")
    cells.append(CapabilityCell("venue_adapter_available", CellStatus.PASS,
                                "every venue has a route-construction adapter"))

    # ── Cell 6: RECEIVER_SCHEMA_COMPATIBLE (V1 SwapHop[]/single router) ────
    # The deployed V1 SwapHop schema settles Uniswap V3 hops through ONE
    # immutable SwapRouter02 and carries no per-hop router/venue field. Any
    # non-native venue (incl. UniV3 *forks* that need a different router) is
    # route-constructable but NOT settleable by this receiver → new receiver.
    non_native = sorted({v for v in venues_norm if v not in RECEIVER_NATIVE_SWAP_VENUES})
    if non_native:
        cells.append(CapabilityCell(
            "receiver_schema_compatible", CellStatus.FAIL,
            f"venue(s) {non_native} cannot be settled by the deployed V1 "
            f"SwapHop[] schema (Uniswap V3 via a single immutable router only); "
            f"requires a new/versioned receiver"))
        return _decide(Verdict.REQUIRES_NEW_RECEIVER, "receiver_schema_compatible",
                       f"receiver_schema_incompatible:{non_native}")
    cells.append(CapabilityCell("receiver_schema_compatible", CellStatus.PASS,
                                "all hops settle via the V1 Uniswap V3 SwapHop schema"))

    # ── Cell 7: CALLDATA_CONSTRUCTABLE (executor-relayed encoder exists) ───
    if provider not in CALLDATA_ENCODABLE_FLASH:
        cells.append(CapabilityCell(
            "calldata_constructable", CellStatus.FAIL,
            f"no executor-relayed calldata encoder for flash provider '{provider}'"))
        return _decide(Verdict.REJECTED, "calldata_constructable",
                       f"calldata_not_constructable:{provider}")
    cells.append(CapabilityCell("calldata_constructable", CellStatus.PASS,
                                f"executor-relayed encoder available for '{provider}'"))

    # ── Cell 8: EXECUTOR_DEPLOYED (a verified executor exists on this chain) ─
    # Venue/flash/schema/calldata compatibility is necessary but NOT sufficient:
    # execution also requires a genuinely DEPLOYED executor on the target chain.
    # Authoritative source = executor_registry (deploy_status=="success"); the
    # runtime may pass ``executor_deployed`` (env-resolved truth). An
    # ``executor_address`` alone is NEVER treated as proof. This is the gate that
    # keeps every chain WITHOUT a deployed executor fail-closed (e.g. all five
    # non-Base chains today) while auto-including a chain the moment its executor
    # is genuinely deployed + registered — no code change required.
    if executor_deployed is None:
        try:
            from . import executor_registry as _exreg
            deployed = bool(_exreg.is_deployed(chain))
            if executor_address is None:
                executor_address = _exreg.deployed_address(chain)
        except Exception:  # noqa: BLE001 — any registry fault ⇒ fail-closed
            deployed = False
    else:
        deployed = bool(executor_deployed)
    if not deployed:
        cells.append(CapabilityCell(
            "executor_deployed", CellStatus.FAIL,
            f"no verified deployed executor on chain '{chain}' — fail-closed"))
        return _decide(Verdict.REJECTED, "executor_deployed",
                       f"no_deployed_executor_on_chain:{chain}")
    cells.append(CapabilityCell("executor_deployed", CellStatus.PASS,
                                f"verified deployed executor on chain '{chain}'"))

    # ── All cells passed ───────────────────────────────────────────────────
    return _decide(Verdict.EXECUTABLE, None,
                   "all_capability_cells_pass: settleable by deployed V1 receiver")


__all__ = [
    "CellStatus", "Verdict", "CapabilityCell", "SettlementDecision",
    "evaluate_settlement", "RECEIVER_NATIVE_SWAP_VENUES", "RECEIVER_FLASH_HEADS",
    "CALLDATA_ENCODABLE_FLASH",
]
