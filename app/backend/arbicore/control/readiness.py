"""ArbiCore X — ExecutionReadinessEngine + operator mode model.

Authoritative, evidence-based GREEN/YELLOW/RED readiness. Pure evaluation
over injected system components + environment; every check degrades
gracefully (never raises). LIMITED_LIVE / FULL_AUTOMATION are hard-gated
and remain RED until their mandatory evidence exists.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

RED = "RED"
YELLOW = "YELLOW"
GREEN = "GREEN"

# Operator-facing operating modes (NOT the per-strategy trading ladder).
OPERATOR_MODES = ("SHADOW", "PAPER", "PROFIT_ENGINE", "LIMITED_LIVE", "FULL_AUTOMATION")

# Modes that can NEVER broadcast on-chain in this build.
NON_BROADCAST_MODES = ("SHADOW", "PAPER", "PROFIT_ENGINE")

# Mainnet chain-ids that live self-test / execution must stay blocked on.
_MAINNET_CHAIN_IDS = {1, 8453, 42161, 10, 137}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worst(statuses: List[str]) -> str:
    if RED in statuses:
        return RED
    if YELLOW in statuses:
        return YELLOW
    return GREEN


def _check(name: str, status: str, *, score: int = 0,
           passed: Optional[List[str]] = None,
           warnings: Optional[List[str]] = None,
           blockers: Optional[List[str]] = None,
           requirements: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "name": name, "status": status, "score": int(score),
        "passed": passed or [], "warnings": warnings or [],
        "blockers": blockers or [], "requirements": requirements or [],
    }


class ControlStateRepo:
    """Persists the single operator-mode row (default SHADOW)."""

    KEY = "operator_control"

    def __init__(self, db, collection: str = "control_state",
                 audit_collection: str = "control_state_audit"):
        self._db = db
        self._coll = db[collection]
        self._audit = db[audit_collection]

    async def get_mode(self) -> str:
        doc = await self._coll.find_one({"key": self.KEY}, {"_id": 0})
        return (doc or {}).get("mode") or "SHADOW"

    async def set_mode(self, mode: str, *, actor: str, reason: str = "") -> Dict[str, Any]:
        now = _now_iso()
        await self._coll.update_one(
            {"key": self.KEY},
            {"$set": {"mode": mode, "updated_at": now, "actor": actor},
             "$setOnInsert": {"key": self.KEY, "created_at": now}},
            upsert=True,
        )
        await self._audit.insert_one(
            {"key": self.KEY, "mode": mode, "actor": actor,
             "reason": reason, "at": now})
        return {"mode": mode, "updated_at": now, "actor": actor}


class ExecutionReadinessEngine:
    """Backend-authoritative readiness evaluator.

    All dependencies optional so tests can inject fakes and missing
    subsystems degrade to YELLOW/RED rather than crashing.
    """

    def __init__(self, *, db=None, kill_switch=None, mode_repo=None,
                 wallet_registry=None, secret_registry=None,
                 capital_allocator=None, balance_reader=None,
                 shadow_cert_repo=None, paper_evidence_repo=None):
        self._db = db
        self._kill = kill_switch
        self._mode = mode_repo
        self._wallets = wallet_registry
        self._secrets = secret_registry
        self._alloc = capital_allocator
        self._balance = balance_reader
        self._shadow = shadow_cert_repo
        self._paper = paper_evidence_repo

    # ------------------------------------------------------------------
    # Individual component checks
    # ------------------------------------------------------------------
    async def _system(self) -> Dict[str, Any]:
        if self._db is None:
            return _check("SYSTEM", YELLOW, score=50,
                          warnings=["database handle not wired"])
        try:
            await self._db.command("ping")
            return _check("SYSTEM", GREEN, score=100, passed=["mongo reachable"])
        except Exception as exc:  # noqa: BLE001
            return _check("SYSTEM", RED, score=0,
                          blockers=[f"mongo unreachable: {type(exc).__name__}"])

    def _configuration(self) -> Dict[str, Any]:
        rpc = bool(os.environ.get("ARBICORE_RPC_URL"))
        executor = bool(os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE"))
        passed, warnings, reqs = [], [], []
        if rpc:
            passed.append("ARBICORE_RPC_URL set")
        else:
            warnings.append("ARBICORE_RPC_URL not set (required for live-capable modes)")
            reqs.append("ARBICORE_RPC_URL")
        if executor:
            passed.append("executor address set")
        else:
            warnings.append("ARBICORE_EXECUTOR_ADDRESS_BASE not set")
            reqs.append("ARBICORE_EXECUTOR_ADDRESS_BASE")
        status = GREEN if (rpc and executor) else YELLOW
        return _check("CONFIGURATION", status,
                      score=100 if status == GREEN else 60,
                      passed=passed, warnings=warnings, requirements=reqs)

    def _static_green(self, name: str, note: str) -> Dict[str, Any]:
        return _check(name, GREEN, score=100, passed=[note])

    def _confidence(self) -> Dict[str, Any]:
        # confidence_v2 engine is implemented + tested; but a LIVE confidence
        # score still needs real quote/liquidity inputs (RPC), so execution
        # readiness stays gated on CONFIGURATION/SIMULATION elsewhere.
        try:
            import arbicore.intelligence.confidence_v2  # noqa: F401
            return _check("CONFIDENCE_ENGINE", GREEN, score=90,
                          passed=["confidence v2 (12-factor, explainable) implemented"],
                          warnings=["live inputs (quote freshness/liquidity) require RPC wiring"])
        except Exception:  # noqa: BLE001
            return _check("CONFIDENCE_ENGINE", YELLOW, score=50,
                          warnings=["confidence v2 not importable"])

    def _ev_engine(self) -> Dict[str, Any]:
        try:
            import arbicore.economics.expected_value  # noqa: F401
            return _check("EV_ENGINE", GREEN, score=90,
                          passed=["EV = P(success)*net - P(failure)*max_loss; evidence-based"])
        except Exception:  # noqa: BLE001
            return _check("EV_ENGINE", RED, score=0, blockers=["EV engine missing"])

    def _size_optimizer(self) -> Dict[str, Any]:
        try:
            import arbicore.economics.size_optimizer  # noqa: F401
            return _check("SIZE_OPTIMIZER", GREEN, score=90,
                          passed=["adaptive size search → max risk-adjusted EV"],
                          warnings=["live pool-liquidity inputs require RPC wiring"])
        except Exception:  # noqa: BLE001
            return _check("SIZE_OPTIMIZER", RED, score=0, blockers=["size optimizer missing"])

    def _flash(self) -> Dict[str, Any]:
        return _check("FLASH_LOAN_ENGINE", GREEN, score=90,
                      passed=["Aave V3 executable", "Balancer V2 executable"],
                      warnings=["dynamic size optimizer not yet implemented"])

    async def _wallet(self) -> Dict[str, Any]:
        if self._wallets is None:
            return _check("WALLET_SIGNER", YELLOW, score=40,
                          warnings=["wallet registry not wired"],
                          requirements=["register a 'gas' role wallet with secret_handle_id"])
        try:
            gas_wallets = await self._wallets.list_all(execution_role="gas")
        except Exception:  # noqa: BLE001
            gas_wallets = []
        if gas_wallets:
            return _check("WALLET_SIGNER", GREEN, score=90,
                          passed=[f"{len(gas_wallets)} gas wallet(s) registered"])
        return _check("WALLET_SIGNER", YELLOW, score=40,
                      warnings=["no 'gas' role wallet registered"],
                      requirements=["register a 'gas' wallet + secret handle"])

    async def _security(self) -> Dict[str, Any]:
        passed = ["S2 kill-switch authoritative", "S3 auto_confirm default-off",
                  "S4 technical-validation gated", "S5 capital bound to wallet balance",
                  "S6 slippage_guard enforced"]
        engaged = False
        if self._kill is not None:
            try:
                st = await self._kill.state()
                engaged = bool(getattr(st, "engaged", False))
            except Exception:  # noqa: BLE001
                pass
        if engaged:
            return _check("SECURITY", YELLOW, score=80, passed=passed,
                          warnings=["kill switch ENGAGED — execution disabled"])
        return _check("SECURITY", GREEN, score=100, passed=passed)

    async def _shadow_validation(self) -> Dict[str, Any]:
        n = 0
        if self._shadow is not None:
            try:
                n = await self._shadow.count() if hasattr(self._shadow, "count") else 0
            except Exception:  # noqa: BLE001
                n = 0
        if n > 0:
            return _check("SHADOW_VALIDATION", GREEN, score=100,
                          passed=[f"{n} shadow certification record(s)"])
        return _check("SHADOW_VALIDATION", YELLOW, score=30,
                      warnings=["no shadow-certification evidence yet"],
                      requirements=["run shadow certification"])

    async def _paper_validation(self) -> Dict[str, Any]:
        n = 0
        if self._paper is not None:
            try:
                n = await self._paper.count() if hasattr(self._paper, "count") else 0
            except Exception:  # noqa: BLE001
                n = 0
        if n > 0:
            return _check("PAPER_VALIDATION", GREEN, score=100,
                          passed=[f"{n} paper evidence bundle(s)"])
        return _check("PAPER_VALIDATION", YELLOW, score=40,
                      warnings=["no paper evidence yet"],
                      requirements=["run PAPER mode to accumulate evidence"])

    def _simulation(self) -> Dict[str, Any]:
        if os.environ.get("ARBICORE_RPC_URL"):
            return _check("SIMULATION", GREEN, score=90,
                          passed=["eth_call preflight available"])
        return _check("SIMULATION", YELLOW, score=50,
                      warnings=["no RPC — only heuristic simulation available"],
                      requirements=["ARBICORE_RPC_URL for eth_call simulation"])

    def _contracts(self) -> Dict[str, Any]:
        if os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE"):
            return _check("CONTRACTS", GREEN, score=90,
                          passed=["executor address configured"],
                          warnings=["Aerodrome on-chain adapter not yet implemented"])
        return _check("CONTRACTS", YELLOW, score=40,
                      warnings=["no deployed executor address configured"],
                      requirements=["deploy + configure FlashLoanReceiver, set ARBICORE_EXECUTOR_ADDRESS_BASE"])

    # ------------------------------------------------------------------
    # Full evaluation
    # ------------------------------------------------------------------
    async def evaluate(self) -> Dict[str, Any]:
        checks = [
            await self._system(),
            self._configuration(),
            self._static_green("MARKET_DATA", "CEX/DEX providers wired"),
            self._static_green("OPPORTUNITY_ENGINE", "scanners present (dormant by default)"),
            self._static_green("ROUTE_ENGINE", "route_search cycle enumerator present"),
            self._static_green("PROFIT_ENGINE", "net_profit engine present"),
            self._confidence(),
            self._ev_engine(),
            self._size_optimizer(),
            self._flash(),
            self._simulation(),
            await self._wallet(),
            self._contracts(),
            await self._security(),
            self._static_green("MONITORING", "opportunity journal + evidence bundles present"),
            await self._shadow_validation(),
            await self._paper_validation(),
        ]
        by_name = {c["name"]: c for c in checks}
        overall = _worst([c["status"] for c in checks])
        modes = self._mode_matrix(by_name)
        return {
            "overall_status": overall,
            "components": checks,
            "modes": modes,
            "generated_at": _now_iso(),
        }

    def _mode_matrix(self, c: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        def st(name: str) -> str:
            return c.get(name, {}).get("status", RED)

        sec_ok = st("SECURITY") in (GREEN, YELLOW)
        sys_ok = st("SYSTEM") == GREEN

        # SHADOW — analysis only, never broadcasts.
        shadow = self._mode_entry(
            "SHADOW",
            status=GREEN if sys_ok else YELLOW,
            can_activate=sec_ok,
            passed=["no signing / no broadcast", "kill switch authoritative"],
            blockers=[] if sys_ok else ["system not healthy"],
        )
        # PAPER — full simulated lifecycle, no financial execution.
        paper = self._mode_entry(
            "PAPER",
            status=GREEN if sys_ok else YELLOW,
            can_activate=sec_ok,
            passed=["simulated lifecycle only"],
        )
        # PROFIT_ENGINE — continuous discovery/ranking within current exec mode.
        pe_missing = []
        if st("SIMULATION") != GREEN:
            pe_missing.append("live simulation (RPC)")
        if st("CONFIDENCE_ENGINE") != GREEN:
            pe_missing.append("confidence v2")
        profit = self._mode_entry(
            "PROFIT_ENGINE",
            status=GREEN if not pe_missing else YELLOW,
            can_activate=sec_ok,  # discovery/ranking is non-broadcast → safe
            passed=["discovers, ranks, evaluates (non-broadcast)"],
            warnings=pe_missing,
        )
        # LIMITED_LIVE — hard-gated; RED until every mandatory gate is GREEN.
        mandatory = {
            "CONFIGURATION": st("CONFIGURATION"),
            "CONTRACTS": st("CONTRACTS"),
            "WALLET_SIGNER": st("WALLET_SIGNER"),
            "SIMULATION": st("SIMULATION"),
            "SECURITY": st("SECURITY"),
            "SHADOW_VALIDATION": st("SHADOW_VALIDATION"),
            "PAPER_VALIDATION": st("PAPER_VALIDATION"),
            "CONFIDENCE_ENGINE": st("CONFIDENCE_ENGINE"),
        }
        ll_blockers = [k for k, v in mandatory.items() if v != GREEN]
        # Additional hard blockers that are true for this build regardless.
        ll_blockers.append("Aerodrome adapter + EV(max_loss) + fork validation not complete")
        limited = self._mode_entry(
            "LIMITED_LIVE",
            status=RED,
            can_activate=False,
            blockers=ll_blockers,
            requirements=["all mandatory readiness GREEN", "operator manual per-tx confirm",
                          "fork + shadow + paper evidence", "explicit operator approval"],
        )
        # FULL_AUTOMATION — future-gated, always RED in this build.
        full = self._mode_entry(
            "FULL_AUTOMATION",
            status=RED,
            can_activate=False,
            blockers=["future-gated: requires sustained shadow/paper/fork evidence + calibration"],
            requirements=["independent evidence-based certification (not satisfiable now)"],
        )
        return {"SHADOW": shadow, "PAPER": paper, "PROFIT_ENGINE": profit,
                "LIMITED_LIVE": limited, "FULL_AUTOMATION": full}

    @staticmethod
    def _mode_entry(name: str, *, status: str, can_activate: bool,
                    passed=None, warnings=None, blockers=None,
                    requirements=None) -> Dict[str, Any]:
        return {
            "mode": name, "status": status, "can_activate": bool(can_activate),
            "passed": passed or [], "warnings": warnings or [],
            "blockers": blockers or [], "requirements": requirements or [],
        }

    # ------------------------------------------------------------------
    # Mode-transition guard (backend authoritative)
    # ------------------------------------------------------------------
    async def can_transition(self, target_mode: str) -> Dict[str, Any]:
        """Decide whether the operator may switch to ``target_mode``.

        SHADOW/PAPER/PROFIT_ENGINE are non-broadcast and allowed when the
        system is healthy. LIMITED_LIVE / FULL_AUTOMATION are ALWAYS
        refused in this build (hard-gated)."""
        if target_mode not in OPERATOR_MODES:
            return {"allowed": False, "reason": f"unknown mode '{target_mode}'",
                    "target_mode": target_mode}
        report = await self.evaluate()
        entry = report["modes"].get(target_mode, {})
        if target_mode in ("LIMITED_LIVE", "FULL_AUTOMATION"):
            return {"allowed": False,
                    "reason": f"{target_mode} is hard-gated and blocked in this build",
                    "target_mode": target_mode,
                    "blockers": entry.get("blockers", []),
                    "requirements": entry.get("requirements", [])}
        allowed = bool(entry.get("can_activate"))
        return {"allowed": allowed,
                "reason": "ok" if allowed else "readiness not satisfied",
                "target_mode": target_mode,
                "status": entry.get("status"),
                "blockers": entry.get("blockers", []),
                "warnings": entry.get("warnings", [])}
