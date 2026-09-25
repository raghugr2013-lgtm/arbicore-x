"""Version-aware settlement binding (ADDITIVE).

Binds ``settlement_dispatcher.evaluate_settlement`` to the CURRENTLY DEPLOYED
receiver's capability — resolved from the committed executor registry record
(``receiver_version`` + ``supported_providers`` + ``supported_dexes``) — rather
than from a catalog. Fail-closed everywhere:

  * No successful deployment on the chain ⇒ every route REJECTED (no executor).
  * ``receiver_version == "v1"`` ⇒ the V1 constants apply (UniV3-only swap;
    Balancer+Aave flash) — identical to the historical behaviour.
  * ``receiver_version == "v2"`` ⇒ capability is the INTERSECTION of the record's
    declared sets and the V2 initial certified scope for that chain. A venue or
    provider is executable ONLY if BOTH the deployed-record declares it AND it is
    within the frozen initial scope. Adapter presence alone grants nothing.

This module performs NO network I/O, NEVER signs/broadcasts/deploys.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .settlement_dispatcher import (
    evaluate_settlement, SettlementDecision, Verdict, CapabilityCell, CellStatus,
    RECEIVER_FLASH_HEADS, RECEIVER_NATIVE_SWAP_VENUES, CALLDATA_ENCODABLE_FLASH,
)
from .executor_interface_v2 import (
    V2_FLASH_HEADS, V2_INITIAL_SCOPE, V2_OUT_OF_SCOPE_CHAINS,
)
from . import executor_registry as _exreg

# V2 flash heads whose deterministic calldata encoder exists (calldata_v2).
_V2_CALLDATA_ENCODABLE = frozenset({"balancer_v2", "aave_v3", "morpho_blue"})

_CHAIN_NAME_TO_ID = {
    "base": 8453, "base_mainnet": 8453, "ethereum": 1, "eth": 1, "mainnet": 1,
    "base_sepolia": 84532, "sepolia": 84532,
}


def _chain_id(chain: Any) -> Optional[int]:
    if isinstance(chain, int):
        return chain
    s = str(chain or "").strip().lower()
    if s.isdigit():
        return int(s)
    return _CHAIN_NAME_TO_ID.get(s)


def evaluate_settlement_for_deployed_receiver(
    *,
    flash_provider: Optional[str],
    swap_venues: List[Optional[str]],
    chain: str,
    registry=None,
) -> SettlementDecision:
    """Fail-closed, version-aware settlement classification bound to the
    deployed receiver recorded for ``chain``."""
    rec: Dict[str, Any] = _exreg.get_deployment(chain) or {}
    deployed = _exreg.is_deployed(chain)
    version = str(rec.get("receiver_version") or "").strip().lower()

    # No verified deployment ⇒ hard REJECT (never executable).
    if not deployed:
        return SettlementDecision(
            executable=False, verdict=Verdict.REJECTED,
            flash_provider=(flash_provider or None),
            swap_venues=[v for v in swap_venues],
            chain=chain, executor_address=None,
            first_blocker="executor_deployed",
            reason=f"no_deployed_executor_on_chain:{chain}",
            cells=[CapabilityCell("executor_deployed", CellStatus.FAIL,
                                  "no verified deployed receiver — fail-closed")])

    if version == "v2":
        cid = _chain_id(chain)
        if cid is None or cid in V2_OUT_OF_SCOPE_CHAINS or cid not in V2_INITIAL_SCOPE:
            return SettlementDecision(
                executable=False, verdict=Verdict.REJECTED,
                flash_provider=(flash_provider or None),
                swap_venues=[v for v in swap_venues], chain=chain,
                executor_address=_exreg.deployed_address(chain),
                first_blocker="chain_scope",
                reason=f"chain_out_of_v2_initial_scope:{chain}",
                cells=[CapabilityCell("chain_scope", CellStatus.FAIL,
                                      "chain not in V2 initial certified scope")])
        scope = V2_INITIAL_SCOPE[cid]
        rec_providers = {str(x).strip().lower() for x in (rec.get("supported_providers") or [])}
        rec_dexes = {str(x).strip().lower() for x in (rec.get("supported_dexes") or [])}
        # INTERSECTION of on-chain-declared record ∩ frozen initial scope.
        flash_heads = frozenset(rec_providers & set(scope["providers"]) & V2_FLASH_HEADS)
        native_venues = frozenset(rec_dexes & set(scope["venues"]))
        encodable = frozenset(flash_heads & _V2_CALLDATA_ENCODABLE)
    else:
        # v1 (or unversioned deployed record) ⇒ historical V1 capability.
        flash_heads = RECEIVER_FLASH_HEADS
        native_venues = RECEIVER_NATIVE_SWAP_VENUES
        encodable = CALLDATA_ENCODABLE_FLASH

    return evaluate_settlement(
        flash_provider=flash_provider,
        swap_venues=swap_venues,
        chain=chain,
        executor_address=_exreg.deployed_address(chain),
        executor_deployed=deployed,
        registry=registry,
        receiver_flash_heads=flash_heads,
        receiver_native_venues=native_venues,
        calldata_encodable_flash=encodable,
    )


__all__ = ["evaluate_settlement_for_deployed_receiver"]
