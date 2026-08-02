"""Telegram alerting — DORMANT by design until the user enables it and provides
a Bot Token + Chat ID via dashboard settings (stored encrypted in MongoDB).
Outbound-only: no webhooks, no inbound commands. Plain-text messages (no
MarkdownV2 escaping pitfalls). Per-kind cooldown prevents alert storms."""
import logging
import time

from telegram import Bot

from core.models import new_id, now_iso
from services import db
from services.vault import decrypt, encrypt, mask

logger = logging.getLogger("telegram")

DEFAULT_RULES = {
    "verdict_flip": True,        # GO/WAIT/NO_GO transitions
    "capability_flip": True,     # deposit/withdraw gate flips
    "go_opportunity": True,      # GO verdict with net spread above threshold
    "go_opened": True,           # E4.7 — opportunity GO window opened
    "go_closed": True,           # E4.7 — opportunity GO window closed
    "venue_qualification_changed": True,  # E4.7 — venue qualification status changed
    "deposit_gate_changed": True,         # E4.7 — venue deposit gate flipped
    "withdrawal_gate_changed": True,      # E4.7 — venue withdrawal gate flipped
    "cycle_stuck": True,         # E2 — execution cycle stuck past SLA (SIMULATED)
    "cycle_manual_review": True, # E2 — execution cycle moved to MANUAL_REVIEW (SIMULATED)
    "daily_loss_kill": True,     # E2/E3 — daily-loss cap tripped the kill switch
    "min_net_spread_pct": 2.0,
    "cooldown_s": 300,
}


class TelegramAlertService:
    def __init__(self):
        self._last_sent = {}  # kind -> monotonic timestamp

    async def get_settings(self, redact: bool = True) -> dict:
        doc = await db.settings_col.find_one({"key": "telegram"}, {"_id": 0}) or {}
        rules = {**DEFAULT_RULES, **(doc.get("rules") or {})}
        out = {"enabled": bool(doc.get("enabled")), "chat_id": doc.get("chat_id") or "",
               "rules": rules, "updated_at": doc.get("updated_at"),
               "token_set": bool(doc.get("bot_token_enc")),
               "token_mask": mask(decrypt(doc["bot_token_enc"])) if doc.get("bot_token_enc") else None}
        if not redact and doc.get("bot_token_enc"):
            out["bot_token"] = decrypt(doc["bot_token_enc"])
        return out

    async def save_settings(self, enabled: bool, chat_id: str, rules: dict = None,
                            bot_token: str = None) -> dict:
        update = {"key": "telegram", "enabled": enabled, "chat_id": (chat_id or "").strip(),
                  "rules": {**DEFAULT_RULES, **(rules or {})}, "updated_at": now_iso()}
        if bot_token:  # token only overwritten when a new one is provided
            update["bot_token_enc"] = encrypt(bot_token.strip())
        await db.settings_col.update_one({"key": "telegram"}, {"$set": update}, upsert=True)
        return await self.get_settings()

    async def _send(self, token: str, chat_id: str, text: str):
        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=text)

    async def _log(self, kind, message, status, error=None):
        try:
            await db.alerts_log.insert_one({"id": new_id(), "ts": now_iso(), "created_at": now_iso(),
                                            "kind": kind, "message": message, "status": status,
                                            "error": error})
        except Exception:
            pass

    async def send_test(self) -> dict:
        s = await self.get_settings(redact=False)
        if not s.get("bot_token") or not s["chat_id"]:
            return {"ok": False, "message": "Bot token and chat ID must be configured first"}
        try:
            await self._send(s["bot_token"], s["chat_id"],
                             "✅ ArbiCore test alert — Telegram channel is wired correctly.")
            await self._log("test", "test alert", "sent")
            return {"ok": True, "message": "Test message delivered"}
        except Exception as e:
            await self._log("test", "test alert", "failed", str(e)[:200])
            return {"ok": False, "message": str(e)[:200]}

    async def notify(self, kind: str, message: str, net_pct: float = None) -> bool:
        """Fire-and-forget alert. Silently no-ops while dormant. Never raises."""
        try:
            s = await self.get_settings(redact=False)
            if not s["enabled"] or not s.get("bot_token") or not s["chat_id"]:
                return False
            rules = s["rules"]
            if rules.get(kind) is False:
                return False
            if kind == "go_opportunity" and net_pct is not None and \
                    net_pct < rules.get("min_net_spread_pct", 2.0):
                return False
            now = time.monotonic()
            if now - self._last_sent.get(kind, -1e9) < rules.get("cooldown_s", 300):
                return False
            self._last_sent[kind] = now
            await self._send(s["bot_token"], s["chat_id"], message)
            await self._log(kind, message, "sent")
            return True
        except Exception as e:
            logger.warning("telegram notify failed: %s", e)
            await self._log(kind, message, "failed", str(e)[:200])
            return False


telegram_alerts = TelegramAlertService()
