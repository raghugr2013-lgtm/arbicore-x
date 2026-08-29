"""Live, read-only Limited-Live readiness probes (additive, STRICTLY fail-closed).

Each probe performs a genuine read (RPC / DB) where possible and returns a
result that maps onto the mandatory eligibility controls in
``limited_live_eligibility.MANDATORY_CONTROLS``. Every probe fails closed:
missing RPC / executor / DB, absent calldata, missing signer, stale data,
unverifiable liquidity, a disabled operator mode, or an engaged kill switch all
produce an explicit DENY / UNKNOWN — NEVER a fabricated PASS.

Nothing here signs, broadcasts, deploys, or enables any live mode. Every RPC
read is a read-only ``eth_call`` / ``eth_getCode`` / ``eth_blockNumber``.

Documented freshness policy (unchanged — not loosened here):
  * quote age    ≤ 12.0 s   (ranking.quote_max_age_sec)
  * block lag    ≤ ARBICORE_PRICE_MAX_BLOCK_LAG (default 5; pre_broadcast policy)
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from ...discovery.base_venues import TOKENS, canonical_symbol
from .provider_liquidity import (
    ProviderLiquidity, ProviderStatus, read_balancer_liquidity,
)

# Documented freshness policy constants (see module docstring).
FRESH_QUOTE_MAX_AGE_S = 12.0

# Operator modes that permit a Limited-Live execution ATTEMPT. Anything else
# (SHADOW / PAPER / PROFIT_ENGINE / UNKNOWN) ⇒ mode_allows = False (DENY).
LIMITED_LIVE_MODES = frozenset({"LIMITED_LIVE", "FULL_AUTOMATION"})


def _cfg_i(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 1) Exact-transaction atomic simulation (read-only eth_call + state override)
# ---------------------------------------------------------------------------
async def probe_atomic_simulation(
    *, bundle: Dict[str, Any], executor_address: Optional[str],
    rpc_url: Optional[str], signer_present: bool = False,
    sim_factory: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """Run the exact-tx atomic simulation via ``AtomicExecutorSimulator``.

    Uses the real configured Base executor address when available. Read-only:
    it NEVER signs or broadcasts. Fail-closed ladder:
      * no RPC                 → UNKNOWN
      * no executor address    → DENY (operator prerequisite absent)
      * no exact calldata      → DENY (read-only audit builds no calldata)
      * no vault signer        → DENY (simulate_atomic gates on signer_present)
      * executor reverts       → DENY
    """
    if sim_factory is None:
        from ...execution.atomic_executor_sim import AtomicExecutorSimulator
        sim_factory = AtomicExecutorSimulator

    if not rpc_url:
        return {"available": False, "passed": False, "status": "UNKNOWN",
                "reason": "rpc_not_configured", "signed": False, "broadcast": False}
    if not executor_address:
        return {"available": False, "passed": False, "status": "DENY",
                "reason": "executor_address_absent (ARBICORE_EXECUTOR_ADDRESS_BASE unset)",
                "signed": False, "broadcast": False}

    sim = sim_factory(rpc_url=rpc_url, executor_address=executor_address)
    readiness = sim.readiness() if hasattr(sim, "readiness") else {}
    try:
        cap = await sim.capability_self_test()
    except Exception as exc:  # noqa: BLE001 — never fabricate a green
        cap = {"code_injection": False, "reason": f"{type(exc).__name__}: {exc}"}

    plan = bundle.get("execution_plan") or {}
    entry_calldata = (plan.get("executor_entry_calldata")
                      or bundle.get("executor_entry_calldata"))
    if not entry_calldata:
        return {"available": False, "passed": False, "status": "DENY",
                "reason": "exact_executor_calldata_absent (read-only audit builds none)",
                "readiness": readiness, "capability_self_test": cap,
                "signed": False, "broadcast": False}

    res = dict(await sim.simulate_atomic(
        entry_calldata=entry_calldata, signer_present=signer_present,
        block_tag="latest"))
    res.setdefault("readiness", readiness)
    res["capability_self_test"] = cap
    res["signed"] = False
    res["broadcast"] = False
    return res


# ---------------------------------------------------------------------------
# 2) Balancer V2 Vault flash-loan liquidity (AVAILABLE vs REQUESTED borrow)
# ---------------------------------------------------------------------------
def _borrow_symbol(bundle: Dict[str, Any]) -> Optional[str]:
    route = bundle.get("route") or {}
    return (route.get("borrow_token")
            or (route.get("cycle_token_path") or [None])[0]
            or (bundle.get("quotes") or {}).get("borrow_token"))


async def probe_balancer_liquidity(
    *, bundle: Dict[str, Any], rpc_url: Optional[str], chain: str = "base",
    provider_factory: Optional[Callable[[], Any]] = None,
    price_lookup: Optional[Callable[[str], Optional[float]]] = None,
) -> Optional[ProviderLiquidity]:
    """Read the REAL Balancer V2 Vault liquidity for the borrow token and
    compare AVAILABLE vs REQUESTED borrow. Never fabricates liquidity:
      * no RPC                 → None (mapped to UNKNOWN downstream)
      * unresolved token       → UNKNOWN
      * read error / no price  → UNKNOWN
      * liquidity < borrow     → UNAVAILABLE
      * liquidity ≥ borrow     → ON_CHAIN_CONFIRMED
    """
    if not rpc_url:
        return None

    symbol = _borrow_symbol(bundle)
    canon = canonical_symbol(symbol) if symbol else None
    if not canon or canon not in TOKENS:
        return ProviderLiquidity(
            provider="balancer_v2", chain=chain,
            status=ProviderStatus.UNKNOWN, reason="borrow_token_unresolved")

    addr = TOKENS[canon]["address"]
    dec = int(TOKENS[canon]["decimals"])
    econ = bundle.get("economics") or {}
    price = econ.get("borrow_token_price_usd")
    if price is None and price_lookup is not None:
        price = price_lookup(canon)
    borrow_usd = bundle.get("input_amount_usd")

    if provider_factory is None:
        from ...providers.rpc import EthJsonRpcProvider
        provider_factory = lambda: EthJsonRpcProvider(chain=chain, url=rpc_url)  # noqa: E731

    provider = provider_factory()
    try:
        return await read_balancer_liquidity(
            provider, chain=chain, token_address=addr, token_decimals=dec,
            token_price_usd=(float(price) if isinstance(price, (int, float)) else None),
            borrow_amount_usd=(float(borrow_usd) if isinstance(borrow_usd, (int, float)) else None))
    except Exception as exc:  # noqa: BLE001 — never fabricate liquidity
        return ProviderLiquidity(
            provider="balancer_v2", chain=chain,
            status=ProviderStatus.UNKNOWN,
            reason=f"balancer_read_error:{type(exc).__name__}")
    finally:
        close = getattr(provider, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# 3) Freshness (quote age + block lag) — documented policy, fail-closed
# ---------------------------------------------------------------------------
def probe_freshness(
    *, bundle: Dict[str, Any], current_block: Optional[int], now_ts: float,
    max_quote_age_s: float = FRESH_QUOTE_MAX_AGE_S,
    max_block_lag: Optional[int] = None,
) -> Dict[str, Any]:
    """Evaluate quote/block freshness against the documented policy. Fails
    closed on any missing timestamp/block, future-dated quote, reorg, or a
    quote/block older than the (unchanged) policy threshold."""
    if max_block_lag is None:
        max_block_lag = _cfg_i("ARBICORE_PRICE_MAX_BLOCK_LAG", 5)

    quotes = bundle.get("quotes") or {}
    verified_at = quotes.get("verified_at_ts")
    quote_block = quotes.get("quote_block")

    def deny(reason: str, **extra: Any) -> Dict[str, Any]:
        return {"ok": False, "reason": reason,
                "max_quote_age_s": max_quote_age_s,
                "max_block_lag": max_block_lag, **extra}

    if verified_at is None:
        return deny("quote_timestamp_missing")
    try:
        age = float(now_ts) - float(verified_at)
    except (TypeError, ValueError):
        return deny("quote_timestamp_invalid")
    if age < 0:
        return deny("quote_timestamp_in_future", quote_age_s=round(age, 3))
    if age > max_quote_age_s:
        return deny(f"quote_stale:{age:.2f}s>{max_quote_age_s}s", quote_age_s=round(age, 3))

    if quote_block is None:
        return deny("quote_block_missing", quote_age_s=round(age, 3))
    if current_block is None:
        return deny("current_block_unavailable", quote_age_s=round(age, 3))
    try:
        lag = int(current_block) - int(quote_block)
    except (TypeError, ValueError):
        return deny("block_numbers_invalid", quote_age_s=round(age, 3))
    if lag < 0:
        return deny(f"reorg:head_{current_block}<quoted_{quote_block}",
                    quote_age_s=round(age, 3), block_lag=lag)
    if lag > max_block_lag:
        return deny(f"block_stale:lag_{lag}>{max_block_lag}",
                    quote_age_s=round(age, 3), block_lag=lag)

    return {"ok": True, "reason": "fresh", "quote_age_s": round(age, 3),
            "block_lag": lag, "max_quote_age_s": max_quote_age_s,
            "max_block_lag": max_block_lag}


# ---------------------------------------------------------------------------
# 4) Honest operator mode + kill-switch state (never enables anything)
# ---------------------------------------------------------------------------
async def probe_mode_and_kill_switch(
    *, db: Any,
    mode_repo_factory: Optional[Callable[[Any], Any]] = None,
    kill_repo_factory: Optional[Callable[[Any], Any]] = None,
) -> Dict[str, Any]:
    """Report the ACTUAL operator mode and kill-switch state (read-only).

    ``mode_allows`` is True only when the persisted operator mode is
    LIMITED_LIVE/FULL_AUTOMATION; a disabled mode or unknown mode ⇒ False.
    ``kill_switch_ok`` is True only when the switch is explicitly disengaged;
    engaged or unreadable ⇒ False. This NEVER changes mode or the kill switch.
    """
    if mode_repo_factory is None:
        from ...control.readiness import ControlStateRepo
        mode_repo_factory = ControlStateRepo
    if kill_repo_factory is None:
        from ...execution.kill_switch import KillSwitchRepo
        kill_repo_factory = KillSwitchRepo

    result: Dict[str, Any] = {
        "mode": "UNKNOWN", "mode_allows": False,
        "kill_switch_engaged": None, "kill_switch_ok": False, "reason": "",
    }
    if db is None:
        result["reason"] = "db_unavailable"
        return result

    try:
        mode = await mode_repo_factory(db).get_mode()
    except Exception as exc:  # noqa: BLE001
        result["reason"] = f"mode_read_failed:{type(exc).__name__}"
        return result
    result["mode"] = mode
    result["mode_allows"] = mode in LIMITED_LIVE_MODES

    try:
        ks = await kill_repo_factory(db).state()
        result["kill_switch_engaged"] = bool(ks.engaged)
        result["kill_switch_ok"] = (ks.engaged is False)
    except Exception as exc:  # noqa: BLE001
        result["kill_switch_engaged"] = None
        result["kill_switch_ok"] = False
        extra = f"kill_read_failed:{type(exc).__name__}"
        result["reason"] = f"{result['reason']};{extra}".strip(";")

    return result


# ---------------------------------------------------------------------------
# Executor address resolution + signer readiness (read-only; no keys)
# ---------------------------------------------------------------------------
def resolve_executor_address(chain: Any = None) -> Optional[str]:
    """Resolve the executor address: environment FIRST
    (ARBICORE_EXECUTOR_ADDRESS_BASE — the sole runtime source), else the
    READ-ONLY deployment registry for ``chain`` (default ARBICORE_CHAIN_ID or
    Base mainnet 8453). Returns None (fail closed) when neither is available.
    Never writes any environment variable and never enables anything."""
    env = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    if env:
        return env
    if chain is None:
        chain = os.environ.get("ARBICORE_CHAIN_ID", "8453")
    try:
        from ...execution.executor_registry import deployed_address
    except Exception:  # noqa: BLE001
        return None
    return deployed_address(chain)


def probe_signer_readiness(*, executor_owner: Optional[str] = None) -> Dict[str, Any]:
    """Report Limited-Live signer/authorization readiness WITHOUT any secret.

    The executor is owner-gated, so the Limited-Live signer's PUBLIC address must
    equal the executor owner EOA. We read only a PUBLIC address from
    ``ARBICORE_EXECUTOR_SIGNER_ADDRESS`` and (when the on-chain owner is known)
    compare them. ``ready`` reflects only that the PUBLIC authorization identity
    is configured and matches — it does NOT mean a private key exists or that
    signing/broadcast is enabled (those remain out-of-band + operator-gated).
    NEVER reads, prints, or stores a private key."""
    signer_addr = os.environ.get("ARBICORE_EXECUTOR_SIGNER_ADDRESS")
    present = bool(signer_addr and signer_addr.startswith("0x") and len(signer_addr) == 42)
    owner_match: Optional[bool] = None
    if present and executor_owner:
        owner_match = (signer_addr.lower() == executor_owner.lower())

    if not present:
        reason = "signer_public_address_absent (ARBICORE_EXECUTOR_SIGNER_ADDRESS unset)"
    elif executor_owner is None:
        reason = "signer_present_but_owner_unverified (executor owner not read)"
    elif owner_match is False:
        reason = "signer_does_not_match_executor_owner"
    else:
        reason = "signer_public_address_matches_executor_owner"

    return {
        "ready": bool(present and owner_match is True),
        "signer_present": present,
        "owner_match": owner_match,
        "reason": reason,
        "requires": ("Limited-Live signer PUBLIC address == executor owner EOA; "
                     "private key held only in the operator vault out-of-band "
                     "(never in repo / env / logs)."),
        "signed": False, "broadcast": False,
    }


# ---------------------------------------------------------------------------
# Read-only on-chain executor identity probe
# ---------------------------------------------------------------------------
async def probe_executor_identity(
    *, executor_address: Optional[str], rpc_url: Optional[str],
    chain: Any = None, expected: Optional[Dict[str, str]] = None,
    inspector: Optional[Any] = None,
) -> Dict[str, Any]:
    """READ-ONLY on-chain identity check of the deployed executor via
    ``inspect_executor`` (eth_getCode + owner()/ROUTER()/VAULT()). Verifies the
    contract exists, has bytecode, exposes the expected entrypoint selector, and
    that its router/vault match the expected (registry) constructor args. Never
    signs/broadcasts, never fabricates READY:
      * no executor address → BLOCKED (executor_address_absent)
      * no RPC              → UNKNOWN (cannot inspect)
      * no bytecode         → BLOCKED
      * router/vault or entrypoint mismatch → BLOCKED
      * all match           → READY (status only; not eligibility)
    """
    result: Dict[str, Any] = {
        "status": "UNKNOWN", "exists": None, "bytecode_present": None,
        "owner": None, "router": None, "vault": None,
        "entrypoint_selector_present": None, "mismatches": [],
        "chain": (str(chain) if chain is not None else None),
        "reason": "", "signed": False, "broadcast": False,
    }
    if not executor_address:
        result.update(status="BLOCKED", exists=False,
                      reason="executor_address_absent")
        return result
    result["executor"] = executor_address
    if not rpc_url:
        result["reason"] = "rpc_not_configured (cannot inspect on-chain)"
        return result

    if inspector is None:
        from ...execution.executor_entrypoint import inspect_executor
        inspector = inspect_executor
    if expected is None:
        try:
            from ...execution.executor_registry import get_deployment
            rec = get_deployment(chain) or {}
            ca = rec.get("constructor_args") or rec.get("constructor_args_expected") or {}
            expected = {"vault": ca.get("balancerVault"), "router": ca.get("uniRouter")}
        except Exception:  # noqa: BLE001
            expected = {}

    try:
        info = await inspector(rpc_url, executor_address)
    except Exception as exc:  # noqa: BLE001
        # Fail-closed (status stays UNKNOWN). Surface a precise, secret-free
        # reason code so operators can distinguish a rate-limited provider from
        # other inspection errors. Never prints the RPC URL.
        msg = str(exc).lower()
        if "429" in msg or "rate limit" in msg or "too many requests" in msg:
            result["reason"] = "RPC_PROVIDER_RATE_LIMITED (executor identity unverified)"
            result["rpc_rate_limited"] = True
        else:
            result["reason"] = f"inspection_error:{type(exc).__name__}"
        return result

    if not info.get("ok"):
        result.update(status="BLOCKED", exists=False, bytecode_present=False,
                      reason=info.get("reason") or "executor_inspection_failed")
        return result

    result.update(exists=True, bytecode_present=True,
                  bytecode_size_bytes=info.get("bytecode_size_bytes"),
                  owner=info.get("owner"), router=info.get("router"),
                  vault=info.get("vault"),
                  entrypoint_selector_present=info.get("entrypoint_selector_present"))

    mismatches: List[str] = []
    exp_vault = (expected or {}).get("vault")
    exp_router = (expected or {}).get("router")
    if exp_vault and info.get("vault") and info["vault"].lower() != exp_vault.lower():
        mismatches.append("vault")
    if exp_router and info.get("router") and info["router"].lower() != exp_router.lower():
        mismatches.append("router")
    result["mismatches"] = mismatches

    if info.get("entrypoint_selector_present") is False:
        result.update(status="BLOCKED", reason="expected_entrypoint_selector_absent")
    elif mismatches:
        result.update(status="BLOCKED",
                      reason=f"identity_mismatch:{','.join(mismatches)}")
    else:
        result.update(status="READY", reason="executor_identity_confirmed_onchain")
    return result


__all__ = [
    "FRESH_QUOTE_MAX_AGE_S", "LIMITED_LIVE_MODES",
    "probe_atomic_simulation", "probe_balancer_liquidity",
    "probe_freshness", "probe_mode_and_kill_switch",
    "resolve_executor_address", "probe_signer_readiness",
    "probe_executor_identity",
]
