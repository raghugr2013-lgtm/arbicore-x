"""Fresh-Cycle Watch — alert framework status surface (DORMANT).

The watcher itself is the existing Opportunity Gate Monitor + the Telegram alert
service. Both are already wired:
  • Opportunity Gate Monitor fires `go_opened` / `go_closed` /
    `venue_qualification_changed` / `deposit_gate_changed` / `withdrawal_gate_changed`
    on every tick — these ARE the fresh-cycle GO transitions because the gate
    runs on the live Fresh-Cycle ROI (swap-price authoritative path).
  • TelegramAlertService is dormant until the operator stores a Bot Token + Chat
    ID via Settings → Telegram. With no credentials, every `notify()` short-circuits
    silently and logs nothing outbound.

This module just exposes a single READ-ONLY status payload the UI can render:
  – credential state (Awaiting Telegram Credentials / Configured)
  – which alert kinds will fire when armed
  – the recent alert log (sent / failed / no-op)

No execution, no sends. Pure visibility.
"""
from core.models import now_iso
from services import db
from services.telegram_alerts import DEFAULT_RULES, telegram_alerts

FRESH_CYCLE_ALERT_KINDS = [
    {"key": "go_opened", "label": "Fresh-cycle GO window OPENED",
     "trigger": "Live Swap → Coinstore bid clears the floor with stable depth and fresh data"},
    {"key": "go_closed", "label": "Fresh-cycle GO window CLOSED",
     "trigger": "Any gate condition fails (ROI fell, depth disappeared, venue de-qualified, data went stale)"},
    {"key": "venue_qualification_changed", "label": "Venue qualification flipped",
     "trigger": "Exchange Intelligence Registry status changed (e.g. → disabled)"},
    {"key": "deposit_gate_changed", "label": "Deposit gate flipped",
     "trigger": "BDAG deposit status changed on the sell venue"},
    {"key": "withdrawal_gate_changed", "label": "Withdrawal gate flipped",
     "trigger": "USDT withdrawal status changed on the sell venue"},
]


async def status() -> dict:
    s = await telegram_alerts.get_settings(redact=True)
    token_set = bool(s.get("token_set"))
    chat_set = bool(s.get("chat_id"))
    armed = bool(s.get("enabled") and token_set and chat_set)
    rules = s.get("rules") or DEFAULT_RULES

    if armed:
        state = "ARMED"
        state_label = "Telegram channel ARMED — alerts will fire on transitions"
    elif token_set or chat_set:
        state = "PARTIAL"
        state_label = ("Awaiting Telegram Credentials — "
                       + ("token missing" if not token_set else "chat ID missing"))
    else:
        state = "DORMANT"
        state_label = "Awaiting Telegram Credentials (Bot Token + Chat ID)"

    recent = await db.alerts_log.find(
        {"kind": {"$in": [k["key"] for k in FRESH_CYCLE_ALERT_KINDS] + ["test"]}},
        {"_id": 0}, sort=[("ts", -1)]).to_list(40)

    kinds = []
    for k in FRESH_CYCLE_ALERT_KINDS:
        enabled = rules.get(k["key"], True)
        kinds.append({**k, "enabled": bool(enabled),
                      "min_net_spread_pct": rules.get("min_net_spread_pct"),
                      "cooldown_s": rules.get("cooldown_s")})

    return {
        "phase": "Fresh-Cycle Watch (alert framework, read-only)",
        "credential_state": state,
        "credential_state_label": state_label,
        "token_set": token_set,
        "token_mask": s.get("token_mask"),
        "chat_id_set": chat_set,
        "alerts_enabled": bool(s.get("enabled")),
        "alert_kinds": kinds,
        "rules": {"min_net_spread_pct": rules.get("min_net_spread_pct"),
                  "cooldown_s": rules.get("cooldown_s")},
        "recent_alerts": recent,
        "recent_count": len(recent),
        "note": ("Telegram is fully DORMANT until a Bot Token AND Chat ID are supplied via "
                 "Settings → Telegram. Every notify() short-circuits silently while dormant. "
                 "No sends, no inbound webhooks, no execution."),
        "generated_at": now_iso(),
    }
