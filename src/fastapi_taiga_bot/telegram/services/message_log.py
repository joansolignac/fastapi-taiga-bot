import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.taiga.models import (
    TaigaAssignmentNotification,
    TaigaDueDateReminder,
    TaigaStatusNotification,
)
from fastapi_taiga_bot.telegram.client import TelegramClient
from fastapi_taiga_bot.telegram.models import TelegramMenuAnchor, TelegramMessageLog


async def log_message(session: AsyncSession, chat_id: int, message_id: int) -> None:
    session.add(TelegramMessageLog(chat_id=chat_id, message_id=message_id))
    await session.commit()


async def clear_chat_history(session: AsyncSession, client: TelegramClient, chat_id: int) -> None:
    logged = (
        await session.exec(select(TelegramMessageLog).where(TelegramMessageLog.chat_id == chat_id))
    ).all()
    assignments = (
        await session.exec(
            select(TaigaAssignmentNotification).where(TaigaAssignmentNotification.chat_id == chat_id)
        )
    ).all()
    status_notifications = (
        await session.exec(
            select(TaigaStatusNotification).where(TaigaStatusNotification.chat_id == chat_id)
        )
    ).all()
    reminders = (
        await session.exec(select(TaigaDueDateReminder).where(TaigaDueDateReminder.chat_id == chat_id))
    ).all()

    message_ids = {
        row.message_id for row in (*logged, *assignments, *status_notifications, *reminders)
    }

    for message_id in message_ids:
        try:
            await client.delete_message(chat_id, message_id)
        except httpx.HTTPStatusError:
            pass  # Too old to delete, or already gone — keep clearing the rest.

    for row in (*logged, *assignments, *status_notifications, *reminders):
        await session.delete(row)

    anchor = await session.get(TelegramMenuAnchor, chat_id)
    if anchor is not None:
        await session.delete(anchor)  # Its message is already covered by `logged` above.

    await session.commit()
