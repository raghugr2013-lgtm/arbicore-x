"""Telegram alerting endpoints — settings, test message, alert log."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from services import db
from services.auth import require_auth
from services.telegram_alerts import telegram_alerts

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(require_auth)])


class AlertSettingsBody(BaseModel):
    enabled: bool = False
    chat_id: str = ""
    bot_token: Optional[str] = None  # only sent when (re)setting the token
    rules: Optional[dict] = None


@router.get("/settings")
async def get_settings():
    return await telegram_alerts.get_settings()


@router.put("/settings")
async def save_settings(body: AlertSettingsBody):
    return await telegram_alerts.save_settings(
        body.enabled, body.chat_id, body.rules,
        body.bot_token if body.bot_token else None)


@router.post("/test")
async def send_test():
    return await telegram_alerts.send_test()


@router.get("/log")
async def alert_log(limit: int = 50):
    return await db.alerts_log.find({}, {"_id": 0}, sort=[("ts", -1)]).to_list(min(limit, 200))
