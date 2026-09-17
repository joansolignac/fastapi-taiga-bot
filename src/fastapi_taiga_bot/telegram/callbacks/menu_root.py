from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.telegram.callbacks.base import TelegramCallback
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.menu_content import MenuContentService, get_menu_content
from fastapi_taiga_bot.taiga.models import TaigaSession


class MenuRootCallback(TelegramCallback):
    data = "menu:root"

    def __init__(self, client: TelegramClient, menu_content: MenuContentService, session: AsyncSession):
        self._client = client
        self._menu_content = menu_content
        self._session = session

    async def handle(self, update: TelegramUpdate) -> None:
        message = update.callback_query.message
        chat_id = message.chat.id

        taiga_session = await self._session.get(TaigaSession, chat_id)
        menu = self._menu_content.build_root_menu(taiga_session is not None)

        await self._client.edit_message_text(
            chat_id, message.message_id, menu["text"], menu["reply_markup"]
        )


def get_menu_root_callback(
    client: TelegramClient = Depends(get_telegram_client),
    menu_content: MenuContentService = Depends(get_menu_content),
    session: AsyncSession = Depends(get_session),
) -> MenuRootCallback:
    return MenuRootCallback(client, menu_content, session)
