"""Wave 7A · Wallet Health composite card.

Reuse notice (VERIFY → REUSE):

    Applies the canonical safety-interlock pattern
    (``READY | WAIT | BLOCKED``) from
    ``services/execution/safety_interlock.py::evaluate()`` to a single
    wallet document.  Combines:

        * on-chain balance sufficiency (Wave 7A `WalletBalanceReader`),
        * secret-handle resolvability (Wave 6A `SecretRegistry`),
        * strategy mode ladder (Wave 6A `ExecutionModeRepo`),
        * capital-policy allocator (Wave 6D),
        * kill switch state (Wave 6D).

    No new safety semantics — this is a composition.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HealthCheck:
    key: str
    label: str
    status: str            # READY | WAIT | BLOCKED
    detail: str
    severity: str          # info | warn | crit
    payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WalletHealthReport:
    wallet_id: str
    overall_status: str    # READY | WAIT | BLOCKED
    checks: List[HealthCheck]
    ready_for_shadow: bool
    ready_for_limited_live: bool
    would_broadcast: bool
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        assert d["would_broadcast"] is False, "WalletHealthReport leaked would_broadcast=True"
        return d


class WalletHealthCard:
    """Read-only composite health card."""

    def __init__(self, *, wallet_registry, secret_registry,
                 balance_reader, mode_repo, capital_allocator,
                 kill_switch):
        self._wallets = wallet_registry
        self._secrets = secret_registry
        self._balance = balance_reader
        self._mode = mode_repo
        self._alloc = capital_allocator
        self._kill = kill_switch

    async def evaluate(self, wallet_id: str, *,
                       min_gas_native: float = 0.001,
                       strategy: str = "flash_loan_arbitrage",
                       ) -> WalletHealthReport:
        checks: List[HealthCheck] = []
        wallet = await self._wallets.get(wallet_id)
        if not wallet:
            return WalletHealthReport(
                wallet_id=wallet_id, overall_status="BLOCKED",
                checks=[HealthCheck(key="wallet_exists", label="Wallet exists",
                                     status="BLOCKED", severity="crit",
                                     detail=f"wallet '{wallet_id}' not registered")],
                ready_for_shadow=False, ready_for_limited_live=False,
                would_broadcast=False, generated_at=_now_iso(),
            )
        checks.append(HealthCheck(
            key="wallet_exists", label="Wallet registered",
            status="READY", severity="info",
            detail=f"role={wallet.get('execution_role')} chain={wallet.get('chain')}",
            payload={k: wallet.get(k) for k in
                     ("chain", "address", "execution_role", "label")},
        ))

        # Address format
        addr = wallet.get("address") or ""
        addr_ok = bool(addr.startswith("0x") and len(addr) == 42)
        checks.append(HealthCheck(
            key="address_valid", label="Address format",
            status="READY" if addr_ok else "BLOCKED",
            severity="info" if addr_ok else "crit",
            detail=addr,
        ))

        # Secret handle
        handle = wallet.get("secret_handle_id")
        role = wallet.get("execution_role")
        if role == "gas":
            secret_ok = False
            secret_detail = "no secret_handle_id bound"
            if handle:
                try:
                    material = await self._secrets.resolve(handle)
                    secret_ok = material is not None
                    secret_detail = ("secret resolved (length-proof only)" if secret_ok
                                     else "secret_handle_id did not resolve")
                except Exception as exc:  # noqa: BLE001
                    secret_detail = f"resolver error: {type(exc).__name__}"
            checks.append(HealthCheck(
                key="secret_bound", label="Signer secret bound",
                status="READY" if secret_ok else "BLOCKED",
                severity="info" if secret_ok else "crit",
                detail=secret_detail,
            ))
        else:
            checks.append(HealthCheck(
                key="secret_bound", label="Signer secret bound",
                status="READY", severity="info",
                detail=f"non-signing role ({role}) — no secret required",
            ))

        # Gas balance
        reading = None
        if addr_ok:
            try:
                reading = await self._balance.read(
                    chain=wallet.get("chain") or "base", address=addr,
                )
            except Exception as exc:  # noqa: BLE001
                reading = None
                checks.append(HealthCheck(
                    key="gas_balance", label="Gas balance",
                    status="WAIT", severity="warn",
                    detail=f"RPC error: {type(exc).__name__}",
                ))
        if reading is not None:
            enough_gas = reading.ok and reading.balance_native >= float(min_gas_native)
            status = "READY" if enough_gas else ("BLOCKED" if reading.ok else "WAIT")
            severity = ("info" if enough_gas
                         else ("crit" if reading.ok else "warn"))
            checks.append(HealthCheck(
                key="gas_balance", label="Gas balance",
                status=status, severity=severity,
                detail=(f"{reading.balance_native} {reading.symbol}"
                        + (f" (~${reading.balance_usd})"
                           if reading.balance_usd is not None else "")
                        + (f" — below floor {min_gas_native}"
                           if not enough_gas and reading.ok else "")),
                payload=reading.to_dict(),
            ))

        # Mode ladder
        try:
            row = await self._mode.get(strategy)
            mode = (row or {}).get("mode") or "OBSERVE"
        except Exception:  # noqa: BLE001
            mode = "OBSERVE"
        checks.append(HealthCheck(
            key="mode_ladder", label=f"Strategy mode ({strategy})",
            status="READY", severity="info",
            detail=mode,
            payload={"mode": mode},
        ))

        # Kill switch
        try:
            ks = await self._kill.state()
            checks.append(HealthCheck(
                key="kill_switch", label="Kill switch",
                status="BLOCKED" if ks.engaged else "READY",
                severity="crit" if ks.engaged else "info",
                detail=("engaged: " + (ks.reason or "n/a")
                        if ks.engaged else "disengaged"),
                payload=ks.to_dict(),
            ))
        except Exception as exc:  # noqa: BLE001
            checks.append(HealthCheck(
                key="kill_switch", label="Kill switch",
                status="WAIT", severity="warn",
                detail=f"unable to read: {type(exc).__name__}",
            ))

        # Capital policy sanity
        try:
            alloc = await self._alloc.evaluate(
                strategy=strategy, proposed_usd=100.0,
            )
            checks.append(HealthCheck(
                key="capital_policy", label="Capital policy",
                status="READY" if alloc.approved else "BLOCKED",
                severity="info" if alloc.approved else "warn",
                detail=(f"$100 test allocation → ${alloc.approved_usd} "
                        f"({alloc.binding_constraint})"),
                payload=alloc.to_dict(),
            ))
        except Exception as exc:  # noqa: BLE001
            checks.append(HealthCheck(
                key="capital_policy", label="Capital policy",
                status="WAIT", severity="warn",
                detail=f"policy check failed: {type(exc).__name__}",
            ))

        # Roll-up
        crits = [c for c in checks if c.status == "BLOCKED"]
        waits = [c for c in checks if c.status == "WAIT"]
        overall = ("BLOCKED" if crits else ("WAIT" if waits else "READY"))

        # SHADOW readiness = no BLOCKED checks except mode-gated ones
        shadow_ok = not crits or all(c.key == "capital_policy" for c in crits)
        # LIMITED_LIVE readiness = READY overall AND mode is LIMITED_LIVE-or-higher
        live_ok = (
            overall == "READY"
            and any(c.key == "mode_ladder"
                     and (c.payload or {}).get("mode") in ("LIMITED_LIVE", "FULL_LIVE")
                     for c in checks)
        )
        return WalletHealthReport(
            wallet_id=wallet_id,
            overall_status=overall,
            checks=checks,
            ready_for_shadow=bool(shadow_ok),
            ready_for_limited_live=bool(live_ok),
            would_broadcast=False,
            generated_at=_now_iso(),
        )
