"""Strategy IR schema, fingerprint identity and non-executable validation."""
import hashlib
import json
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from core.models import new_id, now_iso


class SourceClass(str, Enum):
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"
    MUTATED = "MUTATED"
    HYBRID = "HYBRID"


# Research strategy archetypes ArbiCore can economically evaluate. Unknown types
# are rejected (fail-closed) rather than silently accepted.
ALLOWED_STRATEGY_TYPES = frozenset({
    "dex_dex", "multi_hop", "triangular", "multi_dex_triangular",
    "stablecoin", "stable_volatile_mixed", "fee_tier", "cross_router",
    "same_dex", "flash_funded",
})

# Any of these keys (anywhere in the payload) would imply execution authority and
# are FORBIDDEN in a Strategy IR. Presence => hard reject. This is the core of the
# one-way, non-executable boundary.
FORBIDDEN_KEYS = frozenset({
    "private_key", "privatekey", "secret", "seed", "seed_phrase", "mnemonic",
    "signer", "signer_address", "sign", "signature",
    "calldata", "call_data", "userdata", "user_data", "raw_tx", "raw_transaction",
    "broadcast", "send_transaction", "sendraw",
    "execution_mode", "set_mode", "mode_override",
    "kill_switch", "killswitch", "disable_kill_switch", "disengage_kill",
    "authorize", "authorization", "auth_override", "execute", "auto_execute",
    "bypass", "bypass_simulation", "bypass_gate", "skip_simulation",
    "allowlist_override", "router_allowlist_override", "token_allowlist_override",
    "profitability_override", "profit_override", "simulation_override",
    "quote_freshness_override", "repayment_override", "risk_override",
    "amount_out_min_override", "min_output_override", "readiness_override",
    "live", "enable_live", "broadcast_authorization",
})


class StrategyIRValidationError(ValueError):
    pass


def _scan_forbidden(obj: Any, path: str = "") -> None:
    """Recursively reject any forbidden key (case-insensitive) in nested data."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_l = str(k).strip().lower().replace("-", "_").replace(" ", "_")
            if key_l in FORBIDDEN_KEYS:
                raise StrategyIRValidationError(
                    f"forbidden field '{k}' at '{path or '<root>'}' — Strategy IR is "
                    f"non-executable and must not carry execution/authorization data")
            _scan_forbidden(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _scan_forbidden(item, f"{path}[{i}]")


def _canonical(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _canonical(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_canonical(x) for x in obj]
    return obj


def compute_fingerprint(strategy_type: str, parameters: Dict[str, Any],
                        constraints: Dict[str, Any],
                        required_capabilities: List[str],
                        route_hints: List[Dict[str, Any]]) -> str:
    """Deterministic sha256 over the SEMANTIC definition only (type + params +
    constraints + capabilities + route hints). Excludes volatile fields
    (version, provenance, lineage, timestamps): identical semantics ⇒ identical
    fingerprint; a semantic change ⇒ a new fingerprint (a new strategy)."""
    payload = _canonical({
        "strategy_type": strategy_type,
        "parameters": parameters or {},
        "constraints": constraints or {},
        "required_capabilities": sorted(required_capabilities or []),
        "route_hints": route_hints or [],
    })
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sfp_" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


class StrategyProvenance(BaseModel):
    source: str                          # e.g. "strategy_factory", "github", "arxiv"
    source_ref: str = ""                 # URL / commit / DOI reference (no secrets)
    timestamp: str = Field(default_factory=now_iso)
    trust: float = 0.0                   # 0..1 upstream trust score (advisory only)
    confidence: float = 0.0              # 0..1 upstream confidence (advisory only)

    @field_validator("trust", "confidence")
    @classmethod
    def _unit_interval(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class StrategyIR(BaseModel):
    """A research strategy / hypothesis — DATA ONLY, non-executable."""
    strategy_id: str = Field(default_factory=new_id)
    strategy_version: int = 1
    strategy_fingerprint: str = ""       # derived; ignored/overwritten on validate
    strategy_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    required_capabilities: List[str] = Field(default_factory=list)
    route_hints: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: StrategyProvenance
    source_class: SourceClass = SourceClass.EXTERNAL
    lineage: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)

    @field_validator("strategy_version")
    @classmethod
    def _positive_version(cls, v: int) -> int:
        if int(v) < 1:
            raise ValueError("strategy_version must be >= 1")
        return int(v)

    @field_validator("strategy_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        t = str(v).strip().lower()
        if t not in ALLOWED_STRATEGY_TYPES:
            raise ValueError(f"unsupported strategy_type '{v}' "
                             f"(allowed: {sorted(ALLOWED_STRATEGY_TYPES)})")
        return t

    def validate_non_executable(self) -> "StrategyIR":
        """Reject any forbidden/execution-authority content and (re)derive the
        canonical fingerprint. Returns self for chaining."""
        _scan_forbidden(self.parameters, "parameters")
        _scan_forbidden(self.constraints, "constraints")
        _scan_forbidden(self.route_hints, "route_hints")
        _scan_forbidden({"required_capabilities": self.required_capabilities},
                        "required_capabilities")
        self.strategy_fingerprint = compute_fingerprint(
            self.strategy_type, self.parameters, self.constraints,
            self.required_capabilities, self.route_hints)
        return self

    def to_registry_doc(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["source_class"] = self.source_class.value
        return d
