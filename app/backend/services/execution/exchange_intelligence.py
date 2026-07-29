"""Exchange Intelligence Registry + Ranking Engine (READ-ONLY, NON-EXECUTING).

Tracks EVERY BDAG-listed exchange (not just the connector venues) as a first-
class intelligence record, scores each on liquidity / spread / trust, and ranks
them two different ways:

  • Best Profit Opportunity   — highest raw arbitrage edge, regardless of reach
  • Best Executable Opportunity — what we could ACTUALLY run end-to-end today

The whole point: the highest-profit venue is rarely the best EXECUTABLE venue.
Coinstore stays the only Execution-Approved candidate; every other venue is
Monitor-Only or Disabled until accessibility / KYC / deposit+withdraw gates /
API readiness are verified.

Curated baseline = the live-probed evidence in docs/20 (June 2026 audit). A live
overlay refreshes deposit/withdraw gates (capability registry) and order-book
liquidity/spread for the venues ArbiCore has a live connector for. NO execution,
no orders, no fund movement — this is pure intelligence.
"""
from datetime import datetime, timedelta, timezone

from core.models import now_iso
from services import db
from services.collector import collector
from services.execution import buy_price as bp_resolver

AUDIT_DATE = "2026-06-12T00:00:00+00:00"
AUDIT_DOC = "docs/20-exchange-automation-readiness-audit.md"

# Red flags that DISQUALIFY a venue outright (force "disabled"). Operational
# flags like closed gates / thin book / missing-withdrawal-API are NOT fatal —
# those keep a venue in "monitor_only".
CRITICAL_FLAGS = {
    "no_public_spot_api", "no_api_docs", "wash_trading", "dead_book",
    "dislocated_market", "bdag_suspended", "pair_absent_from_api",
    "listing_unconfirmable",
}

# ---- numeric mappings for scoring ----
_INDIA_NUM = {"verified": 1.0, "allowed": 0.7, "unverified": 0.35, "unknown": 0.1, "restricted": 0.0}
_API_NUM = {"full": 1.0, "partial": 0.6, "trade_only": 0.35, "none": 0.0}
_GATE_NUM = {"open": 1.0, "unverified": 0.4, "closed": 0.0, "suspended": 0.0}


# ---------------------------------------------------------------------------
# Curated baseline — all 11 BDAG-listed exchanges (docs/20, live-probed June 2026)
# ---------------------------------------------------------------------------
CURATED = [
    {
        "exchange": "coinstore", "name": "Coinstore", "bdag_pair": "BDAG/USDT",
        "india_access": "verified", "kyc": "required",
        "api_surface": {"trade": True, "deposit_address": True, "deposit_monitor": True,
                        "withdraw": True, "websocket": True},
        "gates_default": {"deposit": "open", "withdraw": "open"},
        "audited": {"best_bid": 3.97e-05, "usd_2pct": 91, "usd_5pct": 637, "usd_10pct": 1764,
                    "book_total_usd": 2939, "vol_24h_usd": 17200, "vol_reliable": True},
        "est_spread_pct": 0.6, "reliability": 0.95, "red_flags": [], "audit_score": 92,
        "operator_verified": True, "has_connector": True,
        "notes": "User-verified India loop end-to-end; complete documented API "
                 "(deposit address → monitoring → sell → order status → doWithdraw → status). "
                 "Withdrawals only to pre-verified addresses (hard blast-radius cap).",
    },
    {
        "exchange": "bitmart", "name": "BitMart", "bdag_pair": "BDAG/USDT",
        "india_access": "allowed", "kyc": "required",
        "api_surface": {"trade": True, "deposit_address": True, "deposit_monitor": True,
                        "withdraw": True, "websocket": True},
        "gates_default": {"deposit": "open", "withdraw": "open"},
        "audited": {"best_bid": 4.09e-05, "usd_2pct": 359, "usd_5pct": 1117, "usd_10pct": 2726,
                    "book_total_usd": 6188, "vol_24h_usd": 47800, "vol_reliable": True},
        "est_spread_pct": 0.5, "reliability": 0.90, "red_flags": [], "audit_score": 90,
        "operator_verified": False, "has_connector": True,
        "notes": "Deepest real BDAG book; both gates live-observed OPEN; full API parity with "
                 "Coinstore + verified-address withdrawal book. PRE-REQUISITE before promotion: "
                 "one manual ~$20 India deposit→sell→withdraw verification.",
    },
    {
        "exchange": "xt", "name": "XT.COM", "bdag_pair": "BDAG/USDT",
        "india_access": "allowed", "kyc": "required",
        "api_surface": {"trade": True, "deposit_address": True, "deposit_monitor": True,
                        "withdraw": True, "websocket": True},
        "gates_default": {"deposit": "closed", "withdraw": "closed"},
        "audited": {"best_bid": 3.82e-05, "usd_2pct": 30, "usd_5pct": 30, "usd_10pct": 695,
                    "book_total_usd": 4452, "vol_24h_usd": 268000, "vol_reliable": False},
        "est_spread_pct": 2.0, "reliability": 0.70, "red_flags": ["bdag_gates_closed"], "audit_score": 72,
        "operator_verified": False, "has_connector": True,
        "notes": "Structurally complete platform but BDAG deposit AND withdrawal gates currently "
                 "CLOSED (live-observed). Auto-promotable when gates reopen and hold. Reported "
                 "24h volume far exceeds real depth (discounted).",
    },
    {
        "exchange": "pionex", "name": "Pionex", "bdag_pair": "BDAG/USDT",
        "india_access": "allowed", "kyc": "tiered",
        "api_surface": {"trade": True, "deposit_address": False, "deposit_monitor": False,
                        "withdraw": False, "websocket": True},
        "gates_default": {"deposit": "unverified", "withdraw": "unverified"},
        "audited": {"best_bid": 4.10e-05, "usd_2pct": 21, "usd_5pct": 438, "usd_10pct": 1360,
                    "book_total_usd": 3435, "vol_24h_usd": 27500, "vol_reliable": True},
        "est_spread_pct": 1.5, "reliability": 0.60, "red_flags": ["no_deposit_withdraw_api"], "audit_score": 63,
        "operator_verified": False, "has_connector": False,
        "notes": "Spot-trade API only; deposit-address & withdrawal endpoints undocumented → not "
                 "end-to-end automatable. Usable as a manual overflow sell venue.",
    },
    {
        "exchange": "ascendex", "name": "AscendEX", "bdag_pair": "BDAG/USDT",
        "india_access": "allowed", "kyc": "required",
        "api_surface": {"trade": True, "deposit_address": True, "deposit_monitor": True,
                        "withdraw": False, "websocket": True},
        "gates_default": {"deposit": "open", "withdraw": "open"},
        "audited": {"best_bid": 3.66e-05, "usd_2pct": 25, "usd_5pct": 43, "usd_10pct": 83,
                    "book_total_usd": 778, "vol_24h_usd": 126000, "vol_reliable": False},
        "est_spread_pct": 5.0, "reliability": 0.60,
        "red_flags": ["no_withdrawal_api", "thin_liquidity"], "audit_score": 60,
        "operator_verified": False, "has_connector": False,
        "notes": "Most transparent listing (explicit Apr 2026 deposit/withdraw dates) and trade "
                 "automation is possible, but NO public withdrawal-execution API → settlement leg "
                 "is manual; book very thin (~5% spread).",
    },
    {
        "exchange": "lbank", "name": "LBank", "bdag_pair": "BDAG/USDT",
        "india_access": "allowed", "kyc": "required",
        "api_surface": {"trade": False, "deposit_address": True, "deposit_monitor": True,
                        "withdraw": True, "websocket": True},
        "gates_default": {"deposit": "suspended", "withdraw": "suspended"},
        "audited": {"best_bid": None, "usd_2pct": None, "usd_5pct": None, "usd_10pct": None,
                    "book_total_usd": None, "vol_24h_usd": None, "vol_reliable": False},
        "est_spread_pct": None, "reliability": 0.30,
        "red_flags": ["bdag_suspended", "pair_absent_from_api"], "audit_score": 53,
        "operator_verified": False, "has_connector": False,
        "notes": "Capable API platform, but BDAG operationally unstable: suspended Jun 4 & Jun 10 "
                 "2026, pair currently ABSENT from the public pair-list API. Re-audit only after "
                 "≥30 days of stable listing.",
    },
    {
        "exchange": "p2b", "name": "P2B", "bdag_pair": "BDAG/USDT",
        "india_access": "unverified", "kyc": "optional",
        "api_surface": {"trade": True, "deposit_address": False, "deposit_monitor": False,
                        "withdraw": False, "websocket": True},
        "gates_default": {"deposit": "unverified", "withdraw": "unverified"},
        "audited": {"best_bid": 3.73e-05, "usd_2pct": 3, "usd_5pct": 10, "usd_10pct": 19,
                    "book_total_usd": 2468, "vol_24h_usd": 1219000, "vol_reliable": False},
        "est_spread_pct": None, "reliability": 0.10,
        "red_flags": ["wash_trading", "no_deposit_withdraw_api"], "audit_score": 44,
        "operator_verified": False, "has_connector": False,
        "notes": "Wash-trading PROVEN by measurement: ~$1.2M reported 24h volume vs $3 of real bids "
                 "within 2% of best bid. No deposit/withdrawal API. Avoid.",
    },
    {
        "exchange": "biconomy", "name": "Biconomy", "bdag_pair": "BDAG/USDT",
        "india_access": "unknown", "kyc": "unknown",
        "api_surface": {"trade": True, "deposit_address": False, "deposit_monitor": False,
                        "withdraw": False, "websocket": True},
        "gates_default": {"deposit": "unverified", "withdraw": "unverified"},
        "audited": {"best_bid": 4.78e-05, "usd_2pct": 15, "usd_5pct": 43, "usd_10pct": 89,
                    "book_total_usd": 657, "vol_24h_usd": 21400, "vol_reliable": False},
        "est_spread_pct": 20.0, "reliability": 0.20,
        "red_flags": ["dislocated_market", "withdrawal_api_not_public", "india_unverified"], "audit_score": 43,
        "operator_verified": False, "has_connector": False,
        "notes": "Book dislocated ~20% above all other venues with broken ticker quotes; weak MD5 "
                 "request signing; withdrawal API not public and access restricted to 'qualified "
                 "users'. Unsafe microstructure.",
    },
    {
        "exchange": "btcc", "name": "BTCC", "bdag_pair": "BDAG/USDT",
        "india_access": "allowed", "kyc": "required",
        "api_surface": {"trade": False, "deposit_address": False, "deposit_monitor": False,
                        "withdraw": False, "websocket": False},
        "gates_default": {"deposit": "unverified", "withdraw": "unverified"},
        "audited": {"best_bid": None, "usd_2pct": None, "usd_5pct": None, "usd_10pct": None,
                    "book_total_usd": None, "vol_24h_usd": None, "vol_reliable": False},
        "est_spread_pct": None, "reliability": 0.30, "red_flags": ["no_public_spot_api"], "audit_score": 40,
        "operator_verified": False, "has_connector": False,
        "notes": "Derivatives-first exchange; no public spot REST API, no documented withdrawal "
                 "endpoint, spot probe DNS failed. Fine as a manual venue, not automatable.",
    },
    {
        "exchange": "azbit", "name": "Azbit", "bdag_pair": "BDAG/USDT",
        "india_access": "unknown", "kyc": "unknown",
        "api_surface": {"trade": True, "deposit_address": False, "deposit_monitor": False,
                        "withdraw": False, "websocket": False},
        "gates_default": {"deposit": "unverified", "withdraw": "unverified"},
        "audited": {"best_bid": 3.83e-05, "usd_2pct": 19, "usd_5pct": 38, "usd_10pct": 50,
                    "book_total_usd": 123, "vol_24h_usd": 26600, "vol_reliable": False},
        "est_spread_pct": None, "reliability": 0.20,
        "red_flags": ["dead_book", "withdrawal_api_unconfirmed"], "audit_score": 37,
        "operator_verified": False, "has_connector": False,
        "notes": "Effectively dead book ($123 total visible bid-side liquidity); withdrawal API "
                 "unconfirmed; withdrawal complaints in reviews. No economic reason to support.",
    },
    {
        "exchange": "bifinance", "name": "BiFinance", "bdag_pair": "BDAG/USDT",
        "india_access": "unknown", "kyc": "unknown",
        "api_surface": {"trade": False, "deposit_address": False, "deposit_monitor": False,
                        "withdraw": False, "websocket": False},
        "gates_default": {"deposit": "unverified", "withdraw": "unverified"},
        "audited": {"best_bid": None, "usd_2pct": None, "usd_5pct": None, "usd_10pct": None,
                    "book_total_usd": None, "vol_24h_usd": None, "vol_reliable": False},
        "est_spread_pct": None, "reliability": 0.05,
        "red_flags": ["no_api_docs", "listing_unconfirmable"], "audit_score": 22,
        "operator_verified": False, "has_connector": False,
        "notes": "No public API documentation found anywhere; probe DNS failed; BDAG listing not "
                 "programmatically confirmable. Fails every automation criterion.",
    },
]
CURATED_MAP = {c["exchange"]: c for c in CURATED}


def _api_availability(surface: dict) -> str:
    if not surface.get("trade"):
        return "none"
    if surface.get("deposit_address") and surface.get("deposit_monitor") and surface.get("withdraw"):
        return "full"
    if surface.get("deposit_address") or surface.get("deposit_monitor"):
        return "partial"
    return "trade_only"


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _depth_within(bids, pct):
    """USD bid-side depth within `pct`% of the best bid."""
    if not bids:
        return None
    best = bids[0][0]
    floor = best * (1 - pct / 100)
    return round(sum(p * q for p, q in bids if p >= floor), 2)


def _live_overlay(exchange: str) -> dict | None:
    """Scan the collector cache for any route carrying this venue's live book +
    deposit gate. Returns live best_bid / spread / depth / gate or None."""
    for rcache in collector.cache.values():
        m = rcache.get(exchange)
        if not m:
            continue
        ob = m.get("orderbook") or {}
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        if not bids:
            continue
        best_bid = bids[0][0]
        best_ask = asks[0][0] if asks else None
        spread_pct = (round((best_ask - best_bid) / best_bid * 100, 4)
                      if best_ask and best_bid else None)
        return {
            "best_bid": best_bid, "best_ask": best_ask, "spread_pct": spread_pct,
            "usd_2pct": _depth_within(bids, 2), "usd_5pct": _depth_within(bids, 5),
            "usd_10pct": _depth_within(bids, 10),
            "deposit_enabled": (m.get("fee") or {}).get("deposit_enabled"),
            "withdraw_enabled": (m.get("fee") or {}).get("withdraw_enabled"),
            "source": m.get("source"),
        }
    return None


async def _gate_status(exchange: str, curated: dict, live: dict | None) -> dict:
    """Resolve deposit/withdraw gate: live capability registry > live cache > curated."""
    cap = await db.capabilities_col.find_one({"exchange": exchange, "currency": "BDAG"}, {"_id": 0})
    default = curated["gates_default"]
    dep, wd, src = default["deposit"], default["withdraw"], "audit"
    if live and live.get("deposit_enabled") is not None:
        dep = "open" if live["deposit_enabled"] else "closed"
        wd = ("open" if live.get("withdraw_enabled") else "closed") if live.get("withdraw_enabled") is not None else wd
        src = "live"
    if cap:
        dep = "open" if cap.get("deposit_enabled") else "closed"
        wd = "open" if cap.get("withdraw_enabled") else "closed"
        src = "live_capability_registry"
    return {"deposit_status": dep, "withdraw_status": wd, "source": src}


_GATE_BASE = {"open": 1.0, "unverified": 0.5, "closed": 0.2, "suspended": 0.0}
_QUAL_RANK = {"verified": 0, "partial": 1, "pending": 2, "failed": 3}


async def _gate_reliability(exchange: str, gate_status: str, field: str, curated_reliability: float) -> int:
    """Reliability (0–100) for a deposit/withdraw gate: current status + 7-day flip
    history (capability registry) blended with the curated reliability baseline."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    flips = await db.capability_history.count_documents(
        {"exchange": exchange, "currency": "BDAG", "field": field, "ts": {"$gte": since}})
    base = _GATE_BASE.get(gate_status, 0.5)
    status_component = base * max(0.0, 1 - 0.1 * flips)
    return round(100 * (0.6 * status_component + 0.4 * curated_reliability))


def _qualification(c: dict, india: str, api_avail: str, dep_rel: int, wd_rel: int,
                   trust: int, operator_verified: bool) -> dict:
    def crit(name, status, value, detail):
        return {"criterion": name, "status": status, "value": value, "detail": detail}

    india_status = ("verified" if india == "verified" else "partial" if india == "allowed"
                    else "pending" if india in ("unverified", "unknown") else "failed")
    api_status = ("verified" if api_avail == "full" else "partial"
                  if api_avail in ("partial", "trade_only") else "failed")
    items = [
        crit("Manual Verification", "verified" if operator_verified else "pending",
             "operator-verified" if operator_verified else "not verified",
             "Operator has completed a manual end-to-end loop." if operator_verified
             else "Awaiting a manual verification loop."),
        crit("India Accessibility", india_status, india, "ToS / KYC / user-verified access."),
        crit("Deposit Reliability", "verified" if dep_rel >= 70 else "partial" if dep_rel >= 40 else "failed",
             dep_rel, "BDAG deposit gate status + flip history."),
        crit("Withdrawal Reliability", "verified" if wd_rel >= 70 else "partial" if wd_rel >= 40 else "failed",
             wd_rel, "BDAG withdrawal gate status + flip history."),
        crit("API Capability", api_status, api_avail, "Automation API surface (trade/deposit/withdraw)."),
        crit("Trust Score", "verified" if trust >= 70 else "partial" if trust >= 45 else "failed",
             trust, "Composite integrity/reliability score."),
    ]
    passed = sum(1 for i in items if i["status"] == "verified")
    return {"items": items, "verified": passed, "total": len(items),
            "qualification_pct": round(passed / len(items) * 100),
            "fully_qualified": all(i["status"] == "verified" for i in items)}


def _scores(c: dict, api_avail: str, dep: str, wd: str, best_bid, live_spread,
            usd5, vol, vol_reliable, buy_price):
    india_n = _INDIA_NUM.get(c["india_access"], 0.1)
    api_n = _API_NUM.get(api_avail, 0.0)
    gate_n = round((_GATE_NUM.get(dep, 0.4) + _GATE_NUM.get(wd, 0.4)) / 2, 3)
    critical = [f for f in c["red_flags"] if f in CRITICAL_FLAGS]

    # liquidity score: 60% sellable depth @5% (ref $1000), 40% reliable 24h vol (ref $50k)
    d5 = usd5 or 0
    v = vol if vol_reliable else 0
    liq = 0.6 * _clamp(d5 / 1000) + 0.4 * _clamp((v or 0) / 50000)
    liquidity_score = round(liq * 100)

    # spread score: 0% spread → 100, 5% → 0
    sp = live_spread if live_spread is not None else c.get("est_spread_pct")
    spread_score = round(max(0, 100 - sp * 20)) if sp is not None else None

    # trust score: accessibility + api + reliability + (1 - critical-flag penalty)
    no_flags = max(0.0, 1 - 0.25 * len(critical))
    trust = 0.25 * india_n + 0.30 * api_n + 0.25 * c["reliability"] + 0.20 * no_flags
    trust_score = round(trust * 100)

    # profit score: raw arbitrage edge vs cost basis (70%) + liquidity (30%)
    profit_score, edge_pct = None, None
    if best_bid and buy_price:
        edge_pct = round((best_bid - buy_price) / buy_price * 100, 2)
        edge_norm = _clamp(edge_pct / 30)
        profit_score = round((0.7 * edge_norm + 0.3 * liq) * 100)

    # executability score: can we actually run the loop today?
    verified_n = 1.0 if c["operator_verified"] else 0.5
    execu = (0.20 * india_n + 0.20 * api_n + 0.20 * gate_n
             + 0.15 * liq + 0.15 * (trust_score / 100) + 0.10 * verified_n)
    executability_score = round(execu * 100)

    return {
        "liquidity_score": liquidity_score, "spread_score": spread_score,
        "trust_score": trust_score, "profit_score": profit_score, "edge_pct": edge_pct,
        "executability_score": executability_score, "critical_flags": critical,
    }


def _classify(c: dict, override: str | None, execution_approved: bool, critical: list) -> tuple:
    if override in ("execution_approved", "monitor_only", "disabled"):
        return override, "operator override"
    if execution_approved:
        return "execution_approved", "operator-verified + full API + gates open + accessible"
    if critical:
        return "disabled", f"disqualifying flag(s): {', '.join(critical)}"
    return "monitor_only", "tracked & ranked; not executable until verified"


async def _build_one(persisted: dict, buy_price: float | None) -> dict:
    ex = persisted["exchange"]
    c = CURATED_MAP[ex]
    operator_verified = bool(persisted.get("operator_verified", c["operator_verified"]))
    override = persisted.get("status_override")

    api_avail = _api_availability(c["api_surface"])
    live = _live_overlay(ex) if c["has_connector"] else None
    gates = await _gate_status(ex, c, live)
    dep, wd = gates["deposit_status"], gates["withdraw_status"]

    aud = c["audited"]
    best_bid = (live or {}).get("best_bid") if live else aud["best_bid"]
    live_spread = (live or {}).get("spread_pct") if live else None
    usd2 = (live or {}).get("usd_2pct") if live else aud["usd_2pct"]
    usd5 = (live or {}).get("usd_5pct") if live else aud["usd_5pct"]
    usd10 = (live or {}).get("usd_10pct") if live else aud["usd_10pct"]
    vol, vol_reliable = aud["vol_24h_usd"], aud["vol_reliable"]
    data_source = "live" if live else "audit"

    sc = _scores(c, api_avail, dep, wd, best_bid, live_spread, usd5, vol, vol_reliable, buy_price)

    execution_approved = bool(
        operator_verified and api_avail == "full" and dep == "open" and wd == "open"
        and c["india_access"] in ("verified", "allowed") and not sc["critical_flags"])
    status, status_reason = _classify(c, override, execution_approved, sc["critical_flags"])

    dep_rel = await _gate_reliability(ex, dep, "deposit_enabled", c["reliability"])
    wd_rel = await _gate_reliability(ex, wd, "withdraw_enabled", c["reliability"])
    qualification = _qualification(c, c["india_access"], api_avail, dep_rel, wd_rel,
                                   sc["trust_score"], operator_verified)

    last_verified = now_iso() if live else AUDIT_DATE
    return {
        "exchange": ex, "name": c["name"], "bdag_pair": c["bdag_pair"],
        "india_accessibility": c["india_access"], "api_availability": api_avail,
        "api_surface": c["api_surface"], "kyc_requirement": c["kyc"],
        "deposit_status": dep, "withdrawal_status": wd, "gate_source": gates["source"],
        "best_bid": best_bid, "spread_pct": live_spread if live_spread is not None else c.get("est_spread_pct"),
        "liquidity_usd": {"depth_2pct": usd2, "depth_5pct": usd5, "depth_10pct": usd10,
                          "book_total_usd": aud["book_total_usd"]},
        "vol_24h_usd": vol, "vol_reliable": vol_reliable,
        "liquidity_score": sc["liquidity_score"], "spread_score": sc["spread_score"],
        "trust_score": sc["trust_score"], "profit_score": sc["profit_score"],
        "edge_pct": sc["edge_pct"], "executability_score": sc["executability_score"],
        "deposit_reliability": dep_rel, "withdrawal_reliability": wd_rel,
        "qualification": qualification,
        "execution_approved": execution_approved, "operator_verified": operator_verified,
        "status": status, "status_reason": status_reason,
        "red_flags": c["red_flags"], "critical_flags": sc["critical_flags"],
        "audit_score": c["audit_score"], "data_source": data_source,
        "has_connector": c["has_connector"], "last_verified": last_verified,
        "notes": c["notes"],
    }


# ---------------------------------------------------------------------------
# persistence + public API
# ---------------------------------------------------------------------------
async def ensure_seeded():
    for c in CURATED:
        existing = await db.exchange_intelligence.find_one({"exchange": c["exchange"]})
        if not existing:
            await db.exchange_intelligence.insert_one({
                "exchange": c["exchange"], "operator_verified": c["operator_verified"],
                "status_override": None, "created_at": now_iso(), "updated_at": now_iso()})


async def _buy_price_basis() -> dict:
    route = await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0})
    if not route:
        return {"price": None, "source": None, "source_label": None}
    res = await bp_resolver.resolve(route)
    return {"price": res["price"], "source": res["source"], "source_label": res["source_label"],
            "timestamp": res["timestamp"], "route_id": route["id"], "route_name": route.get("name")}


async def registry() -> dict:
    basis = await _buy_price_basis()
    persisted = await db.exchange_intelligence.find({}, {"_id": 0}).to_list(100)
    pmap = {p["exchange"]: p for p in persisted}
    records = []
    for c in CURATED:
        rec = await _build_one(pmap.get(c["exchange"], {"exchange": c["exchange"]}), basis["price"])
        records.append(rec)

    records.sort(key=lambda r: -r["executability_score"])
    buckets = {"execution_approved": [], "monitor_only": [], "disabled": []}
    for r in records:
        buckets[r["status"]].append(r["name"])

    best_profit = sorted(
        [r for r in records if r["profit_score"] is not None],
        key=lambda r: -r["profit_score"])
    best_executable = sorted(records, key=lambda r: -r["executability_score"])

    return {
        "phase": "Exchange Intelligence Registry & Ranking (read-only, non-executing)",
        "generated_at": now_iso(), "audit_baseline": AUDIT_DOC,
        "buy_price_basis": basis,
        "exchanges": records,
        "classification": buckets,
        "counts": {
            "total": len(records),
            "execution_approved": len(buckets["execution_approved"]),
            "monitor_only": len(buckets["monitor_only"]),
            "disabled": len(buckets["disabled"]),
            "live_overlay": sum(1 for r in records if r["data_source"] == "live"),
        },
        "rankings": {
            "best_profit": [_rank_row(r, "profit") for r in best_profit],
            "best_executable": [_rank_row(r, "executable") for r in best_executable],
        },
        "note": "Read-only intelligence. Highest profit ≠ best executable. Coinstore remains the "
                "sole execution-approved candidate; all others are monitor-only or disabled until "
                "accessibility / KYC / deposit+withdraw gates / API readiness are verified. NO "
                "execution, no orders, no fund movement.",
    }


def _rank_row(r: dict, kind: str) -> dict:
    base = {
        "exchange": r["exchange"], "name": r["name"], "status": r["status"],
        "liquidity_score": r["liquidity_score"], "trust_score": r["trust_score"],
        "executability_score": r["executability_score"], "profit_score": r["profit_score"],
        "best_bid": r["best_bid"], "edge_pct": r["edge_pct"],
        "deposit_status": r["deposit_status"], "withdrawal_status": r["withdrawal_status"],
        "api_availability": r["api_availability"], "india_accessibility": r["india_accessibility"],
        "data_source": r["data_source"],
    }
    return base


async def get_one(exchange: str) -> dict | None:
    ex = (exchange or "").lower()
    if ex not in CURATED_MAP:
        return None
    basis = await _buy_price_basis()
    persisted = await db.exchange_intelligence.find_one({"exchange": ex}, {"_id": 0}) or {"exchange": ex}
    return await _build_one(persisted, basis["price"])


async def update_one(exchange: str, operator_verified: bool | None,
                     status_override: str | None) -> dict | None:
    ex = (exchange or "").lower()
    if ex not in CURATED_MAP:
        return None
    if status_override is not None and status_override not in (
            "execution_approved", "monitor_only", "disabled", "auto"):
        raise ValueError("status_override must be execution_approved|monitor_only|disabled|auto")
    patch = {"updated_at": now_iso()}
    if operator_verified is not None:
        patch["operator_verified"] = bool(operator_verified)
    if status_override is not None:
        patch["status_override"] = None if status_override == "auto" else status_override
    await db.exchange_intelligence.update_one(
        {"exchange": ex}, {"$set": patch,
                           "$setOnInsert": {"exchange": ex, "created_at": now_iso()}}, upsert=True)
    return await get_one(ex)


async def assessment() -> dict:
    reg = await registry()
    recs = reg["exchanges"]

    detected = [{"exchange": r["exchange"], "name": r["name"], "bdag_pair": r["bdag_pair"],
                 "status": r["status"], "audit_score": r["audit_score"],
                 "data_source": r["data_source"], "has_connector": r["has_connector"]}
                for r in sorted(recs, key=lambda r: -r["audit_score"])]

    accessibility = [{"exchange": r["exchange"], "name": r["name"],
                      "india_accessibility": r["india_accessibility"], "kyc_requirement": r["kyc_requirement"],
                      "deposit_status": r["deposit_status"], "withdrawal_status": r["withdrawal_status"],
                      "api_availability": r["api_availability"], "gate_source": r["gate_source"]}
                     for r in recs]

    liquidity = sorted(
        [{"exchange": r["exchange"], "name": r["name"], "best_bid": r["best_bid"],
          "depth_5pct_usd": r["liquidity_usd"]["depth_5pct"],
          "depth_10pct_usd": r["liquidity_usd"]["depth_10pct"],
          "vol_24h_usd": r["vol_24h_usd"], "vol_reliable": r["vol_reliable"],
          "liquidity_score": r["liquidity_score"], "spread_score": r["spread_score"],
          "data_source": r["data_source"]}
         for r in recs], key=lambda x: -(x["liquidity_score"] or 0))

    suitability = reg["rankings"]["best_executable"]

    production = [
        {"rank": 1, "tier": "PRIMARY (execution-approved)",
         "exchanges": reg["classification"]["execution_approved"],
         "rationale": "User-verified India loop + complete documented API + verified-address withdrawal."},
        {"rank": 2, "tier": "MONITOR / PROMOTION CANDIDATES",
         "exchanges": [r["name"] for r in recs if r["status"] == "monitor_only"],
         "rationale": "Real tradable BDAG market and viable API, but require accessibility / gate / "
                      "manual-loop verification before any execution. BitMart is the strongest "
                      "promotion candidate (deepest book, both gates open)."},
        {"rank": 3, "tier": "DISABLED (not viable)",
         "exchanges": [r["name"] for r in recs if r["status"] == "disabled"],
         "rationale": "Hard blockers: no public API, fake/dead liquidity, dislocated market, or "
                      "suspended BDAG pair. Tracked for awareness only."},
    ]

    return {
        "phase": "Exchange Suitability Assessment (read-only)",
        "generated_at": reg["generated_at"], "buy_price_basis": reg["buy_price_basis"],
        "counts": reg["counts"],
        "section_1_detected_exchanges": detected,
        "section_2_accessibility_assessment": accessibility,
        "section_3_liquidity_comparison": liquidity,
        "section_4_execution_suitability_ranking": suitability,
        "section_5_recommended_production_ranking": production,
        "headline": ("Best PROFIT venue and best EXECUTABLE venue differ: "
                     f"profit leader = {reg['rankings']['best_profit'][0]['name'] if reg['rankings']['best_profit'] else 'n/a'}, "
                     f"execution leader = {reg['rankings']['best_executable'][0]['name']}. "
                     "ArbiCore prioritizes the executable ranking."),
        "note": reg["note"],
    }
