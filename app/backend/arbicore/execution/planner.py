"""Wave 6B · Execution Planner + Dry-Run + Repository.

Planner:
    Takes an ``opportunity`` payload (compatible with canonical
    ``CanonicalOpportunity``: chain, borrow token/amount, hops[]) plus a
    ``flash_loan_provider`` selector and a ``signer_wallet_id`` (from
    Wave-6A wallet registry).  Produces a fully-specified
    ``ExecutionPlan`` — Borrow → Swap[+] → Repay → Profit.

Dry-run:
    Runs pure-Python economics over the plan (fees, gas estimate,
    slippage, net profit).  Never touches the chain.  Emits an
    ``economics`` block that hangs off the persisted plan and feeds
    the Wave-5 evidence signer.

Repo:
    Append-only ``db.execution_plans`` collection.  Rollback = insert a
    superseding plan (same pattern as evidence bundles).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .adapters import AdapterRegistry
from .dag import (
    ExecutionPlan, ExecutionStep, _now_iso, new_plan_id,
    plan_hash, validate_dag,
)
from .gas import GasOracleBackend, StaticGasOracle
from .mev import MevRouterRegistry
from .mode import ExecutionModeRepo, is_broadcast_allowed
from .simulation import SimulationRegistry, SimulatorBackend
from .slippage import SlippageEstimator


logger = logging.getLogger("arbicore.execution.planner")


def _compute_confidence(economics: Dict[str, Any], quote_route: Any) -> float:
    """Confidence score in [0.0, 1.0] combining four independent signals.

    Signals and weights (canonical for Phase 10.10.8):

    * ``quote_signal``     (weight 0.40) — 1.0 when every hop returned a
      live quote; 0.5 for partial; 0.0 for full break-even fallback.
    * ``margin_signal``    (weight 0.30) — how far above break-even the
      quoted output sits, normalized against a 1 % target margin.  A
      route quoted at exactly break-even scores 0.0; at +1 % → 1.0.
    * ``gas_ratio_signal`` (weight 0.20) — how much of gross profit gas
      would consume.  Below 20 % gas share → 1.0.  Above 100 % → 0.0.
    * ``slippage_signal``  (weight 0.10) — 1.0 when the slippage-adjusted
      minimum output still covers repayment, else 0.0.

    Kept intentionally simple: no ML, no calibration.  The isotonic
    calibrator worker (Wave 4) can post-process this into
    ``adaptive_weights`` scores without changing this formula.  Any
    autonomous decision engine reading ``economics.confidence_score``
    obtains a stable, explainable [0, 1] value.
    """
    # 1. Quote-availability signal
    if quote_route is None:
        quote_signal = 0.0
    else:
        status = getattr(quote_route, "status", "fallback:break_even")
        quote_signal = 1.0 if status == "ok" else 0.5 if status == "partial" else 0.0

    # 2. Margin signal — bounded to [0, 1] against a 1 % target
    effective  = int(economics.get("effective_out_wei") or 0)
    break_even = int(economics.get("min_break_even_wei") or 0)
    if break_even > 0 and effective > break_even:
        margin_bps = ((effective - break_even) * 10_000) / break_even
        # 100 bps = 1 % target margin → score 1.0
        margin_signal = min(1.0, margin_bps / 100.0)
    else:
        margin_signal = 0.0

    # 3. Gas-ratio signal — gas as a share of gross profit
    gross = economics.get("gross_profit_usd")
    gas   = economics.get("gas_estimate_usd")
    if gross is not None and gross > 0 and gas is not None and gas >= 0:
        ratio = min(1.0, float(gas) / float(gross))
        # ratio 0.0 → 1.0 (perfect); 0.2 → 1.0 (below threshold);
        # 0.2..1.0 → linear decay; ≥ 1.0 → 0.0
        if ratio <= 0.2:
            gas_ratio_signal = 1.0
        elif ratio >= 1.0:
            gas_ratio_signal = 0.0
        else:
            gas_ratio_signal = round(1.0 - ((ratio - 0.2) / 0.8), 4)
    else:
        gas_ratio_signal = 0.0

    # 4. Slippage-headroom signal
    slippage_covers = bool(economics.get("min_output_after_slippage_covers_repay"))
    slippage_signal = 1.0 if slippage_covers else 0.5 if "slippage" not in economics else 0.0

    score = (
        0.40 * quote_signal +
        0.30 * margin_signal +
        0.20 * gas_ratio_signal +
        0.10 * slippage_signal
    )
    return round(min(1.0, max(0.0, score)), 4)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class ExecutionPlanner:
    def __init__(self, registry: AdapterRegistry):
        self._registry = registry

    def build(self,
              *,
              strategy: str,
              chain: str,
              borrow_token: str,
              borrow_amount_wei: int,
              flash_loan_provider: str,
              swap_hops: List[Dict[str, Any]],
              signer_wallet_id: Optional[str] = None,
              opportunity_id: Optional[str] = None,
              borrow_amount_usd: Optional[float] = None,
              flash_fee_bps_override: Optional[int] = None,
              mode: str = "SHADOW") -> ExecutionPlan:
        """Compose a plan.  Raises ``ValueError`` on any malformed input.

        ``swap_hops`` is a list of dicts::

            [{"dex": "uniswap_v3", "token_in": "0x...", "token_out": "0x...",
              "amount_in_wei": 1_000, "min_amount_out_wei": 999,
              "fee_tier_bps": 5}, ...]
        """
        if not swap_hops:
            raise ValueError("swap_hops must contain at least one hop")

        fl = self._registry.flash(flash_loan_provider)
        if not fl.supports(chain):
            raise ValueError(
                f"flash-loan provider '{flash_loan_provider}' does not support chain '{chain}'"
            )

        provider_versions: Dict[str, str] = {flash_loan_provider: fl.version}
        dex_route: List[str] = []
        steps: List[ExecutionStep] = []

        # Step 0: BORROW
        callback_receiver = signer_wallet_id or "__signer_wallet__"
        borrow_dict = fl.borrow_step(
            chain=chain, asset=borrow_token, amount_wei=borrow_amount_wei,
            step_index=0, callback_receiver=callback_receiver,
        )
        steps.append(ExecutionStep(**borrow_dict))

        # Steps 1..N: SWAP hops
        last_index = 0
        for i, hop in enumerate(swap_hops, start=1):
            dex_name = hop.get("dex") or ""
            if not dex_name:
                raise ValueError(f"swap hop {i} missing 'dex'")
            dex_adapter = self._registry.dex(dex_name)
            if not dex_adapter.supports(chain):
                raise ValueError(
                    f"DEX '{dex_name}' does not support chain '{chain}'"
                )
            provider_versions[dex_name] = dex_adapter.version
            dex_route.append(dex_name)
            missing = [k for k in ("token_in", "token_out",
                                    "amount_in_wei", "min_amount_out_wei")
                       if k not in hop]
            if missing:
                raise ValueError(
                    f"swap hop {i} missing required field(s): "
                    f"{', '.join(missing)}"
                )
            swap_dict = dex_adapter.swap_step(
                chain=chain,
                token_in=hop["token_in"],
                token_out=hop["token_out"],
                amount_in_wei=int(hop["amount_in_wei"]),
                min_amount_out_wei=int(hop["min_amount_out_wei"]),
                step_index=i,
                depends_on=[last_index],
                fee_tier_bps=hop.get("fee_tier_bps"),
            )
            steps.append(ExecutionStep(**swap_dict))
            last_index = i

        # Step N+1: REPAY (depends on the last swap)
        repay_index = last_index + 1
        repay_dict = fl.repay_step(
            chain=chain, asset=borrow_token, amount_wei=borrow_amount_wei,
            fee_bps=flash_fee_bps_override, step_index=repay_index,
            depends_on=[last_index],
        )
        steps.append(ExecutionStep(**repay_dict))

        # Step N+2: PROFIT — reconciliation marker; contract-free.
        profit_index = repay_index + 1
        profit_step = ExecutionStep(
            step_index=profit_index,
            kind="profit",
            provider="reconciler",
            chain=chain,
            contract_address=None,
            function_signature=None,
            args=[{"expected_profit_token": borrow_token,
                   "signer_wallet_id": signer_wallet_id}],
            value_wei=0,
            depends_on=[repay_index],
            notes="Post-execution profit reconciliation (no on-chain call)",
        )
        steps.append(profit_step)

        # Validate the DAG shape.
        validate_dag(steps)

        # Assemble the plan.
        plan_dict = {
            "plan_id": new_plan_id(),
            "strategy": strategy,
            "mode": mode,
            "opportunity_id": opportunity_id,
            "chain": chain,
            "borrow_token": borrow_token,
            "borrow_amount_wei": int(borrow_amount_wei),
            "borrow_amount_usd": borrow_amount_usd,
            "flash_loan_provider": flash_loan_provider,
            "dex_route": dex_route,
            "signer_wallet_id": signer_wallet_id,
            "steps": [s.to_dict() for s in steps],
            "economics": {},  # populated post-dry-run
            "created_at": _now_iso(),
            "provider_versions": provider_versions,
        }
        # Hash *before* setting the field so it doesn't recurse.
        plan_dict["plan_hash"] = plan_hash(plan_dict)

        return ExecutionPlan(
            plan_id=plan_dict["plan_id"],
            strategy=strategy,
            mode=mode,
            opportunity_id=opportunity_id,
            chain=chain,
            borrow_token=borrow_token,
            borrow_amount_wei=int(borrow_amount_wei),
            borrow_amount_usd=borrow_amount_usd,
            flash_loan_provider=flash_loan_provider,
            dex_route=dex_route,
            signer_wallet_id=signer_wallet_id,
            steps=steps,
            economics={},
            created_at=plan_dict["created_at"],
            plan_hash=plan_dict["plan_hash"],
            provider_versions=provider_versions,
        )


# ---------------------------------------------------------------------------
# Dry-Run Engine
# ---------------------------------------------------------------------------

class DryRunEngine:
    """Pure-Python plan evaluation.  Never touches the chain.

    Wave 6C refinement: the engine now consumes an optional
    ``GasOracleBackend`` (live gas estimate), ``SlippageEstimator``
    (deterministic slippage), and ``SimulationRegistry`` (on-chain
    ``eth_call`` simulation).  All three are strictly additive — when
    absent the engine falls back to the Wave-6B constant-gas heuristic
    and produces exactly the same output as before (backward
    compatible)."""

    def __init__(self, registry: AdapterRegistry,
                 default_gas_estimate_usd: float = 5.0,
                 *,
                 gas_oracle: Optional[GasOracleBackend] = None,
                 slippage: Optional[SlippageEstimator] = None,
                 simulator_registry: Optional[SimulationRegistry] = None,
                 mev_registry: Optional[MevRouterRegistry] = None,
                 quoter: Optional[Any] = None):
        self._registry = registry
        self._default_gas = float(default_gas_estimate_usd)
        self._gas_oracle = gas_oracle
        self._slippage = slippage
        self._simulators = simulator_registry
        self._mev = mev_registry
        # Phase 10.10.8 — canonical live-quote engine.  When provided,
        # ``evaluate_live()`` becomes the production entrypoint.  The
        # legacy sync ``evaluate()`` remains for backward-compatibility.
        self._quoter = quoter

    def evaluate(self, plan: ExecutionPlan, *,
                 quote_effective_out_wei: Optional[int] = None,
                 gas_estimate_usd: Optional[float] = None) -> Dict[str, Any]:
        """Attach an ``economics`` block to ``plan``.

        ``quote_effective_out_wei`` — the operator (or upstream quoter)
        supplies the actually-quoted output amount at the end of the
        swap sequence.  Absent → we estimate a break-even output.
        """
        fl = self._registry.flash(plan.flash_loan_provider)
        premium_bps = fl.fee_bps_default
        # Uniswap V3 tier override is carried in the repay step args.
        repay_step = next((s for s in plan.steps if s.kind == "repay"), None)
        if repay_step and len(repay_step.args) >= 3:
            premium_wei = int(repay_step.args[2] or 0)
            if plan.borrow_amount_wei > 0:
                premium_bps = int(
                    (premium_wei * 10_000) / plan.borrow_amount_wei
                )
        premium_wei = (plan.borrow_amount_wei * premium_bps) // 10_000

        # Minimum output required to break even = borrow + premium.
        min_break_even_wei = plan.borrow_amount_wei + premium_wei

        # Effective quoted output — defaults to break-even for planning stubs.
        effective_out_wei = int(quote_effective_out_wei
                                if quote_effective_out_wei is not None
                                else min_break_even_wei)
        gross_profit_wei = effective_out_wei - min_break_even_wei

        # USD conversion — only when the caller passed borrow_amount_usd.
        gross_profit_usd = None
        if plan.borrow_amount_usd is not None and plan.borrow_amount_wei > 0:
            per_wei_usd = plan.borrow_amount_usd / plan.borrow_amount_wei
            gross_profit_usd = round(gross_profit_wei * per_wei_usd, 6)

        gas_usd = float(gas_estimate_usd if gas_estimate_usd is not None else self._default_gas)
        net_profit_usd = None if gross_profit_usd is None else round(
            gross_profit_usd - gas_usd, 6
        )

        economics = {
            "flash_fee_bps": premium_bps,
            "flash_fee_wei": premium_wei,
            "min_break_even_wei": min_break_even_wei,
            "effective_out_wei": effective_out_wei,
            "gross_profit_wei": gross_profit_wei,
            "gross_profit_usd": gross_profit_usd,
            "gas_estimate_usd": gas_usd,
            "net_profit_usd": net_profit_usd,
            "profitable": bool(net_profit_usd is not None and net_profit_usd > 0),
            # Phase 10.10.8 · quote + gas source annotations.  The sync
            # ``evaluate()`` path is the deterministic / backward-compat
            # flow; ``evaluate_live()`` overrides these with live values.
            "quote_source": ("operator_supplied"
                              if quote_effective_out_wei is not None
                              else "fallback:break_even"),
            "gas_source":   ("operator_supplied"
                              if gas_estimate_usd is not None
                              else "default_static"),
            "engine_version": "dry_run@1",
            "evaluated_at": _now_iso(),
        }

        # ------------------------------------------------------------------
        # Wave 6C additive slippage estimate (deterministic; no chain contact).
        # ------------------------------------------------------------------
        if self._slippage is not None:
            hops = sum(1 for s in plan.steps if s.kind == "swap")
            slip = self._slippage.estimate(
                quoted_output_wei=int(effective_out_wei),
                hops=max(1, hops),
            )
            economics["slippage"] = slip.to_dict()
            economics["slippage_haircut_wei"] = slip.slippage_haircut_wei
            economics["min_output_after_slippage_wei"] = slip.min_output_wei
            economics["min_output_after_slippage_covers_repay"] = bool(
                slip.min_output_wei >= min_break_even_wei
            )

        plan.economics = economics
        return economics

    # ------------------------------------------------------------------
    # Wave 6C — async helpers (optional; called by the /simulate endpoint)
    # ------------------------------------------------------------------

    async def estimate_gas(self, plan: ExecutionPlan) -> Optional[Dict[str, Any]]:
        if self._gas_oracle is None:
            return None
        step_kinds = [s.kind for s in plan.steps]
        est = await self._gas_oracle.estimate(chain=plan.chain, step_kinds=step_kinds)
        return est.to_dict()

    # ------------------------------------------------------------------
    # Phase 10.10.8 · Canonical live-profitability entrypoint
    # ------------------------------------------------------------------
    async def evaluate_live(
        self, plan: ExecutionPlan, *,
        rpc_url: Optional[str] = None,
        force_quote: bool = False,
    ) -> Dict[str, Any]:
        """Live production profitability evaluation.

        Pipeline (all steps happen before ``evaluate()`` is called):

        1. **Live route quote** — via the injected ``QuoterRegistry``.
           Each swap hop is asked for its actual on-chain output.  The
           final hop's ``amount_out_wei`` becomes ``effective_out_wei``.

        2. **Live gas** — via the injected ``GasOracleBackend``.  Its
           ``total_cost_usd`` becomes the deducted ``gas_estimate_usd``.

        3. **Sync ``evaluate()``** is invoked with both live numbers so
           the resulting ``economics`` block reflects real market
           conditions instead of break-even / $5 defaults.

        4. **Confidence score** is computed from four normalized signals
           (profit margin, gas ratio, slippage headroom, quote status)
           and attached to ``economics.confidence_score``.

        Fallback policy: if the quoter is unavailable *or* returns
        ``fallback:*``, we still populate a receipt but flag
        ``economics.quote_source`` accordingly.  The caller — typically
        ``CertificationPipeline`` — turns this into a WAIT verdict.
        """
        # -- 1. Live quote ------------------------------------------------
        quote_route = None
        effective_out_wei: Optional[int] = None
        if self._quoter is not None:
            try:
                quote_route = await self._quoter.quote_plan(
                    plan.to_dict(), rpc_url=rpc_url,
                )
                if quote_route.status in ("ok", "partial"):
                    effective_out_wei = int(quote_route.final_amount_out_wei)
            except Exception as exc:  # noqa: BLE001
                logger.warning("live quote failed: %s", exc)
                quote_route = None
        if effective_out_wei is None and force_quote:
            raise RuntimeError("live quote required but unavailable")

        # -- 2. Live gas --------------------------------------------------
        gas_estimate_usd: Optional[float] = None
        gas_dict: Optional[Dict[str, Any]] = None
        if self._gas_oracle is not None:
            try:
                est = await self._gas_oracle.estimate(
                    chain=plan.chain,
                    step_kinds=[s.kind for s in plan.steps],
                )
                gas_dict = est.to_dict()
                gas_estimate_usd = est.total_cost_usd
            except Exception as exc:  # noqa: BLE001
                logger.warning("live gas failed: %s", exc)

        # -- 3. Delegate to sync evaluate ---------------------------------
        eco = self.evaluate(
            plan,
            quote_effective_out_wei=effective_out_wei,
            gas_estimate_usd=gas_estimate_usd,
        )

        # -- 4. Overwrite provenance + attach live artifacts --------------
        if quote_route is not None:
            eco["quote_source"] = (
                "live" if quote_route.status == "ok"
                else "partial_live" if quote_route.status == "partial"
                else "fallback:break_even"
            )
            eco["quote_route"] = quote_route.to_dict()
        if gas_dict is not None:
            eco["gas_source"] = "live_" + gas_dict.get("method", "unknown")
            eco["gas_detail"] = gas_dict

        # Confidence score in [0, 1] — additive to existing signals.
        eco["confidence_score"] = _compute_confidence(eco, quote_route)
        eco["engine_version"] = "dry_run@live-1"
        plan.economics = eco
        return eco

    async def simulate(self, plan: ExecutionPlan, *,
                       simulator: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self._simulators is None:
            return None
        result = await self._simulators.simulate(plan.to_dict(), simulator=simulator)
        return result.to_dict()

    async def route_mev(self, plan: ExecutionPlan, *,
                        router: Optional[str] = None,
                        protected: bool = True) -> Optional[Dict[str, Any]]:
        if self._mev is None:
            return None
        decision = await self._mev.route(router=router, chain=plan.chain,
                                          protected=protected)
        return decision.to_dict()


# ---------------------------------------------------------------------------
# Repo
# ---------------------------------------------------------------------------

class ExecutionPlansRepo:
    def __init__(self, db, collection: str = "execution_plans"):
        self._db = db
        self._coll = db[collection]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._coll.create_index("plan_id", unique=True)
        await self._coll.create_index([("strategy", 1), ("created_at", -1)])
        await self._coll.create_index("plan_hash")
        self._indexes_ready = True

    async def insert(self, plan: ExecutionPlan) -> Dict[str, Any]:
        doc = plan.to_dict()
        await self._coll.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return await self._coll.find_one({"plan_id": plan_id}, {"_id": 0})

    async def list_recent(self, strategy: Optional[str] = None,
                          chain: Optional[str] = None,
                          limit: int = 20) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if strategy:
            q["strategy"] = strategy
        if chain:
            q["chain"] = chain
        cur = self._coll.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
        return await cur.to_list(limit)


# ---------------------------------------------------------------------------
# Broadcast-guard for callers about to hit any signer path
# ---------------------------------------------------------------------------

async def assert_broadcast_allowed(mode_repo: ExecutionModeRepo,
                                   strategy: str) -> None:
    """Raise ``PermissionError`` if the strategy's current mode does not
    permit broadcasts.  Wave 6B never triggers this — it exists so the
    signer path in Wave 6D can consult a single authoritative gate."""
    row = await mode_repo.get(strategy)
    current = (row or {}).get("mode") or "OBSERVE"
    if not is_broadcast_allowed(current):
        raise PermissionError(
            f"broadcast forbidden — strategy '{strategy}' is in mode '{current}' "
            f"(must be LIMITED_LIVE or FULL_LIVE)"
        )
