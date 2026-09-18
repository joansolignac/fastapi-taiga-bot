from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_taiga_bot.db.engine import get_session
from fastapi_taiga_bot.telegram.callbacks.base import TelegramCallback
from fastapi_taiga_bot.telegram.client import TelegramClient, get_telegram_client
from fastapi_taiga_bot.telegram.schemas.update import TelegramUpdate
from fastapi_taiga_bot.telegram.services.menu_anchor import upsert_menu_anchor
from fastapi_taiga_bot.telegram.services.menu_content import MenuContentService, get_menu_content
from fastapi_taiga_bot.telegram.services.message_log import clear_chat_history, log_message
from fastapi_taiga_bot.taiga.services.auth_service import TaigaAuthService, get_taiga_auth_service


class AuthLogoutCallback(TelegramCallback):
    data = "auth:logout"

    def __init__(
        self,
        client: TelegramClient,
        menu_content: MenuContentService,
        auth_service: TaigaAuthService,
        session: AsyncSession,
    ):
        self._client = client
        self._menu_content = menu_content
        self._auth_service = auth_service
        self._session = session

    async def handle(self, update: TelegramUpdate) -> None:
        message = update.callback_query.message
        chat_id = message.chat.id

        await self._auth_service.logout(self._session, chat_id)
        # This also deletes `message` itself (already logged when it was first
        # sent/edited), so the menu below has to be a new message, not an edit.
        await clear_chat_history(self._session, self._client, chat_id)

        menu = self._menu_content.build_root_menu(False)
        message_id = await self._client.send_message(chat_id, menu["text"], menu["reply_markup"])
        await log_message(self._session, chat_id, message_id)
        await upsert_menu_anchor(self._session, chat_id, message_id)


def get_auth_logout_callback(
    client: TelegramClient = Depends(get_telegram_client),
    menu_content: MenuContentService = Depends(get_menu_content),
    auth_service: TaigaAuthService = Depends(get_taiga_auth_service),
    session: AsyncSession = Depends(get_session),
) -> AuthLogoutCallback:
    return AuthLogoutCallback(client, menu_content, auth_service, session)
