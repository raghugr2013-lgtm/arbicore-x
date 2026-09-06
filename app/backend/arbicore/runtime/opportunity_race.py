"""Six-Chain READ-ONLY Opportunity Race — orchestration layer (SHADOW).

This is a SMALL orchestration component. It does NOT implement a new arbitrage
engine and it does NOT replace the canonical Base OpportunityEngine / the frozen
Base ``ContinuousScanner``. It continuously watches the EXISTING real-data
opportunity surface across the six supported chains and reports whether any
genuinely positive NET opportunity exists — surfacing it as an
OPERATOR_ACTION_REQUIRED candidate. It NEVER executes.

Reuses (never duplicates):
  * ``arbicore.runtime.multichain_readiness.supported_networks``  — the universe
  * ``scripts.vps_runtime_certify._certify_chain``                — the existing
    per-chain read-only DISCOVER→QUOTE→LIQUIDITY→NET-ECONOMICS pipeline (which
    itself composes ``discover_pools_parallel`` + ``QuoterRegistry`` +
    ``compute_true_net_profit`` + the fail-closed economic gates).
  * The Base canonical M3 path is composed at THIS orchestration level via an
    injectable ``base_evaluator`` (the Base engine is never rewritten here).

ABSOLUTE SAFETY (invariant, always): signing=False, broadcast=False,
auto_execution=False, full_live=False. A positive opportunity produces evidence
+ operator-visible state ONLY — never a signed/broadcast transaction, never an
executor call, never a mode promotion, never an autostart in production.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

# Immutable read-only safety posture surfaced on every result/status.
SAFETY_POSTURE: Dict[str, Any] = {
    "posture": "SHADOW / detection-only / fail-closed / read-only",
    "signing": False,
    "broadcast": False,
    "auto_execution": False,
    "full_live": False,
    "withdrawals": False,
}

# Status tokens for a per-chain leg of the race.
STATUS_EVALUATED = "EVALUATED"
STATUS_SKIPPED = "SKIPPED"      # no operator RPC / canonical-deferred (honest)
STATUS_TIMEOUT = "TIMEOUT"      # this chain's leg exceeded per_chain_timeout_s
STATUS_ERROR = "ERROR"          # this chain's leg raised — isolated from others


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ChainEvaluator = Callable[[str, int], Awaitable[Dict[str, Any]]]


async def _default_chain_evaluator(chain: str, pairs_cap: int) -> Dict[str, Any]:
    """Non-Base chains: reuse the existing read-only per-chain certifier."""
    from scripts.vps_runtime_certify import _certify_chain
    return await _certify_chain(chain, cap=pairs_cap)


async def _default_base_evaluator(chain: str, pairs_cap: int) -> Dict[str, Any]:
    """Base leg: COMPOSE the existing canonical Base M3 candidate path.

    This reuses the canonical read-only building blocks WITHOUT modifying or
    duplicating the Base engine / ContinuousScanner:
      * ``m3_0_real_candidate_scan.CANDIDATES``            — genuine Base cycles
      * ``runtime.composition.build_controlled_live_safety`` — real validator
      * ``m3_0_vps_validate._probe_fresh_stages``          — the real quote →
        liquidity/TVL → gas → flash-loan → MEV/slippage → all-in-cost pipeline
      * ``m3_0_real_candidate_scan.validate_candidate``    — the real
        PreBroadcastValidator gates (authoritative ``m3_final_gates.ok``)

    Emits the SAME ``_certify_chain``-shaped dict the orchestrator normalizes.
    Genuinely fail-closed: no Base RPC ⇒ SKIPPED; a candidate is only
    ECONOMICALLY_VALID when the real M3 gate passes, and only surfaced as a
    positive-NET opportunity when the on-chain all-in net (>0) is verified. No
    fabrication, no gross-only positives, no signing/broadcast."""
    import time as _time

    from arbicore.config.persistent import resolve_rpc_url_from_env
    url = resolve_rpc_url_from_env("base")
    if not url:
        return {"skipped": "no_operator_configured_rpc",
                "head": {"block": None, "error": "no_rpc"},
                "rows": [], "candidates": []}

    from arbicore.providers.rpc import EthJsonRpcProvider
    try:
        head_block = await EthJsonRpcProvider(chain="base", url=url).eth_get_block_number()
    except Exception as exc:  # noqa: BLE001 — RPC fault fail-closed (isolated)
        return {"skipped": None, "head": {"block": None,
                "error": f"{type(exc).__name__}: {exc}"}, "rows": [], "candidates": []}

    from arbicore.execution.quoter import QuoterRegistry
    from arbicore.runtime.composition import build_controlled_live_safety
    from scripts.m3_0_real_candidate_scan import (
        CANDIDATES, validate_candidate, _controlled_live_unavailable_reason)
    from scripts.m3_0_vps_validate import _probe_fresh_stages

    quoter = QuoterRegistry()
    validator, _breaker = build_controlled_live_safety(quoter)
    unavailable = None if validator is not None else _controlled_live_unavailable_reason(quoter)

    rows: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    for c in CANDIDATES:
        plan = {"strategy": "flash_loan_arbitrage", "chain": "base",
                "opportunity_id": f"race-scan:{c['name']}",
                "borrow_token": c["borrow_token"],
                "borrow_amount_usd": c["borrow_amount_usd"],
                "flash_loan_provider": "balancer_v2",
                "route_pools": c["route_pools"],
                "cycle_token_path": c["cycle_token_path"],
                "quoted_block": head_block,
                "deadline_ts": _time.time() + 120.0}
        probe = await _probe_fresh_stages(plan, quoter)
        m3 = await validate_candidate(validator, plan, unavailable)

        facts = probe.get("stage_6_facts")
        quotable = bool(isinstance(facts, dict) and facts.get("route_quote_status") == "ok")
        liq_ok = bool(isinstance(facts, dict)
                      and (facts.get("min_pool_tvl_usd_in_route") or 0) > 0)
        all_in = probe.get("stage_10_all_in_cost") or {}
        net = (all_in.get("net_profit_all_in_usd")
               if isinstance(all_in, dict) and all_in.get("available") else None)
        ok = bool(m3.get("ok"))
        rows.append({"venue": "base_canonical_m3", "pair": c["name"],
                     "quotable": quotable, "liquidity_verified": liq_ok})
        candidates.append({
            "chain": "base", "block": head_block,
            "pair": c["name"], "venue": "base_canonical_m3",
            "strategy": "flash_loan_arbitrage",
            "token_path": c["cycle_token_path"],
            "borrow": c["borrow_token"],
            "stages": {"DISCOVERED": True, "QUOTABLE": quotable,
                       "LIQUIDITY_VERIFIED": liq_ok,
                       "ECONOMICALLY_VALID": ok, "LIMITED_LIVE_ELIGIBLE": False},
            "all_in_net_usd": net,
            "gross_profit_usd": (facts.get("gross_profit_pct")
                                 if isinstance(facts, dict) else None),
            "m3_final_gates": m3.get("gates"),
            "eliminated_at": None if ok else "M3_GATES",
            "reason": None if ok else ((m3.get("reasons") or ["m3_gates_denied"])[0]),
            "evidence_id": f"cand:base:m3:{c['name']}:blk{head_block}",
        })

    return {"skipped": None, "head": {"block": head_block, "error": None},
            "rows": rows, "candidates": candidates}


@dataclass
class ChainRaceResult:
    chain: str
    status: str
    candidates_seen: int = 0
    candidates_quoted: int = 0
    candidates_liquidity_verified: int = 0
    economically_valid: int = 0
    positive_net_count: int = 0
    best_net_usd: Optional[float] = None
    head_block: Optional[int] = None
    last_error: Optional[str] = None
    reason: Optional[str] = None
    evidence_ids: List[str] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain": self.chain,
            "status": self.status,
            "candidates_seen": self.candidates_seen,
            "candidates_quoted": self.candidates_quoted,
            "candidates_liquidity_verified": self.candidates_liquidity_verified,
            "economically_valid": self.economically_valid,
            "positive_net_count": self.positive_net_count,
            "best_net_usd": self.best_net_usd,
            "head_block": self.head_block,
            "last_error": self.last_error,
            "reason": self.reason,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass
class RaceResult:
    race_id: str
    scan_started_at: str
    scan_finished_at: str
    interval: int
    chains: List[str]
    per_chain: Dict[str, ChainRaceResult]
    candidates_seen: int
    candidates_quoted: int
    candidates_liquidity_verified: int
    economically_valid: int
    positive_net_count: int
    best_candidate: Optional[Dict[str, Any]]
    operator_action_required: bool
    safety_posture: Dict[str, Any] = field(default_factory=lambda: dict(SAFETY_POSTURE))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "race_id": self.race_id,
            "scan_started_at": self.scan_started_at,
            "scan_finished_at": self.scan_finished_at,
            "interval": self.interval,
            "safety_posture": dict(self.safety_posture),
            "chains": list(self.chains),
            "per_chain": {c: r.to_dict() for c, r in self.per_chain.items()},
            "candidates_seen": self.candidates_seen,
            "candidates_quoted": self.candidates_quoted,
            "candidates_liquidity_verified": self.candidates_liquidity_verified,
            "economically_valid": self.economically_valid,
            "positive_net_count": self.positive_net_count,
            "best_candidate": self.best_candidate,
            "last_error": {c: r.last_error for c, r in self.per_chain.items()},
            "evidence_ids": [eid for r in self.per_chain.values() for eid in r.evidence_ids],
            "operator_action_required": self.operator_action_required,
        }


def _candidate_is_fresh(cand: Dict[str, Any], head_block: Optional[int],
                        max_block_lag: Optional[int]) -> bool:
    """A quote is fresh when its scan block is within ``max_block_lag`` of the
    chain head captured at scan time. Missing block/head ⇒ fail-closed (stale)
    when a lag policy is set; when no policy is configured, freshness is not
    enforced here (the underlying gate already rejects failed/stale quotes)."""
    if max_block_lag is None:
        return True
    cb = cand.get("block")
    if head_block is None or cb is None:
        return False
    try:
        return (int(head_block) - int(cb)) <= int(max_block_lag)
    except (TypeError, ValueError):
        return False


class SixChainOpportunityRace:
    """Operator-controlled, read-only six-chain Opportunity Race orchestrator.

    Bounded-concurrency, per-chain-isolated: a slow/dead RPC or a raising leg on
    one chain can never stop the other five. Never truncates the six-chain
    universe. Never signs/broadcasts/executes.
    """

    def __init__(
        self,
        *,
        interval_s: int = 60,
        per_chain_timeout_s: float = 45.0,
        max_chain_concurrency: int = 6,
        pairs_cap: int = 10,
        max_block_lag: Optional[int] = None,
        history_limit: int = 20,
        chain_evaluator: Optional[ChainEvaluator] = None,
        base_evaluator: Optional[ChainEvaluator] = None,
        networks: Optional[List[str]] = None,
        persist: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self._interval = int(interval_s)
        self._per_chain_timeout = float(per_chain_timeout_s)
        self._max_conc = max(1, int(max_chain_concurrency))
        self._pairs_cap = int(pairs_cap)
        self._max_block_lag = max_block_lag
        self._history_limit = int(history_limit)
        self._chain_eval = chain_evaluator or _default_chain_evaluator
        self._base_eval = base_evaluator or _default_base_evaluator
        self._networks_override = networks
        self._persist = persist

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._scan_lock = asyncio.Lock()
        self._running = False
        self._last_result: Optional[RaceResult] = None
        self._last_scan_at: Optional[str] = None
        self._next_scan_at: Optional[str] = None
        self._history: List[Dict[str, Any]] = []
        self._scan_count = 0

    # ── universe ────────────────────────────────────────────────────────────
    def networks(self) -> List[str]:
        if self._networks_override is not None:
            return list(self._networks_override)
        from .multichain_readiness import supported_networks
        return list(supported_networks())

    # ── single scan (the race) ───────────────────────────────────────────────
    async def _evaluate_chain_isolated(self, chain: str,
                                       sem: asyncio.Semaphore) -> ChainRaceResult:
        """Evaluate one chain, fully isolated. Any timeout/exception is captured
        as this chain's status ONLY and never propagates to sibling chains."""
        evaluator = self._base_eval if (chain or "").lower() == "base" else self._chain_eval
        async with sem:
            try:
                res = await asyncio.wait_for(
                    evaluator(chain, self._pairs_cap),
                    timeout=self._per_chain_timeout)
            except asyncio.TimeoutError:
                return ChainRaceResult(chain=chain, status=STATUS_TIMEOUT,
                                       last_error="per_chain_timeout",
                                       reason="rpc_slow_or_unresponsive")
            except Exception as exc:  # noqa: BLE001 — isolate per-chain failure
                return ChainRaceResult(chain=chain, status=STATUS_ERROR,
                                       last_error=f"{type(exc).__name__}: {exc}",
                                       reason="chain_evaluator_raised")
        return self._normalize(chain, res or {})

    def _normalize(self, chain: str, res: Dict[str, Any]) -> ChainRaceResult:
        head = res.get("head") or {}
        head_block = head.get("block")
        skipped = res.get("skipped")
        rows = res.get("rows") or []
        cands = res.get("candidates") or []

        if skipped:
            return ChainRaceResult(
                chain=chain, status=STATUS_SKIPPED, head_block=head_block,
                last_error=head.get("error"), reason=skipped)

        quoted = sum(1 for r in rows if r.get("quotable"))
        liq = sum(1 for r in rows if r.get("liquidity_verified"))

        econ_valid = 0
        positive: List[Dict[str, Any]] = []
        evidence_ids: List[str] = []
        for c in cands:
            eid = c.get("evidence_id")
            if eid:
                evidence_ids.append(eid)
            stages = c.get("stages") or {}
            is_econ = bool(stages.get("ECONOMICALLY_VALID"))
            if is_econ:
                econ_valid += 1
            net = c.get("all_in_net_usd")
            fresh = _candidate_is_fresh(c, head_block, self._max_block_lag)
            if is_econ and net is not None and float(net) > 0 and fresh:
                positive.append(c)
            elif is_econ and net is not None and float(net) > 0 and not fresh:
                # Genuinely positive economics but a stale quote ⇒ NOT surfaced.
                c = dict(c)
                c["eliminated_at"] = "STALE_QUOTE"
                c["reason"] = "quote_block_older_than_max_lag"

        best_net = max((float(c["all_in_net_usd"]) for c in positive), default=None)
        return ChainRaceResult(
            chain=chain, status=STATUS_EVALUATED, head_block=head_block,
            candidates_seen=len(rows), candidates_quoted=quoted,
            candidates_liquidity_verified=liq, economically_valid=econ_valid,
            positive_net_count=len(positive), best_net_usd=best_net,
            reason=None, evidence_ids=evidence_ids, candidates=positive)

    @staticmethod
    def _select_best(per_chain: Dict[str, ChainRaceResult]) -> Optional[Dict[str, Any]]:
        """Deterministic best-candidate selection across all positive-NET
        candidates: highest true net, tie-broken by (chain, evidence_id)."""
        pool: List[Dict[str, Any]] = []
        for r in per_chain.values():
            pool.extend(r.candidates)
        if not pool:
            return None
        best = sorted(
            pool,
            key=lambda c: (-float(c.get("all_in_net_usd") or 0.0),
                           str(c.get("chain") or ""),
                           str(c.get("evidence_id") or "")),
        )[0]
        out = dict(best)
        out["operator_action_required"] = True
        return out

    async def scan_once(self) -> RaceResult:
        """Run ONE full six-chain read-only race. Chains run concurrently with
        bounded concurrency and per-chain isolation."""
        async with self._scan_lock:
            chains = self.networks()
            started = _now_iso()
            sem = asyncio.Semaphore(self._max_conc)
            # No implicit cap: evaluate EVERY chain in the universe.
            legs = await asyncio.gather(
                *(self._evaluate_chain_isolated(c, sem) for c in chains),
                return_exceptions=False)
            finished = _now_iso()

            per_chain: Dict[str, ChainRaceResult] = {leg.chain: leg for leg in legs}
            seen = sum(r.candidates_seen for r in per_chain.values())
            quoted = sum(r.candidates_quoted for r in per_chain.values())
            liq = sum(r.candidates_liquidity_verified for r in per_chain.values())
            econ = sum(r.economically_valid for r in per_chain.values())
            positive = sum(r.positive_net_count for r in per_chain.values())
            best = self._select_best(per_chain)

            result = RaceResult(
                race_id=f"race:{uuid.uuid4().hex[:12]}",
                scan_started_at=started, scan_finished_at=finished,
                interval=self._interval, chains=chains, per_chain=per_chain,
                candidates_seen=seen, candidates_quoted=quoted,
                candidates_liquidity_verified=liq, economically_valid=econ,
                positive_net_count=positive, best_candidate=best,
                operator_action_required=bool(positive > 0),
            )
            self._last_result = result
            self._last_scan_at = finished
            self._scan_count += 1
            payload = result.to_dict()
            self._history.append(payload)
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit:]
            if self._persist is not None:
                try:
                    await self._persist(payload)
                except Exception:  # noqa: BLE001 — persistence never blocks the race
                    pass
            return result

    # ── lifecycle ─────────────────────────────────────────────────────────────
    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.scan_once()
            except Exception:  # noqa: BLE001 — a scan error never kills the loop
                pass
            self._next_scan_at = _now_iso()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass

    async def start(self) -> Dict[str, Any]:
        if self._running:
            return self.status()
        self._stop_event = asyncio.Event()
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        return self.status()

    async def stop(self) -> Dict[str, Any]:
        self._stop_event.set()
        self._running = False
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self._per_chain_timeout + 5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            except Exception:  # noqa: BLE001
                pass
        self._task = None
        return self.status()

    def status(self) -> Dict[str, Any]:
        last = self._last_result.to_dict() if self._last_result else None
        per_chain_health = {}
        if self._last_result:
            per_chain_health = {c: {"status": r.status, "last_error": r.last_error,
                                    "reason": r.reason}
                                for c, r in self._last_result.per_chain.items()}
        return {
            "state": "RUNNING" if self._running else "STOPPED",
            "mode": "READ-ONLY",
            "safety_posture": dict(SAFETY_POSTURE),
            "chains": self.networks(),
            "chain_count": len(self.networks()),
            "interval": self._interval,
            "scan_count": self._scan_count,
            "last_scan": self._last_scan_at,
            "next_scan": self._next_scan_at,
            "per_chain_health": per_chain_health,
            "positive_net_count": (self._last_result.positive_net_count
                                   if self._last_result else 0),
            "best_candidate": (self._last_result.best_candidate
                               if self._last_result else None),
            "operator_action_required": (self._last_result.operator_action_required
                                         if self._last_result else False),
            "last_result": last,
        }

    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)


# Module-level singleton for the operator API (NOT autostarted).
_RACE_SINGLETON: Optional[SixChainOpportunityRace] = None


def get_opportunity_race() -> SixChainOpportunityRace:
    global _RACE_SINGLETON
    if _RACE_SINGLETON is None:
        import os
        interval = int(os.environ.get("ARBICORE_RACE_INTERVAL_S", "60") or "60")
        _RACE_SINGLETON = SixChainOpportunityRace(interval_s=interval)
    return _RACE_SINGLETON


__all__ = [
    "SAFETY_POSTURE", "SixChainOpportunityRace", "RaceResult", "ChainRaceResult",
    "get_opportunity_race", "STATUS_EVALUATED", "STATUS_SKIPPED",
    "STATUS_TIMEOUT", "STATUS_ERROR",
]
