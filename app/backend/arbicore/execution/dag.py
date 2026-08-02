"""Wave 6B · Execution DAG value objects + planner.

Generic pipeline shape (provider-agnostic):

    BORROW  →  SWAP[+]  →  REPAY  →  PROFIT

Every step is a fully-specified **structured intent** — contract
address, function name, ABI signature, args, chain — but no bytes-level
calldata encoding.  Bytes-level encoding + on-chain simulation land in
Wave 6C.  This keeps Wave 6B strictly "planning" without introducing
web3-py as a runtime dependency.

Invariants:
    * A plan is a value object.  Equal inputs → equal (deterministic)
      plan payload → equal evidence hash.
    * ``mode`` is always ``"SHADOW"`` at this wave (broadcast-guard
      Wave-6A ladder enforces this; the planner rejects any plan
      whose target strategy is not at ``SHADOW`` or lower).
    * Plans never contain private key material; ``signer_wallet_id``
      is a reference resolved by the future Wave-6D signer, not a key.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Step + Plan value objects
# ---------------------------------------------------------------------------

STEP_KINDS: tuple = ("borrow", "swap", "repay", "profit")


@dataclass
class ExecutionStep:
    """One node in the execution DAG."""
    step_index: int
    kind: str                           # borrow | swap | repay | profit
    provider: str                       # e.g. "aave_v3", "uniswap_v3", "balancer_v2"
    chain: str
    contract_address: Optional[str]
    function_signature: Optional[str]   # ABI signature, e.g. "flashLoan(address,uint256,bytes)"
    args: List[Any]                     # decoded args (bytes-level encoding = Wave 6C)
    value_wei: int = 0                  # native value to send with the call
    depends_on: List[int] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class ExecutionPlan:
    """A complete Borrow → Swap[+] → Repay → Profit plan.

    Wave-5 evidence signer picks these up via
    ``source_component="execution_plan"`` (registered in Wave-6E).
    Wave 6B persists them locally for operator review.
    """
    plan_id: str
    strategy: str
    mode: str                           # always "SHADOW" in Wave 6B
    opportunity_id: Optional[str]
    chain: str
    borrow_token: str
    borrow_amount_wei: int
    borrow_amount_usd: Optional[float]
    flash_loan_provider: str
    dex_route: List[str]                # ordered list of DEX providers used
    signer_wallet_id: Optional[str]
    steps: List[ExecutionStep]
    economics: Dict[str, Any]           # populated by dry_run
    created_at: str
    plan_hash: str
    provider_versions: Dict[str, str]   # each adapter's semantic version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "strategy": self.strategy,
            "mode": self.mode,
            "opportunity_id": self.opportunity_id,
            "chain": self.chain,
            "borrow_token": self.borrow_token,
            "borrow_amount_wei": self.borrow_amount_wei,
            "borrow_amount_usd": self.borrow_amount_usd,
            "flash_loan_provider": self.flash_loan_provider,
            "dex_route": list(self.dex_route),
            "signer_wallet_id": self.signer_wallet_id,
            "steps": [s.to_dict() for s in self.steps],
            "economics": copy.deepcopy(self.economics),
            "created_at": self.created_at,
            "plan_hash": self.plan_hash,
            "provider_versions": dict(self.provider_versions),
        }


# ---------------------------------------------------------------------------
# Canonical serialisation + hash (deterministic)
# ---------------------------------------------------------------------------

def _canon(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    return value


def plan_hash(plan_dict: Dict[str, Any]) -> str:
    """SHA-256 over the plan payload minus volatile fields."""
    subset = {k: v for k, v in plan_dict.items()
              if k not in ("plan_id", "created_at", "plan_hash")}
    canonical = json.dumps(_canon(subset), sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_plan_id() -> str:
    return f"plan-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def validate_dag(steps: List[ExecutionStep]) -> None:
    """Ensures the DAG contains the mandatory sequence Borrow →
    Swap[+] → Repay → Profit and that every ``depends_on`` reference is
    valid + acyclic."""
    if not steps:
        raise ValueError("empty plan")
    kinds = [s.kind for s in steps]
    for k in kinds:
        if k not in STEP_KINDS:
            raise ValueError(f"unknown step kind '{k}'")
    if kinds[0] != "borrow":
        raise ValueError("first step must be 'borrow'")
    if kinds[-1] != "profit":
        raise ValueError("last step must be 'profit'")
    if "repay" not in kinds:
        raise ValueError("plan must contain a 'repay' step")
    # Repay must precede profit.
    if kinds.index("repay") >= kinds.index("profit"):
        raise ValueError("'repay' must precede 'profit'")
    # At least one swap between borrow and repay.
    swap_span = kinds.index("repay") - 1
    if swap_span < 1 or kinds[1] != "swap":
        raise ValueError("plan must contain at least one 'swap' between borrow and repay")
    # Acyclicity: depends_on must point to earlier indices.
    seen = set()
    for s in steps:
        for dep in s.depends_on:
            if dep >= s.step_index or dep < 0 or dep not in seen:
                raise ValueError(
                    f"step {s.step_index} has invalid depends_on={dep}"
                )
        seen.add(s.step_index)
