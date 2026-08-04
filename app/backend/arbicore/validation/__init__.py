"""Validation framework (Stage 3 · v2.6.0).

Read-only analytics over MID. Produces the numbers required for the
7-day VPS validation run: opportunity recurrence, confidence
calibration, venue / provider / scanner rankings, regime slots,
execution-probability histograms, and an automated summary payload.

Every function is pure I/O against ``MidReader``. Nothing writes.
"""
from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _pl(row: Dict[str, Any]) -> Dict[str, Any]:
    return row.get("payload") or row.get("data") or {}


class ValidationReporter:
    """Composes read-only analytics over the MID collection surface."""

    def __init__(self, mid_reader: Any) -> None:
        self._mid = mid_reader

    async def _rows(self, collection: str, limit: int = 500) -> List[Dict]:
        try:
            return await self._mid.query(collection, limit=limit)
        except Exception:                                            # noqa
            return []

    # -------- 1. Opportunity Recurrence -------------------------------
    async def opportunity_recurrence(self, limit: int = 500) -> Dict[str, Any]:
        rows = await self._rows("mid_routes", limit=limit)
        counts: Counter = Counter()
        for r in rows:
            p = _pl(r)
            key = (p.get("route_id")
                    or (r.get("fingerprint") or {}).get("route_id")
                    or "unknown")
            counts[key] += 1
        top = counts.most_common(20)
        return {
            "total_route_rows": len(rows),
            "unique_routes": len(counts),
            "top_routes": [
                {"route_id": k, "count": v} for k, v in top
            ],
        }

    # -------- 2. Confidence Calibration -------------------------------
    async def confidence_calibration(self,
                                       limit: int = 500) -> Dict[str, Any]:
        """Bucket opportunities by predicted confidence and report the
        fraction that turned into positive-EV paper decisions."""
        opps = await self._rows("mid_opportunities", limit=limit)
        decisions = await self._rows("mid_decisions", limit=limit)
        # Index decisions by opp_id
        dec_by_opp: Dict[str, str] = {}
        for d in decisions:
            p = _pl(d)
            oid = p.get("opp_id") or d.get("opp_id")
            if not oid:
                continue
            verdict = p.get("verdict") or p.get("decision") or ""
            dec_by_opp[oid] = str(verdict).upper()

        buckets: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"count": 0, "go": 0, "block": 0})
        for r in opps:
            p = _pl(r)
            c = p.get("confidence")
            oid = p.get("opp_id") or r.get("opp_id")
            if c is None:
                continue
            try:
                cf = float(c)
            except (TypeError, ValueError):
                continue
            lo = int(cf * 10) / 10
            key = f"{lo:.1f}-{lo + 0.1:.1f}"
            b = buckets[key]
            b["count"] += 1
            v = dec_by_opp.get(oid, "")
            if v.startswith("GO") or v == "APPROVE":
                b["go"] += 1
            elif v.startswith("BLOCK") or v == "REJECT" or v.startswith("NO"):
                b["block"] += 1
        return {"buckets": {k: b for k, b in sorted(buckets.items())},
                 "sampled_opps": len(opps),
                 "sampled_decisions": len(decisions)}

    # -------- 3. Venue Ranking ----------------------------------------
    async def venue_ranking(self, limit: int = 500) -> Dict[str, Any]:
        rows = await self._rows("mid_opportunities", limit=limit)
        buy: Counter = Counter()
        sell: Counter = Counter()
        profit: Dict[str, List[float]] = defaultdict(list)
        for r in rows:
            p = _pl(r)
            if p.get("venue_buy"):
                buy[p["venue_buy"]] += 1
            if p.get("venue_sell"):
                sell[p["venue_sell"]] += 1
            for v in (p.get("venue_buy"), p.get("venue_sell")):
                np = p.get("net_profit_usd") or p.get("expected_profit_usd")
                if v and np is not None:
                    try:
                        profit[v].append(float(np))
                    except (TypeError, ValueError):
                        pass
        ranking = []
        for v in sorted(set(buy) | set(sell)):
            plist = profit.get(v, [])
            ranking.append({
                "venue": v,
                "buy_count": buy[v],
                "sell_count": sell[v],
                "total_appearances": buy[v] + sell[v],
                "avg_net_profit_usd": (round(mean(plist), 4)
                                          if plist else None),
                "profit_samples": len(plist),
            })
        ranking.sort(key=lambda x: x["total_appearances"], reverse=True)
        return {"venues": ranking, "sampled_opps": len(rows)}

    # -------- 4. Provider Ranking -------------------------------------
    def provider_ranking(self, registry: Any) -> Dict[str, Any]:
        snapshot = registry.snapshot()
        rows: List[Dict[str, Any]] = []
        for kind, provs in (snapshot.get("by_kind") or {}).items():
            for p in provs:
                rows.append({**p, "kind": kind})
        rows.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        return {"provider_count": len(rows),
                 "healthy_count": sum(1 for r in rows
                                        if r.get("status") == "HEALTHY"),
                 "ranked": rows[:50]}

    # -------- 5. Scanner Ranking --------------------------------------
    async def scanner_ranking(self,
                                scanners: Iterable[Any]) -> Dict[str, Any]:
        rows = []
        for s in scanners:
            st = s.stats
            rows.append({
                "scanner_id": getattr(s, "scanner_id", "unknown"),
                "running": s.is_running(),
                "iterations": st.get("iterations", 0),
                "opportunities_emitted": st.get("opportunities_emitted", 0),
                "quotes_collected": st.get("quotes_collected", 0),
                "hit_rate": (
                    round(st.get("opportunities_emitted", 0)
                           / max(st.get("iterations", 1), 1), 4)
                ),
                "last_run_at": st.get("last_run_at"),
                "last_error": st.get("last_error"),
            })
        rows.sort(key=lambda r: r["opportunities_emitted"], reverse=True)
        return {"scanners": rows}

    # -------- 6. Regime Analysis --------------------------------------
    async def regime_analysis(self, limit: int = 500) -> Dict[str, Any]:
        rows = await self._rows("mid_opportunities", limit=limit)
        by_regime: Counter = Counter()
        profit_by_regime: Dict[str, List[float]] = defaultdict(list)
        for r in rows:
            p = _pl(r)
            regime = p.get("market_regime") or "UNKNOWN"
            by_regime[regime] += 1
            np = p.get("net_profit_usd") or p.get("expected_profit_usd")
            if np is not None:
                try:
                    profit_by_regime[regime].append(float(np))
                except (TypeError, ValueError):
                    pass
        return {
            "regimes": [
                {"regime": r, "opportunity_count": c,
                  "avg_net_profit_usd": (round(mean(profit_by_regime[r]), 4)
                                             if profit_by_regime[r] else None)}
                for r, c in by_regime.most_common()
            ],
            "sampled_opps": len(rows),
        }

    # -------- 7. Execution Probability Report --------------------------
    async def execution_probability(self,
                                       limit: int = 500) -> Dict[str, Any]:
        # In v2.6 we approximate execution_probability using confidence ×
        # is_profitable × freshness. Real learning-based execution
        # probability lands in v2.7 when the Wave-1B-γ engine binds
        # concrete outcome data.
        rows = await self._rows("mid_opportunities", limit=limit)
        buckets = defaultdict(lambda: {"count": 0, "profitable": 0,
                                          "median_conf": []})
        for r in rows:
            p = _pl(r)
            np = p.get("net_profit_usd") or 0
            conf = float(p.get("confidence") or 0.0)
            bucket = "profitable" if (np or 0) > 0 else "unprofitable"
            b = buckets[bucket]
            b["count"] += 1
            b["median_conf"].append(conf)
            if np > 0:
                b["profitable"] += 1
        out = {}
        for k, v in buckets.items():
            confs = v["median_conf"]
            confs.sort()
            median = confs[len(confs) // 2] if confs else 0.0
            out[k] = {"count": v["count"], "median_confidence": median}
        return {"summary": out, "sampled_opps": len(rows)}

    # -------- 8. Historical Analytics ---------------------------------
    async def historical_analytics(self,
                                      limit: int = 500) -> Dict[str, Any]:
        opps = await self._rows("mid_opportunities", limit=limit)
        n_shadow = sum(1 for r in opps if _pl(r).get("shadow"))
        n_live = sum(1 for r in opps if _pl(r).get("live"))
        types: Counter = Counter()
        for r in opps:
            t = _pl(r).get("opportunity_type") or "unknown"
            types[t] += 1
        return {
            "sampled_opps": len(opps),
            "shadow_count": n_shadow,
            "live_count": n_live,
            "by_type": dict(types),
        }

    # -------- 9. Automated Summary ------------------------------------
    async def summary(self, *, scanners: Iterable[Any],
                        registry: Any) -> Dict[str, Any]:
        t0 = time.time()
        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"),
            "recurrence": await self.opportunity_recurrence(),
            "calibration": await self.confidence_calibration(),
            "venue_ranking": await self.venue_ranking(),
            "scanner_ranking": await self.scanner_ranking(scanners),
            "provider_ranking": self.provider_ranking(registry),
            "regime": await self.regime_analysis(),
            "execution_probability": await self.execution_probability(),
            "historical": await self.historical_analytics(),
            "elapsed_ms": round((time.time() - t0) * 1000, 2),
        }


__all__ = ["ValidationReporter"]
