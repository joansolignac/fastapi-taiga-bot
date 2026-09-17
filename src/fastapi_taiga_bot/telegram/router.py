from fastapi import APIRouter, Depends

from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.dispatcher import CommandDispatcher, get_dispatcher
from fastapi_taiga_bot.telegram.security import verify_telegram_webhook_secret

router = APIRouter(
    prefix="/telegram",
    tags=["telegram"],
    dependencies=[Depends(verify_telegram_webhook_secret)],
)

@router.post("/webhook")
async def telegram_webhook(
    update: TelegramUpdate,
    dispatcher: CommandDispatcher = Depends(get_dispatcher)
    ) -> dict:
    await dispatcher.dispatch(update)
    return { "ok": True }