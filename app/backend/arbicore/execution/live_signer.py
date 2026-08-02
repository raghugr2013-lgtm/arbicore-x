"""Wave 6D · Live Signer.

Purpose: turn an ``ExecutionPlan`` into a set of *unsigned* EVM
transaction envelopes ready for future broadcast.  This wave never
actually signs with a real EVM private key — that requires
bytes-level calldata encoding (Wave 6E) — but it exposes the full
gate ladder so the signing pipeline is testable end-to-end today:

    1. Kill switch guard — refuse if engaged.
    2. Mode ladder guard — refuse unless mode ∈ (LIMITED_LIVE, FULL_LIVE).
    3. Capital policy guard — refuse if allocator says ``approved=False``.
    4. Secret registry resolve — verify the signer wallet's
       ``secret_handle_id`` resolves to key material *without* leaking
       it back through any surface.  Length-only proof surfaces.
    5. Produce a ``LiveSigningReceipt`` — never contains plaintext key
       material or signed bytes.

Result envelope shape::

    {
      "signed": false,                       # invariant in Wave 6D
      "denied_reasons": [...],               # empty when gates passed
      "gate_ladder": {                       # visibility for operators
        "kill_switch":       "PASS"|"DENIED",
        "mode":              "PASS"|"DENIED",
        "capital_policy":    "PASS"|"DENIED",
        "secret_resolution": "PASS"|"DENIED",
      },
      "plan_id": "...",
      "strategy": "...",
      "mode": "SHADOW",
      "signer_wallet_id": "...",
      "signing_algorithm": "ed25519",
      "would_broadcast": false,              # ALWAYS false in this wave
      "receipt_id": "sign-<uuid>",
      "envelopes": [],                       # populated only in Wave 6E
      "audit": { "actor": "...", "at": "..." }
    }
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .kill_switch import KillSwitchEngagedError, KillSwitchRepo
from .mode import is_broadcast_allowed, ExecutionModeRepo
from .capital_policy import CapitalAllocator

logger = logging.getLogger("arbicore.execution.live_signer")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LiveSigningReceipt:
    receipt_id: str
    plan_id: str
    strategy: str
    mode: str
    signer_wallet_id: Optional[str]
    signing_algorithm: str
    signed: bool
    would_broadcast: bool
    denied_reasons: List[str]
    gate_ladder: Dict[str, str]
    envelopes: List[Dict[str, Any]] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        assert d["would_broadcast"] is False, "LiveSigningReceipt leaked would_broadcast=True"
        return d


class LiveSigner:
    """Gate-only signer.  Never emits raw signed transactions in Wave 6D.

    In Wave 6E — after bytes-level calldata encoding lands — this class
    is extended with an actual EVM signing backend gated behind the
    same ladder.  The gate ladder here is the authoritative broadcast
    boundary.
    """

    def __init__(self, *,
                 kill_switch: KillSwitchRepo,
                 mode_repo: ExecutionModeRepo,
                 wallet_registry,           # WalletRegistryRepo — kept loose to avoid a cycle
                 secret_registry,           # SecretRegistry
                 capital_allocator: CapitalAllocator,
                 signing_algorithm: str = "ed25519"):
        self._kill = kill_switch
        self._mode = mode_repo
        self._wallets = wallet_registry
        self._secrets = secret_registry
        self._allocator = capital_allocator
        self._algorithm = signing_algorithm

    async def sign_plan(self, plan_doc: Dict[str, Any], *,
                        actor: str = "operator",
                        available_liquidity_usd: float = 1_000_000.0,
                        reference_capital_usd: float = 5_000.0,
                        expected_net_profit_usd: Optional[float] = None,
                        ) -> LiveSigningReceipt:
        """Run the gate ladder and produce a receipt.

        Wave 6D never emits signed transaction bytes; the receipt shows
        each gate's decision so operators can validate the pipeline
        end-to-end without any live broadcast risk.
        """
        plan_id = plan_doc.get("plan_id") or ""
        strategy = plan_doc.get("strategy") or ""
        signer_wallet_id = plan_doc.get("signer_wallet_id")
        gate_ladder: Dict[str, str] = {}
        denied: List[str] = []
        # 1. Kill-switch gate
        try:
            await self._kill.guard()
            gate_ladder["kill_switch"] = "PASS"
        except KillSwitchEngagedError as exc:
            gate_ladder["kill_switch"] = "DENIED"
            denied.append(f"kill_switch_engaged: {exc}")
        # 2. Mode gate — must be LIMITED_LIVE or FULL_LIVE
        mode_row = await self._mode.get(strategy)
        current_mode = (mode_row or {}).get("mode") or "OBSERVE"
        if is_broadcast_allowed(current_mode):
            gate_ladder["mode"] = "PASS"
        else:
            gate_ladder["mode"] = "DENIED"
            denied.append(
                f"mode_gate: strategy '{strategy}' is '{current_mode}' — "
                f"must be LIMITED_LIVE or FULL_LIVE to sign"
            )
        # 3. Capital policy gate
        alloc = await self._allocator.evaluate(
            strategy=strategy,
            proposed_usd=float(plan_doc.get("borrow_amount_usd") or 0),
            available_liquidity_usd=available_liquidity_usd,
            reference_capital_usd=reference_capital_usd,
            expected_net_profit_usd=expected_net_profit_usd,
        )
        if alloc.approved:
            gate_ladder["capital_policy"] = "PASS"
        else:
            gate_ladder["capital_policy"] = "DENIED"
            denied.append(f"capital_policy: {alloc.binding_constraint} — "
                          f"{'; '.join(alloc.reasons) or 'denied'}")
        # 4. Secret resolution gate
        secret_ok = False
        if not signer_wallet_id:
            gate_ladder["secret_resolution"] = "DENIED"
            denied.append("secret_resolution: plan carries no signer_wallet_id")
        else:
            try:
                wallet = await self._wallets.get(signer_wallet_id)
                if not wallet:
                    gate_ladder["secret_resolution"] = "DENIED"
                    denied.append(
                        f"secret_resolution: wallet '{signer_wallet_id}' not registered"
                    )
                elif wallet.get("execution_role") != "gas":
                    gate_ladder["secret_resolution"] = "DENIED"
                    denied.append(
                        f"secret_resolution: wallet role is "
                        f"'{wallet.get('execution_role')}' (must be 'gas')"
                    )
                else:
                    handle_id = wallet.get("secret_handle_id")
                    if not handle_id:
                        gate_ladder["secret_resolution"] = "DENIED"
                        denied.append(
                            "secret_resolution: gas wallet carries no secret_handle_id"
                        )
                    else:
                        material = await self._secrets.resolve(handle_id)
                        if material is None:
                            gate_ladder["secret_resolution"] = "DENIED"
                            denied.append(
                                "secret_resolution: secret_handle_id did not resolve"
                            )
                        else:
                            # Length-only proof — never emit plaintext.
                            gate_ladder["secret_resolution"] = "PASS"
                            secret_ok = True
            except Exception as exc:  # noqa: BLE001
                gate_ladder["secret_resolution"] = "DENIED"
                denied.append(
                    f"secret_resolution: unexpected error {type(exc).__name__}: {exc}"
                )

        signed = False
        envelopes: List[Dict[str, Any]] = []
        # Wave-6D INVARIANT: even when all four gates pass, we do NOT
        # emit signed bytes yet — bytes-level calldata encoding lands
        # in Wave 6E once the executor contract is verified.  The
        # receipt records that the ladder passed and that the plan is
        # signing-eligible.
        if not denied and secret_ok and is_broadcast_allowed(current_mode):
            # Signing-eligible but held at Wave-6D barrier.
            envelopes = [{
                "step_index": s.get("step_index"),
                "kind": s.get("kind"),
                "envelope": "pending_calldata_encoding",
                "would_broadcast": False,
            } for s in plan_doc.get("steps") or []]
        receipt_id = f"sign-{uuid.uuid4().hex}"
        return LiveSigningReceipt(
            receipt_id=receipt_id,
            plan_id=plan_id,
            strategy=strategy,
            mode=current_mode,
            signer_wallet_id=signer_wallet_id,
            signing_algorithm=self._algorithm,
            signed=signed,
            would_broadcast=False,
            denied_reasons=denied,
            gate_ladder=gate_ladder,
            envelopes=envelopes,
            audit={"actor": actor, "at": _now_iso()},
        )
