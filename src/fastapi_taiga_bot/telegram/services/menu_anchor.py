import httpx
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.telegram.client import TelegramClient
from fastapi_taiga_bot.telegram.models import TelegramMenuAnchor
from fastapi_taiga_bot.telegram.services.menu_content import MenuContentService
from fastapi_taiga_bot.telegram.services.message_log import log_message


async def refresh_menu_anchor(
    session: AsyncSession,
    client: TelegramClient,
    menu_content: MenuContentService,
    chat_id: int,
    is_logged_in: bool,
    display_name: str | None = None,
) -> None:
    """Deletes the previous anchor message (if any) and sends a fresh root
    menu, so it becomes the newest message in the chat. Call this only from
    push-notification-triggered flows (webhook processing, due-date cron
    batches) — never from user-initiated flows, which are already the
    newest message by virtue of being a direct response to the user's own
    action and should call `upsert_menu_anchor` instead."""
    anchor = await session.get(TelegramMenuAnchor, chat_id)
    if anchor is not None:
        try:
            await client.delete_message(chat_id, anchor.message_id)
        except httpx.HTTPStatusError:
            pass  # Already gone, or too old to delete.

    menu = menu_content.build_root_menu(is_logged_in, display_name)
    message_id = await client.send_message(chat_id, menu["text"], menu["reply_markup"])
    await log_message(session, chat_id, message_id)
    await upsert_menu_anchor(session, chat_id, message_id)


async def upsert_menu_anchor(session: AsyncSession, chat_id: int, message_id: int) -> None:
    anchor = await session.get(TelegramMenuAnchor, chat_id)
    if anchor is not None:
        anchor.message_id = message_id
        session.add(anchor)
    else:
        session.add(TelegramMenuAnchor(chat_id=chat_id, message_id=message_id))
    await session.commit()
