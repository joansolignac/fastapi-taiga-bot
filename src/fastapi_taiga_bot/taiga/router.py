from fastapi import APIRouter, Body, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.taiga.security import verify_taiga_webhook_secret
from fastapi_taiga_bot.taiga.services.webhook_notification_service import (
    TaigaWebhookNotificationService,
    get_taiga_webhook_notification_service,
)

router = APIRouter(
    prefix="/taiga",
    tags=["taiga"],
    dependencies=[Depends(verify_taiga_webhook_secret)],
)

@router.post("/webhook")
async def taiga_webhook(
    payload: dict = Body(...),
    notification_service: TaigaWebhookNotificationService = Depends(get_taiga_webhook_notification_service),
    session: AsyncSession = Depends(get_session),
    ) -> dict:
    await notification_service.process(session, payload)
    return { "ok": True }
