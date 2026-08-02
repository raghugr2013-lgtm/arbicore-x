"""Phase E4 — Real API Integration Preparation (READ-ONLY, NON-EXECUTING).

Composes the existing read-only key infrastructure (vault + key_health +
exchange_private + balances + healthstats) into a cohesive *integration readiness*
assessment for the execution venues (Coinstore primary).

Verifies, with NO fund movement / NO trading / NO withdrawals / NO wallet calls:
  • connectivity        — public endpoint reachability + latency
  • credential validation — single signed account-read (reuses key_health)
  • permission           — read access verified; write scopes deliberately NOT probed
  • capability           — which read-only execution capabilities are reachable;
                           write capabilities are reported as venue-declared but
                           intentionally untested in E4 (probed only at E5 w/ approval)
  • health               — rolling REST telemetry from the live collector + balance poller

NO new signing code: this module reuses the already-tested read-only signed calls.
"""
import time

from core import healthstats, registry
from services import db, key_health, vault
from services.balances import balance_service
from services.execution import venue_registry

# Capabilities the live execution loop will eventually need, and how E4 treats them.
EXEC_CAPS = [
    {"cap": "public_market_data", "label": "Public market data (ticker / order book)",
     "tier": "E4 read-only", "probe": "connectivity"},
    {"cap": "account_balance_read", "label": "Account balance read (signed)",
     "tier": "E4 read-only", "probe": "signed_read"},
    {"cap": "deposit_address_read", "label": "Deposit address / deposit history read",
     "tier": "E5 live", "probe": None, "declared": "deposit_monitoring"},
    {"cap": "spot_trade", "label": "Spot trade — sell BDAG",
     "tier": "E5 live (WRITE)", "probe": None, "declared": "trading_api", "write": True},
    {"cap": "withdrawal", "label": "USDT withdrawal to whitelist",
     "tier": "E5 live (WRITE)", "probe": None, "declared": "withdrawal_api", "write": True},
]


async def probe_connectivity(exchange: str) -> dict:
    """Public-endpoint reachability + latency. Read-only; never authenticated."""
    t0 = time.monotonic()
    try:
        conn = registry.resolve(exchange, "live")
    except Exception as e:
        return {"ok": False, "latency_ms": None, "detail": f"no connector: {str(e)[:120]}"}
    try:
        await conn.get_ticker("BDAG", "USDT")
        ok, detail = True, "public market data reachable"
    except Exception as e:
        # SymbolNotListed / MalformedResponse still prove the endpoint is reachable
        name = type(e).__name__
        if name in ("SymbolNotListed", "MalformedResponse"):
            ok, detail = True, "endpoint reachable (BDAG/USDT not listed here)"
        else:
            ok, detail = False, f"{name}: {str(e)[:120]}"
    return {"ok": ok, "latency_ms": round((time.monotonic() - t0) * 1000), "detail": detail}


async def _latest_key(exchange: str):
    return await db.api_keys_col.find_one({"exchange": exchange}, {"_id": 0},
                                          sort=[("created_at", -1)])


def _health_telemetry(exchange: str) -> dict:
    rest = (healthstats.current() or {}).get(exchange) or {}
    bs = (balance_service.state.get(exchange) or {})
    return {
        "rest_requests": rest.get("requests"),
        "rest_success_rate_pct": rest.get("success_rate_pct"),
        "rest_avg_latency_ms": rest.get("avg_latency_ms"),
        "balance_poll_status": bs.get("status"),
        "balance_last_poll_at": bs.get("last_poll_at"),
        "balance_latency_ms": bs.get("latency_ms"),
        "balance_fail_streak": bs.get("fail_streak"),
    }


async def readiness(exchange: str) -> dict:
    exchange = exchange.lower()
    role_map = await venue_registry.get_role_map()
    role = role_map.get(exchange, "watch")
    conn_caps = {}
    venue_name = exchange.upper()
    try:
        c = registry.resolve(exchange, "live")
        conn_caps = getattr(c, "capabilities", {}) or {}
        venue_name = getattr(c, "name", venue_name)
    except Exception:
        pass

    conn = await probe_connectivity(exchange)
    key = await _latest_key(exchange)
    key_ok = bool(key and key.get("status") == "healthy")
    key_present = bool(key)

    capabilities = []
    for spec in EXEC_CAPS:
        if spec["probe"] == "connectivity":
            status = "verified" if conn["ok"] else "failed"
            note = conn["detail"]
        elif spec["probe"] == "signed_read":
            if not key_present:
                status, note = "pending", "no read-only key stored yet"
            elif key_ok:
                status, note = "verified", key.get("last_test_message") or "signed account read OK"
            else:
                status, note = "failed", key.get("last_test_message") or "key present but unverified"
        else:  # write / E5 capability — declared by venue, intentionally NOT probed in E4
            declared = bool(conn_caps.get(spec.get("declared"), False)) if spec.get("declared") else None
            status = "declared_untested" if declared else "unknown_untested"
            note = "venue-declared; NOT probed in E4 (no fund-moving calls)"
        capabilities.append({**{k: spec[k] for k in ("cap", "label", "tier")},
                             "write": spec.get("write", False), "status": status, "note": note})

    # read-only readiness = verified E4-tier caps / required E4-tier caps
    e4 = [c for c in capabilities if c["tier"] == "E4 read-only"]
    verified = sum(1 for c in e4 if c["status"] == "verified")
    score = round(verified / len(e4) * 100) if e4 else 0

    if not key_present:
        verdict = "NEEDS_READONLY_KEY"
    elif key_ok and conn["ok"]:
        verdict = "READ_VERIFIED"
    elif not key_ok:
        verdict = "KEY_ERROR"
    else:
        verdict = "CONNECTIVITY_ERROR"

    checklist = [
        {"item": "Public connectivity", "status": "pass" if conn["ok"] else "fail",
         "detail": conn["detail"]},
        {"item": "Read-only API key stored", "status": "pass" if key_present else "pending",
         "detail": key.get("label") if key else "add a Coinstore read-only key to continue"},
        {"item": "Signed credential validation", "status":
            "pass" if key_ok else ("fail" if key_present else "pending"),
         "detail": (key.get("last_test_message") if key else None) or "—"},
        {"item": "Read permission (balance)", "status":
            "pass" if key_ok else "pending", "detail": "account balance readable"},
        {"item": "Write scopes (trade/withdraw)", "status": "n/a",
         "detail": "intentionally NOT verified in E4 — key should be READ-ONLY until E5"},
    ]

    return {
        "exchange": exchange, "venue_name": venue_name, "role": role,
        "verdict": verdict, "readiness_score": score,
        "connectivity": conn,
        "key": vault._public(key) if key else None,
        "capabilities": capabilities,
        "checklist": checklist,
        "health": _health_telemetry(exchange),
        "permission_note": "E4 verifies READ access only. Create the Coinstore API key with "
                            "READ-ONLY scope. Trade/withdraw permissions are enabled only at E5 "
                            "with explicit approval, whitelist, and per-cycle caps.",
        "note": "Read-only integration preparation — no trading, no withdrawals, no wallet, no fund movement.",
    }


async def verify_key(key_id: str) -> dict:
    """Full read-only verification of a stored vault key: connectivity + signed read."""
    creds = await vault.get_credentials(key_id)
    if not creds:
        return None
    conn = await probe_connectivity(creds["exchange"])
    result = await key_health.run_test(creds["exchange"], creds["api_key"],
                                       creds["api_secret"], creds["passphrase"])
    await vault.set_test_result(key_id, result["ok"], result["message"])
    return {
        "key": await vault.get_key_public(key_id),
        "connectivity": conn,
        "credential_validation": result,
        "read_permission_verified": result["ok"],
        "write_permission_tested": False,
        "note": "Single signed account-read only. No trade, no withdraw, no fund movement.",
    }


async def integration_status() -> dict:
    """Readiness summary for the execution venues (primary + backup)."""
    role_map = await venue_registry.get_role_map()
    targets = [ex for ex, role in role_map.items() if role in ("primary", "backup")]
    targets.sort(key=lambda ex: 0 if role_map[ex] == "primary" else 1)
    venues = [await readiness(ex) for ex in targets]
    return {
        "phase": "E4 — Real API Integration Preparation (read-only)",
        "venues": venues,
        "note": "Composes vault + key_health + balance poller + REST telemetry. "
                "No fund-moving code is reachable in E4.",
    }
