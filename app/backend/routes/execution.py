"""Phase E2 — Execution Framework endpoints (SIMULATED / DISABLED BY DEFAULT).

Authenticated config / venue-registry / classification / opportunity / fund-
tracking endpoints. The cycle endpoints operate SIMULATED cycles only (dry-run):
no exchange API calls, no wallet transactions, no fund movement.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from services.auth import require_auth
from services.execution import (arbitrage_cycles, arbitrage_intel, audit, bdag_transfers, buy_price_audit,
                                certification,
                                certification_evidence, certification_review,
                                classification, config,
                                cycle_model,
                                cycle_timing,
                                evidence_accuracy, evidence_report,
                                exchange_intelligence, executable_quote, fee_provenance,
                                fresh_cycle_analytics, fresh_cycle_watch,
                                operator_console,
                                opportunity_gate,
                                permanent_ledger, production_workflow, quote_capture, quote_resolver,
                                safety_interlock,
                                fees as exec_fees, funding, integration_prep,
                                ledger, manual_engine, opportunity, portal_diag,
                                price_verification,
                                recovery_proof, venue_registry,
                                wallet_observer)
from services.execution.opportunity_gate import opportunity_monitor
from services.execution.fund_tracker import fund_tracker
from services.execution.integration_monitor import integration_monitor
from services.execution.shadow import shadow_runner
from services.execution.campaign import shadow_campaign
from services.execution import drift_runner as drift_runner_mod
from services.execution.drift_runner import drift_runner
from services import db

router = APIRouter(prefix="/api/execution", tags=["execution"],
                   dependencies=[Depends(require_auth)])


# ---------------- status ----------------

@router.get("/status")
async def execution_status():
    cfg = await config.get_config()
    ft = await fund_tracker.status()
    shadow = await shadow_runner.status()
    return {
        "phase": "E4 — Real API Integration Prep (read-only) on the E2/E3 framework",
        "execution_enabled": cfg["execution_enabled"],
        "wallet_enabled": cfg["wallet_enabled"],
        "hard_freeze": cfg["hard_freeze"],
        "shadow_enabled": cfg["shadow_enabled"],
        "mode": "SHADOW (live data, non-executing)" if cfg["shadow_enabled"] else "SIMULATED / DRY-RUN",
        "fund_tracker": ft,
        "shadow": shadow,
        "note": "No fund-moving code is active. Shadow runs record would-do decisions off live data only.",
    }


@router.get("/shadow/status")
async def shadow_status():
    return await shadow_runner.status()


# ---------------- certification config + kill switches ----------------

@router.get("/config")
async def get_config():
    return await config.get_config()


class ConfigPatch(BaseModel):
    execution_enabled: Optional[bool] = None
    wallet_enabled: Optional[bool] = None
    hard_freeze: Optional[bool] = None
    shadow_enabled: Optional[bool] = None
    default_funding_asset: Optional[str] = None
    withdrawal_whitelist: Optional[list] = None
    limits: Optional[dict] = None


@router.patch("/config")
async def patch_config(body: ConfigPatch):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return await config.update_config(patch)


# ---------------- venue registry ----------------

@router.get("/venues")
async def list_venues():
    return {"venues": await venue_registry.list_venues(), "roles": venue_registry.ROLES}


class VenueRolePatch(BaseModel):
    role: str


@router.patch("/venues/{exchange}")
async def set_venue_role(exchange: str, body: VenueRolePatch):
    try:
        return await venue_registry.set_role(exchange.lower(), body.role.lower())
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------- funding asset flexibility ----------------

@router.get("/funding")
async def funding_calc(size_usd: float = 25.0):
    if size_usd <= 0:
        raise HTTPException(400, "size_usd must be positive")
    return funding.funding_breakdown(size_usd)


# ---------------- Exchange Intelligence Registry & Ranking (READ-ONLY) ----------------
# NOTE: static sub-paths MUST be declared before the /{exchange} catch-all.

@router.get("/exchanges")
async def exchange_registry():
    return await exchange_intelligence.registry()


@router.get("/exchanges/assessment")
async def exchange_assessment():
    return await exchange_intelligence.assessment()


class ExchangePatch(BaseModel):
    operator_verified: Optional[bool] = None
    status_override: Optional[str] = None


@router.patch("/exchanges/{exchange}")
async def patch_exchange(exchange: str, body: ExchangePatch):
    try:
        res = await exchange_intelligence.update_one(
            exchange, body.operator_verified, body.status_override)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if res is None:
        raise HTTPException(404, "exchange not found")
    return res


@router.get("/exchanges/{exchange}")
async def get_exchange(exchange: str):
    res = await exchange_intelligence.get_one(exchange)
    if res is None:
        raise HTTPException(404, "exchange not found")
    return res


# ---------------- E4.7 opportunity gate/windows/status (static paths BEFORE the /{route_id} catch-all) ----------------

@router.get("/opportunity/gate")
async def opportunity_gate_eval(route_id: Optional[str] = None):
    if not route_id:
        route = await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0, "id": 1})
        route_id = (route or {}).get("id")
    return await opportunity_gate.evaluate(route_id)


@router.get("/opportunity/windows")
async def opportunity_windows(limit: int = 100):
    return await opportunity_monitor.history(limit)


@router.get("/opportunity/status")
async def opportunity_status():
    return await opportunity_monitor.status()


# ---------------- portal vs exchange opportunity widget ----------------

@router.get("/opportunity/{route_id}")
async def opportunity_widget(route_id: str):
    return await opportunity.portal_vs_exchange(route_id)


# ---------------- route classification + automation coverage ----------------

@router.get("/classification/{route_id}")
async def route_classification(route_id: str):
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        raise HTTPException(404, "route not found")
    return await classification.classify_route(route)


# ---------------- manual opportunity engine ----------------

@router.get("/manual-opportunities/{route_id}")
async def manual_opportunities(route_id: str, min_net: Optional[float] = None):
    return await manual_engine.opportunities(route_id, min_net)


# ---------------- fund tracking / recovery (SIMULATED cycles) ----------------

@router.get("/cycles")
async def list_cycles(limit: int = 100, state: Optional[str] = None):
    return {"cycles": await fund_tracker.list_cycles(limit, state)}


class CycleCreate(BaseModel):
    route_id: str
    size_usd: float = 25.0
    funding_asset: Optional[str] = None


@router.post("/cycles")
async def create_cycle(body: CycleCreate):
    try:
        return await fund_tracker.create_cycle(body.route_id, body.size_usd, body.funding_asset)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/cycles/{cycle_id}")
async def get_cycle(cycle_id: str):
    cycle = await fund_tracker.get_cycle(cycle_id)
    if not cycle:
        raise HTTPException(404, "cycle not found")
    return cycle


@router.post("/cycles/{cycle_id}/advance")
async def advance_cycle(cycle_id: str):
    try:
        return await fund_tracker.advance(cycle_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/cycles/{cycle_id}/abort")
async def abort_cycle(cycle_id: str):
    try:
        return await fund_tracker.abort(cycle_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/cycles/{cycle_id}/manual-review")
async def manual_review_cycle(cycle_id: str):
    try:
        return await fund_tracker.force_manual_review(cycle_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/cycles/{cycle_id}/audit")
async def cycle_audit(cycle_id: str):
    return {"cycle_id": cycle_id, "trail": await audit.trail(cycle_id)}


@router.get("/cycles/{cycle_id}/timeline")
async def cycle_timeline(cycle_id: str):
    tl = await fund_tracker.timeline(cycle_id)
    if not tl:
        raise HTTPException(404, "cycle not found")
    return tl


# ---------------- E4 — real API integration preparation (read-only) ----------------

@router.get("/integration/status")
async def integration_status():
    return await integration_prep.integration_status()


@router.get("/integration/monitor")
async def integration_monitor_status():
    return await integration_monitor.status()


@router.get("/integration/readiness/{exchange}")
async def integration_readiness(exchange: str):
    return await integration_prep.readiness(exchange)


@router.post("/integration/verify/{key_id}")
async def integration_verify(key_id: str):
    res = await integration_prep.verify_key(key_id)
    if res is None:
        raise HTTPException(404, "key not found")
    return res


# ---------------- E4 — shadow certification report ----------------

@router.get("/certification/report")
async def certification_report():
    return await certification.report()


# ---------------- E4.5 — shadow certification campaign (hands-off, NON-EXECUTING) ----------------

@router.get("/campaign/status")
async def campaign_status():
    return await shadow_campaign.status()


@router.get("/campaign/history")
async def campaign_history(limit: int = 20):
    return {"campaigns": await shadow_campaign.history(limit)}


class CampaignStart(BaseModel):
    target_completed: Optional[int] = None
    thresholds: Optional[dict] = None
    cycle_size_usd: Optional[float] = None


@router.post("/campaign/start")
async def campaign_start(body: CampaignStart):
    try:
        return await shadow_campaign.start(body.target_completed, body.thresholds, body.cycle_size_usd)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/campaign/stop")
async def campaign_stop():
    try:
        return await shadow_campaign.stop()
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------- E4.5 — comprehensive Certification Review package (READ-ONLY) ----------------

@router.get("/certification/review")
async def certification_review_pkg(regenerate: bool = False, campaign_id: Optional[str] = None):
    if campaign_id:
        res = await certification_review.review_for_campaign(campaign_id, regenerate)
        if res is None:
            raise HTTPException(404, "campaign not found")
        return res
    return await certification_review.latest_review(regenerate)


@router.get("/certification/review/download")
async def certification_review_download(format: str = "md", regenerate: bool = False,
                                        campaign_id: Optional[str] = None):
    if campaign_id:
        pkg = await certification_review.review_for_campaign(campaign_id, regenerate)
        if pkg is None:
            raise HTTPException(404, "campaign not found")
    else:
        pkg = await certification_review.latest_review(regenerate)
    stamp = ((pkg.get("campaign") or {}).get("id") or "none")[:8]
    if (format or "md").lower() == "json":
        import json
        return Response(content=json.dumps(pkg, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f"attachment; filename=certification_review_{stamp}.json"})
    return Response(content=certification_review.to_markdown(pkg), media_type="text/markdown",
                    headers={"Content-Disposition": f"attachment; filename=certification_review_{stamp}.md"})


@router.get("/certification/evidence")
async def certification_evidence_pkg(campaign_id: Optional[str] = None):
    return await certification_evidence.build(campaign_id)


@router.get("/certification/evidence/download")
async def certification_evidence_download(format: str = "md", campaign_id: Optional[str] = None):
    pkg = await certification_evidence.build(campaign_id)
    stamp = (pkg.get("campaign_id") or "none")[:8]
    if (format or "md").lower() == "json":
        import json
        return Response(content=json.dumps(pkg, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f"attachment; filename=certification_evidence_{stamp}.json"})
    return Response(content=certification_evidence.to_markdown(pkg), media_type="text/markdown",
                    headers={"Content-Disposition": f"attachment; filename=certification_evidence_{stamp}.md"})


# ---------------- Price Verification & Calculation Transparency (READ-ONLY) ----------------

@router.get("/price-verification")
async def price_verification_pkg(route_id: Optional[str] = None):
    return await price_verification.build(route_id)



# ---------------- E4.6 Part A — BDAG Arbitrage Intelligence Engine (READ-ONLY) ----------------

@router.get("/intel/{route_id}")
async def arbitrage_intelligence(route_id: str, size_usd: Optional[float] = None,
                                 utilization_pct: int = 75):
    return await arbitrage_intel.analyze(route_id, size_usd, utilization_pct)


@router.get("/portal/diagnostic")
async def portal_diagnostic():
    return await portal_diag.report()


# ---------------- Production Workflow Blueprint + Next-Cycle Readiness (READ-ONLY) ----------------

@router.get("/workflow/blueprint")
async def workflow_blueprint(route_id: Optional[str] = None):
    return await production_workflow.blueprint(route_id)


@router.get("/workflow/readiness")
async def workflow_readiness(route_id: Optional[str] = None):
    return await production_workflow.next_cycle_readiness(route_id)


# ---------------- E4.7 Live Opportunity Gate + Safety Interlock (READ-ONLY) ----------------

@router.get("/interlock")
async def safety_interlock_eval(route_id: Optional[str] = None):
    return await safety_interlock.evaluate(route_id)


# ---------------- Permanent Institutional Ledger (immutable, READ-ONLY) ----------------

@router.get("/ledger/permanent")
async def permanent_ledger_view(limit: int = 5000):
    return await permanent_ledger.build(limit)


@router.post("/ledger/permanent/backfill")
async def permanent_ledger_backfill():
    return await permanent_ledger.backfill()


@router.get("/ledger/permanent/export")
async def permanent_ledger_export(format: str = "xlsx", limit: int = 5000):
    fmt = (format or "xlsx").lower()
    if fmt == "csv":
        csv_str = await permanent_ledger.export_csv(limit)
        return Response(content=csv_str, media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=production_ledger.csv"})
    if fmt == "json":
        import json
        led = await permanent_ledger.build(limit)
        return Response(content=json.dumps(led, indent=2), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=production_ledger.json"})
    data = await permanent_ledger.export_xlsx(limit)
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=production_ledger.xlsx"})


# ---------------- E4.6 — verified fee model (editable overrides) ----------------

@router.get("/fees")
async def get_fees():
    return {"fees": await exec_fees.get_fees(), "provenance": exec_fees.FEE_PROVENANCE,
            "defaults": exec_fees.FEE_DEFAULTS}


@router.patch("/fees")
async def patch_fees(body: dict):
    return await exec_fees.update_fees(body)


# ---------------- E4.6 Part B — production ledger & profit accounting (READ-ONLY) ----------------

@router.get("/ledger")
async def production_ledger(limit: int = 1000):
    return await ledger.build_ledger(limit)


@router.get("/ledger/export")
async def ledger_export(format: str = "csv", limit: int = 1000):
    if (format or "csv").lower() == "json":
        import json
        led = await ledger.build_ledger(limit)
        return Response(content=json.dumps(led, indent=2), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=production_ledger.json"})
    csv_str = await ledger.export_csv(limit)
    return Response(content=csv_str, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=production_ledger.csv"})


# ---------------- E4.6 Part C — recovery proof campaign (isolated, NON-EXECUTING) ----------------

@router.post("/recovery-proof/run")
async def recovery_proof_run():
    return await recovery_proof.run()


@router.get("/recovery-proof/status")
async def recovery_proof_status():
    latest = await recovery_proof.latest()
    return {"latest": latest, "note": "Isolated recovery_proof cycles, excluded from certification."}


@router.get("/recovery-proof/history")
async def recovery_proof_history(limit: int = 20):
    return {"proofs": await recovery_proof.history(limit)}


# ---------------- Fee Provenance Report (READ-ONLY) ----------------

@router.get("/fee-provenance")
async def fee_provenance_report():
    return await fee_provenance.build()


@router.get("/fee-provenance/download")
async def fee_provenance_download(format: str = "md"):
    pkg = await fee_provenance.build()
    if (format or "md").lower() == "json":
        import json
        return Response(content=json.dumps(pkg, indent=2), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=fee_provenance.json"})
    md = evidence_report.fee_provenance_md(pkg)
    return Response(content=md, media_type="text/markdown",
                    headers={"Content-Disposition": "attachment; filename=fee_provenance.md"})


# ---------------- Fresh-Cycle Opportunity Analytics (READ-ONLY) ----------------

@router.get("/fresh-cycle/analytics")
async def fresh_cycle_analytics_pkg(days: int = 30):
    return await fresh_cycle_analytics.analytics(_clamp_days(days))


@router.get("/fresh-cycle/stats")
async def fresh_cycle_stats(days: int = 30):
    return await fresh_cycle_analytics.stats(_clamp_days(days))


@router.get("/fresh-cycle/survivability")
async def fresh_cycle_survivability(days: int = 30, limit: int = 200):
    return await fresh_cycle_analytics.survivability(_clamp_days(days),
                                                     max(1, min(limit, 1000)))


@router.get("/fresh-cycle/evidence")
async def fresh_cycle_evidence(days: int = 30):
    return await fresh_cycle_analytics.evidence(_clamp_days(days))


@router.get("/fresh-cycle/observation-window")
async def fresh_cycle_observation_window():
    return await fresh_cycle_analytics.observation_window()


@router.get("/fresh-cycle/download")
async def fresh_cycle_download(format: str = "md", days: int = 30):
    days = _clamp_days(days)
    pkg = await fresh_cycle_analytics.analytics(days)
    if (format or "md").lower() == "json":
        import json
        return Response(content=json.dumps(pkg, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f"attachment; filename=fresh_cycle_{days}d.json"})
    md = evidence_report.fresh_cycle_md(pkg, days)
    return Response(content=md, media_type="text/markdown",
                    headers={"Content-Disposition": f"attachment; filename=fresh_cycle_{days}d.md"})


# ---------------- Fresh-Cycle Watch (Telegram framework, DORMANT) ----------------

@router.get("/fresh-cycle/watch")
async def fresh_cycle_watch_status():
    return await fresh_cycle_watch.status()


# ---------------- Final Evidence Report (bundle, READ-ONLY) ----------------

@router.get("/evidence-report")
async def evidence_report_pkg(days: int = 30):
    return await evidence_report.build(_clamp_days(days))


@router.get("/evidence-report/download")
async def evidence_report_download(format: str = "md", days: int = 30):
    days = _clamp_days(days)
    pkg = await evidence_report.build(days)
    if (format or "md").lower() == "json":
        import json
        return Response(content=json.dumps(pkg, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f"attachment; filename=evidence_report_{days}d.json"})
    md = evidence_report.to_markdown(pkg)
    return Response(content=md, media_type="text/markdown",
                    headers={"Content-Disposition": f"attachment; filename=evidence_report_{days}d.md"})


def _clamp_days(days):
    try:
        return max(1, min(int(days), 90))
    except (TypeError, ValueError):
        return 30


# ---------------- BDAG Transfer Evidence (measured-from-real-transactions) ----------------

class BdagTransferIn(BaseModel):
    amount_bdag: float
    fee_bdag: float
    tx_hash: Optional[str] = None
    source: Optional[str] = "operator_attested"
    note: Optional[str] = None


@router.get("/bdag-transfers")
async def bdag_transfers_status():
    return await bdag_transfers.status()


@router.get("/bdag-transfers/list")
async def bdag_transfers_list(limit: int = 50):
    return {"transfers": await bdag_transfers.list_transfers(limit)}


@router.get("/bdag-transfers/rolling-average")
async def bdag_transfers_rolling_average():
    return await bdag_transfers.rolling_average()


@router.post("/bdag-transfers")
async def bdag_transfers_record(body: BdagTransferIn):
    if body.amount_bdag <= 0 or body.fee_bdag < 0:
        raise HTTPException(status_code=400, detail="amount_bdag must be > 0 and fee_bdag must be ≥ 0")
    return await bdag_transfers.record(
        amount_bdag=body.amount_bdag, fee_bdag=body.fee_bdag,
        tx_hash=body.tx_hash, source=body.source or "operator_attested", note=body.note)


# ---------------- Real Arbitrage Cycle Model ----------------

@router.get("/cycle-model")
async def cycle_model_pkg(route_id: Optional[str] = None):
    return await cycle_model.build(route_id)


# ---------------- Evidence Accuracy Report ----------------

@router.get("/evidence-accuracy")
async def evidence_accuracy_report():
    return await evidence_accuracy.build()


# ---------------- BlockDAG Buy-Price Source Audit (READ-ONLY) ----------------

class EmpiricalQuoteIn(BaseModel):
    investment_usd: float
    bdag_received: float
    pay_token: Optional[str] = "USDT"
    reported_ui_price: Optional[float] = None
    note: Optional[str] = None


@router.get("/buy-price-audit")
async def buy_price_audit_report():
    return await buy_price_audit.build()


@router.get("/buy-price-audit/empirical")
async def buy_price_audit_empirical_list(limit: int = 20):
    return {"quotes": await buy_price_audit.list_empirical(limit)}


@router.post("/buy-price-audit/empirical")
async def buy_price_audit_empirical_record(body: EmpiricalQuoteIn):
    try:
        return await buy_price_audit.record_empirical(
            investment_usd=body.investment_usd, bdag_received=body.bdag_received,
            pay_token=body.pay_token or "USDT", note=body.note,
            reported_ui_price=body.reported_ui_price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



# ---------------- Executable Quote Resolver (READ-ONLY) ----------------

@router.get("/executable-quote")
async def executable_quote_resolve():
    return await executable_quote.resolve()



# ---------------- Pre-Trade Quote Resolver (READ-ONLY, NON-COMMITTING) ----------------

class QuoteIn(BaseModel):
    investment_usd: float
    pay_token: Optional[str] = "USDT"


@router.post("/quote-resolver")
async def quote_resolver_quote(body: QuoteIn):
    if body.investment_usd is None or body.investment_usd <= 0:
        raise HTTPException(status_code=400, detail="investment_usd must be > 0")
    return await quote_resolver.quote(body.investment_usd, body.pay_token or "USDT")


@router.get("/quote-resolver/strategies")
async def quote_resolver_strategies():
    return await quote_resolver.strategies()



# ---------------- Executable Quote Capture (READ-ONLY) ----------------

class QuoteCaptureIn(BaseModel):
    input_amount: float
    bdag_allocated: float
    input_token: Optional[str] = "USDT"
    source: Optional[str] = "manual"
    raw: Optional[dict] = None
    note: Optional[str] = None


@router.get("/quote-capture")
async def quote_capture_status():
    return await quote_capture.status()


@router.get("/quote-capture/list")
async def quote_capture_list(limit: int = 50):
    return {"captures": await quote_capture.list_captures(limit)}


@router.post("/quote-capture")
async def quote_capture_record(body: QuoteCaptureIn):
    try:
        return await quote_capture.record(
            input_amount=body.input_amount,
            bdag_allocated=body.bdag_allocated,
            input_token=body.input_token or "USDT",
            source=body.source or "manual",
            raw=body.raw, note=body.note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



# ---------------- Arbitrage Cycle Evidence (READ-ONLY tracking) ----------------

class CycleCreateIn(BaseModel):
    input_amount: float
    quote_price: float
    bdag_expected: float
    best_bid: Optional[float] = None
    expected_roi_pct: Optional[float] = None
    note: Optional[str] = None


class CycleTransitionIn(BaseModel):
    to_state: str
    fields: Optional[dict] = None


@router.get("/arb-cycles")
async def cycles_status():
    return await arbitrage_cycles.status()


@router.get("/arb-cycles/{cycle_id}")
async def cycles_get(cycle_id: str):
    d = await arbitrage_cycles.get(cycle_id)
    if not d:
        raise HTTPException(status_code=404, detail="cycle not found")
    return d


@router.post("/arb-cycles")
async def cycles_create(body: CycleCreateIn):
    return await arbitrage_cycles.create(
        input_amount=body.input_amount, quote_price=body.quote_price,
        bdag_expected=body.bdag_expected, best_bid=body.best_bid,
        expected_roi_pct=body.expected_roi_pct, note=body.note)


@router.post("/arb-cycles/{cycle_id}/transition")
async def cycles_transition(cycle_id: str, body: CycleTransitionIn):
    try:
        return await arbitrage_cycles.transition(cycle_id, body.to_state, **(body.fields or {}))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/arb-cycles/{cycle_id}/abort")
async def cycles_abort(cycle_id: str, reason: Optional[str] = None):
    try:
        return await arbitrage_cycles.abort(cycle_id, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------- Operator Console (READ-ONLY, human-in-the-loop) ----------------

@router.get("/operator-console")
async def operator_console_pkg(investment_usd: float = 50.0):
    if investment_usd is None or investment_usd <= 0:
        raise HTTPException(status_code=400, detail="investment_usd must be > 0")
    return await operator_console.build(investment_usd)


# ---------------- Wallet + Coinstore Observer (READ-ONLY) ----------------

class ObserverConfigPatch(BaseModel):
    enabled: Optional[bool] = None
    poll_interval_s: Optional[int] = None
    operator_bdag_address: Optional[str] = None
    operator_bsc_address: Optional[str] = None
    coinstore_bdag_deposit_address: Optional[str] = None
    coinstore_usdt_hot_wallet_address: Optional[str] = None
    blockdag_rpc_primary: Optional[str] = None
    blockdag_rpc_secondary: Optional[str] = None
    bscscan_api_base: Optional[str] = None
    bscscan_api_key: Optional[str] = None
    max_blocks_per_tick: Optional[int] = None
    force_primary_down: Optional[bool] = None
    # legacy compat — accepted but ignored
    blockdag_explorer_base: Optional[str] = None
    blockdag_explorer_kind: Optional[str] = None


class CoinstoreSellStamp(BaseModel):
    cycle_id: str
    order_id: str
    bdag_sold: float
    usdt_received: float
    fee_usdt: Optional[float] = None
    best_bid_at_sell: Optional[float] = None


class LinkEventBody(BaseModel):
    cycle_id: str


@router.get("/observer/status")
async def observer_status():
    return await wallet_observer.status()


@router.get("/observer/config")
async def observer_get_config():
    return await wallet_observer.get_config()


@router.put("/observer/config")
async def observer_put_config(patch: ObserverConfigPatch):
    try:
        return await wallet_observer.update_config(patch.dict(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/observer/events")
async def observer_events(limit: int = 50, status: Optional[str] = None):
    return await wallet_observer.list_events(limit=limit, status=status)


@router.post("/observer/poll")
async def observer_poll_now():
    return await wallet_observer.poller.run_once()


@router.post("/observer/events/{event_id}/link")
async def observer_link_event(event_id: str, body: LinkEventBody):
    try:
        return await wallet_observer.link_event_to_cycle(event_id, body.cycle_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/observer/coinstore-sells")
async def observer_coinstore_sells(limit: int = 50):
    return await wallet_observer.list_sells(limit=limit)


@router.post("/observer/coinstore-sell")
async def observer_stamp_sell(body: CoinstoreSellStamp):
    try:
        return await wallet_observer.stamp_coinstore_sell(
            cycle_id=body.cycle_id, order_id=body.order_id,
            bdag_sold=body.bdag_sold, usdt_received=body.usdt_received,
            fee_usdt=body.fee_usdt, best_bid_at_sell=body.best_bid_at_sell,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/observer/rpc-health")
async def observer_rpc_health():
    rpc = wallet_observer.poller.rpc
    if not rpc:
        cfg = await wallet_observer.get_config()
        wallet_observer.poller.rebuild_rpc(
            primary=cfg.get("blockdag_rpc_primary"),
            secondary=cfg.get("blockdag_rpc_secondary"),
        )
        rpc = wallet_observer.poller.rpc
    return rpc.health_snapshot()


@router.post("/observer/diagnostic")
async def observer_run_diagnostic(body: Optional[dict] = None):
    body = body or {}
    return await wallet_observer.run_diagnostic(
        test_address=body.get("test_address"),
        test_tx=body.get("test_tx"),
        expected_chain_id=body.get("expected_chain_id"),
    )


@router.get("/observer/diagnostic/last")
async def observer_last_diagnostic():
    doc = await db.db[wallet_observer.DIAG_COLL].find_one({}, {"_id": 0},
                                                          sort=[("ran_at", -1)])
    return doc or {"available": False, "note": "no diagnostic run yet"}


# ---------------- Cycle Timing + Risk Decay Engine (READ-ONLY) ----------------

@router.get("/cycle-timing")
async def cycle_timing_report(limit: int = 200):
    if limit <= 0 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be in (0, 500]")
    return await cycle_timing.build_report(limit=limit)


@router.get("/cycle-timing/forecast")
async def cycle_timing_forecast(captured_price: float, best_bid: float,
                                investment_usd: float,
                                taker_fee_pct: float = 0.20,
                                bdag_transfer_fee_base: float = 0.0):
    if captured_price <= 0 or best_bid <= 0 or investment_usd <= 0:
        raise HTTPException(status_code=400,
                             detail="captured_price, best_bid, investment_usd must all be > 0")
    return await cycle_timing.forecast_now(
        captured_price=captured_price, best_bid=best_bid,
        investment_usd=investment_usd, taker_fee_pct=taker_fee_pct,
        bdag_transfer_fee_base=bdag_transfer_fee_base,
    )


@router.get("/drift-analysis")
async def drift_analysis_latest(symbol: str = "BDAGUSDT", venue: str = "coinstore"):
    """Latest cached drift snapshot for the (symbol, venue) pair.

    Read-only parallel intelligence layer. Never mutates buy-price authority,
    quote-capture authority, or any execution decision.
    """
    doc = await drift_runner_mod.latest(symbol=symbol, venue=venue)
    if not doc:
        return {
            "available": False,
            "symbol": symbol, "venue": venue,
            "note": "no drift snapshot yet — runner ticks every 10 min after boot; POST /run forces an immediate recompute",
            "schema_version": 1,
        }
    return {"available": True, **doc}


@router.post("/drift-analysis/run")
async def drift_analysis_run(body: Optional[dict] = None):
    """Force an immediate recompute. Optional body: { symbols: [{symbol, venue}, ...] }."""
    body = body or {}
    pairs = None
    if body.get("symbols"):
        pairs = [(p["symbol"], p.get("venue", "coinstore")) for p in body["symbols"]]
    summaries = await drift_runner.run_once(symbols=pairs)
    return {"ran_at": summaries[0].get("computed_at") if summaries and "computed_at" in summaries[0] else None,
            "summaries": summaries}


@router.get("/drift-analysis/history")
async def drift_analysis_history(symbol: str = "BDAGUSDT", venue: str = "coinstore",
                                  limit: int = 50):
    if limit <= 0 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be in (0, 500]")
    docs = await drift_runner_mod.history(symbol=symbol, venue=venue, limit=limit)
    # Strip heavy fields from history responses to keep payloads light
    light = []
    for d in docs:
        light.append({
            "computed_at": d.get("computed_at"),
            "computed_at_ts": d.get("computed_at_ts"),
            "regime": (d.get("regime") or {}).get("label"),
            "risk_label": (d.get("risk_score") or {}).get("label"),
            "risk_score": (d.get("risk_score") or {}).get("score_0_100"),
            "max_buy_usd": (d.get("opportunity_capacity") or {}).get("max_buy_usd"),
            "recommended_buy_usd": (d.get("opportunity_capacity") or {}).get("recommended_buy_usd"),
            "opportunity_capacity_score_0_100": (d.get("opportunity_capacity") or {}).get("opportunity_capacity_score_0_100"),
            "sample_count_summary": d.get("sample_count_summary"),
        })
    return {"symbol": symbol, "venue": venue, "count": len(light), "snapshots": light}


@router.get("/drift-analysis/symbols")
async def drift_analysis_symbols():
    return {"pairs": await drift_runner_mod.symbols(),
            "runner": await drift_runner.status()}



# ============================================================================
# APPROVAL REQUIRED MODE — sizing + proposals + approve/reject + auto-mode flag
# Parallel intelligence layer; never modifies buy_price, quote_capture,
# wallet_observer, or any execution path that would move funds.
# ============================================================================
from services.execution import sizing as sizing_svc
from services.execution import approval_workflow as approval_wf


@router.get("/sizing-targets")
async def get_sizing_targets():
    """Live sizing inputs used by the Approval Console + userscript v2."""
    return await sizing_svc.compute_targets()


@router.get("/proposed")
async def get_proposed():
    """Ranked list of actionable proposals (primary + secondary)."""
    return await approval_wf.build_proposals()


@router.post("/proposed/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, body: dict):
    size_usd = float(body.get("size_usd") or 0)
    approve_mode = body.get("approve_mode") or "recommended"
    note = body.get("note")
    if size_usd <= 0:
        raise HTTPException(status_code=400, detail="size_usd must be positive")
    try:
        return await approval_wf.approve(proposal_id, size_usd, approve_mode, note)
    except (ValueError, LookupError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/proposed/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, body: Optional[dict] = None):
    body = body or {}
    return await approval_wf.reject(proposal_id, body.get("reason"))


@router.get("/auto-mode/status")
async def get_auto_mode_status():
    return await approval_wf.auto_mode_status()


@router.put("/auto-mode/status")
async def set_auto_mode_status(body: dict):
    return await approval_wf.set_auto_mode(bool(body.get("enabled")))


# Public batch capture endpoint — userscript v2 POSTs verified multi-size quotes.
# Gated by the ARBICORE_QUOTE_CAPTURE_KEY header (same key as single-shot capture).
import os as _os
ARBICORE_QUOTE_CAPTURE_KEY = _os.environ.get("ARBICORE_QUOTE_CAPTURE_KEY", "")


# ---- Proposer worker status + history --------------------------------------
from services.execution.approval_proposer import approval_proposer as _proposer
from services.execution import approval_proposer as _proposer_mod


@router.get("/proposer/status")
async def proposer_status():
    return await _proposer.status()


@router.get("/proposed/current")
async def proposed_current():
    """Returns the latest auto-built snapshot persisted by the proposer worker.
    Falls back to a live build_proposals() if nothing is cached yet."""
    snap = await _proposer_mod.current_snapshot()
    if snap:
        return {"source": "proposer_cache", **snap}
    live = await approval_wf.build_proposals()
    return {"source": "live_rebuild", **live}


@router.get("/proposed/history")
async def proposed_history(limit: int = 20):
    return {"snapshots": await _proposer_mod.recent_snapshots(min(max(limit, 1), 100))}
