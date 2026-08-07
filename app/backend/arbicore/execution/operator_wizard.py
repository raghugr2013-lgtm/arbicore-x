"""Flash Loan LIMITED_LIVE — Operator Readiness Aggregator.

Read-only backend service that exposes the state of every step the
operator must clear before broadcasting the first controlled Flash Loan
transaction on Base mainnet.

Design principles:
    * READ-ONLY. This module never writes; every mutating step is
      handled by the existing wave-6/wave-7 endpoints.
    * COMPOSES existing repos and helpers — no new state, no new
      collections. Wizard state is a *derived* view.
    * OFFLINE-SAFE. When ``ARBICORE_RPC_URL`` is absent, RPC-dependent
      steps degrade gracefully to ``PENDING`` with a clear reason.

Consumed by:
    * ``GET /api/arbicore/wizard/state``
    * ``GET /api/arbicore/executor/verify``
    * ``GET /api/arbicore/post-trade/latest``
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from eth_utils import keccak, to_checksum_address

from arbicore.execution.calldata import (
    BALANCER_V2_VAULT_BY_CHAIN,
    UNISWAP_V3_ROUTER_BY_CHAIN,
)


# --------------------------------------------------------------------------- #
# Utilities
# --------------------------------------------------------------------------- #

_STATUS_READY   = "READY"
_STATUS_WAIT    = "WAIT"      # something is configured but not fully wired
_STATUS_BLOCKED = "BLOCKED"   # required for LIMITED_LIVE and MISSING
_STATUS_INFO    = "INFO"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _selector(sig: str) -> str:
    return "0x" + keccak(text=sig)[:4].hex()


def _base_rpc_url() -> Optional[str]:
    for k in ("ARBICORE_RPC_URL_BASE", "ARBICORE_RPC_URL"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return None


def _rpc_post(url: str, method: str, params: List[Any], timeout: int = 6) -> Dict[str, Any]:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={
            "Content-Type": "application/json",
            # Public Base RPC endpoints (Coinbase CDP) 403 the default
            # Python-urllib User-Agent; send a browser-like UA so the
            # readiness/verify probes match the httpx runtime path.
            "User-Agent": "Mozilla/5.0 (ArbiCore-X readiness probe)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _decode_address(hex_word: str) -> str:
    """Decode a 32-byte ABI word into an EVM address."""
    hx = hex_word.lower().replace("0x", "")
    if len(hx) < 40:
        raise ValueError(f"cannot decode address from {hex_word!r}")
    return to_checksum_address("0x" + hx[-40:])


# --------------------------------------------------------------------------- #
# WizardStep — single row of the 10-step readiness table
# --------------------------------------------------------------------------- #

@dataclass
class WizardStep:
    key: str
    label: str
    status: str                              # READY | WAIT | BLOCKED | INFO
    detail: str = ""
    action_hint: str = ""
    fix_path: str = ""                       # UI deep-link (Phase 10.6)
    reason: str = ""                         # why this step is required
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Executor verification
# --------------------------------------------------------------------------- #

_SEL_VAULT  = _selector("balancerVault()")
_SEL_ROUTER = _selector("uniRouter()")
_SEL_AAVE   = _selector("aavePool()")
_SEL_OWNER  = _selector("owner()")

# The runtime uses chain="base" for BOTH Base mainnet and Base Sepolia;
# they are distinguished only by the RPC's reported chain id. Expected
# venue addresses are therefore keyed by numeric chain id.
_BASE_MAINNET_ID = 8453
_BASE_SEPOLIA_ID = 84532
_EXPECTED_VAULT_BY_ID = {
    _BASE_MAINNET_ID: "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
    _BASE_SEPOLIA_ID: "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
}
_EXPECTED_ROUTER_BY_ID = {
    _BASE_MAINNET_ID: "0x2626664c2603336E57B271c5C0b26F421741e481",
    _BASE_SEPOLIA_ID: "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4",
}
_EXPECTED_AAVE_BY_ID = {
    _BASE_MAINNET_ID: "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    _BASE_SEPOLIA_ID: "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27",
}


async def verify_executor(*, address: Optional[str] = None,
                          chain: str = "base",
                          expected_owner: Optional[str] = None,
                          ) -> Dict[str, Any]:
    """Verify a deployed FlashLoanReceiver contract.

    Steps performed (all read-only, none broadcast a tx):
        1. Resolve address — argument > ``ARBICORE_EXECUTOR_ADDRESS_BASE``.
        2. ``eth_getCode`` — proves the contract is deployed.
        3. ``eth_call VAULT()``  — must equal the Balancer V2 Vault on chain.
        4. ``eth_call ROUTER()`` — must equal the Uniswap V3 SwapRouter on chain.
        5. ``eth_call owner()``  — optional match against ``expected_owner``.
        6. Aggregate → READY | WAIT | BLOCKED.

    Every RPC failure downgrades to WAIT (not BLOCKED) so the operator
    can distinguish an infra problem from a config problem.
    """
    result: Dict[str, Any] = {
        "chain": chain,
        "address": None,
        "checks": {
            "address_configured":     {"status": _STATUS_BLOCKED, "detail": ""},
            "rpc_available":          {"status": _STATUS_BLOCKED, "detail": ""},
            "contract_deployed":      {"status": _STATUS_BLOCKED, "detail": ""},
            "vault_matches":          {"status": _STATUS_BLOCKED, "detail": ""},
            "router_matches":         {"status": _STATUS_BLOCKED, "detail": ""},
            "aave_pool_matches":      {"status": _STATUS_BLOCKED, "detail": ""},
            "owner_matches":          {"status": _STATUS_INFO,    "detail": "not checked"},
        },
        "expected": {},
        "generated_at": _iso_now(),
    }

    # (1) address resolution
    addr = (address or "").strip() or os.environ.get(
        "ARBICORE_EXECUTOR_ADDRESS_BASE", "",
    ).strip()
    if not addr:
        result["checks"]["address_configured"]["detail"] = (
            "no address supplied and ARBICORE_EXECUTOR_ADDRESS_BASE is unset"
        )
        result["overall_status"] = _STATUS_BLOCKED
        result["ready"] = False
        return result
    try:
        addr = to_checksum_address(addr)
    except Exception as exc:
        result["checks"]["address_configured"]["detail"] = f"invalid address: {exc}"
        result["overall_status"] = _STATUS_BLOCKED
        result["ready"] = False
        return result
    result["address"] = addr
    result["checks"]["address_configured"] = {"status": _STATUS_READY, "detail": addr}

    # (2) RPC availability
    rpc_url = _base_rpc_url()
    if not rpc_url:
        result["checks"]["rpc_available"] = {
            "status": _STATUS_WAIT,
            "detail": "ARBICORE_RPC_URL not set — cannot query chain",
        }
        result["overall_status"] = _STATUS_WAIT
        result["ready"] = False
        return result
    try:
        chain_id_resp = _rpc_post(rpc_url, "eth_chainId", [])
        chain_id_hex = (chain_id_resp.get("result") or "").strip()
        chain_id = int(chain_id_hex, 16) if chain_id_hex else 0
        result["checks"]["rpc_available"] = {
            "status": _STATUS_READY,
            "detail": f"chain_id={chain_id} @ {rpc_url}",
            "chain_id": chain_id,
        }
        result["expected"] = {
            "chain_id": chain_id,
            "vault":     _EXPECTED_VAULT_BY_ID.get(chain_id, ""),
            "router":    _EXPECTED_ROUTER_BY_ID.get(chain_id, ""),
            "aave_pool": _EXPECTED_AAVE_BY_ID.get(chain_id, ""),
        }
    except Exception as exc:
        result["checks"]["rpc_available"] = {
            "status": _STATUS_WAIT,
            "detail": f"RPC error: {type(exc).__name__}: {exc}",
        }
        result["overall_status"] = _STATUS_WAIT
        result["ready"] = False
        return result

    # (3) eth_getCode → deployed?
    try:
        code_resp = _rpc_post(rpc_url, "eth_getCode", [addr, "latest"])
        code = (code_resp.get("result") or "").strip()
        if not code or code in ("0x", "0x0"):
            result["checks"]["contract_deployed"] = {
                "status": _STATUS_BLOCKED,
                "detail": "no bytecode at address — contract not deployed",
            }
            result["overall_status"] = _STATUS_BLOCKED
            result["ready"] = False
            return result
        result["checks"]["contract_deployed"] = {
            "status": _STATUS_READY,
            "detail": f"bytecode length: {(len(code) - 2) // 2} bytes",
        }
    except Exception as exc:
        result["checks"]["contract_deployed"] = {
            "status": _STATUS_WAIT,
            "detail": f"eth_getCode error: {type(exc).__name__}: {exc}",
        }
        result["overall_status"] = _STATUS_WAIT
        result["ready"] = False
        return result

    # (4) eth_call VAULT()
    def _call_returns_address(selector: str) -> Optional[str]:
        try:
            resp = _rpc_post(rpc_url, "eth_call",
                             [{"to": addr, "data": selector}, "latest"])
            hexword = (resp.get("result") or "").strip()
            if not hexword or hexword == "0x":
                return None
            return _decode_address(hexword)
        except Exception:
            return None

    exp = result.get("expected", {})
    exp_vault  = (exp.get("vault") or "")
    exp_router = (exp.get("router") or "")
    exp_aave   = (exp.get("aave_pool") or "")

    vault = _call_returns_address(_SEL_VAULT)
    if vault and exp_vault and vault.lower() == exp_vault.lower():
        result["checks"]["vault_matches"] = {
            "status": _STATUS_READY,
            "detail": f"balancerVault() = {vault}",
        }
    else:
        result["checks"]["vault_matches"] = {
            "status": _STATUS_BLOCKED,
            "detail": (f"balancerVault() = {vault} (expected {exp_vault})"
                       if vault else "balancerVault() call reverted or returned empty"),
        }

    # (5) eth_call uniRouter()
    router = _call_returns_address(_SEL_ROUTER)
    if router and exp_router and router.lower() == exp_router.lower():
        result["checks"]["router_matches"] = {
            "status": _STATUS_READY,
            "detail": f"uniRouter() = {router}",
        }
    else:
        result["checks"]["router_matches"] = {
            "status": _STATUS_BLOCKED,
            "detail": (f"uniRouter() = {router} (expected {exp_router})"
                       if router else "uniRouter() call reverted or returned empty"),
        }

    # (5b) eth_call aavePool() — the first LIMITED_LIVE head is Aave V3.
    aave = _call_returns_address(_SEL_AAVE)
    if aave and exp_aave and aave.lower() == exp_aave.lower():
        result["checks"]["aave_pool_matches"] = {
            "status": _STATUS_READY,
            "detail": f"aavePool() = {aave}",
        }
    else:
        result["checks"]["aave_pool_matches"] = {
            "status": _STATUS_BLOCKED,
            "detail": (f"aavePool() = {aave} (expected {exp_aave})"
                       if aave else "aavePool() call reverted or returned empty"),
        }

    # (6) owner()
    owner = _call_returns_address(_SEL_OWNER)
    if owner:
        if expected_owner and owner.lower() == expected_owner.lower():
            result["checks"]["owner_matches"] = {
                "status": _STATUS_READY,
                "detail": f"owner() = {owner} (matches expected)",
            }
        else:
            result["checks"]["owner_matches"] = {
                "status": _STATUS_INFO,
                "detail": f"owner() = {owner}",
                "value": owner,
            }

    # Aggregate
    critical = [result["checks"][k]["status"]
                for k in ("address_configured", "contract_deployed",
                          "vault_matches", "router_matches", "aave_pool_matches")]
    if all(s == _STATUS_READY for s in critical):
        overall = _STATUS_READY
    elif _STATUS_BLOCKED in critical:
        overall = _STATUS_BLOCKED
    else:
        overall = _STATUS_WAIT
    result["overall_status"] = overall
    result["ready"] = overall == _STATUS_READY
    return result


# --------------------------------------------------------------------------- #
# RPC check
# --------------------------------------------------------------------------- #

async def check_rpc() -> Dict[str, Any]:
    """Ping the configured RPC — returns chain id + latest block."""
    rpc_url = _base_rpc_url()
    if not rpc_url:
        return {
            "status": _STATUS_BLOCKED,
            "detail": "ARBICORE_RPC_URL is not set in backend/.env",
            "generated_at": _iso_now(),
        }
    try:
        cid = _rpc_post(rpc_url, "eth_chainId", [])
        block = _rpc_post(rpc_url, "eth_blockNumber", [])
        chain_id = int((cid.get("result") or "0x0"), 16)
        block_num = int((block.get("result") or "0x0"), 16)
        return {
            "status": _STATUS_READY,
            "detail": (f"chain_id={chain_id}, block={block_num}, "
                       f"is_base={chain_id == 8453}"),
            "chain_id": chain_id,
            "block_number": block_num,
            "rpc_url_masked": rpc_url.split("//")[-1].split("/")[0],
            "is_base_mainnet": chain_id == 8453,
            "generated_at": _iso_now(),
        }
    except Exception as exc:
        return {
            "status": _STATUS_WAIT,
            "detail": f"RPC error: {type(exc).__name__}: {exc}",
            "generated_at": _iso_now(),
        }


# --------------------------------------------------------------------------- #
# Wizard aggregator
# --------------------------------------------------------------------------- #

async def build_wizard_state(*,
                              kill_switch_repo,
                              mode_repo,
                              wallet_registry,
                              secret_registry,
                              wallet_balance_reader,
                              certifier,
                              strategy: str = "flash_loan_arbitrage",
                              chain: str = "base",
                              ) -> Dict[str, Any]:
    steps: List[WizardStep] = []

    # 1. RPC configuration
    rpc = await check_rpc()
    if rpc["status"] == _STATUS_READY and rpc.get("is_base_mainnet"):
        rpc_status, rpc_detail = _STATUS_READY, rpc["detail"]
    elif rpc["status"] == _STATUS_READY:
        rpc_status = _STATUS_WAIT
        rpc_detail = f"connected but chain_id={rpc.get('chain_id')} (want 8453 = Base)"
    else:
        rpc_status, rpc_detail = _STATUS_BLOCKED, rpc.get("detail", "")
    steps.append(WizardStep(
        key="rpc",
        label="RPC configuration",
        status=rpc_status,
        detail=rpc_detail,
        action_hint="Set ARBICORE_RPC_URL=https://mainnet.base.org in backend/.env; restart backend",
        evidence={k: v for k, v in rpc.items() if k in
                  ("chain_id", "block_number", "rpc_url_masked", "is_base_mainnet")},
    ))

    # 2. Wallet registration
    try:
        wallets = await wallet_registry.list_all(chain=chain, execution_role="gas")
    except Exception:
        wallets = []
    gas_wallets = wallets
    if gas_wallets:
        steps.append(WizardStep(
            key="wallet",
            label="Wallet registration",
            status=_STATUS_READY,
            detail=f"{len(gas_wallets)} gas wallet(s) registered on {chain}",
            evidence={"wallets": [{"id": w.get("wallet_id"),
                                     "address": w.get("address"),
                                     "secret_handle_id": w.get("secret_handle_id") or ""}
                                    for w in gas_wallets]},
        ))
        primary_wallet = gas_wallets[0]
    else:
        primary_wallet = None
        steps.append(WizardStep(
            key="wallet",
            label="Wallet registration",
            status=_STATUS_BLOCKED,
            detail=f"no gas wallet registered on {chain}",
            action_hint="POST /api/arbicore/execution/wallets with { chain, address, execution_role: 'gas' }",
        ))

    # 3. Secret registration
    try:
        handles = await secret_registry.list_handles()
    except Exception:
        handles = []
    secret_count = len(handles)
    handle_id_for_wallet = (primary_wallet or {}).get("secret_handle_id") or ""
    has_secret = bool(handle_id_for_wallet) and any(
        (h.get("handle_id") == handle_id_for_wallet) for h in handles
    )
    if primary_wallet and has_secret:
        steps.append(WizardStep(
            key="secret",
            label="Secret registration (Fernet)",
            status=_STATUS_READY,
            detail=(f"secret registered for wallet {primary_wallet.get('wallet_id')} "
                    f"(handle {handle_id_for_wallet[:12]}…)"),
            evidence={"secret_count_total": secret_count,
                       "secret_handle_id": handle_id_for_wallet},
        ))
    elif primary_wallet:
        steps.append(WizardStep(
            key="secret",
            label="Secret registration (Fernet)",
            status=_STATUS_BLOCKED,
            detail=(f"wallet {primary_wallet.get('wallet_id')} "
                    "has no Fernet-wrapped key attached"),
            action_hint="PUT secret via /api/arbicore/execution/secrets then re-register wallet with the returned handle_id",
            evidence={"secret_count_total": secret_count},
        ))
    else:
        steps.append(WizardStep(
            key="secret",
            label="Secret registration (Fernet)",
            status=_STATUS_WAIT,
            detail="cannot evaluate — wallet registration missing",
        ))

    # 4. Gas wallet verification (balance)
    if primary_wallet and rpc["status"] == _STATUS_READY:
        try:
            reading = await wallet_balance_reader.read(
                chain=primary_wallet.get("chain") or "base",
                address=primary_wallet.get("address") or "",
            )
            native = float(reading.balance_native or 0)
            if native >= 0.005:
                steps.append(WizardStep(
                    key="gas_balance",
                    label="Gas wallet balance",
                    status=_STATUS_READY,
                    detail=f"{native:.6f} ETH on {chain}",
                    evidence={"native_balance_eth": native},
                ))
            elif native > 0:
                steps.append(WizardStep(
                    key="gas_balance",
                    label="Gas wallet balance",
                    status=_STATUS_WAIT,
                    detail=f"only {native:.6f} ETH — recommend >= 0.005 for safety",
                    action_hint="Send ~0.02 ETH to the burner wallet on Base",
                    evidence={"native_balance_eth": native},
                ))
            else:
                steps.append(WizardStep(
                    key="gas_balance",
                    label="Gas wallet balance",
                    status=_STATUS_BLOCKED,
                    detail="0 ETH — cannot pay for gas",
                    action_hint="Send ~0.02 ETH to the burner wallet on Base",
                    evidence={"native_balance_eth": native},
                ))
        except Exception as exc:
            steps.append(WizardStep(
                key="gas_balance",
                label="Gas wallet balance",
                status=_STATUS_WAIT,
                detail=f"balance read failed: {type(exc).__name__}: {exc}",
            ))
    else:
        steps.append(WizardStep(
            key="gas_balance",
            label="Gas wallet balance",
            status=_STATUS_WAIT,
            detail="cannot evaluate — wallet or RPC not ready",
        ))

    # 5. FlashLoanReceiver deployment
    exec_addr = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE", "").strip()
    if exec_addr and rpc["status"] == _STATUS_READY:
        exec_verify = await verify_executor(chain=chain)
        exec_status = exec_verify["overall_status"]
        exec_detail_bits: List[str] = []
        for k, v in exec_verify["checks"].items():
            if v["status"] == _STATUS_BLOCKED:
                exec_detail_bits.append(f"{k}: {v['detail']}")
        steps.append(WizardStep(
            key="executor",
            label="FlashLoanReceiver deployment",
            status=exec_status,
            detail=(f"address {exec_addr} · " +
                    ("verified" if exec_status == _STATUS_READY
                     else "; ".join(exec_detail_bits) or "pending")),
            action_hint=("Deploy contracts/FlashLoanReceiver.sol on Base "
                         "then set ARBICORE_EXECUTOR_ADDRESS_BASE"),
            evidence=exec_verify,
        ))
    elif exec_addr:
        steps.append(WizardStep(
            key="executor",
            label="FlashLoanReceiver deployment",
            status=_STATUS_WAIT,
            detail="address configured but RPC not ready",
            action_hint="Set ARBICORE_RPC_URL first",
        ))
    else:
        steps.append(WizardStep(
            key="executor",
            label="FlashLoanReceiver deployment",
            status=_STATUS_BLOCKED,
            detail="ARBICORE_EXECUTOR_ADDRESS_BASE not set",
            action_hint=("Deploy contracts/FlashLoanReceiver.sol on Base "
                         "(see canonical_repo/contracts/DEPLOY.md), "
                         "then set ARBICORE_EXECUTOR_ADDRESS_BASE"),
        ))

    # 6. Executor verification (duplicate summary, exposes contract identity)
    steps.append(WizardStep(
        key="executor_verify",
        label="Executor identity verification",
        status=(steps[-1].status if exec_addr else _STATUS_WAIT),
        detail=("VAULT() + ROUTER() checks — see step 5"
                if exec_addr else "cannot verify — no executor address"),
    ))

    # 7. Kill Switch — must be DISENGAGED to broadcast
    try:
        ks = await kill_switch_repo.state()
        ks_dict = ks.to_dict()
        if not ks_dict.get("engaged"):
            steps.append(WizardStep(
                key="kill_switch",
                label="Kill Switch",
                status=_STATUS_READY,
                detail="DISENGAGED — broadcasting allowed",
                evidence=ks_dict,
            ))
        else:
            steps.append(WizardStep(
                key="kill_switch",
                label="Kill Switch",
                status=_STATUS_BLOCKED,
                detail=f"ENGAGED: {ks_dict.get('reason','no reason set')}",
                action_hint="POST /api/arbicore/execution/kill-switch/disengage",
                evidence=ks_dict,
            ))
    except Exception as exc:
        steps.append(WizardStep(
            key="kill_switch",
            label="Kill Switch",
            status=_STATUS_WAIT,
            detail=f"state unavailable: {type(exc).__name__}: {exc}",
        ))

    # 8. Certification pass — we don't rerun here (has side effects); we
    #    surface the last known cert if any, else INFO.
    steps.append(WizardStep(
        key="certification",
        label="Certification pass",
        status=_STATUS_INFO,
        detail=("Run the 11-stage certifier from the Flash Loan Operator page; "
                "all stages must PASS."),
        action_hint="POST /api/arbicore/execution/certification/run",
    ))

    # 9. Mode ladder — strategy must be LIMITED_LIVE
    try:
        mode = await mode_repo.get(strategy)
        m = (mode or {}).get("mode") or "SHADOW"
        if m == "LIMITED_LIVE":
            steps.append(WizardStep(
                key="mode",
                label="Execution mode",
                status=_STATUS_READY,
                detail=f"{strategy} = LIMITED_LIVE",
                evidence={"strategy": strategy, "mode": m},
            ))
        else:
            steps.append(WizardStep(
                key="mode",
                label="Execution mode",
                status=_STATUS_WAIT,
                detail=f"{strategy} = {m} (need LIMITED_LIVE)",
                action_hint=(f"POST /api/arbicore/execution/mode/{strategy} "
                             "{ mode: 'LIMITED_LIVE', reason: '...' }"),
                evidence={"strategy": strategy, "mode": m},
            ))
    except Exception as exc:
        steps.append(WizardStep(
            key="mode",
            label="Execution mode",
            status=_STATUS_WAIT,
            detail=f"mode read failed: {type(exc).__name__}: {exc}",
        ))

    # 10. Final execution checklist (aggregate)
    blockers = [s for s in steps if s.status == _STATUS_BLOCKED]
    if blockers:
        overall = _STATUS_BLOCKED
        detail = f"{len(blockers)} blocking step(s): " + \
                 ", ".join(s.key for s in blockers)
    elif any(s.status == _STATUS_WAIT for s in steps
             if s.key not in ("certification",)):
        overall = _STATUS_WAIT
        detail = "some steps still WAIT — resolve before broadcast"
    else:
        overall = _STATUS_READY
        detail = "all prerequisites cleared — operator may broadcast"
    steps.append(WizardStep(
        key="final",
        label="Final execution checklist",
        status=overall,
        detail=detail,
        action_hint=("From the Flash Loan Operator page: Prepare broadcast → "
                     "review preflight → Confirm."),
        fix_path="/v2/flash-loan-operator",
        reason="This is where the operator submits and confirms the plan.",
    ))

    # Phase 10.6 — enrich every step with a fix_path + reason so the UI
    # can render tap-and-go navigation for every blocker.
    _FIX_PATHS: Dict[str, str] = {
        "rpc":              "/v2/settings/network",
        "wallet":           "/v2/flash-loan-operator",  # wallet registration lives here
        "secret":           "/v2/settings/secrets",
        "gas_balance":      "/v2/flash-loan-operator",
        "executor":         "/v2/executor-verify",
        "executor_verify":  "/v2/executor-verify",
        "kill_switch":      "/v2/flash-loan-operator",
        "certification":    "/v2/flash-loan-operator",
        "mode":             "/v2/flash-loan-operator",
        "final":            "/v2/flash-loan-operator",
    }
    _REASONS: Dict[str, str] = {
        "rpc":              "The backend must reach Base to preflight and broadcast.",
        "wallet":           "A registered gas wallet is needed to sign the transaction.",
        "secret":           "The wallet's private key must be Fernet-wrapped so the signer can resolve it.",
        "gas_balance":      "The burner needs ETH on Base to pay gas.",
        "executor":         "FlashLoanReceiver.sol must be deployed on Base and its address configured.",
        "executor_verify":  "The deployed contract's VAULT() and ROUTER() must match the Balancer + Uniswap addresses.",
        "kill_switch":      "Broadcast is refused at gate 1 while the kill switch is engaged.",
        "certification":    "The 11-stage certifier must pass before LIMITED_LIVE broadcasts.",
        "mode":             "The strategy must be in LIMITED_LIVE mode; SHADOW blocks the broadcast at gate 2.",
        "final":            "This is where the operator submits and confirms the plan.",
    }
    for s in steps:
        if not s.fix_path:
            s.fix_path = _FIX_PATHS.get(s.key, "")
        if not s.reason:
            s.reason = _REASONS.get(s.key, "")

    return {
        "strategy": strategy,
        "chain": chain,
        "overall_status": overall,
        "ready_to_broadcast": overall == _STATUS_READY,
        "steps": [s.to_dict() for s in steps],
        "step_count": len(steps),
        "blockers": [s.key for s in blockers],
        "generated_at": _iso_now(),
    }


# --------------------------------------------------------------------------- #
# Phase 10.6 — Family-specific prerequisite checker
# --------------------------------------------------------------------------- #

async def check_flash_loan_prereqs(*,
                                     kill_switch_repo, mode_repo,
                                     wallet_registry, secret_registry,
                                     wallet_balance_reader, scanner_repo=None,
                                     network_repo=None, chain: str = "base",
                                     ) -> Dict[str, Any]:
    """Compact, family-scoped prerequisite check.

    Returns a shape callers can render as an inline banner on the
    Flash Loan Operator page BEFORE the operator hits Broadcast.

        {
          "ok": bool,
          "family": "flash_loan_arb",
          "chain": "base",
          "checks": [{key, status, detail, fix_path}, ...],
          "unmet": [key, ...],   # blocking prereqs
        }
    """
    checks: List[Dict[str, Any]] = []

    # 1. Base network enabled + RPC configured
    rpc_ok = False
    if network_repo is not None:
        try:
            cfg = await network_repo.get()
            chains_on = (cfg.get("chains_enabled") or {}).get(chain, False)
            rpcs = (cfg.get("rpc_urls") or {}).get(chain) or []
            rpc_ok = bool(chains_on) and bool(rpcs)
        except Exception:  # noqa: BLE001
            rpc_ok = False
    checks.append({
        "key": "base_network_enabled",
        "status": _STATUS_READY if rpc_ok else _STATUS_BLOCKED,
        "detail": f"chain '{chain}' enabled and RPC configured" if rpc_ok
                   else f"chain '{chain}' disabled OR no RPC in Network config",
        "fix_path": "/v2/settings/network",
    })

    # 2. RPC health — use check_rpc
    try:
        rpc_health = await check_rpc()
        rpc_healthy = rpc_health.get("status") == _STATUS_READY \
                       and rpc_health.get("is_base_mainnet")
    except Exception:  # noqa: BLE001
        rpc_healthy = False
    checks.append({
        "key": "rpc_healthy",
        "status": _STATUS_READY if rpc_healthy else _STATUS_WAIT,
        "detail": "RPC pings and returns chain_id=8453" if rpc_healthy
                   else "RPC unreachable or wrong chain",
        "fix_path": "/v2/settings/network",
    })

    # 3. Wallet registered
    try:
        gas_wallets = await wallet_registry.list_all(chain=chain,
                                                       execution_role="gas")
    except Exception:  # noqa: BLE001
        gas_wallets = []
    wallet_ok = len(gas_wallets) > 0
    checks.append({
        "key": "wallet_registered",
        "status": _STATUS_READY if wallet_ok else _STATUS_BLOCKED,
        "detail": f"{len(gas_wallets)} gas wallet(s) on {chain}",
        "fix_path": "/v2/flash-loan-operator",
    })

    # 4. Secret available
    try:
        handles = await secret_registry.list_handles()
    except Exception:  # noqa: BLE001
        handles = []
    handle_id = (gas_wallets[0].get("secret_handle_id") if gas_wallets else "") or ""
    secret_ok = bool(handle_id) and any(
        h.get("handle_id") == handle_id for h in handles
    )
    checks.append({
        "key": "secret_available",
        "status": _STATUS_READY if secret_ok else _STATUS_BLOCKED,
        "detail": "Fernet-wrapped key attached to gas wallet" if secret_ok
                   else "no secret bound to the gas wallet",
        "fix_path": "/v2/settings/secrets",
    })

    # 5. Executor verified
    exec_ready = False
    try:
        vr = await verify_executor(chain=chain)
        exec_ready = vr.get("ready") is True
    except Exception:  # noqa: BLE001
        exec_ready = False
    checks.append({
        "key": "executor_verified",
        "status": _STATUS_READY if exec_ready else _STATUS_BLOCKED,
        "detail": "FlashLoanReceiver bytecode + VAULT + ROUTER checks green"
                   if exec_ready else "executor not deployed or verification failed",
        "fix_path": "/v2/executor-verify",
    })

    # 6. Scanner family enabled
    family_on = False
    if scanner_repo is not None:
        try:
            fam = await scanner_repo.get_family("flash_loan_arb")
            family_on = bool(fam.get("enabled"))
        except Exception:  # noqa: BLE001
            family_on = False
    checks.append({
        "key": "scanner_family_enabled",
        "status": _STATUS_READY if family_on else _STATUS_WAIT,
        "detail": "Flash Loan scanner family enabled" if family_on
                   else "Flash Loan family disabled — opportunities won't be discovered",
        "fix_path": "/v2/settings/scanner",
    })

    # 7. Mode = LIMITED_LIVE
    try:
        mode = await mode_repo.get("flash_loan_arbitrage")
        m = (mode or {}).get("mode") or "SHADOW"
        mode_ok = (m == "LIMITED_LIVE")
    except Exception:  # noqa: BLE001
        mode_ok = False
        m = "?"
    checks.append({
        "key": "mode_limited_live",
        "status": _STATUS_READY if mode_ok else _STATUS_WAIT,
        "detail": f"strategy mode = {m}",
        "fix_path": "/v2/flash-loan-operator",
    })

    # 8. Kill switch disengaged
    try:
        ks = await kill_switch_repo.state()
        engaged = ks.to_dict().get("engaged")
    except Exception:  # noqa: BLE001
        engaged = True
    checks.append({
        "key": "kill_switch_disengaged",
        "status": _STATUS_READY if not engaged else _STATUS_BLOCKED,
        "detail": "kill switch DISENGAGED" if not engaged else "kill switch ENGAGED",
        "fix_path": "/v2/flash-loan-operator",
    })

    unmet = [c["key"] for c in checks if c["status"] == _STATUS_BLOCKED]
    return {
        "family": "flash_loan_arb",
        "chain": chain,
        "ok": len(unmet) == 0,
        "checks": checks,
        "unmet": unmet,
        "generated_at": _iso_now(),
    }


# --------------------------------------------------------------------------- #
# Post-trade dashboard aggregator
# --------------------------------------------------------------------------- #

async def latest_broadcast_receipts(*,
                                     plans_repo,
                                     evidence_repo=None,
                                     limit: int = 5,
                                     ) -> Dict[str, Any]:
    """Return the last N broadcast attempts against real plans.

    Sources — read-only, best-effort:
        * ``execution_plans`` collection: `broadcast_last_result` field
          (populated by ``LimitedLiveBroadcaster`` on each attempt).
        * ``evidence_bundles`` collection: latest signed receipt bundles.
    """
    try:
        plans = await plans_repo.list_recent(limit=200)
    except Exception:
        plans = []
    receipts: List[Dict[str, Any]] = []
    for p in plans:
        r = p.get("broadcast_last_result") or p.get("broadcast_receipt")
        if not r:
            continue
        receipts.append({
            "plan_id": p.get("plan_id"),
            "strategy": p.get("strategy"),
            "chain": p.get("chain"),
            "mode": (r.get("mode") or p.get("mode") or "").upper(),
            "broadcast_sent": bool(r.get("broadcast_sent")),
            "tx_hash": r.get("tx_hash") or "",
            "gas_used": r.get("gas_used") or r.get("gas_limit_hint"),
            "gas_price_wei": r.get("gas_price_wei"),
            "nonce": r.get("nonce"),
            "preflight_ok": r.get("preflight_ok"),
            "gate_denied": r.get("gate_denied"),
            "denied_reason": r.get("denied_reason"),
            "borrow_amount_wei": p.get("borrow_amount_wei"),
            "borrow_token": p.get("borrow_token"),
            "recipient": p.get("recipient"),
            "profit_recipient": p.get("profit_recipient"),
            "attempted_at": r.get("at") or p.get("updated_at"),
            "evidence_ref": r.get("evidence_ref"),
        })
        if len(receipts) >= limit:
            break

    latest = receipts[0] if receipts else None
    return {
        "count": len(receipts),
        "latest": latest,
        "receipts": receipts,
        "generated_at": _iso_now(),
    }
