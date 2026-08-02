"""Phase 10.3 · Telegram alerts — activation of the canonical service.

Faithful port of the canonical ``services/telegram_alerts.py`` from
``arbicore-x-v1.0.2.bundle``, adapted to the current backend's runtime:

    * Configuration lives in the ``arbicore_config`` collection under
      kind ``telegram_alerts`` (Draft / Apply / Rollback via
      :class:`ConfigRepo`), NOT in a bespoke ``settings`` collection.
    * Bot token is Fernet-wrapped via the existing :class:`SecretRegistry`
      instead of the canonical bundle's inline ``vault.encrypt`` helper,
      so we don't duplicate crypto.
    * Alert history lives in a dedicated ``telegram_alerts_log`` collection.

Design constraints preserved from the canonical version:
    * OUTBOUND-ONLY — no webhooks, no inbound commands.
    * Plain-text messages (avoid MarkdownV2 escaping pitfalls).
    * Per-kind cooldown prevents alert storms.
    * ``get_settings(redact=True)`` NEVER returns the plaintext token.
    * ``send_test()`` requires a configured token + chat.
    * All raise-worthy errors are logged and swallowed — an alerting
      failure MUST NEVER crash a broadcast pipeline.

Ships DORMANT: `enabled=False`, no token, no chat — the operator
provisions from the UI. Send loop runs only when `enabled and token and chat_id`.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config.persistent import ConfigRepo


logger = logging.getLogger("arbicore.telegram")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


TELEGRAM_KIND = "telegram_alerts"
LOG_COLLECTION = "telegram_alerts_log"

# Rules matrix mirrored from the canonical bundle's DEFAULT_RULES.
DEFAULT_RULES: Dict[str, Any] = {
    # Verdict / mode transitions
    "verdict_flip": True,
    "capability_flip": True,
    "mode_flip": True,
    # Opportunity lifecycle
    "go_opportunity": True,
    "go_opened": True,
    "go_closed": True,
    "min_net_spread_pct": 2.0,
    # Venue / capability changes
    "venue_qualification_changed": True,
    "deposit_gate_changed": True,
    "withdrawal_gate_changed": True,
    # Execution
    "cycle_stuck": True,
    "cycle_manual_review": True,
    "daily_loss_kill": True,
    # LIMITED_LIVE lifecycle (new — Phase 8/9)
    "kill_switch_engaged": True,
    "kill_switch_disengaged": True,
    "first_broadcast": True,
    "broadcast_sent": True,
    "capital_denied": True,
    "executor_verified": True,
    # Cooldowns
    "cooldown_s": 300,
}

DEFAULT_TELEGRAM_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "chat_id": "",
    "token_handle_id": "",       # points into arbicore_secrets
    "token_mask": "",            # cached mask so we can render without decrypt
    "rules": dict(DEFAULT_RULES),
    "updated_at": None,
    "updated_by": None,
}


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return token[:2] + "…"
    return token[:4] + "…" + token[-4:]


class TelegramAlertService:
    """Read-write facade around the Telegram-alerts config + log."""

    def __init__(self, db, *, config_repo: ConfigRepo, secret_registry):
        self._db = db
        self._log = db[LOG_COLLECTION]
        self._cfg = config_repo
        self._secrets = secret_registry
        # In-process per-kind cooldown ledger.  Restarts reset — that's
        # the correct behaviour (a restart is itself a legitimate signal
        # to re-notify).
        self._last_sent: Dict[str, float] = {}
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._log.create_index([("kind", 1), ("at", -1)])
        self._indexes_ready = True

    async def ensure_seeded(self) -> Dict[str, Any]:
        current = await self._cfg.get_current(TELEGRAM_KIND, default={})
        if current:
            return current
        await self._cfg.apply(TELEGRAM_KIND,
                               patch=dict(DEFAULT_TELEGRAM_CONFIG),
                               actor="system:boot",
                               reason="seed defaults for telegram_alerts")
        return await self._cfg.get_current(TELEGRAM_KIND,
                                            default=DEFAULT_TELEGRAM_CONFIG)

    # -----------------------------------------------------------------
    # settings
    # -----------------------------------------------------------------

    async def get_settings(self, *, redact: bool = True) -> Dict[str, Any]:
        cfg = await self._cfg.get_current(TELEGRAM_KIND,
                                            default=DEFAULT_TELEGRAM_CONFIG)
        out = {
            "enabled":    bool(cfg.get("enabled")),
            "chat_id":    cfg.get("chat_id") or "",
            "rules":      {**DEFAULT_RULES, **(cfg.get("rules") or {})},
            "token_set":  bool(cfg.get("token_handle_id")),
            "token_mask": cfg.get("token_mask") or "",
            "updated_at": cfg.get("updated_at"),
            "updated_by": cfg.get("updated_by"),
        }
        # Never expose plaintext.
        return out

    async def save_settings(self, *, enabled: Optional[bool] = None,
                             chat_id: Optional[str] = None,
                             rules: Optional[Dict[str, Any]] = None,
                             bot_token: Optional[str] = None,
                             actor: str = "operator",
                             reason: str = "") -> Dict[str, Any]:
        """Update Telegram alert configuration.

        ``bot_token`` — if provided, is Fernet-wrapped and its handle
        stored in the config document. Passing ``bot_token=None`` (the
        default) leaves the current token untouched.
        """
        patch: Dict[str, Any] = {}
        if enabled is not None:
            patch["enabled"] = bool(enabled)
        if chat_id is not None:
            patch["chat_id"] = str(chat_id).strip()
        if rules is not None:
            patch["rules"] = {**DEFAULT_RULES, **(rules or {})}
        if bot_token:
            handle = await self._secrets.put(
                bot_token.encode("utf-8"),
                scope="custom",
                algorithm="telegram_bot_token",
                label="telegram_bot_token",
            )
            # Best-effort: drop the previous handle if any (non-fatal).
            prev = (await self._cfg.get_current(TELEGRAM_KIND, default={})).get("token_handle_id")
            if prev and prev != handle.handle_id:
                try:
                    await self._secrets.delete(prev)
                except Exception:  # noqa: BLE001
                    pass
            patch["token_handle_id"] = handle.handle_id
            patch["token_mask"] = _mask_token(bot_token)
        if not patch:
            return await self.get_settings()
        await self._cfg.apply(TELEGRAM_KIND, patch=patch,
                                actor=actor, reason=reason or "operator update")
        return await self.get_settings()

    async def _resolve_token(self) -> Optional[str]:
        cfg = await self._cfg.get_current(TELEGRAM_KIND, default={})
        handle = cfg.get("token_handle_id") or ""
        if not handle:
            return None
        try:
            plaintext = await self._secrets.resolve(handle)
            if plaintext:
                return plaintext.decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram token resolve failed: %s", exc)
        return None

    # -----------------------------------------------------------------
    # send
    # -----------------------------------------------------------------

    def _cooldown_ok(self, kind: str, cooldown_s: float) -> bool:
        last = self._last_sent.get(kind, 0.0)
        return (time.monotonic() - last) >= cooldown_s

    async def send_test(self, *, actor: str = "operator") -> Dict[str, Any]:
        """Send a plain hello — used by the UI to verify the config."""
        return await self._send(kind="test",
                                 text=f"ArbiCore X — Telegram alerts test @ {_iso_now()}",
                                 force=True, actor=actor)

    async def emit(self, *, kind: str, text: str,
                    payload: Optional[Dict[str, Any]] = None,
                    actor: str = "system") -> Dict[str, Any]:
        """Emit an alert of ``kind``. Respects per-kind cooldown + rules."""
        settings = await self.get_settings()
        if not settings["enabled"]:
            return {"sent": False, "reason": "telegram alerts disabled"}
        rules = settings["rules"]
        if not rules.get(kind, True):
            return {"sent": False, "reason": f"rule '{kind}' disabled"}
        cooldown_s = float(rules.get("cooldown_s") or 300)
        if not self._cooldown_ok(kind, cooldown_s):
            return {"sent": False, "reason": f"cooldown active ({cooldown_s}s)"}
        return await self._send(kind=kind, text=text, payload=payload, actor=actor)

    async def _send(self, *, kind: str, text: str,
                     payload: Optional[Dict[str, Any]] = None,
                     force: bool = False,
                     actor: str = "system") -> Dict[str, Any]:
        await self.ensure_indexes()
        cfg = await self._cfg.get_current(TELEGRAM_KIND, default={})
        chat_id = (cfg.get("chat_id") or "").strip()
        token = await self._resolve_token()
        if not chat_id or not token:
            entry = {
                "kind": kind, "at": _iso_now(), "text": text,
                "sent": False, "error": "chat_id or bot token missing",
                "payload": payload or {}, "actor": actor,
            }
            await self._log.insert_one(entry)
            return {"sent": False, "reason": entry["error"]}

        # Import lazily so the runtime dependency is optional at boot.
        try:
            import httpx  # local import — never at module top
        except Exception as exc:
            entry = {"kind": kind, "at": _iso_now(), "text": text,
                     "sent": False, "error": f"httpx unavailable: {exc}",
                     "payload": payload or {}, "actor": actor}
            await self._log.insert_one(entry)
            return {"sent": False, "reason": entry["error"]}

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = {"chat_id": chat_id, "text": text}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=body)
            ok = resp.status_code == 200 and resp.json().get("ok") is True
            entry = {"kind": kind, "at": _iso_now(), "text": text,
                      "sent": ok, "http_status": resp.status_code,
                      "response": resp.json() if ok else resp.text[:200],
                      "payload": payload or {}, "actor": actor}
        except Exception as exc:  # noqa: BLE001
            entry = {"kind": kind, "at": _iso_now(), "text": text,
                     "sent": False, "error": f"send failed: {exc}",
                     "payload": payload or {}, "actor": actor}
        await self._log.insert_one(entry)
        if entry["sent"]:
            self._last_sent[kind] = time.monotonic()
        return {"sent": entry["sent"],
                 "reason": entry.get("error") or "ok",
                 "http_status": entry.get("http_status")}

    # -----------------------------------------------------------------
    # log
    # -----------------------------------------------------------------

    async def history(self, *, limit: int = 50,
                       kind: Optional[str] = None) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if kind:
            q["kind"] = kind
        cur = self._log.find(q, {"_id": 0}).sort("at", -1).limit(limit)
        return await cur.to_list(limit)
