"""In-memory per-exchange REST request telemetry (success/error/latency).
Recorded by ExchangeConnector._get on every live REST call; flushed to the
`exchange_health_snaps` collection every 5 minutes by the balance service.
Feeds the API-uptime component of Exchange Health Analytics (Sprint 4)."""
from collections import defaultdict


def _empty():
    return {"requests": 0, "errors": 0, "latency_sum_ms": 0.0}


_stats = defaultdict(_empty)


def record(exchange: str, ok: bool, latency_ms: float):
    s = _stats[exchange]
    s["requests"] += 1
    if not ok:
        s["errors"] += 1
    s["latency_sum_ms"] += latency_ms


def _view(s):
    req = s["requests"]
    return {"requests": req, "errors": s["errors"],
            "success_rate_pct": round((1 - s["errors"] / req) * 100, 2) if req else None,
            "avg_latency_ms": round(s["latency_sum_ms"] / req, 1) if req else None}


def snapshot_and_reset() -> dict:
    out = {ex: _view(s) for ex, s in _stats.items()}
    _stats.clear()
    return out


def current() -> dict:
    return {ex: _view(s) for ex, s in _stats.items()}
