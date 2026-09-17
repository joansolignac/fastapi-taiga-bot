from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.taiga.services.due_date_reminder_service import (
    TaigaDueDateReminderService,
    get_taiga_due_date_reminder_service,
)
from fastapi_taiga_bot.telegram.callbacks.base import TelegramCallback
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate


class DueDateMoreTimeCallback(TelegramCallback):
    data = "due:more_time"

    def __init__(self, reminder_service: TaigaDueDateReminderService, session: AsyncSession):
        self._reminder_service = reminder_service
        self._session = session

    async def handle(self, update: TelegramUpdate) -> None:
        message = update.callback_query.message
        await self._reminder_service.respond(
            self._session, message.chat.id, message.message_id, "needs_more_time"
        )


def get_due_date_more_time_callback(
    reminder_service: TaigaDueDateReminderService = Depends(get_taiga_due_date_reminder_service),
    session: AsyncSession = Depends(get_session),
) -> DueDateMoreTimeCallback:
    return DueDateMoreTimeCallback(reminder_service, session)
