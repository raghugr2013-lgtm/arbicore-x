"""Post-Validation Review & Calibration framework (v2.8.0 · read-only).

Consumes data already accumulated in MID + the live registry + live
scanner stats. Produces four artefacts:

  * calibration_report()  — every metric the operator will archive
  * recommendations()     — advisory-only tuning suggestions
  * readiness_score()     — per-subsystem + overall scores
  * executive_summary()   — narrative + go/no-go verdict

Nothing here writes runtime state, changes scanning behaviour, or
enables execution. Everything is a query over collections and
existing snapshots.
"""
from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pl(row: Dict[str, Any]) -> Dict[str, Any]:
    return row.get("payload") or row.get("data") or {}


def _safe_pct(num: float, den: float) -> float:
    return round(num / den * 100.0, 2) if den else 0.0


class PostValidationReviewer:
    """Composes calibration / recommendations / scoring / executive summary."""

    def __init__(self, *, mid_reader, registry,
                  live_scanners: List[Any],
                  runtime_config,
                  paper_engine=None,
                  kill_switch=None,
                  validation_reporter=None,
                  daily_writer=None) -> None:
        self._mid = mid_reader
        self._reg = registry
        self._scanners = list(live_scanners or [])
        self._cfg = runtime_config
        self._paper = paper_engine
        self._kill = kill_switch
        self._reporter = validation_reporter
        self._daily = daily_writer

    # ------------------------------------------------------------------
    # 1. Calibration Report
    # ------------------------------------------------------------------
    async def calibration_report(self, sample_limit: int = 2000) -> Dict[str, Any]:
        t0 = time.time()
        opps = await self._q("opportunities", sample_limit)
        routes = await self._q("routes", sample_limit)
        decisions = await self._q("decisions", sample_limit)

        # ---- Provider layer ---------------------------------------------------
        prov_snap = self._reg.snapshot() if self._reg else {}
        prov_rows: List[Dict[str, Any]] = []
        for kind, rows in (prov_snap.get("by_kind") or {}).items():
            for r in rows:
                s = r.get("success", 0) or 0
                f = r.get("failure", 0) or 0
                total = s + f
                prov_rows.append({
                    "provider_id": r.get("provider_id"),
                    "kind": kind,
                    "status": r.get("status"),
                    "score": r.get("score"),
                    "ewma_latency_ms": r.get("ewma_latency_ms"),
                    "success": s, "failure": f, "total_calls": total,
                    "error_rate": (f / total) if total else None,
                })
        prov_rows.sort(
            key=lambda r: (r["error_rate"] if r["error_rate"] is not None else -1,
                            -(r.get("score") or 0)))

        # ---- Exchange (CEX venue) ranking -----------------------------------
        venue_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"buy": 0, "sell": 0, "gross_usd": [], "net_usd": []})
        for r in opps:
            p = _pl(r)
            for v_key, side in (("venue_buy", "buy"), ("venue_sell", "sell")):
                v = p.get(v_key)
                if not v:
                    continue
                venue_stats[v][side] += 1
                if p.get("gross_profit_usd") is not None:
                    venue_stats[v]["gross_usd"].append(
                        float(p["gross_profit_usd"]))
                if p.get("net_profit_usd") is not None:
                    venue_stats[v]["net_usd"].append(
                        float(p["net_profit_usd"]))
        venue_rows = []
        for v, s in venue_stats.items():
            venue_rows.append({
                "venue": v,
                "appearances": s["buy"] + s["sell"],
                "as_buy": s["buy"], "as_sell": s["sell"],
                "avg_gross_usd": round(mean(s["gross_usd"]), 4)
                                 if s["gross_usd"] else None,
                "avg_net_usd": round(mean(s["net_usd"]), 4)
                                 if s["net_usd"] else None,
                "profitable_rate": _safe_pct(
                    sum(1 for x in s["net_usd"] if x > 0),
                    len(s["net_usd"])) / 100.0 if s["net_usd"] else None,
            })
        venue_rows.sort(key=lambda r: r["appearances"], reverse=True)

        # ---- Scanner ranking -------------------------------------------------
        scanner_rows = []
        for sc in self._scanners:
            st = sc.stats
            iters = st.get("iterations", 0) or 0
            emit = st.get("opportunities_emitted", 0) or 0
            scanner_rows.append({
                "scanner_id": getattr(sc, "scanner_id", "?"),
                "running": sc.is_running(),
                "iterations": iters,
                "quotes_collected": st.get("quotes_collected", 0),
                "opportunities_emitted": emit,
                "hit_rate": round(emit / iters, 4) if iters else 0.0,
                "last_error": st.get("last_error"),
            })
        scanner_rows.sort(
            key=lambda r: r["opportunities_emitted"], reverse=True)

        # ---- Opportunity frequency, recurrence, lifetime --------------------
        freq_by_type: Counter = Counter()
        freq_by_chain: Counter = Counter()
        for r in opps:
            p = _pl(r)
            freq_by_type[p.get("opportunity_type") or "unknown"] += 1
            freq_by_chain[p.get("chain") or "unknown"] += 1
        route_counter: Counter = Counter()
        for r in routes:
            rid = (_pl(r).get("route_id")
                    or (r.get("fingerprint") or {}).get("route_id")
                    or "unknown")
            route_counter[rid] += 1

        lifetimes: List[Dict[str, Any]] = []
        try:
            life_rows = await self._mid.query(
                "opportunity_lifetime", limit=sample_limit)
        except Exception:                                            # noqa
            life_rows = []
        lifetime_ms_samples: List[float] = []
        for r in life_rows or []:
            p = _pl(r) or r
            lt = p.get("lifetime_ms")
            if lt is not None:
                try:
                    lifetime_ms_samples.append(float(lt))
                except (TypeError, ValueError):
                    pass
        lifetime_stats = _summ_stats(lifetime_ms_samples) if lifetime_ms_samples else None

        # ---- Confidence calibration ------------------------------------------
        dec_by_opp: Dict[str, str] = {}
        for d in decisions:
            p = _pl(d)
            oid = p.get("opp_id") or d.get("opp_id")
            if not oid:
                continue
            v = (p.get("verdict") or p.get("decision") or "").upper()
            dec_by_opp[oid] = v
        buckets: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"count": 0, "go": 0, "block": 0})
        for r in opps:
            p = _pl(r)
            c = p.get("confidence")
            if c is None:
                continue
            try:
                cf = float(c)
            except (TypeError, ValueError):
                continue
            b_key = f"{int(cf*10)/10:.1f}-{int(cf*10)/10 + 0.1:.1f}"
            buckets[b_key]["count"] += 1
            oid = p.get("opp_id") or r.get("opp_id")
            v = dec_by_opp.get(oid, "")
            if v.startswith("GO"):   buckets[b_key]["go"] += 1
            elif v.startswith(("BLOCK", "NO", "REJECT")): buckets[b_key]["block"] += 1

        # ---- Expected vs observed profitability -----------------------------
        exp_vs_obs = _summ_stats([
            float(_pl(r).get("net_profit_usd"))
            for r in opps if _pl(r).get("net_profit_usd") is not None])
        gross_stats = _summ_stats([
            float(_pl(r).get("gross_profit_usd"))
            for r in opps if _pl(r).get("gross_profit_usd") is not None])
        profitable_count = sum(1 for r in opps
                                 if (_pl(r).get("net_profit_usd") or 0) > 0)
        total_with_net = sum(1 for r in opps
                              if _pl(r).get("net_profit_usd") is not None)

        # ---- Paper engine ----------------------------------------------------
        paper_stats = (self._paper.stats.to_dict()
                        if self._paper and hasattr(self._paper.stats, "to_dict")
                        else (self._paper.stats if self._paper else {}))

        # ---- Anomalies (from daily writer) ----------------------------------
        anomalies = self._daily.last_anomalies if self._daily else []

        # ---- Regime distribution --------------------------------------------
        regime_counter: Counter = Counter()
        for r in opps:
            regime_counter[_pl(r).get("market_regime") or "UNKNOWN"] += 1

        # ---- Uptime & error stats -------------------------------------------
        # No wall-clock uptime available server-side without an extra
        # timer; approximate via scanner iteration counts × cadence.
        approx_uptime_seconds = _approx_uptime(self._scanners, self._cfg)
        error_stats = {
            "scanners_with_last_error": sum(1 for r in scanner_rows
                                                 if r.get("last_error")),
            "scanners_total": len(scanner_rows),
            "provider_tripped": sum(1 for r in prov_rows
                                        if r.get("status") == "TRIPPED"),
        }

        return {
            "generated_at": _iso(),
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
            "sample_limit": sample_limit,
            "sampled": {
                "opportunities": len(opps),
                "routes": len(routes),
                "decisions": len(decisions),
                "lifetime_rows": len(life_rows or []),
            },
            "provider_ranking": prov_rows,
            "provider_reliability": {
                "total": len(prov_rows),
                "healthy": sum(1 for r in prov_rows
                                if r["status"] == "HEALTHY"),
                "tripped": sum(1 for r in prov_rows
                                if r["status"] == "TRIPPED"),
                "avg_ewma_latency_ms": round(mean(
                    [r["ewma_latency_ms"] for r in prov_rows
                      if r.get("ewma_latency_ms") is not None] or [0]), 2),
            },
            "exchange_ranking": venue_rows,
            "scanner_ranking": scanner_rows,
            "opportunity_frequency": {
                "by_type": dict(freq_by_type),
                "by_chain": dict(freq_by_chain),
                "total": len(opps),
            },
            "opportunity_recurrence": {
                "unique_routes": len(route_counter),
                "top_routes": [{"route_id": k, "count": v}
                                 for k, v in route_counter.most_common(20)],
            },
            "opportunity_lifetime": {
                "samples": len(lifetime_ms_samples),
                "stats_ms": lifetime_stats,
            },
            "confidence_calibration": {
                "buckets": {k: b for k, b in sorted(buckets.items())},
                "sampled_opps": len(opps),
                "sampled_decisions": len(decisions),
            },
            "expected_vs_observed": {
                "sampled_with_net": total_with_net,
                "profitable_count": profitable_count,
                "profitable_pct": _safe_pct(profitable_count, total_with_net),
                "net_profit_usd": exp_vs_obs,
                "gross_profit_usd": gross_stats,
            },
            "paper_engine": paper_stats,
            "validation_anomalies": anomalies,
            "regime_distribution": [
                {"regime": k, "count": v} for k, v in regime_counter.most_common()],
            "system_health": {
                "approx_uptime_seconds": approx_uptime_seconds,
                "errors": error_stats,
                "kill_switch_engaged": bool(self._kill.is_engaged())
                                         if self._kill else None,
            },
        }

    # ------------------------------------------------------------------
    # 2. Recommendations (advisory only)
    # ------------------------------------------------------------------
    async def recommendations(self, sample_limit: int = 2000) -> Dict[str, Any]:
        report = await self.calibration_report(sample_limit=sample_limit)
        recs: List[Dict[str, Any]] = []

        # Providers to disable
        for row in report["provider_ranking"]:
            er = row["error_rate"] or 0.0
            total = row["total_calls"]
            if total >= 30 and er >= 0.5:
                recs.append({
                    "category": "provider_disable",
                    "target": row["provider_id"],
                    "reason": f"error_rate={er:.1%} on {total} calls",
                    "severity": "high",
                    "advisory": (
                        f"Set PROVIDER_{_env_key_for(row)}_ENABLED to exclude "
                        f"or add failover URLs."),
                })
            if row["status"] == "TRIPPED":
                recs.append({
                    "category": "provider_disable",
                    "target": row["provider_id"],
                    "reason": "breaker is currently TRIPPED",
                    "severity": "high",
                    "advisory": "Remove or replace this provider before Stage 6.",
                })

        # Providers to prioritise
        for row in report["provider_ranking"]:
            if (row["total_calls"] >= 30
                    and (row["error_rate"] or 0) < 0.05
                    and (row["ewma_latency_ms"] or 0) < 200
                    and row["status"] == "HEALTHY"):
                recs.append({
                    "category": "provider_priority_boost",
                    "target": row["provider_id"],
                    "reason": (f"error={row['error_rate']:.1%}, "
                                 f"lat={row['ewma_latency_ms']:.0f}ms"),
                    "severity": "info",
                    "advisory": "Consider raising registry priority for this provider.",
                })

        # Exchanges producing poor opportunities
        for e in report["exchange_ranking"]:
            if (e["appearances"] >= 20
                    and e.get("avg_net_usd") is not None
                    and e["avg_net_usd"] < 0):
                recs.append({
                    "category": "exchange_reconsider",
                    "target": e["venue"],
                    "reason": (f"avg net profit ${e['avg_net_usd']:.2f} on "
                                 f"{e['appearances']} appearances"),
                    "severity": "medium",
                    "advisory": ("Investigate fee ladder for this venue. "
                                    "Update ECON_VENUE_FEE_BPS if inaccurate."),
                })

        # Scanner threshold adjustments
        for s in report["scanner_ranking"]:
            if (s["iterations"] >= 100
                    and s["opportunities_emitted"] == 0):
                recs.append({
                    "category": "scanner_threshold",
                    "target": s["scanner_id"],
                    "reason": (f"{s['iterations']} iterations, zero emissions"),
                    "severity": "high",
                    "advisory": ("Lower LIVE_MIN_SPREAD_BPS / CROSS_MIN_NET_BPS "
                                    "or investigate provider quotes."),
                })
            if s.get("hit_rate", 0) > 0.5 and s["iterations"] >= 100:
                recs.append({
                    "category": "scanner_threshold",
                    "target": s["scanner_id"],
                    "reason": f"hit_rate={s['hit_rate']:.2f} is very high",
                    "severity": "info",
                    "advisory": "Raise threshold to reduce noise.",
                })

        # Confidence threshold recommendation
        buckets = report["confidence_calibration"]["buckets"]
        if buckets:
            # find lowest bucket where go rate becomes majority
            sorted_bs = sorted(buckets.items())
            for k, v in sorted_bs:
                total = v["count"]
                if total >= 10 and v["go"] / total >= 0.5:
                    recs.append({
                        "category": "confidence_threshold",
                        "target": "paper_engine",
                        "reason": (f"bucket {k}: {v['go']}/{total} = "
                                     f"{v['go']/total:.1%} GO"),
                        "severity": "info",
                        "advisory": (f"Set confidence floor near lower bound "
                                        f"of bucket {k}."),
                    })
                    break

        # Fee tuning recommendation
        exp = report["expected_vs_observed"]
        if exp["sampled_with_net"] >= 50 and exp["profitable_pct"] < 5.0:
            recs.append({
                "category": "fee_tuning",
                "target": "arbicore.economics.VENUE_FEE_BPS",
                "reason": (f"only {exp['profitable_pct']:.1f}% of live opps "
                             f"were net-profitable"),
                "severity": "medium",
                "advisory": ("Verify per-venue fee assumptions against your "
                                "actual account tier. Tune ECON_VENUE_FEE_BPS."),
            })

        # Polling cadence recommendation
        total_ops = sum(s["opportunities_emitted"] for s in report["scanner_ranking"])
        if report["sampled"]["opportunities"] < 100 and total_ops < 20:
            recs.append({
                "category": "polling_cadence",
                "target": "LIVE_TICK_INTERVAL_SECONDS",
                "reason": "very low sample volume during the window",
                "severity": "info",
                "advisory": ("Reduce LIVE_TICK_INTERVAL_SECONDS to 10 or lower "
                                "if provider rate-limits allow."),
            })

        # Retry / timeout recommendations based on error observations
        hh = self._cfg.hardening
        prov_errored = [r for r in report["provider_ranking"]
                          if r.get("error_rate") is not None
                          and r["error_rate"] > 0.1
                          and r["total_calls"] >= 20]
        if len(prov_errored) >= 3:
            recs.append({
                "category": "retry_hardening",
                "target": "HARDEN_HTTP_RETRIES",
                "reason": (f"{len(prov_errored)} providers with >10% error rate"),
                "severity": "info",
                "advisory": (
                    f"Consider raising HARDEN_HTTP_RETRIES from "
                    f"{hh.http_retries} to 3, and increase "
                    f"HARDEN_HTTP_BACKOFF_MS from {hh.http_backoff_initial_ms} "
                    f"to 500."),
            })

        # Timeout recommendation
        avg_lat = report["provider_reliability"]["avg_ewma_latency_ms"]
        if avg_lat and avg_lat > hh.http_timeout_seconds * 1000 * 0.4:
            recs.append({
                "category": "timeout_hardening",
                "target": "HARDEN_HTTP_TIMEOUT_S",
                "reason": (f"avg ewma latency {avg_lat:.0f}ms is close to "
                             f"the {hh.http_timeout_seconds}s timeout"),
                "severity": "medium",
                "advisory": ("Increase HARDEN_HTTP_TIMEOUT_S to keep p95 "
                                "well under the timeout."),
            })

        return {
            "generated_at": _iso(),
            "recommendation_count": len(recs),
            "by_severity": {
                s: sum(1 for r in recs if r["severity"] == s)
                for s in ("info", "medium", "high")
            },
            "recommendations": recs,
            "note": ("Advisory only. No configuration is modified. "
                       "Apply changes via env vars and restart if agreed."),
        }

    # ------------------------------------------------------------------
    # 3. Readiness Score
    # ------------------------------------------------------------------
    async def readiness_score(self, sample_limit: int = 2000) -> Dict[str, Any]:
        report = await self.calibration_report(sample_limit=sample_limit)

        # Market Intelligence — did we accumulate a meaningful volume of
        # live opportunities?
        opps_total = report["opportunity_frequency"]["total"]
        live_types = [t for t in report["opportunity_frequency"]["by_type"]
                       if t not in ("unknown",)]
        mi_score = _clip01(opps_total / 1000.0) * 0.7 + \
                    _clip01(len(live_types) / 3.0) * 0.3

        # Provider layer — healthy % + avg latency
        pr = report["provider_reliability"]
        prov_pct = _safe_pct(pr["healthy"], pr["total"] or 1) / 100.0
        lat_score = _clip01(1 - (pr["avg_ewma_latency_ms"] or 0) / 3000.0)
        prov_score = 0.7 * prov_pct + 0.3 * lat_score

        # Scanner layer — average hit rate + running count
        sr = report["scanner_ranking"]
        running_pct = _safe_pct(sum(1 for s in sr if s["running"]),
                                  len(sr) or 1) / 100.0
        avg_hit = mean([s["hit_rate"] for s in sr]) if sr else 0.0
        scan_score = 0.6 * running_pct + 0.4 * _clip01(avg_hit / 0.5)

        # Paper engine — analysed / (analysed + blocked)
        pe = report["paper_engine"] or {}
        pe_score = 0.5
        if pe:
            analysed = pe.get("analyses", 0) or 0
            blocked = pe.get("policy_blocked", 0) or 0
            total = analysed + blocked
            if total:
                # blocked is CORRECT during v2.7.0 (kill engaged); we
                # score by how consistently the engine sees traffic.
                pe_score = _clip01(total / 500.0)

        # Validation framework — daily writer running + anomalies bound
        vf_score = 1.0
        if self._daily is None:
            vf_score = 0.4
        elif not self._daily.is_running():
            vf_score = 0.5
        anomalies = report["validation_anomalies"] or []
        crit = sum(1 for a in anomalies if a.get("severity") == "critical")
        vf_score = max(0.0, vf_score - 0.2 * crit)

        # Operations — approximate uptime + zero critical anomalies
        up = report["system_health"]["approx_uptime_seconds"] or 0
        ops_score = _clip01(up / (7 * 24 * 3600)) * 0.7 \
                     + (1.0 if crit == 0 else 0.0) * 0.3

        # Safety — the invariant. Must be 1.0 for any go-decision.
        safety_ok = report["system_health"]["kill_switch_engaged"]
        safety_score = 1.0 if safety_ok else 0.0

        overall = (
            0.20 * mi_score + 0.20 * prov_score + 0.15 * scan_score +
            0.10 * pe_score + 0.15 * vf_score + 0.10 * ops_score +
            0.10 * safety_score
        )

        def _explain(name: str, s: float, note: str) -> Dict[str, Any]:
            return {"subsystem": name, "score": round(s, 3),
                     "grade": _grade(s), "explanation": note}

        return {
            "generated_at": _iso(),
            "scores": [
                _explain("Market Intelligence", mi_score,
                          f"{opps_total} opps observed across "
                          f"{len(live_types)} types."),
                _explain("Provider Layer", prov_score,
                          f"{pr['healthy']}/{pr['total']} HEALTHY, "
                          f"avg ewma latency {pr['avg_ewma_latency_ms']:.0f}ms."),
                _explain("Scanner Layer", scan_score,
                          f"running: {int(running_pct*100)}%, "
                          f"avg hit rate {avg_hit:.2f}."),
                _explain("Paper Engine", pe_score,
                          f"analysed={pe.get('analyses',0)} "
                          f"blocked={pe.get('policy_blocked',0)}."),
                _explain("Validation Framework", vf_score,
                          f"daily writer bound, {crit} critical anomalies."),
                _explain("Operations", ops_score,
                          f"approx uptime {up}s, "
                          f"{crit} critical anomalies."),
                _explain("Safety", safety_score,
                          "Kill switch engaged."
                          if safety_ok else "KILL SWITCH DISENGAGED — HARD FAIL."),
            ],
            "overall": {
                "score": round(overall, 3),
                "grade": _grade(overall),
                "verdict": _verdict(overall, safety_ok),
            },
        }

    # ------------------------------------------------------------------
    # 4. Executive Summary
    # ------------------------------------------------------------------
    async def executive_summary(self,
                                  sample_limit: int = 2000) -> Dict[str, Any]:
        report = await self.calibration_report(sample_limit=sample_limit)
        recs = await self.recommendations(sample_limit=sample_limit)
        readiness = await self.readiness_score(sample_limit=sample_limit)

        worked, needs, tune = [], [], []

        # Worked well
        pr = report["provider_reliability"]
        if pr["total"] and pr["healthy"] / pr["total"] >= 0.9:
            worked.append(f"{pr['healthy']}/{pr['total']} providers HEALTHY.")
        if report["system_health"]["kill_switch_engaged"]:
            worked.append("Kill switch remained ENGAGED for the entire window.")
        sr = report["scanner_ranking"]
        if sr and all(s["running"] for s in sr):
            worked.append(f"All {len(sr)} live scanners stayed running.")
        pe = report["paper_engine"] or {}
        if (pe.get("policy_blocked", 0) or 0) > 0 and (
                pe.get("analyses", 0) or 0) == 0:
            worked.append(
                "Paper Engine correctly blocked every candidate while the "
                "kill switch was engaged (safety invariant held).")

        # Needs improvement
        high_recs = [r for r in recs["recommendations"]
                      if r["severity"] == "high"]
        needs.extend(f"{r['category']}: {r['target']} — {r['reason']}"
                     for r in high_recs)

        # What should be tuned
        med_recs = [r for r in recs["recommendations"]
                     if r["severity"] == "medium"]
        tune.extend(f"{r['category']}: {r['target']} — {r['advisory']}"
                    for r in med_recs)

        overall_score = readiness["overall"]["score"]
        recommend_another_run = overall_score < 0.75 or len(high_recs) > 0
        ready_next = (overall_score >= 0.75
                       and not high_recs
                       and report["system_health"]["kill_switch_engaged"])

        return {
            "generated_at": _iso(),
            "overall_score": overall_score,
            "grade": readiness["overall"]["grade"],
            "verdict": readiness["overall"]["verdict"],
            "recommendation_counts": recs["by_severity"],
            "worked_well": worked,
            "needs_improvement": needs,
            "should_tune": tune,
            "another_validation_run_recommended": recommend_another_run,
            "ready_for_next_phase": ready_next,
            "next_phase_gate": (
                "Sign-off to plan Stage 6 (Limited-Live Executor) "
                "only after another clean 7-day validation run with zero "
                "high-severity recommendations."
                if recommend_another_run else
                "Proceed to Stage 6 planning: draft the Limited-Live "
                "Executor RFC. Kill switch must remain admin-only."),
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    async def _q(self, collection: str, limit: int) -> List[Dict[str, Any]]:
        try:
            return await self._mid.query(collection, limit=limit)
        except Exception:                                            # noqa
            return []


def _summ_stats(xs: List[float]) -> Dict[str, float]:
    if not xs:
        return {}
    xs = sorted(xs)
    return {
        "count": len(xs),
        "min": round(xs[0], 4),
        "max": round(xs[-1], 4),
        "mean": round(mean(xs), 4),
        "median": round(median(xs), 4),
        "p10": round(xs[max(0, int(len(xs)*0.10) - 1)], 4),
        "p90": round(xs[min(len(xs)-1, int(len(xs)*0.90))], 4),
    }


def _clip01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _grade(score: float) -> str:
    if score >= 0.90: return "A"
    if score >= 0.75: return "B"
    if score >= 0.60: return "C"
    if score >= 0.40: return "D"
    return "F"


def _verdict(overall: float, safety_ok: bool) -> str:
    if not safety_ok:
        return "REJECT — safety invariant failed."
    if overall >= 0.90:
        return "READY — proceed to next phase planning."
    if overall >= 0.75:
        return "READY WITH MINOR TUNING — apply advisory recommendations."
    if overall >= 0.60:
        return "NOT READY — run another 7-day validation after tuning."
    return "NOT READY — investigate high-severity items before re-running."


def _env_key_for(row: Dict[str, Any]) -> str:
    """Map a provider row to the env-var stub name for the advisory."""
    kind = row.get("kind", "")
    return {
        "rpc": "RPC_URL",
        "quote_aggregator": "CEX_ENABLED",
        "dex": "DEX_ENABLED",
    }.get(kind, "PROVIDER")


def _approx_uptime(scanners: Iterable[Any], cfg) -> int:
    """Estimate uptime from the highest-iteration live scanner."""
    max_iters = 0
    interval = 15.0
    for s in scanners:
        it = s.stats.get("iterations", 0) or 0
        if it > max_iters:
            max_iters = it
            interval = cfg.scanners.live_market_interval_s
    return int(max_iters * interval)


__all__ = ["PostValidationReviewer"]
